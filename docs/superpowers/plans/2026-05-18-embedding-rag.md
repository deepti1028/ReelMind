# Embedding + RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Step 20 (reel embedding) and a category-scoped chat RAG pipeline using HyDE + bge-small-en-v1.5 + Groq Llama, all free.

**Architecture:** Each reel gets one embedding (hashtags + caption + transcript) stored in `reel_chunks`. At chat time, Groq Llama generates a hypothetical transcript from the user's question (HyDE), embeds it with the same model, and does pgvector cosine search scoped to the user's category. A second Groq call synthesizes the answer from retrieved chunks.

**Tech Stack:** `sentence-transformers` (`BAAI/bge-small-en-v1.5`, 384-dim, local), `groq` (Llama 3.3 70B, free tier), `supabase-py` (pgvector via RPC), `fastapi`, `pytest`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `supabase/migrations/20260518000001_resize_reel_chunks_embedding.sql` | Create | Resize embedding column 1536→384, rebuild ivfflat |
| `supabase/migrations/20260518000002_add_match_reel_chunks_fn.sql` | Create | Postgres retrieval function used by rag.py |
| `backend/services/embedder.py` | Create | Build chunk text, embed documents, embed queries |
| `backend/services/rag.py` | Create | HyDE, retrieval, generation, persist messages |
| `backend/api/v1/chat.py` | Create | Chat session + message endpoints |
| `backend/api/v1/__init__.py` | Modify | Register chat router |
| `backend/workers/tasks.py` | Modify | Insert Step 20 between Step 17 and Step 18 |
| `backend/tests/test_embedder.py` | Create | Unit tests for embedder |
| `backend/tests/test_rag.py` | Create | Unit tests for RAG pipeline |
| `backend/tests/test_chat_endpoint.py` | Create | Integration tests for chat endpoints |
| `backend/tests/test_tasks_resilience.py` | Modify | Add Step 20 test |

---

## Task 1: DB Migrations

**Files:**
- Create: `supabase/migrations/20260518000001_resize_reel_chunks_embedding.sql`
- Create: `supabase/migrations/20260518000002_add_match_reel_chunks_fn.sql`

- [ ] **Step 1: Write migration 1 — resize embedding column**

```sql
-- supabase/migrations/20260518000001_resize_reel_chunks_embedding.sql
-- Resize from 1536 (OpenAI placeholder) to 384 (bge-small-en-v1.5 actual output)
drop index if exists idx_reel_chunks_embedding;

alter table public.reel_chunks
  alter column embedding type vector(384);

create index idx_reel_chunks_embedding on public.reel_chunks
  using ivfflat (embedding vector_cosine_ops) with (lists = 50);
```

- [ ] **Step 2: Write migration 2 — add retrieval function**

```sql
-- supabase/migrations/20260518000002_add_match_reel_chunks_fn.sql
create or replace function match_reel_chunks(
    query_embedding vector(384),
    p_user_id       uuid,
    p_category_id   uuid,
    p_creator       text    default null,
    match_count     int     default 10,
    threshold       float   default 0.3
)
returns table (
    reel_id        uuid,
    content        text,
    similarity     float,
    creator_handle text,
    thumbnail_url  text,
    caption        text
)
language sql as $$
    select
        rc.reel_id,
        rc.content,
        1 - (rc.embedding <=> query_embedding) as similarity,
        r.creator_handle,
        r.thumbnail_url,
        r.caption
    from reel_chunks rc
    join reels r on r.id = rc.reel_id
    where rc.user_id = p_user_id
      and r.category_id = p_category_id
      and r.status = 'ready'
      and (p_creator is null
           or r.creator_handle ilike '%' || p_creator || '%')
      and 1 - (rc.embedding <=> query_embedding) > threshold
    order by rc.embedding <=> query_embedding
    limit match_count;
$$;
```

- [ ] **Step 3: Apply migrations**

```bash
cd /Users/deeptijain/Desktop/Deepti/Projects/ReelMind && supabase db push
```

Expected: `Applied 2 migration(s)` (or similar success output).

- [ ] **Step 4: Verify column type and function exist**

```bash
supabase db diff --use-migra
```

Expected: no pending changes (clean diff).

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/20260518000001_resize_reel_chunks_embedding.sql \
        supabase/migrations/20260518000002_add_match_reel_chunks_fn.sql
