"""Tests for PATCH /api/v1/reels/{reel_id}/category."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import get_current_user_id
from api.v1.reels import router

# Minimal test app with auth overridden
_app = FastAPI()
_app.include_router(router, prefix="/api/v1/reels")
_app.dependency_overrides[get_current_user_id] = lambda: "user-test-id"
client = TestClient(_app)

REEL_ID = "reel-abc-123"


def _make_supabase_patch_mock(reel_status="pending_category", category_id=None):
    """Mock supabase for the PATCH endpoint."""
    db = MagicMock()

    # Reel fetch: .table("reels").select(...).eq(id).eq(user_id).maybe_single().execute()
    reel_row = {
        "id": REEL_ID,
        "user_id": "user-test-id",
        "status": reel_status,
        "suggested_categories": ["Fitness", "Nutrition"],
    }
    (
        db.table.return_value
        .select.return_value
        .eq.return_value
        .eq.return_value
        .maybe_single.return_value
        .execute.return_value
        .data
    ) = reel_row

    # Category lookup: .table("categories").select(...).ilike(name).or_(...).execute()
    if category_id:
        cat_rows = [{"id": category_id, "name": "Fitness"}]
    else:
        cat_rows = []
    (
        db.table.return_value
        .select.return_value
        .ilike.return_value
        .or_.return_value
        .execute.return_value
        .data
    ) = cat_rows

    # Profile fetch for FCM token (returns None — no token configured in tests)
    (
        db.table.return_value
        .select.return_value
        .eq.return_value
        .maybe_single.return_value
        .execute.return_value
        .data
    ) = {"fcm_token": None}

    db.table.return_value.update.return_value.eq.return_value.execute.return_value = None
    return db


@patch("api.v1.reels.get_supabase")
def test_assign_category_marks_ready(mock_get_supabase):
    mock_get_supabase.return_value = _make_supabase_patch_mock(
        category_id="cat-uuid-fitness"
    )
    with patch("api.v1.reels.send_push_notification", return_value=False) as _push:
        resp = client.patch(
            f"/api/v1/reels/{REEL_ID}/category",
            json={"category_name": "Fitness"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"
    assert resp.json()["category"] == "Fitness"
    # Verify the update payload (defensive against column-name typos)
    update_calls = mock_get_supabase.return_value.table.return_value.update.call_args_list
    final_update = update_calls[-1].args[0]
    assert final_update["category_id"] == "cat-uuid-fitness"
    assert final_update["confidence"] == 1.0
    assert final_update["status"] == "ready"
    assert final_update["suggested_categories"] == []
    _push.assert_called_once()
    push_kwargs = _push.call_args.kwargs
    assert push_kwargs["title"] == "Reel categorised!"


@patch("api.v1.reels.get_supabase")
def test_null_category_name_marks_uncategorised(mock_get_supabase):
    mock_get_supabase.return_value = _make_supabase_patch_mock()
    with patch("api.v1.reels.send_push_notification", return_value=False) as _push:
        resp = client.patch(
            f"/api/v1/reels/{REEL_ID}/category",
            json={"category_name": None},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "uncategorised"
    update_calls = mock_get_supabase.return_value.table.return_value.update.call_args_list
    final_update = update_calls[-1].args[0]
    assert final_update["status"] == "uncategorised"
    assert final_update["suggested_categories"] == []
    _push.assert_called_once()
    push_kwargs = _push.call_args.kwargs
    assert push_kwargs["title"] == "Reel saved"


@patch("api.v1.reels.get_supabase")
def test_already_resolved_returns_409(mock_get_supabase):
    mock_get_supabase.return_value = _make_supabase_patch_mock(reel_status="ready")
    resp = client.patch(
        f"/api/v1/reels/{REEL_ID}/category",
        json={"category_name": "Fitness"},
    )
    assert resp.status_code == 409


@patch("api.v1.reels.get_supabase")
def test_reel_not_found_returns_404(mock_get_supabase):
    db = MagicMock()
    (
        db.table.return_value
        .select.return_value
        .eq.return_value
        .eq.return_value
        .maybe_single.return_value
        .execute.return_value
        .data
    ) = None
    mock_get_supabase.return_value = db
    resp = client.patch(
        f"/api/v1/reels/{REEL_ID}/category",
        json={"category_name": "Fitness"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Auto-create tests (Task 1)
# ---------------------------------------------------------------------------

def _make_supabase_auto_create_mock(category_found=False, new_cat_id="new-cat-uuid"):
    """Table-routing mock that supports the auto-create branch in update_reel_category."""
    reels_mock = MagicMock()
    categories_mock = MagicMock()
    profiles_mock = MagicMock()

    # Reel fetch: .select().eq(id).eq(user_id).maybe_single().execute().data
    reel_row = {
        "id": REEL_ID,
        "user_id": "user-test-id",
        "status": "pending_category",
        "suggested_categories": ["Fitness"],
    }
    (
        reels_mock.select.return_value
        .eq.return_value.eq.return_value
        .maybe_single.return_value.execute.return_value.data
    ) = reel_row
    reels_mock.update.return_value.eq.return_value.execute.return_value = None

    # Profile fetch for FCM token
    (
        profiles_mock.select.return_value
        .eq.return_value.maybe_single.return_value.execute.return_value.data
    ) = {"fcm_token": None}

    # Category lookup: .select().ilike(name).or_(...).execute().data
    cat_data = [{"id": "existing-cat-id", "name": "Travel"}] if category_found else []
    (
        categories_mock.select.return_value
        .ilike.return_value.or_.return_value.execute.return_value.data
    ) = cat_data

    # Category insert (auto-create path)
    categories_mock.insert.return_value.execute.return_value.data = [
        {"id": new_cat_id, "name": "Travel Vlogs"}
    ]

    db = MagicMock()

    def _table(name):
        if name == "reels":
            return reels_mock
        if name == "categories":
            return categories_mock
        if name == "profiles":
            return profiles_mock
        return MagicMock()

    db.table.side_effect = _table
    return db


@patch("api.v1.reels.get_supabase")
@patch("api.v1.reels.send_push_notification", return_value=False)
def test_patch_auto_creates_category_when_not_found(_push, mock_get_supabase):
    """Unknown category name → auto-creates row, marks reel ready, returns created=True."""
    db = _make_supabase_auto_create_mock(category_found=False, new_cat_id="new-cat-uuid")
    mock_get_supabase.return_value = db

    resp = client.patch(
        f"/api/v1/reels/{REEL_ID}/category",
        json={"category_name": "Travel Vlogs"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["created"] is True

    # Verify insert was called on categories table with correct user_id
    cat_insert_call = db.table("categories").insert.call_args.args[0]
    assert cat_insert_call["user_id"] == "user-test-id"
    assert cat_insert_call["is_default"] is False

    # Verify reel was updated to ready
    reels_update_call = db.table("reels").update.call_args.args[0]
    assert reels_update_call["status"] == "ready"
    assert reels_update_call["category_id"] == "new-cat-uuid"


@patch("api.v1.reels.get_supabase")
@patch("api.v1.reels.send_push_notification", return_value=False)
def test_patch_case_insensitive_reuses_existing_category(_push, mock_get_supabase):
    """Lowercase name that matches existing category → reuses it, no insert, created=False."""
    db = _make_supabase_auto_create_mock(category_found=True)
    mock_get_supabase.return_value = db

    resp = client.patch(
        f"/api/v1/reels/{REEL_ID}/category",
        json={"category_name": "travel"},  # lowercase
    )

    assert resp.status_code == 200
    assert resp.json()["created"] is False

    # Verify insert was NOT called
    db.table("categories").insert.assert_not_called()


@patch("api.v1.reels.get_supabase")
@patch("api.v1.reels.send_push_notification", return_value=False)
def test_patch_title_cases_new_category_name(_push, mock_get_supabase):
    """Input 'travel vlogs' → stored as 'Travel Vlogs' (title-cased)."""
    db = _make_supabase_auto_create_mock(category_found=False)
    mock_get_supabase.return_value = db

    client.patch(
        f"/api/v1/reels/{REEL_ID}/category",
        json={"category_name": "travel vlogs"},
    )

    cat_insert_call = db.table("categories").insert.call_args.args[0]
    assert cat_insert_call["name"] == "Travel Vlogs"
