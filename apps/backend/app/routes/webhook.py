"""Retell webhook handler — receives call lifecycle events.

Retell POSTs to this endpoint at three moments:
  call_started   → call is live (log only)
  call_ended     → call finished; full transcript available; trigger PDF render
  call_analyzed  → post-call sentiment/summary from Retell (stored for audit trail)

The x-retell-signature header is verified on every request so spoofed
events from third parties are rejected before any DB writes happen.

Add this URL in the Retell dashboard → Agent → Webhook URL:
  https://your-domain.com/webhook/retell
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.database import get_admin_client

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/retell", status_code=status.HTTP_204_NO_CONTENT)
async def retell_webhook(request: Request) -> Response:
    """Receive and process Retell call lifecycle events.

    Uses the raw request body for signature verification — do NOT parse
    the body before verifying, or the HMAC will not match.
    """
    raw_body: bytes = await request.body()
    signature: str  = request.headers.get("x-retell-signature", "")
    api_key: str    = os.getenv("RETELL_API_KEY", "")

    if not _verify_signature(raw_body, api_key, signature):
        logger.warning("Retell webhook: invalid signature — rejecting request")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    event:          str  = payload.get("event", "")
    call:           dict = payload.get("call") or {}
    retell_call_id: str  = call.get("call_id", "")

    logger.info("Retell webhook | event=%s call_id=%s", event, retell_call_id)

    if event == "call_started":
        pass  # Connection already logged by the WebSocket handler

    elif event == "call_ended":
        _handle_call_ended(retell_call_id, call)

    elif event == "call_analyzed":
        _handle_call_analyzed(retell_call_id, call)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Signature verification ─────────────────────────────────────────────────────

def _verify_signature(raw_body: bytes, api_key: str, signature: str) -> bool:
    """Return True if x-retell-signature matches the expected HMAC-SHA256.

    Tries the Retell SDK's verify() first (authoritative), then falls back
    to a manual HMAC so the endpoint works even if the SDK is unavailable.
    """
    if not api_key or not signature:
        return False

    # Preferred: let the SDK handle the exact signature format.
    try:
        from retell import Retell  # noqa: PLC0415
        return bool(Retell.verify(raw_body.decode("utf-8"), api_key, signature))
    except (ImportError, AttributeError):
        pass

    # Fallback: HMAC-SHA256, base64-encoded.
    mac      = hmac.new(api_key.encode("utf-8"), raw_body, hashlib.sha256)
    expected = base64.b64encode(mac.digest()).decode()
    return hmac.compare_digest(expected, signature)


# ── Event handlers ─────────────────────────────────────────────────────────────

def _handle_call_ended(retell_call_id: str, call: dict) -> None:
    """Store the transcript and trigger the PDF render job.

    The transcript_object is the structured audit trail (role + content +
    timestamps).  transcript is a plain text version of the same data.
    Both are stored so the review screen can display the transcript and
    the audit log has the timestamped version.

    If all required fields have answers the session is marked completed
    and the render job is enqueued.  If the call ended mid-conversation
    (some fields still unanswered) the transcript is stored but the
    session stays active so the user can continue via the web form.
    """
    if not retell_call_id:
        return

    db = get_admin_client()

    # Locate the session by the Retell call ID written at call-start time.
    session_res = (
        db.table("sessions")
        .select("id, status, pdf_id")
        .eq("retell_call_id", retell_call_id)
        .single()
        .execute()
    )
    if not session_res.data:
        logger.warning(
            "Retell webhook call_ended: no session for retell_call_id=%s", retell_call_id
        )
        return

    session_id = session_res.data["id"]
    pdf_id     = session_res.data["pdf_id"]

    # Store the full transcript regardless of completion status.
    transcript_object = call.get("transcript_object") or []
    transcript_text   = call.get("transcript") or ""

    db.table("sessions").update({
        "call_transcript":        transcript_object,  # structured — used for review screen
        "call_transcript_text":   transcript_text,    # plain text — used for search / display
    }).eq("id", session_id).execute()

    logger.info(
        "Transcript stored | session=%s turns=%d", session_id, len(transcript_object)
    )

    # Only auto-complete if the session is still active (not already completed/abandoned).
    if session_res.data["status"] != "active":
        return

    # Check whether all required fields are answered.
    pdf_res = (
        db.table("pdfs").select("fields").eq("id", pdf_id).single().execute()
    )
    fields: list[dict] = (pdf_res.data or {}).get("fields") or []
    required_names     = {f["name"] for f in fields if f.get("required", False)}

    answers_res = (
        db.table("field_answers")
        .select("field_name")
        .eq("session_id", session_id)
        .execute()
    )
    answered_names = {r["field_name"] for r in (answers_res.data or [])}

    unanswered_required = required_names - answered_names
    if unanswered_required:
        logger.info(
            "Call ended with unanswered required fields | session=%s missing=%s",
            session_id, unanswered_required,
        )
        return  # Session stays active — user can complete via web form

    # All required fields answered — mark completed and enqueue render.
    db.table("sessions").update({
        "status":       "completed",
        "pdf_status":   "pending",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", session_id).execute()

    try:
        from app.tasks.pdf_renderer import render_pdf  # noqa: PLC0415
        render_pdf.delay(session_id)
        logger.info("render_pdf enqueued from webhook | session=%s", session_id)
    except Exception as exc:
        logger.error(
            "Failed to enqueue render_pdf from webhook | session=%s error=%s",
            session_id, exc,
        )


def _handle_call_analyzed(retell_call_id: str, call: dict) -> None:
    """Store Retell's post-call analysis (sentiment, summary, custom data)."""
    if not retell_call_id:
        return

    call_analysis = call.get("call_analysis")
    if not call_analysis:
        return

    db = get_admin_client()

    session_res = (
        db.table("sessions")
        .select("id")
        .eq("retell_call_id", retell_call_id)
        .single()
        .execute()
    )
    if not session_res.data:
        return

    db.table("sessions").update({
        "call_analysis": call_analysis,
    }).eq("id", session_res.data["id"]).execute()

    logger.info("Call analysis stored | session=%s", session_res.data["id"])
