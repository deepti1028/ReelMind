from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from groq import Groq

from config import get_config
from services.embedder import embed_query
from supabase_client import get_supabase

logger = logging.getLogger(__name__)

_HYDE_SYSTEM = (
    "You are helping retrieve relevant Instagram Reel transcripts for a user's question.\n"
    "Do two things:\n"
    "1. Write a short hypothetical reel transcript (3-5 sentences) that would perfectly "
    "answer the question. Write in first person as if you are a creator speaking in a reel.\n"
    "2. Extract any explicit filters: creator username only.\n\n"
    "Return valid JSON only, no other text:\n"
    '{"hypothetical_doc": "...", "filters": {"creator_handle": null}}'
)

_ANSWER_SYSTEM = (
    "You are a helpful assistant answering questions based on the user's saved Instagram Reels.\n"
    "Answer using ONLY the reel content provided. Be specific and conversational.\n"
    "If the reels don't contain enough to answer, say so honestly — don't make things up."
)

_MODEL = "llama-3.3-70b-versatile"

_groq_client: Groq | None = None


class RagGenerationError(Exception):
    pass


def _get_groq_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=get_config().GROQ_API_KEY)
    return _groq_client


def _hyde_and_extract_filters(user_message: str) -> tuple[str, dict]:
    try:
        response = _get_groq_client().chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": _HYDE_SYSTEM},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
        )
        parsed = json.loads(response.choices[0].message.content)
        return parsed["hypothetical_doc"], parsed.get("filters", {})
    except Exception as exc:
        logger.warning("HyDE failed, falling back to raw query | %s", exc)
        return user_message, {}


def _retrieve(
    query_vec: list[float],
    user_id: str,
    category_id: str,
    filters: dict,
    supabase,
) -> list[dict]:
    results = supabase.rpc(
        "match_reel_chunks",
        query_embedding=query_vec,
        p_user_id=user_id,
        p_category_id=category_id,
        p_creator=filters.get("creator_handle"),
        match_count=10,
        threshold=0.3,
    ).execute()

    seen: dict[str, dict] = {}
    for row in (results.data or []):
        reel_id = str(row["reel_id"])
        if reel_id not in seen or row["similarity"] > seen[reel_id]["similarity"]:
            seen[reel_id] = row
    return sorted(seen.values(), key=lambda r: r["similarity"], reverse=True)[:5]


def _generate(
    user_message: str,
    chunks: list[dict],
    history: list[dict],
    groq_client: Groq,
) -> str:
    if chunks:
        context_block = "\n\n---\n\n".join(
            f"[Reel by @{r.get('creator_handle') or 'unknown'}]\n{r['content']}"
            for r in chunks
        )
        user_content = f"Reels:\n{context_block}\n\nQuestion: {user_message}"
    else:
        user_content = f"No relevant reels found.\n\nQuestion: {user_message}"

    try:
        response = groq_client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": _ANSWER_SYSTEM},
                *history,
                {"role": "user", "content": user_content},
            ],
            temperature=0.5,
        )
        return response.choices[0].message.content
    except Exception as exc:
        raise RagGenerationError(str(exc)) from exc


def answer(
    session: dict,
    user_message: str,
    history: list[dict],
) -> dict:
    user_id = str(session["user_id"])
    category_id = str(session["category_id"])
    supabase = get_supabase()
    groq = _get_groq_client()

    hypothetical_doc, filters = _hyde_and_extract_filters(user_message)
    query_vec = embed_query(hypothetical_doc)

    chunks = _retrieve(query_vec, user_id, category_id, filters, supabase)
    generated = _generate(user_message, chunks, history, groq)

    return {
        "content": generated,
        "sources": [
            {
                "reel_id": str(r["reel_id"]),
                "creator_handle": r.get("creator_handle"),
                "thumbnail_url": r.get("thumbnail_url"),
                "caption": r.get("caption"),
            }
            for r in chunks
        ],
    }
