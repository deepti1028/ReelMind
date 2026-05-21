# Gemini Embedding Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the local `BAAI/bge-small-en-v1.5` sentence-transformers model with Google's `text-embedding-004` API (768-dim), extract a shared Gemini client singleton, and resize the Supabase `reel_chunks.embedding` column accordingly.

**Architecture:** A new `services/gemini_client.py` module holds the single `genai.Client` singleton shared by both `embedder.py` and `rag.py`. `embedder.py` swaps sentence-transformers for Gemini API calls using `task_type` instead of an instruction prefix. `workers/tasks.py` wraps Step 20 in retryable `EmbeddingError` handling.

**Tech Stack:** `google-genai` (already installed), Supabase `pgvector`, Celery, pytest

---

## File Map

| Action | File | What changes |
|---|---|---|
| CREATE | `backend/services/gemini_client.py` | Shared `genai.Client` lazy singleton |
| REWRITE | `backend/services/embedder.py` | Replaces sentence-transformers with Gemini API |
| MODIFY | `backend/services/rag.py` | Drops own client singleton, imports `get_gemini_client` |
| MODIFY | `backend/workers/tasks.py` | Wraps Step 20 in `EmbeddingError` retry handling |
| MODIFY | `backend/requirements.txt` | Removes `sentence-transformers==3.2.1` |
| MODIFY | `backend/.env.example` | Updates GEMINI_API_KEY comment |
| REWRITE | `backend/tests/test_embedder.py` | Replaces sentence-transformers mocks with Gemini mocks |
| MODIFY | `backend/tests/test_rag.py` | Updates `_get_gemini_client` patch targets + embed dimension |
| CREATE | `supabase/migrations/20260522000001_resize_embeddings_to_768.sql` | Wipes reels/chunks, resizes to 768, updates SQL fn |

---

## Task 1: Create `services/gemini_client.py`

**Files:**
- Create: `backend/services/gemini_client.py`

- [ ] **Step 1: Create the file**

```python
# backend/services/gemini_client.py
from __future__ import annotations

from google import genai

from config import get_config

_client: genai.Client | None = None


def get_gemini_client() -> genai.Client:
    global _client
    if _client is None:
        key = get_config().GEMINI_API_KEY
        if not key:
            raise RuntimeError("GEMINI_API_KEY not configured")
        _client = genai.Client(api_key=key)
    return _client
```

- [ ] **Step 2: Verify the import works**

Run from `backend/` with virtualenv active:
```bash
cd backend && source venv/bin/activate && python -c "from services.gemini_client import get_gemini_client; print('import OK')"
```
Expected: `import OK`

- [ ] **Step 3: Commit**

```bash
git add backend/services/gemini_client.py
git commit -m "feat: add shared Gemini client singleton"
```

---

## Task 2: Rewrite `tests/test_embedder.py` (red phase)

**Files:**
- Rewrite: `backend/tests/test_embedder.py`

- [ ] **Step 1: Replace the entire file**

```python
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
```

- [ ] **Step 2: Run and confirm tests fail**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/test_embedder.py -v
```
Expected: several failures including `ImportError: cannot import name 'EmbeddingError'` and `AssertionError` on dimension checks. This is the expected red phase.

---

## Task 3: Rewrite `services/embedder.py` (green phase)

**Files:**
- Rewrite: `backend/services/embedder.py`

- [ ] **Step 1: Replace the entire file**

```python
# backend/services/embedder.py
from __future__ import annotations

from google.genai import types

from services.gemini_client import get_gemini_client

_MODEL = "text-embedding-004"


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
            config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
        )
        return list(response.embeddings[0].values)
    except Exception as exc:
        raise EmbeddingError(str(exc), is_retryable=True) from exc


def embed_query(text: str) -> list[float]:
    try:
        response = get_gemini_client().models.embed_content(
            model=_MODEL,
            contents=text,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
        )
        return list(response.embeddings[0].values)
    except Exception as exc:
        raise EmbeddingError(str(exc), is_retryable=True) from exc
```

- [ ] **Step 2: Run tests and confirm they pass**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/test_embedder.py -v
```
Expected: all tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/services/embedder.py backend/tests/test_embedder.py
git commit -m "feat: replace sentence-transformers with Gemini text-embedding-004"
```

---

## Task 4: Update `services/rag.py`

**Files:**
- Modify: `backend/services/rag.py`

`rag.py` currently manages its own Gemini client with a `_gemini_client` global and `_get_gemini_client()` function. These need to be removed and replaced with the shared singleton.

- [ ] **Step 1: Remove the private client singleton and replace the import**

In `backend/services/rag.py`:

Remove these lines (lines 45–55):
```python
_gemini_client: genai.Client | None = None


