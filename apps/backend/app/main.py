import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import recordings, transcriptions

load_dotenv()

app = FastAPI(
    title="Voice to PDF API",
    version="0.1.0",
    description="Convert voice recordings to PDF documents",
)

origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(recordings.router, prefix="/api/recordings", tags=["recordings"])
app.include_router(
    transcriptions.router, prefix="/api/transcriptions", tags=["transcriptions"]
)


@app.get("/")
async def root() -> dict:
    return {"message": "Voice to PDF API", "version": "0.1.0"}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
