from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.deps import get_current_user_id
from services import rag
from services.rag import RagGenerationError
from supabase_client import get_supabase

router = APIRouter()


class CreateSessionRequest(BaseModel):
    category_id: uuid.UUID


class SendMessageRequest(BaseModel):
    content: str


class ReelSource(BaseModel):
    reel_id: str
    creator_handle: Optional[str] = None
    thumbnail_url: Optional[str] = None
    caption: Optional[str] = None


class MessageResponse(BaseModel):
    message_id: str
    content: str
    sources: List[ReelSource]


def _get_session_or_403(session_id: str, user_id: str, supabase) -> dict:
    row = (
        supabase.table("chat_sessions")
        .select("id, user_id, category_id")
        .eq("id", session_id)
        .single()
        .execute()
    )
    if not row.data or str(row.data["user_id"]) != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return row.data


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
def create_session(
    body: CreateSessionRequest,
    user_id: str = Depends(get_current_user_id),
):
    supabase = get_supabase()
    result = supabase.table("chat_sessions").insert({
        "user_id": user_id,
        "category_id": str(body.category_id),
    }).execute()
    return {"session_id": result.data[0]["id"]}


@router.post("/sessions/{session_id}/messages", response_model=MessageResponse)
def send_message(
    session_id: str,
    body: SendMessageRequest,
    user_id: str = Depends(get_current_user_id),
):
    supabase = get_supabase()
    session = _get_session_or_403(session_id, user_id, supabase)

    history_rows = (
        supabase.table("chat_messages")
        .select("role, content")
        .eq("session_id", session_id)
        .order("created_at", desc=False)
        .limit(6)
        .execute()
    )
    history = [
        {"role": r["role"], "content": r["content"]}
        for r in (history_rows.data or [])
    ]

    try:
        result = rag.answer(session, body.content, history)
    except RagGenerationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat service temporarily unavailable",
        )

    supabase.table("chat_messages").insert({
        "session_id": session_id,
        "role": "user",
        "content": body.content,
    }).execute()

    saved = supabase.table("chat_messages").insert({
        "session_id": session_id,
        "role": "assistant",
        "content": result["content"],
        "sources": result["sources"],
    }).execute()

    return MessageResponse(
        message_id=saved.data[0]["id"],
        content=result["content"],
        sources=[ReelSource(**s) for s in result["sources"]],
    )


@router.get("/sessions/{session_id}/messages")
def get_messages(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    supabase = get_supabase()
    _get_session_or_403(session_id, user_id, supabase)
    rows = (
        supabase.table("chat_messages")
        .select("id, role, content, sources, created_at")
        .eq("session_id", session_id)
        .order("created_at", desc=False)
        .execute()
    )
    return rows.data or []
