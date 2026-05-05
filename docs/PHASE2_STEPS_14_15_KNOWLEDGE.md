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

## File Inventory

```
backend/
├── api/
│   └── v1/
│       └── reels.py           ← Step 14: POST /api/v1/reels endpoint
├── workers/
│   ├── celery_app.py          ← Celery configuration (unchanged from Phase 1)
│   └── tasks.py               ← Step 15 wired in here
├── services/
│   └── downloader.py          ← Step 15: yt-dlp wrapper (NEW in this phase)
├── schemas/
│   └── reel.py                ← request/response Pydantic models
└── requirements.txt           ← yt-dlp pinned here

render.yaml                    ← apt-get install ffmpeg added at build time
```

The `services/` folder is the home for any "do one thing, no HTTP routes, no Celery glue" module. As we add Whisper, Claude, and embedding services in later steps, they'll all live here.

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

## Step 15 — The Audio Downloader Service

Now we cross the API/worker boundary. Step 14 ends by calling `process_reel.delay(reel_id)`. From here on, we're inside a Celery worker process — a separate Python process from the FastAPI app, with its own memory, connecting to the same Redis and Supabase.

The worker's first job is to download the reel's audio. This is implemented in [`backend/services/downloader.py`](../backend/services/downloader.py).

### Why download audio specifically (not video)?

The Whisper transcription API (Step 16) accepts audio files up to 25 MB. A typical reel video is 5-50 MB; the audio track alone is 0.5-3 MB. Downloading audio-only is:

