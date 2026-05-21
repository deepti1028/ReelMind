# Production Deployment: Steps 23-24 + Celery + Redis + FCM

**Date:** 2026-05-21
**Status:** Approved, pending implementation
**Goal:** Make the full reel ingestion pipeline work end-to-end in production. This means two things done in order: (1) close the remaining code gaps in the category-assignment flow (Steps 23-24), then (2) deploy Celery + Redis + FCM to Render so the pipeline actually runs on real user submissions.

---

## Background

FastAPI is already deployed on Render at `https://reelmind-8paz.onrender.com`. When a user shares a reel, the iOS app POSTs to this server, which inserts a DB row and dispatches a Celery task. However nothing actually processes that task because:

- No Celery worker is deployed on Render
- No Redis is configured on Render (Celery has no broker)
- `FIREBASE_SERVICE_ACCOUNT_JSON` is not set on Render (FCM push silently disabled)

Additionally, the pipeline's `pending_category` branch — triggered when Llama classifies with low confidence — leads to a broken user flow because Steps 23-24 have known code gaps:

- Backend `PATCH /reels/{id}/category` returns 422 for unknown category names instead of auto-creating them
- `CategoriseReelView` writes directly to Supabase (bypasses backend, missing `user_id`)
- `ReelCategoryAPI.assignAsync` (async/await wrapper with error handling) does not exist yet

Steps 23-24 must be closed first so that when Celery runs in production and fires a `pending_category` push, the user can actually respond to it correctly.

---

## Architecture (after all changes)

```
iPhone
  └── POST /api/v1/reels
          │
          ▼
  Render Web Service (FastAPI)               ← already deployed
          │ process_reel.delay(reel_id)
          ▼
  Upstash Redis (free tier)                  ← new, external
          │
          ▼
  Render Background Worker (Celery)          ← new Render service
          ├── Step 15: Download audio + metadata
          ├── Step 16: Transcribe (Groq Whisper)
          ├── Step 17: Build classification signal
          ├── Step 18: Classify (Groq Llama 3.3 70B)
          ├── Step 19: Confidence routing
          │     ├── confidence ≥ 0.70 → status=ready → FCM push "Reel saved!"
          │     └── confidence < 0.70 → status=pending_category → FCM push with suggestions
          ├── Step 20: Embed content + store reel_chunk (384-dim)
          └── Step 22: FCM push via Firebase Admin SDK

  pending_category push → user taps notification
          ├── Entry A: inline action buttons → ReelCategoryAPI.assign → PATCH /reels/{id}/category
          └── Entry B: CategoriseReelView sheet → ReelCategoryAPI.assignAsync → PATCH /reels/{id}/category
                  Backend: normalise name → case-insensitive lookup → auto-create if missing → status=ready
```

---

## Phase 1: Steps 23-24 Code Gaps (prerequisite — code only, no infrastructure)

These three gaps must be closed before deploying Celery to production.

### Gap 1 — Backend: auto-create category on `PATCH /reels/{id}/category`

**File:** `backend/api/v1/reels.py`

Currently the endpoint does an exact `.eq("name", payload.category_name)` lookup and returns 422 if the name isn't found. Change to:

1. Normalise the name: strip whitespace, title-case (`"travel vlogs"` → `"Travel Vlogs"`)
2. Case-insensitive lookup: `.ilike("name", normalised_name).or_(f"user_id.eq.{user_id},user_id.is.null")`
3. If found → use existing `category_id`, `created=False`
4. If not found → insert new row `{user_id, name: normalised_name, is_default: False}` → use new `category_id`, `created=True`
5. Update reel: `status=ready`, `confidence=1.0`, `suggested_categories=[]`
6. Send FCM push: "Added to {normalised_name}"
7. Return `{reel_id, status: "ready", category: normalised_name, created: bool}`
8. Status guard: return `409 Conflict` if `reel.status != "pending_category"` (prevents double-assignment)

