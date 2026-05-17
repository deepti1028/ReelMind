# Steps 18+19 — Classification & Confidence Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Step 18 (Groq Llama 3.3 70B reel classification) and Step 19 (confidence routing) — classifying reels into user categories, routing high-confidence results to `ready` and low-confidence to `pending_category`, with a 1-hour Celery Beat timeout and a user-response API endpoint.

**Architecture:** New `services/classifier.py` (pure function, Groq call) following the same pattern as `transcriber.py` and `signal_builder.py`. `workers/tasks.py` gains Steps 18+19 blocks after Step 17. New `workers/beat_tasks.py` scans every 30 minutes for stale `pending_category` reels. New `PATCH /api/v1/reels/{reel_id}/category` endpoint handles FCM button tap responses.

**Tech Stack:** Groq Python SDK (already in `requirements.txt`), `llama-3.3-70b-versatile`, `temperature=0`, `response_format={"type": "json_object"}`. No new dependencies.

**Context:**
- All commands run from `backend/` with `source venv/bin/activate`
- Tests: `pytest tests/ -v`
- Spec: `docs/superpowers/specs/2026-05-17-step18-19-classification-routing-design.md`
- The `conftest.py` already adds `backend/` to `sys.path` — no path setup needed in test files

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `supabase/migrations/20260517000001_add_suggested_categories_to_reels.sql` | Add `suggested_categories text[]` column |
| Create | `backend/services/classifier.py` | `ClassificationResult`, `ClassificationError`, `classify_reel()` |
| Create | `backend/tests/test_classifier.py` | 10 unit tests for the classifier (mocked Groq) |
| Create | `backend/workers/beat_tasks.py` | `expire_pending_categories` Celery Beat task |
| Create | `backend/tests/test_beat_tasks.py` | 3 unit tests for the timeout task |
| Modify | `backend/workers/celery_app.py` | Register Beat schedule (every 30 min) |
| Modify | `backend/workers/tasks.py` | Add Steps 18+19 blocks + FCM token fetch |
| Modify | `backend/tests/test_tasks_resilience.py` | Add 4 Step 18+19 routing tests |
| Modify | `backend/schemas/reel.py` | Add `CategoryChoiceRequest` Pydantic model |
| Modify | `backend/api/v1/reels.py` | Add `PATCH /{reel_id}/category` endpoint |
| Create | `backend/tests/test_category_endpoint.py` | 5 endpoint tests |

---

## Task 1: DB Migration — add `suggested_categories` column

**Files:**
- Create: `supabase/migrations/20260517000001_add_suggested_categories_to_reels.sql`

- [ ] **Step 1: Write the migration**

```sql
-- Add suggested_categories to reels for pending_category FCM flow (Step 22)
-- Stores the category names shown to the user as FCM notification buttons.
ALTER TABLE public.reels
ADD COLUMN IF NOT EXISTS suggested_categories text[] DEFAULT '{}';
```

Save to `supabase/migrations/20260517000001_add_suggested_categories_to_reels.sql`.

- [ ] **Step 2: Apply the migration**

```bash
cd /path/to/ReelMind && supabase db push
```

Expected: migration applied successfully, no errors.

- [ ] **Step 3: Commit**

```bash
git add supabase/migrations/20260517000001_add_suggested_categories_to_reels.sql
git commit -m "feat: add suggested_categories column to reels for pending_category flow"
```

---

## Task 2: Write classifier tests (red phase)

**Files:**
- Create: `backend/tests/test_classifier.py`

- [ ] **Step 1: Create the test file**

