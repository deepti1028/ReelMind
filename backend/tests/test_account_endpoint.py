"""Tests for DELETE /api/v1/account."""
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import pytest


def _make_app():
    from api.deps import get_current_user_id
    from api.v1.account import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_user_id] = lambda: "user-test-id"
    return app


def test_delete_account_returns_204():
    """Successful deletion returns 204 No Content."""
    client = TestClient(_make_app())
    mock_db = MagicMock()

    with patch("api.v1.account.get_supabase", return_value=mock_db):
        response = client.delete(
            "/api/v1/account",
            headers={"Authorization": "Bearer fake-token"},
        )

    assert response.status_code == 204
    assert response.content == b""


def test_delete_account_calls_admin_delete_user():
    """admin.delete_user is called with the authenticated user's ID."""
    client = TestClient(_make_app())
    mock_db = MagicMock()

    with patch("api.v1.account.get_supabase", return_value=mock_db):
        client.delete(
            "/api/v1/account",
            headers={"Authorization": "Bearer fake-token"},
        )

    mock_db.auth.admin.delete_user.assert_called_once_with("user-test-id")