def _get_gemini_client() -> genai.Client:
    global _gemini_client
    if _gemini_client is None:
        cfg = get_config()
        if not cfg.GEMINI_API_KEY:
            raise RagGenerationError("GEMINI_API_KEY not configured")
        _gemini_client = genai.Client(api_key=cfg.GEMINI_API_KEY)
    return _gemini_client
```

Add this import at the top of the imports section (after `from config import get_config`):
```python
from services.gemini_client import get_gemini_client
```

Remove the `from config import get_config` import if it's no longer used elsewhere in the file (it was only used inside `_get_gemini_client()`).

- [ ] **Step 2: Replace all `_get_gemini_client()` call sites**

In `answer()` (around line 152), change:
```python
gemini = _get_gemini_client()
```
to:
```python
gemini = get_gemini_client()
```

- [ ] **Step 3: Verify the import works**

```bash
cd backend && source venv/bin/activate && python -c "from services.rag import answer; print('import OK')"
```
Expected: `import OK`

- [ ] **Step 4: Commit**

```bash
git add backend/services/rag.py
git commit -m "refactor: use shared Gemini client singleton in rag.py"
```

---

## Task 5: Update `tests/test_rag.py`

**Files:**
- Modify: `backend/tests/test_rag.py`

All tests currently patch `services.rag._get_gemini_client`. After Task 4, `rag.py` imports `get_gemini_client` from `services.gemini_client`, so the patch target is now `services.rag.get_gemini_client`. The embed dimension in mocks also changes from 384 to 768.

- [ ] **Step 1: Replace every patch target and fix embed dimensions**

Replace all occurrences of:
```python
patch("services.rag._get_gemini_client", return_value=mock_client)
```
with:
```python
patch("services.rag.get_gemini_client", return_value=mock_client)
```

There are 6 occurrences (one per test function). Also replace all occurrences of:
```python
patch("services.rag.embed_query", return_value=[0.1] * 384)
```
with:
```python
patch("services.rag.embed_query", return_value=[0.1] * 768)
```

There are 6 occurrences of the embed_query mock too.

The full updated file:

```python
# backend/tests/test_rag.py
import json
from unittest.mock import MagicMock, call, patch

import pytest


def _make_session(user_id="user-abc", category_id="cat-xyz"):
    return {"id": "session-123", "user_id": user_id, "category_id": category_id}


def _gemini_response(content: str):
    mock = MagicMock()
    mock.text = content
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
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        _gemini_response(hyde_json),
        _gemini_response("The best sunscreen for oily skin is..."),
    ]
    mock_db = _supabase_with_chunks([_fake_chunk()])

    with patch("services.rag.get_gemini_client", return_value=mock_client), \
         patch("services.rag.get_supabase", return_value=mock_db), \
         patch("services.rag.embed_query", return_value=[0.1] * 768):
        result = answer(_make_session(), "best sunscreens for oily skin", [])

    assert result["content"] == "The best sunscreen for oily skin is..."
    assert len(result["sources"]) == 1
    assert result["sources"][0]["reel_id"] == "reel-1"
    assert result["sources"][0]["creator_handle"] == "skinguru"


# --- HyDE fallback ---

def test_hyde_json_parse_failure_falls_back_to_raw_query():
    from services.rag import answer

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        _gemini_response("not valid json {{"),
        _gemini_response("I couldn't find much"),
    ]
    mock_db = _supabase_with_chunks([])

    with patch("services.rag.get_gemini_client", return_value=mock_client), \
         patch("services.rag.get_supabase", return_value=mock_db), \
         patch("services.rag.embed_query", return_value=[0.1] * 768) as mock_embed:
        answer(_make_session(), "best sunscreens", [])

    mock_embed.assert_called_once_with("best sunscreens")


def test_hyde_gemini_exception_falls_back_to_raw_query():
    from services.rag import answer

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        Exception("timeout"),
        _gemini_response("answer"),
    ]
    mock_db = _supabase_with_chunks([])

    with patch("services.rag.get_gemini_client", return_value=mock_client), \
         patch("services.rag.get_supabase", return_value=mock_db), \
         patch("services.rag.embed_query", return_value=[0.1] * 768) as mock_embed:
        answer(_make_session(), "my question", [])

    mock_embed.assert_called_once_with("my question")


# --- Creator filter ---