```python
"""Tests for services.classifier — Step 18 Groq Llama classification."""
from unittest.mock import MagicMock, patch
import json
import pytest

CATEGORIES = ["Skincare", "Haircare", "Fitness", "Nutrition"]


def _make_groq_response(category_id: int, confidence: float, alternative_ids: list[int]):
    """Build a mock Groq chat completion response."""
    content = json.dumps({
        "category_id": category_id,
        "confidence": confidence,
        "alternative_ids": alternative_ids,
    })
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_bad_json_response():
    msg = MagicMock()
    msg.content = "not valid json {{{"
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------

@patch("services.classifier.Groq")
def test_happy_path_high_confidence(mock_groq_cls):
    mock_groq_cls.return_value.chat.completions.create.return_value = (
        _make_groq_response(3, 0.92, [4])
    )
    from services.classifier import classify_reel
    result = classify_reel("Great workout!", "Gym time!", ["fitness"], CATEGORIES)
    assert result.category == "Fitness"
    assert result.confidence == 0.92
    assert result.alternatives == ["Nutrition"]


@patch("services.classifier.Groq")
def test_category_id_mapped_to_name(mock_groq_cls):
    mock_groq_cls.return_value.chat.completions.create.return_value = (
        _make_groq_response(1, 0.85, [])
    )
    from services.classifier import classify_reel
    result = classify_reel(None, "Moisturiser review", [], CATEGORIES)
    assert result.category == "Skincare"
    assert result.alternatives == []


@patch("services.classifier.Groq")
def test_alternatives_mapped_to_names(mock_groq_cls):
    mock_groq_cls.return_value.chat.completions.create.return_value = (
        _make_groq_response(1, 0.75, [3, 4])
    )
    from services.classifier import classify_reel
    result = classify_reel("skin routine", None, [], CATEGORIES)
    assert result.alternatives == ["Fitness", "Nutrition"]


# ---------------------------------------------------------------------------
# JSON parse retry
# ---------------------------------------------------------------------------

@patch("services.classifier.Groq")
def test_json_parse_failure_retried_once(mock_groq_cls):
    good_resp = _make_groq_response(1, 0.9, [])
    mock_groq_cls.return_value.chat.completions.create.side_effect = [
        _make_bad_json_response(),
        good_resp,
    ]
    from services.classifier import classify_reel
    result = classify_reel(None, "Skincare routine", [], CATEGORIES)
    assert result.category == "Skincare"
    assert mock_groq_cls.return_value.chat.completions.create.call_count == 2


@patch("services.classifier.Groq")
def test_json_parse_failure_twice_raises_non_retryable(mock_groq_cls):
    mock_groq_cls.return_value.chat.completions.create.return_value = (
        _make_bad_json_response()
    )
    from services.classifier import classify_reel, ClassificationError
    with pytest.raises(ClassificationError) as exc_info:
        classify_reel(None, "caption", [], CATEGORIES)
    assert exc_info.value.is_retryable is False


# ---------------------------------------------------------------------------
# Validation failures
# ---------------------------------------------------------------------------

@patch("services.classifier.Groq")
def test_invalid_category_id_raises_non_retryable(mock_groq_cls):
    mock_groq_cls.return_value.chat.completions.create.return_value = (
        _make_groq_response(99, 0.9, [])
    )
    from services.classifier import classify_reel, ClassificationError
    with pytest.raises(ClassificationError) as exc_info:
        classify_reel(None, "caption", [], CATEGORIES)
    assert exc_info.value.is_retryable is False


@patch("services.classifier.Groq")
def test_confidence_out_of_range_raises_non_retryable(mock_groq_cls):
    mock_groq_cls.return_value.chat.completions.create.return_value = (
        _make_groq_response(1, 1.5, [])
    )
    from services.classifier import classify_reel, ClassificationError
    with pytest.raises(ClassificationError) as exc_info:
        classify_reel(None, "caption", [], CATEGORIES)
    assert exc_info.value.is_retryable is False


@patch("services.classifier.Groq")
def test_category_in_alternatives_raises_non_retryable(mock_groq_cls):
    mock_groq_cls.return_value.chat.completions.create.return_value = (
        _make_groq_response(1, 0.9, [1])  # category_id == alternative_id
    )
    from services.classifier import classify_reel, ClassificationError
    with pytest.raises(ClassificationError) as exc_info:
        classify_reel(None, "caption", [], CATEGORIES)
    assert exc_info.value.is_retryable is False


# ---------------------------------------------------------------------------
# Groq API errors
# ---------------------------------------------------------------------------

@patch("services.classifier.Groq")
def test_groq_429_is_retryable(mock_groq_cls):
    from groq import RateLimitError
    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_groq_cls.return_value.chat.completions.create.side_effect = RateLimitError(
        message="rate limit exceeded",
        response=mock_response,
        body={},
    )
    from services.classifier import classify_reel, ClassificationError
    with pytest.raises(ClassificationError) as exc_info:
        classify_reel(None, "caption", [], CATEGORIES)
    assert exc_info.value.is_retryable is True


@patch("services.classifier.Groq")
def test_groq_400_not_retryable(mock_groq_cls):
    from groq import APIStatusError
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_groq_cls.return_value.chat.completions.create.side_effect = APIStatusError(
        message="bad request",
        response=mock_response,
        body={},
    )
    from services.classifier import classify_reel, ClassificationError
    with pytest.raises(ClassificationError) as exc_info:
        classify_reel(None, "caption", [], CATEGORIES)
    assert exc_info.value.is_retryable is False


@patch("services.classifier.Groq")
def test_temperature_is_zero(mock_groq_cls):
    mock_groq_cls.return_value.chat.completions.create.return_value = (
        _make_groq_response(1, 0.9, [])
    )
    from services.classifier import classify_reel
    classify_reel(None, "caption", [], CATEGORIES)
    kwargs = mock_groq_cls.return_value.chat.completions.create.call_args.kwargs
    assert kwargs["temperature"] == 0
```

- [ ] **Step 2: Run tests — verify all fail with ImportError**

```bash
cd backend && source venv/bin/activate && pytest tests/test_classifier.py -v
```

Expected: All 10 tests FAIL with `ModuleNotFoundError: No module named 'services.classifier'`

- [ ] **Step 3: Commit the test file as spec**

```bash
git add backend/tests/test_classifier.py
git commit -m "test: add classifier tests (all failing — TDD red phase)"
```

---

## Task 3: Implement `services/classifier.py` (green phase)

**Files:**
- Create: `backend/services/classifier.py`

