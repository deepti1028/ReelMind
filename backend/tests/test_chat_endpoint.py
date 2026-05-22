import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


USER_ID = "user-test-id"
SESSION_ID = str(uuid.uuid4())
CATEGORY_ID = str(uuid.uuid4())


def _build_client():
    from api.deps import get_current_user_id
    from api.v1.chat import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/chat")
    app.dependency_overrides[get_current_user_id] = lambda: USER_ID
    return TestClient(app)


def _make_chat_db(session_user_id=USER_ID, history=None):
    """Mock supabase routing chat_sessions and chat_messages by table name."""
    sessions_mock = MagicMock()
    messages_mock = MagicMock()

    (
        sessions_mock.select.return_value
        .eq.return_value.single.return_value.execute.return_value.data
    ) = {"id": SESSION_ID, "user_id": session_user_id, "category_id": CATEGORY_ID}

    (
        messages_mock.select.return_value
        .eq.return_value.order.return_value.limit.return_value.execute.return_value.data
    ) = history or []

    (
        messages_mock.select.return_value
        .eq.return_value.order.return_value.execute.return_value.data
    ) = history or []

    messages_mock.insert.return_value.execute.return_value.data = [
        {"id": "msg-assistant-1"}
    ]

    db = MagicMock()

    def _table(name):
        if name == "chat_sessions":
            return sessions_mock
        if name == "chat_messages":
            return messages_mock
        return MagicMock()

    db.table.side_effect = _table
    return db


# --- POST /sessions ---

@patch("api.v1.chat.get_supabase")
def test_create_session_returns_session_id(mock_get_supabase):
    db = MagicMock()
    db.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": SESSION_ID}
    ]
    mock_get_supabase.return_value = db

    client = _build_client()
    resp = client.post("/api/v1/chat/sessions", json={"category_id": CATEGORY_ID})

    assert resp.status_code == 201
    assert resp.json()["session_id"] == SESSION_ID


@patch("api.v1.chat.get_supabase")
def test_create_session_stores_user_id(mock_get_supabase):
    db = MagicMock()
    db.table.return_value.insert.return_value.execute.return_value.data = [
        {"id": SESSION_ID}
    ]
    mock_get_supabase.return_value = db

    client = _build_client()
    client.post("/api/v1/chat/sessions", json={"category_id": CATEGORY_ID})

    payload = db.table.return_value.insert.call_args.args[0]
    assert payload["user_id"] == USER_ID
    assert payload["category_id"] == CATEGORY_ID


# --- POST /sessions/{id}/messages ---

@patch("api.v1.chat.get_supabase")
@patch("api.v1.chat.rag")
def test_send_message_returns_content_and_sources(mock_rag, mock_get_supabase):
    mock_get_supabase.return_value = _make_chat_db()
    mock_rag.answer.return_value = {
        "content": "Best sunscreens are A and B",
        "sources": [{"reel_id": "r1", "creator_handle": "guru",
                      "thumbnail_url": None, "caption": "spf"}],
    }

    client = _build_client()
    resp = client.post(
        f"/api/v1/chat/sessions/{SESSION_ID}/messages",
        json={"content": "best sunscreens for oily skin"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["content"] == "Best sunscreens are A and B"
    assert body["sources"][0]["reel_id"] == "r1"
    assert "id" in body
    assert "role" in body
    assert "created_at" in body


@patch("api.v1.chat.get_supabase")
def test_send_message_to_other_users_session_returns_403(mock_get_supabase):
    mock_get_supabase.return_value = _make_chat_db(session_user_id="other-user")

    client = _build_client()
    resp = client.post(
        f"/api/v1/chat/sessions/{SESSION_ID}/messages",
        json={"content": "hi"},
    )

    assert resp.status_code == 403


@patch("api.v1.chat.get_supabase")
@patch("api.v1.chat.rag")
def test_send_message_rag_failure_returns_503(mock_rag, mock_get_supabase):
    from services.rag import RagGenerationError
    mock_get_supabase.return_value = _make_chat_db()
    mock_rag.answer.side_effect = RagGenerationError("groq down")

    client = _build_client()
    resp = client.post(
        f"/api/v1/chat/sessions/{SESSION_ID}/messages",
        json={"content": "sunscreen"},
    )

    assert resp.status_code == 503


# --- GET /sessions/{id}/messages ---

@patch("api.v1.chat.get_supabase")
def test_get_messages_returns_history(mock_get_supabase):
    history = [
        {"id": "m1", "role": "user", "content": "hi", "sources": None,
         "created_at": "2026-05-18T00:00:00Z"},
        {"id": "m2", "role": "assistant", "content": "hello", "sources": [],
         "created_at": "2026-05-18T00:00:01Z"},
    ]
    mock_get_supabase.return_value = _make_chat_db(history=history)

    client = _build_client()
    resp = client.get(f"/api/v1/chat/sessions/{SESSION_ID}/messages")

    assert resp.status_code == 200
    assert len(resp.json()) == 2


@patch("api.v1.chat.get_supabase")
def test_get_messages_other_users_session_returns_403(mock_get_supabase):
    mock_get_supabase.return_value = _make_chat_db(session_user_id="other-user")

    client = _build_client()
    resp = client.get(f"/api/v1/chat/sessions/{SESSION_ID}/messages")

    assert resp.status_code == 403
