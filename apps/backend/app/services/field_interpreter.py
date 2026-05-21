"""LLM-powered field interpretation — runs once at PDF upload time.

Raw PDF field names and labels are often garbled tooltips or internal
identifiers (e.g. "enter along with your them name: to a meeting with you."
or "Prop_Addr_1").  This module sends the full field list to the LLM in a
single call and gets back:

  - form_type:    What kind of form this is ("Real Estate Purchase Agreement",
                  "Medical Intake Form", "Employment Application", etc.)
  - clean_label:  A short, human-readable field label (2–5 words)
  - question:     The exact spoken question the voice agent should ask

Results are merged back into the field schema and stored in pdfs.fields so
every downstream consumer (voice agent, prompt builder) uses clean data.
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a form-analysis expert. You will be given a list of PDF form fields \
(their internal names, raw labels, and types). Your job is to:

1. Identify what type of form this is (be specific — e.g. "Real Estate Purchase \
Agreement", "Medical Patient Intake Form", "W-9 Tax Form", "Job Application").

2. For EACH field provide:
   - clean_label: A short, natural human-readable label (2–5 words max). \
Strip any garbled tooltip text. Use the field name as a guide if the label \
is nonsense.
   - question: The exact question a voice agent should speak to collect this \
field's value. Make it natural, conversational, and specific to the form type. \
For a dropdown/radio, list the options in the question. For a checkbox, ask \
"Yes or No". For a date, mention the format.

Return ONLY a raw JSON object — no markdown, no explanation — in this format:
{
  "form_type": "...",
  "fields": [
    {"name": "<exact field name>", "clean_label": "...", "question": "..."},
    ...
  ]
}
"""


def interpret_fields(fields: list[dict]) -> dict:
    """Enhance field labels and generate spoken questions using an LLM.

    Args:
        fields: Canonical field schema list (from build_field_schema).

    Returns:
        {"form_type": str, "fields": [{name, clean_label, question}, ...]}
        On failure returns an empty dict — callers fall back to raw labels.
    """
    if not fields:
        return {}

    field_descriptions = _format_fields_for_llm(fields)

    user_message = (
        f"Here are the form fields:\n\n{field_descriptions}\n\n"
        "Return the JSON object as instructed."
    )

    from app.services.ai_agent import chat as ai_chat  # noqa: PLC0415

    try:
        raw = ai_chat(_SYSTEM_PROMPT, [{"role": "user", "content": user_message}])
        result = _parse_json(raw)
        if not result or "fields" not in result:
            logger.warning("Field interpreter returned unexpected structure")
            return {}
        logger.info("Field interpreter done | form_type=%s fields=%d",
                    result.get("form_type", "unknown"), len(result["fields"]))
        return result
    except Exception as exc:
        logger.error("Field interpreter failed: %s", exc)
        return {}


def apply_interpretation(fields: list[dict], interpretation: dict) -> list[dict]:
    """Merge LLM interpretation back into the field schema list.

    Updates each field in-place with clean_label and question.
    Falls back to the original label if a field is not found in the result.
    """
    if not interpretation or "fields" not in interpretation:
        return fields

    lookup = {
        item["name"]: item
        for item in interpretation["fields"]
        if isinstance(item, dict) and "name" in item
    }

    for field in fields:
        interp = lookup.get(field["name"])
        if not interp:
            continue
        if interp.get("clean_label"):
            field["clean_label"] = interp["clean_label"]
        if interp.get("question"):
            field["question"] = interp["question"]

    return fields


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_fields_for_llm(fields: list[dict]) -> str:
    lines = []
    for f in fields:
        name  = f["name"]
        label = f.get("label") or name
        ftype = f.get("type", "text")
        opts  = f.get("options") or []
        line  = f'name="{name}" | label="{label}" | type={ftype}'
        if opts:
            line += f' | options={opts}'
        lines.append(f"- {line}")
    return "\n".join(lines)


def _parse_json(text: str) -> dict:
    text = text.strip()
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass
    return {}
