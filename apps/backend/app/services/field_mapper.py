"""Extract and normalize one form field value from a raw voice transcript.

Distinct from the conversational chat agent — this is a focused, one-shot
extraction call that returns structured JSON rather than a prose reply.

Usage:
    result = map_field("my birthday is March 4th 1985", field_schema_dict)
    # {"value": "1985-03-04", "confidence": 0.95, "needs_clarification": False, ...}
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from app.services.ai_agent import chat as ai_chat

logger = logging.getLogger(__name__)

# ── Type-specific extraction rules ────────────────────────────────────────────
# Injected verbatim into the extraction prompt so the LLM knows the exact
# output format required for each field type.
_TYPE_RULES: dict[str, str] = {
    "text": (
        "Return the answer as clean, trimmed plain text. Remove filler words "
        "('um', 'uh', 'like') but preserve all meaningful content."
    ),
    "date": (
        "Return the date in YYYY-MM-DD (ISO 8601). Convert natural language: "
        "'March 4th 1985' → '1985-03-04', 'last Tuesday' requires the actual "
        "calendar date — if you cannot determine the year or month precisely, "
        "set needsClarification to true."
    ),
    "checkbox": (
        'Return exactly "yes" or "no". Map any affirmative ("correct", '
        '"true", "agree", "yep", "sure") to "yes"; anything negative to "no".'
    ),
    "dropdown": (
        "Return exactly one of the valid options listed below. "
        "Match case-insensitively but output the value exactly as listed. "
        "If the transcript does not clearly match any option, set needsClarification."
    ),
    "radiobutton": (
        "Return exactly one of the valid options listed below. "
        "Match case-insensitively but output the value exactly as listed. "
        "If no option clearly matches, set needsClarification."
    ),
    "signature": (
        "Return the full legal name as stated. Preserve original capitalization. "
        "If the name is spelled out letter-by-letter, reconstruct the word."
    ),
}

# ── Label-pattern sub-rules for plain text fields ─────────────────────────────
# First keyword match in the lower-cased field label wins.
_LABEL_RULES: list[tuple[str, str]] = [
    ("date",    "Return in YYYY-MM-DD format (ISO 8601). If year is absent, set needsClarification."),
    ("dob",     "Date of birth — return in YYYY-MM-DD format. If year is absent, set needsClarification."),
    ("birth",   "Date of birth — return in YYYY-MM-DD format. If year is absent, set needsClarification."),
    ("phone",   "Return as (XXX) XXX-XXXX. Normalize digits spoken individually: '5 5 5 1 2 3 4' → '(555) 123-4'."),
    ("mobile",  "Return as (XXX) XXX-XXXX."),
    ("fax",     "Return as (XXX) XXX-XXXX."),
    ("email",   "Return as name@domain.com. Lower-case the entire address."),
    ("zip",     "Return as a 5-digit string, zero-padded if needed."),
    ("postal",  "Return as a 5-digit string, zero-padded if needed."),
    ("ssn",     "Return in XXX-XX-XXXX format. Treat digit groups spoken separately."),
    ("ein",     "Return in XX-XXXXXXX format."),
    ("amount",  "Return as a plain number without currency symbols or commas (e.g. '50000')."),
    ("salary",  "Return as a plain number without currency symbols or commas."),
    ("income",  "Return as a plain number without currency symbols or commas."),
    ("percent", "Return as a plain number between 0 and 100 (no % sign)."),
    ("url",     "Return a full URL. Prepend 'https://' if the user omitted the scheme."),
    ("website", "Return a full URL. Prepend 'https://' if the user omitted the scheme."),
]

_SYSTEM_PROMPT = """\
You are a precise form-field extraction assistant. Extract and normalize exactly \
one field's value from the voice transcript provided by the user.

Respond with ONLY a JSON object — no prose, no markdown fences, no explanation. \
Raw JSON only.

Required shape:
{
  "value": <string | null>,
  "confidence": <number 0.0–1.0>,
  "needsClarification": <boolean>,
  "clarificationHint": <string | null>
}

Confidence guide:
  1.0   Clear, complete, correct format — no ambiguity.
  0.7–0.99  Answer found; minor normalization applied (e.g. date reformatted).
  0.5–0.69  Plausible but ambiguous or only partially stated.
  < 0.5   Answer absent, contradictory, or in a completely wrong format
          — set needsClarification to true.

Set needsClarification to true whenever:
  - The answer is missing from the transcript
  - The format cannot be determined (e.g. date with no year)
  - The value does not match any listed option (for choice fields)
  - The answer is contradictory or unintelligible

