# Gemini Embedding Migration Design
**Date:** 2026-05-22  
**Status:** Approved

## Summary

Replace the local `BAAI/bge-small-en-v1.5` sentence-transformers model with Google's `text-embedding-004` API. The current model runs locally inside the Celery worker (384-dim, no API, no network). The new model is a Gemini API call (768-dim). A shared Gemini client singleton is extracted so `embedder.py` and `rag.py` no longer each manage their own client.

---

## Decision Log

| Decision | Choice | Reason |
|---|---|---|
| Target model | `text-embedding-004` | Stable, 768-dim, idiomatic Gemini |
| Dimensions | 768 | Fixed by model; replaces 384 |
| Task types | `RETRIEVAL_DOCUMENT` / `RETRIEVAL_QUERY` | Replaces BGE instruction prefix; idiomatic |
| Client architecture | Shared singleton (`gemini_client.py`) | Avoids two independent singletons in `embedder.py` and `rag.py` |
| API failures | `EmbeddingError(is_retryable=True)` | Retries up to 3× with 60s backoff, same as transcription |
| Existing data | Truncate `reels` + `reel_chunks` in migration | Clean slate; user will save a new reel to test |

---

## Architecture

```
services/
  gemini_client.py   ← NEW — shared genai.Client singleton
  embedder.py        ← MODIFIED — Gemini API replaces sentence-transformers
  rag.py             ← MODIFIED — drops own _gemini_client, imports get_gemini_client()
workers/
  tasks.py           ← MODIFIED — Step 20 wraps EmbeddingError as retryable
supabase/migrations/
  20260522000001_resize_embeddings_to_768.sql  ← NEW
```

---

## Files Changed

### NEW — `backend/services/gemini_client.py`

Lazy singleton. Initialised once from `GEMINI_API_KEY`. Raises `RuntimeError` if the key is missing (config error — not retryable, bubbles up as task failure).

```python
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

### MODIFIED — `backend/services/embedder.py`

- Remove: `SentenceTransformer`, `_model` global, `_get_model()`
- Remove: `sentence-transformers` import
- Add: `EmbeddingError(Exception)` with `is_retryable: bool` — same pattern as `TranscriptionError`
- Add: `from services.gemini_client import get_gemini_client`
- `build_chunk_text()` — unchanged
- `embed_document(text)` — calls Gemini with `task_type="RETRIEVAL_DOCUMENT"`, returns `list[float]` (768 values)
- `embed_query(text)` — calls Gemini with `task_type="RETRIEVAL_QUERY"`, returns `list[float]` (768 values). Old instruction-prefix string deleted.
- All Gemini API exceptions caught → raise `EmbeddingError(is_retryable=True)`

API call pattern:
```python
from google.genai import types

response = get_gemini_client().models.embed_content(
    model="text-embedding-004",
    contents=text,
    config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
)
return list(response.embeddings[0].values)
```

### MODIFIED — `backend/services/rag.py`

- Remove: `_gemini_client` global, `_get_gemini_client()` function, `RagGenerationError("GEMINI_API_KEY not configured")` guard
- Add: `from services.gemini_client import get_gemini_client`
- Replace all `_get_gemini_client()` call sites with `get_gemini_client()`
- `RagGenerationError` stays in `rag.py` — it's a RAG concern, not a client concern
- `answer()` function signature and all retrieval/generation logic unchanged

### MODIFIED — `backend/workers/tasks.py`

Step 20 currently has no error handling around `embed_document()`. Add:

```python
from services.embedder import EmbeddingError, build_chunk_text, embed_document

# Step 20
if _chunk_text:
    log.info("step 20 | embedding | chars=%d", len(_chunk_text))
    try:
        _embedding = embed_document(_chunk_text)
    except EmbeddingError as exc:
        log.warning("step 20 | embedding failed | retryable=%s | %s", exc.is_retryable, exc)
        return _handle_pipeline_error(self, supabase, reel_id, exc, exc.is_retryable, log)
    supabase.table("reel_chunks").upsert({...}).execute()
```

### MODIFIED — `backend/requirements.txt`

- Remove: `sentence-transformers==3.2.1`
- `google-genai` already present — no change needed

### NEW — `supabase/migrations/20260522000001_resize_embeddings_to_768.sql`

```sql
-- Wipe all reel data (clean slate for Gemini embedding migration)
truncate table public.reel_chunks cascade;
truncate table public.reels cascade;

-- Resize embedding column from 384 (bge-small-en-v1.5) to 768 (text-embedding-004)
drop index if exists idx_reel_chunks_embedding;

alter table public.reel_chunks
  alter column embedding type vector(768);

create index idx_reel_chunks_embedding on public.reel_chunks
  using ivfflat (embedding vector_cosine_ops) with (lists = 50);

-- Update match_reel_chunks to use 768-dim query vector
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

---

## Tests

### `backend/tests/test_embedder.py` — full rewrite

- Remove: numpy import, `_get_model` patch, 384-dim assertions, instruction-prefix assertions
- Add: mock `get_gemini_client()` — return a mock whose `.models.embed_content()` returns an object with `.embeddings[0].values` = list of 768 floats
- Test `embed_document` calls with `task_type="RETRIEVAL_DOCUMENT"`
- Test `embed_query` calls with `task_type="RETRIEVAL_QUERY"`
- Test that a Gemini API exception raises `EmbeddingError(is_retryable=True)`
- Test `build_chunk_text` — unchanged, tests stay identical

### `backend/tests/test_rag.py`

- Update any mock that patches `services.embedder._get_model` or patches at sentence-transformers level
- Mock `services.embedder.get_gemini_client` or `services.embedder.embed_query` directly (the latter is simpler and already decoupled)

---

## Error Handling

| Failure | Behaviour |
|---|---|
| `GEMINI_API_KEY` missing | `RuntimeError` from `gemini_client.py`, task fails immediately (no retry) |
| Gemini API error (rate limit, timeout, quota) | `EmbeddingError(is_retryable=True)`, Celery retries up to 3× with 60s/120s/180s backoff |
| No content to embed (`_chunk_text` is None) | Log warning, skip Step 20 — unchanged from current behaviour |

---

## Migration Checklist (for implementation plan)

1. Create `services/gemini_client.py`
2. Update `services/embedder.py`
3. Update `services/rag.py`
4. Update `workers/tasks.py` (Step 20 error handling)
5. Remove `sentence-transformers` from `requirements.txt`
6. Write and apply DB migration (`supabase db push`)
7. Rewrite `tests/test_embedder.py`
8. Update `tests/test_rag.py`
9. Smoke test: save a new reel end-to-end, verify chunk is stored with 768-dim embedding
