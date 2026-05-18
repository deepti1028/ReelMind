# Step 17 — Classification Signal Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Step 17 of the ingestion pipeline — a pure function that assembles a normalized, prompt-ready classification signal from all available reel data (transcript, caption, hashtags) and gates the pipeline on signal existence.

**Architecture:** New `services/signal_builder.py` follows the existing service module pattern (same structure as `transcriber.py`). It is a pure function — no I/O, no DB access. `workers/tasks.py` is updated to initialize `transcription = None` before Step 16 (fixing a latent NameError) and to call `build_classification_signal` in the new Step 17 block, catching `NoSignalError` to mark the reel `uncategorised`.

**Tech Stack:** Python stdlib only (dataclasses). No new dependencies.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/services/signal_builder.py` | `ClassificationSignal`, `NoSignalError`, `build_classification_signal()` |
| Create | `backend/tests/test_signal_builder.py` | All 11 test cases — pure function, no mocks needed |
| Modify | `backend/workers/tasks.py` | Fix `transcription` init + add Step 17 block |

---

## Context You Need

- All backend commands run from `backend/` with `source venv/bin/activate`.
- Tests use `pytest`. Run from `backend/`: `pytest tests/test_signal_builder.py -v`
- `backend/tests/conftest.py` already adds `backend/` to `sys.path` — no path setup needed in test files.
- `tasks.py` currently has a latent bug: `transcription` is only assigned inside the `else` branch of the Step 16 try/except. On the graceful-degradation path and the "no audio URL" path, it is never assigned, so Step 17 would raise `NameError`. Task 3 fixes this.
- The existing `# Steps 17-22 — TODO` block in `tasks.py` (lines 163–170) is replaced by the Step 17 implementation + a revised TODO comment for Steps 18–22.

---

## Task 1: Write all tests (all failing)

**Files:**
- Create: `backend/tests/test_signal_builder.py`

- [ ] **Step 1: Create the test file**

