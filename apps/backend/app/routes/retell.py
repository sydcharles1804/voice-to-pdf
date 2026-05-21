"""WebSocket endpoint for Retell AI Custom LLM integration.

Retell connects here when a web call starts.  The protocol:
  1. Retell sends ``call_details``  — we extract session_id and validate
  2. Retell sends ``response_required`` whenever the user finishes speaking
     (or the call opens and the agent should speak first)
  3. We reply with the LLM's text; Retell converts it to speech via TTS

Session context (field schema, answered fields, conversation history) is
loaded from the DB on every turn — no in-process state is kept between
turns so multiple concurrent calls are safe.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.database import get_admin_client
from app.services.ai_agent import chat as ai_chat
from app.services.conversation import append_turns, derive_cursor, load_history
from app.services.field_mapper import map_field
from app.services.prompt_builder import build_system_prompt

logger = logging.getLogger(__name__)
router = APIRouter()

# Sent to the LLM when the call opens and the agent should speak first
# (Retell sends response_required with an empty transcript on agent-first calls).
_AGENT_FIRST_TRIGGER = (
    "The voice call has just connected. "
    "Greet the user warmly, tell them you will help them fill out the form, "
    "and immediately ask about the first field."
)


@router.websocket("/{call_id}")
async def retell_llm_websocket(websocket: WebSocket, call_id: str) -> None:
    """Retell Custom LLM WebSocket handler.

    Retell connects to {base_url}/{call_id} for every call.
    The call_id comes from the path; session_id comes from call_details.
    All turns of the call flow through this single persistent connection.
    The handler is stateless between calls — all state lives in the DB.
    """
    await websocket.accept()
    session_id: str | None = None

    try:
        db = get_admin_client()
    except Exception as exc:
        logger.error("Retell WS: failed to get admin client — %s", exc)
        await websocket.close(code=1011, reason="internal error")
        return

    # Resolve session_id from the call_id in the URL path.
    logger.info("Retell WS: looking up session for call_id=%s", call_id)
    try:
        session_res = (
            db.table("sessions")
            .select("id")
            .eq("retell_call_id", call_id)
            .maybe_single()
            .execute()
        )
        if session_res and session_res.data:
            session_id = session_res.data["id"]
            logger.info("Retell call connected | call=%s session=%s", call_id, session_id)
        else:
            logger.warning("Retell WS: no session found for call_id=%s — will wait for call_details", call_id)
    except Exception as exc:
        logger.warning("Retell WS: session lookup error for call_id=%s error=%s", call_id, exc)

    try:
        async for raw in websocket.iter_json():
            interaction_type: str = raw.get("interaction_type", "")
            logger.debug("Retell WS message | type=%s session=%s", interaction_type, session_id)

            # ── 1. call_details — update session_id if not already resolved ──
            if interaction_type == "call_details":
                if not session_id:
                    dynamic_vars: dict = (
                        (raw.get("call") or {}).get("retell_llm_dynamic_variables") or {}
                    )
                    session_id = dynamic_vars.get("session_id")
                    if session_id:
                        logger.info("Retell call_details | session=%s", session_id)
                    else:
                        logger.warning("Retell WS: no session_id in call_details — closing")
                        await websocket.close(code=1008, reason="session_id required")
                        return

            # ── 2. response_required / reminder_required — generate LLM reply ─
            elif interaction_type in ("response_required", "reminder_required"):
                if not session_id:
                    logger.warning(
                        "Retell WS: %s with no session_id — closing", interaction_type
                    )
                    await websocket.close(code=1008, reason="session_id required")
                    return

                response_id: int     = raw.get("response_id", 0)
                transcript:  list    = raw.get("transcript") or []

                # Extract the latest user turn from Retell's live transcript.
                # If transcript is empty the agent speaks first — use a synthetic trigger.
                user_message: str = next(
                    (
                        t.get("content", "").strip()
                        for t in reversed(transcript)
                        if t.get("role") == "user"
                    ),
                    "",
                )

                reply = _generate_reply(db, session_id, user_message)

                await websocket.send_json({
                    "response_type":    "response",
                    "response_id":      response_id,
                    "content":          reply,
                    "content_complete": True,
                    "end_call":         False,
                })

    except WebSocketDisconnect:
        logger.info("Retell call disconnected | session=%s", session_id)
    except Exception as exc:
        logger.error("Retell WS unhandled error | session=%s error=%s", session_id, exc)


# ── Private helpers ────────────────────────────────────────────────────────────

def _generate_reply(db, session_id: str, user_message: str) -> str:
    """Load session state, run the LLM, persist the new turns, return reply text.

    Never raises — any failure returns a graceful fallback so the call stays
    alive and Retell has something to speak to the user.
    """
    try:
        return _process_turn(db, session_id, user_message)
    except Exception as exc:
        logger.error(
            "Retell reply generation failed | session=%s error=%s", session_id, exc
        )
        return "I'm sorry, I ran into a problem. Could you please repeat that?"


def _process_turn(db, session_id: str, user_message: str) -> str:
    """Core turn logic — mirrors POST /sessions/:id/chat but uses the admin client."""

    # ── Load session ──────────────────────────────────────────────────────────
    session_res = (
        db.table("sessions")
        .select("status, pdf_id, user_id, conversation_history, skipped_fields")
        .eq("id", session_id)
        .single()
        .execute()
    )

    if not session_res.data:
        return "I can't find your session. Please restart the form."

    if session_res.data["status"] != "active":
        return "This session is no longer active. Please start a new one."

    pdf_id        = session_res.data["pdf_id"]
    history       = load_history(session_res.data)
    skipped_names = set(session_res.data.get("skipped_fields") or [])

    # ── Load field schema ─────────────────────────────────────────────────────
    pdf_res = (
        db.table("pdfs")
        .select("fields")
        .eq("id", pdf_id)
        .single()
        .execute()
    )
    fields: list[dict] = (pdf_res.data or {}).get("fields") or []

    # ── Which fields are already answered? ────────────────────────────────────
    answers_res = (
        db.table("field_answers")
        .select("field_name")
        .eq("session_id", session_id)
        .execute()
    )
    answered_names = {r["field_name"] for r in (answers_res.data or [])}

    # ── Rebuild prompt and derive cursor ──────────────────────────────────────
    current_field, current_field_index = derive_cursor(fields, answered_names, skipped_names)

    system_prompt = build_system_prompt(
        fields,
        answered_names,
        skipped_names=skipped_names,
        current_field=current_field,
        current_field_index=current_field_index,
    )

    # ── Build message list ────────────────────────────────────────────────────
    effective_message = user_message if user_message else _AGENT_FIRST_TRIGGER
    messages = history + [{"role": "user", "content": effective_message}]

    # ── Call LLM ─────────────────────────────────────────────────────────────
    reply = ai_chat(system_prompt, messages)

    # ── Mid-call answer saving ────────────────────────────────────────────────
    # Save confirmed answers immediately so the next turn's prompt reflects them.
    if user_message and current_field:
        _try_save_answer(db, session_id, session_res.data.get("user_id", ""), user_message, current_field, reply)

    # ── Persist new turns (sliding window) ────────────────────────────────────
    if user_message:
        new_history = append_turns(
            history,
            [
                {"role": "user",      "content": user_message},
                {"role": "assistant", "content": reply},
            ],
        )
        db.table("sessions").update(
            {"conversation_history": new_history}
        ).eq("id", session_id).execute()

    return reply


def _try_save_answer(
    db, session_id: str, user_id: str,
    user_message: str, field: dict, reply: str,
) -> None:
    """Save a confirmed answer mid-call if the LLM reply contains a confirmation.

    Looks for "I'll record [value]" or "I'll update [label] to [value]" in the
    reply. If found, runs the value through map_field() and upserts to field_answers.
    """
    # Match: "I'll record "X" for Y" or "I'll update Y to "X""
    patterns = [
        r"""I['']ll record ["“]?(.+?)["”]? for """,
        r"""I['']ll update .+? to ["“]?(.+?)["”]?[.\n]""",
        r"""recording ["“]?(.+?)["”]? for """,
    ]
    raw_value: str | None = None
    for pattern in patterns:
        m = re.search(pattern, reply, re.IGNORECASE)
        if m:
            raw_value = m.group(1).strip()
            break

    if not raw_value:
        return

    try:
        result = map_field(transcript=raw_value, field=field)
        if result["needs_clarification"] or result["value"] is None:
            return

        db.table("field_answers").upsert(
            {
                "session_id":     session_id,
                "user_id":        user_id,
                "field_name":     field["name"],
                "field_label":    field.get("label") or field["name"],
                "answer":         result["value"],
                "raw_transcript": raw_value,
                "confidence":     result["confidence"],
                "answered_at":    datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="session_id,field_name",
        ).execute()

        logger.info(
            "Mid-call answer saved | session=%s field=%s value=%s",
            session_id, field["name"], result["value"],
        )
    except Exception as exc:
        logger.warning("Mid-call answer save failed | session=%s field=%s error=%s",
                       session_id, field["name"], exc)
