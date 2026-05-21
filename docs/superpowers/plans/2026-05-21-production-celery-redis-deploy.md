# Production Celery + Redis Deploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy Celery + Redis to production on Render so the full reel ingestion pipeline (Steps 15-22) runs automatically when users share reels from their iPhone.

**Architecture:** FastAPI already runs on Render at `reelmind-8paz.onrender.com`. We add a second Render service (a background worker running Celery) connected to Upstash Redis as the task broker. Firebase Admin SDK is already implemented — it just needs the `FIREBASE_SERVICE_ACCOUNT_JSON` env var set on the worker to enable FCM pushes.

**Tech Stack:** Render (web + worker services), Upstash Redis (managed, free-tier, TLS), Firebase Admin SDK, `render.yaml`

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

| File | Action | Responsibility |
|---|---|---|
| `render.yaml` | Modify | Add `reelmind-celery` worker service |
| `CLAUDE.md` | Modify | Fix stale statements about pipeline steps and vector dimension |

---

## Task 1: Verify Phase 1 Tests Still Pass

Before touching any infrastructure, confirm the backend tests are green. This catches any regression before we build on top.

**Files:** None modified — read-only verification.

- [ ] **Step 1: Run the full backend test suite**

```bash
cd /Users/deeptijain/Desktop/Deepti/Projects/ReelMind/backend && source venv/bin/activate && \
pytest tests/ -v 2>&1 | tail -30
```

Expected output (all tests pass):
```
tests/test_category_endpoint.py::test_assign_category_marks_ready PASSED
tests/test_category_endpoint.py::test_null_category_name_marks_uncategorised PASSED
tests/test_category_endpoint.py::test_already_resolved_returns_409 PASSED
tests/test_category_endpoint.py::test_reel_not_found_returns_404 PASSED
tests/test_category_endpoint.py::test_patch_auto_creates_category_when_not_found PASSED
tests/test_category_endpoint.py::test_patch_case_insensitive_reuses_existing_category PASSED
tests/test_category_endpoint.py::test_patch_title_cases_new_category_name PASSED
...
N passed
```

If any test fails, stop and fix it before continuing.

---

## Task 2: Add Celery Worker Service to `render.yaml`

Render reads `render.yaml` from the repo root to know what services to deploy. We add a `worker` type service that runs Celery. The `worker` type never receives HTTP traffic and never sleeps — it stays alive 24/7 on the free tier (unlike the web service which can spin down).

**Files:**
- Modify: `render.yaml`

- [ ] **Step 1: Open `render.yaml` and append the Celery worker service**

The current file ends after the `reelmind-api` web service. Add the following block at the end of the file (after the last line):

```yaml
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
```

**Why `concurrency=1`:** The sentence-transformers embedding model loads ~300 MB into RAM. Render free tier allows up to 512 MB. Two workers would exceed the limit and get OOM-killed.

**Why `sync: false`:** These env vars contain secrets and must be set manually in the Render dashboard — they are not committed to the repo.

After the edit, the full `render.yaml` should look like this:

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
```

- [ ] **Step 2: Commit**

```bash
cd /Users/deeptijain/Desktop/Deepti/Projects/ReelMind && \
git add render.yaml && \
git commit -m "feat: add reelmind-celery worker service to render.yaml"
```

---

## Task 3: Update `CLAUDE.md` to Reflect Current State

`CLAUDE.md` has two stale statements that will mislead future work:
1. "Steps 17–22 not yet implemented" — they ARE implemented (classification, confidence routing, embeddings, FCM push all exist in `workers/tasks.py`)
2. "must be migrated to `vector(384)`" — already done via `supabase/migrations/20260518000001_resize_reel_chunks_embedding.sql`

We also need to add production deployment context and the `FIREBASE_SERVICE_ACCOUNT_JSON` env var.

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Fix the "What This Project Is" section**

Find this line in `CLAUDE.md`:

```
ReelMind is an iOS app that lets users save Instagram Reels via the iOS Share Sheet. When a user shares a reel URL, a background pipeline downloads it, transcribes its audio (Groq Whisper), classifies it into a category (Groq Llama 3.3 70B), and generates embeddings (sentence-transformers locally in Celery). Steps 17–22 of the pipeline (classification, embeddings, FCM push) are not yet implemented.
```

Replace with:

```
ReelMind is an iOS app that lets users save Instagram Reels via the iOS Share Sheet. When a user shares a reel URL, a background pipeline downloads it, transcribes its audio (Groq Whisper), classifies it into a category (Groq Llama 3.3 70B), generates embeddings (sentence-transformers locally in Celery), and sends an FCM push notification. All pipeline steps (Steps 15–22) are implemented.
```

- [ ] **Step 2: Fix the env vars section — add `FIREBASE_SERVICE_ACCOUNT_JSON`, remove stale FCM_SERVER_KEY note**

Find this line in the `### Environment variables` section:

