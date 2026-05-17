"""Tests for workers.beat_tasks — pending_category timeout."""
from unittest.mock import MagicMock, patch


def _make_supabase_mock(updated_rows: list[dict]):
    """Supabase mock returning updated_rows for the bulk update execute(),
    plus a per-user fcm_token fetch for each updated row."""
    mock_db = MagicMock()

    # bulk update chain
    (
        mock_db.table.return_value
        .update.return_value
        .eq.return_value
        .lt.return_value
        .execute.return_value
        .data
    ) = updated_rows

    # profile fetch chain (returns no fcm_token by default)
    (
        mock_db.table.return_value
        .select.return_value
        .eq.return_value
        .maybe_single.return_value
        .execute.return_value
        .data
    ) = {"fcm_token": None}

    return mock_db


@patch("workers.beat_tasks.get_supabase")
def test_stale_reels_transitioned(mock_get_supabase):
    updated = [
        {"id": "reel-1", "user_id": "user-1"},
        {"id": "reel-2", "user_id": "user-2"},
    ]
    mock_db = _make_supabase_mock(updated)
    mock_get_supabase.return_value = mock_db

    from workers.beat_tasks import expire_pending_categories
    with patch("workers.beat_tasks.send_push_notification", return_value=False) as _push:
        result = expire_pending_categories()

    assert result["expired"] == 2
    assert "reel-1" in result["reel_ids"]
    assert "reel-2" in result["reel_ids"]
    assert _push.call_count == 2  # one push per expired reel


@patch("workers.beat_tasks.get_supabase")
def test_fresh_reels_not_touched(mock_get_supabase):
    """No stale rows → bulk update returns empty data, returns empty result."""
    mock_db = _make_supabase_mock([])
    mock_get_supabase.return_value = mock_db

    from workers.beat_tasks import expire_pending_categories
    with patch("workers.beat_tasks.send_push_notification", return_value=False) as _push:
        result = expire_pending_categories()

    assert result["expired"] == 0
    assert result["reel_ids"] == []
    assert _push.call_count == 0


@patch("workers.beat_tasks.get_supabase")
def test_returns_count_and_ids(mock_get_supabase):
    mock_db = _make_supabase_mock([{"id": "reel-abc", "user_id": "user-x"}])
    mock_get_supabase.return_value = mock_db

    from workers.beat_tasks import expire_pending_categories
    with patch("workers.beat_tasks.send_push_notification", return_value=False) as _push:
        result = expire_pending_categories()

    assert result == {"expired": 1, "reel_ids": ["reel-abc"]}
    assert _push.call_count == 1


@patch("workers.beat_tasks.get_supabase")
def test_update_uses_status_guard_against_race(mock_get_supabase):
    """Update must filter on status='pending_category' so it skips rows the user already resolved."""
    mock_db = _make_supabase_mock([])
    mock_get_supabase.return_value = mock_db

    from workers.beat_tasks import expire_pending_categories
    with patch("workers.beat_tasks.send_push_notification", return_value=False) as _push:
        expire_pending_categories()

    # Verify the update chain includes .eq("status", "pending_category")
    update_chain = mock_db.table.return_value.update.return_value
    update_chain.eq.assert_called_once_with("status", "pending_category")
    assert _push.call_count == 0


@patch("workers.beat_tasks.get_supabase")
def test_update_payload_is_correct(mock_get_supabase):
    """Update payload must set status=uncategorised AND clear suggested_categories."""
    mock_db = _make_supabase_mock([])
    mock_get_supabase.return_value = mock_db

    from workers.beat_tasks import expire_pending_categories
    with patch("workers.beat_tasks.send_push_notification", return_value=False) as _push:
        expire_pending_categories()

    payload = mock_db.table.return_value.update.call_args[0][0]
    assert payload["status"] == "uncategorised"
    assert payload["suggested_categories"] == []
    assert _push.call_count == 0