git commit -m "feat: migrate reel_chunks embedding to 384-dim + add match_reel_chunks fn"
```

---

## Task 2: `services/embedder.py` (TDD)

**Files:**
- Create: `backend/tests/test_embedder.py`
- Create: `backend/services/embedder.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_embedder.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && source venv/bin/activate && pytest tests/test_embedder.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.embedder'`

- [ ] **Step 3: Implement `services/embedder.py`**

```python
# backend/services/embedder.py
from __future__ import annotations

from sentence_transformers import SentenceTransformer

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("BAAI/bge-small-en-v1.5")
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && source venv/bin/activate && pytest tests/test_embedder.py -v
```

Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/services/embedder.py backend/tests/test_embedder.py
git commit -m "feat: add services/embedder.py with bge-small-en-v1.5"
```

---

## Task 3: Step 20 in `workers/tasks.py` (TDD)

**Files:**
- Modify: `backend/tests/test_tasks_resilience.py` (add test at bottom)
- Modify: `backend/workers/tasks.py`

- [ ] **Step 1: Write the failing test — append to `test_tasks_resilience.py`**

Add this block at the bottom of `backend/tests/test_tasks_resilience.py`:

```python
# ---------------------------------------------------------------------------
# Step 20 — embed + store chunk
# ---------------------------------------------------------------------------

def test_step20_builds_enriched_text_and_stores_embedding():
    """Step 20 calls build_chunk_text + embed_document and upserts into reel_chunks."""
    from workers.tasks import process_reel

    task_self = _make_task_self()
    mock_db = _make_step18_supabase_mock()

    signal_mock = MagicMock()
    signal_mock.text = "Fitness content"
    signal_mock.source_summary = "transcript"

    fake_embedding = [0.1] * 384

    with patch("workers.tasks.send_push_notification"):
        with patch("workers.tasks.get_supabase", return_value=mock_db):
            with patch("workers.tasks.download_reel", return_value=_make_download_result()):
                with patch("workers.tasks.transcribe_audio",
                           return_value=MagicMock(text="workout content", has_audio=True)):
                    with patch("workers.tasks.build_classification_signal",
                               return_value=signal_mock):
                        with patch("workers.tasks.classify_reel",
                                   return_value=_make_classification_result(confidence=0.92)):
                            with patch("workers.tasks.embed_document",
                                       return_value=fake_embedding) as mock_embed:
                                with patch("workers.tasks.build_chunk_text",
                                           return_value="enriched text") as mock_build:
                                    with patch("os.path.exists", return_value=False):
                                        process_reel.run.__func__(task_self, "reel-123")

    mock_build.assert_called_once_with(
        transcript="workout content",
        caption="Test caption #tag1",
        hashtags=["tag1"],
    )
    mock_embed.assert_called_once_with("enriched text")
    table_calls = [c[0][0] for c in mock_db.table.call_args_list]
    assert "reel_chunks" in table_calls


def test_step20_skipped_when_no_content():
    """Step 20 does not call embed_document when build_chunk_text returns None."""
    from workers.tasks import process_reel

    task_self = _make_task_self()
    mock_db = _make_step18_supabase_mock()

    signal_mock = MagicMock()
    signal_mock.text = "Fitness content"
    signal_mock.source_summary = "transcript"

    with patch("workers.tasks.send_push_notification"):
        with patch("workers.tasks.get_supabase", return_value=mock_db):
            with patch("workers.tasks.download_reel", return_value=_make_download_result()):
                with patch("workers.tasks.transcribe_audio",
                           return_value=MagicMock(text="workout content", has_audio=True)):
                    with patch("workers.tasks.build_classification_signal",
                               return_value=signal_mock):
                        with patch("workers.tasks.classify_reel",
                                   return_value=_make_classification_result(confidence=0.92)):
                            with patch("workers.tasks.build_chunk_text", return_value=None):
                                with patch("workers.tasks.embed_document") as mock_embed:
                                    with patch("os.path.exists", return_value=False):
                                        process_reel.run.__func__(task_self, "reel-123")

    mock_embed.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && source venv/bin/activate && pytest tests/test_tasks_resilience.py::test_step20_builds_enriched_text_and_stores_embedding tests/test_tasks_resilience.py::test_step20_skipped_when_no_content -v
