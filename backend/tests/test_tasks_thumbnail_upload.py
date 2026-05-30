"""Tests for Step 15b — thumbnail upload wired into workers/tasks.py."""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call
from typing import Optional

import pytest


def _make_supabase_mock(user_id: str = "user-1"):
    mock_db = MagicMock()
    # .table(...).select(...).eq(...).single().execute().data
    select_result = (
        mock_db.table.return_value
        .select.return_value
        .eq.return_value
        .single.return_value
        .execute.return_value
    )
    select_result.data = {
        "url": "https://instagram.com/reel/ABC/",
        "user_id": user_id,
        "status": "queued",
        "fcm_token": None,
    }
    mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
        None
    )
    mock_db.table.return_value.delete.return_value.eq.return_value.execute.return_value = (
        None
    )
    return mock_db


def _make_task_self(retries: int = 0, max_retries: int = 3):
    task_self = MagicMock()
    task_self.request.retries = retries
    task_self.max_retries = max_retries
    from celery.exceptions import Retry
    task_self.retry.side_effect = Retry()
    return task_self


def _make_download_result(thumbnail_path: str | None = "/tmp/reel-1.jpg"):
    result = MagicMock()
    result.audio_path = None
    result.temp_dir = "/tmp/reel_test"
    result.thumbnail_path = thumbnail_path
    result.metadata.creator_handle = "testuser"
    result.metadata.hashtags = []
    result.metadata.caption = "test caption"
    result.metadata.thumbnail_url = "https://scontent.cdninstagram.com/cdn/thumb.jpg"
    result.metadata.user.is_private = False
    result.metadata.product_type = "clips"
    return result


_PERMANENT_URL = (
    "https://supabase.co/storage/v1/object/public/thumbnails/user-1/reel-1.jpg"
)
_CDN_URL = "https://scontent.cdninstagram.com/cdn/thumb.jpg"


def test_step15b_calls_upload_thumbnail_and_stores_permanent_url():
    """When thumbnail_path is present, upload_thumbnail is called and the
    permanent URL it returns is stored in the DB — not the original CDN URL."""
    from workers.tasks import process_reel
    from services.signal_builder import NoSignalError

    mock_db = _make_supabase_mock()

    with (
        patch("workers.tasks.get_supabase", return_value=mock_db),
        patch("workers.tasks.download_reel", return_value=_make_download_result()),
        patch("workers.tasks.upload_thumbnail", return_value=_PERMANENT_URL) as mock_upload,
        patch("workers.tasks.build_classification_signal", side_effect=NoSignalError("no signal")),
    ):
        process_reel.run.__func__(_make_task_self(), "reel-1")

    mock_upload.assert_called_once_with(
        reel_id="reel-1",
        user_id="user-1",
        thumbnail_path="/tmp/reel-1.jpg",
        fallback_url=_CDN_URL,
    )

    update_payloads = [
        c.args[0]
        for c in mock_db.table.return_value.update.call_args_list
        if c.args and "thumbnail_url" in c.args[0]
    ]
    assert len(update_payloads) == 1, f"Expected 1 update with thumbnail_url, got: {update_payloads}"
    assert update_payloads[0]["thumbnail_url"] == _PERMANENT_URL


def test_step15b_skips_upload_when_no_thumbnail_path():
    """When thumbnail_path is None, upload_thumbnail is NOT called and the
    original CDN URL (or None) is used in the DB update."""
    from workers.tasks import process_reel
    from services.signal_builder import NoSignalError

    mock_db = _make_supabase_mock()
    download_result = _make_download_result(thumbnail_path=None)
    download_result.metadata.thumbnail_url = None  # no URL either

    with (
        patch("workers.tasks.get_supabase", return_value=mock_db),
        patch("workers.tasks.download_reel", return_value=download_result),
        patch("workers.tasks.upload_thumbnail") as mock_upload,
        patch("workers.tasks.build_classification_signal", side_effect=NoSignalError("no signal")),
    ):
        process_reel.run.__func__(_make_task_self(), "reel-1")

    mock_upload.assert_not_called()

    update_payloads = [
        c.args[0]
        for c in mock_db.table.return_value.update.call_args_list
        if c.args and "thumbnail_url" in c.args[0]
    ]
    assert len(update_payloads) == 1
    assert update_payloads[0]["thumbnail_url"] is None
