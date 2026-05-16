"""Tests for graceful degradation and retry-safe behavior in workers/tasks.py."""
from unittest.mock import MagicMock, patch, call

import pytest


def _make_supabase_mock(status="queued", url="https://instagram.com/reel/ABC/"):
    """Return a mock supabase client wired up for typical task usage."""
    mock_db = MagicMock()

    # .table("reels").select(...).eq(...).single().execute().data
    select_chain = (
        mock_db.table.return_value
        .select.return_value
        .eq.return_value
        .single.return_value
        .execute.return_value
    )
    select_chain.data = {"url": url, "user_id": "user-1", "status": status}

    # .table("reels").update(...).eq(...).execute()
    mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = None
    return mock_db


def _make_task_self(retries=0, max_retries=3):
    task_self = MagicMock()
    task_self.request.retries = retries
    task_self.max_retries = max_retries
    # Make task_self.retry raise Retry exception like Celery does
    from celery.exceptions import Retry
    task_self.retry.side_effect = Retry()
    return task_self


def _make_download_result(audio_path="/tmp/audio.m4a", temp_dir="/tmp/reel_test"):
    result = MagicMock()
    result.audio_path = audio_path
    result.temp_dir = temp_dir
    result.metadata.creator_handle = "testuser"
    result.metadata.hashtags = ["tag1"]
    result.metadata.caption = "Test caption #tag1"
    result.metadata.thumbnail_url = None
    return result


def test_transcription_failure_does_not_mark_reel_failed():
    """Non-retryable TranscriptionError → has_audio=False saved, status NOT set to failed."""
    from services.transcriber import TranscriptionError
    from workers.tasks import process_reel

    task_self = _make_task_self(retries=3, max_retries=3)  # retries exhausted
    mock_db = _make_supabase_mock()

    with patch("workers.tasks.get_supabase", return_value=mock_db):
        with patch("workers.tasks.download_reel", return_value=_make_download_result()):
            with patch("workers.tasks.transcribe_audio",
                       side_effect=TranscriptionError("bad codec", is_retryable=False)):
                with patch("os.path.exists", return_value=False):
                    result = process_reel.run.__func__(task_self, "reel-123")

    # Should NOT return status=failed
    assert result.get("status") != "failed"

    # Verify "failed" was never set via DB update
    all_update_dicts = [
        c[0][0]
        for c in mock_db.table.return_value.update.call_args_list
    ]
    assert not any(d.get("status") == "failed" for d in all_update_dicts), (
        f"Expected no status=failed update, but got: {all_update_dicts}"
    )


def test_transcription_failure_sets_has_audio_false():
    """When transcription fails, has_audio=False is written to DB."""
    from services.transcriber import TranscriptionError
    from workers.tasks import process_reel

    task_self = _make_task_self(retries=3, max_retries=3)
    mock_db = _make_supabase_mock()

    with patch("workers.tasks.get_supabase", return_value=mock_db):
        with patch("workers.tasks.download_reel", return_value=_make_download_result()):
            with patch("workers.tasks.transcribe_audio",
                       side_effect=TranscriptionError("codec", is_retryable=False)):
                with patch("os.path.exists", return_value=False):
                    process_reel.run.__func__(task_self, "reel-123")

    all_update_dicts = [
        c[0][0]
        for c in mock_db.table.return_value.update.call_args_list
    ]
    assert any(d.get("has_audio") is False for d in all_update_dicts), (
        f"Expected has_audio=False in one update, got: {all_update_dicts}"
    )


def test_retryable_transcription_failure_schedules_celery_retry():
    """Retryable TranscriptionError with retries remaining → Celery retry raised."""
    from services.transcriber import TranscriptionError
    from workers.tasks import process_reel
    from celery.exceptions import Retry

    task_self = _make_task_self(retries=0, max_retries=3)
    mock_db = _make_supabase_mock()

    with patch("workers.tasks.get_supabase", return_value=mock_db):
        with patch("workers.tasks.download_reel", return_value=_make_download_result()):
            with patch("workers.tasks.transcribe_audio",
                       side_effect=TranscriptionError("timeout", is_retryable=True)):
                with patch("os.path.exists", return_value=False):
                    with pytest.raises(Retry):
                        process_reel.run.__func__(task_self, "reel-123")


def test_terminal_state_guard_skips_already_ready_reel():
    """If reel.status == 'ready', task returns immediately without re-processing."""
    from workers.tasks import process_reel

    task_self = _make_task_self()
    mock_db = _make_supabase_mock(status="ready")

    with patch("workers.tasks.get_supabase", return_value=mock_db):
        with patch("workers.tasks.download_reel") as mock_dl:
            result = process_reel.run.__func__(task_self, "reel-123")

    mock_dl.assert_not_called()
    assert result["status"] == "already_ready"


def test_download_failure_still_marks_reel_failed():
    """DownloadError (non-retryable, retries exhausted) → status=failed is correct behavior."""
    from services.downloader import DownloadError
    from workers.tasks import process_reel

    task_self = _make_task_self(retries=3, max_retries=3)
    mock_db = _make_supabase_mock()

    with patch("workers.tasks.get_supabase", return_value=mock_db):
        with patch("workers.tasks.download_reel",
                   side_effect=DownloadError("404 deleted", is_retryable=False)):
            with patch("os.path.exists", return_value=False):
                result = process_reel.run.__func__(task_self, "reel-123")

    assert result["status"] == "failed"