```

Expected: `ImportError` or `AttributeError` — `build_chunk_text` / `embed_document` not imported in `tasks.py`.

- [ ] **Step 3: Add import + Step 20 block to `workers/tasks.py`**

Add to the imports block at the top of `backend/workers/tasks.py` (after the existing service imports):

```python
from services.embedder import build_chunk_text, embed_document
```

Then insert this block **between** the Step 17 log statement and the `# Step 18` comment (after `log.info("step 17 | signal built ...")` and before `log.info("step 18 | fetching categories ...")`):

```python
        # ------------------------------------------------------------------
        # Step 20 — embed reel content + store chunk
        # ------------------------------------------------------------------
        _chunk_text = build_chunk_text(
            transcript=_transcript_text,
            caption=meta.caption,
            hashtags=meta.hashtags,
        )
        if _chunk_text:
            log.info("step 20 | embedding | chars=%d", len(_chunk_text))
            _embedding = embed_document(_chunk_text)
            supabase.table("reel_chunks").upsert({
                "reel_id": reel_id,
                "user_id": reel_data["user_id"],
                "chunk_index": 0,
                "content": _chunk_text,
                "embedding": _embedding,
            }).execute()
            log.info("step 20 | chunk stored")
        else:
            log.warning("step 20 | no content to embed — skipping")
```

- [ ] **Step 4: Run new tests and full suite to verify no regressions**

```bash
cd backend && source venv/bin/activate && pytest tests/test_tasks_resilience.py -v
```

Expected: all tests pass including the two new Step 20 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/workers/tasks.py backend/tests/test_tasks_resilience.py
git commit -m "feat: add Step 20 — embed reel content into reel_chunks"
```

---

## Task 4: `services/rag.py` (TDD)

**Files:**
- Create: `backend/tests/test_rag.py`
- Create: `backend/services/rag.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_rag.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && source venv/bin/activate && pytest tests/test_rag.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.rag'`

- [ ] **Step 3: Implement `services/rag.py`**

```python
# backend/services/rag.py
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
    results = supabase.rpc("match_reel_chunks", {
        "query_embedding": query_vec,
        "p_user_id": user_id,
        "p_category_id": category_id,
        "p_creator": filters.get("creator_handle"),
        "match_count": 10,
        "threshold": 0.3,
    }).execute()

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && source venv/bin/activate && pytest tests/test_rag.py -v
```

Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/services/rag.py backend/tests/test_rag.py
git commit -m "feat: add services/rag.py — HyDE + pgvector retrieval + Groq generation"
```

---

## Task 5: `api/v1/chat.py` + register router (TDD)

**Files:**
- Create: `backend/tests/test_chat_endpoint.py`
- Create: `backend/api/v1/chat.py`
- Modify: `backend/api/v1/__init__.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_chat_endpoint.py
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
    assert "message_id" in body


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && source venv/bin/activate && pytest tests/test_chat_endpoint.py -v
```

Expected: `ModuleNotFoundError: No module named 'api.v1.chat'`

- [ ] **Step 3: Implement `api/v1/chat.py`**

```python
# backend/api/v1/chat.py
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.deps import get_current_user_id
from services import rag
from services.rag import RagGenerationError
from supabase_client import get_supabase

router = APIRouter()


class CreateSessionRequest(BaseModel):
    category_id: uuid.UUID


class SendMessageRequest(BaseModel):
    content: str


class ReelSource(BaseModel):
    reel_id: str
    creator_handle: str | None = None
    thumbnail_url: str | None = None
    caption: str | None = None


class MessageResponse(BaseModel):
    message_id: str
    content: str
    sources: list[ReelSource]


def _get_session_or_403(session_id: str, user_id: str, supabase) -> dict:
    row = (
        supabase.table("chat_sessions")
        .select("id, user_id, category_id")
        .eq("id", session_id)
        .single()
        .execute()
    )
    if not row.data or str(row.data["user_id"]) != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return row.data


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
def create_session(
    body: CreateSessionRequest,
    user_id: str = Depends(get_current_user_id),
):
    supabase = get_supabase()
    result = supabase.table("chat_sessions").insert({
        "user_id": user_id,
        "category_id": str(body.category_id),
    }).execute()
    return {"session_id": result.data[0]["id"]}