**Tests:** `backend/tests/test_category_endpoint.py`
- Update `_make_supabase_patch_mock`: change category lookup chain from `.eq` to `.ilike`
- Delete `test_unknown_category_name_returns_422` (behaviour changed)
- Add `test_patch_auto_creates_category_when_not_found`
- Add `test_patch_case_insensitive_reuses_existing_category`
- Add `test_patch_title_cases_new_category_name`

The full test code and mock helper are already written in `docs/superpowers/plans/2026-05-18-steps-23-24-category-assignment.md` — use them verbatim.

### Gap 2 — iOS: `ReelCategoryAPI.assignAsync`

**File:** `frontend/ReelCategoryAPI.swift`

Add `assignAsync(reelId:categoryName:)` — an async/await version of the existing fire-and-forget `assign()`. Throws `URLError(.userAuthenticationRequired)` if no auth token, `URLError(.badServerResponse)` on non-2xx. Used by `CategoriseReelView` so the sheet can show an error alert on failure. The existing `assign()` is kept unchanged (still used by notification action handler).

### Gap 3 — iOS: Fix `CategoriseReelView`

**File:** `frontend/CategoriseReelView.swift`

Three changes:
1. Add `@State private var assignError: Bool = false`
2. Replace `createCategoryAndAssign()` — remove the direct Supabase `insert` Task entirely; just call `assignAndDismiss(categoryName: trimmed)` (backend now handles creation)
3. Replace `assignAndDismiss()` — change from fire-and-forget `ReelCategoryAPI.assign` to a `Task { try await ReelCategoryAPI.assignAsync(...) }` that sets `assignError = true` on catch
4. Add `.alert("Couldn't save", isPresented: $assignError)` to the NavigationView

Full implementation code is in `docs/superpowers/plans/2026-05-18-steps-23-24-category-assignment.md`.

---

## Phase 2: Infrastructure (after Phase 1 is merged)

### Upstash Redis (free tier)
- Broker for Celery task queue
- Free tier: 10,000 commands/day, 256MB, no credit card required
- URL format: `rediss://default:xxxx@xxx.upstash.io:6379` (TLS)
- Each reel uses ~10-15 Redis commands → supports ~700-1,000 reels/day free

### Render Background Worker (new)
- Type: `worker` (Render never routes HTTP to it, no sleep behaviour)
- Plan: free
- Command: `celery -A workers.celery_app worker --loglevel=info --concurrency=1`
- `concurrency=1`: keeps memory within free tier limits (sentence-transformers model loads ~300MB)
- Defined in `render.yaml` alongside the existing web service

### Firebase Admin SDK (FCM)
- Already implemented in `services/notifier.py`
- Needs `FIREBASE_SERVICE_ACCOUNT_JSON`: base64-encoded Firebase service account JSON
- Set only on the Celery worker service (FastAPI never sends pushes directly)

---

## Changes Required

### Manual steps (done by you)

