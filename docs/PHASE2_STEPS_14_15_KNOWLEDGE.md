# ReelMind — Phase 2 Steps 14 & 15 Knowledge Document

### The Backend Ingestion Pipeline: From URL to Audio

*Written so anyone can pick up the backend code and understand exactly what happens between the moment the iOS extension fires a `POST /api/v1/reels` and the moment the Celery worker has an mp3 file ready for transcription.*

---

## The Big Picture

The Share Extension hands us a single thing: a URL string. From there, we have to:

1. **Authenticate the request.** The extension sent us a Supabase JWT — we need to verify it's real and figure out which user it belongs to.
2. **Persist the reel.** Create a row in the `reels` table with `status='queued'` so the user can immediately see "I shared something, it's processing."
3. **Refuse duplicates.** If the user shares the same reel twice, we don't want to re-process it.
4. **Hand off to a worker.** Dispatch a Celery task and **return HTTP 202 immediately**. The Share Extension is waiting (briefly) for our response — every millisecond of latency here matters.
5. **Asynchronously, in the worker:** download the reel's audio as an mp3 so subsequent steps (Whisper transcription, classification) have something to work with.

Steps 14 and 15 of the build plan together cover exactly this slice of the pipeline.

| Step | What it covers |
|---|---|
| **14 (Backend)** | Queue ingestion job in Celery — the synchronous API endpoint |
| **15 (Backend)** | Download reel audio in worker — the first step of the async Celery task |

We document them together because they're meant to be read in sequence: Step 14 is the door, Step 15 is the first room you walk into. Without Step 14, no work ever reaches the worker. Without Step 15, the worker has nothing useful to do.

---

> ⚠️ **Implementation update (2026-05-09):** This doc was written assuming `yt-dlp` + `ffmpeg` for Step 15. We abandoned that approach during implementation — research showed yt-dlp's Instagram extractor doesn't reliably surface caption/hashtag metadata, and we needed a richer payload (music info, like counts, etc.) than it exposes. The actual implementation scrapes Instagram's HTML directly and parses the embedded JSON. Step 14 is unchanged. The "Step 15" section below describes what we **actually built**; references to yt-dlp/mp3/ffmpeg in older sections of this doc are historical context only.

---

## File Inventory

```
backend/
├── api/
│   └── v1/
│       └── reels.py           ← Step 14: POST /api/v1/reels endpoint
├── workers/
│   ├── celery_app.py          ← Celery configuration (unchanged from Phase 1)
│   └── tasks.py               ← Step 15 + Step 16 wired in here
├── services/
│   ├── downloader.py          ← Step 15: Instagram JSON scraper + DASH audio extractor
│   └── transcriber.py         ← Step 16: Groq Whisper wrapper (see Steps 16-18 doc)
├── schemas/
│   └── reel.py                ← request/response Pydantic models
└── requirements.txt           ← curl_cffi + parsel pinned here (no yt-dlp, no ffmpeg)
```

The `services/` folder is the home for any "do one thing, no HTTP routes, no Celery glue" module. Whisper transcription and Llama classification live alongside it.

---

## Step 14 — The `POST /api/v1/reels` Endpoint

The full implementation is in [`backend/api/v1/reels.py`](../backend/api/v1/reels.py). It's ~100 lines. Let's walk through it section by section.

### The endpoint signature

```python
@router.post("", response_model=ReelQueuedResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_reel(
    payload: ReelCreate,
    authorization: str = Header(..., description="Bearer <supabase_jwt>"),
):
```

A few things worth understanding:

| Element | Why |
|---|---|
| `status_code=HTTP_202_ACCEPTED` | 202 means "I got your request and will process it later." It's the canonical status for any endpoint that dispatches async work. 200 OK would be misleading because the work isn't done yet. |
| `response_model=ReelQueuedResponse` | A Pydantic model defined in `schemas/reel.py`. Forces the JSON shape so the iOS app (or future web client) gets a stable contract. |
| `authorization: str = Header(...)` | The `...` is FastAPI's way of saying "this header is required" — if it's missing, FastAPI auto-rejects with 422 before our function runs. |
| `payload: ReelCreate` | Defined in `schemas/reel.py` as `{"url": HttpUrl}`. The `HttpUrl` type validates that `url` is a real URL string before our code sees it. |