def test_creator_filter_extracted_and_passed_to_rpc():
    from services.rag import answer

    hyde_json = json.dumps({
        "hypothetical_doc": "skincareguru reviews sunscreen",
        "filters": {"creator_handle": "skincareguru"},
    })
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        _gemini_response(hyde_json),
        _gemini_response("Found reels by skincareguru"),
    ]
    mock_db = _supabase_with_chunks([])

    with patch("services.rag.get_gemini_client", return_value=mock_client), \
         patch("services.rag.get_supabase", return_value=mock_db), \
         patch("services.rag.embed_query", return_value=[0.1] * 768):
        answer(_make_session(), "reels by creator skincareguru", [])

    rpc_kwargs = mock_db.rpc.call_args[1]
    assert rpc_kwargs["p_creator"] == "skincareguru"


# --- Deduplication ---

def test_duplicate_reel_id_deduplication_keeps_highest_similarity():
    from services.rag import answer

    hyde_json = json.dumps({"hypothetical_doc": "doc", "filters": {"creator_handle": None}})
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        _gemini_response(hyde_json),
        _gemini_response("answer"),
    ]
    chunks = [
        _fake_chunk(reel_id="reel-1", similarity=0.5),
        _fake_chunk(reel_id="reel-1", similarity=0.9),
        _fake_chunk(reel_id="reel-2", similarity=0.7),
    ]
    mock_db = _supabase_with_chunks(chunks)

    with patch("services.rag.get_gemini_client", return_value=mock_client), \
         patch("services.rag.get_supabase", return_value=mock_db), \
         patch("services.rag.embed_query", return_value=[0.1] * 768):
        result = answer(_make_session(), "sunscreen", [])

    source_ids = [s["reel_id"] for s in result["sources"]]
    assert source_ids.count("reel-1") == 1
    assert "reel-2" in source_ids


# --- Zero results ---

def test_zero_chunks_returns_empty_sources():
    from services.rag import answer

    hyde_json = json.dumps({"hypothetical_doc": "doc", "filters": {"creator_handle": None}})
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        _gemini_response(hyde_json),
        _gemini_response("I couldn't find relevant reels in this category"),
    ]
    mock_db = _supabase_with_chunks([])

    with patch("services.rag.get_gemini_client", return_value=mock_client), \
         patch("services.rag.get_supabase", return_value=mock_db), \
         patch("services.rag.embed_query", return_value=[0.1] * 768):
        result = answer(_make_session(), "sunscreen", [])

    assert result["sources"] == []


# --- Generation failure ---

def test_generation_failure_raises_rag_generation_error():
    from services.rag import RagGenerationError, answer

    hyde_json = json.dumps({"hypothetical_doc": "doc", "filters": {"creator_handle": None}})
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = [
        _gemini_response(hyde_json),
        Exception("Gemini 503"),
    ]
    mock_db = _supabase_with_chunks([_fake_chunk()])

    with patch("services.rag.get_gemini_client", return_value=mock_client), \
         patch("services.rag.get_supabase", return_value=mock_db), \
         patch("services.rag.embed_query", return_value=[0.1] * 768):
        with pytest.raises(RagGenerationError):
            answer(_make_session(), "sunscreen", [])
```

- [ ] **Step 2: Run rag tests**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/test_rag.py -v
```
Expected: all tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_rag.py
git commit -m "test: update rag tests for shared Gemini client + 768-dim embed mock"
```

---

## Task 6: Update `workers/tasks.py` (Step 20 error handling)

**Files:**
- Modify: `backend/workers/tasks.py`

Currently Step 20 has no error handling — an embedding API failure crashes the entire task without a retry. Add `EmbeddingError` to the import and wrap the `embed_document()` call.

- [ ] **Step 1: Update the import line**

Find this line near the top of `backend/workers/tasks.py`:
```python
from services.embedder import build_chunk_text, embed_document
```

Replace with:
```python
from services.embedder import EmbeddingError, build_chunk_text, embed_document
```

- [ ] **Step 2: Wrap Step 20 in error handling**

Find the Step 20 block (around line 219–234):
```python
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

Replace with:
```python
        if _chunk_text:
            log.info("step 20 | embedding | chars=%d", len(_chunk_text))
            try:
                _embedding = embed_document(_chunk_text)
            except EmbeddingError as exc:
                log.warning(
                    "step 20 | embedding failed | retryable=%s | %s",
                    exc.is_retryable,
                    exc,
                )
                return _handle_pipeline_error(
                    self, supabase, reel_id, exc, exc.is_retryable, log
                )
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

- [ ] **Step 3: Verify import is clean**

```bash
cd backend && source venv/bin/activate && python -c "from workers.tasks import process_reel; print('import OK')"
```
Expected: `import OK`

- [ ] **Step 4: Run tasks resilience tests**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/test_tasks_resilience.py -v
```
Expected: all existing tests PASS (Step 20 mocks in these tests patch `embed_document` directly — no change needed there)

