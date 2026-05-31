# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- ALWAYS read graphify-out/GRAPH_REPORT.md before reading any source files, running grep/glob searches, or answering codebase questions. The graph is your primary map of the codebase.
- IF graphify-out/wiki/index.md EXISTS, navigate it instead of reading raw files
- For cross-module "how does X relate to Y" questions, prefer `graphify query "<question>"`, `graphify path "<A>" "<B>"`, or `graphify explain "<concept>"` over grep — these traverse the graph's EXTRACTED + INFERRED edges instead of scanning files
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

---

## What This Project Is

ReelMind is an iOS app that lets users save Instagram Reels via the iOS Share Sheet. When a user shares a reel URL, a background pipeline downloads it, transcribes its audio (Groq `whisper-large-v3-turbo`), classifies it into a category (Google Gemini `gemini-3.1-flash-lite`), generates embeddings (Gemini `gemini-embedding-2` via API), and sends an FCM push notification. All pipeline steps (Steps 15–22) are implemented.

---

## Backend Commands

All backend commands run from `backend/` with the virtualenv active:

```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt        # first time or after dep changes

# Start Redis (required for Celery)
docker compose up -d

# Start FastAPI (port 8000)
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Start Celery worker (separate terminal, venv active)
celery -A workers.celery_app worker --loglevel=info --without-gossip --without-mingle

# Smoke test Celery
python -c "from workers.tasks import ping; print(ping.delay().get(timeout=5))"

# Test the downloader in isolation
python -m services.downloader <reel_url> [reel_id]

# Stop Redis
docker compose down
```

API docs: http://localhost:8000/docs  
Health check: http://localhost:8000/api/v1/health

### Environment variables

Copy `backend/.env.example` → `backend/.env`. Required vars: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`. Optional: `GROQ_API_KEY`, `REDIS_URL` (defaults to `redis://localhost:6379`), `FIREBASE_SERVICE_ACCOUNT_JSON` (base64-encoded Firebase service account JSON — enables FCM push; if unset, push is silently skipped), `TAVILY_API_KEY`.

Production deployment: A **single Render web service** (`ReelMind`) runs both FastAPI and Celery in one process via the start command:
`cd backend && (uvicorn main:app --host 0.0.0.0 --port $PORT &) && celery -A workers.celery_app worker --loglevel=info --concurrency=2 --without-gossip --without-mingle`
Build command: `pip install -r backend/requirements.txt`. Redis is managed by Upstash (free tier, TLS URL). `render.yaml` exists in the repo but is **not used** — the service was created manually in the Render dashboard and all settings are configured there.

### Database / Supabase

Migrations live in `supabase/migrations/`. Apply with:

```bash
supabase db push
```

The `reel_chunks.embedding` column is `vector(768)` (migrated via `supabase/migrations/20260522000001_resize_embeddings_to_768.sql`). The embedding model is `gemini-embedding-2` (768-dim, Gemini API).

---

## iOS Commands

Open `ReelMind.xcworkspace` (not `.xcodeproj`) in Xcode — CocoaPods injects Firebase dependencies via the workspace. Build and run with ⌘R. There is no separate lint or test command configured.

---

## Architecture

### System topology

```
iOS App (SwiftUI)
    └── SupabaseManager  ← Supabase auth + data
    └── AuthSession      ← session state, mirrors JWT to App Group UserDefaults

iOS Share Extension ("URL Sharing module")
    └── ShareViewController  ← extracts URL, reads JWT from App Group, POSTs to backend

Backend (single Render web service — FastAPI + Celery in one process)
    └── POST /api/v1/reels  ← inserts reel row, dispatches Celery task
    └── Celery worker       ← runs ingestion pipeline (download → transcribe → …)
    └── Supabase            ← single database for both iOS and backend

Redis (Upstash, TLS)  ← Celery broker (local Docker in dev, Upstash in prod)
```

### iOS app navigation (`frontend/`)

`RootView` is the single routing hub. It reads two conditions — `AuthSession.session` (Supabase JWT) and the `@AppStorage("hasCompletedOnboarding")` flag — and routes to:

- `OnboardingFlow` (first launch, before onboarding is marked complete)
- `LoginView` / `SignupView` (after onboarding, no session)
- `ContentView` (authenticated main app)