```
Copy `backend/.env.example` → `backend/.env`. Required vars: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`. Optional: `GROQ_API_KEY`, `REDIS_URL` (defaults to `redis://localhost:6379`), `FCM_SERVER_KEY`, `TAVILY_API_KEY`.
```

Replace with:

```
Copy `backend/.env.example` → `backend/.env`. Required vars: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`. Optional: `GROQ_API_KEY`, `REDIS_URL` (defaults to `redis://localhost:6379`), `FIREBASE_SERVICE_ACCOUNT_JSON` (base64-encoded Firebase service account JSON — enables FCM push; if unset, push is silently skipped), `TAVILY_API_KEY`.

Production deployment: FastAPI runs on Render (`reelmind-api` web service). Celery runs on Render (`reelmind-celery` worker service). Redis is managed by Upstash (free tier, TLS URL). Set `REDIS_URL` on both Render services. Set `FIREBASE_SERVICE_ACCOUNT_JSON` only on the Celery worker — FastAPI never sends pushes directly.
```

- [ ] **Step 3: Fix the stale database note about vector dimension**

Find this paragraph in `### Database / Supabase`:

```
The `reel_chunks.embedding` column is currently `vector(1536)` but **must be migrated to `vector(384)`** before implementing Step 20 (embeddings), since `sentence-transformers/all-MiniLM-L6-v2` produces 384-dimensional vectors.
```

Replace with:

```
The `reel_chunks.embedding` column is `vector(384)` (migrated via `supabase/migrations/20260518000001_resize_reel_chunks_embedding.sql`). The embedding model is `BAAI/bge-small-en-v1.5` (384-dim).
```

- [ ] **Step 4: Fix the stale pipeline description**

Find this in `### Backend ingestion pipeline`:

```
- **Steps 17–22**: not yet implemented (classification, caption extraction, embeddings, confidence routing, FCM push).
```

Replace with:

```
- **Step 17** (`workers/tasks.py`): Build classification signal from transcript, caption, and hashtags.
- **Step 18** (`services/classifier.py`): Classify via Groq Llama 3.3 70B → category name + confidence score.
- **Step 19** (`workers/tasks.py`): Confidence routing — ≥0.70 → `status=ready`; <0.70 → `status=pending_category` with suggested categories.
- **Step 20** (`services/embedder.py`): Embed transcript+caption+hashtags as 384-dim vector → store in `reel_chunks`.
- **Step 22** (`services/notifier.py`): FCM push via Firebase Admin SDK. `ready` path: "Reel saved!". `pending_category` path: push with action buttons for suggested categories. Requires `FIREBASE_SERVICE_ACCOUNT_JSON` env var; silently skips if unset.
```

- [ ] **Step 5: Commit**

```bash
cd /Users/deeptijain/Desktop/Deepti/Projects/ReelMind && \
git add CLAUDE.md && \
git commit -m "docs: update CLAUDE.md — all pipeline steps implemented, fix stale statements"
```

---

## Task 4: Manual Infrastructure Steps (You Do These)

These steps cannot be done by Claude — they require browser access and Render dashboard credentials. Do them **after** the code changes above are pushed to `main`.

### Step M1 — Create Upstash Redis

