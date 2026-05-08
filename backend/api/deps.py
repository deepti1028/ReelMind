"""FastAPI dependency: extract authenticated user_id from Supabase JWT."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase_client import get_supabase

_bearer = HTTPBearer()


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> str:
    """Verify a Supabase JWT and return the user's UUID string.

    Raises 401 if the token is missing, malformed, or rejected by Supabase.
    """
    token = credentials.credentials
    supabase = get_supabase()
    try:
        response = supabase.auth.get_user(token)
        if response.user is None:
            raise ValueError("no user in response")
        return str(response.user.id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired auth token",
        )
