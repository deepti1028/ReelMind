"""Tests for PATCH /api/v1/profiles/fcm-token."""
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_client():
    """Build a minimal test app with auth overridden."""
    from api.deps import get_current_user_id
    from api.v1.profiles import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/profiles")
    app.dependency_overrides[get_current_user_id] = lambda: "user-test-id"
    return TestClient(app)


@patch("api.v1.profiles.get_supabase")
def test_token_upload_returns_ok(mock_get_supabase):
    db = MagicMock()
    db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
    mock_get_supabase.return_value = db

    client = _build_client()
    resp = client.patch(
        "/api/v1/profiles/fcm-token",
        json={"fcm_token": "device-token-abc"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@patch("api.v1.profiles.get_supabase")
def test_token_upload_writes_correct_payload(mock_get_supabase):
    db = MagicMock()
    db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
    mock_get_supabase.return_value = db

    client = _build_client()
    client.patch(
        "/api/v1/profiles/fcm-token",
        json={"fcm_token": "device-token-abc"},
    )

    # Defensive against column-name typos
    payload = db.table.return_value.update.call_args.args[0]
    assert payload["fcm_token"] == "device-token-abc"
    assert "fcm_token_updated_at" in payload  # timestamp set


@patch("api.v1.profiles.get_supabase")
def test_token_upload_scoped_to_authenticated_user(mock_get_supabase):
    db = MagicMock()
    db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
    mock_get_supabase.return_value = db

    client = _build_client()
    client.patch(
        "/api/v1/profiles/fcm-token",
        json={"fcm_token": "device-token-abc"},
    )

    eq_call = db.table.return_value.update.return_value.eq.call_args
    assert eq_call.args == ("id", "user-test-id")


def test_missing_token_returns_422():
    """Pydantic rejects body without fcm_token."""
    client = _build_client()
    resp = client.patch("/api/v1/profiles/fcm-token", json={})
    assert resp.status_code == 422