- **Faster** (less bandwidth)
- **Smaller** (well under Whisper's limit)
- **All we need** (we don't keep the video — we just want the spoken content)

`yt-dlp` makes this trivial via the `bestaudio` format selector and a postprocessor that pipes through `ffmpeg`.

### Why yt-dlp and not the official Instagram API?

Short answer: **there is no official Instagram API for reels.** Meta has the Graph API for business accounts, but it doesn't expose reel content. The community-maintained downloader libraries (`yt-dlp`, `instaloader`, `instagrapi`) reverse-engineer Instagram's web interface.

We chose **yt-dlp** because:

| Criterion | yt-dlp | instaloader | instagrapi |
|---|---|---|---|
| Active maintenance | ✅ Major releases monthly | ✅ Active | ⚠️ Less frequent |
| ToS pressure | Treats public content as public, no login required for public reels | Same | Often requires login |
| Format flexibility | Built-in audio extraction via ffmpeg | Limited | Limited |
| Track record | Used by millions of users for thousands of sites | Instagram-only | Instagram-only |

The trade-off: we're depending on an unstable upstream (Instagram's HTML structure can change), so `yt-dlp` versions need to be kept reasonably current. We pinned `yt-dlp==2024.11.18` — the last release before our build date — and you should bump this every few months.

### The system dependency: ffmpeg

`yt-dlp` itself doesn't decode audio. It downloads the source stream (often `.m4a` or some HLS variant) and shells out to `ffmpeg` to convert it to mp3. **ffmpeg must be installed at the OS level.**

On macOS for local dev: `brew install ffmpeg`.
On Render (production): we updated `render.yaml`'s build command:

```yaml
buildCommand: apt-get update -y && apt-get install -y ffmpeg && pip install -r backend/requirements.txt
```

Render's build environment runs as root on Ubuntu, so `apt-get` works without `sudo`. The first build will be slower (~30 s for the apt cache update + ffmpeg install), but subsequent builds are fast because Render caches the build environment.

**If `ffmpeg` is missing, our code will return a non-retryable error.** Watch the Celery logs for `"ffmpeg may not be installed"` — that's the diagnostic we surface in [`downloader.py`](../backend/services/downloader.py).

### Walkthrough of `download_reel_audio()`

```python
def download_reel_audio(url: str, reel_id: str) -> DownloadResult:
    output_dir = tempfile.mkdtemp(prefix="reelmind_")
    output_template = os.path.join(output_dir, f"{reel_id}.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "128",
        }],
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
    }
```

| Option | What it does |
|---|---|
| `format: "bestaudio/best"` | Prefer audio-only streams; fall back to "best" (any stream) if Instagram only serves combined video+audio. |
| `FFmpegExtractAudio` postprocessor | After download, transcode whatever we got into mp3 at 128 kbps. 128 kbps is the sweet spot — high enough for clean Whisper transcription, low enough to stay fast. |
| `outtmpl` | yt-dlp uses `printf`-like template strings. `%(ext)s` is replaced with the actual extension after postprocessing — so the final file lands at `/tmp/reelmind_xxx/<reel_id>.mp3`. |
| `quiet: True, no_warnings: True` | Suppress yt-dlp's own logging — we control logging via Python's `logging` module. |
| `socket_timeout: 30` | Don't sit forever on a hung connection. 30 s is generous but bounded. |
| (deliberately omitted) `cookies` | We don't pass login cookies, so private reels will fail with an extractor error. That's by design — see error handling below. |

The actual download:

```python
with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(url, download=True)
```

`extract_info(url, download=True)` does two jobs in one call:
1. Downloads the audio file
2. Returns a `dict` of metadata about the reel (caption, uploader, thumbnail URL, duration, etc.)

This is convenient for **Step 17 (caption fallback)** — we capture the metadata for free during the download and don't need a second yt-dlp call. (See the Steps 16-18 doc for how that metadata is used.)

### Error handling: the retryable/non-retryable distinction

This is the most important design choice in the file:

```python
class DownloadError(Exception):
    def __init__(self, message: str, *, is_retryable: bool = False):
        super().__init__(message)
        self.is_retryable = is_retryable
```

We define our own exception class with an `is_retryable` flag, and we map yt-dlp's many possible errors to one or the other:

| Original error | Mapped to | Why |
|---|---|---|
| `GeoRestrictionError` | non-retryable | The reel is blocked in our server's region. Retrying from the same server won't help. |
| `ExtractorError` containing "private" / "login" / "unavailable" | non-retryable | The reel is private, deleted, or removed. Permanent state. |
| `ExtractorError` (other) | non-retryable | Instagram changed their HTML and yt-dlp can't parse anymore. Won't fix until yt-dlp is updated. |
| `DownloadError` containing "private" / "login" / "deleted" | non-retryable | Same as above |
| `DownloadError` (other, generic) | **retryable** | Likely network timeout or transient 5xx. Worth retrying. |
| `Exception` (anything else) | retryable | Conservative — assume unknown errors might be transient. |

The Celery task uses this flag to decide whether to call `self.retry()`:

```python
if exc.is_retryable and self.request.retries < self.max_retries:
    raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))
supabase.table("reels").update({"status": "failed"}).eq("id", reel_id).execute()
```

Retries are scheduled with linear backoff: 60 s, 120 s, 180 s. We don't use exponential because the per-task time limit is 600 s and we want to fit three retries inside that budget for transient failures.

**Without this distinction, every failure would burn three retries before giving up** — including private reels that would never succeed. That's wasted compute and a slow user experience (a 3-minute wait before the user sees "this reel is private"). With the distinction, private/deleted reels fail in ~5 seconds and the user sees the failure status immediately.

### What gets returned

```python
@dataclass
class DownloadResult:
    audio_path: str
    metadata: ReelMetadata
```

A path to the mp3 and a `ReelMetadata` struct containing `caption`, `hashtags`, `creator_handle`, `thumbnail_url`, `duration_seconds`. The metadata feeds Step 17; the audio path feeds Step 16.

---

## Step 15 inside `process_reel` — How It's Called

Look at [`backend/workers/tasks.py`](../backend/workers/tasks.py). Stripped to just the Step 15 parts:

```python
@celery_app.task(bind=True, max_retries=3)
def process_reel(self, reel_id: str) -> dict:
    supabase = get_supabase()

    # Mark as processing so the iOS app can show a spinner
    supabase.table("reels").update({
        "status": "processing",
        "retry_count": self.request.retries,
    }).eq("id", reel_id).execute()

    # Fetch URL
    row = supabase.table("reels").select("url, user_id").eq("id", reel_id).single().execute()
    url = row.data["url"]

    # Step 15
    try:
        result = download_reel_audio(url, reel_id)
    except DownloadError as exc:
        if exc.is_retryable and self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))
        supabase.table("reels").update({"status": "failed"}).eq("id", reel_id).execute()
        return {"reel_id": reel_id, "status": "failed", "error": str(exc)}

    # Persist metadata (caption, creator, thumbnail) immediately
    supabase.table("reels").update({
        "caption": result.metadata.caption,
        "hashtags": result.metadata.hashtags,
        "creator_handle": result.metadata.creator_handle,
        "thumbnail_url": result.metadata.thumbnail_url,
    }).eq("id", reel_id).execute()

    # … Steps 16-22 follow …
```

**The order of operations matters:**

1. **Mark `status='processing'` first.** This gives the iOS app a signal that work has started — prevents the user from thinking nothing is happening.
2. **Fetch the URL second.** We don't trust the Celery argument blindly because the reel record is the source of truth, and a future feature might let users edit URLs before processing starts.
3. **Download third.**
4. **Persist metadata immediately after download.** Even if Step 16 (Whisper) fails next, the caption/creator/thumbnail are already saved. The user gets *some* data on their reel card rather than a blank.

This "save partial data as you go" pattern is repeated throughout the pipeline. It's a deliberate choice over the alternative ("run everything, save at the end, treat failures as all-or-nothing"). The reasoning:

- Pipelines have many failure modes. The longer the pipeline, the more likely at least one step fails.
- Users prefer a partially-populated reel to a fully-failed one.
- Re-running the pipeline from a partial state is cheaper than re-running from scratch — though we don't yet implement "resume from step N", the data is in place when we eventually want to.

---

## Cleanup: the `finally` block

```python
finally:
    if audio_path and os.path.exists(audio_path):
        try:
            os.remove(audio_path)
            parent = os.path.dirname(audio_path)
            if parent and not os.listdir(parent):
                os.rmdir(parent)
        except OSError as exc:
            logger.warning("Could not clean up audio file %s: %s", audio_path, exc)
```

The mp3 file is only useful for the duration of one Celery task — once Whisper has read it, we don't need it again. The `finally` block (covering the entire pipeline body) ensures we delete it whether the task succeeds, fails, or retries.

We also try to remove the parent temp directory if it's empty. `tempfile.mkdtemp()` creates a unique dir per call, so if we leak the dir (don't clean it up), `/tmp/` accumulates empty directories over time. Render's free tier has a small `/tmp/`, so this matters.