### Step-by-step: what happens when a request arrives

```
┌────────────────────────────────────────────────────────┐
│  POST /api/v1/reels                                    │
│  Authorization: Bearer <jwt>                           │
│  { "url": "https://www.instagram.com/reel/XYZ/" }      │
└─────────────────┬──────────────────────────────────────┘
                  ▼
   ┌──────────────────────────────────────┐
   │ 1. Strip "Bearer " prefix from header │
   └──────────────────┬───────────────────┘
                      ▼
   ┌──────────────────────────────────────┐
   │ 2. supabase.auth.get_user(jwt)       │
   │    → 401 if invalid/expired          │
   │    → user_id otherwise               │
   └──────────────────┬───────────────────┘
                      ▼
   ┌──────────────────────────────────────────────┐
   │ 3. INSERT INTO reels (user_id, url, status)  │
   │    VALUES ($1, $2, 'queued')                 │
   │    → 23505 (UNIQUE violation) → 409 Conflict │
   │    → success → reel_id                       │
   └──────────────────┬───────────────────────────┘
                      ▼
   ┌──────────────────────────────────────┐
   │ 4. process_reel.delay(reel_id)       │
   │    → Celery enqueues to Redis        │
   └──────────────────┬───────────────────┘
                      ▼
   ┌──────────────────────────────────────┐
   │ 5. Return 202 + reel_id              │
   └──────────────────────────────────────┘
```

Each numbered step has a corresponding code block, which we'll dissect now.

### 1. Auth header parsing

```python
token = authorization.removeprefix("Bearer ").strip()
```

Defensive but minimal. `removeprefix` is a Python 3.9+ method that returns the original string unchanged if the prefix isn't present — so `"abcd".removeprefix("Bearer ") == "abcd"`. We don't error on malformed headers because Supabase's `get_user` will fail in that case anyway, and we only want one place that produces 401s.

### 2. JWT verification — the auth boundary

```python
try:
    user_response = supabase.auth.get_user(token)
    user_id = str(user_response.user.id)
except Exception as exc:
    raise HTTPException(status_code=401, detail="Invalid or expired auth token")
```

This is the single most important line in the file. **`supabase.auth.get_user(token)` calls the Supabase Auth API** to verify the JWT. If the token is forged, expired, or malformed, it throws. We catch broadly because the SDK throws several different exception types depending on the failure mode, and they all mean the same thing to us: 401.

A common alternative would be to decode the JWT locally with the project's JWT secret. We don't do that because:

- **It requires storing yet another secret** (the JWT signing secret) on the backend.
- **Network calls to Supabase Auth are fast** (~50ms) and Supabase is already in our request path for the database write that follows.
- **Local decoding doesn't catch revoked sessions.** If a user logs out, their old JWT is still cryptographically valid; only Supabase's server-side session table knows it's revoked.

So we trade a tiny amount of latency for stronger correctness. Worth it.

**Why does the service-role client validate user JWTs at all?** Even though our `supabase` client was initialised with the service-role key (which bypasses RLS), the `auth.get_user()` method takes an explicit JWT argument. Internally it makes an authenticated HTTP call to Supabase Auth using that JWT, not the service-role key. So service-role-keyed clients can validate user tokens just fine.

### 3. Insert with duplicate handling

```python
try:
    result = (
        supabase.table("reels")
        .insert({"user_id": user_id, "url": url_str, "status": "queued"})
        .execute()
    )
    reel_id = result.data[0]["id"]
except Exception as exc:
    error_str = str(exc).lower()
    if any(k in error_str for k in ("unique", "duplicate", "23505")):
        # … return 409 with existing reel info …
```

Two important patterns here:

**Pattern: insert-first, handle-conflict.** Rather than doing a `SELECT … WHERE user_id = ? AND url = ?` to check for an existing reel and *then* inserting, we just attempt the insert and let the database's UNIQUE constraint do the dedup work. This is faster (one round trip instead of two) and **race-condition-free** — two concurrent requests for the same URL can't both succeed because the constraint is enforced atomically.

The `(user_id, url)` UNIQUE constraint comes from the migration in [`supabase/migrations/20260502000004_create_reels_table.sql`](../supabase/migrations/20260502000004_create_reels_table.sql).

