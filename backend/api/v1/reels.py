"""Reels endpoints — capture and processing pipeline entry."""

from fastapi import APIRouter, status

from schemas.reel import ReelCreate

router = APIRouter()


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_reel(payload: ReelCreate):
    """Capture a reel URL and queue it for processing.

    Returns 202 immediately — actual processing (download, transcribe,
    embed, classify) happens asynchronously in a Celery worker.
    """
    # TODO (Step 14): create reel record in Supabase with status='queued'
    # TODO (Step 14): dispatch Celery task to process this reel
    # TODO (Step 21): check for duplicate URL before queuing
    return {
        "status": "queued",
        "message": "Reel received and queued for processing",
        "url": str(payload.url),
    }