Errors during cleanup are logged but never raised — we don't want a transient permission issue on cleanup to mark a successful reel as failed.

---

## Render Deployment Notes

For the backend to actually receive POSTs on Render, the env vars in `render.yaml` must be set in the Render dashboard:

| Env var | Where to get it |
|---|---|
| `SUPABASE_URL` | Supabase dashboard → Project Settings → API |
| `SUPABASE_ANON_KEY` | Same |
| `SUPABASE_SERVICE_ROLE_KEY` | Same — under "Service Role Key" (keep secret!) |
| `OPENAI_API_KEY` | platform.openai.com → API Keys |
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys |
| `REDIS_URL` | The cloud Redis instance (Upstash or Render's add-on) |

`sync: false` in `render.yaml` means Render does **not** pull these from a synced source — they must be entered manually in the Render dashboard. The `sync: false` flag is the Render-recommended way to flag secret values.

The build command `apt-get install -y ffmpeg && pip install -r backend/requirements.txt` runs on every deploy. The first build is ~2 minutes; subsequent ones are ~30 s thanks to apt and pip caching.

---

## Edge Cases We Handle

| Scenario | Status code / behavior |
|---|---|
| Missing `Authorization` header | 422 (FastAPI auto-rejects) |
| Malformed `Authorization` header (no `Bearer ` prefix) | 401 (Supabase auth fails) |
| Expired/forged JWT | 401 |
| Valid JWT, user already saved this URL | 409 with existing reel info |
| Valid JWT, valid URL, valid user, healthy DB | 202 + `reel_id` |
| DB write succeeds but Celery dispatch fails (Redis down) | Reel is queued in DB but never processed; needs a sweeper (TODO) |
| Reel URL is private | Reel marked `failed` quickly (no retries) |
| Reel URL is region-blocked | Reel marked `failed` quickly (no retries) |
| Reel URL gives a network timeout | Retries up to 3× with linear backoff |
| ffmpeg is missing | Reel marked `failed` with diagnostic in logs |

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

Watch Terminal 3 (Celery) — you should see logs:
- `"Starting audio download for reel <id>"`
- `"Audio ready: /tmp/reelmind_xxx/<id>.mp3 (XXX KB)"`

Then look at the `reels` table in Supabase Studio:
- The row should have `status='processing'` (or further along if subsequent steps run)
- `caption`, `creator_handle`, `thumbnail_url` should be populated

---

## Key Design Decisions Summary

| Decision | What we chose | Why |
|---|---|---|
| Auth verification | `supabase.auth.get_user()` (network call) | Catches revoked sessions; no extra secret to store |
| Duplicate handling | Insert-then-catch unique violation | Race-condition-free; one round trip |
| Returning duplicate info | 409 with existing reel details | Lets clients render "you already saved this" |
| Async dispatch | Celery `.delay()` to Redis | Keeps the API endpoint sub-100ms |
| Argument passed to worker | `reel_id` only | Tiny payload, worker re-reads source of truth |
| Audio download library | yt-dlp | Most active, most reliable, ffmpeg integration |
| Audio format | mp3 @ 128 kbps | Whisper-friendly, small, good quality |
| Audio storage location | `tempfile.mkdtemp()` in `/tmp` | Ephemeral, auto-cleaned, no Supabase Storage costs |
| Error categorization | `is_retryable` flag on custom exception | Lets Celery retry network errors but skip permanent failures |
| Retry backoff | Linear: 60/120/180 s | Fits inside 600 s task time limit |
| Metadata persistence timing | Immediately after download, before transcription | Partial data > no data on failure |
| Cleanup strategy | `finally` block with logged-only failures | Prevents accumulated `/tmp` cruft |

---

## Cross-references

- **Step 11 (FCM)** — not yet done; needed for Step 22 (push notification on completion). Steps 14 & 15 do not depend on it.
- **Step 16 (Whisper)** — runs immediately after Step 15 in the same Celery task. Reads the audio file produced here.
- **Step 17 (caption fallback)** — uses the metadata captured during Step 15.
- **Step 18 (Claude classification)** — also runs in the same Celery task.
- **Step 19 (confidence routing)** — TODO. Will translate the classifier's `category` name into a `category_id` and update `reels.status` to `ready` or `uncategorised`.
- **Step 21 (duplicate URL detection)** — partially implemented here via the 409 response. The "show 'you already saved this on [date]' notification" UX is iOS-side work.

---

*ReelMind Phase 2 Knowledge Doc — Steps 14 & 15 — v1.0*