**Pattern: stringly-typed error matching.** PostgREST (the layer Supabase uses to expose PostgreSQL over REST) returns errors as JSON with an error code field, but `supabase-py` wraps them in a generic exception. Rather than reaching into private internals, we just lowercase the exception message and look for indicators of a unique violation. The Postgres error code `23505` is the canonical signal, but we also check `"unique"` and `"duplicate"` because different driver versions phrase the message differently.

If we get a duplicate, we look up the existing reel and return its details:

```python
existing = supabase.table("reels").select("id, created_at, status") \
    .eq("user_id", user_id).eq("url", url_str) \
    .is_("deleted_at", "null").single().execute()

raise HTTPException(
    status_code=409,
    detail={
        "message": "You already saved this reel",
        "reel_id": existing.data["id"],
        "saved_at": existing.data["created_at"],
        "current_status": existing.data["status"],
    },
)
```

The iOS app (or any client) can render this as: *"You already saved this on May 1st — it's currently being processed."*

This actually implements **Step 21 (duplicate URL detection)** from the build plan, even though it's listed separately. We did it now because the schema-level UNIQUE constraint forces us to handle the violation here — there's no way to defer that handling to Step 21 cleanly.

### 4. Celery dispatch

```python
process_reel.delay(reel_id)
```

`.delay(...)` is Celery's shortcut for "enqueue this task with these args." Internally it serialises `("workers.tasks.process_reel", reel_id, ...)` to JSON and pushes it onto the Redis broker. A worker process (running `celery -A workers.celery_app worker`) picks it up and runs it.

Things worth knowing:

- **`delay()` returns instantly** — typically <5ms. It does not wait for the worker to ack the task.
- **We pass `reel_id`, not the reel object.** Sending small primitives is the Celery best practice; sending large objects bloats the broker and risks serialization issues. The worker re-fetches the reel from the database when it starts.
- **No retry config at the dispatch site.** Retry behavior is configured on the task itself (`max_retries=3` decorator on `process_reel`).

### 5. The response

```python
return ReelQueuedResponse(
    reel_id=reel_id,
    status="queued",
    message="Reel received and queued for processing",
)
```

Three fields. The `reel_id` is the most important — the iOS app uses it to look up the reel later (e.g. when it polls for status or receives a push notification with the same ID).

---

## Step 15 — The Reel Extractor (Custom Instagram Scraper)

Now we cross the API/worker boundary. Step 14 ends by calling `process_reel.delay(reel_id)`. From here on, we're inside a Celery worker process — a separate Python process from the FastAPI app, with its own memory, connecting to the same Redis and Supabase.

The worker's first job is to download the reel's **audio** (for Whisper) and **metadata** (caption, hashtags, creator, thumbnail, music info, etc.). This is implemented in [`backend/services/downloader.py`](../backend/services/downloader.py).

### Why we abandoned yt-dlp

The original plan called for `yt-dlp` + `ffmpeg`. We changed direction during implementation for two reasons:

1. **Caption/hashtag extraction is unreliable.** yt-dlp's Instagram extractor reads only the video stream and thin metadata — it frequently returns empty or truncated captions and misses hashtag arrays.
2. **We want richer signal.** The classifier benefits from like counts, music titles, verified-author flag, and more. yt-dlp doesn't surface these.

We replaced it with a custom 3-stage extractor that scrapes the public reel HTML directly, parses the JSON blob Instagram embeds in a `<script type="application/json">` tag, and pulls the audio-only DASH stream URL out of the `video_dash_manifest` XML inside that JSON.

### Tech stack — no ffmpeg, no yt-dlp

| Library | Role |
|---|---|
| `curl_cffi` | HTTPS client that impersonates a real Chrome TLS fingerprint. Without this, Instagram returns a degraded HTML response that doesn't include the JSON blob we need. |
| `parsel` | CSS selector for finding the embedded `<script type="application/json">` blocks in the HTML. |
| `xml.etree.ElementTree` (stdlib) | Parses the DASH manifest XML to extract the audio Representation's `<BaseURL>`. |

**No `ffmpeg`** — we save the audio in its native container (`.m4a`, AAC codec inside MP4) and feed it directly to Groq Whisper, which accepts m4a. This eliminates a system-level dependency.

### Three-stage pipeline inside `download_reel`

