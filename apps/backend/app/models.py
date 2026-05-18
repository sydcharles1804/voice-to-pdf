from datetime import datetime
from typing import Generic, Literal, Optional, TypeVar

from pydantic import BaseModel

# Mirror the TypeScript types in packages/types/src/index.ts
RecordingStatus = Literal["idle", "recording", "paused", "stopped"]
TranscriptionStatus = Literal["pending", "processing", "completed", "failed"]
PDFStatus = Literal["pending", "generating", "completed", "failed"]

T = TypeVar("T")


class AudioRecording(BaseModel):
    id: str
    user_id: str
    filename: str
    duration: float
    file_size: int
    mime_type: str
    status: RecordingStatus
    created_at: datetime
    updated_at: datetime


class TranscriptionResult(BaseModel):
    id: str
    recording_id: str
    text: str
    language: str
    confidence: float
    status: TranscriptionStatus
    word_count: int
    created_at: datetime
    updated_at: datetime


class PDFDocument(BaseModel):
    id: str
    transcription_id: str
    user_id: str
    filename: str
    file_size: int
    page_count: int
    status: PDFStatus
    download_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ApiResponse(BaseModel, Generic[T]):
    data: T
    message: str
    success: bool


class ApiError(BaseModel):
    message: str
    code: str
    status_code: int
