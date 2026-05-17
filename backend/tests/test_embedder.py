import numpy as np
import pytest
from unittest.mock import MagicMock, patch


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


def test_embed_document_returns_list_of_384_floats():
    from services.embedder import embed_document
    mock_model = MagicMock()
    mock_model.encode.return_value = np.array([0.1] * 384)
    with patch("services.embedder._get_model", return_value=mock_model):
        result = embed_document("some reel content")
    assert isinstance(result, list)
    assert len(result) == 384
    mock_model.encode.assert_called_once_with("some reel content", normalize_embeddings=True)


def test_embed_query_uses_instruction_prefix():
    from services.embedder import embed_query
    mock_model = MagicMock()
    mock_model.encode.return_value = np.array([0.1] * 384)
    with patch("services.embedder._get_model", return_value=mock_model):
        embed_query("best sunscreens for oily skin")
    called_text = mock_model.encode.call_args[0][0]
    assert called_text.startswith("Represent this sentence for searching relevant passages:")
    assert "best sunscreens for oily skin" in called_text


def test_embed_query_normalize_embeddings():
    from services.embedder import embed_query
    mock_model = MagicMock()
    mock_model.encode.return_value = np.array([0.1] * 384)
    with patch("services.embedder._get_model", return_value=mock_model):
        embed_query("query")
    mock_model.encode.assert_called_once_with(
        "Represent this sentence for searching relevant passages: query",
        normalize_embeddings=True,
    )
