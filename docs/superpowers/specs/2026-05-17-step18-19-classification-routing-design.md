# Steps 18+19 — Classification & Confidence Routing Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Step 18 (Groq Llama 3.3 70B classification) and Step 19 (confidence routing) of the ingestion pipeline. A reel with sufficient signal is classified into one of the user's categories; low-confidence reels enter a `pending_category` state awaiting user input via FCM action buttons (Step 22); unresponded reels expire to `uncategorised` after 1 hour.

**Architecture:** New `services/classifier.py` follows the existing service module pattern (same as `transcriber.py`, `signal_builder.py`). It is a pure function — no I/O beyond the Groq API call. `workers/tasks.py` gains Steps 18+19 blocks. A new `workers/beat_tasks.py` handles the 1-hour timeout. A new `PATCH /api/v1/reels/{reel_id}/category` endpoint handles the user's FCM button tap response. One DB migration adds `suggested_categories text[]` to reels.

**Tech Stack:** Groq Python SDK (`groq`), `llama-3.3-70b-versatile`, `temperature=0`, `response_format={"type": "json_object"}`. No new dependencies beyond the existing Groq SDK already used by the transcriber.

**Free tier constraint:** Groq free tier — ~14k tokens/min on Llama. Classification prompt is small (~500 tokens). Well within limits for development.

---

## Files

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/services/classifier.py` | `ClassificationResult`, `ClassificationError`, `classify_reel()` |
| Create | `backend/workers/beat_tasks.py` | Celery Beat task — expire `pending_category` reels after 1 hr |
| Create | `backend/tests/test_classifier.py` | Unit tests for classifier (mocked Groq) |
| Create | `backend/tests/test_beat_tasks.py` | Unit tests for timeout task (mocked Supabase) |
| Modify | `backend/workers/tasks.py` | Add Steps 18+19 blocks |
| Modify | `backend/workers/celery_app.py` | Register Beat schedule |
| Modify | `backend/api/v1/reels.py` | Add `PATCH /{reel_id}/category` endpoint |
| Create | `supabase/migrations/20260517000001_add_suggested_categories_to_reels.sql` | Add `suggested_categories text[]` column |

---

## Data Model

### `ClassificationResult`

```python
@dataclass
class ClassificationResult:
    category: str           # exact name from the list given to Llama (mapped from category_id)
    confidence: float       # 0.0–1.0
    alternatives: list[str] # up to 2 other plausible category names, best first
```

### `ClassificationError`

```python
class ClassificationError(Exception):
    def __init__(self, message: str, is_retryable: bool = True):
        super().__init__(message)
        self.is_retryable = is_retryable
```

### DB migration — `suggested_categories`

```sql
ALTER TABLE public.reels
ADD COLUMN IF NOT EXISTS suggested_categories text[] DEFAULT '{}';
```

Stores the category names offered to the user in the FCM notification. Used by the timeout task (to know what was suggested) and cleared on resolution.

---

## Reel Status Flow

```
queued → processing → ready                        (≥70% confidence, auto-assigned)
queued → processing → pending_category → ready     (user picks via FCM button tap)
                              └──────── → uncategorised  (1hr timeout, no response)
queued → processing → uncategorised               (Step 17 gate: no signal)
queued → processing → failed                      (unrecoverable errors)
```

---

## `services/classifier.py`

### Function signature

```python
def classify_reel(
    transcript: str | None,
    caption: str | None,
    hashtags: list[str],
    categories: list[str],  # exact names fetched from DB for this user
) -> ClassificationResult:
```

### Category ID mapping

To eliminate spelling drift and casing bugs, Llama works with sequential integer IDs, not raw strings:

```python
id_to_name: dict[int, str] = {i + 1: name for i, name in enumerate(categories)}
name_to_id: dict[str, int] = {name: i for i, name in id_to_name.items()}
category_list_str = "\n".join(f"{cid}: {name}" for cid, name in id_to_name.items())
```

Llama returns `{"category_id": 2, ...}`. We map back with `id_to_name[2]`.

### Prompt

```
System:
You are a content classifier for a personal content library app.
Classify the reel into EXACTLY ONE category from the provided list.

Use the overall semantic meaning of the content.
Do NOT classify based only on hashtags if the transcript/caption suggests otherwise.

Categories:
{category_list_str}

Return ONLY valid JSON with exactly this schema:
{
  "category_id": <integer from the list above>,
  "confidence": <float 0.0 to 1.0>,
  "alternative_ids": [<integer>, <integer>]
}

Rules:
- category_id must be one of the integers listed
- confidence: 0.9–1.0 = very certain | 0.7–0.89 = strong match | 0.4–0.69 = weak/ambiguous | 0.0–0.39 = mostly guesswork
- alternative_ids: 0–2 other plausible category IDs, best first. Must not include category_id.
- Always return a single best guess — never refuse to classify, never invent IDs
- Never return markdown

User:
Transcript:
{transcript or "(none)"}

Caption:
{caption or "(none)"}

