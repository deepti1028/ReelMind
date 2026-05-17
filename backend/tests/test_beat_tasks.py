"""Tests for workers.beat_tasks — pending_category timeout."""
from unittest.mock import MagicMock, patch
import pytest


def _make_supabase_mock(stale_rows: list[dict]):
    """Supabase mock returning stale_rows for the pending_category query."""
    mock_db = MagicMock()
    (
        mock_db.table.return_value
        .select.return_value
        .eq.return_value
        .lt.return_value
        .execute.return_value
        .data
    ) = stale_rows
    return mock_db


@patch("workers.beat_tasks.get_supabase")
def test_stale_reels_transitioned(mock_get_supabase):
    stale = [
        {"id": "reel-1", "user_id": "user-1"},
        {"id": "reel-2", "user_id": "user-2"},
    ]
    mock_db = _make_supabase_mock(stale)
    mock_get_supabase.return_value = mock_db

    from workers.beat_tasks import expire_pending_categories
    result = expire_pending_categories()

    assert result["expired"] == 2
    assert "reel-1" in result["reel_ids"]
    assert "reel-2" in result["reel_ids"]
    assert mock_db.table.return_value.update.call_count == 2


@patch("workers.beat_tasks.get_supabase")
def test_fresh_reels_not_touched(mock_get_supabase):
    mock_db = _make_supabase_mock([])
    mock_get_supabase.return_value = mock_db

    from workers.beat_tasks import expire_pending_categories
    result = expire_pending_categories()

    assert result["expired"] == 0
    assert result["reel_ids"] == []
    mock_db.table.return_value.update.assert_not_called()


@patch("workers.beat_tasks.get_supabase")
def test_returns_count_and_ids(mock_get_supabase):
    stale = [{"id": "reel-abc", "user_id": "user-x"}]
    mock_db = _make_supabase_mock(stale)
    mock_get_supabase.return_value = mock_db

    from workers.beat_tasks import expire_pending_categories
    result = expire_pending_categories()

    assert result == {"expired": 1, "reel_ids": ["reel-abc"]}
