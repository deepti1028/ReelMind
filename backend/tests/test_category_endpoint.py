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

    # Reel fetch: .table("reels").select(...).eq(id).eq(user_id).single().execute()
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
        .single.return_value
        .execute.return_value
        .data
    ) = reel_row

    # Category lookup: .table("categories").select(...).eq(name).or_(...).execute()
    if category_id:
        cat_rows = [{"id": category_id, "name": "Fitness"}]
    else:
        cat_rows = []
    (
        db.table.return_value
        .select.return_value
        .eq.return_value
        .or_.return_value
        .execute.return_value
        .data
    ) = cat_rows

    db.table.return_value.update.return_value.eq.return_value.execute.return_value = None
    return db


@patch("api.v1.reels.get_supabase")
def test_assign_category_marks_ready(mock_get_supabase):
    mock_get_supabase.return_value = _make_supabase_patch_mock(
        category_id="cat-uuid-fitness"
    )
    resp = client.patch(
        f"/api/v1/reels/{REEL_ID}/category",
        json={"category_name": "Fitness"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"
    assert resp.json()["category"] == "Fitness"


@patch("api.v1.reels.get_supabase")
def test_null_category_name_marks_uncategorised(mock_get_supabase):
    mock_get_supabase.return_value = _make_supabase_patch_mock()
    resp = client.patch(
        f"/api/v1/reels/{REEL_ID}/category",
        json={"category_name": None},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "uncategorised"


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
        .single.return_value
        .execute.return_value
        .data
    ) = None
    mock_get_supabase.return_value = db
    resp = client.patch(
        f"/api/v1/reels/{REEL_ID}/category",
        json={"category_name": "Fitness"},
    )
    assert resp.status_code == 404


@patch("api.v1.reels.get_supabase")
def test_unknown_category_name_returns_422(mock_get_supabase):
    db = _make_supabase_patch_mock(category_id=None)  # empty cat_rows
    mock_get_supabase.return_value = db
    resp = client.patch(
        f"/api/v1/reels/{REEL_ID}/category",
        json={"category_name": "NonExistentCategory"},
    )
    assert resp.status_code == 422