- [ ] **Step 1: Create the implementation**

```python
"""Reel content classifier — Step 18 of the ingestion pipeline.

Calls Groq Llama 3.3 70B to classify a reel's content signal into one of
the user's categories. Returns a ClassificationResult with the chosen
category name, confidence score, and up to 2 alternative categories.

Public surface:
    classify_reel(transcript, caption, hashtags, categories) -> ClassificationResult
    ClassificationResult, ClassificationError
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from groq import APIStatusError, Groq, RateLimitError

from config import get_config

logger = logging.getLogger(__name__)

_MODEL = "llama-3.3-70b-versatile"


@dataclass
class ClassificationResult:
    category: str           # exact name from the list given to Llama
    confidence: float       # 0.0–1.0
    alternatives: list[str] = field(default_factory=list)  # up to 2, best first


class ClassificationError(Exception):
    def __init__(self, message: str, is_retryable: bool = True) -> None:
        super().__init__(message)
        self.is_retryable = is_retryable


def classify_reel(
    transcript: str | None,
    caption: str | None,
    hashtags: list[str],
    categories: list[str],
) -> ClassificationResult:
    """Classify reel content into one of the provided categories via Groq Llama.

    Args:
        transcript: Raw transcript text from Step 16, or None.
        caption:    Caption text from Step 15, or None.
        hashtags:   List of hashtag strings from Step 15 (may be empty).
        categories: Exact category names from the DB for this user.

    Returns:
        ClassificationResult with category name, confidence, and alternatives.

    Raises:
        ClassificationError: On API failure, two consecutive JSON parse failures,
                            or schema validation failure. has .is_retryable flag.
    """
    # Map sequential IDs to category names to avoid spelling/casing issues.
    id_to_name: dict[int, str] = {i + 1: name for i, name in enumerate(categories)}
    category_list_str = "\n".join(f"{cid}: {name}" for cid, name in id_to_name.items())

    transcript_text = transcript or "(none)"
    caption_text = caption or "(none)"
    hashtag_text = " ".join(f"#{t}" for t in hashtags) if hashtags else "(none)"

    system_prompt = f"""You are a content classifier for a personal content library app.
Classify the reel into EXACTLY ONE category from the provided list.

Use the overall semantic meaning of the content.
Do NOT classify based only on hashtags if the transcript/caption suggests otherwise.

Categories:
{category_list_str}

Return ONLY valid JSON with exactly this schema:
{{
  "category_id": <integer from the list above>,
  "confidence": <float 0.0 to 1.0>,
  "alternative_ids": [<integer>, <integer>]
}}

Rules:
- category_id must be one of the integers listed
- confidence: 0.9-1.0 = very certain | 0.7-0.89 = strong match | 0.4-0.69 = weak/ambiguous | 0.0-0.39 = mostly guesswork
- alternative_ids: 0-2 other plausible category IDs, best first. Must not include category_id.
- Always return a single best guess — never refuse to classify, never invent IDs
- Never return markdown"""

    user_message = f"""Transcript:
{transcript_text}

Caption:
{caption_text}

Hashtags:
{hashtag_text}"""

    cfg = get_config()
    client = Groq(api_key=cfg.GROQ_API_KEY)

    parsed: dict | None = None
    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content
            parsed = json.loads(raw)
            break
        except RateLimitError as exc:
            raise ClassificationError(str(exc), is_retryable=True) from exc
        except APIStatusError as exc:
            retryable = exc.status_code >= 500
            raise ClassificationError(str(exc), is_retryable=retryable) from exc
        except json.JSONDecodeError:
            if attempt == 1:
                raise ClassificationError(
                    "JSON parse failed twice — persistent model formatting issue",
                    is_retryable=False,
                )
            logger.warning("classifier | JSON parse failed on attempt 1 — retrying")

    # Validate response schema
    try:
        category_id = int(parsed["category_id"])
        confidence = float(parsed["confidence"])
        alternative_ids = [int(a) for a in parsed.get("alternative_ids", [])]
    except (KeyError, TypeError, ValueError) as exc:
        raise ClassificationError(
            f"response missing required fields: {exc}", is_retryable=False
        ) from exc

    if category_id not in id_to_name:
        raise ClassificationError(
            f"category_id {category_id} not in valid range 1–{len(id_to_name)}",
            is_retryable=False,
        )
    if not (0.0 <= confidence <= 1.0):
        raise ClassificationError(
            f"confidence {confidence} out of [0.0, 1.0]", is_retryable=False
        )
    if any(a not in id_to_name for a in alternative_ids):
        raise ClassificationError(
            "alternative_ids contains invalid category ID", is_retryable=False
        )
    if category_id in alternative_ids:
        raise ClassificationError(
            "category_id must not appear in alternative_ids", is_retryable=False
        )

    logger.info(
        "classifier | category=%s | confidence=%.2f | alternatives=%s",
        id_to_name[category_id],
        confidence,
        [id_to_name[a] for a in alternative_ids],
    )

    return ClassificationResult(
        category=id_to_name[category_id],
        confidence=confidence,
        alternatives=[id_to_name[a] for a in alternative_ids],
    )
```