```python
# backend/tests/test_signal_builder.py
"""Tests for services.signal_builder — Step 17 classification signal assembly."""
import pytest


# ---------------------------------------------------------------------------
# No-signal gate (4 cases)
# ---------------------------------------------------------------------------

def test_raises_when_all_none():
    from services.signal_builder import build_classification_signal, NoSignalError
    with pytest.raises(NoSignalError):
        build_classification_signal(transcript=None, caption=None, hashtags=[])


def test_raises_when_all_empty_strings():
    from services.signal_builder import build_classification_signal, NoSignalError
    with pytest.raises(NoSignalError):
        build_classification_signal(transcript="", caption="", hashtags=[])


def test_raises_when_all_whitespace():
    from services.signal_builder import build_classification_signal, NoSignalError
    with pytest.raises(NoSignalError):
        build_classification_signal(transcript="   ", caption="\t\n", hashtags=["", "  "])


def test_raises_when_hashtags_all_empty_strings():
    from services.signal_builder import build_classification_signal, NoSignalError
    with pytest.raises(NoSignalError):
        build_classification_signal(transcript=None, caption=None, hashtags=["", "  ", "\t"])


# ---------------------------------------------------------------------------
# Happy paths — single signal
# ---------------------------------------------------------------------------

def test_transcript_only():
    from services.signal_builder import build_classification_signal
    result = build_classification_signal(
        transcript="A 5-minute HIIT workout.",
        caption=None,
        hashtags=[],
    )
    assert result.has_transcript is True
    assert result.has_caption is False
    assert result.has_hashtags is False
    assert "[Transcript]\nA 5-minute HIIT workout." in result.text
    assert "[Caption]" not in result.text
    assert "[Hashtags]" not in result.text
    assert result.source_summary == "transcript"


def test_caption_only():
    from services.signal_builder import build_classification_signal
    result = build_classification_signal(
        transcript=None,
        caption="Full body burn in 15 min!",
        hashtags=[],
    )
    assert result.has_transcript is False
    assert result.has_caption is True
    assert result.has_hashtags is False
    assert "[Caption]\nFull body burn in 15 min!" in result.text
    assert "[Transcript]" not in result.text
    assert result.source_summary == "caption"


def test_hashtags_only():
    from services.signal_builder import build_classification_signal
    result = build_classification_signal(
        transcript=None,
        caption=None,
        hashtags=["fitness", "gym", "workout"],
    )
    assert result.has_transcript is False
    assert result.has_caption is False
    assert result.has_hashtags is True
    assert "[Hashtags]\n#fitness #gym #workout" in result.text
    assert "[Transcript]" not in result.text
    assert result.source_summary == "hashtags"


# ---------------------------------------------------------------------------
# Happy paths — combined signals
# ---------------------------------------------------------------------------

def test_full_signal():
    from services.signal_builder import build_classification_signal
    result = build_classification_signal(
        transcript="The creator shows a workout.",
        caption="Full body burn!",
        hashtags=["fitness", "gym"],
    )
    assert result.has_transcript is True
    assert result.has_caption is True
    assert result.has_hashtags is True
    assert "[Transcript]" in result.text
    assert "[Caption]" in result.text
    assert "[Hashtags]" in result.text
    assert result.source_summary == "transcript+caption+hashtags"


def test_transcript_and_hashtags_no_caption():
    from services.signal_builder import build_classification_signal
    result = build_classification_signal(
        transcript="A cooking tutorial.",
        caption=None,
        hashtags=["food", "recipe"],
    )
    assert result.has_transcript is True
    assert result.has_caption is False
    assert result.has_hashtags is True
    assert "[Transcript]" in result.text
    assert "[Caption]" not in result.text
    assert "[Hashtags]" in result.text
    assert result.source_summary == "transcript+hashtags"


def test_caption_and_hashtags_no_transcript():
    from services.signal_builder import build_classification_signal
    result = build_classification_signal(
        transcript=None,
        caption="Check out this recipe!",
        hashtags=["food", "cooking"],
    )
    assert result.has_transcript is False
    assert result.has_caption is True
    assert result.has_hashtags is True
    assert "[Transcript]" not in result.text
    assert "[Caption]" in result.text
    assert "[Hashtags]" in result.text
    assert result.source_summary == "caption+hashtags"


# ---------------------------------------------------------------------------
# Normalization edge cases
# ---------------------------------------------------------------------------

def test_whitespace_transcript_treated_as_absent():
    from services.signal_builder import build_classification_signal
    result = build_classification_signal(
        transcript="   ",
        caption="Short caption.",
        hashtags=[],
    )
    assert result.has_transcript is False
    assert result.has_caption is True
    assert "[Transcript]" not in result.text
    assert result.source_summary == "caption"


def test_empty_hashtag_strings_filtered():
    from services.signal_builder import build_classification_signal
    result = build_classification_signal(
        transcript=None,
        caption=None,
        hashtags=["", "fitness", "  ", "gym"],
    )
    assert result.has_hashtags is True
    assert "#fitness" in result.text
    assert "#gym" in result.text
    assert result.text.count("#") == 2


def test_source_summary_reflects_actual_sources():
    from services.signal_builder import build_classification_signal
    result = build_classification_signal(
        transcript=None,
        caption="A caption.",
        hashtags=["tag1"],
    )
    assert result.source_summary == "caption+hashtags"
```

- [ ] **Step 2: Run tests — verify all fail with ImportError**

```bash
cd backend && source venv/bin/activate && pytest tests/test_signal_builder.py -v
```

Expected: All 11 tests FAIL with `ModuleNotFoundError: No module named 'services.signal_builder'`

- [ ] **Step 3: Commit the test file as a spec**

```bash
git add backend/tests/test_signal_builder.py
git commit -m "test: add signal_builder tests (all failing — TDD red phase)"
```

---

## Task 2: Implement `services/signal_builder.py`

