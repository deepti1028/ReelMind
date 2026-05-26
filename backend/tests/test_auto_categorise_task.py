"""Tests for auto_categorise behaviour in schema and Celery task."""
from schemas.reel import ReelCreate


def test_reel_create_auto_categorise_defaults_true():
    r = ReelCreate(url="https://www.instagram.com/reel/ABC123/")
    assert r.auto_categorise is True


def test_reel_create_auto_categorise_can_be_false():
    r = ReelCreate(url="https://www.instagram.com/reel/ABC123/", auto_categorise=False)
    assert r.auto_categorise is False


from unittest.mock import MagicMock, patch


def _make_supabase_mock():
    db = MagicMock()
    # .table("reels").select().eq().single().execute().data
    db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "url": "https://www.instagram.com/reel/ABC/",
        "user_id": "user-1",
        "status": "processing",
        "fcm_token": None,
    }
    db.table.return_value.update.return_value.eq.return_value.execute.return_value = None
    db.table.return_value.upsert.return_value.execute.return_value = None
    return db


def _make_task_self():
    task_self = MagicMock()
    task_self.request.retries = 0
    task_self.max_retries = 3
    return task_self


def _make_download_result():
    r = MagicMock()
    r.audio_path = "/tmp/audio.m4a"
    r.temp_dir = "/tmp/reel_test"
    r.metadata.creator_handle = "testuser"
    r.metadata.hashtags = ["cooking"]
    r.metadata.caption = "My reel caption"
    r.metadata.thumbnail_url = None
    r.metadata.user.is_private = False
    r.metadata.product_type = "clips"
    return r


def _make_transcription_result():
    t = MagicMock()
    t.text = "Hello world transcript"
    t.has_audio = True
    return t


def test_auto_categorise_false_skips_classify():
    """When auto_categorise=False, classify_reel is never called and status=ready with no category_id."""
    from workers.tasks import process_reel

    task_self = _make_task_self()
    mock_db = _make_supabase_mock()

    with patch("workers.tasks.get_supabase", return_value=mock_db), \
         patch("workers.tasks.download_reel", return_value=_make_download_result()), \
         patch("workers.tasks.transcribe_audio", return_value=_make_transcription_result()), \
         patch("workers.tasks.classify_reel") as mock_classify, \
         patch("workers.tasks.build_chunk_text", return_value=None), \
         patch("workers.tasks.send_push_notification"), \
         patch("os.path.exists", return_value=False):
        result = process_reel.run.__func__(task_self, "reel-123", False)

    mock_classify.assert_not_called()
    assert result["status"] == "ready"
    # Verify a DB update with status=ready and no category_id was made
    all_updates = [c.args[0] for c in mock_db.table.return_value.update.call_args_list]
    ready_updates = [u for u in all_updates if u.get("status") == "ready"]
    assert ready_updates, f"Expected at least one status=ready update, got: {all_updates}"
    assert all("category_id" not in u for u in ready_updates)


def test_auto_categorise_true_still_classifies():
    """When auto_categorise=True (default), classify_reel is called as normal."""
    from workers.tasks import process_reel

    task_self = _make_task_self()
    mock_db = _make_supabase_mock()

    classification = MagicMock()
    classification.category = "Cooking"
    classification.confidence = 0.95
    classification.alternatives = []

    # categories lookup for step 18
    mock_db.table.return_value.select.return_value.or_.return_value.execute.return_value.data = [
        {"id": "cat-1", "name": "Cooking"}
    ]

    with patch("workers.tasks.get_supabase", return_value=mock_db), \
         patch("workers.tasks.download_reel", return_value=_make_download_result()), \
         patch("workers.tasks.transcribe_audio", return_value=_make_transcription_result()), \
         patch("workers.tasks.classify_reel", return_value=classification) as mock_classify, \
         patch("workers.tasks.build_classification_signal", return_value=MagicMock(text="signal", source_summary="transcript")), \
         patch("workers.tasks.build_chunk_text", return_value=None), \
         patch("workers.tasks.send_push_notification"), \
         patch("os.path.exists", return_value=False):
        result = process_reel.run.__func__(task_self, "reel-123", True)

    mock_classify.assert_called_once()