@router.post("/sessions/{session_id}/messages", response_model=MessageResponse)
def send_message(
    session_id: str,
    body: SendMessageRequest,
    user_id: str = Depends(get_current_user_id),
):
    supabase = get_supabase()
    session = _get_session_or_403(session_id, user_id, supabase)

    history_rows = (
        supabase.table("chat_messages")
        .select("role, content")
        .eq("session_id", session_id)
        .order("created_at", desc=False)
        .limit(6)
        .execute()
    )
    history = [
        {"role": r["role"], "content": r["content"]}
        for r in (history_rows.data or [])
    ]

    try:
        result = rag.answer(session, body.content, history)
    except RagGenerationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat service temporarily unavailable",
        )

    supabase.table("chat_messages").insert({
        "session_id": session_id,
        "role": "user",
        "content": body.content,
    }).execute()

    saved = supabase.table("chat_messages").insert({
        "session_id": session_id,
        "role": "assistant",
        "content": result["content"],
        "sources": result["sources"],
    }).execute()

    return MessageResponse(
        message_id=saved.data[0]["id"],
        content=result["content"],
        sources=[ReelSource(**s) for s in result["sources"]],
    )


@router.get("/sessions/{session_id}/messages")
def get_messages(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
):
    supabase = get_supabase()
    _get_session_or_403(session_id, user_id, supabase)
    rows = (
        supabase.table("chat_messages")
        .select("id, role, content, sources, created_at")
        .eq("session_id", session_id)
        .order("created_at", desc=False)
        .execute()
    )
    return rows.data or []
```

- [ ] **Step 4: Register chat router in `api/v1/__init__.py`**

Edit `backend/api/v1/__init__.py`:

```python
"""API v1 router aggregator."""

from fastapi import APIRouter

from api.v1 import chat, health, profiles, reels

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health.router, tags=["health"])
api_router.include_router(reels.router, prefix="/reels", tags=["reels"])
api_router.include_router(profiles.router, prefix="/profiles", tags=["profiles"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && source venv/bin/activate && pytest tests/test_chat_endpoint.py -v
```

Expected: `8 passed`

- [ ] **Step 6: Run full test suite to verify no regressions**

```bash
cd backend && source venv/bin/activate && pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/api/v1/chat.py backend/api/v1/__init__.py backend/tests/test_chat_endpoint.py
git commit -m "feat: add chat endpoints — POST /sessions, POST /messages, GET /messages"
```

---

## Task 6: End-to-end smoke test

**Prerequisite:** Redis running (`docker compose up -d`), FastAPI running (`uvicorn main:app --reload`), Celery worker running, `.env` has `GROQ_API_KEY` and Supabase vars.

- [ ] **Step 1: Verify model downloads and embedder works**

```bash
cd backend && source venv/bin/activate && python -c "
from services.embedder import build_chunk_text, embed_document, embed_query
text = build_chunk_text('hey here are sunscreens', 'SPF picks', ['skincare'])
print('chunk text:', text[:60])
vec = embed_document(text)
print('embed_document dim:', len(vec))
qvec = embed_query('best sunscreens for oily skin')
print('embed_query dim:', len(qvec))
print('All embedder OK')
"
```

Expected output:
```
chunk text: #skincare
SPF picks
hey here are sunscreens
embed_document dim: 384
embed_query dim: 384
All embedder OK
```

- [ ] **Step 2: Verify chat router is registered**

Start the API server and check docs:

```bash
cd backend && source venv/bin/activate && uvicorn main:app --reload --port 8000
```

Then open: `http://localhost:8000/docs` — confirm `/api/v1/chat/sessions` endpoints are listed.

- [ ] **Step 3: Save a reel and verify Step 20 runs**

Using an authenticated token, POST a reel URL to `POST /api/v1/reels`. After the Celery task completes, check that a row exists in `reel_chunks` with `embedding` populated (non-null, 384 elements).

Run in Supabase SQL editor:
```sql
select id, reel_id, chunk_index, length(content), embedding is not null as has_embedding
from reel_chunks
order by created_at desc
limit 5;
```

Expected: rows with `has_embedding = true`.

- [ ] **Step 4: Test a chat query end-to-end**

```bash
# 1. Create a chat session (replace TOKEN and CATEGORY_ID)
curl -X POST http://localhost:8000/api/v1/chat/sessions \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"category_id": "CATEGORY_ID"}'

# 2. Send a message (replace SESSION_ID)
curl -X POST http://localhost:8000/api/v1/chat/sessions/SESSION_ID/messages \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "best sunscreens for oily skin"}'
```

Expected: JSON response with `content` (Groq-generated answer) and `sources` (list of reel metadata).