```
┌────────────────────────────────────────────────────────┐
│  Stage 1 — Fetch                                       │
│  curl_cffi.get(url, impersonate="chrome")              │
│  Detects: 4xx, 5xx, login redirect → DownloadError     │
└────────────────────────┬───────────────────────────────┘
                         ▼
┌────────────────────────────────────────────────────────┐
│  Stage 2 — Locate media item                           │
│  parsel finds every <script type="application/json">   │
│  Recursive walk for either of the keys IG ships under: │
│    xdt_api__v1__media__shortcode_web_info              │
│    xdt_api__v1__media__shortcode__web_info             │
│  → returns items[0] dict                               │
└────────────────────────┬───────────────────────────────┘
                         ▼
┌────────────────────────────────────────────────────────┐
│  Stage 3 — Parse + downloads                           │
│  Build ReelMetadata dataclass                          │
│  Parse video_dash_manifest XML for audio URL           │
│  Download audio  → /tmp/reelmind_xxx/<reel_id>.m4a     │
│  Download thumb  → /tmp/reelmind_xxx/<reel_id>.jpg     │
│  (video download function exists but is gated off)     │
└────────────────────────────────────────────────────────┘
```

### What gets returned

```python
@dataclass
class DownloadResult:
    metadata: ReelMetadata       # rich dataclass — see below
    audio_path: str | None       # /tmp/.../<reel_id>.m4a
    thumbnail_path: str | None   # /tmp/.../<reel_id>.jpg
    video_path: str | None       # only when download_video=True (default off)
    temp_dir: str                # caller is responsible for cleanup
```

`ReelMetadata` carries every useful field from the JSON, including some we don't yet persist (likes, comments, music title/artist, post timestamp, original dimensions, verified-author flag, view count, paid-partnership flag). Forward-compat fields go into `metadata.extra`. See [docs/backlog.md](backlog.md) → "Persist richer reel metadata" for the plan to surface those in the schema.

### What "persist" means here

There are two storage layers, and they have very different lifetimes:

| Storage | What lives there | Lifetime |
|---|---|---|
| `/tmp/reelmind_xxx/<reel_id>.m4a` (temp dir) | Downloaded audio file, downloaded thumbnail JPG | **Deleted at the end of the Celery task** in the `finally` block |
| `reels` row in Supabase | DB columns: `caption`, `hashtags`, `creator_handle`, `thumbnail_url` (and after Step 16: `transcript`, `has_audio`) | **Forever** (until soft-delete) |

When we say "Step 15 persists metadata to DB" we mean the `supabase.table("reels").update({...})` call in `tasks.py` — those columns survive the task. The audio file does not.

### Error mapping — retryable vs non-retryable

The downloader raises a custom `DownloadError(is_retryable: bool)`. The Celery task reads `is_retryable` to decide between calling `self.retry()` and marking the reel `failed`.

| Failure | Class | Reason |
|---|---|---|
| Network timeout / connection reset (`curl_cffi` raised) | retryable | Wifi blip, IG latency spike — refresh fixes it |
| HTTP 5xx from Instagram | retryable | Their server is having a moment |
| Couldn't find JSON blob in HTML | retryable | IG occasionally serves degraded HTML |
| Audio/thumbnail file download HTTP 5xx | retryable | CDN blip |
| HTTP 401 / 403 from `/reel/...` | **non**-retryable | Reel is private or login-walled; retries won't help |
| HTTP 404 from `/reel/...` | **non**-retryable | Reel deleted |
| Redirected to `/accounts/login` | **non**-retryable | Same as 401 |
| Audio/thumbnail file download HTTP 4xx | **non**-retryable | Asset URL expired or revoked |

Each error log line includes both the **HTTP status code** and a **likely cause** so on-call can diagnose without re-running the request. Example log lines:

```
HTTP response | status=403 | bytes=14821
Instagram returned 403 — likely login-required / private reel
```

### Linear backoff

When the Celery task receives a retryable error, it schedules a retry with **linear backoff** — wait time grows by a constant amount each attempt:

| Attempt | Wait before retry |
|---|---|
| 1st failure | 60 s |
| 2nd failure | 120 s |
| 3rd failure | 180 s |
| 4th failure | give up, mark `failed` |

Code: `countdown = 60 * (self.request.retries + 1)` ([tasks.py](../backend/workers/tasks.py)).

