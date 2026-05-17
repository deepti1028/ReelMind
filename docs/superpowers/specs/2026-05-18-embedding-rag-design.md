# Embedding + RAG Design
**Date:** 2026-05-18
**Status:** Approved

---

## Problem

ReelMind users save Instagram Reels into categories. The chat feature lets a user open a category and ask natural-language questions against their saved reels — e.g. "best sunscreens for oily skin", "reels by creator @skinfluencer", "which reel mentioned XYZ brand?". The user should not need to be precise or know how to phrase things.

Chunking is out of scope: short-form reels (15–60s, ~50–200 words) fit in a single embedding. The real design challenge is in **what to embed** and **how to retrieve + generate**.

---

## Decisions

| Concern | Decision | Reason |
|---|---|---|
| Embedding model | `BAAI/bge-small-en-v1.5` (384-dim) | Better retrieval benchmarks than `all-MiniLM-L6-v2` at same dimension; free, local |
| Chunking | 1 chunk per reel (`chunk_index=0`) | Short-form content fits in 512 tokens; no sub-reel granularity needed |
| Chunk content | hashtags + caption + transcript (enriched) | All three signals needed; caption alone handles music-only reels |
| Query strategy | HyDE (Hypothetical Document Embedding) | Bridges the query↔document embedding space mismatch; handles vague/informal queries |
| Filter extraction | Co-located with HyDE in one Groq call | Creator handle queries need a structured SQL filter, not semantic search |
| Retrieval | pgvector cosine similarity via `match_reel_chunks` RPC | Filtered by user_id + category_id + optional creator; threshold 0.3 |
| Generation LLM | Groq Llama 3.3 70B | Already in use for classification; free tier; 128k context |
| Chat scope | Category-scoped only (MVP) | Global cross-category chat deferred |

---

## Architecture

```
INGESTION (Celery worker)
  process_reel task
    Step 15 — download
    Step 16 — transcribe
    Step 17 — build signal
    Step 20 — embed reel        ← NEW (before classification)
    Step 18 — classify
    Step 19 — confidence routing + FCM push

  services/embedder.py          ← NEW
    - loads bge-small-en-v1.5 as process-level singleton
    - builds enriched chunk text: "{hashtags}\n{caption}\n{transcript}"
    - upserts 1 row into reel_chunks (chunk_index=0)

CHAT (FastAPI)
  POST /api/v1/chat/sessions                     ← new
  POST /api/v1/chat/sessions/{id}/messages       ← new (triggers RAG)
  GET  /api/v1/chat/sessions/{id}/messages       ← new

  services/rag.py               ← NEW
    1. HyDE + filter extraction  (Groq Llama call #1)
    2. embed hypothetical doc    (bge-small, local)
    3. pgvector retrieval        (match_reel_chunks RPC)
    4. answer generation         (Groq Llama call #2)
    5. persist messages + return sources

DB
  - Migrate reel_chunks.embedding: vector(1536) → vector(384)
  - Add match_reel_chunks() Postgres function
```

---

## DB Changes

### Migration 1 — resize embedding column
File: `supabase/migrations/20260518000001_resize_reel_chunks_embedding.sql`

```sql
drop index if exists idx_reel_chunks_embedding;

alter table public.reel_chunks
  alter column embedding type vector(384);

create index idx_reel_chunks_embedding on public.reel_chunks
  using ivfflat (embedding vector_cosine_ops) with (lists = 50);
```

### Migration 2 — retrieval function
File: `supabase/migrations/20260518000002_add_match_reel_chunks_fn.sql`

```sql
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

---

## Ingestion: `services/embedder.py`

Single responsibility: embed text. Shared by ingestion pipeline (documents) and chat RAG (query-side HyDE docs).

```python
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
    """Embed reel content for storage. No instruction prefix for bge-small documents."""
    return _get_model().encode(text, normalize_embeddings=True).tolist()

def embed_query(text: str) -> list[float]:
    """Embed a query or hypothetical doc for retrieval. Uses bge-small instruction prefix."""
    prefixed = f"Represent this sentence for searching relevant passages: {text}"
    return _get_model().encode(prefixed, normalize_embeddings=True).tolist()
```

**Model loading:** `_get_model()` is a process-level singleton. First call downloads ~33 MB and keeps the model in worker memory. No reload cost for subsequent reels.

### Step 20 insertion point in `workers/tasks.py`

Inserted between Step 17 (signal built) and Step 18 (classification). Embedding is purely content-based — does not depend on the category result. Runs in both the `ready` and `pending_category` routing paths since it executes before either early return.

```python
# Step 20 — embed reel content
chunk_text = build_chunk_text(
    transcript=_transcript_text,
    caption=meta.caption,
    hashtags=meta.hashtags,
)
if chunk_text:
    log.info("step 20 | embedding | chars=%d", len(chunk_text))
    embedding = embed_document(chunk_text)
    supabase.table("reel_chunks").upsert({
        "reel_id": reel_id,
        "user_id": reel_data["user_id"],
        "chunk_index": 0,
        "content": chunk_text,
        "embedding": embedding,
    }).execute()
    log.info("step 20 | chunk stored")
else:
    log.warning("step 20 | no content to embed — skipping")
