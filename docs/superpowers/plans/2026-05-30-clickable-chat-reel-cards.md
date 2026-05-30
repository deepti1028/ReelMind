# Clickable Chat Reel Cards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make reel source cards in the chat view tappable — threading `url` from the Supabase SQL function through the backend API and into the iOS `ReelSource` model so `ChatReelCard` (already written in `ChatView.swift`) can open the reel in Instagram.

**Architecture:** Add `r.url` to the `match_reel_chunks` SQL function return → include it in the RAG service sources dict → add it to the backend `ReelSource` Pydantic model → add it to the iOS `ReelSource` struct. The `ChatReelCard` UI code in `ChatView.swift` already references `source.url` and will compile once the iOS model is updated.

**Tech Stack:** PostgreSQL (Supabase), Python/FastAPI/Pydantic, Swift/SwiftUI, pytest

---

## File Map

| File | Change |
|---|---|
| `supabase/migrations/20260530000002_add_url_to_match_reel_chunks.sql` | **Create** — adds `url text` to function return + SELECT |
| `backend/services/rag.py` | **Modify** — add `"url": r.get("url")` to sources dict |
| `backend/api/v1/chat.py` | **Modify** — add `url: Optional[str] = None` to `ReelSource` |
| `backend/tests/test_chat_endpoint.py` | **Modify** — add test asserting `url` appears in sources response |
| `frontend/Services/ChatService.swift` | **Modify** — add `let url: String?` + CodingKey to `ReelSource` |
| `frontend/Views/ChatView.swift` | **No change** — `ChatReelCard` already written, compiles once iOS model is updated |

---

## Task 1: SQL Migration — add `url` to `match_reel_chunks`

**Files:**
- Create: `supabase/migrations/20260530000002_add_url_to_match_reel_chunks.sql`

- [ ] **Step 1: Create the migration file**

Create `supabase/migrations/20260530000002_add_url_to_match_reel_chunks.sql` with this exact content:

```sql
-- Extend match_reel_chunks to return the reel's Instagram URL.
-- Uses CREATE OR REPLACE — non-destructive, no downtime.
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
    caption        text,
    url            text
)
language sql as $$
    select
        rc.reel_id,
        rc.content,
        1 - (rc.embedding <=> query_embedding) as similarity,
        r.creator_handle,
        r.thumbnail_url,
        r.caption,
        r.url
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
cd /Users/deeptijain/Desktop/Deepti/Projects/ReelMind
supabase db push
```

Expected output contains: `Applying migration 20260530000002_add_url_to_match_reel_chunks.sql` with no errors.

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260530000002_add_url_to_match_reel_chunks.sql
git commit -m "feat: add url to match_reel_chunks SQL function"
```

---

## Task 2: Backend — RAG service + API model (TDD)

**Files:**
- Modify: `backend/services/rag.py` (lines 153–160)
- Modify: `backend/api/v1/chat.py` (line 31)
- Modify: `backend/tests/test_chat_endpoint.py`

- [ ] **Step 1: Write the failing test**

Open `backend/tests/test_chat_endpoint.py`. Add this test after `test_send_message_returns_content_and_sources` (around line 118):

```python
@patch("api.v1.chat.get_supabase")
@patch("api.v1.chat.rag")
def test_send_message_sources_include_url(mock_rag, mock_get_supabase):
    mock_get_supabase.return_value = _make_chat_db()
    mock_rag.answer.return_value = {
        "content": "Use SPF 50",
        "sources": [{
            "reel_id": "r1",
            "creator_handle": "skincareguru",
            "thumbnail_url": "https://cdn.example.com/thumb.jpg",
            "caption": "Best sunscreen",
            "url": "https://www.instagram.com/reel/abc123/",
        }],
    }

    client = _build_client()
    resp = client.post(
        f"/api/v1/chat/sessions/{SESSION_ID}/messages",
        json={"content": "sunscreen for oily skin"},
    )

    assert resp.status_code == 200
    sources = resp.json()["sources"]
    assert len(sources) == 1
    assert sources[0]["url"] == "https://www.instagram.com/reel/abc123/"
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
cd /Users/deeptijain/Desktop/Deepti/Projects/ReelMind/backend
source venv/bin/activate
pytest tests/test_chat_endpoint.py::test_send_message_sources_include_url -v
```

Expected: **FAILED** — `assert None == "https://www.instagram.com/reel/abc123/"` (url stripped by Pydantic because field doesn't exist yet).

- [ ] **Step 3: Add `url` to the RAG sources dict**

Open `backend/services/rag.py`. Find the `return` block near line 151 and replace the sources list:

```python
    return {
        "content": generated,
        "sources": [
            {
                "reel_id": str(r["reel_id"]),
                "creator_handle": r.get("creator_handle"),
                "thumbnail_url": r.get("thumbnail_url"),
                "caption": r.get("caption"),
                "url": r.get("url"),
            }
            for r in chunks
        ],
    }
