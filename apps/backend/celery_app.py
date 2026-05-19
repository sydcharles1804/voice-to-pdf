import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery = Celery(
    "voice_to_pdf",
    broker=_REDIS_URL,
    backend=_REDIS_URL,
    include=["app.tasks.pdf_renderer"],
)

celery.conf.update(
    # Serialisation
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Reliability
    task_acks_late=True,            # ack only after the task body completes
    worker_prefetch_multiplier=1,   # one task at a time per worker thread
    task_track_started=True,        # lets callers detect the rendering state

    # Results TTL — we store status in Supabase, so we don't need Celery results long
    result_expires=3600,            # 1 hour
)