- [ ] **Step 2: Run the classifier tests — verify all 10 pass**

```bash
cd backend && source venv/bin/activate && pytest tests/test_classifier.py -v
```

Expected: `10 passed`

- [ ] **Step 3: Run the full test suite to check for regressions**

```bash
cd backend && source venv/bin/activate && pytest tests/ -v
```

Expected: All pre-existing tests still pass. Total count increases by 10.

- [ ] **Step 4: Commit**

```bash
git add backend/services/classifier.py
git commit -m "feat: add classifier service — Step 18 Groq Llama classification"
```

---

## Task 4: Write and implement `workers/beat_tasks.py`

**Files:**
- Create: `backend/tests/test_beat_tasks.py`
- Create: `backend/workers/beat_tasks.py`

- [ ] **Step 1: Write beat task tests (all failing)**

```python
"""Tests for workers.beat_tasks — pending_category timeout."""
from unittest.mock import MagicMock, patch
import pytest


def _make_supabase_mock(stale_rows: list[dict]):
    """Supabase mock returning stale_rows for the pending_category query."""
    mock_db = MagicMock()
    (
        mock_db.table.return_value
        .select.return_value
        .eq.return_value
        .lt.return_value
        .execute.return_value
        .data
    ) = stale_rows
    return mock_db


@patch("workers.beat_tasks.get_supabase")
def test_stale_reels_transitioned(mock_get_supabase):
    stale = [
        {"id": "reel-1", "user_id": "user-1"},
        {"id": "reel-2", "user_id": "user-2"},
    ]
    mock_db = _make_supabase_mock(stale)
    mock_get_supabase.return_value = mock_db

    from workers.beat_tasks import expire_pending_categories
    result = expire_pending_categories()

    assert result["expired"] == 2
    assert "reel-1" in result["reel_ids"]
    assert "reel-2" in result["reel_ids"]
    assert mock_db.table.return_value.update.call_count == 2


@patch("workers.beat_tasks.get_supabase")
def test_fresh_reels_not_touched(mock_get_supabase):
    mock_db = _make_supabase_mock([])
    mock_get_supabase.return_value = mock_db

    from workers.beat_tasks import expire_pending_categories
    result = expire_pending_categories()

    assert result["expired"] == 0
    assert result["reel_ids"] == []
    mock_db.table.return_value.update.assert_not_called()


@patch("workers.beat_tasks.get_supabase")
def test_returns_count_and_ids(mock_get_supabase):
    stale = [{"id": "reel-abc", "user_id": "user-x"}]
    mock_db = _make_supabase_mock(stale)
    mock_get_supabase.return_value = mock_db

    from workers.beat_tasks import expire_pending_categories
    result = expire_pending_categories()

    assert result == {"expired": 1, "reel_ids": ["reel-abc"]}
```

- [ ] **Step 2: Run tests — verify all 3 fail with ImportError**

```bash
cd backend && source venv/bin/activate && pytest tests/test_beat_tasks.py -v
```

Expected: 3 tests FAIL with `ModuleNotFoundError: No module named 'workers.beat_tasks'`

- [ ] **Step 3: Implement `workers/beat_tasks.py`**

```python
"""Celery Beat periodic tasks — scheduled maintenance jobs."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from supabase_client import get_supabase
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

PENDING_CATEGORY_TIMEOUT_HOURS = 1


@celery_app.task(name="workers.beat_tasks.expire_pending_categories")
def expire_pending_categories() -> dict:
    """Move pending_category reels older than 1 hour to uncategorised.

    Runs every 30 minutes via Celery Beat. Catches reels where the user did
    not respond to the FCM category-suggestion notification within the timeout.
    """
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

- [ ] **Step 4: Run beat task tests — verify all 3 pass**

```bash
cd backend && source venv/bin/activate && pytest tests/test_beat_tasks.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Run the full test suite**

```bash
cd backend && source venv/bin/activate && pytest tests/ -v
```

