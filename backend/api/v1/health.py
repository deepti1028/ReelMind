"""Health check endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.api_route("/health", methods=["GET", "HEAD"])
async def health_check():
    return {"status": "ok"}