Hashtags:
{" ".join(f"#{t}" for t in hashtags) or "(none)"}
```

### Groq call parameters

```python
response = groq_client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "system", "content": system_prompt},
              {"role": "user", "content": user_message}],
    temperature=0,
    response_format={"type": "json_object"},
)
```

### Validation (after JSON parse)

```python
assert category_id in id_to_name                             # valid ID
assert 0.0 <= confidence <= 1.0                              # valid range
assert all(a in id_to_name for a in alternative_ids)        # valid IDs
assert category_id not in alternative_ids                    # no overlap
```

Any assertion failure → `ClassificationError(is_retryable=False)`.

### Error handling

| Error | Retryable? | Notes |
|-------|-----------|-------|
| Groq 429 rate limit | Yes | Backoff via existing `_handle_pipeline_error` |
| Groq 5xx server error | Yes | Backoff |
| Groq 400 bad request | No | Prompt or payload error |
| JSON parse failure (first) | **Yes — once** | Transient truncation or streaming cutoff |
| JSON parse failure (second) | No | Persistent model issue |
| Validation failure | No | Model returned structurally invalid data |

JSON-parse-once retry is tracked via a local flag inside `classify_reel`, not a Celery retry — it's an internal implementation detail of the function.

---

## Steps 18+19 in `workers/tasks.py`

After Step 17 builds `signal` and `_transcript_text` is extracted:

```python
# ------------------------------------------------------------------
# Step 18 — fetch categories + call Llama classifier
# ------------------------------------------------------------------
log.info("step 18 | fetching categories for user=%s", reel_data["user_id"])
rows = supabase.table("categories").select("id, name").or_(
    f"user_id.eq.{reel_data['user_id']},user_id.is.null"
).execute()
category_db_map = {row["name"]: row["id"] for row in rows.data}  # name → db UUID
category_names = list(category_db_map.keys())

log.info("step 18 | classifying | categories=%d", len(category_names))
try:
    classification = classify_reel(
        transcript=_transcript_text,
        caption=meta.caption,
        hashtags=meta.hashtags,
        categories=category_names,
    )
    log.info(
        "step 18 | classification done | category=%s | confidence=%.2f | alternatives=%s",
        classification.category,
        classification.confidence,
        classification.alternatives,
    )
except ClassificationError as exc:
    log.warning("step 18 | classification error | retryable=%s | %s", exc.is_retryable, exc)
    return _handle_pipeline_error(self, supabase, reel_id, exc, exc.is_retryable, log)

# ------------------------------------------------------------------
# Step 19 — confidence routing
# ------------------------------------------------------------------
CONFIDENCE_THRESHOLD = 0.70  # configurable — move to config.py if needed

if classification.confidence >= CONFIDENCE_THRESHOLD:
    log.info("step 19 | auto-assigning | confidence=%.2f >= %.2f", classification.confidence, CONFIDENCE_THRESHOLD)
    supabase.table("reels").update({
        "category_id": category_db_map[classification.category],
        "confidence": classification.confidence,
        "status": "ready",
    }).eq("id", reel_id).execute()
    # TODO Step 22: FCM push — "Your reel has been saved and categorised!"
    log.info("step 19 | status=ready")
    return {"reel_id": reel_id, "status": "ready", "category": classification.category}

else:
    suggestions = [classification.category] + classification.alternatives[:2]
    log.info(
        "step 19 | low confidence=%.2f — pending_category | suggestions=%s",
        classification.confidence,
        suggestions,
    )
    supabase.table("reels").update({
        "status": "pending_category",
        "suggested_categories": suggestions,
        "confidence": classification.confidence,
    }).eq("id", reel_id).execute()
    # TODO Step 22: FCM push — notification with buttons:
    #   [suggestion1] [suggestion2] [Choose in App] [Uncategorised]
    #   Body: "Your reel is saved — help us categorise it!"
    log.info("step 19 | status=pending_category")
    return {"reel_id": reel_id, "status": "pending_category", "suggestions": suggestions}
