from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import CurrentUser, get_current_user
from api.v1.feedback import router   # will cause ImportError until Step 3


def test_current_user_is_dataclass():
    user = CurrentUser(id="abc", email="a@b.com")
    assert user.id == "abc"
    assert user.email == "a@b.com"


_app = FastAPI()
_app.include_router(router)
_app.dependency_overrides[get_current_user] = lambda: CurrentUser(
    id="user-test-uuid", email="tester@example.com"
)
client = TestClient(_app)

VALID_PAYLOAD = {"type": "Bug Report", "message": "Something is broken."}


@patch("api.v1.feedback.httpx.AsyncClient")
def test_send_feedback_success(mock_cls):
    mock_resp = MagicMock()
    mock_resp.is_success = True
    mock_cls.return_value.__aenter__.return_value.post.return_value = mock_resp
    resp = client.post("/feedback", json=VALID_PAYLOAD)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


@patch("api.v1.feedback.httpx.AsyncClient")
def test_send_feedback_resend_failure_returns_502(mock_cls):
    mock_resp = MagicMock()
    mock_resp.is_success = False
    mock_cls.return_value.__aenter__.return_value.post.return_value = mock_resp
    resp = client.post("/feedback", json=VALID_PAYLOAD)
    assert resp.status_code == 502


def test_send_feedback_empty_message_returns_422():
    resp = client.post("/feedback", json={"type": "General", "message": ""})
    assert resp.status_code == 422


def test_send_feedback_invalid_type_returns_422():
    resp = client.post("/feedback", json={"type": "Other", "message": "hi"})
    assert resp.status_code == 422


@patch("api.v1.feedback.httpx.AsyncClient")
def test_email_body_contains_user_email(mock_cls):
    mock_resp = MagicMock()
    mock_resp.is_success = True
    mock_cls.return_value.__aenter__.return_value.post.return_value = mock_resp
    client.post("/feedback", json=VALID_PAYLOAD)
    call_kwargs = mock_cls.return_value.__aenter__.return_value.post.call_args.kwargs
    assert "tester@example.com" in call_kwargs["json"]["text"]


@patch("api.v1.feedback.httpx.AsyncClient")
def test_email_subject_contains_type(mock_cls):
    mock_resp = MagicMock()
    mock_resp.is_success = True
    mock_cls.return_value.__aenter__.return_value.post.return_value = mock_resp
    client.post("/feedback", json=VALID_PAYLOAD)
    call_kwargs = mock_cls.return_value.__aenter__.return_value.post.call_args.kwargs
    assert call_kwargs["json"]["subject"] == "[ReelMind Feedback] Bug Report"


@patch("api.v1.feedback.httpx.AsyncClient")
def test_no_resend_key_returns_500(mock_cls, monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    resp = client.post("/feedback", json=VALID_PAYLOAD)
    assert resp.status_code == 500