Expected: All previous tests still pass. Total count increases by 3.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_beat_tasks.py backend/workers/beat_tasks.py
git commit -m "feat: add beat_tasks — expire pending_category reels after 1 hour"
```

---

## Task 5: Register Beat schedule in `celery_app.py`

**Files:**
- Modify: `backend/workers/celery_app.py`

- [ ] **Step 1: Read the current celery_app.py**

```bash
cat backend/workers/celery_app.py
```

- [ ] **Step 2: Add the Beat schedule**

Add after the existing `celery_app` configuration (at the bottom of the file, before any existing `include` or schedule config):

```python
celery_app.conf.beat_schedule = {
    "expire-pending-categories": {
        "task": "workers.beat_tasks.expire_pending_categories",
        "schedule": 30 * 60,  # every 30 minutes
    },
}
```

Also ensure `workers.beat_tasks` is in the `include` list. Find the `celery_app` instantiation and add it if not already present:
```python
# Find the line like:
celery_app = Celery(
    "reelmind",
    include=["workers.tasks"],   # <-- add "workers.beat_tasks" here
    ...
)
# Change to:
celery_app = Celery(
    "reelmind",
    include=["workers.tasks", "workers.beat_tasks"],
    ...
)
```

- [ ] **Step 3: Smoke test the import**

```bash
cd backend && source venv/bin/activate && python -c "
from workers.celery_app import celery_app
from workers.beat_tasks import expire_pending_categories
print('beat schedule:', celery_app.conf.beat_schedule)
print('imports OK')
"
```

Expected output includes `'expire-pending-categories'` in the beat schedule dict and `imports OK`.

- [ ] **Step 4: Commit**

```bash
git add backend/workers/celery_app.py
git commit -m "feat: register expire_pending_categories Beat schedule (every 30 min)"
```

---

## Task 6: Steps 18+19 in `workers/tasks.py`

**Files:**
- Modify: `backend/workers/tasks.py`
- Modify: `backend/tests/test_tasks_resilience.py`

- [ ] **Step 1: Write new resilience tests for Steps 18+19 (all failing)**

Add the following to the end of `backend/tests/test_tasks_resilience.py`:

```python
# ---------------------------------------------------------------------------
# Helpers for Step 18+19 tests
# ---------------------------------------------------------------------------

def _make_step18_supabase_mock(
    fcm_token=None,
    categories=None,
    reel_status="queued",
):
    """Supabase mock that routes table() calls by table name."""
    if categories is None:
        categories = [
            {"id": "cat-fitness", "name": "Fitness"},
            {"id": "cat-nutrition", "name": "Nutrition"},
        ]

    reels_mock = MagicMock()
    profiles_mock = MagicMock()
    categories_mock = MagicMock()

    # Reels: select chain (single row fetch)
    reel_row = {
        "url": "https://instagram.com/reel/ABC/",
        "user_id": "user-1",
        "status": reel_status,
    }
    (
        reels_mock.select.return_value
        .eq.return_value
        .single.return_value
        .execute.return_value
        .data
    ) = reel_row
    reels_mock.update.return_value.eq.return_value.execute.return_value = None

    # Profiles: fcm_token fetch
    (
        profiles_mock.select.return_value
        .eq.return_value
        .single.return_value
        .execute.return_value
        .data
    ) = {"fcm_token": fcm_token}

    # Categories: select + or_ chain
    (
        categories_mock.select.return_value
        .or_.return_value
        .execute.return_value
        .data
    ) = categories

    db_mock = MagicMock()

    def _table(name):
        if name == "reels":
            return reels_mock
        if name == "profiles":
            return profiles_mock
        if name == "categories":
            return categories_mock
        return MagicMock()

    db_mock.table.side_effect = _table
    return db_mock


def _make_classification_result(category="Fitness", confidence=0.92, alternatives=None):
    from services.classifier import ClassificationResult
    return ClassificationResult(
        category=category,
        confidence=confidence,
        alternatives=alternatives or ["Nutrition"],
    )


# ---------------------------------------------------------------------------
# Step 18+19 routing tests
# ---------------------------------------------------------------------------

def test_high_confidence_marks_ready():
    """classify_reel returns ≥0.70 confidence → reel status set to ready."""
    from workers.tasks import process_reel

    task_self = _make_task_self()
    mock_db = _make_step18_supabase_mock()

    signal_mock = MagicMock()
    signal_mock.text = "Fitness content"
    signal_mock.source_summary = "transcript"

    with patch("workers.tasks.get_supabase", return_value=mock_db):
        with patch("workers.tasks.download_reel", return_value=_make_download_result()):
            with patch("workers.tasks.transcribe_audio",
                       return_value=MagicMock(text="workout", has_audio=True)):
                with patch("workers.tasks.build_classification_signal",
                           return_value=signal_mock):
                    with patch("workers.tasks.classify_reel",
                               return_value=_make_classification_result(confidence=0.92)):
                        with patch("os.path.exists", return_value=False):
                            result = process_reel.run.__func__(task_self, "reel-123")

    assert result["status"] == "ready"
    assert result["category"] == "Fitness"


def test_low_confidence_marks_pending_category():
    """classify_reel returns <0.70 confidence → reel status set to pending_category."""
    from workers.tasks import process_reel

    task_self = _make_task_self()
    mock_db = _make_step18_supabase_mock()

    signal_mock = MagicMock()
    signal_mock.text = "Ambiguous content"
    signal_mock.source_summary = "caption"

    with patch("workers.tasks.get_supabase", return_value=mock_db):
        with patch("workers.tasks.download_reel", return_value=_make_download_result()):
            with patch("workers.tasks.transcribe_audio",
                       return_value=MagicMock(text="", has_audio=False)):
                with patch("workers.tasks.build_classification_signal",
                           return_value=signal_mock):
                    with patch("workers.tasks.classify_reel",
                               return_value=_make_classification_result(confidence=0.55)):
                        with patch("os.path.exists", return_value=False):
                            result = process_reel.run.__func__(task_self, "reel-123")

    assert result["status"] == "pending_category"
    assert "suggestions" in result
    assert "Fitness" in result["suggestions"]


