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


class PDFField(BaseModel):
    name: str
    type: str                        # text | checkbox | dropdown | signature
    label: str
    required: bool = False
    options: list[str] = []          # non-empty for dropdown fields


class PDF(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    original_name: str
    storage_path: str
    file_size: Optional[int] = None
    page_count: Optional[int] = None
    field_count: Optional[int] = None
    fields: list[PDFField] = []
    created_at: datetime
    updated_at: datetime


class PDFUploadResponse(BaseModel):
    pdf_id: str
    field_count: int
    fields: list[PDFField]


class Session(BaseModel):
    id: UUID
    user_id: UUID
    pdf_id: UUID
    status: SessionStatus
    pdf_status: Optional[PDFRenderStatus] = None  # None until session is completed
    output_path: Optional[str] = None
    fields_total: Optional[int] = None
    fields_answered: int = 0
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


# ─── Request bodies ────────────────────────────────────────────────────────────

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
