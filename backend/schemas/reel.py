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
    summary: Optional[str] = None
    confidence: Optional[float] = None
    created_at: datetime
