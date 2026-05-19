import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.auth import get_current_user
from app.database import get_admin_client, get_client
from app.models import ApiResponse, PDFUploadResponse
from app.services.pdf_extractor import (
    MAX_BYTES,
    extract_fields,
    validate_magic,
    validate_size,
)

router = APIRouter()

_BUCKET = "pdf-templates"


@router.post(
    "/",
    response_model=ApiResponse[PDFUploadResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Upload a PDF template",
)
async def upload_pdf(
    file: UploadFile = File(..., description="PDF file, max 25 MB"),
    ctx: dict = Depends(get_current_user),
) -> dict:
    """Accept a multipart PDF upload, validate it, extract AcroForm fields,
    upload to Supabase Storage, and persist metadata in the pdfs table.

    Validation order (fail-fast, cheapest checks first):
      1. Content-Type header — quick pre-flight before reading bytes
      2. File size ≤ 25 MB
      3. Magic bytes — confirms the payload is actually a PDF regardless of
         the filename extension or Content-Type header
    """
    user_id = str(ctx["user"].id)

    # ── 1. Content-Type pre-flight ────────────────────────────────────────────
    # Rejects obviously wrong uploads without reading the body.
    content_type = (file.content_type or "").lower()
    if content_type and content_type not in ("application/pdf", "application/octet-stream", ""):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Expected a PDF file, got content-type '{content_type}'",
        )

    # ── 2. Read body ──────────────────────────────────────────────────────────
    # We read one byte more than the limit so we can give an accurate error
    # without buffering the entire oversized file into memory.
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the 25 MB limit ({len(content) / 1_048_576:.1f} MB uploaded so far)",
        )

    # ── 3. Magic bytes ────────────────────────────────────────────────────────
    try:
        validate_magic(content)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # ── 4. Field extraction ───────────────────────────────────────────────────
    try:
        page_count, fields = extract_fields(content)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not parse PDF structure: {exc}",
        )

    # ── 5. Build storage path and upload ─────────────────────────────────────
    # Convention: {user_id}/{pdf_id}.pdf  — user_id prefix lets storage RLS
    # (storage.foldername check) enforce ownership even without service role.
    pdf_id = str(uuid.uuid4())
    original_name = file.filename or "upload.pdf"
    display_name = Path(original_name).stem
    storage_path = f"{user_id}/{pdf_id}.pdf"

    # Storage uploads go through the admin client because supabase-py's storage
    # layer does not inherit the PostgREST JWT set via client.postgrest.auth().
    # The admin client is safe here: we already verified the caller is authenticated,
    # and the storage path is scoped to their user_id.
    try:
        get_admin_client().storage.from_(_BUCKET).upload(
            path=storage_path,
            file=content,
            file_options={"content-type": "application/pdf"},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Storage upload failed: {exc}",
        )

    # ── 6. Persist metadata via user-scoped client (RLS applies) ─────────────
    try:
        db = get_client(ctx["token"])
        pdf_res = (
            db.table("pdfs")
            .insert({
                "id": pdf_id,
                "user_id": user_id,
                "name": display_name,
                "original_name": original_name,
                "storage_path": storage_path,
                "file_size": len(content),
                "page_count": page_count,
                "field_count": len(fields),
                "fields": fields,
            })
            .execute()
        )
    except Exception as exc:
        # Best-effort: remove the orphaned storage object so we don't leak files.
        try:
            get_admin_client().storage.from_(_BUCKET).remove([storage_path])
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database insert failed: {exc}",
        )

    return {
        "data": {
            "pdf_id": pdf_res.data[0]["id"],
            "field_count": len(fields),
            "fields": fields,
        },
        "message": f"PDF uploaded — {len(fields)} fillable field(s) detected",
        "success": True,
    }