**Files:**
- Create: `backend/services/signal_builder.py`

- [ ] **Step 1: Create the implementation**

```python
# backend/services/signal_builder.py
"""Classification signal builder — Step 17 of the ingestion pipeline.

Assembles a normalized, prompt-ready text signal from all available reel
data (transcript, caption, hashtags) for the Llama classifier in Step 18.

Public surface:
    build_classification_signal(transcript, caption, hashtags) -> ClassificationSignal
    ClassificationSignal, NoSignalError
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ClassificationSignal:
    text: str            # assembled, prompt-ready text for the Llama classifier
    has_transcript: bool
    has_caption: bool
    has_hashtags: bool
    source_summary: str  # e.g. "transcript+caption+hashtags" — for log lines


class NoSignalError(Exception):
    """Raised when all signals are empty after normalization.

    Not retryable — no amount of retrying will produce new data without
    a fresh download.
    """


def build_classification_signal(
    transcript: str | None,
    caption: str | None,
    hashtags: list[str],
) -> ClassificationSignal:
    """Assemble a normalized classification signal from available reel data.

    Normalizes each field (strips whitespace, filters empty hashtags),
    checks that at least one field has content, then builds a labeled
    prompt-ready text string for Step 18.

    Args:
        transcript: Raw transcript text from Step 16, or None.
        caption:    Caption text from Step 15, or None.
        hashtags:   List of hashtag strings from Step 15 (may be empty).

    Returns:
        ClassificationSignal with assembled text and source metadata.

    Raises:
        NoSignalError: All three signals are empty after normalization.
    """
    t = (transcript or "").strip()
    c = (caption or "").strip()
    h = [tag.strip() for tag in (hashtags or []) if tag.strip()]

    if not t and not c and not h:
        raise NoSignalError(
            "no usable signal: transcript, caption, and hashtags are all "
            "empty after normalization"
        )

    sections: list[str] = []
    sources: list[str] = []

    if t:
        sections.append(f"[Transcript]\n{t}")
        sources.append("transcript")

    if c:
        sections.append(f"[Caption]\n{c}")
        sources.append("caption")

    if h:
        hashtag_line = " ".join(f"#{tag}" for tag in h)
        sections.append(f"[Hashtags]\n{hashtag_line}")
        sources.append("hashtags")

    return ClassificationSignal(
        text="\n\n".join(sections),
        has_transcript=bool(t),
        has_caption=bool(c),
        has_hashtags=bool(h),
        source_summary="+".join(sources),
    )
```

- [ ] **Step 2: Run tests — verify all 11 pass**

```bash
cd backend && source venv/bin/activate && pytest tests/test_signal_builder.py -v
```

Expected: `11 passed` — all green.

- [ ] **Step 3: Run the full test suite to check for regressions**

```bash
cd backend && source venv/bin/activate && pytest tests/ -v
```

Expected: All pre-existing tests still pass. New: 11 more passing.

- [ ] **Step 4: Commit**

```bash
git add backend/services/signal_builder.py
git commit -m "feat: add signal_builder service — Step 17 classification signal assembly"
```

---

## Task 3: Integrate Step 17 into `workers/tasks.py`

**Files:**
- Modify: `backend/workers/tasks.py`

Two changes:
1. Add `TranscriptionResult` to the `transcriber` import and initialize `transcription = None` before Step 16 to fix the latent `NameError`.
2. Replace the `# Steps 17-22 — TODO` block with the Step 17 implementation + a revised TODO for Steps 18–22.

- [ ] **Step 1: Update the import line for `services.transcriber`**

Find this line near the top of `backend/workers/tasks.py`:

```python
from services.transcriber import TranscriptionError, transcribe_audio
```

Replace with:

```python
from services.signal_builder import NoSignalError, build_classification_signal
from services.transcriber import TranscriptionError, TranscriptionResult, transcribe_audio
```

