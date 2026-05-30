"""Tests for services.storage — Step 15b permanent thumbnail upload."""
from unittest.mock import MagicMock, mock_open, patch

import pytest


def _make_storage_mock(fail_count: int = 0):
    """Return a supabase mock whose upload fails `fail_count` times then succeeds."""
    mock_supabase = MagicMock()
    bucket = mock_supabase.storage.from_.return_value
    bucket.get_public_url.return_value = (
        "https://supabase.co/storage/v1/object/public/thumbnails/user-1/reel-1.jpg"
    )

    state = {"calls": 0}

    def upload_side_effect(*args, **kwargs):
        state["calls"] += 1
        if state["calls"] <= fail_count:
            raise Exception(f"StorageException: network error (call {state['calls']})")
        return MagicMock()

    bucket.upload.side_effect = upload_side_effect
    return mock_supabase


_PERMANENT_URL = (
    "https://supabase.co/storage/v1/object/public/thumbnails/user-1/reel-1.jpg"
)
_FALLBACK_URL = "https://scontent.cdninstagram.com/cdn/thumb.jpg"


@patch("services.storage.time.sleep")
@patch("services.storage.get_supabase")
def test_upload_success_returns_permanent_url(mock_get_supabase, mock_sleep):
    mock_get_supabase.return_value = _make_storage_mock(fail_count=0)

    from services.storage import upload_thumbnail

    with patch("builtins.open", mock_open(read_data=b"fake-image-bytes")):
        result = upload_thumbnail(
            reel_id="reel-1",
            user_id="user-1",
            thumbnail_path="/tmp/reel-1.jpg",
            fallback_url=_FALLBACK_URL,
        )

    assert result == _PERMANENT_URL
    mock_sleep.assert_not_called()


@patch("services.storage.time.sleep")
@patch("services.storage.get_supabase")
def test_upload_retries_on_failure_then_succeeds(mock_get_supabase, mock_sleep):
    """Fails twice, succeeds on 3rd attempt — returns permanent URL, slept twice."""
    mock_get_supabase.return_value = _make_storage_mock(fail_count=2)

    from services.storage import upload_thumbnail

    with patch("builtins.open", mock_open(read_data=b"fake-image-bytes")):
        result = upload_thumbnail(
            reel_id="reel-1",
            user_id="user-1",
            thumbnail_path="/tmp/reel-1.jpg",
            fallback_url=_FALLBACK_URL,
        )

    assert result == _PERMANENT_URL
    assert mock_sleep.call_count == 2
    # attempt=1 → 2**1=2s, attempt=2 → 2**2=4s
    mock_sleep.assert_any_call(2)
    mock_sleep.assert_any_call(4)


@patch("services.storage.time.sleep")
@patch("services.storage.get_supabase")
def test_upload_all_retries_exhausted_returns_fallback(mock_get_supabase, mock_sleep):
    """All 4 attempts fail — returns fallback CDN URL, slept 3 times."""
    mock_get_supabase.return_value = _make_storage_mock(fail_count=99)

    from services.storage import upload_thumbnail

    with patch("builtins.open", mock_open(read_data=b"fake-image-bytes")):
        result = upload_thumbnail(
            reel_id="reel-1",
            user_id="user-1",
            thumbnail_path="/tmp/reel-1.jpg",
            fallback_url=_FALLBACK_URL,
        )

    assert result == _FALLBACK_URL
    assert mock_sleep.call_count == 3  # 3 sleeps between 4 attempts


@patch("services.storage.time.sleep")
@patch("services.storage.get_supabase")
def test_upload_all_retries_exhausted_no_fallback_returns_none(
    mock_get_supabase, mock_sleep
):
    """All attempts fail with no fallback_url provided — returns None."""
    mock_get_supabase.return_value = _make_storage_mock(fail_count=99)

    from services.storage import upload_thumbnail

    with patch("builtins.open", mock_open(read_data=b"fake-image-bytes")):
        result = upload_thumbnail(
            reel_id="reel-1",
            user_id="user-1",
            thumbnail_path="/tmp/reel-1.jpg",
            fallback_url=None,
        )

    assert result is None


@patch("services.storage.time.sleep")
@patch("services.storage.get_supabase")
def test_storage_path_uses_user_and_reel_ids(mock_get_supabase, mock_sleep):
    """Upload path is '{user_id}/{reel_id}.jpg'."""
    mock_supabase = _make_storage_mock(fail_count=0)
    mock_get_supabase.return_value = mock_supabase

    from services.storage import upload_thumbnail

    with patch("builtins.open", mock_open(read_data=b"fake-image-bytes")):
        upload_thumbnail(
            reel_id="reel-abc",
            user_id="user-xyz",
            thumbnail_path="/tmp/reel-abc.jpg",
            fallback_url=None,
        )

    upload_call = mock_supabase.storage.from_.return_value.upload.call_args
    assert upload_call.kwargs["path"] == "user-xyz/reel-abc.jpg"


@patch("services.storage.time.sleep")
@patch("services.storage.get_supabase")
def test_file_not_found_returns_fallback_without_retrying(mock_get_supabase, mock_sleep):
    """If the local thumbnail file doesn't exist, return fallback immediately — no retries."""
    mock_get_supabase.return_value = _make_storage_mock(fail_count=0)

    from services.storage import upload_thumbnail

    result = upload_thumbnail(
        reel_id="reel-1",
        user_id="user-1",
        thumbnail_path="/nonexistent/path/reel-1.jpg",
        fallback_url=_FALLBACK_URL,
    )

    assert result == _FALLBACK_URL
    mock_sleep.assert_not_called()
    mock_get_supabase.return_value.storage.from_.return_value.upload.assert_not_called()
