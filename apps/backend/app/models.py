from datetime import datetime
from typing import Generic, Literal, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field

T = TypeVar("T")

SessionStatus = Literal["active", "completed", "abandoned"]
PDFRenderStatus = Literal["pending", "rendering", "done", "failed"]


# ─── DB row shapes (returned by Supabase) ─────────────────────────────────────

class User(BaseModel):
    id: UUID
    email: Optional[str] = None
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class FieldCoords(BaseModel):
    x: Optional[float] = None        # left edge in PDF points (72 pt = 1 inch)
    y: Optional[float] = None        # top edge in PDF points
    width: Optional[float] = None
    height: Optional[float] = None


class FieldSchema(BaseModel):
    id: str                          # stable UUID assigned at upload time
    name: str                        # AcroForm internal key (/T)
    label: str                       # resolved human label
    type: str                        # text | checkbox | radiobutton | dropdown | signature
    required: bool = False
    options: list[str] = []          # non-empty for dropdown fields only
    pageNumber: int = 1              # 1-indexed page number
    coords: FieldCoords = FieldCoords()


class PDF(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    original_name: str
    storage_path: str
    file_size: Optional[int] = None
    page_count: Optional[int] = None
    field_count: Optional[int] = None
    fields: list[FieldSchema] = []
    created_at: datetime
    updated_at: datetime


class PDFUploadResponse(BaseModel):
    pdf_id: str
    field_count: int
    fields: list[FieldSchema]


class Session(BaseModel):
    id: UUID
    user_id: UUID
    pdf_id: UUID
    status: SessionStatus
    pdf_status: Optional[PDFRenderStatus] = None  # None until session is completed
    output_path: Optional[str] = None
    download_url: Optional[str] = None            # 24-hour signed URL, injected on GET (not stored in DB)
    fields_total: Optional[int] = None
    fields_answered: int = 0
    skipped_fields: list[str] = []
    started_at: datetime
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class FieldAnswer(BaseModel):
    id: UUID
    session_id: UUID
    user_id: UUID
    field_name: str
    field_label: Optional[str] = None
    answer: Optional[str] = None
    raw_transcript: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    answered_at: datetime
    created_at: datetime
    updated_at: datetime


# ─── Request / response bodies ────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    pdf_id: UUID


class SubmitAnswerRequest(BaseModel):
    field_name: str
    field_label: Optional[str] = None
    answer: str
    raw_transcript: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)


class CompleteSessionRequest(BaseModel):
    output_path: Optional[str] = None


class SkipFieldRequest(BaseModel):
    field_name: str                       # must match a FieldSchema.name in the session's PDF


class ChatRequest(BaseModel):
    message: str                          # the user's current transcribed message


class ChatResponse(BaseModel):
    reply: str                            # AI assistant's text reply


class ExtractRequest(BaseModel):
    field_name: str                       # must match a FieldSchema.name in the session's PDF
    transcript: str                       # raw speech-to-text from the user


class MapResult(BaseModel):
    value: Optional[str] = None           # normalized value, ready to pass to POST /answer
    confidence: float = Field(ge=0, le=1)
    needs_clarification: bool             # if True, ask the user to rephrase before saving
    clarification_hint: Optional[str] = None  # friendly follow-up question for the user


# ─── Compound response ─────────────────────────────────────────────────────────

class SessionDetail(BaseModel):
    session: Session
    answers: list[FieldAnswer]


# ─── Generic envelope ──────────────────────────────────────────────────────────

class ApiResponse(BaseModel, Generic[T]):
    data: T
    message: str
    success: bool


class ApiError(BaseModel):
    message: str
    code: str
    status_code: int