We chose linear over **exponential backoff** (60/120/240/480) because exponential quickly exceeds Celery's 600 s task time limit. Linear stays inside the budget and gives predictable worst-case recovery (~6 minutes).

**Without the retryable/non-retryable distinction, every failure would burn three retries** — including private reels that would never succeed. That's wasted compute and a slow UX. With the distinction, private/deleted reels fail in ~5 seconds.

---

## Step 15 inside `process_reel` — how it's called

Look at [`backend/workers/tasks.py`](../backend/workers/tasks.py). The relevant slice:

```python
@celery_app.task(bind=True, max_retries=3)
def process_reel(self, reel_id: str) -> dict:
    supabase = get_supabase()
    download_result = None
    try:
        # Mark processing so the iOS app sees the spinner state
        supabase.table("reels").update({
            "status": "processing",
            "retry_count": self.request.retries,
        }).eq("id", reel_id).execute()

        # Fetch URL from DB (source of truth, not the Celery arg)
        row = supabase.table("reels").select("url, user_id").eq("id", reel_id).single().execute()
        url = row.data["url"]

        # Step 15 — extract + download
        try:
            download_result = download_reel(url, reel_id)
        except DownloadError as exc:
            return _handle_pipeline_error(self, supabase, reel_id, exc, exc.is_retryable, log)

        # Persist metadata immediately, before transcription
        meta = download_result.metadata
        supabase.table("reels").update({
            "caption": meta.caption,
            "hashtags": meta.hashtags,
            "creator_handle": meta.creator_handle or None,
            "thumbnail_url": meta.thumbnail_url,
        }).eq("id", reel_id).execute()

        # … Step 16 (transcription) follows …
    finally:
        if download_result is not None:
            _cleanup(download_result, log)  # rm -rf the temp_dir
```

**Order of operations matters:**

1. **Mark `status='processing'` first** so the iOS app shows the spinner.
2. **Fetch URL second** — the DB row is the source of truth, not the Celery arg.
3. **Download third.**
4. **Persist metadata immediately after download** — before transcription. If Whisper later fails, the caption/hashtags/creator/thumbnail are already saved and the user gets *some* data on their reel card.

This "save partial data as you go" pattern is deliberate. Pipelines have many failure modes; partial data beats a blank card.

---

## Cleanup — the `finally` block

```python
def _cleanup(result: DownloadResult, log) -> None:
    temp_dir = result.temp_dir
    if not temp_dir or not os.path.exists(temp_dir):
        return
    log.info("cleanup | removing temp_dir=%s", temp_dir)
    for name in os.listdir(temp_dir):
        os.remove(os.path.join(temp_dir, name))
    os.rmdir(temp_dir)
```

The audio + thumbnail files are only useful for the duration of one Celery task. The `finally` block (wrapping the entire pipeline body) deletes the whole temp dir whether the task succeeded, failed, or retried.

`tempfile.mkdtemp()` creates a unique dir per call, so leaking the dir would accumulate empty directories in `/tmp/`. Render's free tier has a small `/tmp/`, so this matters.

Errors during cleanup are logged but never raised — we don't want a transient permission issue on cleanup to mark a successful reel as failed.

---

## What you can verify after Step 15 + Step 16

You can test the whole download → metadata → transcription pipeline end-to-end **without** waiting for Step 18 (classification).

**In the Celery worker logs** — full per-stage trace (each line carries `reel_id` for grep):

```
process_reel start | retry=0/3
marking status=processing
reel url loaded | url=https://www.instagram.com/reel/...
step 15 | downloading reel
fetching reel HTML
HTTP response | status=200 | bytes=...
media item located in JSON blob #1
DASH manifest present | length=8421 chars
audio stream selected | codec=mp4a.40.5 | bandwidth=66525 | host=instagram.fdel1-7.fna.fbcdn.net
metadata parsed | shortcode=DYFKkLQvXMP | creator=@gima_ashi | has_audio=True | duration=19.4s
downloading audio | dest=/tmp/reelmind_.../<id>.m4a
audio download done | bytes=162590
downloading thumbnail | dest=/tmp/reelmind_.../<id>.jpg
step 15 | persisting metadata | creator=@gima_ashi | hashtags=10 | caption_chars=156 | thumb=True
step 15 | metadata saved to DB
step 16 | transcribing audio
calling Groq Whisper | model=whisper-large-v3-turbo
transcription done | language=en | duration=19.4s | chars=247 | has_audio=True
step 16 | transcript saved to DB
cleanup | removing temp_dir=/tmp/reelmind_...
process_reel done
```

