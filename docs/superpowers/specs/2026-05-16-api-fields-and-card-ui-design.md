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

- Duplicate path: change `.select("id, status")` → `.select("*")` so all populated fields are returned.
- Response: annotate the endpoint with `response_model=ReelResponse` and return the full reel dict. The `url` field in the response comes from the DB row (not the `url_str` local variable) to stay consistent.

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