```

Import additions to `tasks.py`:
```python
from services.classifier import ClassificationError, ClassificationResult, classify_reel
```

---

## `PATCH /api/v1/reels/{reel_id}/category`

Called by the iOS app when user taps a category button in the FCM notification.

**Request body:**
```json
{"category_name": "Fitness"}   // or null to skip to uncategorised (tapping "Uncategorised" button)
```

**Two paths based on `category_name`:**

**Path A — user picked a category (`category_name` is a string):**
1. Auth via `deps.py` (existing `get_current_user`)
2. Fetch reel — verify `user_id` matches, verify `status == "pending_category"` (idempotency guard)
3. Look up `category_id` from user's categories (default + user-created) by `category_name`
4. Update reel:
   ```python
   {"category_id": <uuid>, "confidence": 1.0, "status": "ready", "suggested_categories": []}
   ```
5. Return `200 {"reel_id": "...", "status": "ready", "category": "Fitness"}`
6. TODO Step 22: FCM push — "Reel categorised!"

**Path B — user tapped "Uncategorised" (`category_name` is null):**
1. Auth + reel ownership check (same as Path A)
2. Update reel:
   ```python
   {"status": "uncategorised", "suggested_categories": []}
   ```
3. Return `200 {"reel_id": "...", "status": "uncategorised"}`
4. TODO Step 22: FCM push — "Saved to Uncategorised — you can move it anytime"

**Error cases:**
- Reel not found or not owned by user → 404
- `status != "pending_category"` → 409 (already resolved — idempotent, return current status)
- `category_name` (string) not in user's categories → 422

---

## `workers/beat_tasks.py` — Timeout Task

```python
"""Celery Beat periodic tasks."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from supabase_client import get_supabase
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

PENDING_CATEGORY_TIMEOUT_HOURS = 1


@celery_app.task(name="workers.beat_tasks.expire_pending_categories")
def expire_pending_categories() -> dict:
    """Move pending_category reels older than 1 hour to uncategorised."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=PENDING_CATEGORY_TIMEOUT_HOURS)
    supabase = get_supabase()

    stale = (
        supabase.table("reels")
        .select("id, user_id")
        .eq("status", "pending_category")
        .lt("updated_at", cutoff.isoformat())
        .execute()
    )

    expired = []
    for row in stale.data:
        supabase.table("reels").update({
            "status": "uncategorised",
            "suggested_categories": [],
        }).eq("id", row["id"]).execute()
        # TODO Step 22: FCM push — "Saved to Uncategorised — you can move it anytime"
        logger.info("beat | expired pending_category | reel_id=%s", row["id"])
        expired.append(row["id"])

    logger.info("beat | expire_pending_categories done | expired=%d", len(expired))
    return {"expired": len(expired), "reel_ids": expired}
```

### Beat schedule in `celery_app.py`

```python
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    "expire-pending-categories": {
        "task": "workers.beat_tasks.expire_pending_categories",
        "schedule": 30 * 60,  # every 30 minutes
    },
}
```

To run the Beat scheduler in dev:
```bash
celery -A workers.celery_app beat --loglevel=info
```

---

## Testing Strategy

### `tests/test_classifier.py` (mock Groq)

| Test | What it verifies |
|------|-----------------|
| `test_happy_path_high_confidence` | Valid JSON → `ClassificationResult` with correct field mapping |
| `test_category_id_mapped_to_name` | Integer `category_id` correctly maps to category name |
| `test_alternatives_mapped` | `alternative_ids` map to correct names |
| `test_json_parse_failure_retried_once` | First bad JSON → retries; second bad JSON → `ClassificationError(is_retryable=False)` |
| `test_invalid_category_id_raises` | `category_id` not in map → `ClassificationError(is_retryable=False)` |
| `test_confidence_out_of_range_raises` | `confidence > 1.0` → `ClassificationError(is_retryable=False)` |
| `test_category_in_alternatives_raises` | `category_id` in `alternative_ids` → `ClassificationError(is_retryable=False)` |
| `test_groq_429_is_retryable` | HTTP 429 → `ClassificationError(is_retryable=True)` |
| `test_groq_400_not_retryable` | HTTP 400 → `ClassificationError(is_retryable=False)` |
| `test_temperature_is_zero` | Groq call uses `temperature=0` |

### `tests/test_beat_tasks.py` (mock Supabase)

| Test | What it verifies |
|------|-----------------|
| `test_stale_reels_transitioned` | Reels older than 1hr in `pending_category` → `uncategorised` |
| `test_fresh_reels_not_touched` | Reels younger than 1hr → unchanged |
| `test_returns_count_and_ids` | Return dict includes `expired` count and `reel_ids` list |

---

## Step 22 FCM Backlog (forward reference)

The following `# TODO Step 22` markers are left in the code for Step 22 implementation:

| Location | Trigger | FCM message |
|----------|---------|-------------|
| `tasks.py` Step 19 (ready) | `status = "ready"` | "Your reel has been saved and categorised!" |
| `tasks.py` Step 19 (pending) | `status = "pending_category"` | "Help us categorise your reel!" + 4 action buttons |
| `api/v1/reels.py` PATCH | User picks category | "Reel categorised!" |
| `beat_tasks.py` | Timeout expiry | "Saved to Uncategorised — you can move it anytime" |
| `tasks.py` Step 17 | `status = "uncategorised"` | "We couldn't categorise your reel — no text or audio found." |

FCM notification buttons for `pending_category` (iOS, max 4 actions):
- `[suggestion1]` — background action, calls `PATCH /category`
- `[suggestion2]` — background action, calls `PATCH /category`
- `[Choose in App]` — foreground action, opens ReelMind categorise/create-category flow
- `[Uncategorised]` — background action, calls `PATCH /category` with `category_name = null` → skips to `uncategorised` immediately

Notification body: *"Your reel is saved — help us categorise it! Ignoring this will save it to Uncategorised."*
