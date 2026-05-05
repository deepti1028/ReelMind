# ReelMind — Phase 2 Steps 16, 17 & 18 Knowledge Document

### The AI Pipeline: From Audio to Categorised Reel

*Written so anyone can understand exactly how a downloaded mp3 is converted into structured data — a transcript, a category, a confidence score, and a 2-sentence summary — that drives everything else in the app.*

---

## The Big Picture

By the time these three steps run, a Celery worker already has:

- An mp3 file on disk (from Step 15)
- The reel's caption, hashtags, creator handle, and thumbnail URL (also from Step 15)
- A `reels` row in `status='processing'` (Step 14 set the status; Step 15 populated the metadata)

What we **don't** have yet:

- The spoken content of the reel (the transcript)
- Any sense of what the reel is *about* (category, summary)
- A confidence number to drive routing in Step 19

Steps 16-18 produce all three. They are the **first AI/LLM steps in the entire app**, and the foundation everything else builds on:

- The transcript feeds chunking + embedding (Step 20) and ultimately the chat/RAG layer (Steps 35+)
- The category drives library organisation (Steps 26-30)
- The summary appears as the 2-line description on the reel card (Step 27)
- The confidence score determines whether the reel auto-files itself or lands in the Uncategorised inbox (Step 19)

| Step | Job | Where it lives |
|---|---|---|
| **16 (AI)** | Transcribe audio with Whisper | [`backend/services/transcriber.py`](../backend/services/transcriber.py) |
| **17 (AI)** | Caption + hashtag extraction (fallback path) | Captured during Step 15 in [`backend/services/downloader.py`](../backend/services/downloader.py); used here as classifier input |
| **18 (AI)** | LLM classification with Claude | [`backend/services/classifier.py`](../backend/services/classifier.py) |

The three steps are wired together inside a single Celery task in [`backend/workers/tasks.py`](../backend/workers/tasks.py).

---

## File Inventory

```
backend/
├── services/
│   ├── transcriber.py    ← Step 16 (NEW)
│   ├── classifier.py     ← Step 18 (NEW)
│   └── downloader.py     ← already exists; Step 17 metadata extraction added in Step 15
├── workers/
│   └── tasks.py          ← orchestrates 15 → 16 → 17 → 18 in one task
├── config.py             ← ANTHROPIC_API_KEY added
└── .env.example          ← ANTHROPIC_API_KEY added

render.yaml               ← OPENAI_API_KEY, ANTHROPIC_API_KEY, REDIS_URL added to envVars
```

---

## Step 16 — Whisper Transcription

The implementation is intentionally minimal: a single function in [`backend/services/transcriber.py`](../backend/services/transcriber.py).

### Why Whisper specifically?

OpenAI's `whisper-1` model is the industry-standard speech-to-text API. Why we chose it over alternatives:

| Option | Pros | Cons |
|---|---|---|
| **OpenAI Whisper API** ✅ | Best-in-class accuracy across languages and accents, handles music + speech, no infra to run | Per-minute API cost (~$0.006/min) |
| Self-hosted Whisper (open-source weights) | No per-call cost | Need a GPU; cold starts; ops burden |
| Google Speech-to-Text | Good accuracy | Per-minute cost similar; more friction setting up |
| Assembly AI / Deepgram | Solid options | Yet another vendor to manage |

For our scale (a few hundred reels per active user per month), the API cost is negligible compared to the engineering cost of self-hosting. So: hosted Whisper.

### The implementation

```python
def transcribe_audio(audio_path: str) -> str:
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found at {audio_path}")

    client = _get_client()
    with path.open("rb") as f:
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
        )

    transcript = (response.text or "").strip()
    return transcript
```

A few intentional choices:

| Choice | Why |
|---|---|
| **Singleton OpenAI client** (`_get_client`) | OpenAI's SDK is thread-safe and reusable. Creating one per call wastes a TLS handshake per transcription. The lazy singleton means we only instantiate once per worker. |
| **No `response_format="text"`** | The default JSON response gives us `response.text` plus other fields (duration, language). We only use `.text` today, but the JSON form lets us add features (e.g., language detection) without changing the call. |
| **Strip and default to empty string** | Whisper occasionally returns `None` for completely silent audio. We normalize to `""` so callers can rely on always getting a string. |
| **`raise FileNotFoundError`** | Defensive — should never happen because `download_reel_audio` just produced this file, but if it does (e.g., a `/tmp` cleanup race), we want a clear error rather than a confusing OpenAI SDK exception. |
| **Errors not caught here** | The function lets OpenAI SDK exceptions propagate. The Celery task catches them broadly and degrades to caption-only classification (see "Best-effort policy" below). |

### What does Whisper return for a typical reel?

A 30-second skincare reel might return:

```
"Hey gorgeous, today I'm sharing my five-step morning routine for glass skin.
Step one: gentle cleanser — I love this one because it doesn't strip your moisture barrier..."
```

A 30-second music-only fashion reel returns:

```
""
```

A 30-second cooking reel where the creator just narrates briefly returns:

```
"Add the garlic. Let it sizzle for thirty seconds. Don't burn it."
```

These wildly different outputs are exactly why Step 17 exists.

### File size considerations

Whisper has a 25 MB upload limit. Our mp3s are encoded at 128 kbps:

- 30-second reel ≈ 480 KB
- 90-second reel (Instagram's max) ≈ 1.4 MB

We're nowhere near the limit. If Instagram ever extends reels beyond 90 s, we'd want to add a chunking pre-pass — but that's a non-issue today.

---

## Step 17 — Caption + Hashtag Fallback

This step is **not a separate function** — it's a design pattern. The work happens in two places:

1. **Capture** — during the yt-dlp download in Step 15, we extract caption, hashtags, creator, thumbnail. Already covered in the Steps 14-15 doc.
2. **Use** — when calling the classifier in Step 18, we always include caption + hashtags as input, regardless of whether Whisper produced a transcript.

### Why no dedicated "fallback" function?

The naive design would be:

```
if transcript is empty:
    classify_using_caption_only(caption, hashtags)
else:
    classify_using_transcript(transcript)
```

We did not do this. Instead:

```
classify_using_everything(transcript, caption, hashtags)  # transcript may be empty
```

Reasons:

1. **Even when Whisper produces a transcript, the caption + hashtags add signal.** A reel where someone says "this is so good" while the caption reads "BEST CHOCOLATE CAKE RECIPE EVER 🍰 #baking #dessert" — the caption is doing all the classifying work.
2. **One code path = fewer bugs.** Two parallel classification paths would each need their own prompt, tests, error handling. One path with optional inputs is simpler.
3. **Claude handles missing inputs gracefully.** When transcript is empty, our prompt says `"(no transcript — Whisper returned empty)"` and Claude weights caption + hashtags accordingly.

### Hashtag extraction details

In [`downloader.py`](../backend/services/downloader.py):

```python
_HASHTAG_RE = re.compile(r"#(\w+)")

def _extract_metadata(info: dict) -> ReelMetadata:
    caption = info.get("description") or info.get("title") or ""
    hashtags = _HASHTAG_RE.findall(caption)
    ...
```

A few notes:

- **`description` is the actual caption.** `yt-dlp` calls Instagram captions "description" because it generalises across YouTube, Twitter, TikTok, etc.
- **`title` is the fallback.** Some reels have no caption but yt-dlp synthesises a title from the URL or creator name.
- **`\w+` matches alphanumerics + underscore.** This intentionally excludes Instagram's full hashtag character set (which allows some Unicode), but the regex is good enough for English-language reels which dominate our user base. Adding Unicode support is trivial: `r"#([\wÀ-￿]+)"`.
- **The hashtags are stored as a Postgres `text[]`** — see the `hashtags text[] default '{}'` column in [`supabase/migrations/20260502000004_create_reels_table.sql`](../supabase/migrations/20260502000004_create_reels_table.sql). The Supabase Python client serialises Python lists to Postgres arrays automatically.

### What about `creator_handle` and `thumbnail_url`?

These are also captured in Step 17's metadata pass even though they're not used by the classifier. We persist them to the `reels` row for use by:

- **Reel cards in the iOS UI** (Step 27) — show the creator handle and thumbnail
- **Source attribution in chat responses** (Step 42) — "From your library: @skincareexpert"

Capturing them now means we don't need to re-call yt-dlp later when the iOS UI is built.

---

## Step 18 — Claude Classification

This is the most complex of the three steps. The whole file is in [`backend/services/classifier.py`](../backend/services/classifier.py); roughly 150 lines.

### The job, precisely stated

Given:
- A transcript (possibly empty)
- A caption (possibly empty)
- A list of hashtags (possibly empty)
- A list of category names available to *this user* (defaults + their custom ones)

Produce:
- One category from that list (or the literal string `"Uncategorised"`)
- A confidence score `0.0–1.0`
- A 2-sentence summary suitable for the reel card

### Why Claude and not OpenAI / Gemini / a small classifier model?

| Option | Why considered | Why we picked / didn't |
|---|---|---|
| **Claude (Sonnet 4.6)** ✅ | Strong instruction following, reliable JSON output, good safety on user-generated content | Picked |
| GPT-4 / GPT-4o | Equally capable | Already using OpenAI for Whisper + embeddings — diversifying providers reduces single-vendor risk |
| Gemini | Cost-competitive | One more vendor account to manage |
| Fine-tuned small model | Cheaper per call | Need labelled training data we don't have; can't easily handle user-created custom categories |
| Embedding + cosine similarity | Free | Loses the summary/confidence; categories without good embedding distinctions perform poorly |

The build plan says "send to Claude" — we agreed during Phase 1 that having two providers (OpenAI for vector ops, Anthropic for classification + chat synthesis) gives us redundancy without much overhead. If one provider has an outage, only half the pipeline breaks.

### Model choice: `claude-sonnet-4-6`

The `CLASSIFY_MODEL` constant. We use Sonnet 4.6 because:

- **Latency.** Sonnet responds in 1-3 seconds for our prompt size; Opus would be 3-6 s.
- **Cost.** Sonnet 4.6 is significantly cheaper per token than Opus, and our task doesn't need Opus's extra reasoning power.
- **JSON reliability.** Sonnet produces valid JSON >99% of the time when instructed clearly. Haiku is a touch less reliable on structured outputs.

Haiku 4.5 (`claude-haiku-4-5-20251001`) would also work and is cheaper still. We chose Sonnet for the safety margin on classification accuracy. **If cost becomes a concern, this is the first place to optimise** — switching to Haiku is a one-line change.

### The system prompt

```python
def _build_system_prompt(available_categories: list[str]) -> str:
    cats = "\n".join(f"  - {c}" for c in available_categories)
    return f"""You are the content classifier for ReelMind, an iOS app...

Your job is to read a reel's transcript and caption, then assign it to ONE category from this user's list:

{cats}

If no category fits with reasonable confidence, return "{UNCATEGORISED}".

Output rules:
  - Return ONLY a single JSON object — no preamble, no markdown fences, no commentary.
  - The object must match this exact schema:

    {{
      "category":   "<one of the categories above, or '{UNCATEGORISED}'>",
      "confidence": <float between 0.0 and 1.0>,
      "summary":    "<2-sentence plain-language summary describing what the reel is about>"
    }}

Confidence guide:
  >= 0.85   Very clear category fit (transcript explicitly about this topic)
  0.75-0.85 Clear fit (caption + hashtags strongly suggest it)
  0.60-0.75 Probable fit (some signals point this way)
  <  0.60   Unclear — prefer "{UNCATEGORISED}" over a low-confidence guess

If both transcript and caption are empty or uninformative, return "{UNCATEGORISED}" with confidence 0.0 and a generic summary.
"""
```

This prompt is the result of several deliberate choices:

#### Choice: explicit JSON schema in the prompt

We tell Claude the exact JSON shape we want, with field names and types. We do **not** rely on tool use / structured outputs / response format JSON mode. Reasons:

- Anthropic's tool-use API is more verbose and adds another moving part. For a single output schema, plain-text JSON instruction is simpler.
- Claude is reliable at producing valid JSON when the schema is in the system prompt. Defensive parsing (see below) catches the rare miss.
- Prompt-only JSON works across model versions; tool use sometimes requires SDK updates.

#### Choice: confidence bands, not a vague "give a confidence"

Without bands, models tend to default to 0.7-0.9 for everything ("seems pretty confident"). With bands, the model can no longer cluster everything in the high range — assigning 0.85 vs 0.75 means something specific.

The bands also align with the Step 19 threshold (`>= 0.75` auto-files, `< 0.75` goes to Uncategorised). We picked 0.75 because it's the natural break between "clear fit" and "probable fit" in our scheme — high enough to avoid bad auto-files, low enough that most reels do auto-file.

#### Choice: tell Claude to prefer "Uncategorised" for low confidence

This is an important safety. Without it, Claude would return its best guess at any confidence level. With it, Claude self-routes uncertain reels to Uncategorised, where the user can manually triage them. The cost of a wrong category (a reel about skincare ending up under Fitness) is much higher than the cost of an Uncategorised reel (one extra tap by the user).

#### Choice: include "no preamble, no markdown fences, no commentary"

LLMs love to wrap JSON in ```` ```json ... ``` ```` fences or add "Here's your classification:" preambles. Telling them not to helps, but doesn't fully prevent it — so we **also defend in parsing** (see below).

### The user message

```python
def _build_user_message(transcript: str, caption: str, hashtags: list[str]) -> str:
    transcript_block = transcript.strip() or "(no transcript — Whisper returned empty)"
    caption_block = caption.strip() or "(no caption)"
    hashtag_block = ", ".join(f"#{t}" for t in hashtags) if hashtags else "(none)"

    return f"""TRANSCRIPT:
{transcript_block}

CAPTION:
{caption_block}

HASHTAGS:
{hashtag_block}

Classify this reel. Return only the JSON object."""
```

Three labelled sections. The labels (`TRANSCRIPT:`, `CAPTION:`, `HASHTAGS:`) help Claude understand the structure without us having to spell out "the first paragraph is the transcript." The placeholder text `"(no transcript — Whisper returned empty)"` is more informative than just an empty string — it tells Claude *why* this section is empty, which improves classification when only the caption is available.

The closing `"Classify this reel. Return only the JSON object."` is a redundant nudge — the system prompt already says this, but repeating it at the end of the user message reduces the rate of accidental preambles.

### Defensive JSON parsing

```python
def _parse_response(raw: str) -> Classification:
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Could not parse classifier JSON; raw output: %s", raw[:300])
        return Classification(category=UNCATEGORISED, confidence=0.0, summary="")

    category = str(data.get("category") or UNCATEGORISED).strip()
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    summary = str(data.get("summary") or "").strip()

    return Classification(category=category, confidence=confidence, summary=summary)
```

Three layers of defense:

1. **Strip code fences** even though the prompt says not to use them. Claude rarely does, but "rarely" isn't "never," and the cost is one regex.
2. **`try/except json.JSONDecodeError`** with a graceful fallback to Uncategorised. We log the raw output (first 300 chars) so we can diagnose later.
3. **Per-field type coercion + clamping.** `confidence` is forced into `[0.0, 1.0]`; `category` and `summary` are cast to string and stripped. This handles model outputs like `confidence: "0.85"` (string instead of number) or `confidence: 1.5` (out of range — possible if Claude hallucinates).

### The "snap unknowns to Uncategorised" check

After parsing, we have a final guard:

```python
if result.category != UNCATEGORISED and result.category not in available_categories:
    logger.warning("Classifier returned unknown category %r — snapping to %s", ...)
    result = Classification(
        category=UNCATEGORISED,
        confidence=result.confidence,
        summary=result.summary,
    )
```

Even though we instruct Claude to only pick from the user's list, models sometimes invent plausible-sounding categories. Example: user has `Fitness`, model returns `Yoga`. Without this guard, we'd later try to look up the `Yoga` category by name in the database and get nothing.

By snapping to Uncategorised here, we guarantee that the rest of the pipeline only ever sees valid category names, and the user can manually create a `Yoga` category later if they want.

### The early-exit case

```python
if not (transcript.strip() or caption.strip() or hashtags):
    logger.info("Skipping classification — no transcript, caption, or hashtags")
    return Classification(category=UNCATEGORISED, confidence=0.0, summary="")
```

If we have absolutely zero signal — empty transcript, empty caption, no hashtags — we don't even bother calling Claude. The result will obviously be Uncategorised, and a no-op API call is wasted money and latency.

---

## Wiring It All Together: `process_reel`

The orchestration in [`backend/workers/tasks.py`](../backend/workers/tasks.py) follows a strict sequence with **distinct error policies per step**. Here's the conceptual flow:

```
┌─────────────────────────────────────────────────────────────┐
│ START: status='processing', retry_count=N                   │
└─────────────────┬───────────────────────────────────────────┘
                  ▼
   ┌──────────────────────────────────────────────────────┐
   │ Step 15: download_reel_audio(url)                    │
   │ → permanent failure: status='failed', return         │
   │ → retryable failure (and retries left): self.retry() │
   │ → success: have audio_path + metadata                │
   └──────────────────┬───────────────────────────────────┘
                      ▼
   ┌──────────────────────────────────────────────────────┐
   │ Persist metadata: caption, hashtags, creator, thumb  │
   │ (always — even if everything below fails)            │
   └──────────────────┬───────────────────────────────────┘
                      ▼
   ┌──────────────────────────────────────────────────────┐
   │ Step 16: transcribe_audio(audio_path)                │
   │ → exception → log + transcript = ""                  │
   │ → success → persist transcript                       │
   │ (NEVER fails the task — best-effort)                 │
   └──────────────────┬───────────────────────────────────┘
                      ▼
   ┌──────────────────────────────────────────────────────┐
   │ Step 17: caption fallback (no-op — already captured) │
   │ → just logs "no transcript" if relevant              │
   └──────────────────┬───────────────────────────────────┘
                      ▼
   ┌──────────────────────────────────────────────────────┐
   │ Fetch user's category list (defaults + custom)       │
   └──────────────────┬───────────────────────────────────┘
                      ▼
   ┌──────────────────────────────────────────────────────┐
   │ Step 18: classify_reel(transcript, caption, ...)     │
   │ → exception → log + Classification(Uncategorised)    │
   │ → success → persist confidence + summary             │
   │ (NEVER fails the task — best-effort)                 │
   └──────────────────┬───────────────────────────────────┘
                      ▼
   ┌──────────────────────────────────────────────────────┐
   │ FINALLY: delete temp audio file                      │
   │ Return {"status": "classified", "category": ...}     │
   └──────────────────────────────────────────────────────┘
```

### The two error policies

There are two distinct policies in play, and the difference matters:

| Step | Policy | Reason |
|---|---|---|
| **Step 15 (download)** | **Fail-fast** — failure marks reel `failed` and returns | Without audio, nothing else can work. There's no degraded mode. |
| **Step 16 (Whisper)** | **Best-effort** — failure → empty transcript, continue | Caption + hashtags can still produce a reasonable classification. Better partial than nothing. |
| **Step 18 (Claude)** | **Best-effort** — failure → Uncategorised, continue | The user can manually triage. Better Uncategorised than `failed`. |

This is a pragmatic choice. A "Whisper went down for 5 minutes" outage shouldn't fail every reel that hits the pipeline during that window — they should land in the user's library with a category derived from their captions. When Whisper recovers, the user's existing reels keep working; they just don't have a transcript (which only matters for the chat/RAG layer, Step 35+).

### The category fetch query

```python
cats_response = (
    supabase.table("categories")
    .select("name")
    .or_(f"user_id.eq.{user_id},is_default.eq.true")
    .execute()
)
available_categories = [c["name"] for c in (cats_response.data or [])]
```

This fetches the union of:

- The user's custom categories (`user_id = <this user>`)
- All default categories (`is_default = true`, `user_id = NULL`)

The `.or_()` syntax in supabase-py takes a comma-separated PostgREST filter string. Each clause is `column.operator.value`. So this expands to:

```sql
WHERE user_id = '<uid>' OR is_default = TRUE
```

Note: we use the service-role client, which bypasses RLS. The explicit filter is necessary because there's no `auth.uid()` to drive RLS in worker context.

The result is a list like `["Skincare", "Haircare", "Bodycare", "Fitness", "Nutrition", "Fashion", "Yoga"]` (six defaults + one custom). This list is passed verbatim into Claude's system prompt.

### What happens to the category name *after* classification?

The Celery task **only persists `summary` and `confidence`** here:

```python
supabase.table("reels").update({
    "summary": classification.summary,
    "confidence": classification.confidence,
}).eq("id", reel_id).execute()
```

**It does NOT update `category_id`.** That's deliberate:

- The classifier returns a category *name* (e.g., `"Skincare"`), not an *id*.
- Looking up the `category_id` from the name and applying the 0.75 threshold to decide auto-file vs Uncategorised is **Step 19's job** (confidence threshold routing).
- Keeping these concerns separate makes both pieces simpler and means Step 19 can be implemented and changed independently without touching the classifier.

We also don't update `status` here (it stays `'processing'` until Step 19 runs). This is a TODO documented in the code; for now, reels that complete Step 18 stay in `'processing'` indefinitely. The iOS app will need Step 19 to set `'ready'` or `'uncategorised'` before reels become visible in the library.

---

## Configuration: `ANTHROPIC_API_KEY`

Three places to set this:

### 1. Local development: `backend/.env`

Copy from `.env.example`:

```
ANTHROPIC_API_KEY=sk-ant-api03-...
```

Get a key from [console.anthropic.com](https://console.anthropic.com) → API Keys.

### 2. Backend code: `backend/config.py`

Already wired:

```python
# Anthropic (Claude classification — Step 18)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
```

The classifier uses `get_config().ANTHROPIC_API_KEY` at first-call time (lazy singleton). If the key is missing, the classifier raises `RuntimeError("ANTHROPIC_API_KEY is not configured")` rather than crashing the whole worker — Celery will catch the error, log it, mark the reel `failed`, and move on to the next task.

### 3. Render deployment: `render.yaml`

Already wired:

```yaml
- key: ANTHROPIC_API_KEY
  sync: false
```

`sync: false` means the value is set manually in the Render dashboard (not in the YAML). After deploying, go to:

```
Render → reelmind-api service → Environment → Add Environment Variable
```

…and paste your real key. Then redeploy (or Render will auto-redeploy on the next push).

We also added `OPENAI_API_KEY` and `REDIS_URL` to `render.yaml` at the same time — they were missing before, which would have been a silent break in production once Steps 16-18 ran.

---

## A Note on Prompt Caching

Anthropic supports **prompt caching** — letting you mark a stable prefix of your prompt (e.g., system instructions + few-shot examples) so subsequent calls reading the same prefix pay 10% of the input cost.

We **deliberately did not enable prompt caching here**. Reasons:

- **Minimum prefix size for Sonnet caching is 1024 tokens.** Our system prompt + category list is well under that — typically 300-500 tokens. Caching would silently no-op.
- **The cacheable portion (system prompt + category list) is per-user** — different users have different category lists. Cache hit rates would be low unless a single user saved many reels in a 5-minute TTL window.
- **The user-message portion (transcript + caption) is per-reel** — never cacheable.

If we ever expand the system prompt with extensive few-shot examples (pushing it past 1024 tokens), revisit this decision. There's a TODO comment in [`classifier.py`](../backend/services/classifier.py) explaining the rationale so future-you doesn't have to re-derive it.

---

## Edge Cases We Handle

| Scenario | Behavior |
|---|---|
| Whisper API down | Transcript = `""`, classification proceeds with caption only |
| Whisper returns empty (music-only reel) | Same as above — caption fallback handles it |
| Reel has no caption AND no transcript AND no hashtags | Classifier early-exits to Uncategorised (no API call) |
| Anthropic API down | Reel marked classified=Uncategorised, confidence=0.0 |
| Anthropic API key missing | Same as above (logged as error) |
| Claude returns malformed JSON | Falls back to Uncategorised, raw output logged for diagnosis |
| Claude invents a category not in the list | Snapped to Uncategorised |
| Claude returns `confidence: 1.5` | Clamped to 1.0 |
| Claude returns `confidence: "0.85"` (string) | Coerced to float |
| User has zero custom categories | Defaults still work — categories list always has the 6 defaults |
| Audio file deleted before Whisper runs | `FileNotFoundError` raised, caught by best-effort handler, transcript = `""` |
| Reel transcript is in a non-English language | Whisper handles 50+ languages; Claude handles all major languages — works as-is |

---

## What's NOT Done Here

These are explicitly **not** part of Steps 16-18 and live in later steps:

- **Step 19 (confidence threshold routing).** The classifier returns a category *name*; Step 19 will resolve it to a `category_id`, apply the 0.75 threshold, and update `reels.status` to `'ready'` or `'uncategorised'`. Without Step 19, all classified reels stay in `'processing'`.
- **Step 20 (chunk + embed transcript).** The transcript is stored on the reel row but not yet split into chunks or embedded. Until Step 20, the chat/RAG layer (Steps 35+) has nothing to retrieve.
- **Step 22 (FCM push notification).** The completion push happens after Step 19 has decided the final category. We've left the TODO in `process_reel` exactly where it goes.
- **Auto-creating user categories from notification reply (Step 24).** The classifier is allowed to return any category name, but only existing names are honored. If the user wants a `Yoga` category, they create it via the iOS UI (Step 32) — not via the classifier inventing it.
- **Multi-language considerations.** Whisper auto-detects language; Claude handles non-English fine. But our category names are in English. A reel in Hindi about skincare will likely classify correctly, but the summary will probably come back in English (Claude's default) unless we adjust the prompt. This is acceptable for v1.

---

## How to Verify This Code Works

End-to-end smoke test:

```bash
# 1. Make sure ffmpeg is installed locally
ffmpeg -version  # macOS: brew install ffmpeg

# 2. Set both API keys in backend/.env
echo "OPENAI_API_KEY=sk-..." >> backend/.env
echo "ANTHROPIC_API_KEY=sk-ant-..." >> backend/.env

# 3. Start Redis
docker run -p 6379:6379 redis

# 4. Start a Celery worker
cd backend && celery -A workers.celery_app worker --loglevel=info

# 5. From another shell, dispatch a task directly (skip the API for this test)
cd backend && python -c "
from workers.tasks import process_reel
# Use a real reel ID from your Supabase reels table:
result = process_reel.apply_async(args=['<reel_id>'])
print(result.get(timeout=120))
"
```

Watch the Celery logs:

```
Starting audio download for reel <id>
Audio ready: /tmp/reelmind_xxx/<id>.mp3 (487 KB), creator=@example, 5 hashtags
Transcribing <id>.mp3 (0.48 MB) with Whisper
Whisper produced 412 chars of transcript
Calling Claude classifier (transcript=412 chars, caption=89 chars, 5 hashtags, 7 categories)
Classified as 'Skincare' (confidence=0.92)
Step 15 complete — audio at /tmp/...
```

Then check Supabase Studio:

```sql
SELECT id, status, transcript, caption, hashtags, creator_handle,
       summary, confidence, retry_count
FROM reels
WHERE id = '<reel_id>';
```

You should see all the AI-derived fields populated. The `status` will still be `'processing'` (Step 19 hasn't run yet) — that's expected.

---

## Cost Estimate (Per Reel)

For a typical 30-second reel:

| Service | Quantity | Cost |
|---|---|---|
| Whisper (transcription) | ~0.5 min | $0.003 |
| Claude Sonnet 4.6 (classification) | ~1 K input, ~150 output tokens | $0.0035 |
| **Total** | | **~$0.006** |

That's about **$6 per 1,000 reels classified.** For a user saving 30 reels/day = ~$0.18/day = ~$5/month per active user. Comfortably below the price point of any paid app tier.

The biggest cost driver is Claude. If we ever need to optimise:
1. Switch to Haiku 4.5 (~5x cheaper, slight accuracy hit)
2. Enable prompt caching once the prompt grows past 1024 tokens
3. Skip Claude for reels with very high signal (e.g., a reel with `#skincare` hashtag and a Skincare-named creator could rule-based classify)

---

## Key Design Decisions Summary

| Decision | What we chose | Why |
|---|---|---|
| Transcription provider | OpenAI Whisper API | Best accuracy, no infra |
| Audio format passed to Whisper | mp3 @ 128 kbps | Whisper-friendly, well under size limit |
| Caption capture timing | During Step 15 (yt-dlp metadata) | Free side-effect of the download we already do |
| Hashtag extraction method | Regex `#(\w+)` over caption | Cheap and good enough for English |
| Fallback architecture | Single classifier path with optional inputs | Fewer code paths, fewer bugs |
| Classification provider | Anthropic Claude | Provider redundancy with OpenAI; strong instruction following |
| Classification model | `claude-sonnet-4-6` | Latency/cost/accuracy sweet spot |
| Output format | JSON via prompt instructions (not tool use) | Simpler, version-stable |
| Confidence bands | Defined in prompt with explicit thresholds | Forces meaningful confidence numbers |
| Low-confidence handling | Prompt instructs prefer Uncategorised | Avoids miscategorised auto-files |
| Defensive parsing | Strip fences, type-coerce, clamp, snap-unknowns | Three layers of guard against bad model output |
| Step 16 / 18 error policy | Best-effort (continue on failure) | Partial data > full failure; outages don't poison the pipeline |
| Step 15 error policy | Fail-fast | Without audio, nothing else can work |
| Where category_id is set | Step 19 (TODO), not here | Separation of concerns: classify ≠ route |
| Prompt caching | Not enabled (yet) | Prefix below the 1024-token minimum |
| API keys | Lazy singleton clients | One TLS handshake per worker, not per task |

---

## Cross-references

- **Steps 14-15** — produce the inputs to these steps (audio file + metadata). See `PHASE2_STEPS_14_15_KNOWLEDGE.md`.
- **Step 19 (confidence routing)** — TODO. Reads `summary` and `confidence` (set here), looks up `category_id` from name, sets final `status`.
- **Step 20 (chunk + embed)** — TODO. Reads the `transcript` (set here), splits into ~200-token chunks, calls `text-embedding-3-small`, stores vectors in `reel_chunks`.
- **Step 22 (FCM push)** — TODO. Fires "Saved to {category} - tap to reassign" using the category resolved by Step 19.
- **Step 35 (RAG retrieval)** — Phase 4. Queries the embeddings produced by Step 20.

---

*ReelMind Phase 2 Knowledge Doc — Steps 16, 17 & 18 — v1.0*
