"""API v1 router aggregator."""

from fastapi import APIRouter

from api.v1 import health, reels

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health.router, tags=["health"])
api_router.include_router(reels.router, prefix="/reels", tags=["reels"])