```

- [ ] **Step 4: Add `url` to the backend `ReelSource` Pydantic model**

Open `backend/api/v1/chat.py`. Find the `ReelSource` class (around line 26) and add the `url` field:

```python
class ReelSource(BaseModel):
    reel_id: str
    creator_handle: Optional[str] = None
    thumbnail_url: Optional[str] = None
    caption: Optional[str] = None
    url: Optional[str] = None
```

- [ ] **Step 5: Run the test to confirm it passes**

```bash
pytest tests/test_chat_endpoint.py::test_send_message_sources_include_url -v
```

Expected: **PASSED**

- [ ] **Step 6: Run the full test suite to confirm no regressions**

```bash
pytest tests/test_chat_endpoint.py -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/services/rag.py backend/api/v1/chat.py backend/tests/test_chat_endpoint.py
git commit -m "feat: include reel url in chat sources response"
```

---

## Task 3: iOS — Add `url` to `ReelSource`

**Files:**
- Modify: `frontend/Services/ChatService.swift` (lines 6–18)

- [ ] **Step 1: Add `url` to the `ReelSource` struct**

Open `frontend/Services/ChatService.swift`. Replace the `ReelSource` struct (lines 5–18) with:

```swift
struct ReelSource: Decodable, Identifiable {
    var id: String { reelId }
    let reelId: String
    let creatorHandle: String?
    let thumbnailUrl: String?
    let caption: String?
    let url: String?

    enum CodingKeys: String, CodingKey {
        case reelId = "reel_id"
        case creatorHandle = "creator_handle"
        case thumbnailUrl = "thumbnail_url"
        case caption
        case url
    }
}
```

- [ ] **Step 2: Verify the project builds**

In Xcode, press **⌘B** (Product → Build).

Expected: build succeeds with 0 errors. The `source.url` reference in `ChatReelCard` (ChatView.swift line 374) was the only unresolved symbol — it resolves now.

- [ ] **Step 3: Commit**

```bash
git add frontend/Services/ChatService.swift
git commit -m "feat: add url field to iOS ReelSource for tappable chat cards"
```

---

## Task 4: End-to-end smoke test

No code changes in this task — just verify the full pipeline works.

- [ ] **Step 1: Start the backend locally**

```bash
cd /Users/deeptijain/Desktop/Deepti/Projects/ReelMind/backend
source venv/bin/activate
docker compose up -d          # start Redis
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

- [ ] **Step 2: Confirm the health check passes**

```bash
curl http://localhost:8000/api/v1/health
```

Expected: `{"status": "ok"}` (or similar).

- [ ] **Step 3: Verify `url` appears in a real chat response**

Create a chat session and send a message via the API docs at http://localhost:8000/docs:

1. `POST /api/v1/reels/sessions` with a valid `category_id` from your Supabase `categories` table
2. `POST /api/v1/chat/sessions/{session_id}/messages` with `{"content": "show me something"}`
3. Inspect the response — `sources[N].url` should be a non-null Instagram URL like `https://www.instagram.com/reel/...`

If `sources` is empty, that means the category has no `ready` reels — use a category that has processed reels.

- [ ] **Step 4: Build and run the iOS app**

Open `ReelMind.xcworkspace` in Xcode, run on simulator or device (⌘R). Open a category that has saved reels, open the chat, send a message. Tap a reel card in the AI response — Instagram should open.

- [ ] **Step 5: Stop local backend**

```bash
docker compose down
```