`AuthSession` (an `ObservableObject` injected at the root) keeps the Supabase session in sync and mirrors the JWT access token into App Group UserDefaults (`group.com.reelmind.app`) so the share extension can read it without an in-process auth flow.

### Share Extension (`URL Sharing module/`)

`ShareViewController` is a UIKit view controller (not SwiftUI). Key points:
- Backend URL is **hardcoded** in `K.backendBaseURL` — must be updated when the Render URL or ngrok tunnel changes.
- It reads the auth token from App Group UserDefaults (key: `supabaseAuthToken`) — if the user isn't logged in, the backend will reject the POST with 401, but the extension still animates "Saved!" because the animation timeline runs in parallel and does not wait for the network response.
- URLs are also written to the App Group queue (`pendingReelURLs`) as an offline fallback; the main app is expected to drain this queue on launch (not yet implemented).
- `hasStartedSlideUp` / `hasStartedTimeline` guard idempotency because iOS fires `viewWillAppear`/`viewDidAppear` more than once per presentation.

### Backend ingestion pipeline (`backend/`)

`POST /api/v1/reels` (in `api/v1/reels.py`):
1. Auth: `api/deps.py` verifies the Supabase JWT via `supabase.auth.get_user()`.
2. Upserts a `profiles` row (avoids trigger + RLS conflicts on signup).
3. Inserts a `reels` row with `status="queued"`. Duplicate URL → returns existing row, no new task.
4. Dispatches `process_reel.delay(reel_id)` and returns HTTP 202.

`process_reel` Celery task (`workers/tasks.py`) — all pipeline stages in one task:
- **Step 15** (`services/downloader.py`): scrapes Instagram reel HTML using `curl_cffi` (TLS fingerprint impersonation), parses the embedded `application/json` GraphQL blob with `parsel`, extracts audio URL from the DASH manifest. Downloads audio-only `.m4a` and thumbnail to a temp dir.
- **Step 16** (`services/transcriber.py`): sends `.m4a` to Groq `whisper-large-v3-turbo`, persists transcript + `has_audio` flag.
- **Step 17** (`workers/tasks.py`): Build classification signal from transcript, caption, and hashtags.
- **Step 18** (`services/classifier.py`): Classify via Google Gemini `gemini-3.1-flash-lite` → category name + confidence score.
- **Step 19** (`workers/tasks.py`): Confidence routing — ≥0.70 → `status=ready`; <0.70 → `status=pending_category` with suggested categories.
- **Step 20** (`services/embedder.py`): Embed transcript+caption+hashtags as 768-dim vector via Gemini `gemini-embedding-2` → store in `reel_chunks`.
- **Step 22** (`services/notifier.py`): FCM push via Firebase Admin SDK. `ready` path: "Reel saved!". `pending_category` path: push with action buttons for suggested categories. Requires `FIREBASE_SERVICE_ACCOUNT_JSON` env var; silently skips if unset.

`DownloadError.is_retryable` controls whether Celery retries (max 3, backoff 60s × retry number) or marks the reel `status="failed"`. The temp dir is always cleaned up in the `finally` block.

### Database schema (Supabase / PostgreSQL)

Core tables: `profiles`, `categories`, `reels`, `reel_chunks`, `chat_sessions`, `chat_messages`, `feedback`. All have RLS enabled. The backend uses the **service role key** (bypasses RLS) via `supabase_client.py`; the iOS app uses the **anon key** (subject to RLS).

Key `reels` columns: `url` (unique per user), `status` (queued → processing → ready/failed), `transcript`, `has_audio` (bool, NULL = not yet processed), `caption`, `hashtags` (array), `creator_handle`, `thumbnail_url`.

### AI stack decisions

All AI services use free-tier providers (see `docs/DECISIONS.md`):
- Transcription: Groq `whisper-large-v3-turbo`
- Classification: Google Gemini `gemini-3.1-flash-lite`
- Chat / RAG: Google Gemini `gemini-2.5-flash`
- Embeddings: Gemini `gemini-embedding-2` (API call in Celery worker, requires `GEMINI_API_KEY`, 768-dim output)

Caption + hashtags are always fed to the classifier as primary signal alongside the transcript, not as a fallback.