clarificationHint must be a short, friendly question to ask the user when
needsClarification is true; null otherwise."""


def _extraction_rule(field: dict) -> str:
    """Return the format rule line to inject into the user message."""
    ftype = field.get("type", "text")

    if ftype == "text":
        label_lower = (field.get("label") or "").lower()
        for keyword, rule in _LABEL_RULES:
            if keyword in label_lower:
                return rule
        return _TYPE_RULES["text"]

    return _TYPE_RULES.get(ftype, _TYPE_RULES["text"])


def _build_user_message(transcript: str, field: dict) -> str:
    """Compose the user-turn message sent to the LLM."""
    label    = field.get("label") or field.get("name", "unknown")
    ftype    = field.get("type", "text")
    required = "yes" if field.get("required") else "no"
    rule     = _extraction_rule(field)

    lines = [
        f"Field:    {label}",
        f"Type:     {ftype}",
        f"Required: {required}",
        f"Format:   {rule}",
    ]

    options = field.get("options") or []
    if options and ftype in ("dropdown", "radiobutton"):
        opts_str = ", ".join(f'"{o}"' for o in options)
        lines.append(f"Options:  {opts_str}")

    lines.append("")
    lines.append(f'Transcript: "{transcript}"')

    return "\n".join(lines)


def _extract_json(text: str) -> dict | None:
    """Parse JSON from LLM output, tolerating leading/trailing prose."""
    # Try direct parse first (happy path — LLM obeyed the instruction).
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Extract the first {...} block in case the LLM added a preamble.
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


def _validate_and_sanitize(raw: dict, field: dict) -> dict:
    """Apply post-LLM validation rules and return a clean, safe result dict.

    The LLM is trusted for extraction but not for format correctness.
    This layer catches cases the model may miss:
      - dropdown/radiobutton values that don't match any option
      - date strings that aren't YYYY-MM-DD
      - confidence below the clarification threshold
    """
    value       = raw.get("value")
    confidence  = float(raw.get("confidence", 0.0))
    needs_clari = bool(raw.get("needsClarification", False))
    hint        = raw.get("clarificationHint") or None

    ftype   = field.get("type", "text")
    label   = field.get("label") or field.get("name", "this field")
    options = [str(o) for o in (field.get("options") or [])]

    # ── Choice-field option check ─────────────────────────────────────────────
    if ftype in ("dropdown", "radiobutton") and value is not None:
        # Case-insensitive match; output as the option is listed.
        lower_map = {o.lower(): o for o in options}
        canonical = lower_map.get(str(value).lower())
        if canonical:
            value = canonical
        else:
            # LLM returned something not in the list.
            needs_clari = True
            confidence  = min(confidence, 0.4)
            opts_str    = ", ".join(options)
            hint = f"Please choose one of: {opts_str}."
            value = None

    # ── Date format check ─────────────────────────────────────────────────────
    if ftype == "text" and value and "date" in (field.get("label") or "").lower():
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(value)):
            needs_clari = True
            confidence  = min(confidence, 0.4)
            hint = hint or f"Could you give the date for {label} in MM/DD/YYYY format?"
            value = None

    # ── Low-confidence gate ───────────────────────────────────────────────────
    if confidence < 0.5:
        needs_clari = True
        if not hint:
            hint = f"I didn't quite catch that. Could you repeat your answer for {label}?"

    # ── Null value always needs clarification ─────────────────────────────────
    if value is None and not needs_clari:
        needs_clari = True
        hint = hint or f"Could you provide your answer for {label}?"

    return {
        "value":              str(value) if value is not None else None,
        "confidence":         round(max(0.0, min(1.0, confidence)), 3),
        "needs_clarification": needs_clari,
        "clarification_hint": hint,
    }


def map_field(transcript: str, field: dict) -> dict[str, Any]:
    """Extract and normalize one field's value from a raw voice transcript.

    Args:
        transcript: The user's raw speech-to-text output.
        field:      A ``FieldSchema`` dict from ``pdfs.fields``.

    Returns:
        ::

            {
              "value":              str | None,   # normalized value ready to save
              "confidence":         float,         # 0.0–1.0
              "needs_clarification": bool,
              "clarification_hint": str | None,   # question to ask if clarification needed
            }

    Never raises — if the LLM call fails or returns unparseable output the
    function returns a safe ``needs_clarification=True`` fallback so the
    caller can ask the user to repeat themselves.
    """
    user_message = _build_user_message(transcript, field)

    try:
        raw_reply = ai_chat(
            system_prompt=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception as exc:
        logger.error(
            "map_field LLM call failed | field=%s error=%s",
            field.get("name"), exc,
        )
        return {
            "value":              None,
            "confidence":         0.0,
            "needs_clarification": True,
            "clarification_hint": (
                f"Sorry, I couldn't process that. "
                f"Could you repeat your answer for {field.get('label') or field.get('name')}?"
            ),
        }

    parsed = _extract_json(raw_reply)
    if parsed is None:
        logger.warning(
            "map_field JSON parse failed | field=%s reply=%r",
            field.get("name"), raw_reply[:200],
        )
        return {
            "value":              None,
            "confidence":         0.0,
            "needs_clarification": True,
            "clarification_hint": (
                f"I had trouble understanding that. "
                f"Could you repeat your answer for {field.get('label') or field.get('name')}?"
            ),
        }

    return _validate_and_sanitize(parsed, field)
