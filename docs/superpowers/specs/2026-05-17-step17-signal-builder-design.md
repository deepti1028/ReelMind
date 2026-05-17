# Step 17 — Classification Signal Builder Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Step 17 of the ingestion pipeline — assemble a normalized, prompt-ready classification signal from all available reel data (transcript, caption, hashtags), gate the pipeline on signal existence, and stop cleanly when no signal is present.

**Architecture:** A new `services/signal_builder.py` module follows the existing downloader/transcriber service pattern. It is a pure function with no I/O or DB access — it takes already-computed in-memory values from Steps 15/16 and returns a `ClassificationSignal` dataclass. `workers/tasks.py` catches `NoSignalError` to handle the no-signal branch.

**Tech Stack:** Python stdlib only (dataclasses, string operations). No new dependencies.

---

## Files

| Action | File |
|--------|------|
| Create | `backend/services/signal_builder.py` |
| Modify | `backend/workers/tasks.py` |
| Create | `backend/tests/test_signal_builder.py` |

---

## Data Model

### `ClassificationSignal`

```python
@dataclass
class ClassificationSignal:
    text: str            # assembled, prompt-ready text for the Llama classifier
    has_transcript: bool
    has_caption: bool
    has_hashtags: bool
    source_summary: str  # e.g. "transcript+caption+hashtags" — for log lines
```

`text` is what Step 18 embeds directly into the Llama classification prompt.

### `NoSignalError`

```python
class NoSignalError(Exception):
    pass
```

Raised when all three signals are empty after normalization. Not retryable — there is nothing to retry without new data.

---

## Public Surface

```python
def build_classification_signal(
    transcript: str | None,
    caption: str | None,
    hashtags: list[str],
) -> ClassificationSignal:
    ...
```

Raises `NoSignalError` if all signals are absent after normalization.

---

## Normalization Rules

Applied before the existence check:

| Field | Rule |
|-------|------|
| `transcript` | `.strip()` — empty string or whitespace-only → absent |
| `caption` | `.strip()` — empty string or whitespace-only → absent |
| `hashtags` | Filter out empty/whitespace-only strings, strip each tag; empty list → absent |

These rules ensure that Whisper returning `""` (silent reel), caption being `None` from the scraper, and an empty hashtag list are all treated uniformly as "no signal."

---

## Signal Matrix (all 8 combinations)

| transcript | caption | hashtags | Action |
|-----------|---------|----------|--------|
| ✓ | ✓ | ✓ | Proceed — full signal |
| ✓ | ✓ | ✗ | Proceed — transcript + caption |
| ✓ | ✗ | ✓ | Proceed — transcript + hashtags |
| ✓ | ✗ | ✗ | Proceed — transcript only |
| ✗ | ✓ | ✓ | Proceed — caption + hashtags |
| ✗ | ✓ | ✗ | Proceed — caption only |
| ✗ | ✗ | ✓ | Proceed — hashtags only |
| ✗ | ✗ | ✗ | **STOP** → raise `NoSignalError` |

The threshold is "any signal at all." Signal quality (e.g., too-short caption, ambiguous hashtags) is **not** judged here — that is the responsibility of Step 19 (confidence routing), which can mark a reel `uncategorised` if Llama's classification confidence is too low.

---

## Text Assembly Format

Only sections with content are included. Labels are explicit to give the Llama classifier clear signal-type context.

```
[Transcript]
{transcript text}

[Caption]
{caption text}

[Hashtags]
#tag1 #tag2 #tag3
```

**Examples:**

Full signal:
```
[Transcript]
The creator demonstrates a 5-minute full-body HIIT workout with no equipment.

[Caption]
Full body burn in 15 min!

[Hashtags]
#fitness #gym #workout #hiit
```

Hashtags only:
```
[Hashtags]
#fitness #gym #workout
```

Caption + hashtags (no transcript):
```
[Caption]
Check out this amazing recipe!

[Hashtags]
#food #cooking #recipe
```

---

## `tasks.py` Integration

### Variable naming contract

At the point Step 17 runs in `process_reel`:

- `meta` — `ReelMetadata` from `download_result.metadata` (always set if Step 15 succeeded)
- `transcription` — `TranscriptionResult | None`. Currently in `tasks.py`, `transcription` is only assigned inside the `else` clause of the Step 16 try/except (i.e., only on success). On the graceful degradation path and the "no audio URL" path it is never assigned, which would cause a `NameError` in Step 17.

  **Required fix in `tasks.py`:** Add `transcription: TranscriptionResult | None = None` immediately before the Step 16 `if download_result.audio_path:` block. This makes the variable well-defined for all paths that reach Step 17.

### Step 17 block in `process_reel`

```python
# ------------------------------------------------------------------
# Step 17 — build classification signal
# ------------------------------------------------------------------
from services.signal_builder import build_classification_signal, NoSignalError

_transcript_text = transcription.text if (transcription is not None) else None

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
        "step 17 | no usable signal (transcript=None, caption=None, hashtags=[]) "
        "— marking uncategorised"
    )
    supabase.table("reels").update(
        {"status": "uncategorised"}
    ).eq("id", reel_id).execute()
    # TODO Step 22: FCM push — notify user this reel could not be categorised.
    # Both status='uncategorised' (here) and status='ready' (Step 19) need an
    # FCM notification with different message text:
    #   uncategorised → "We couldn't categorise your reel — no text or audio found."
    #   ready         → "Your reel has been saved and categorised!"
    return {"reel_id": reel_id, "status": "uncategorised"}

# `signal` is now available in-memory for Step 18 (Llama classification)
```

---

## Step 22 FCM Backlog Note

Step 22 (FCM push) must handle **two distinct terminal states** from the pipeline:

| Status | FCM message |
|--------|-------------|
| `ready` | "Your reel has been saved and categorised!" |
| `uncategorised` | "We saved your reel but couldn't categorise it — no text or audio was found." |
| `failed` | No FCM push (already tracked; user sees failed status in app) |

This is a forward-looking note for when Step 22 is designed. The `status` column in the `reels` table is the source of truth — Step 22 reads it after the pipeline completes.

---

## Testing Strategy

All tests live in `backend/tests/test_signal_builder.py`. No mocks needed — `build_classification_signal` is a pure function.

**Cases to cover:**

1. All three signals present → full text with all three sections
2. Transcript only → text has only `[Transcript]` section
3. Caption only → text has only `[Caption]` section
4. Hashtags only → text has only `[Hashtags]` section
5. Transcript + hashtags (no caption) → two sections, no `[Caption]`
6. Caption + hashtags (no transcript) → two sections, no `[Transcript]`
7. All None / empty → raises `NoSignalError`
8. Whitespace-only transcript → treated as absent
9. Whitespace-only caption → treated as absent
10. Hashtags list with empty strings → filtered out; if all empty → absent
11. `source_summary` reflects actual sources (e.g. `"caption+hashtags"`)

---

## What Step 17 Does NOT Do

- Does not write to the DB (all signals already persisted by Steps 15/16)
- Does not read from the DB (values passed in-memory from prior steps)
- Does not call any external API
- Does not judge signal quality (that is Step 19's job)
- Does not mark the reel `ready` (Step 18/19 responsibility)
- Does not differentiate between `has_audio=False` due to silent reel vs. transcription failure — both result in `transcript=None` being passed in
