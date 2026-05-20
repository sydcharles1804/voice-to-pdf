import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import get_current_user
from app.database import get_admin_client, get_client

logger = logging.getLogger(__name__)
from app.models import (
    ApiResponse,
    ChatRequest,
    ChatResponse,
    CompleteSessionRequest,
    CreateSessionRequest,
    ExtractRequest,
    FieldAnswer,
    MapResult,
    Session,
    SessionDetail,
    SkipFieldRequest,
    SubmitAnswerRequest,
)
from app.services.ai_agent import chat as ai_chat
from app.services.conversation import append_turns, derive_cursor, load_history
from app.services.field_mapper import map_field
from app.services.prompt_builder import build_system_prompt

router = APIRouter()

_OUTPUT_BUCKET  = "completed-pdfs"
_SIGNED_URL_TTL = 86_400  # 24 hours in seconds


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
    """Return a session and all its field answers, ordered by answered_at.

    When pdf_status is 'done', a fresh 24-hour signed download URL is
    injected into the session payload as ``download_url``.  The URL is
    regenerated on every request so it is never stale — signed URLs expire
    and storing them in the DB would create a 24-hour time-bomb.
    """
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

    session_data = dict(session_res.data)

    # Attach a fresh signed URL whenever the filled PDF is ready.
    if session_data.get("pdf_status") == "done" and session_data.get("output_path"):
        try:
            url_res = get_admin_client().storage.from_(_OUTPUT_BUCKET).create_signed_url(
                session_data["output_path"], _SIGNED_URL_TTL
            )
            session_data["download_url"] = (
                url_res.get("signedURL") or url_res.get("signedUrl") or None
            )
        except Exception as exc:
            logger.warning(
                "Could not generate signed URL | session=%s error=%s", session_id, exc
            )

    answers_res = (
        db.table("field_answers")
        .select("*")
        .eq("session_id", session_id)
        .order("answered_at")
        .execute()
    )

    return {
        "data": {
            "session": session_data,
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


# ─── POST /sessions/:id/skip ─────────────────────────────────────────────────

@router.post("/{session_id}/skip", response_model=ApiResponse[dict])
async def skip_field(
    session_id: str,
    body: SkipFieldRequest,
    ctx: dict = Depends(get_current_user),
) -> dict:
    """Mark an optional field as skipped for a session.

    Skipped fields are excluded from the cursor, so the AI won't ask about
    them again.  Required fields cannot be skipped — returns 409 if attempted.
    Calling skip on the same field twice is a no-op.

    The transcript panel can use this endpoint to skip fields without going
    through the voice conversation (e.g. a tap-to-skip button).
    """
    db = get_client(ctx["token"])

    session_res = (
        db.table("sessions")
        .select("id, status, pdf_id, skipped_fields")
        .eq("id", session_id)
        .single()
        .execute()
    )
    if not session_res.data:
        raise HTTPException(status_code=404, detail="Session not found")
    if session_res.data["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session is '{session_res.data['status']}' — cannot modify a non-active session",
        )

    pdf_id = session_res.data["pdf_id"]

    pdf_res = (
        db.table("pdfs")
        .select("fields")
        .eq("id", pdf_id)
        .single()
        .execute()
    )
    if not pdf_res.data:
        raise HTTPException(status_code=404, detail="PDF not found")

    fields: list[dict] = pdf_res.data.get("fields") or []
    field = next((f for f in fields if f["name"] == body.field_name), None)
    if field is None:
        raise HTTPException(
            status_code=404,
            detail=f"Field '{body.field_name}' not found in this PDF's schema",
        )
    if field.get("required", False):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Field '{field.get('label') or body.field_name}' is required and cannot be skipped",
        )

    current_skipped: list[str] = session_res.data.get("skipped_fields") or []
    if body.field_name not in current_skipped:
        updated_skipped = current_skipped + [body.field_name]
        db.table("sessions").update(
            {"skipped_fields": updated_skipped}
        ).eq("id", session_id).execute()
    else:
        updated_skipped = current_skipped

    return {
        "data": {"skipped_fields": updated_skipped},
        "message": f"Field '{field.get('label') or body.field_name}' skipped",
        "success": True,
    }


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


# ─── POST /sessions/:id/chat ──────────────────────────────────────────────────

@router.post("/{session_id}/chat", response_model=ApiResponse[ChatResponse])
async def chat(
    session_id: str,
    body: ChatRequest,
    ctx: dict = Depends(get_current_user),
) -> dict:
    """One turn of the AI form-filling conversation.

    The system prompt is rebuilt on every call so it always reflects the
    current answered/unanswered state.  Conversation history is stored
    server-side (sliding window of 8 turns) — the client only sends the
    current user message.

    Typical client loop:
        1. User speaks → transcript sent as ``message``
        2. This endpoint returns the AI's reply (next question or confirmation)
        3. Client plays reply via TTS
        4. When the AI confirms a value, client calls POST /sessions/:id/answer
        5. Repeat until all fields answered, then POST /sessions/:id/complete
    """
    db = get_client(ctx["token"])

    # ── Verify the session is still active; load stored history ───────────────
    session_res = (
        db.table("sessions")
        .select("id, status, pdf_id, conversation_history, skipped_fields")
        .eq("id", session_id)
        .single()
        .execute()
    )
    if not session_res.data:
        raise HTTPException(status_code=404, detail="Session not found")
    if session_res.data["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session is '{session_res.data['status']}' — chat is only available for active sessions",
        )

    pdf_id        = session_res.data["pdf_id"]
    history       = load_history(session_res.data)
    skipped_names = set(session_res.data.get("skipped_fields") or [])

    # ── Load field schema (stored once at upload time — no re-extraction) ─────
    pdf_res = (
        db.table("pdfs")
        .select("fields")
        .eq("id", pdf_id)
        .single()
        .execute()
    )
    if not pdf_res.data:
        raise HTTPException(status_code=404, detail="PDF not found")

    fields: list[dict] = pdf_res.data.get("fields") or []

    # ── Which fields are already answered for this session? ───────────────────
    answers_res = (
        db.table("field_answers")
        .select("field_name")
        .eq("session_id", session_id)
        .execute()
    )
    answered_names = {row["field_name"] for row in (answers_res.data or [])}

    # ── Derive cursor: which field to ask about next ───────────────────────────
    current_field, current_field_index = derive_cursor(fields, answered_names, skipped_names)

    # ── Build system prompt with live progress and current task ───────────────
    system_prompt = build_system_prompt(
        fields,
        answered_names,
        skipped_names=skipped_names,
        current_field=current_field,
        current_field_index=current_field_index,
    )

    # ── Build messages: stored history + new user turn ────────────────────────
    messages = history + [{"role": "user", "content": body.message}]

    try:
        reply = ai_chat(system_prompt, messages)
    except RuntimeError as exc:
        logger.error("AI chat config error | session=%s error=%s", session_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is not available. Please contact support.",
        )
    except Exception as exc:
        logger.error("AI chat error | session=%s error=%s", session_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service returned an unexpected error.",
        )

    # ── Persist the new turns (sliding window) ────────────────────────────────
    new_history = append_turns(
        history,
        [
            {"role": "user",      "content": body.message},
            {"role": "assistant", "content": reply},
        ],
    )
    db.table("sessions").update(
        {"conversation_history": new_history}
    ).eq("id", session_id).execute()

    return {
        "data": {"reply": reply},
        "message": "Reply generated",
        "success": True,
    }


# ─── POST /sessions/:id/extract ───────────────────────────────────────────────

@router.post("/{session_id}/extract", response_model=ApiResponse[MapResult])
async def extract_field(
    session_id: str,
    body: ExtractRequest,
    ctx: dict = Depends(get_current_user),
) -> dict:
    """Extract and normalize one field's value from a raw voice transcript.

    Call this after the user speaks an answer and the speech-to-text transcript
    is available.  The field mapper uses a focused LLM prompt to normalize the
    raw text into the format required by the target field (date → YYYY-MM-DD,
    checkbox → yes/no, dropdown → exact option string, etc.).

    Client workflow:
        1. User speaks → transcript arrives
        2. Call POST /sessions/:id/extract with field_name + transcript
        3. If needs_clarification == false and confidence is acceptable:
               POST /sessions/:id/answer with the normalized value
        4. If needs_clarification == true:
               Pass clarification_hint to the AI agent so it asks the user to rephrase
    """
    db = get_client(ctx["token"])

    # ── Verify the session is active ────────────────────────────────────────
    session_res = (
        db.table("sessions")
        .select("id, status, pdf_id")
        .eq("id", session_id)
        .single()
        .execute()
    )
    if not session_res.data:
        raise HTTPException(status_code=404, detail="Session not found")
    if session_res.data["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Session is '{session_res.data['status']}' — extraction only available for active sessions",
        )

    pdf_id = session_res.data["pdf_id"]

    # ── Load field schema and locate the target field ────────────────────────
    pdf_res = (
        db.table("pdfs")
        .select("fields")
        .eq("id", pdf_id)
        .single()
        .execute()
    )
    if not pdf_res.data:
        raise HTTPException(status_code=404, detail="PDF not found")

    fields: list[dict] = pdf_res.data.get("fields") or []
    field = next((f for f in fields if f["name"] == body.field_name), None)
    if field is None:
        raise HTTPException(
            status_code=404,
            detail=f"Field '{body.field_name}' not found in this PDF's schema",
        )

    # ── Run the field mapper ─────────────────────────────────────────────────
    # map_field never raises — failures return needs_clarification=True.
    result = map_field(transcript=body.transcript, field=field)

    logger.info(
        "extract_field | session=%s field=%s confidence=%.2f needs_clarification=%s",
        session_id, body.field_name, result["confidence"], result["needs_clarification"],
    )

    return {
        "data": result,
        "message": "Field extracted",
        "success": True,
    }