def test_classification_retryable_error_triggers_retry():
    """ClassificationError(is_retryable=True) → Celery retry raised."""
    from celery.exceptions import Retry
    from services.classifier import ClassificationError
    from workers.tasks import process_reel

    task_self = _make_task_self(retries=0, max_retries=3)
    mock_db = _make_step18_supabase_mock()

    signal_mock = MagicMock()
    signal_mock.text = "content"
    signal_mock.source_summary = "transcript"

    with patch("workers.tasks.get_supabase", return_value=mock_db):
        with patch("workers.tasks.download_reel", return_value=_make_download_result()):
            with patch("workers.tasks.transcribe_audio",
                       return_value=MagicMock(text="content", has_audio=True)):
                with patch("workers.tasks.build_classification_signal",
                           return_value=signal_mock):
                    with patch("workers.tasks.classify_reel",
                               side_effect=ClassificationError("rate limit", is_retryable=True)):
                        with patch("os.path.exists", return_value=False):
                            with pytest.raises(Retry):
                                process_reel.run.__func__(task_self, "reel-123")


def test_classification_non_retryable_error_marks_failed():
    """ClassificationError(is_retryable=False) → reel marked failed."""
    from services.classifier import ClassificationError
    from workers.tasks import process_reel

    task_self = _make_task_self()
    mock_db = _make_step18_supabase_mock()

    signal_mock = MagicMock()
    signal_mock.text = "content"
    signal_mock.source_summary = "transcript"

    with patch("workers.tasks.get_supabase", return_value=mock_db):
        with patch("workers.tasks.download_reel", return_value=_make_download_result()):
            with patch("workers.tasks.transcribe_audio",
                       return_value=MagicMock(text="content", has_audio=True)):
                with patch("workers.tasks.build_classification_signal",
                           return_value=signal_mock):
                    with patch("workers.tasks.classify_reel",
                               side_effect=ClassificationError("bad schema", is_retryable=False)):
                        with patch("os.path.exists", return_value=False):
                            result = process_reel.run.__func__(task_self, "reel-123")

    assert result["status"] == "failed"
```

- [ ] **Step 2: Run new tests — verify they fail**

```bash
cd backend && source venv/bin/activate && pytest tests/test_tasks_resilience.py -v -k "step18 or high_confidence or low_confidence or classification"
```

Expected: The 4 new tests FAIL (either `ImportError` or assertion errors).

- [ ] **Step 3: Update imports in `tasks.py`**

Find the import block at the top of `backend/workers/tasks.py` and add:

```python
from services.classifier import ClassificationError, ClassificationResult, classify_reel
```

The existing import for `signal_builder` is already there. Add this line directly after it.

- [ ] **Step 4: Add FCM token fetch after the reel row fetch**

In `process_reel`, find the block that ends with:
```python
        log.info("reel url loaded | url=%s | current_status=%s", url, reel_data.get("status"))
```

Add immediately after it:
```python
        log.info("fetching FCM token for user=%s", reel_data["user_id"])
        _profile = (
            supabase.table("profiles")
            .select("fcm_token")
            .eq("id", reel_data["user_id"])
            .single()
            .execute()
        )
        _fcm_token: str | None = _profile.data.get("fcm_token")
```

- [ ] **Step 5: Replace the Step 18 placeholder with Steps 18+19**

Find this block near the end of `process_reel` (after Step 17):
```python
        log.info("process_reel done — signal ready, awaiting Step 18")
        return {
            "reel_id": reel_id,
            "status": "processing",
            "signal_sources": signal.source_summary,
        }
```

Replace it with:
```python
        # ------------------------------------------------------------------
        # Step 18 — fetch categories + call Llama classifier
        # ------------------------------------------------------------------
        log.info("step 18 | fetching categories for user=%s", reel_data["user_id"])
        _cat_rows = (
            supabase.table("categories")
            .select("id, name")
            .or_(f"user_id.eq.{reel_data['user_id']},user_id.is.null")
            .execute()
        )
        category_db_map = {row["name"]: row["id"] for row in _cat_rows.data}
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
                "step 18 | done | category=%s | confidence=%.2f | alternatives=%s",
                classification.category,
                classification.confidence,
                classification.alternatives,
            )
        except ClassificationError as exc:
            log.warning(
                "step 18 | classification error | retryable=%s | %s",
                exc.is_retryable,
                exc,
            )
            return _handle_pipeline_error(
                self, supabase, reel_id, exc, exc.is_retryable, log
            )

        # ------------------------------------------------------------------
        # Step 19 — confidence routing
        # ------------------------------------------------------------------
        _CONFIDENCE_THRESHOLD = 0.70

        if classification.confidence >= _CONFIDENCE_THRESHOLD:
            log.info(
                "step 19 | auto-assigning | confidence=%.2f >= %.2f",
                classification.confidence,
                _CONFIDENCE_THRESHOLD,
            )
            supabase.table("reels").update({
                "category_id": category_db_map[classification.category],
                "confidence": classification.confidence,
                "status": "ready",
            }).eq("id", reel_id).execute()
            # TODO Step 22: FCM push — "Your reel has been saved and categorised!"
            log.info("step 19 | status=ready")
            return {
                "reel_id": reel_id,
                "status": "ready",
                "category": classification.category,
            }
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
            # TODO Step 22: FCM push with buttons [suggestion1] [suggestion2]
            #   [Choose in App] [Uncategorised]
            log.info("step 19 | status=pending_category")
            return {
                "reel_id": reel_id,
                "status": "pending_category",
                "suggestions": suggestions,
            }
