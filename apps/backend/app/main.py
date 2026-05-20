import os
from pathlib import Path

from dotenv import load_dotenv

# Must run before any app.* imports — database.py reads env vars at module level.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import pdfs, retell, sessions

app = FastAPI(
    title="Voice to PDF API",
    version="0.2.0",
    description="Voice-driven PDF form-filling — powered by Supabase + FastAPI",
)

origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pdfs.router,     prefix="/pdfs",     tags=["pdfs"])
app.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
app.include_router(retell.router, prefix="/retell-llm-websocket", tags=["retell"])


@app.get("/")
async def root() -> dict:
    return {"message": "Voice to PDF API", "version": "0.2.0"}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
