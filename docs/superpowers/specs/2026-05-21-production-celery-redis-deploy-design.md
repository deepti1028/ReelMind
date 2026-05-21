# Production Celery + Redis Deployment Design

**Date:** 2026-05-21
**Status:** Approved, pending implementation
**Goal:** Make the full reel ingestion pipeline (Steps 15–22) work in production by deploying a Celery worker and connecting a free managed Redis instance, and enabling FCM push notifications via the Firebase Admin SDK.

---

## Background

FastAPI is already deployed on Render at `https://reelmind-8paz.onrender.com`. When a user shares a reel, the iOS app POSTs to this server, which inserts a DB row and dispatches a Celery task. However:

- No Redis is configured on Render → Celery has no broker, task dispatch fails silently
- No Celery worker is deployed on Render → even if dispatch worked, nothing would process the task
- `FIREBASE_SERVICE_ACCOUNT_JSON` is not set on Render → FCM push notifications are silently disabled

The entire pipeline code (Steps 15–22) is already written and working locally. This plan is purely about making it work in production.

---

## Architecture

```
iPhone
  └── POST /api/v1/reels
          │
          ▼
  Render Web Service (FastAPI)        ← already deployed
          │
          │ process_reel.delay(reel_id)
          ▼
  Upstash Redis (free tier)           ← new, external service
          │
          │ picks up task
          ▼
  Render Background Worker (Celery)   ← new Render service
          │
          ├── Step 15: Download reel audio + metadata
          ├── Step 16: Transcribe (Groq Whisper)
          ├── Step 17: Build classification signal
          ├── Step 18: Classify (Groq Llama 3.3 70B)
          ├── Step 19: Confidence routing → status=ready or pending_category
          ├── Step 20: Embed content + store reel_chunk (BAAI/bge-small-en-v1.5, 384-dim)
          └── Step 22: FCM push notification to user's device
```

Both Render services share the same Upstash Redis URL. FastAPI writes tasks; Celery reads and executes them.

---

## Components

### Upstash Redis (free tier)
- Broker for Celery task queue
- Free tier: 10,000 commands/day, 256MB, no credit card required
- Connection: TLS Redis URL (`rediss://default:xxxx@xxx.upstash.io:6379`)
- No code changes needed — just set `REDIS_URL` env var on both Render services

### Render Background Worker (new service)
- Type: `worker` (not `web`) — Render never routes HTTP to it
- Plan: free tier
- Runs: `celery -A workers.celery_app worker --loglevel=info --concurrency=1`
- Concurrency 1: keeps memory within Render free tier limits (sentence-transformers model is large)
- Defined in `render.yaml` alongside the existing web service

### Firebase Admin SDK (FCM push)
- Already implemented in `services/notifier.py`
- Requires `FIREBASE_SERVICE_ACCOUNT_JSON` env var: base64-encoded Firebase service account JSON
- Set on the Celery worker service only (FastAPI never sends pushes)

---

## Changes Required

### Manual steps (done by you, not code)

**Step M1 — Create Upstash Redis**
1. Go to [upstash.com](https://upstash.com) → sign up (free, no credit card)
2. Create a new Redis database → select the region closest to Render Oregon (`us-west-1` or `us-east-1`)
3. Copy the Redis connection URL (starts with `rediss://`)

**Step M2 — Get Firebase service account JSON**
1. Go to [Firebase Console](https://console.firebase.google.com) → select your project
2. Project Settings → Service Accounts → Generate new private key → download JSON file
3. In your terminal, base64-encode it:
   ```bash
   base64 -i /path/to/serviceAccount.json | tr -d '\n'
   ```
4. Copy the output string

**Step M3 — Set env vars on Render**
In the Render dashboard, add to **both** services (reelmind-api and reelmind-celery):
- `REDIS_URL` → Upstash Redis URL from Step M1

Add to **reelmind-celery only**:
- `FIREBASE_SERVICE_ACCOUNT_JSON` → base64 string from Step M2

**Step M4 — Deploy**
After the code changes are committed and pushed, Render auto-deploys both services.
Verify by checking Render logs for:
- reelmind-api: no Redis connection errors on startup
- reelmind-celery: `celery@xxx ready` in logs

**Step M5 — Smoke test**
1. Open the iOS app and share a reel
2. Watch reelmind-celery logs in Render dashboard — should see steps 15–22 running
3. Check the reel appears in the app with a category assigned
4. Confirm push notification arrives on device

---

### Code changes (done by Claude)

**Step C1 — Update render.yaml**
Add a `worker` service for Celery alongside the existing `web` service.
File: `render.yaml`

```yaml
# Add after the existing web service:
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

**Step C2 — Add REDIS_URL to existing web service env vars in render.yaml**
The FastAPI service also needs `REDIS_URL` to dispatch tasks to Upstash.
File: `render.yaml` — add to existing `reelmind-api` envVars block:
```yaml
- key: REDIS_URL
  sync: false
```

**Step C3 — Update CLAUDE.md**
The CLAUDE.md says "Steps 17–22 not yet implemented" — this is outdated. Update it to reflect that the full pipeline is implemented and document the production deployment setup.

---

## Error Handling

- **Redis unreachable at startup**: FastAPI will still serve HTTP, but `process_reel.delay()` will raise. The reel row will stay `status=queued`. No crash — existing error handling in `api/v1/reels.py` wraps the dispatch.
- **Celery worker crash**: Render auto-restarts background workers. In-flight task is lost; reel stays `status=processing`. Max retries (3) handle transient failures.
- **FCM push failure**: `send_push_notification` never raises — failure is logged and returns False. Pipeline still completes; reel status is correct even without the push.
- **Upstash rate limit (10K/day)**: Unlikely for a small app. Each reel = ~10–15 Redis commands. Supports ~700–1000 reels/day on free tier.

---

## Testing Checklist

- [ ] `REDIS_URL` set on both Render services
- [ ] `FIREBASE_SERVICE_ACCOUNT_JSON` set on Celery worker service
- [ ] Render shows `reelmind-celery` service as deployed and running
- [ ] Celery logs show `celery@xxx ready`
- [ ] Share a reel → Celery logs show all pipeline steps completing
- [ ] Reel appears in app with category
- [ ] Push notification received on device
