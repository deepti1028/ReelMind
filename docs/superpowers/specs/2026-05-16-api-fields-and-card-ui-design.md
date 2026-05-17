# Design: API Field Completeness & Reel Card UI

**Date:** 2026-05-16  
**Scope:** Backend schema fixes + iOS model/query/card UI updates  
**Approach:** Option A — minimal surgical fixes, no architectural changes

---

## Problem

1. `ReelResponse` Pydantic schema is missing `transcript`, `caption`, `hashtags`, `has_audio`, `retry_count`, `updated_at` — the POST endpoint response is incomplete.
2. The duplicate-URL path in `POST /api/v1/reels` selects only `id, status`, discarding all other populated fields.
3. `Reel.swift` is missing the `has_audio: Bool?` column added in migration `20260507000001`.
4. `ReelsService.fetchReels()` does not join the `categories` table, so category names are never available to the UI.
5. `ReelCard` shows nothing useful when a reel is freshly queued (all metadata fields are null).
6. `ReelCard` does not surface `has_audio`, category name, or `updated_at`.

---

## Architecture

No new endpoints. No change to the data flow. The iOS app continues to read reels directly from Supabase (RLS-scoped, anon key). FastAPI is only called by the share extension for `POST /api/v1/reels`.

```
Share Extension → POST /api/v1/reels (FastAPI) → Supabase insert → Celery task
iOS App         → Supabase SDK .select("*, categories(name)") → Reel list
```

---

## Backend Changes

### `backend/schemas/reel.py` — `ReelResponse`

Add all missing columns so the schema matches the full `reels` DB table:

```python
class ReelResponse(BaseModel):
    id: UUID
    url: str
    status: str
    category_id: Optional[UUID] = None
    creator_handle: Optional[str] = None
    thumbnail_url: Optional[str] = None
    transcript: Optional[str] = None
    caption: Optional[str] = None
    hashtags: list[str] = []
    summary: Optional[str] = None
    confidence: Optional[float] = None
    has_audio: Optional[bool] = None
    retry_count: Optional[int] = None
    created_at: datetime
    updated_at: datetime
```

### `backend/api/v1/reels.py` — `create_reel`

Five issues fixed together:

1. **Exception as control flow** — replace `try/except APIError("23505")` with `upsert(ignore_duplicates=True)` and an empty `result.data` check. An expected duplicate is not an exception; `result.data == []` is a clean boolean branch.

2. **Full row on all paths** — `upsert` returns the inserted row directly on fresh insert. The duplicate fallback `SELECT` uses `select("*")` instead of `select("id, status")`.

3. **`url` from DB, not request** — response returns `reel["url"]` (the DB-stored value), not `url_str` (the Pydantic-normalized request string).

4. **Typed response** — endpoint gets `response_model=ReelResponse` so FastAPI validates the output and OpenAPI docs are correct.

5. **Correct HTTP status per case** — 202 only when a Celery task is actually dispatched (fresh insert). Duplicates return 200 OK (no work queued). FastAPI `Response` is injected to set the status conditionally.

```python
@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=ReelResponse)
async def create_reel(
    payload: ReelCreate,
    user_id: str = Depends(get_current_user_id),
    response: Response,
):
    supabase = get_supabase()
    url_str = str(payload.url)

    supabase.table("profiles").upsert(
        {"id": user_id}, on_conflict="id", ignore_duplicates=True
    ).execute()

    result = (
        supabase.table("reels")
        .upsert(
            {"user_id": user_id, "url": url_str, "status": "queued"},
            on_conflict="user_id,url",
            ignore_duplicates=True,
        )
        .execute()
    )

    if result.data:
        reel = result.data[0]
        process_reel.delay(reel["id"])
        # response.status_code stays 202 (default)
    else:
        existing = (
            supabase.table("reels")
            .select("*")
            .eq("user_id", user_id)
            .eq("url", url_str)
            .single()
            .execute()
        )
        reel = existing.data
        response.status_code = status.HTTP_200_OK  # duplicate — nothing queued

    return reel
```

Round-trip count is unchanged (2 for fresh insert, 3 for duplicate) but control flow is semantically correct throughout.

---

## iOS Changes

### `frontend/TempReels/Reel.swift`

Add `hasAudio: Bool?` with `CodingKey` `"has_audio"`.

Add nested `CategoryInfo` struct for decoding the PostgREST join result:

```swift
struct CategoryInfo: Decodable, Hashable {
    let name: String
}
```

Add `categories: CategoryInfo?` property with `CodingKey` `"categories"`. Supabase returns `"categories": null` when `category_id` is null, which decodes cleanly to `nil`.

### `frontend/TempReels/ReelsService.swift`

Change `.select()` to `.select("*, categories(name)")`. PostgREST resolves the FK join automatically. No other changes.

### `frontend/TempReels/ReelsListView.swift` — `ReelCard`

**Minimal fallback (queued/no-metadata state):**  
When `thumbnailUrl`, `creatorHandle`, `caption`, and `hashtags` are all absent, render a compact single-row card: status pill + URL domain (extracted from the URL string) + timestamp. No empty gaps.

**Category chip:**  
When `categories?.name` is non-nil, render a small neutral capsule chip (e.g. "Cooking") below the hashtags row, using the same styling as existing hashtag chips but in grey.

**`has_audio` badge (replaces raw char-count):**  
In the footer row:
- `hasAudio == true` + transcript present → `🎙 transcript`
- `hasAudio == false` → `📄 caption-only`
- `hasAudio == nil` → nothing (not yet processed)

**`updated_at` in footer:**  
Show "updated MMM d, HH:mm" only when `status == "processing"` or `status == "failed"`. Hidden otherwise.

---

## Error Handling

- `CategoryInfo` decodes from a nullable join — no special error handling needed, Swift `Optional` covers it.
- `has_audio` is `Optional<Bool>` — three-state (true / false / nil) maps correctly to the DB column's three states.
- URL domain extraction uses `URL(string:)?.host` — falls back to the raw URL string if parsing fails.
- All new card elements are guarded with `if let` or non-empty checks — no crash paths.

---

## Out of Scope

- Steps 17–22 (classification, embeddings, FCM push) — not touched.
- GET list/detail endpoints on FastAPI — not added (direct Supabase is correct here).
- Pagination or filtering in `fetchReels()` — deferred.
- Production-grade card UI polish — this is a testing UI.