```

If `build_chunk_text` returns `None` (the `NoSignalError` path — no transcript, no caption, no hashtags), embedding is skipped. That reel is already marked `uncategorised` and excluded from chat retrieval via `status = 'ready'` filter in `match_reel_chunks`.

---

## Chat API: `api/v1/chat.py`

### Schemas

```python
class CreateSessionRequest(BaseModel):
    category_id: uuid.UUID

class SendMessageRequest(BaseModel):
    content: str

class ReelSource(BaseModel):
    reel_id: str
    creator_handle: str | None
    thumbnail_url: str | None
    caption: str | None

class MessageResponse(BaseModel):
    message_id: str
    content: str
    sources: list[ReelSource]
```

### Endpoints

**`POST /api/v1/chat/sessions`**
- Auth: `get_current_user_id`
- Creates a `chat_sessions` row with `user_id` and `category_id`
- Returns `{ session_id }`

**`POST /api/v1/chat/sessions/{session_id}/messages`**
- Auth: `get_current_user_id`
- Ownership check: `chat_sessions.user_id == authenticated user_id` → 403 otherwise
- Loads last 6 messages from session (3 turns) for conversational context
- Calls `rag.answer(session, user_message, history)` → `{content, sources}`
- Returns `MessageResponse`

**`GET /api/v1/chat/sessions/{session_id}/messages`**
- Auth: `get_current_user_id`
- Ownership check: same as above
- Returns messages ordered by `created_at asc`

---

## RAG Pipeline: `services/rag.py`

### Step 1 — HyDE + filter extraction (Groq call #1)

```
System prompt:
  "You are helping retrieve relevant Instagram Reel transcripts for a user's question.
   Do two things:
   1. Write a short hypothetical reel transcript (3–5 sentences) that would perfectly
      answer the question. Write in first person as if you are the creator speaking.
   2. Extract any explicit filters mentioned: creator username only.
   Return valid JSON only:
   {"hypothetical_doc": "...", "filters": {"creator_handle": null}}"
```

On JSON parse failure → fall back to `embed_query(raw_user_message)`. No error surface to user.

### Step 2 — Embed hypothetical doc

```python
query_vec = embed_query(hyde_result["hypothetical_doc"])
# Fallback: embed_query(user_message) if HyDE failed
```

`embed_query` uses the bge-small instruction prefix so the query embedding aligns with how documents were encoded.

### Step 3 — Retrieval

```python
results = supabase.rpc("match_reel_chunks", {
    "query_embedding": query_vec,
    "p_user_id": user_id,
    "p_category_id": str(session["category_id"]),
    "p_creator": filters.get("creator_handle"),
    "match_count": 10,
    "threshold": 0.3,
}).execute()
```

Deduplicate by `reel_id` (keep highest similarity per reel), take top 5 for generation context.

### Step 4 — Answer generation (Groq call #2)

```
System prompt:
  "You are a helpful assistant answering questions based on the user's saved Instagram Reels.
   Answer using ONLY the reel content provided. Be specific and conversational.
   If the reels don't contain enough to answer, say so honestly — don't make things up."

User message:
  "Reels:\n{context_block}\n\nQuestion: {user_message}"

Context block: top 5 chunks formatted as:
  [Reel by @creator_handle]
  {content}
  ---
```

Conversation history (last 6 messages) is injected between system prompt and the final user message to support follow-up queries.

### Step 5 — Persist + return

```python
# User message — no sources
supabase.table("chat_messages").insert({
    "session_id": session_id, "role": "user", "content": user_message
}).execute()

# Assistant message — sources stored as JSONB array
supabase.table("chat_messages").insert({
    "session_id": session_id, "role": "assistant",
    "content": answer,
    "sources": [
        {"reel_id": r["reel_id"], "creator_handle": r["creator_handle"],
         "thumbnail_url": r["thumbnail_url"], "caption": r["caption"]}
        for r in top_chunks
    ],
}).execute()
```

---

## Error Handling

| Failure point | Behaviour |
|---|---|
| HyDE Groq call fails | Fall back to raw query embedding; continue silently |
| JSON parse fails on HyDE response | Same fallback as above |
| Zero chunks retrieved | Return `"I couldn't find relevant reels in this category"`, empty sources |
| Generation Groq call fails | Raise HTTP 503; do not save partial messages |
| Step 20 embedding fails (ingestion) | Log warning, skip chunk insert; reel still classified + notified |

---

## Upgrade Paths (deferred)

- **Hybrid retrieval (vector + tsvector):** add a `tsvector` GIN index on `reel_chunks.content` + RRF merge if exact brand-name recall proves weak
- **Cross-encoder reranking:** `cross-encoder/ms-marco-MiniLM-L-6-v2` (local, free) — rerank top-20 → top-5 if precision is a problem
- **Global chat:** remove `p_category_id` filter and surface category name in sources
- **Larger embedding model:** swap to `BAAI/bge-base-en-v1.5` (768-dim) with a DB migration if retrieval quality needs improvement

---

## Files Touched

| File | Change |
|---|---|
| `supabase/migrations/20260518000001_resize_reel_chunks_embedding.sql` | New migration |
| `supabase/migrations/20260518000002_add_match_reel_chunks_fn.sql` | New migration |
| `backend/services/embedder.py` | New service |
| `backend/services/rag.py` | New service |
| `backend/api/v1/chat.py` | New router |
| `backend/main.py` | Register chat router |
| `backend/workers/tasks.py` | Insert Step 20 between Step 17 and Step 18 |
| `backend/requirements.txt` | Add `sentence-transformers`, `groq` already present |
