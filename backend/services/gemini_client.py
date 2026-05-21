"""Shared Gemini client singleton for embeddings and RAG."""

from __future__ import annotations

import threading

from google import genai

from config import get_config

_client: genai.Client | None = None
_lock = threading.Lock()


def get_gemini_client() -> genai.Client:
    """Get or initialize the shared Gemini client.

    Uses double-checked locking to ensure thread-safe initialization.

    Returns:
        genai.Client: The shared Google Gemini client instance.

    Raises:
        RuntimeError: If GEMINI_API_KEY is not configured.
    """
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                key = get_config().GEMINI_API_KEY
                if not key:
                    raise RuntimeError("GEMINI_API_KEY not configured")
                _client = genai.Client(api_key=key)
    return _client
