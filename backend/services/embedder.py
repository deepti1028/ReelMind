from __future__ import annotations

from sentence_transformers import SentenceTransformer

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        # device='cpu' prevents PyTorch from initializing Metal/MPS on macOS,
        # which would spawn ObjC background threads that conflict with Celery's fork().
        _model = SentenceTransformer("BAAI/bge-small-en-v1.5", device="cpu")
    return _model


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
    return _get_model().encode(text, normalize_embeddings=True).tolist()


def embed_query(text: str) -> list[float]:
    prefixed = f"Represent this sentence for searching relevant passages: {text}"
    return _get_model().encode(prefixed, normalize_embeddings=True).tolist()
