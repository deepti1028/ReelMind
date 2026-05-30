# Thumbnail Permanent Storage — Design

**Date:** 2026-05-30
**Status:** Approved

## Problem

Instagram CDN URLs (`scontent.cdninstagram.com`) stored in `reels.thumbnail_url` are signed and time-limited — they expire after roughly one week. After expiry, `AsyncImage` in `ThumbnailView` receives a 403 and falls through to the placeholder. The codebase already acknowledges this at `downloader.py:805`: "asset URL expired or revoked (IG CDN URLs are signed+short-lived)".

The thumbnail file **is** downloaded to a local temp path during the pipeline (`DownloadResult.thumbnail_path`) but is never uploaded to permanent storage — it is just cleaned up in the `finally` block.

## Scope

Future reels only. No backfill of existing expired thumbnails.

---

## Architecture

```
Pipeline (tasks.py)
  ├── Step 15:  download_reel() → DownloadResult (thumbnail already on disk at thumbnail_path)
  ├── Step 15b: upload_thumbnail() → permanent Supabase Storage URL  [NEW]
  └── Supabase UPDATE reels SET thumbnail_url = <permanent URL>

iOS ThumbnailView — unchanged, AsyncImage loads whatever URL is in thumbnail_url
```

---

## Components

### 1. Supabase Storage bucket — `thumbnails`

- Public bucket (unauthenticated reads, service-role writes)
- Storage path per file: `{user_id}/{reel_id}.jpg`
- `upsert=True` on upload so re-processing the same reel never 409s

**Migration:** `supabase/migrations/20260530000001_thumbnails_bucket.sql`

```sql
insert into storage.buckets (id, name, public)
values ('thumbnails', 'thumbnails', true)
on conflict (id) do nothing;

create policy "Public thumbnail read"
on storage.objects for select
using (bucket_id = 'thumbnails');
```

---

### 2. `backend/services/storage.py` (new file, ~60 lines)

Single public function:

```
upload_thumbnail(
    reel_id: str,
    user_id: str,
    thumbnail_path: str,
    fallback_url: str | None,
) -> str | None
```

**Behaviour:**
- Uploads the local `.jpg` file to `thumbnails/{user_id}/{reel_id}.jpg`
- On success: calls `.get_public_url()` and returns the permanent URL
- On failure: retries up to 3 times with exponential backoff (2s → 4s → 8s)
- If all retries exhausted: logs a warning and returns `fallback_url` (the Instagram CDN URL)

**Logs emitted:**
```
storage | uploading thumbnail | reel_id=... | path=...
storage | upload success | reel_id=... | public_url=...
storage | upload attempt failed (1/3) | reel_id=... | error=... | retrying in 2s
storage | upload attempt failed (2/3) | reel_id=... | error=... | retrying in 4s
storage | upload attempt failed (3/3) | reel_id=... | error=... | falling back to CDN URL
storage | all retries exhausted | reel_id=... | using fallback CDN url
```

---

### 3. `backend/workers/tasks.py` changes (small)

**Import:** add `upload_thumbnail` from `services.storage`.

**New Step 15b block** — inserted after download succeeds, before the Supabase `UPDATE`:

```python
# Step 15b — upload thumbnail to permanent storage
permanent_thumb_url = meta.thumbnail_url  # Instagram CDN URL as default fallback
if download_result.thumbnail_path:
    log.info("step 15b | uploading thumbnail | reel_id=%s", reel_id)
    permanent_thumb_url = upload_thumbnail(
        reel_id=reel_id,
        user_id=user_id,
        thumbnail_path=download_result.thumbnail_path,
        fallback_url=meta.thumbnail_url,
    )
    log.info(
        "step 15b | thumbnail url resolved | reel_id=%s | url=%s",
        reel_id, permanent_thumb_url,
    )
else:
    log.warning("step 15b | no thumbnail_path, skipping upload | reel_id=%s", reel_id)

# existing UPDATE uses permanent_thumb_url instead of meta.thumbnail_url
```

The `finally` cleanup block is unchanged — temp files are still cleaned up after the upload completes.

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| Upload succeeds on first try | Permanent Supabase Storage URL stored |
| Upload fails, retries succeed | Permanent URL stored after retry |
| All 3 retries exhausted | Instagram CDN URL stored (works for ~1 week) |
| `thumbnail_path` is None (no thumbnail downloaded) | `null` stored in `thumbnail_url` |

---

## File Change Summary

| File | Change |
|---|---|
| `supabase/migrations/20260530000001_thumbnails_bucket.sql` | New — bucket + RLS policy |
| `backend/services/storage.py` | New — ~60 lines |
| `backend/workers/tasks.py` | Modified — import + ~15 lines for Step 15b |

No iOS changes required.
