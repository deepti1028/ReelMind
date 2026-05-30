"""Supabase Storage helpers — permanent thumbnail upload (Step 15b)."""
from __future__ import annotations

import logging
import time

from supabase_client import get_supabase

log = logging.getLogger(__name__)

_BUCKET = "thumbnails"
_MAX_ATTEMPTS = 4  # 1 initial + 3 retries; delays: 2s → 4s → 8s


def upload_thumbnail(
    reel_id: str,
    user_id: str,
    thumbnail_path: str,
    fallback_url: str | None = None,
) -> str | None:
    """Upload a local thumbnail file to Supabase Storage.

    Returns the permanent public URL on success, or fallback_url after
    exhausting retries (which may itself be None).
    """
    storage_path = f"{user_id}/{reel_id}.jpg"
    log.info(
        "storage | uploading thumbnail | reel_id=%s | local_path=%s | storage_path=%s",
        reel_id,
        thumbnail_path,
        storage_path,
    )

    with open(thumbnail_path, "rb") as fh:
        file_bytes = fh.read()

    supabase = get_supabase()

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            supabase.storage.from_(_BUCKET).upload(
                path=storage_path,
                file=file_bytes,
                file_options={"content-type": "image/jpeg", "upsert": "true"},
            )
            public_url: str = supabase.storage.from_(_BUCKET).get_public_url(
                storage_path
            )
            log.info(
                "storage | upload success | reel_id=%s | public_url=%s",
                reel_id,
                public_url,
            )
            return public_url
        except Exception as exc:
            backoff = 2**attempt  # 2, 4, 8 seconds
            if attempt < _MAX_ATTEMPTS:
                log.warning(
                    "storage | upload attempt failed (%d/%d) | reel_id=%s"
                    " | error=%s | retrying in %ds",
                    attempt,
                    _MAX_ATTEMPTS,
                    reel_id,
                    exc,
                    backoff,
                )
                time.sleep(backoff)
            else:
                log.warning(
                    "storage | upload attempt failed (%d/%d) | reel_id=%s"
                    " | error=%s | falling back to CDN URL",
                    attempt,
                    _MAX_ATTEMPTS,
                    reel_id,
                    exc,
                )

    log.warning(
        "storage | all retries exhausted | reel_id=%s | using fallback_url=%s",
        reel_id,
        fallback_url,
    )
    return fallback_url