**In Supabase Studio** (`reels` table):

- `status`: `queued` → `processing` (stays there until Step 19 lands)
- `caption`: actual reel text
- `hashtags`: array like `["halloween", "halloweenmakeupideas", ...]`
- `creator_handle`: IG @username
- `thumbnail_url`: an Instagram CDN URL (open in browser to verify)
- `transcript`: the Whisper output
- `has_audio`: `true` for spoken reels, `false` for music-only

**In the iOS app** (pull-to-refresh after the worker finishes):

The dev-only rich card in [`frontend/TempReels/ReelsListView.swift`](../frontend/TempReels/ReelsListView.swift) renders thumbnail + `@creator_handle` + status pill (orange = `processing`) + caption excerpt + hashtag chips + transcript char count. Stuck at orange `processing` is the **success state** for now — Step 19 will flip it to `ready`/`uncategorised` once classification lands. See [docs/backlog.md](backlog.md) → "Replace dev-only rich reel card".

---

## Render Deployment Notes

For the backend to actually receive POSTs on Render, the env vars in `render.yaml` must be set in the Render dashboard:

| Env var | Where to get it |
|---|---|
| `SUPABASE_URL` | Supabase dashboard → Project Settings → API |
| `SUPABASE_ANON_KEY` | Same |
| `SUPABASE_SERVICE_ROLE_KEY` | Same — under "Service Role Key" (keep secret!) |
| `GROQ_API_KEY` | console.groq.com → API Keys |
| `REDIS_URL` | The cloud Redis instance (Upstash or Render's add-on) |

`sync: false` in `render.yaml` means Render does **not** pull these from a synced source — they must be entered manually in the Render dashboard.

The build command is just `pip install -r backend/requirements.txt` — **no `apt-get install ffmpeg`** since we removed the ffmpeg dependency by using the native `.m4a` audio container directly (Groq Whisper accepts m4a).

---

## Edge Cases We Handle

| Scenario | Status code / behavior |
|---|---|
| Missing `Authorization` header | 422 (FastAPI auto-rejects) |
| Malformed `Authorization` header (no `Bearer ` prefix) | 401 (Supabase auth fails) |
| Expired/forged JWT | 401 |
| Valid JWT, user already saved this URL | 409 with existing reel info |
| Valid JWT, valid URL, valid user, healthy DB | 202 + `reel_id` |
| DB write succeeds but Celery dispatch fails (Redis down) | Reel queued in DB but never processed; needs a sweeper (TODO) |
| Reel URL is private (HTTP 401/403 or login redirect) | Reel marked `failed` quickly (no retries) |
| Reel URL is deleted (HTTP 404) | Reel marked `failed` quickly (no retries) |
| Reel URL gives a network timeout / 5xx | Retries up to 3× with linear backoff (60/120/180 s) |
| Instagram serves degraded HTML missing the JSON blob | Retried (assumed transient) |
| Reel has no audio track (silent / `has_audio=false` in JSON) | Audio download skipped; `has_audio=false` written to DB; pipeline continues |
| Audio CDN URL expired between scrape and download | Retried — Step 15 re-runs the full scrape |

---

## What's NOT Done Here

These are explicitly **not** part of Steps 14 & 15 and live in later steps:

- **Background sweeper for `status='queued'` reels that never got processed.** If Redis or the workers are down at the moment of dispatch, a reel could be stuck in `queued` forever. A periodic sweep is on the backlog.
- **Rate limiting per user.** Right now a user could POST 1000 URLs in a second and we'd happily try to process all of them. Out of scope for v1.
- **Idempotency keys.** We rely on the `(user_id, url)` UNIQUE constraint to handle duplicate POSTs. If a single URL needs to be POSTed under multiple keys (rare), we'd need a separate idempotency mechanism.
- **Cleanup of audio files on task crash before the `finally` block runs.** Python's `finally` runs on most failure modes, but a hard kill (SIGKILL, OOM) can leave files. Render's `/tmp` is wiped on container restart, so this is self-healing in production.

---

## How to Verify This Code Works

Local smoke test:

```bash
# Terminal 1: start Redis (Docker shortcut)
docker run -p 6379:6379 redis

# Terminal 2: start the FastAPI app
cd backend
uvicorn main:app --reload --port 8000

# Terminal 3: start a Celery worker
cd backend
celery -A workers.celery_app worker --loglevel=info

# Terminal 4: send a request
# (Get a real Supabase JWT first — easiest way is to log in via the iOS app
#  and read it from the App Group UserDefaults, OR use Supabase Studio's
#  SQL editor to issue a test JWT.)

curl -X POST http://localhost:8000/api/v1/reels \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-supabase-jwt>" \
  -d '{"url": "https://www.instagram.com/reel/<some-public-reel-id>/"}'
```

Expected output: HTTP 202, JSON `{"reel_id": "...", "status": "queued", "message": "..."}`.

Watch Terminal 3 (Celery) — you should see the full per-stage trace shown in the "What you can verify" section above (HTML fetch → JSON locate → DASH parse → audio + thumbnail download → metadata persist → Whisper → transcript persist → cleanup).

Then look at the `reels` table in Supabase Studio:
- The row should have `status='processing'` (will stay there until Step 19 lands)
- `caption`, `creator_handle`, `thumbnail_url`, `hashtags`, `transcript`, `has_audio` should all be populated

---

## Key Design Decisions Summary

| Decision | What we chose | Why |
|---|---|---|
| Auth verification | `supabase.auth.get_user()` (network call) | Catches revoked sessions; no extra secret to store |
| Duplicate handling | Insert-then-catch unique violation | Race-condition-free; one round trip |
| Returning duplicate info | 409 with existing reel details | Lets clients render "you already saved this" |
| Async dispatch | Celery `.delay()` to Redis | Keeps the API endpoint sub-100ms |
| Argument passed to worker | `reel_id` only | Tiny payload, worker re-reads source of truth |
| Audio download approach | Custom HTML scrape + DASH manifest parse (curl_cffi + parsel) | yt-dlp's caption/hashtag extraction is unreliable; we need richer signal |
| Audio format | Native `.m4a` (HE-AAC inside MP4 container) | No ffmpeg dependency; Groq Whisper accepts m4a directly |
| Audio storage location | `tempfile.mkdtemp()` in `/tmp` | Ephemeral, auto-cleaned, no Supabase Storage costs |
| Thumbnail handling | Download to `/tmp` + store IG CDN URL in DB | URL works immediately for the iOS card; mirroring to Supabase Storage is on the backlog |
| Video download | Function exists, gated off (`download_video=False`) | Not needed for transcription; on the backlog for in-app playback |
| Error categorization | `is_retryable` flag on `DownloadError` / `TranscriptionError` | Lets Celery retry network errors but skip permanent failures |
| Retry backoff | Linear: 60/120/180 s | Fits inside 600 s task time limit |
| Metadata persistence timing | Immediately after download, before transcription | Partial data > no data on failure |
| Cleanup strategy | `finally` block with logged-only failures | Prevents accumulated `/tmp` cruft |
| Status after Step 16 | Stays `processing` until Step 19 routes to `ready` / `uncategorised` | Don't lie about readiness — reel isn't browsable until classified |

---

## Cross-references

- **Step 11 (FCM)** — not yet done; needed for Step 22 (push notification on completion). Steps 14 & 15 do not depend on it.
- **Step 16 (Whisper)** — runs immediately after Step 15 in the same Celery task. Reads the audio file produced here.
- **Step 17 (caption fallback)** — uses the metadata captured during Step 15.
- **Step 18 (Claude classification)** — also runs in the same Celery task.
- **Step 19 (confidence routing)** — TODO. Will translate the classifier's `category` name into a `category_id` and update `reels.status` to `ready` or `uncategorised`.
- **Step 21 (duplicate URL detection)** — partially implemented here via the 409 response. The "show 'you already saved this on [date]' notification" UX is iOS-side work.

---

*ReelMind Phase 2 Knowledge Doc — Steps 14 & 15 — v2.0 (2026-05-10: rewritten Step 15 to reflect the custom-scraper implementation that replaced yt-dlp)*
