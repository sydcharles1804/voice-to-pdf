"""Extract confirmed field answers from a completed Retell call transcript.

After a voice call ends, the full conversation transcript is available.
This module handles the two-stage extraction pipeline:

  Stage 1 — Bulk extraction
    Send the entire transcript + field list to the LLM in one call.
    The LLM reads the conversation and returns the FINAL confirmed answer
    for each field, respecting corrections and skips.

  Stage 2 — Per-field normalization
    Each raw extracted answer is passed through map_field() to validate
    format, match dropdown options, and gate on confidence.
    Low-confidence or ambiguous answers are skipped rather than saved.

This approach is more reliable than trying to correlate individual
transcript turns to fields line-by-line, because the LLM can understand
corrections ("actually, change that to..."), skips, and implicit confirmations.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are extracting confirmed form field answers from a completed voice conversation.

The user filled out a form by speaking with an AI assistant. Your job is to
identify the FINAL confirmed answer for each field — the value the assistant
said it would record, after any corrections the user made.

Rules:
- If the user corrected an answer, use the MOST RECENT confirmed value.
- If a field was explicitly skipped, set its value to null.
- If a field was never reached or never confirmed, set its value to null.
- Do NOT infer, guess, or fill in values that were not stated.
- Return ONLY a raw JSON object — no markdown, no explanation.
  Keys must be the exact field_name strings provided. Values are strings or null.
"""


def extract_answers_from_transcript(
    transcript_object: list[dict],
    fields: list[dict],
) -> dict[str, str | None]:
    """Return {field_name: final_answer} extracted from the call transcript.

    Returns an empty dict on any failure — callers treat missing keys as
    unanswered fields rather than errors.

    Args:
        transcript_object: Retell's structured transcript — list of
                           {role: "agent"|"user", content: str} dicts.
        fields:            Full FieldSchema list from pdfs.fields.
    """
    if not transcript_object or not fields:
        return {}

    transcript_text = _format_transcript(transcript_object)
    fields_text     = _format_fields(fields)
    field_names     = [f["name"] for f in fields]

    user_message = (
        f"Fields to extract:\n{fields_text}\n\n"
        f"Conversation transcript:\n{transcript_text}\n\n"
        "Return a JSON object mapping each field_name to its final confirmed "
        "answer (string), or null if not answered."
    )

    from app.services.ai_agent import chat as ai_chat  # noqa: PLC0415

    try:
        raw = ai_chat(_SYSTEM_PROMPT, [{"role": "user", "content": user_message}])
        extracted = _parse_json(raw)
    except Exception as exc:
        logger.error("Transcript extraction LLM call failed: %s", exc)
        return {}

    # Keep only keys that correspond to actual field names.
    return {k: v for k, v in extracted.items() if k in field_names}


def save_extracted_answers(
    db,
    session_id: str,
    user_id: str,
    extracted: dict[str, str | None],
    fields: list[dict],
) -> int:
    """Normalize and upsert extracted answers into field_answers.

    Runs each raw answer through map_field() for format validation and
    confidence gating.  Answers that fail validation are skipped.

    Returns the count of answers successfully saved.
    """
    from app.services.field_mapper import map_field  # noqa: PLC0415

    saved = 0
    for field in fields:
        field_name = field["name"]
        raw_value  = extracted.get(field_name)

        if not raw_value:
            continue

        result = map_field(transcript=str(raw_value), field=field)

        if result["needs_clarification"] or result["value"] is None:
            logger.info(
                "Skipping low-quality extraction | session=%s field=%s confidence=%.2f",
                session_id, field_name, result["confidence"],
            )
            continue

        db.table("field_answers").upsert(
            {
                "session_id":     session_id,
                "user_id":        user_id,
                "field_name":     field_name,
                "field_label":    field.get("label") or field_name,
                "answer":         result["value"],
                "raw_transcript": str(raw_value),
                "confidence":     result["confidence"],
                "answered_at":    datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="session_id,field_name",
        ).execute()

        saved += 1

    logger.info(
        "Transcript extraction complete | session=%s saved=%d/%d",
        session_id, saved, len(fields),
    )
    return saved


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_transcript(transcript_object: list[dict]) -> str:
    lines = []
    for turn in transcript_object:
        role    = turn.get("role", "unknown").capitalize()
        content = turn.get("content", "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _format_fields(fields: list[dict]) -> str:
    lines = []
    for f in fields:
        name  = f["name"]
        label = f.get("label") or name
        ftype = f.get("type", "text")
        opts  = f.get("options") or []
        line  = f'field_name="{name}" | label="{label}" | type={ftype}'
        if opts:
            line += f' | options={opts}'
        lines.append(f"- {line}")
    return "\n".join(lines)


def _parse_json(text: str) -> dict:
    """Try json.loads first, then regex fallback for LLM preamble."""
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

    logger.warning("Could not parse extraction response: %.200s", text)
    return {}
