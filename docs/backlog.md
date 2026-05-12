# ReelMind Phase 1 — Backlog

Deferred features and enhancements for future phases.

## Database & Security

### Advanced RLS Policies (Phase 2)
- Implement granular row-level access control beyond basic user isolation
- Support for future sharing features (user-to-user reel sharing)
- Category-level permissions if needed
- Consider: public library profiles, collaborative collections

**Current State:** Basic RLS only — users see/modify only their own data + service role bypass for backend processing.

## Features

### Public & Sharing (Phase 2+)
- Allow users to make categories/reels public
- Share reels with other users
- Collaborative collections
- Public profiles

**Current State:** Everything private by default. No sharing mechanism.

## Infrastructure

### Migrate Redis to Cloud Before Production Deployment
- Currently running Redis locally via Docker for development
- **Before final deployment**, must point to a managed cloud Redis instance
- Options to evaluate: Upstash Redis, Redis Cloud (Redis Labs), Railway Redis add-on, AWS ElastiCache
- Update `REDIS_URL` env var in production environment to cloud endpoint
- Ensure TLS/auth is configured for cloud Redis
- Verify Celery workers can connect to cloud Redis from production server

**Current State:** Docker Redis on localhost:6379 for development.

## IOS targeted app versions

### Current IOS app is build for 16+
- Make sure to check weather this means that users with older iphone versions wouldn't be able to use your app?



## Save Reels by Users

### Few decesions that needs to be re iterated
- We should save the reels that are in the uncategorised state by our llm/backend. This can be used for adding new default reels or to understand the parts of our LLM that still needs to get trained

## App Group Queue — Offline Fallback Drain

### Drain the pending URL queue on main app launch (Phase 2)
- The Share Extension writes every reel URL to `UserDefaults(suiteName: "group.com.deepti.ReelMind")` under key `pendingReelURLs` **before** it fires the backend POST. This queue is a reliability net: if the POST fails (no internet, server down, 401), the URL is not lost — it sits in the shared container.
- On each main app launch, the app should read this queue, call `GET /api/v1/reels?status=queued,failed` for the user, compare, and re-POST any URLs that are in the local queue but missing from the backend (or in `failed` state).
- After a successful re-POST, remove the URL from the queue.
- **Current state:** Queue is write-only. The drain logic does not exist yet. If a POST fails silently, the URL is orphaned in the queue and never retried.
- **Why deferred:** The main app launch flow and auth persistence haven't been built yet. This depends on the login/token-storage work (Phase 2).

## Share Extension UX

### Show error to user when no URL is found (Phase 2)
- Currently if the Share Extension receives something that isn't a valid Instagram reel URL (e.g. a photo, a story, a profile link), we silently do nothing
- User should see a clear error message: "This doesn't look like an Instagram reel. Only public reel links are supported."
- Helps user understand why nothing happened instead of thinking the app is broken

### Show ReelMind in share sheet only when sharing from Instagram (Phase 2)
- Currently the app appears in the share sheet from any app as long as a URL is being shared
- Should only be visible when the user is sharing from Instagram specifically
- Requires updating `NSExtensionActivationRule` in the Share Extension's `Info.plist` to filter by source app bundle ID (`com.burbn.instagram`)
- This is an undocumented/complex predicate rule — needs research and testing to confirm it works reliably across iOS versions

### Remove "Testing" default category before public launch
- A "Testing" default category was added in migration `20260507000002_seed_testing_category.sql` for development convenience (so we can dump test reels into a known place during Phase 2 verification).
- Before public launch, either:
  - (a) drop it via a new migration, or
  - (b) add `is_internal` boolean to `categories` and hide internal categories from regular users
- Tracking here so we don't accidentally ship a "Testing" category to real users.

### Make ReelMind appear in share sheet by default on first install
- When the app is freshly installed, the user currently has to manually scroll into "More" in the share sheet and toggle ReelMind on / pin it to the top
- We want it visible (and ideally near the top) the first time a user opens the share sheet, no manual toggling needed
- Investigate: iOS doesn't directly expose ordering control, but Apple's heuristics weight extensions higher when (a) the app has been launched recently, (b) the user has used the extension before, (c) the activation rule is tightly scoped. We may be able to nudge first-impression visibility by ensuring the main app launches once after install (onboarding flow) before the user tries to share.
- Worth researching whether `LSApplicationQueriesSchemes` or `NSExtensionActivationRule` tightening helps

## Reel Asset Persistence

### Persist downloaded video to Supabase Storage (Phase 2+)
- `backend/services/downloader.py` already includes video-download support gated behind `download_video=False`. We currently skip video download in the main pipeline because we only need the audio for Whisper.
- When we want video playback inside the app (offline access, in-feed playback), wire `download_video=True` in `process_reel`, upload the resulting mp4 to Supabase Storage, and add a `video_url` column on `reels` pointing at the storage object.
- Same flow for thumbnails — currently we download them to `/tmp` and store the original Instagram CDN URL in `reels.thumbnail_url`. IG CDN URLs expire; mirroring to Supabase Storage and rewriting `thumbnail_url` on completion is the durable fix.

### Replace dev-only rich reel card with the final design (Phase 2+)
- [`frontend/TempReels/ReelsListView.swift`](../frontend/TempReels/ReelsListView.swift) currently renders thumbnail + creator + status pill + caption + hashtag chips + transcript-char-count footer. This is intentionally informational — its job is to make the backend pipeline observable end-to-end while we're building Steps 15-22 (you can see at a glance whether a reel is `queued`/`processing`/`ready`/`failed`, whether transcription ran, etc.).
- Before public release, swap this for the final UX (likely simpler, possibly category-grouped, no status pill or transcript count visible to end users).
- The rich-card view code can be deleted; the data fields it reads (`thumbnailUrl`, `creatorHandle`, `caption`, `hashtags`, `transcript`, `status`) will continue to exist on the `Reel` model.

### Persist richer reel metadata (Phase 2+)
- The downloader returns a fully populated `ReelMetadata` dataclass (likes, comments, view count, music title/artist, post timestamp, original dimensions, verified-author flag, sharing-friction flag, etc.). Today we only persist `caption`, `hashtags`, `creator_handle`, `thumbnail_url`, and `has_audio`.
- When product needs surface (e.g. "show like count on the card", "filter by music", "sort by post date"), add columns and persist from the dataclass — no second scrape required.

---

*Last updated: 2026-05-09*
