import json
from unittest.mock import MagicMock, call, patch

import pytest


def _make_session(user_id="user-abc", category_id="cat-xyz"):
    return {"id": "session-123", "user_id": user_id, "category_id": category_id}


def _groq_response(content: str):
    mock = MagicMock()
    mock.choices[0].message.content = content
    return mock


def _supabase_with_chunks(chunks: list[dict]):
    db = MagicMock()
    db.rpc.return_value.execute.return_value.data = chunks
    db.table.return_value.insert.return_value.execute.return_value.data = [{"id": "msg-1"}]
    return db


def _fake_chunk(reel_id="reel-1", similarity=0.8):
    return {
        "reel_id": reel_id,
        "content": "hey guys today I'm reviewing sunscreens",
        "similarity": similarity,
        "creator_handle": "skinguru",
        "thumbnail_url": "https://thumb.jpg",
        "caption": "SPF picks",
    }


# --- HyDE + answer happy path ---

def test_answer_returns_content_and_sources():
    from services.rag import answer

    hyde_json = json.dumps({
        "hypothetical_doc": "hey guys here are my top sunscreen picks for oily skin",
        "filters": {"creator_handle": None},
    })
    mock_groq = MagicMock()
    mock_groq.chat.completions.create.side_effect = [
        _groq_response(hyde_json),
        _groq_response("The best sunscreen for oily skin is..."),
    ]
    mock_db = _supabase_with_chunks([_fake_chunk()])

    with patch("services.rag._get_groq_client", return_value=mock_groq), \
         patch("services.rag.get_supabase", return_value=mock_db), \
         patch("services.rag.embed_query", return_value=[0.1] * 384):
        result = answer(_make_session(), "best sunscreens for oily skin", [])

    assert result["content"] == "The best sunscreen for oily skin is..."
    assert len(result["sources"]) == 1
    assert result["sources"][0]["reel_id"] == "reel-1"
    assert result["sources"][0]["creator_handle"] == "skinguru"


# --- HyDE fallback ---

def test_hyde_json_parse_failure_falls_back_to_raw_query():
    from services.rag import answer

    mock_groq = MagicMock()
    mock_groq.chat.completions.create.side_effect = [
        _groq_response("not valid json {{"),
        _groq_response("I couldn't find much"),
    ]
    mock_db = _supabase_with_chunks([])

    with patch("services.rag._get_groq_client", return_value=mock_groq), \
         patch("services.rag.get_supabase", return_value=mock_db), \
         patch("services.rag.embed_query", return_value=[0.1] * 384) as mock_embed:
        answer(_make_session(), "best sunscreens", [])

    # embed_query must be called with the raw user message as fallback
    mock_embed.assert_called_once_with("best sunscreens")


def test_hyde_groq_exception_falls_back_to_raw_query():
    from services.rag import answer

    mock_groq = MagicMock()
    mock_groq.chat.completions.create.side_effect = [
        Exception("timeout"),
        _groq_response("answer"),
    ]
    mock_db = _supabase_with_chunks([])

    with patch("services.rag._get_groq_client", return_value=mock_groq), \
         patch("services.rag.get_supabase", return_value=mock_db), \
         patch("services.rag.embed_query", return_value=[0.1] * 384) as mock_embed:
        answer(_make_session(), "my question", [])

    mock_embed.assert_called_once_with("my question")


# --- Creator filter ---

def test_creator_filter_extracted_and_passed_to_rpc():
    from services.rag import answer

    hyde_json = json.dumps({
        "hypothetical_doc": "skincareguru reviews sunscreen",
        "filters": {"creator_handle": "skincareguru"},
    })
    mock_groq = MagicMock()
    mock_groq.chat.completions.create.side_effect = [
        _groq_response(hyde_json),
        _groq_response("Found reels by skincareguru"),
    ]
    mock_db = _supabase_with_chunks([])

    with patch("services.rag._get_groq_client", return_value=mock_groq), \
         patch("services.rag.get_supabase", return_value=mock_db), \
         patch("services.rag.embed_query", return_value=[0.1] * 384):
        answer(_make_session(), "reels by creator skincareguru", [])

    rpc_kwargs = mock_db.rpc.call_args[1]
    assert rpc_kwargs["p_creator"] == "skincareguru"


# --- Deduplication ---

def test_duplicate_reel_id_deduplication_keeps_highest_similarity():
    from services.rag import answer

    hyde_json = json.dumps({"hypothetical_doc": "doc", "filters": {"creator_handle": None}})
    mock_groq = MagicMock()
    mock_groq.chat.completions.create.side_effect = [
        _groq_response(hyde_json),
        _groq_response("answer"),
    ]
    chunks = [
        _fake_chunk(reel_id="reel-1", similarity=0.5),
        _fake_chunk(reel_id="reel-1", similarity=0.9),  # same reel, higher sim
        _fake_chunk(reel_id="reel-2", similarity=0.7),
    ]
    mock_db = _supabase_with_chunks(chunks)

    with patch("services.rag._get_groq_client", return_value=mock_groq), \
         patch("services.rag.get_supabase", return_value=mock_db), \
         patch("services.rag.embed_query", return_value=[0.1] * 384):
        result = answer(_make_session(), "sunscreen", [])

    # Two distinct reels in sources, reel-1 kept only once
    source_ids = [s["reel_id"] for s in result["sources"]]
    assert source_ids.count("reel-1") == 1
    assert "reel-2" in source_ids


# --- Zero results ---

def test_zero_chunks_returns_empty_sources():
    from services.rag import answer

    hyde_json = json.dumps({"hypothetical_doc": "doc", "filters": {"creator_handle": None}})
    mock_groq = MagicMock()
    mock_groq.chat.completions.create.side_effect = [
        _groq_response(hyde_json),
        _groq_response("I couldn't find relevant reels in this category"),
    ]
    mock_db = _supabase_with_chunks([])

    with patch("services.rag._get_groq_client", return_value=mock_groq), \
         patch("services.rag.get_supabase", return_value=mock_db), \
         patch("services.rag.embed_query", return_value=[0.1] * 384):
        result = answer(_make_session(), "sunscreen", [])

    assert result["sources"] == []


# --- Generation failure ---

def test_generation_failure_raises_rag_generation_error():
    from services.rag import RagGenerationError, answer

    hyde_json = json.dumps({"hypothetical_doc": "doc", "filters": {"creator_handle": None}})
    mock_groq = MagicMock()
    mock_groq.chat.completions.create.side_effect = [
        _groq_response(hyde_json),
        Exception("Groq 503"),
    ]
    mock_db = _supabase_with_chunks([_fake_chunk()])

    with patch("services.rag._get_groq_client", return_value=mock_groq), \
         patch("services.rag.get_supabase", return_value=mock_db), \
         patch("services.rag.embed_query", return_value=[0.1] * 384):
        with pytest.raises(RagGenerationError):
            answer(_make_session(), "sunscreen", [])
