"""Account management endpoints."""

from fastapi import APIRouter, Depends, status

from api.deps import get_current_user_id
from supabase_client import get_supabase

router = APIRouter()


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(user_id: str = Depends(get_current_user_id)):
    """Permanently delete the authenticated user's account.

    Uses the service-role Supabase client to call auth.admin.delete_user,
    which cascades to profiles → reels → reel_chunks via FK ON DELETE CASCADE.
    """
    supabase = get_supabase()
    supabase.auth.admin.delete_user(user_id)