1. Go to [upstash.com](https://upstash.com) → click **Sign Up** (free, no credit card required)
2. After signing in → click **Create Database**
3. Name: `reelmind` → Region: **US-West-1** (Oregon — closest to Render's Oregon region → lower latency) → Type: **Regional** → click **Create**
4. On the database detail page → copy the **Redis URL** — it starts with `rediss://default:xxxx@xxx.upstash.io:6379`
   - Save this string — you'll paste it as `REDIS_URL` on both Render services

**Why Upstash, not another provider:** Free tier includes 10,000 commands/day and 256 MB — enough for ~700-1,000 reels/day. No credit card required. TLS connection is included.

### Step M2 — Get Firebase Service Account JSON

1. Go to [Firebase Console](https://console.firebase.google.com) → select your ReelMind project
2. Click the gear icon (⚙) → **Project Settings** → **Service Accounts** tab
3. Click **Generate new private key** → **Generate key** → a `.json` file downloads
4. In your Mac terminal, run:
   ```bash
   base64 -i /path/to/downloaded-serviceAccount.json | tr -d '\n'
   ```
   Replace `/path/to/downloaded-serviceAccount.json` with the actual path (e.g. `~/Downloads/reelmind-firebase-adminsdk-xxxx.json`)
5. Copy the entire output string — this is `FIREBASE_SERVICE_ACCOUNT_JSON`

**Why base64?** Render env vars are single-line strings. The JSON file contains newlines that would break parsing. Base64 encodes it to a safe single-line string. The backend's `notifier.py` already handles decoding it back.

### Step M3 — Set Env Vars on Render

Push the code changes first (`git push origin main`), then:

**On `reelmind-api` (existing web service):**
1. [Render Dashboard](https://dashboard.render.com) → select `reelmind-api` → **Environment** tab
2. Verify `REDIS_URL` is set (it was already in `render.yaml` as `sync: false` — you may have set it already). If not, add it now with the Upstash URL from Step M1.

**On `reelmind-celery` (new worker — Render creates it automatically when render.yaml is pushed):**
1. In Render Dashboard → select `reelmind-celery` → **Environment** tab
2. Add ALL of the following variables:
   - `REDIS_URL` → paste the Upstash `rediss://...` URL from Step M1
   - `FIREBASE_SERVICE_ACCOUNT_JSON` → paste the base64 string from Step M2
   - `SUPABASE_URL` → same value as on `reelmind-api`
   - `SUPABASE_ANON_KEY` → same value as on `reelmind-api`
   - `SUPABASE_SERVICE_ROLE_KEY` → same value as on `reelmind-api`
   - `GROQ_API_KEY` → same value as on `reelmind-api`

**Important:** After setting env vars, Render auto-redeploys the service.

### Step M4 — Verify Deployment

1. In Render Dashboard → `reelmind-celery` → **Logs** tab
2. Wait ~2-3 minutes for the build to complete (pip install + model download)
3. Look for this line in the logs:
   ```
   celery@<hostname> ready.
   ```
   If you see it → Celery is running and connected to Redis successfully.

4. In Render Dashboard → `reelmind-api` → **Logs** tab
5. Look for Redis connection errors. If none → the web service is connecting to Upstash correctly.

### Step M5 — End-to-End Smoke Test

1. Open the ReelMind iOS app on your iPhone → make sure you're logged in
2. Find any Instagram reel → tap Share → select ReelMind from the share sheet
3. Watch `reelmind-celery` logs in the Render dashboard — you should see:
   ```
   [Step 15] Downloading reel <reel_id>
   [Step 16] Transcribing audio
   [Step 18] Classifying with Llama
   [Step 19] Confidence: 0.85 → status=ready
   [Step 20] Embedding stored
   [Step 22] FCM push sent
   Task process_reel[<uuid>] succeeded
   ```
4. Check the app — the reel should appear with a category assigned
5. A push notification should arrive on your iPhone saying "Reel saved!" (or if confidence < 0.70, a "Help us categorise" notification with suggested categories)

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Covered by |
|---|---|
| Gap 1: Backend auto-create category | Already implemented — Task 1 verifies |
| Gap 2: iOS `assignAsync` | Already implemented — Task 1 verifies (Xcode build) |
| Gap 3: iOS `CategoriseReelView` fix | Already implemented — Task 1 verifies |
| Render worker service in render.yaml | Task 2 |
| REDIS_URL on web service | Already in render.yaml |
| FIREBASE_SERVICE_ACCOUNT_JSON on worker | Task 4 (M3) |
| Upstash Redis setup | Task 4 (M1) |
| Render env vars | Task 4 (M3) |
| Deploy and verify | Task 4 (M4, M5) |
| CLAUDE.md updated | Task 3 |

**Placeholder scan:** No TBDs or incomplete sections. All code blocks are complete.

**Type consistency:** No new types introduced — only configuration and documentation changes in this plan.
