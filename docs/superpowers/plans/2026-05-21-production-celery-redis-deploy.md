# Production Celery + Redis Deploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy Celery + Redis to production on Render so the full reel ingestion pipeline (Steps 15–22) runs automatically when users share reels from their iPhone.

**Architecture (Option B — Single Service):** FastAPI already runs on Render at `reelmind-8paz.onrender.com`. Both uvicorn and Celery run inside the **same** `reelmind-api` web service using a combined start command. A separate background worker service was rejected because Render has no free tier for background workers ($7/month minimum). Option B works because the embedder uses the Gemini API (no local model in RAM) — peak memory ~200 MB, well under the 512 MB free-tier limit.

**Tech Stack:** Render (single web service running both uvicorn + Celery), Upstash Redis (managed, free-tier, TLS), Firebase Admin SDK, `render.yaml`

---

## Status: What Is Done vs Pending

| Milestone | Status |
|---|---|
| Phase 1 tests verified | ✅ Done |
| `render.yaml` updated (worker block + GEMINI_API_KEY) | ✅ Done |
| `CLAUDE.md` updated (all pipeline steps, correct vector dim) | ✅ Done |
| ngrok URLs replaced with Render URL in iOS files | ✅ Done |
| Upstash Redis created | ✅ Done |
| Firebase key already on Render from prior work | ✅ Done |
| `REDIS_URL` set on `reelmind-api` in Render dashboard | ✅ Done |
| `GEMINI_API_KEY` set on `reelmind-api` in Render dashboard | ✅ Done |
| Render start command updated to Option B | ✅ Done |
| Verify `celery@<hostname> ready.` in logs | ⏳ M4 |
| End-to-end smoke test | ⏳ M5 |
| `git push origin main` | ⏳ Pending |
| Rebuild iOS app in Xcode (⌘R) | ⏳ Pending |

---

## Status Check: Phase 1 Already Done

Before doing anything, verify Phase 1 (Steps 23-24 code gaps) is fully implemented. All of these files were already updated in a previous session:

| File | What was done |
|---|---|
| `backend/api/v1/reels.py` | Auto-create branch: `.ilike` lookup, title-case normalisation, 409 status guard |
| `backend/tests/test_category_endpoint.py` | Mock updated to `.ilike`, 3 auto-create tests added, 422 test removed |
| `frontend/ReelCategoryAPI.swift` | `assignAsync` added (async/await, throws on failure) |
| `frontend/CategoriseReelView.swift` | Supabase direct write removed, `assignAndDismiss` uses `assignAsync`, `assignError` alert added |

---

## File Map

| File | Action | Status |
|---|---|---|
| `render.yaml` | Modified — worker block added + GEMINI_API_KEY on both services | ✅ Done |
| `CLAUDE.md` | Modified — all stale statements fixed | ✅ Done |
| `URL Sharing module/ShareViewController.swift` | Modified — ngrok → Render URL | ✅ Done |
| `frontend/SupabaseManager.swift` | Modified — ngrok → Render URL | ✅ Done |

---

## Task 1: Verify Phase 1 Tests Still Pass ✅

Before touching any infrastructure, confirm the backend tests are green.

**Files:** None modified — read-only verification.

- [x] **Step 1: Run the full backend test suite**

```bash
cd /Users/deeptijain/Desktop/Deepti/Projects/ReelMind/backend && source venv/bin/activate && \
pytest tests/ -v 2>&1 | tail -30
```

---

## Task 2: Update `render.yaml` ✅

The `render.yaml` was updated with two changes:
1. Added `reelmind-celery` worker block (serves as infrastructure-as-code documentation even though Celery actually runs inside the web service — Option B)
2. Added `GEMINI_API_KEY` to both the web service and worker blocks (the embedder calls the Gemini API)
3. Changed `FCM_SERVER_KEY` → `FIREBASE_SERVICE_ACCOUNT_JSON` on the worker block

**Final `render.yaml` state:**

```yaml
services:
  - type: web
    name: reelmind-api
    runtime: python
    region: oregon
    plan: free
    buildCommand: pip install -r backend/requirements.txt
    startCommand: cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT
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
      - key: FCM_SERVER_KEY
        sync: false
      - key: REDIS_URL
        sync: false
      - key: TAVILY_API_KEY
        sync: false
      - key: GEMINI_API_KEY
        sync: false

  - type: worker
    name: reelmind-celery
    runtime: python
    region: oregon
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
      - key: GEMINI_API_KEY
        sync: false
```

> **Note:** The `render.yaml` `startCommand` for `reelmind-api` still shows the uvicorn-only command. The actual start command used in the Render dashboard (Option B, set manually) is different — see Task 4 Step M3 below.

- [x] **Step 1: Edit render.yaml**
- [x] **Step 2: Commit**

---

## Task 3: Update `CLAUDE.md` ✅

`CLAUDE.md` was updated with the following fixes:
1. "What This Project Is" — removed "Steps 17–22 not yet implemented", replaced with "All pipeline steps (Steps 15–22) are implemented."
2. Env vars — `FCM_SERVER_KEY` → `FIREBASE_SERVICE_ACCOUNT_JSON`; added production deployment topology note
3. Database section — updated from `vector(1536)`/`vector(384)` confusion to `vector(768)` migrated via `20260522000001_resize_embeddings_to_768.sql`, model is `gemini-embedding-2`
4. Pipeline section — Steps 17–22 now described with actual implementation details
5. AI stack section — `gemini-embedding-2` (768-dim, Gemini API) replaces sentence-transformers note

