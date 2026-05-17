"""Celery Beat periodic tasks — scheduled maintenance jobs."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from supabase_client import get_supabase
from services.notifier import send_push_notification
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

PENDING_CATEGORY_TIMEOUT_HOURS = 1


@celery_app.task(name="workers.beat_tasks.expire_pending_categories")
def expire_pending_categories() -> dict:
    """Move pending_category reels older than 1 hour to uncategorised.

    Runs every 30 minutes via Celery Beat. Catches reels where the user did
    not respond to the FCM category-suggestion notification within the timeout.

    Uses a single bulk update with .eq("status", "pending_category") as a
    concurrency guard — if a user has already responded to the FCM (via the
    PATCH /reels/{id}/category endpoint), the row's status will have changed
    and the update will skip it.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=PENDING_CATEGORY_TIMEOUT_HOURS)
    supabase = get_supabase()

    result = (
        supabase.table("reels")
        .update({
            "status": "uncategorised",
            "suggested_categories": [],
        })
        .eq("status", "pending_category")
        .lt("updated_at", cutoff.isoformat())
        .execute()
    )

    expired_ids = []
    for row in (result.data or []):
        expired_ids.append(row["id"])
        profile = (
            supabase.table("profiles")
            .select("fcm_token")
            .eq("id", row["user_id"])
            .maybe_single()
            .execute()
        )
        fcm_token = (profile.data or {}).get("fcm_token") if profile.data else None
        send_push_notification(
            fcm_token=fcm_token,
            title="Reel saved",
            body="Added to Uncategorised — you can move it anytime",
            data={"reel_id": row["id"], "status": "uncategorised"},
        )

    logger.info("beat | expire_pending_categories done | expired=%d", len(expired_ids))
    return {"expired": len(expired_ids), "reel_ids": expired_ids}