```

- [ ] **Step 6: Run all tests — verify new tests pass and no regressions**

```bash
cd backend && source venv/bin/activate && pytest tests/ -v
```

Expected: All tests pass. The 4 new Step 18+19 routing tests are now green.

- [ ] **Step 7: Smoke test the Celery import**

```bash
cd backend && source venv/bin/activate && python -c "
from workers.tasks import process_reel
from services.classifier import classify_reel, ClassificationResult, ClassificationError
print('imports OK')
print('ClassificationResult fields:', list(ClassificationResult.__dataclass_fields__))
"
```

Expected:
```
imports OK
ClassificationResult fields: ['category', 'confidence', 'alternatives']
```

- [ ] **Step 8: Commit**

```bash
git add backend/workers/tasks.py backend/tests/test_tasks_resilience.py
git commit -m "feat: implement Steps 18+19 — Llama classification and confidence routing"
```

---

## Task 7: `PATCH /api/v1/reels/{reel_id}/category` endpoint

**Files:**
- Modify: `backend/schemas/reel.py`
- Modify: `backend/api/v1/reels.py`
- Create: `backend/tests/test_category_endpoint.py`

- [ ] **Step 1: Read the existing schemas/reel.py**

```bash
cat backend/schemas/reel.py
```

- [ ] **Step 2: Add `CategoryChoiceRequest` to schemas**

Add to the end of `backend/schemas/reel.py`:

```python
class CategoryChoiceRequest(BaseModel):
    """Body for PATCH /reels/{reel_id}/category.

    category_name: exact category name (string) → assigns category, marks ready.
    category_name: null → skips to uncategorised immediately.
    """
    category_name: str | None = None