**Step M1 — Create Upstash Redis** (before code is deployed)
1. Go to [upstash.com](https://upstash.com) → sign up (free, no credit card)
2. Create Redis database → region: `us-west-1` (closest to Render Oregon)
3. Copy the `REDIS_URL` connection string (starts with `rediss://`)

**Step M2 — Get Firebase service account JSON** (before code is deployed)
1. [Firebase Console](https://console.firebase.google.com) → your project → Project Settings → Service Accounts
2. Generate new private key → download JSON file
3. In terminal: `base64 -i /path/to/serviceAccount.json | tr -d '\n'`
4. Copy the output (this is `FIREBASE_SERVICE_ACCOUNT_JSON`)

**Step M3 — Set env vars on Render** (after Steps M1 and M2)

On **reelmind-api** (existing web service) — add:
- `REDIS_URL` → Upstash URL from Step M1

On **reelmind-celery** (new worker service, created automatically when render.yaml is pushed) — add:
- `REDIS_URL` → same Upstash URL
- `FIREBASE_SERVICE_ACCOUNT_JSON` → base64 string from Step M2
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, `GROQ_API_KEY` → same values as reelmind-api

**Step M4 — Deploy and verify**
1. After code changes are pushed, Render auto-deploys both services
2. In Render dashboard → reelmind-celery logs → confirm `celery@xxx ready`
3. In Render dashboard → reelmind-api logs → confirm no Redis connection errors

**Step M5 — Smoke test**
1. Share a real Instagram reel from iPhone
2. Watch reelmind-celery logs — should see Steps 15-22 running sequentially
3. Check the reel appears in the app with a category assigned
4. Confirm push notification arrives on device

### Code changes (done by Claude)

**Step C1 — Close Steps 23-24 gaps** (Phase 1)
- `backend/api/v1/reels.py`: add auto-create branch (Gap 1)
- `backend/tests/test_category_endpoint.py`: update mocks, delete 422 test, add 3 new tests (Gap 1)
- `frontend/ReelCategoryAPI.swift`: add `assignAsync` (Gap 2)
- `frontend/CategoriseReelView.swift`: fix `createCategoryAndAssign`, upgrade `assignAndDismiss`, add error alert (Gap 3)

**Step C2 — Add Celery worker to render.yaml** (Phase 2)

```yaml
- type: worker
  name: reelmind-celery
  runtime: python
  plan: free
  buildCommand: pip install -r backend/requirements.txt
  startCommand: cd backend && celery -A workers.celery_app worker --loglevel=info --concurrency=1
  envVars:
    - key: ENVIRONMENT
      value: production
    - key: SUPABASE_URL
      sync: false
    - key: SUPABASE_ANON_KEY
      sync: false
    - key: SUPABASE_SERVICE_ROLE_KEY
      sync: false
    - key: GROQ_API_KEY
      sync: false
    - key: REDIS_URL
      sync: false
    - key: FIREBASE_SERVICE_ACCOUNT_JSON
      sync: false
```

**Step C3 — Add REDIS_URL to reelmind-api in render.yaml**

The FastAPI service needs `REDIS_URL` to dispatch tasks to Upstash:
```yaml
- key: REDIS_URL
  sync: false
```

**Step C4 — Update CLAUDE.md**
- Correct "Steps 17–22 not yet implemented" — all steps are implemented
- Document production deployment setup (Upstash Redis, Render worker service)
- Update environment variables list to include `FIREBASE_SERVICE_ACCOUNT_JSON`

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| Redis unreachable (FastAPI side) | `process_reel.delay()` raises — reel stays `queued`. FastAPI still serves HTTP. |
| Celery worker crash | Render auto-restarts. In-flight task lost; reel stays `processing`. Celery retries (max 3, 60s backoff). |
| FCM push failure | `send_push_notification` never raises. Pipeline completes; reel status is correct regardless. |
| `pending_category` push, user offline | Fire-and-forget assign path silently fails. Reel stays `pending_category`. User can re-open sheet via app. |
| `pending_category` push, sheet path, network failure | `assignAsync` throws → `assignError = true` → alert shown. Sheet stays open for retry. |
| Upstash rate limit (10K commands/day) | Unlikely for a small app. ~700-1000 reels/day free. Monitor in Upstash dashboard if needed. |
| Double-assignment (user taps two buttons) | Backend returns `409 Conflict` on second request. iOS ignores. |

---

## Testing Checklist

**Phase 1 (Steps 23-24)**
- [ ] All existing `test_category_endpoint.py` tests pass
- [ ] 3 new auto-create tests pass
- [ ] Xcode build succeeds (no compiler errors)
- [ ] Type new category in `CategoriseReelView` → reel categorised, new category appears, no Supabase direct write
- [ ] Type existing category in different case → no duplicate created
- [ ] Kill network, tap category in sheet → "Couldn't save" alert appears

**Phase 2 (infrastructure)**
- [ ] `REDIS_URL` set on both Render services
- [ ] `FIREBASE_SERVICE_ACCOUNT_JSON` set on reelmind-celery
- [ ] Render shows reelmind-celery as deployed and running
- [ ] Celery logs show `celery@xxx ready`
- [ ] Share a reel → Celery logs show all pipeline steps completing
- [ ] Reel appears in app with category assigned
- [ ] Push notification received on device
