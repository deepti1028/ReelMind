"""Reels endpoints — capture and processing pipeline entry."""

from fastapi import APIRouter, Depends, Response, status

from api.deps import get_current_user_id
from schemas.reel import ReelCreate, ReelResponse
from supabase_client import get_supabase
from workers.tasks import process_reel

router = APIRouter()


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=ReelResponse)
async def create_reel(
    payload: ReelCreate,
    response: Response,
    user_id: str = Depends(get_current_user_id),
):
    """Capture a reel URL and queue it for processing.

    Returns 202 when a Celery task is dispatched (fresh insert).
    Returns 200 when the URL already exists for this user (duplicate — no task queued).
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

    # Upsert the reel row. ON CONFLICT (user_id, url) DO NOTHING returns an
    # empty result set — result.data == [] signals a duplicate without using
    # exceptions for control flow.
    result = (
        supabase.table("reels")
        .upsert(
            {"user_id": user_id, "url": url_str, "status": "queued"},
            on_conflict="user_id,url",
            ignore_duplicates=True,
        )
        .execute()
    )

    if result.data:
        # Fresh insert — dispatch Celery task, return 202 (default).
        reel = result.data[0]
        process_reel.delay(reel["id"])
    else:
        # Duplicate URL — fetch the existing row in full, return 200.
        existing = (
            supabase.table("reels")
            .select("*")
            .eq("user_id", user_id)
            .eq("url", url_str)
            .single()
            .execute()
        )
        reel = existing.data
        response.status_code = status.HTTP_200_OK

    return reel
