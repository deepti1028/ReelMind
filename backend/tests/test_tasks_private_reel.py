from unittest.mock import MagicMock, patch

from services.downloader import DownloadError


def _make_supabase_mock(url="https://www.instagram.com/reel/ABC/"):
    db = MagicMock()
    (
        db.table.return_value
        .select.return_value
        .eq.return_value
        .single.return_value
        .execute.return_value
        .data
    ) = {"url": url, "user_id": "user-1", "status": "processing"}
    db.table.return_value.update.return_value.eq.return_value.execute.return_value = None
    db.table.return_value.delete.return_value.eq.return_value.execute.return_value = None
    return db


def _make_task_self(retries=0):
    task_self = MagicMock()
    task_self.request.retries = retries
    task_self.max_retries = 3
    return task_self


def _make_download_result(is_private=False, product_type="clips"):
    r = MagicMock()
    r.audio_path = None
    r.temp_dir = "/tmp/reel_test"
    r.metadata.creator_handle = "testuser"
    r.metadata.hashtags = []
    r.metadata.caption = "Test caption"
    r.metadata.thumbnail_url = None
    r.metadata.user.is_private = is_private
    r.metadata.product_type = product_type
    return r


def test_private_content_download_error_deletes_row_and_notifies():
    """DownloadError(is_private_content=True) → row deleted, FCM push, no retry."""
    from workers.tasks import process_reel

    task_self = _make_task_self()
    mock_db = _make_supabase_mock()

    with patch("workers.tasks.get_supabase", return_value=mock_db):
        with patch(
            "workers.tasks.download_reel",
            side_effect=DownloadError("private", is_private_content=True),
        ):
            with patch("workers.tasks.send_push_notification") as mock_push:
                result = process_reel(task_self, "reel-123")

    mock_db.table.return_value.delete.return_value.eq.return_value.execute.assert_called_once()
    mock_push.assert_called_once()
    assert mock_push.call_args[1]["title"] == "Can't save this"
    assert "private" in mock_push.call_args[1]["body"].lower()
    assert result["status"] == "rejected_private"


def test_non_retryable_download_error_without_private_flag_marks_failed():
    """DownloadError(is_private_content=False) → existing failed path, row NOT deleted."""
    from workers.tasks import process_reel

    # retries=3 == max_retries → _handle_pipeline_error skips retry, marks failed
    task_self = _make_task_self(retries=3)
    mock_db = _make_supabase_mock()

    with patch("workers.tasks.get_supabase", return_value=mock_db):
        with patch(
            "workers.tasks.download_reel",
            side_effect=DownloadError("404", is_retryable=False),
        ):
            with patch("workers.tasks.send_push_notification"):
                process_reel(task_self, "reel-123")

    mock_db.table.return_value.delete.return_value.eq.return_value.execute.assert_not_called()


def test_is_private_flag_in_metadata_deletes_row_and_notifies():
    """metadata.user.is_private=True → row deleted, private FCM push."""
    from workers.tasks import process_reel

    task_self = _make_task_self()
    mock_db = _make_supabase_mock()

    with patch("workers.tasks.get_supabase", return_value=mock_db):
        with patch(
            "workers.tasks.download_reel",
            return_value=_make_download_result(is_private=True, product_type="clips"),
        ):
            with patch("workers.tasks.send_push_notification") as mock_push:
                result = process_reel(task_self, "reel-123")

    mock_db.table.return_value.delete.return_value.eq.return_value.execute.assert_called_once()
    mock_push.assert_called_once()
    assert mock_push.call_args[1]["title"] == "Can't save this"
    assert "private" in mock_push.call_args[1]["body"].lower()
    assert result["status"] == "rejected_private"


def test_wrong_product_type_deletes_row_and_notifies():
    """metadata.product_type='feed' → row deleted, not-a-reel FCM push."""
    from workers.tasks import process_reel

    task_self = _make_task_self()
    mock_db = _make_supabase_mock()

    with patch("workers.tasks.get_supabase", return_value=mock_db):
        with patch(
            "workers.tasks.download_reel",
            return_value=_make_download_result(is_private=False, product_type="feed"),
        ):
            with patch("workers.tasks.send_push_notification") as mock_push:
                result = process_reel(task_self, "reel-123")

    mock_db.table.return_value.delete.return_value.eq.return_value.execute.assert_called_once()
    mock_push.assert_called_once()
    assert mock_push.call_args[1]["title"] == "Can't save this"
    assert result["status"] == "rejected_not_reel"


def test_valid_public_reel_does_not_delete_row():
    """product_type='clips', is_private=False → pipeline continues, row NOT deleted."""
    from workers.tasks import process_reel

    task_self = _make_task_self()
    mock_db = _make_supabase_mock()

    with patch("workers.tasks.get_supabase", return_value=mock_db):
        with patch(
            "workers.tasks.download_reel",
            return_value=_make_download_result(is_private=False, product_type="clips"),
        ):
            with patch("workers.tasks.transcribe_audio", side_effect=Exception("stop")):
                try:
                    process_reel(task_self, "reel-123")
                except Exception:
                    pass

    mock_db.table.return_value.delete.return_value.eq.return_value.execute.assert_not_called()


def test_none_product_type_does_not_delete_row():
    """product_type=None (unknown) → pipeline continues, row NOT deleted."""
    from workers.tasks import process_reel

    task_self = _make_task_self()
    mock_db = _make_supabase_mock()

    with patch("workers.tasks.get_supabase", return_value=mock_db):
        with patch(
            "workers.tasks.download_reel",
            return_value=_make_download_result(is_private=False, product_type=None),
        ):
            with patch("workers.tasks.transcribe_audio", side_effect=Exception("stop")):
                try:
                    process_reel(task_self, "reel-123")
                except Exception:
                    pass

    mock_db.table.return_value.delete.return_value.eq.return_value.execute.assert_not_called()
