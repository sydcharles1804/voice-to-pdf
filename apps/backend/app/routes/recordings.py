import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, UploadFile, File

router = APIRouter()


@router.get("/")
async def list_recordings() -> dict:
    return {"data": [], "message": "Recordings retrieved", "success": True}


@router.post("/upload")
async def upload_recording(file: UploadFile = File(...)) -> dict:
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="File must be an audio file")

    recording = {
        "id": str(uuid.uuid4()),
        "filename": file.filename,
        "mime_type": file.content_type,
        "status": "stopped",
        "created_at": datetime.utcnow().isoformat(),
    }

    return {"data": recording, "message": "Recording uploaded successfully", "success": True}


@router.get("/{recording_id}")
async def get_recording(recording_id: str) -> dict:
    raise HTTPException(status_code=404, detail="Recording not found")


@router.delete("/{recording_id}")
async def delete_recording(recording_id: str) -> dict:
    raise HTTPException(status_code=404, detail="Recording not found")
