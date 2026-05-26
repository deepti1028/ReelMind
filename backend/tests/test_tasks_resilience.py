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
    result.metadata.user.is_private = False
    result.metadata.product_type = "clips"
    return result


def test_transcription_failure_does_not_mark_reel_failed():
    """Non-retryable TranscriptionError → has_audio=False saved, status NOT set to failed."""
    from services.transcriber import TranscriptionError
    from workers.tasks import process_reel

    task_self = _make_task_self(retries=3, max_retries=3)  # retries exhausted
    # Use the step18-aware mock so the classifier step finds categories and
    # the routing update can resolve category_id from the name map.
    mock_db = _make_step18_supabase_mock()

    with patch("workers.tasks.get_supabase", return_value=mock_db):
        with patch("workers.tasks.download_reel", return_value=_make_download_result()):
            with patch("workers.tasks.transcribe_audio",
                       side_effect=TranscriptionError("bad codec", is_retryable=False)):
                with patch("workers.tasks.classify_reel",
                           return_value=_make_classification_result(confidence=0.92)):
                    with patch("workers.tasks.build_chunk_text", return_value=None):
                        with patch("os.path.exists", return_value=False):
                            result = process_reel.run.__func__(task_self, "reel-123")

    # Should NOT return status=failed
    assert result.get("status") != "failed"

    # Verify "failed" was never set via DB update on the reels table
    reels_table = mock_db.table("reels")
    all_update_dicts = [
        c[0][0]
        for c in reels_table.update.call_args_list
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
                with patch("workers.tasks.build_chunk_text", return_value=None):
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


# ---------------------------------------------------------------------------
# Helpers for Step 18+19 tests
# ---------------------------------------------------------------------------

def _make_step18_supabase_mock(
    fcm_token=None,
    categories=None,
    reel_status="queued",
):
    """Supabase mock that routes table() calls by table name."""
    if categories is None:
        categories = [
            {"id": "cat-fitness", "name": "Fitness"},
            {"id": "cat-nutrition", "name": "Nutrition"},
        ]

    reels_mock = MagicMock()
    profiles_mock = MagicMock()
    categories_mock = MagicMock()

    # Reels: select chain (single row fetch)
    reel_row = {
        "url": "https://instagram.com/reel/ABC/",
        "user_id": "user-1",
        "status": reel_status,
    }
    (
        reels_mock.select.return_value
        .eq.return_value
        .single.return_value
        .execute.return_value
        .data
    ) = reel_row
    reels_mock.update.return_value.eq.return_value.execute.return_value = None

    # Profiles: fcm_token fetch
    (
        profiles_mock.select.return_value
        .eq.return_value
        .single.return_value
        .execute.return_value
        .data
    ) = {"fcm_token": fcm_token}

    # Categories: select + or_ chain
    (
        categories_mock.select.return_value
        .or_.return_value
        .execute.return_value
        .data
    ) = categories

    db_mock = MagicMock()

    def _table(name):
        if name == "reels":
            return reels_mock
        if name == "profiles":
            return profiles_mock
        if name == "categories":
            return categories_mock
        return MagicMock()

    db_mock.table.side_effect = _table
    return db_mock


def _make_classification_result(category="Fitness", confidence=0.92, alternatives=None):
    from services.classifier import ClassificationResult
    return ClassificationResult(
        category=category,
        confidence=confidence,
        alternatives=alternatives or ["Nutrition"],
    )


# ---------------------------------------------------------------------------
# Step 18+19 routing tests
# ---------------------------------------------------------------------------

def test_high_confidence_marks_ready():
    """classify_reel returns ≥0.70 confidence → reel status set to ready."""
    from workers.tasks import process_reel

    task_self = _make_task_self()
    mock_db = _make_step18_supabase_mock()

    signal_mock = MagicMock()
    signal_mock.text = "Fitness content"
    signal_mock.source_summary = "transcript"

    with patch("workers.tasks.send_push_notification", return_value=False) as _push:
        with patch("workers.tasks.get_supabase", return_value=mock_db):
            with patch("workers.tasks.download_reel", return_value=_make_download_result()):
                with patch("workers.tasks.transcribe_audio",
                           return_value=MagicMock(text="workout", has_audio=True)):
                    with patch("workers.tasks.build_classification_signal",
                               return_value=signal_mock):
                        with patch("workers.tasks.classify_reel",
                                   return_value=_make_classification_result(confidence=0.92)):
                            with patch("workers.tasks.build_chunk_text", return_value=None):
                                with patch("os.path.exists", return_value=False):
                                    result = process_reel.run.__func__(task_self, "reel-123")

    assert result["status"] == "ready"
    assert result["category"] == "Fitness"

    # Verify the reels.update payload (defensive against column-name typos)
    reels_mock = mock_db.table("reels")
    update_payloads = [call.args[0] for call in reels_mock.update.call_args_list]
    final_update = update_payloads[-1]
    assert final_update["status"] == "ready"
    assert final_update["category_id"] == "cat-fitness"
    assert final_update["confidence"] == 0.92

    _push.assert_called_once()
    push_kwargs = _push.call_args.kwargs
    assert push_kwargs["title"] == "Reel saved!"
    assert "Fitness" in push_kwargs["body"]


def test_low_confidence_marks_pending_category():
    """classify_reel returns <0.70 confidence → reel status set to pending_category."""
    from workers.tasks import process_reel

    task_self = _make_task_self()
    mock_db = _make_step18_supabase_mock()

    signal_mock = MagicMock()
    signal_mock.text = "Ambiguous content"
    signal_mock.source_summary = "caption"

    with patch("workers.tasks.send_push_notification", return_value=False) as _push:
        with patch("workers.tasks.get_supabase", return_value=mock_db):
            with patch("workers.tasks.download_reel", return_value=_make_download_result()):
                with patch("workers.tasks.transcribe_audio",
                           return_value=MagicMock(text="", has_audio=False)):
                    with patch("workers.tasks.build_classification_signal",
                               return_value=signal_mock):
                        with patch("workers.tasks.classify_reel",
                                   return_value=_make_classification_result(confidence=0.55)):
                            with patch("workers.tasks.build_chunk_text", return_value=None):
                                with patch("os.path.exists", return_value=False):
                                    result = process_reel.run.__func__(task_self, "reel-123")

    assert result["status"] == "pending_category"
    assert "suggestions" in result
    assert "Fitness" in result["suggestions"]

    reels_mock = mock_db.table("reels")
    update_payloads = [call.args[0] for call in reels_mock.update.call_args_list]
    final_update = update_payloads[-1]
    assert final_update["status"] == "pending_category"
    assert final_update["suggested_categories"] == ["Fitness", "Nutrition"]
    assert final_update["confidence"] == 0.55

    _push.assert_called_once()
    push_kwargs = _push.call_args.kwargs
    assert push_kwargs["category_id"] == "CATEGORISE"
    assert push_kwargs["title"] == "Help us categorise this reel"


def test_classification_retryable_error_triggers_retry():
    """ClassificationError(is_retryable=True) → Celery retry raised."""
    from celery.exceptions import Retry
    from services.classifier import ClassificationError
    from workers.tasks import process_reel

    task_self = _make_task_self(retries=0, max_retries=3)
    mock_db = _make_step18_supabase_mock()

    signal_mock = MagicMock()
    signal_mock.text = "content"
    signal_mock.source_summary = "transcript"

    with patch("workers.tasks.send_push_notification", return_value=False):
        with patch("workers.tasks.get_supabase", return_value=mock_db):
            with patch("workers.tasks.download_reel", return_value=_make_download_result()):
                with patch("workers.tasks.transcribe_audio",
                           return_value=MagicMock(text="content", has_audio=True)):
                    with patch("workers.tasks.build_classification_signal",
                               return_value=signal_mock):
                        with patch("workers.tasks.classify_reel",
                                   side_effect=ClassificationError("rate limit", is_retryable=True)):
                            with patch("workers.tasks.build_chunk_text", return_value=None):
                                with patch("os.path.exists", return_value=False):
                                    with pytest.raises(Retry):
                                        process_reel.run.__func__(task_self, "reel-123")


def test_classification_non_retryable_error_marks_failed():
    """ClassificationError(is_retryable=False) → reel marked failed."""
    from services.classifier import ClassificationError
    from workers.tasks import process_reel

    task_self = _make_task_self()
    mock_db = _make_step18_supabase_mock()

    signal_mock = MagicMock()
    signal_mock.text = "content"
    signal_mock.source_summary = "transcript"

    with patch("workers.tasks.send_push_notification", return_value=False):
        with patch("workers.tasks.get_supabase", return_value=mock_db):
            with patch("workers.tasks.download_reel", return_value=_make_download_result()):
                with patch("workers.tasks.transcribe_audio",
                           return_value=MagicMock(text="content", has_audio=True)):
                    with patch("workers.tasks.build_classification_signal",
                               return_value=signal_mock):
                        with patch("workers.tasks.classify_reel",
                                   side_effect=ClassificationError("bad schema", is_retryable=False)):
                            with patch("workers.tasks.build_chunk_text", return_value=None):
                                with patch("os.path.exists", return_value=False):
                                    result = process_reel.run.__func__(task_self, "reel-123")

    assert result["status"] == "failed"


# ---------------------------------------------------------------------------
# Step 20 — embed + store chunk
# ---------------------------------------------------------------------------

def test_step20_builds_enriched_text_and_stores_embedding():
    """Step 20 calls build_chunk_text + embed_document and upserts into reel_chunks."""
    from workers.tasks import process_reel

    task_self = _make_task_self()
    mock_db = _make_step18_supabase_mock()

    signal_mock = MagicMock()
    signal_mock.text = "Fitness content"
    signal_mock.source_summary = "transcript"

    fake_embedding = [0.1] * 384

    with patch("workers.tasks.send_push_notification"):
        with patch("workers.tasks.get_supabase", return_value=mock_db):
            with patch("workers.tasks.download_reel", return_value=_make_download_result()):
                with patch("workers.tasks.transcribe_audio",
                           return_value=MagicMock(text="workout content", has_audio=True)):
                    with patch("workers.tasks.build_classification_signal",
                               return_value=signal_mock):
                        with patch("workers.tasks.classify_reel",
                                   return_value=_make_classification_result(confidence=0.92)):
                            with patch("workers.tasks.embed_document",
                                       return_value=fake_embedding) as mock_embed:
                                with patch("workers.tasks.build_chunk_text",
                                           return_value="enriched text") as mock_build:
                                    with patch("os.path.exists", return_value=False):
                                        process_reel.run.__func__(task_self, "reel-123")

    mock_build.assert_called_once_with(
        transcript="workout content",
        caption="Test caption #tag1",
        hashtags=["tag1"],
    )
    mock_embed.assert_called_once_with("enriched text")
    table_calls = [c[0][0] for c in mock_db.table.call_args_list]
    assert "reel_chunks" in table_calls


def test_step20_skipped_when_no_content():
    """Step 20 does not call embed_document when build_chunk_text returns None."""
    from workers.tasks import process_reel

    task_self = _make_task_self()
    mock_db = _make_step18_supabase_mock()

    signal_mock = MagicMock()
    signal_mock.text = "Fitness content"
    signal_mock.source_summary = "transcript"

    with patch("workers.tasks.send_push_notification"):
        with patch("workers.tasks.get_supabase", return_value=mock_db):
            with patch("workers.tasks.download_reel", return_value=_make_download_result()):
                with patch("workers.tasks.transcribe_audio",
                           return_value=MagicMock(text="workout content", has_audio=True)):
                    with patch("workers.tasks.build_classification_signal",
                               return_value=signal_mock):
                        with patch("workers.tasks.classify_reel",
                                   return_value=_make_classification_result(confidence=0.92)):
                            with patch("workers.tasks.build_chunk_text", return_value=None):
                                with patch("workers.tasks.embed_document") as mock_embed:
                                    with patch("os.path.exists", return_value=False):
                                        process_reel.run.__func__(task_self, "reel-123")

    mock_embed.assert_not_called()
