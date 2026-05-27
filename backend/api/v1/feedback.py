"""Feedback endpoint — emails user feedback to the app owner via Resend."""

import os
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.deps import CurrentUser, get_current_user

router = APIRouter()

_RESEND_URL = "https://api.resend.com/emails"
_FEEDBACK_TO = "deepti.jain2810@gmail.com"
_FEEDBACK_FROM = "onboarding@resend.dev"


class FeedbackRequest(BaseModel):
    type: Literal["Bug Report", "Feature Request", "General"]
    message: str = Field(..., min_length=1, max_length=2000)


@router.post("/feedback", status_code=status.HTTP_200_OK)
async def send_feedback(
    body: FeedbackRequest,
    user: CurrentUser = Depends(get_current_user),
):
    api_key = os.getenv("RESEND_API_KEY", "")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Feedback service not configured",
        )

    sender_label = user.email if user.email else f"user:{user.id}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            _RESEND_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "from": _FEEDBACK_FROM,
                "to": [_FEEDBACK_TO],
                "subject": f"[ReelMind Feedback] {body.type}",
                "text": f"From: {sender_label}\n\n{body.message}",
            },
        )

    if not resp.is_success:
        print(f"[feedback] Resend error {resp.status_code}: {resp.text}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Resend error {resp.status_code}: {resp.text}",
        )

    return {"ok": True}
