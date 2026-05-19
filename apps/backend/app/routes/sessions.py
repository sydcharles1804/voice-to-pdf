import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import get_current_user
from app.database import get_client

logger = logging.getLogger(__name__)
from app.models import (
    ApiResponse,
    CompleteSessionRequest,
    CreateSessionRequest,
    FieldAnswer,
    Session,
    SessionDetail,
    SubmitAnswerRequest,
)

router = APIRouter()


# ─── POST /sessions ────────────────────────────────────────────────────────────

@router.post("/", response_model=ApiResponse[Session], status_code=status.HTTP_201_CREATED)
async def create_session(
    body: CreateSessionRequest,
    ctx: dict = Depends(get_current_user),
) -> dict:
    """Start a new voice-fill session for a PDF.

    Copies field_count from the PDF row into fields_total so progress can be
    tracked without re-querying the pdfs table on every answer.
    """
    db = get_client(ctx["token"])
    user_id = str(ctx["user"].id)

    # Verify the PDF exists and belongs to the caller (RLS enforces ownership,
    # but we need field_count to populate fields_total on the session).
    pdf_res = (
        db.table("pdfs")
        .select("id, field_count")
        .eq("id", str(body.pdf_id))
        .single()
        .execute()
    )
    if not pdf_res.data:
        raise HTTPException(status_code=404, detail="PDF not found")

    session_res = (
        db.table("sessions")
        .insert({
            "user_id": user_id,
            "pdf_id": str(body.pdf_id),
            "status": "active",
            "fields_total": pdf_res.data.get("field_count"),
            "fields_answered": 0,
        })
        .execute()
    )

    return {"data": session_res.data[0], "message": "Session created", "success": True}


# ─── GET /sessions/:id ────────────────────────────────────────────────────────

@router.get("/{session_id}", response_model=ApiResponse[SessionDetail])
async def get_session(
    session_id: str,
    ctx: dict = Depends(get_current_user),
) -> dict:
    """Return a session and all its field answers, ordered by answered_at."""
    db = get_client(ctx["token"])

    session_res = (
        db.table("sessions")
        .select("*")
        .eq("id", session_id)
        .single()
        .execute()
    )
    if not session_res.data:
        raise HTTPException(status_code=404, detail="Session not found")

    answers_res = (
        db.table("field_answers")
        .select("*")
        .eq("session_id", session_id)
        .order("answered_at")
        .execute()
    )

    return {
        "data": {
            "session": session_res.data,
            "answers": answers_res.data or [],
        },
        "message": "Session retrieved",
        "success": True,
    }


# ─── POST /sessions/:id/answer ────────────────────────────────────────────────

@router.post("/{session_id}/answer", response_model=ApiResponse[FieldAnswer])
async def submit_answer(
    session_id: str,
    body: SubmitAnswerRequest,
    ctx: dict = Depends(get_current_user),
) -> dict:
    """Record one field answer for an active session.

    Upserts on (session_id, field_name) — submitting the same field again
    overwrites the previous answer without creating a duplicate row.
    Only increments fields_answered when the field is answered for the first time.
    """
    db = get_client(ctx["token"])
    user_id = str(ctx["user"].id)

    # Verify the session is still active.
    session_res = (
        db.table("sessions")
        .select("id, status, fields_answered")
        .eq("id", session_id)
        .single()
        .execute()
    )
    if not session_res.data:
        raise HTTPException(status_code=404, detail="Session not found")
    if session_res.data["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session is '{session_res.data['status']}' — cannot accept new answers",
        )

    # Check whether this field already has an answer (determines counter increment).
    existing_res = (
        db.table("field_answers")
        .select("id")
        .eq("session_id", session_id)
        .eq("field_name", body.field_name)
        .execute()
    )
    is_new_field = len(existing_res.data or []) == 0

    # Upsert — the DB UNIQUE(session_id, field_name) constraint is the authority.
    answer_res = (
        db.table("field_answers")
        .upsert(
            {
                "session_id": session_id,
                "user_id": user_id,
                "field_name": body.field_name,
                "field_label": body.field_label,
                "answer": body.answer,
                "raw_transcript": body.raw_transcript,
                "confidence": body.confidence,
                "answered_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="session_id,field_name",
        )
        .execute()
    )

    if is_new_field:
        db.table("sessions").update(
            {"fields_answered": session_res.data["fields_answered"] + 1}
        ).eq("id", session_id).execute()

    return {"data": answer_res.data[0], "message": "Answer recorded", "success": True}


# ─── POST /sessions/:id/complete ──────────────────────────────────────────────

@router.post("/{session_id}/complete", response_model=ApiResponse[Session])
async def complete_session(
    session_id: str,
    body: CompleteSessionRequest,
    ctx: dict = Depends(get_current_user),
) -> dict:
    """Mark a session as completed and enqueue a background PDF render job.

    The PDF is generated asynchronously by a Celery worker. Poll
    GET /sessions/:id and check pdf_status:
      pending   → job is queued, worker hasn't started yet
      rendering → worker is actively filling the PDF
      done      → output_path is set, PDF is ready in Supabase Storage
      failed    → all retries exhausted; check worker logs
    """
    db = get_client(ctx["token"])

    session_res = (
        db.table("sessions")
        .select("id, status")
        .eq("id", session_id)
        .single()
        .execute()
    )
    if not session_res.data:
        raise HTTPException(status_code=404, detail="Session not found")
    if session_res.data["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session is already '{session_res.data['status']}'",
        )

    updated_res = (
        db.table("sessions")
        .update({
            "status":       "completed",
            "pdf_status":   "pending",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        .eq("id", session_id)
        .execute()
    )

    # Enqueue the background render job. If the broker is unavailable we log
    # the error but still return 200 — the session is already marked complete
    # in the DB and the job can be re-queued manually.
    try:
        from app.tasks.pdf_renderer import render_pdf
        render_pdf.delay(session_id)
        logger.info("render_pdf enqueued | session=%s", session_id)
    except Exception as exc:
        logger.error("Failed to enqueue render_pdf | session=%s error=%s", session_id, exc)

    return {
        "data": updated_res.data[0],
        "message": "Session completed — PDF rendering queued",
        "success": True,
    }