```

- [ ] **Step 3: Write endpoint tests (all failing)**

```python
"""Tests for PATCH /api/v1/reels/{reel_id}/category."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import get_current_user_id
from api.v1.reels import router

# Minimal test app with auth overridden
_app = FastAPI()
_app.include_router(router, prefix="/api/v1/reels")
_app.dependency_overrides[get_current_user_id] = lambda: "user-test-id"
client = TestClient(_app)

REEL_ID = "reel-abc-123"


def _make_supabase_patch_mock(reel_status="pending_category", category_id=None):
    """Mock supabase for the PATCH endpoint."""
    db = MagicMock()

    # Reel fetch: .table("reels").select(...).eq(id).eq(user_id).single().execute()
    reel_row = {
        "id": REEL_ID,
        "user_id": "user-test-id",
        "status": reel_status,
        "suggested_categories": ["Fitness", "Nutrition"],
    }
    (
        db.table.return_value
        .select.return_value
        .eq.return_value
        .eq.return_value
        .single.return_value
        .execute.return_value
        .data
    ) = reel_row

    # Category lookup: .table("categories").select(...).eq(name).or_(...).execute()
    if category_id:
        cat_rows = [{"id": category_id, "name": "Fitness"}]
    else:
        cat_rows = []
    (
        db.table.return_value
        .select.return_value
        .eq.return_value
        .or_.return_value
        .execute.return_value
        .data
    ) = cat_rows

    db.table.return_value.update.return_value.eq.return_value.execute.return_value = None
    return db


@patch("api.v1.reels.get_supabase")
def test_assign_category_marks_ready(mock_get_supabase):
    mock_get_supabase.return_value = _make_supabase_patch_mock(
        category_id="cat-uuid-fitness"
    )
    resp = client.patch(
        f"/api/v1/reels/{REEL_ID}/category",
        json={"category_name": "Fitness"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"
    assert resp.json()["category"] == "Fitness"


@patch("api.v1.reels.get_supabase")
def test_null_category_name_marks_uncategorised(mock_get_supabase):
    mock_get_supabase.return_value = _make_supabase_patch_mock()
    resp = client.patch(
        f"/api/v1/reels/{REEL_ID}/category",
        json={"category_name": None},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "uncategorised"


@patch("api.v1.reels.get_supabase")
def test_already_resolved_returns_409(mock_get_supabase):
    mock_get_supabase.return_value = _make_supabase_patch_mock(reel_status="ready")
    resp = client.patch(
        f"/api/v1/reels/{REEL_ID}/category",
        json={"category_name": "Fitness"},
    )
    assert resp.status_code == 409


@patch("api.v1.reels.get_supabase")
def test_reel_not_found_returns_404(mock_get_supabase):
    db = MagicMock()
    (
        db.table.return_value
        .select.return_value
        .eq.return_value
        .eq.return_value
        .single.return_value
        .execute.return_value
        .data
    ) = None
    mock_get_supabase.return_value = db
    resp = client.patch(
        f"/api/v1/reels/{REEL_ID}/category",
        json={"category_name": "Fitness"},
    )
    assert resp.status_code == 404


@patch("api.v1.reels.get_supabase")
def test_unknown_category_name_returns_422(mock_get_supabase):
    db = _make_supabase_patch_mock(category_id=None)  # empty cat_rows
    mock_get_supabase.return_value = db
    resp = client.patch(
        f"/api/v1/reels/{REEL_ID}/category",
        json={"category_name": "NonExistentCategory"},
    )
    assert resp.status_code == 422
```

Save to `backend/tests/test_category_endpoint.py`.

- [ ] **Step 4: Run endpoint tests — verify all 5 fail**

```bash
cd backend && source venv/bin/activate && pytest tests/test_category_endpoint.py -v
```

Expected: All 5 tests FAIL (either 404 Not Found from the router or assertion failures).

- [ ] **Step 5: Add the endpoint to `api/v1/reels.py`**

Add to `backend/api/v1/reels.py`:

First, update the imports at the top:
```python
from fastapi import APIRouter, Depends, HTTPException, Response, status

from api.deps import get_current_user_id
from schemas.reel import CategoryChoiceRequest, ReelCreate, ReelResponse
from supabase_client import get_supabase
from workers.tasks import process_reel
```

Then add the new endpoint after `create_reel`:

```python
@router.patch("/{reel_id}/category", status_code=status.HTTP_200_OK)
async def update_reel_category(
    reel_id: str,
    payload: CategoryChoiceRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Handle user's category choice from an FCM notification button tap.

    Path A (category_name is a string): assigns the category, marks reel ready.
    Path B (category_name is null): moves reel to uncategorised immediately.

    Returns 409 if the reel is already resolved (idempotent guard).
    Returns 404 if the reel does not belong to this user.
    Returns 422 if category_name is not in the user's categories.
    """
    supabase = get_supabase()

    # Fetch and validate reel ownership
    reel_row = (
        supabase.table("reels")
        .select("id, user_id, status, suggested_categories")
        .eq("id", reel_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    if not reel_row.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reel not found")

    reel = reel_row.data
    if reel["status"] != "pending_category":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Reel already resolved (status={reel['status']})",
        )

    # Path B — user tapped "Uncategorised"
    if payload.category_name is None:
        supabase.table("reels").update({
            "status": "uncategorised",
            "suggested_categories": [],
        }).eq("id", reel_id).execute()
        # TODO Step 22: FCM push — "Saved to Uncategorised — you can move it anytime"
        return {"reel_id": reel_id, "status": "uncategorised"}

    # Path A — user picked a specific category
    cat_rows = (
        supabase.table("categories")
        .select("id, name")
        .eq("name", payload.category_name)
        .or_(f"user_id.eq.{user_id},user_id.is.null")
        .execute()
    )
    if not cat_rows.data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Category '{payload.category_name}' not found for this user",
        )

    category_id = cat_rows.data[0]["id"]
    supabase.table("reels").update({
        "category_id": category_id,
        "confidence": 1.0,
        "status": "ready",
        "suggested_categories": [],
    }).eq("id", reel_id).execute()
    # TODO Step 22: FCM push — "Reel categorised!"
    return {"reel_id": reel_id, "status": "ready", "category": payload.category_name}
```

- [ ] **Step 6: Run endpoint tests — verify all 5 pass**

```bash
cd backend && source venv/bin/activate && pytest tests/test_category_endpoint.py -v
```

Expected: `5 passed`

- [ ] **Step 7: Run the full test suite**

```bash
cd backend && source venv/bin/activate && pytest tests/ -v
```

Expected: All tests pass. Verify total count includes all previous tests + 5 new endpoint tests.

- [ ] **Step 8: Commit**

```bash
git add backend/schemas/reel.py backend/api/v1/reels.py backend/tests/test_category_endpoint.py
git commit -m "feat: add PATCH /reels/{reel_id}/category endpoint for FCM category choice"
```

---

## Final Verification

- [ ] **Run the complete test suite one last time**

```bash
cd backend && source venv/bin/activate && pytest tests/ -v
```

Expected: All tests pass, 0 failures.

- [ ] **Smoke test all new imports together**

```bash
cd backend && source venv/bin/activate && python -c "
from workers.tasks import process_reel
from workers.beat_tasks import expire_pending_categories
from workers.celery_app import celery_app
from services.classifier import classify_reel, ClassificationResult, ClassificationError
from api.v1.reels import router
print('All imports OK')
print('Beat schedule keys:', list(celery_app.conf.beat_schedule.keys()))
print('ClassificationResult fields:', list(ClassificationResult.__dataclass_fields__))
"
```

Expected:
```
All imports OK
Beat schedule keys: ['expire-pending-categories']
ClassificationResult fields: ['category', 'confidence', 'alternatives']
```