- [ ] **Step 5: Commit**

```bash
git add backend/workers/tasks.py
git commit -m "feat: wrap Step 20 embed_document call in retryable EmbeddingError handling"
```

---

## Task 7: Remove `sentence-transformers` from `requirements.txt`

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/.env.example`

- [ ] **Step 1: Remove sentence-transformers**

In `backend/requirements.txt`, remove this line:
```
sentence-transformers==3.2.1
```

Also update the comment above `google-genai` to reflect it now also handles embeddings. Replace:
```
# Google Gemini API — used for classification and RAG
google-genai
# Local embedding model (no API, runs in Celery worker)
sentence-transformers==3.2.1
```
with:
```
# Google Gemini API — used for classification, RAG, and embeddings (text-embedding-004)
google-genai
```

- [ ] **Step 2: Update `.env.example` comment**

In `backend/.env.example`, update the `GEMINI_API_KEY` comment from:
```
# Google Gemini API (Classification + RAG — free tier)
```
to:
```
# Google Gemini API (Classification + RAG + Embeddings — free tier)
```

- [ ] **Step 3: Verify all imports still work without sentence-transformers**

```bash
cd backend && source venv/bin/activate && python -c "
from services.gemini_client import get_gemini_client
from services.embedder import build_chunk_text, embed_document, embed_query, EmbeddingError
from services.rag import answer
from workers.tasks import process_reel
print('All imports OK')
"
```
Expected: `All imports OK`

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt backend/.env.example
git commit -m "chore: remove sentence-transformers, GEMINI_API_KEY now covers embeddings"
```

---

## Task 8: Write and apply DB migration

**Files:**
- Create: `supabase/migrations/20260522000001_resize_embeddings_to_768.sql`

- [ ] **Step 1: Create the migration file**

```sql
-- supabase/migrations/20260522000001_resize_embeddings_to_768.sql
-- Wipe all reel data (clean slate — migrating from bge-small-en-v1.5 384-dim to
-- text-embedding-004 768-dim; existing embeddings are incompatible)
truncate table public.reel_chunks cascade;
truncate table public.reels cascade;

-- Resize embedding column from 384 to 768
drop index if exists idx_reel_chunks_embedding;

alter table public.reel_chunks
  alter column embedding type vector(768);

create index idx_reel_chunks_embedding on public.reel_chunks
  using ivfflat (embedding vector_cosine_ops) with (lists = 50);

-- Update match_reel_chunks to accept 768-dim query vector
create or replace function match_reel_chunks(
    query_embedding vector(768),
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

- [ ] **Step 2: Apply the migration**

```bash
supabase db push
```
Expected: migration applied successfully, no errors.

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260522000001_resize_embeddings_to_768.sql
git commit -m "feat: resize reel_chunks.embedding to vector(768) for text-embedding-004"
```

---

## Task 9: Run full test suite and smoke test

**Files:** none

- [ ] **Step 1: Run all backend tests**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/ -v
```
Expected: all tests PASS, no failures.

- [ ] **Step 2: Verify Celery worker boots**

Start Redis if not running:
```bash
docker compose up -d
```

Start Celery (separate terminal, venv active):
```bash
cd backend && source venv/bin/activate && celery -A workers.celery_app worker --loglevel=info
```
Expected output includes: `celery@<hostname> ready.`

- [ ] **Step 3: Smoke-test the ping task**

```bash
cd backend && source venv/bin/activate && python -c "
from workers.tasks import ping
result = ping.delay().get(timeout=5)
print('Ping result:', result)
"
```
Expected: `Ping result: pong`

- [ ] **Step 4: End-to-end reel smoke test**

With FastAPI running (`uvicorn main:app --reload --host 0.0.0.0 --port 8000`) and Celery worker running, share a new Instagram Reel URL via the iOS Share Extension. Then verify in Supabase:

```sql
-- Run in Supabase SQL editor
select id, status, transcript, has_audio from reels order by created_at desc limit 1;
select reel_id, chunk_index, length(content) as content_len, array_length(embedding, 1) as embedding_dim
from reel_chunks order by created_at desc limit 1;
```
Expected: `embedding_dim = 768`, reel status = `ready` or `pending_category`.
