# backend/services/embedder.py
from __future__ import annotations

from google.genai import types

from services.gemini_client import get_gemini_client

_MODEL = "gemini-embedding-2"


class EmbeddingError(Exception):
    def __init__(self, message: str, is_retryable: bool = True):
        super().__init__(message)
        self.is_retryable = is_retryable


def build_chunk_text(
    transcript: str | None,
    caption: str | None,
    hashtags: list[str],
) -> str | None:
    parts = []
    if hashtags:
        parts.append(" ".join(f"#{h}" for h in hashtags))
    if caption:
        parts.append(caption)
    if transcript:
        parts.append(transcript)
    return "\n".join(parts) if parts else None


def embed_document(text: str) -> list[float]:
    try:
        response = get_gemini_client().models.embed_content(
            model=_MODEL,
            contents=text,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=768
            ),
        )
        return list(response.embeddings[0].values)
    except Exception as exc:
        raise EmbeddingError(str(exc), is_retryable=True) from exc


def embed_query(text: str) -> list[float]:
    try:
        response = get_gemini_client().models.embed_content(
            model=_MODEL,
            contents=text,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=768
            ),
        )
        return list(response.embeddings[0].values)
    except Exception as exc:
        raise EmbeddingError(str(exc), is_retryable=True) from exc
