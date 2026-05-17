"""Celery Beat periodic tasks — scheduled maintenance jobs."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from supabase_client import get_supabase
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

PENDING_CATEGORY_TIMEOUT_HOURS = 1


@celery_app.task(name="workers.beat_tasks.expire_pending_categories")
def expire_pending_categories() -> dict:
    """Move pending_category reels older than 1 hour to uncategorised.

    Runs every 30 minutes via Celery Beat. Catches reels where the user did
    not respond to the FCM category-suggestion notification within the timeout.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=PENDING_CATEGORY_TIMEOUT_HOURS)
    supabase = get_supabase()

    stale = (
        supabase.table("reels")
        .select("id, user_id")
        .eq("status", "pending_category")
        .lt("updated_at", cutoff.isoformat())
        .execute()
    )

    expired = []
    for row in stale.data:
        supabase.table("reels").update({
            "status": "uncategorised",
            "suggested_categories": [],
        }).eq("id", row["id"]).execute()
        # TODO Step 22: FCM push — "Saved to Uncategorised — you can move it anytime"
        logger.info("beat | expired pending_category | reel_id=%s", row["id"])
        expired.append(row["id"])

    logger.info("beat | expire_pending_categories done | expired=%d", len(expired))
    return {"expired": len(expired), "reel_ids": expired}
