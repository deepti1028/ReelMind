# backend/tests/test_embedder.py
import pytest
from unittest.mock import MagicMock, patch


def _make_embed_response(dims: int = 768):
    embedding = MagicMock()
    embedding.values = [0.1] * dims
    response = MagicMock()
    response.embeddings = [embedding]
    return response


# --- build_chunk_text (unchanged logic, tests kept for regression) ---

def test_build_chunk_text_all_signals():
    from services.embedder import build_chunk_text
    result = build_chunk_text("transcript text", "caption text", ["skincare", "spf"])
    assert result == "#skincare #spf\ncaption text\ntranscript text"


def test_build_chunk_text_caption_only_when_no_transcript():
    from services.embedder import build_chunk_text
    result = build_chunk_text(None, "caption only", [])
    assert result == "caption only"


def test_build_chunk_text_no_content_returns_none():
    from services.embedder import build_chunk_text
    result = build_chunk_text(None, None, [])
    assert result is None


def test_build_chunk_text_empty_hashtags_skipped():
    from services.embedder import build_chunk_text
    result = build_chunk_text("transcript", "caption", [])
    assert result == "caption\ntranscript"


# --- embed_document ---

def test_embed_document_returns_768_floats():
    from services.embedder import embed_document
    mock_client = MagicMock()
    mock_client.models.embed_content.return_value = _make_embed_response(768)
    with patch("services.embedder.get_gemini_client", return_value=mock_client):
        result = embed_document("some reel content")
    assert isinstance(result, list)
    assert len(result) == 768
    assert all(isinstance(v, float) for v in result)


def test_embed_document_uses_retrieval_document_task_type():
    from services.embedder import embed_document
    mock_client = MagicMock()
    mock_client.models.embed_content.return_value = _make_embed_response()
    with patch("services.embedder.get_gemini_client", return_value=mock_client):
        embed_document("some reel content")
    config = mock_client.models.embed_content.call_args.kwargs["config"]
    assert "RETRIEVAL_DOCUMENT" in str(config.task_type)


def test_embed_document_uses_correct_model():
    from services.embedder import embed_document
    mock_client = MagicMock()
    mock_client.models.embed_content.return_value = _make_embed_response()
    with patch("services.embedder.get_gemini_client", return_value=mock_client):
        embed_document("some reel content")
    assert mock_client.models.embed_content.call_args.kwargs["model"] == "text-embedding-004"


def test_embed_document_api_error_raises_embedding_error():
    from services.embedder import EmbeddingError, embed_document
    mock_client = MagicMock()
    mock_client.models.embed_content.side_effect = Exception("rate limit exceeded")
    with patch("services.embedder.get_gemini_client", return_value=mock_client):
        with pytest.raises(EmbeddingError) as exc_info:
            embed_document("some text")
    assert exc_info.value.is_retryable is True


# --- embed_query ---

def test_embed_query_returns_768_floats():
    from services.embedder import embed_query
    mock_client = MagicMock()
    mock_client.models.embed_content.return_value = _make_embed_response(768)
    with patch("services.embedder.get_gemini_client", return_value=mock_client):
        result = embed_query("best sunscreens for oily skin")
    assert isinstance(result, list)
    assert len(result) == 768


def test_embed_query_uses_retrieval_query_task_type():
    from services.embedder import embed_query
    mock_client = MagicMock()
    mock_client.models.embed_content.return_value = _make_embed_response()
    with patch("services.embedder.get_gemini_client", return_value=mock_client):
        embed_query("best sunscreens for oily skin")
    config = mock_client.models.embed_content.call_args.kwargs["config"]
    assert "RETRIEVAL_QUERY" in str(config.task_type)


def test_embed_query_uses_correct_model():
    from services.embedder import embed_query
    mock_client = MagicMock()
    mock_client.models.embed_content.return_value = _make_embed_response()
    with patch("services.embedder.get_gemini_client", return_value=mock_client):
        embed_query("some query")
    assert mock_client.models.embed_content.call_args.kwargs["model"] == "text-embedding-004"


def test_embed_query_api_error_raises_embedding_error():
    from services.embedder import EmbeddingError, embed_query
    mock_client = MagicMock()
    mock_client.models.embed_content.side_effect = Exception("connection timeout")
    with patch("services.embedder.get_gemini_client", return_value=mock_client):
        with pytest.raises(EmbeddingError) as exc_info:
            embed_query("some query")
    assert exc_info.value.is_retryable is True
