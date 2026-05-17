"""Pydantic schemas for Reel-related requests and responses."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class ReelCreate(BaseModel):
    url: HttpUrl = Field(..., description="The Instagram reel URL")


class ReelResponse(BaseModel):
    id: UUID
    url: str
    status: str
    category_id: Optional[UUID] = None
    creator_handle: Optional[str] = None
    thumbnail_url: Optional[str] = None
    transcript: Optional[str] = None
    caption: Optional[str] = None
    hashtags: list[str] = []
    summary: Optional[str] = None
    confidence: Optional[float] = None
    has_audio: Optional[bool] = None
    retry_count: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class CategoryChoiceRequest(BaseModel):
    """Body for PATCH /reels/{reel_id}/category.

    category_name: exact category name (string) → assigns category, marks ready.
    category_name: null → skips to uncategorised immediately.
    """
    category_name: Optional[str] = None
