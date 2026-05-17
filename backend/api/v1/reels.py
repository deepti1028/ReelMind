"""Reels endpoints — capture and processing pipeline entry."""

from fastapi import APIRouter, Depends, HTTPException, Response, status

from api.deps import get_current_user_id
from schemas.reel import CategoryChoiceRequest, ReelCreate, ReelResponse
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


@router.patch("/{reel_id}/category", status_code=status.HTTP_200_OK)
async def update_reel_category(
    reel_id: str,
    payload: CategoryChoiceRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Handle user's category choice from an FCM notification button tap.

    Path A (category_name is a string): assigns the category, marks reel ready.
    Path B (category_name is null): moves reel to uncategorised immediately.

    Returns 409 if the reel is already resolved (idempotent guard).
    Returns 404 if the reel does not belong to this user.
    Returns 422 if category_name is not in the user's categories.
    """
    supabase = get_supabase()

    # Fetch and validate reel ownership
    reel_row = (
        supabase.table("reels")
        .select("id, user_id, status, suggested_categories")
        .eq("id", reel_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    if not reel_row.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reel not found")

    reel = reel_row.data
    if reel["status"] != "pending_category":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Reel already resolved (status={reel['status']})",
        )

    # Path B — user tapped "Uncategorised"
    if payload.category_name is None:
        supabase.table("reels").update({
            "status": "uncategorised",
            "suggested_categories": [],
        }).eq("id", reel_id).execute()
        # TODO Step 22: FCM push — "Saved to Uncategorised — you can move it anytime"
        return {"reel_id": reel_id, "status": "uncategorised"}

    # Path A — user picked a specific category
    cat_rows = (
        supabase.table("categories")
        .select("id, name")
        .eq("name", payload.category_name)
        .or_(f"user_id.eq.{user_id},user_id.is.null")
        .execute()
    )
    if not cat_rows.data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Category '{payload.category_name}' not found for this user",
        )

    category_id = cat_rows.data[0]["id"]
    supabase.table("reels").update({
        "category_id": category_id,
        "confidence": 1.0,
        "status": "ready",
        "suggested_categories": [],
    }).eq("id", reel_id).execute()
    # TODO Step 22: FCM push — "Reel categorised!"
    return {"reel_id": reel_id, "status": "ready", "category": payload.category_name}
