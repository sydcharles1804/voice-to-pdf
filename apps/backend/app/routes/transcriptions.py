from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class TranscribeRequest(BaseModel):
    recording_id: str
    language: str = "en"


@router.post("/")
async def create_transcription(body: TranscribeRequest) -> dict:
    return {
        "data": {
            "id": "placeholder",
            "recording_id": body.recording_id,
            "language": body.language,
            "status": "pending",
        },
        "message": "Transcription queued",
        "success": True,
    }


@router.get("/{transcription_id}")
async def get_transcription(transcription_id: str) -> dict:
    raise HTTPException(status_code=404, detail="Transcription not found")


@router.post("/{transcription_id}/generate-pdf")
async def generate_pdf(transcription_id: str) -> dict:
    raise HTTPException(status_code=404, detail="Transcription not found")