- [x] **Step 1–5: All edits and commit done**

---

## Task 4: Replace ngrok URLs with Render URL ✅

Replaced all hardcoded ngrok tunnel URLs with the permanent Render URL `https://reelmind-8paz.onrender.com` in:

| File | Line | Change |
|---|---|---|
| `URL Sharing module/ShareViewController.swift` | ~45 | `K.backendBaseURL = "https://reelmind-8paz.onrender.com"` |
| `frontend/SupabaseManager.swift` | 12 | `AppConfig.backendBaseURL = URL(string: "https://reelmind-8paz.onrender.com")!` |

- [x] **Both files updated**

> **Rebuild iOS app required:** After pushing these changes to GitHub, rebuild the iOS app in Xcode (⌘R) and reinstall on device so the new URL takes effect.

---

## Task 5: Manual Infrastructure Steps (You Do These)

### Step M1 — Create Upstash Redis ✅

Done. Upstash database created, `rediss://` (double-s, TLS) URL obtained.

> **Note on URL format:** The Upstash dashboard shows the URL prefixed with `redis-cli --tls -u` — that is CLI flag syntax. The actual `REDIS_URL` value starts after `-u`, i.e. `rediss://default:xxxx@xxx.upstash.io:6379`. Must use `rediss://` (double-s) — single-s `redis://` will fail because Upstash requires TLS.

### Step M2 — Firebase Service Account JSON ✅

Already set from prior work. The `FIREBASE_SERVICE_ACCOUNT_JSON` (base64-encoded) was set on the `reelmind-api` Render service in a previous session. No action needed.

### Step M3 — Set Env Vars + Update Start Command on Render ✅

All env vars set on `reelmind-api` (the single web service running both uvicorn + Celery):

| Var | Value |
|---|---|
| `REDIS_URL` | `rediss://...` Upstash URL |
| `GEMINI_API_KEY` | Gemini API key |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | base64-encoded Firebase service account JSON |
| `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` | Already set |
| `GROQ_API_KEY` | Already set |

**Start command** set in Render → `reelmind-api` → Settings → Start Command:

```
cd backend && (uvicorn main:app --host 0.0.0.0 --port $PORT &) && celery -A workers.celery_app worker --loglevel=info --concurrency=2
```

> **Why `(uvicorn ... &)` with parens:** Without the subshell, bash `&` sends `cd backend && uvicorn` to background and runs `celery` from the repo root — so `workers` package is not found (`ModuleNotFoundError: No module named 'workers'`). The subshell `(cmd &)` runs uvicorn in background while keeping the `cd backend` working directory in effect for the celery command that follows.
>
> **Why `--concurrency=2`:** Embedder uses the Gemini API (no local model in RAM). Idle ~120 MB, peak ~200 MB, well under 512 MB free-tier limit. Two workers safe.
>
> **Why `reelmind-celery` worker block is NOT used:** Render background workers have no free tier. The `render.yaml` block is kept as infrastructure-as-code documentation but Render was not instructed to create a separate `reelmind-celery` service.

### Step M4 — Verify Deployment ⏳

1. In Render Dashboard → `reelmind-api` → **Logs** tab
2. Wait for build/restart to complete
3. Look for this line in the logs:
   ```
   celery@<hostname> ready.
   ```
   This confirms Celery started and connected to Upstash Redis successfully.

4. Also confirm no Redis connection errors in the logs.

### Step M5 — End-to-End Smoke Test ⏳

1. Rebuild iOS app in Xcode (⌘R) — required for the Render URL change to take effect
2. Open the ReelMind iOS app on iPhone → make sure you're logged in
3. Find any Instagram reel → tap Share → select ReelMind from the share sheet
4. Watch `reelmind-api` logs in Render dashboard — expect:
   ```
   [Step 15] Downloading reel <reel_id>
   [Step 16] Transcribing audio
   [Step 18] Classifying with Llama
   [Step 19] Confidence: 0.85 → status=ready
   [Step 20] Embedding stored
   [Step 22] FCM push sent
   Task process_reel[<uuid>] succeeded
   ```
5. Check the app — the reel should appear with a category assigned
6. A push notification should arrive: "Reel saved!" (or "Help us categorise" with suggested categories if confidence < 0.70)

### Step M6 — Push to GitHub ⏳

```bash
git push origin main
```

This syncs all local commits (render.yaml, CLAUDE.md, Swift URL changes) to the remote.

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Covered by | Status |
|---|---|---|
| Gap 1: Backend auto-create category | Task 1 verifies | ✅ |
| Gap 2: iOS `assignAsync` | Task 1 verifies | ✅ |
| Gap 3: iOS `CategoriseReelView` fix | Task 1 verifies | ✅ |
| Render: Celery running in production | Option B — single service start command | ✅ |
| REDIS_URL on web service | Task 5 M3 | ✅ |
| GEMINI_API_KEY on web service | Task 5 M3 | ✅ |
| FIREBASE_SERVICE_ACCOUNT_JSON | Task 5 M2 — already set | ✅ |
| Upstash Redis (TLS, `rediss://`) | Task 5 M1 | ✅ |
| ngrok URLs replaced | Task 4 | ✅ |
| CLAUDE.md updated | Task 3 | ✅ |
| Deployment verified | Task 5 M4 | ⏳ |
| End-to-end smoke test | Task 5 M5 | ⏳ |
| `git push origin main` | Task 5 M6 | ⏳ |