- [ ] **Step 2: Initialize `transcription` before the Step 16 block**

Find this line in `process_reel` (just before `if download_result.audio_path:`):

```python
        # ------------------------------------------------------------------
        # Step 16 — transcribe audio
        # ------------------------------------------------------------------
        if download_result.audio_path:
```

Replace with:

```python
        # ------------------------------------------------------------------
        # Step 16 — transcribe audio
        # ------------------------------------------------------------------
        transcription: TranscriptionResult | None = None
        if download_result.audio_path:
```

- [ ] **Step 3: Replace the TODO block with the Step 17 implementation**

Find this entire block (after the Step 16 `else` clause ends):

```python
        # ------------------------------------------------------------------
        # Steps 17-22 — TODO (classification, embeddings, push)
        # ------------------------------------------------------------------
        # Until Step 18 lands, we leave the row in 'processing'. Once
        # classification + confidence routing exist, we'll set 'ready' or
        # 'uncategorised'. Marking 'ready' here would be a lie — the reel
        # is not yet usable for category browsing or search.

        log.info("process_reel done")
        return {
            "reel_id": reel_id,
            "status": "metadata_and_transcript_saved",
            "has_audio": (
                download_result.audio_path is not None
                and os.path.exists(download_result.audio_path)
            ),
        }
```

Replace with:

```python
        # ------------------------------------------------------------------
        # Step 17 — build classification signal
        # ------------------------------------------------------------------
        _transcript_text = transcription.text if transcription is not None else None

        try:
            signal = build_classification_signal(
                transcript=_transcript_text,
                caption=meta.caption,
                hashtags=meta.hashtags,
            )
            log.info(
                "step 17 | signal built | sources=%s | chars=%d",
                signal.source_summary,
                len(signal.text),
            )
        except NoSignalError:
            log.warning(
                "step 17 | no usable signal (transcript=None, caption=None, "
                "hashtags=[]) — marking uncategorised"
            )
            supabase.table("reels").update(
                {"status": "uncategorised"}
            ).eq("id", reel_id).execute()
            # TODO Step 22: FCM push — notify user this reel could not be categorised.
            # Both status='uncategorised' (here) and status='ready' (Step 19) need
            # an FCM notification with different message text:
            #   uncategorised → "We couldn't categorise your reel — no text or audio found."
            #   ready         → "Your reel has been saved and categorised!"
            return {"reel_id": reel_id, "status": "uncategorised"}

        # ------------------------------------------------------------------
        # Steps 18-22 — TODO (Llama classification, confidence routing,
        #               embeddings, FCM push)
        # ------------------------------------------------------------------
        # `signal` is available in-memory for Step 18. Until Step 18 lands,
        # the row stays in 'processing'. Marking 'ready' here would be a
        # lie — the reel is not yet categorised or searchable.

        log.info("process_reel done — signal ready, awaiting Step 18")
        return {
            "reel_id": reel_id,
            "status": "processing",
            "signal_sources": signal.source_summary,
        }
```

- [ ] **Step 4: Run the full test suite**

```bash
cd backend && source venv/bin/activate && pytest tests/ -v
```

Expected: All tests pass. The `test_tasks_resilience.py` tests should still pass since we haven't changed any retry or error-handling logic.

- [ ] **Step 5: Smoke-test the Celery import (no worker needed)**

```bash
cd backend && source venv/bin/activate && python -c "
from workers.tasks import process_reel
from services.signal_builder import build_classification_signal, NoSignalError, ClassificationSignal
print('imports OK')
print('ClassificationSignal fields:', [f for f in ClassificationSignal.__dataclass_fields__])
"
```

Expected output:
```
imports OK
ClassificationSignal fields: ['text', 'has_transcript', 'has_caption', 'has_hashtags', 'source_summary']
```

- [ ] **Step 6: Commit**

```bash
git add backend/workers/tasks.py
git commit -m "feat: implement Step 17 — classification signal builder integration"
```
