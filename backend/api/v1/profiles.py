"""Profile endpoints — FCM token registration (Step 22)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status

from api.deps import get_current_user_id
from schemas.reel import FCMTokenRequest
from supabase_client import get_supabase

router = APIRouter()


@router.patch("/fcm-token", status_code=status.HTTP_200_OK)
async def update_fcm_token(
    payload: FCMTokenRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Upload (or refresh) the device's FCM registration token."""
    supabase = get_supabase()
    supabase.table("profiles").update({
        "fcm_token": payload.fcm_token,
        "fcm_token_updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", user_id).execute()
    return {"status": "ok"}
