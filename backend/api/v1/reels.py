"""Reels endpoints — capture and processing pipeline entry."""

from fastapi import APIRouter, Depends, HTTPException, status
from postgrest.exceptions import APIError

from api.deps import get_current_user_id
from schemas.reel import ReelCreate
from supabase_client import get_supabase
from workers.tasks import process_reel

router = APIRouter()


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_reel(
    payload: ReelCreate,
    user_id: str = Depends(get_current_user_id),
):
    """Capture a reel URL and queue it for processing.

    Returns 202 immediately — actual processing (download, transcribe,
    embed, classify) happens asynchronously in a Celery worker.
    """
    supabase = get_supabase()
    url_str = str(payload.url)

    # Ensure a profile row exists for this user. Idempotent — service role
    # bypasses RLS. We do this here (rather than via a trigger on auth.users)
    # because Supabase triggers + RLS on public tables fight each other and
    # break signup. This upsert is cheap and runs at most once per new user.
    supabase.table("profiles").upsert(
        {"id": user_id},
        on_conflict="id",
        ignore_duplicates=True,
    ).execute()

    # Insert reel row. On duplicate (user already saved this URL), fetch the
    # existing row instead so the response is still useful.
    try:
        result = (
            supabase.table("reels")
            .insert({"user_id": user_id, "url": url_str, "status": "queued"})
            .execute()
        )
        reel = result.data[0]
        is_duplicate = False
    except APIError as exc:
        # Postgres unique violation code is 23505
        if exc.code == "23505":
            existing = (
                supabase.table("reels")
                .select("id, status")
                .eq("user_id", user_id)
                .eq("url", url_str)
                .single()
                .execute()
            )
            reel = existing.data
            is_duplicate = True
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error: {exc.message}",
            )

    reel_id = reel["id"]

    # Only queue the Celery task if this is a fresh insert.
    # Duplicates keep whatever status they already have.
    if not is_duplicate:
        process_reel.delay(reel_id)

    return {
        "status": reel["status"],
        "reel_id": reel_id,
        "duplicate": is_duplicate,
        "url": url_str,
    }
