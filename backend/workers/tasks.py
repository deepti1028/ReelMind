"""Celery task definitions.

These are placeholders for Phase 1 — actual implementations land in Phase 2
(Steps 14-21 of the build plan).
"""

from workers.celery_app import celery_app


@celery_app.task(name="workers.tasks.process_reel", bind=True, max_retries=3)
def process_reel(self, reel_id: str) -> dict:
    """Process a saved reel end-to-end.

    Pipeline (Phase 2):
        1. Download reel audio                       — Step 15
        2. Transcribe with Groq Whisper-large-v3     — Step 16
        3. Caption + hashtag extraction (compulsory) — Step 17
        4. Classify with Groq Llama 3.3              — Step 18
        5. Confidence routing                        — Step 19
        6. Chunk + embed via sentence-transformers   — Step 20
        7. Send FCM push notification                — Step 22
    """
    # TODO: implement in Phase 2
    return {"reel_id": reel_id, "status": "stub"}


@celery_app.task(name="workers.tasks.ping")
def ping() -> str:
    """Simple smoke test — verifies workers are alive."""
    return "pong"
