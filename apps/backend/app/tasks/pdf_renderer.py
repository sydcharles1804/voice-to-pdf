"""Celery task: render a filled PDF from a completed session.

Triggered by POST /sessions/:id/complete. Runs in a separate worker process,
so it never blocks the API server.

State transitions written to sessions.pdf_status:
  pending → rendering → done     (happy path)
                      ↘ failed   (all retries exhausted)
"""

import logging

from celery import Task

from celery_app import celery
from app.database import get_admin_client
from app.services.pdf_filler import fill_pdf

logger = logging.getLogger(__name__)

_TEMPLATE_BUCKET  = "pdf-templates"
_OUTPUT_BUCKET    = "completed-pdfs"


def _set_pdf_status(session_id: str, pdf_status: str) -> None:
    """Write pdf_status to the DB. Swallows errors so it never masks the root cause."""
    try:
        get_admin_client().table("sessions").update(
            {"pdf_status": pdf_status}
        ).eq("id", session_id).execute()
    except Exception as exc:
        logger.warning("Could not update pdf_status for %s: %s", session_id, exc)


@celery.task(
    bind=True,
    max_retries=3,
    name="app.tasks.pdf_renderer.render_pdf",
    # Exponential backoff: 30 s, 60 s, 120 s between retries.
    # Overridden per retry via self.retry(countdown=...).
)
def render_pdf(self: Task, session_id: str) -> dict:
    """Fetch session answers, fill the PDF template, and upload the result.

    Args:
        session_id: UUID of the session row to process.

    Returns:
        {"session_id": ..., "output_path": ...} on success.

    The function is idempotent: if the output already exists in storage and
    the DB already shows pdf_status=done, it returns early without re-uploading.
    """
    logger.info("render_pdf started | session=%s attempt=%d", session_id, self.request.retries + 1)
    admin = get_admin_client()

    try:
        # ── Mark as rendering ────────────────────────────────────────────────
        _set_pdf_status(session_id, "rendering")

        # ── Fetch session ────────────────────────────────────────────────────
        session_res = (
            admin.table("sessions")
            .select("user_id, pdf_id, pdf_status")
            .eq("id", session_id)
            .single()
            .execute()
        )
        if not session_res.data:
            raise ValueError(f"Session {session_id} not found")

        session = session_res.data

        # Idempotency guard — don't re-render if already done.
        if session.get("pdf_status") == "done":
            logger.info("render_pdf skipped (already done) | session=%s", session_id)
            return {"session_id": session_id, "skipped": True}

        user_id = session["user_id"]
        pdf_id  = session["pdf_id"]

        # ── Fetch PDF template metadata ──────────────────────────────────────
        pdf_res = (
            admin.table("pdfs")
            .select("storage_path")
            .eq("id", pdf_id)
            .single()
            .execute()
        )
        if not pdf_res.data:
            raise ValueError(f"PDF template {pdf_id} not found")

        template_path = pdf_res.data["storage_path"]

        # ── Fetch field answers ──────────────────────────────────────────────
        answers_res = (
            admin.table("field_answers")
            .select("field_name, answer")
            .eq("session_id", session_id)
            .execute()
        )
        answers: dict[str, str] = {
            row["field_name"]: row["answer"] or ""
            for row in (answers_res.data or [])
        }

        # ── Download template from Storage ───────────────────────────────────
        template_bytes: bytes = (
            admin.storage.from_(_TEMPLATE_BUCKET).download(template_path)
        )

        # ── Fill fields ──────────────────────────────────────────────────────
        filled_bytes = fill_pdf(template_bytes, answers)

        # ── Upload filled PDF ────────────────────────────────────────────────
        # Convention: {user_id}/{session_id}.pdf in completed-pdfs bucket.
        output_path = f"{user_id}/{session_id}.pdf"
        admin.storage.from_(_OUTPUT_BUCKET).upload(
            path=output_path,
            file=filled_bytes,
            file_options={"content-type": "application/pdf", "upsert": "true"},
        )

        # ── Persist result ───────────────────────────────────────────────────
        admin.table("sessions").update({
            "pdf_status":  "done",
            "output_path": output_path,
        }).eq("id", session_id).execute()

        logger.info("render_pdf done | session=%s output=%s", session_id, output_path)
        return {"session_id": session_id, "output_path": output_path}

    except Exception as exc:
        logger.error("render_pdf error | session=%s attempt=%d error=%s",
                     session_id, self.request.retries + 1, exc)

        retries_left = self.max_retries - self.request.retries
        if retries_left > 0:
            # Exponential backoff: 30 s → 60 s → 120 s
            countdown = 30 * (2 ** self.request.retries)
            logger.info("render_pdf retrying in %ds | session=%s", countdown, session_id)
            raise self.retry(exc=exc, countdown=countdown)

        # All retries exhausted — mark permanently failed.
        _set_pdf_status(session_id, "failed")
        logger.error("render_pdf permanently failed | session=%s", session_id)
        raise
