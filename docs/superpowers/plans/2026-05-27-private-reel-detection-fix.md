# Private Reel Detection Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect private Instagram reels that return HTTP 200 (no login redirect) but serve stripped HTML with no media payload — currently misclassified as a transient/retryable failure causing 3 unnecessary Celery retries.

**Architecture:** Add a `_html_signals_private_content(html)` helper in `downloader.py` that scans all `<script type="application/json">` blocks (without the `video_versions`/`shortcode` filter) for any dict where `is_private` is `True`. Wire it into `_extract_media_item` so that when the media payload cannot be found, we check for private markers before deciding whether the error is retryable or a definitive private-content rejection.

**Tech Stack:** Python, `parsel` (already used for HTML parsing), pytest

---

## Background: Why This Happens

When Instagram serves a private reel URL to an unauthenticated request it returns **HTTP 200** with a stripped page. The current detection in `_fetch_reel_html` only catches:
- HTTP 401/403 → `is_private_content=True` ✓
- Login-wall redirect (`/accounts/login` in URL or `"LoginAndSignupPage"` in body) → `is_private_content=True` ✓

But for private accounts Instagram often serves a **200 OK page** that:
- Contains basic user metadata JSON (with `"is_private": true`) 
- Does **not** contain `video_versions` or `shortcode` in any JSON block

`_extract_media_item` filters out any block without those markers, so it never reads the user metadata, finds nothing, and raises `DownloadError(is_retryable=True)`. Celery retries 3× with exponential backoff before marking the reel failed.

---

## File Map

| File | Change |
|---|---|
| `backend/services/downloader.py` | Add `_html_signals_private_content()` helper; update `_extract_media_item()` to call it before raising retryable error |
| `backend/tests/test_downloader_private_detection.py` | New — unit tests for the helper and for `_extract_media_item`'s error-routing |

No other files change. `workers/tasks.py` already handles `DownloadError(is_private_content=True)` correctly (deletes row, pushes FCM, returns `rejected_private`).

---

### Task 1: Add `_html_signals_private_content` and fix `_extract_media_item`

**Files:**
- Modify: `backend/services/downloader.py` (around line 389 — `_extract_media_item`, and after `_walk_dicts`)
- Test: `backend/tests/test_downloader_private_detection.py` (create new)

---

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_downloader_private_detection.py`:

```python
import json
import pytest
from services.downloader import DownloadError


# ---------------------------------------------------------------------------
# Helpers — build minimal HTML pages
# ---------------------------------------------------------------------------

def _html_with_json_blocks(*payloads):
    """Wrap each dict as a <script type="application/json"> block."""
    blocks = "".join(
        f'<script type="application/json">{json.dumps(p)}</script>'
        for p in payloads
    )
    return f"<html><head>{blocks}</head><body></body></html>"


def _private_user_block():
    """JSON block with user metadata marking account private — no video payload."""
    return {"user": {"pk": "123", "username": "secretuser", "is_private": True}}


def _public_user_block():
    return {"user": {"pk": "456", "username": "publicuser", "is_private": False}}


def _media_block():
    """Minimal valid media block that _extract_media_item can find."""
    return {
        "gql_data": {
            "shortcode_media": {
                "items": [{"pk": "999", "video_versions": [{"url": "https://cdn.ig/v.mp4"}]}]
            }
        }
    }


# ---------------------------------------------------------------------------
# Unit tests for _html_signals_private_content
# ---------------------------------------------------------------------------

def test_signals_private_when_is_private_true_in_json_block():
    from services.downloader import _html_signals_private_content
    html = _html_with_json_blocks(_private_user_block())
    assert _html_signals_private_content(html) is True


def test_signals_false_when_is_private_false_in_json_block():
    from services.downloader import _html_signals_private_content
    html = _html_with_json_blocks(_public_user_block())
    assert _html_signals_private_content(html) is False


def test_signals_false_when_no_json_blocks():
    from services.downloader import _html_signals_private_content
    assert _html_signals_private_content("<html><body>nothing here</body></html>") is False


def test_signals_false_when_json_blocks_have_no_is_private_key():
    from services.downloader import _html_signals_private_content
    html = _html_with_json_blocks({"config": {"csrf_token": "abc"}})
    assert _html_signals_private_content(html) is False


def test_signals_true_when_one_of_multiple_blocks_is_private():
    from services.downloader import _html_signals_private_content
    html = _html_with_json_blocks(
        {"config": {"csrf_token": "abc"}},
        _private_user_block(),
        {"unrelated": True},
    )
    assert _html_signals_private_content(html) is True


def test_signals_false_when_media_block_has_no_is_private():
    from services.downloader import _html_signals_private_content
    html = _html_with_json_blocks(_media_block())
    assert _html_signals_private_content(html) is False


# ---------------------------------------------------------------------------
# Integration tests for _extract_media_item error routing
# ---------------------------------------------------------------------------

def test_extract_raises_private_error_when_html_signals_private():
    """No media item + private marker → DownloadError(is_private_content=True)."""
    from services.downloader import _extract_media_item
    import logging
    log = logging.LoggerAdapter(logging.getLogger("test"), {})

    html = _html_with_json_blocks(_private_user_block())
    with pytest.raises(DownloadError) as exc_info:
        _extract_media_item(html, log)

    assert exc_info.value.is_private_content is True
    assert exc_info.value.is_retryable is False


def test_extract_raises_retryable_error_when_no_private_signal():
    """No media item + no private marker → DownloadError(is_retryable=True) (existing behaviour)."""
    from services.downloader import _extract_media_item
    import logging
    log = logging.LoggerAdapter(logging.getLogger("test"), {})

    html = _html_with_json_blocks({"config": {"csrf_token": "abc"}})
    with pytest.raises(DownloadError) as exc_info:
        _extract_media_item(html, log)

    assert exc_info.value.is_retryable is True
    assert exc_info.value.is_private_content is False


def test_extract_returns_item_when_media_present_even_with_private_block():
    """If a valid media item IS found, private marker in other blocks is irrelevant."""
    from services.downloader import _extract_media_item
    import logging
    log = logging.LoggerAdapter(logging.getLogger("test"), {})

    # Both a private user block and a valid media block
    html = _html_with_json_blocks(_private_user_block(), _media_block())
    result = _extract_media_item(html, log)
    assert result["pk"] == "999"
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && source venv/bin/activate
pytest tests/test_downloader_private_detection.py -v
```

Expected: `ImportError: cannot import name '_html_signals_private_content'` for the helper tests; `DownloadError` raised with wrong flags for the routing tests.

- [ ] **Step 3: Add `_html_signals_private_content` to `downloader.py`**

In `backend/services/downloader.py`, add this function after `_walk_dicts` (around line 454, before the Stage 3 comment block):

```python
def _html_signals_private_content(html: str) -> bool:
    """Return True if any <script type=application/json> block contains a dict
    where ``is_private`` is True.

    Instagram serves private-account reel pages as HTTP 200 with user metadata
    JSON (including is_private=True) but no media payload. Scanning for this
    flag lets us distinguish a definitive private-content rejection from a
    transient parse failure.
    """
    selector = Selector(html)
    for raw in selector.css('script[type="application/json"]::text').getall():
        try:
            blob = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for node in _walk_dicts(blob):
            if node.get("is_private") is True:
                return True
    return False
```

- [ ] **Step 4: Update `_extract_media_item` to call the helper**

In `backend/services/downloader.py`, replace the final `log.error` + `raise DownloadError` block in `_extract_media_item` (currently lines 417–427):

```python
    if _html_signals_private_content(html):
        log.error(
            "JSON locate failed | candidates_scanned=%d | "
            "private_marker=True | reel is from a private account",
            candidates,
        )
        raise DownloadError(
            "Instagram returned a private-account page — no media payload present",
            is_retryable=False,
            is_private_content=True,
        )

    log.error(
        "JSON locate failed | candidates_scanned=%d | likely_cause=IG served "
        "degraded HTML (no JSON blob), changed their page structure, or "
        "returned a logged-out shell",
        candidates,
    )
    raise DownloadError(
        "could not locate reel media payload in HTML — Instagram likely changed "
        "their page structure or returned a degraded response",
        is_retryable=True,
    )
```

Note: `_extract_media_item`'s signature must also accept `html` so the helper can be called. The current signature is:

```python
def _extract_media_item(html: str, log: logging.LoggerAdapter) -> dict[str, Any]:
```

`html` is already the first parameter — no signature change needed.

- [ ] **Step 5: Run to confirm tests pass**

```bash
pytest tests/test_downloader_private_detection.py -v
```

Expected: 9 PASSED

- [ ] **Step 6: Run the full test suite to check for regressions**

```bash
pytest --tb=short -q
```

Expected: All previously passing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add backend/services/downloader.py backend/tests/test_downloader_private_detection.py
git commit -m "fix: detect private-account 200 pages before retrying download"
```

---

## What Changes End-to-End

Before this fix, sharing a private reel URL:
1. Share Extension POSTs → 202 (DB row inserted, task queued)
2. Celery: `_fetch_reel_html` returns 200 OK HTML
3. `_extract_media_item` finds no media → `DownloadError(is_retryable=True)`
4. Celery retries 3× (60s, 120s, 180s backoff)
5. After max retries → reel marked `status=failed` (row stays in DB)
6. No FCM push to user

After this fix:
1. Same up to step 2
2. `_extract_media_item` finds no media + detects `is_private=True` → `DownloadError(is_private_content=True)`
3. `process_reel` catches it → deletes reel row + FCM push ("Can't save this — private reel")
4. Returns immediately, no retries

## Edge Cases Covered

| Scenario | Result |
|---|---|
| Private account, page has user JSON with `is_private=True` | `is_private_content=True`, immediate rejection |
| Private account, page has NO JSON at all | Still `is_retryable=True` (can't distinguish from transient) |
| Public account, parse fails due to IG structure change | Still `is_retryable=True` (correct — transient) |
| Public account, media found even though other block has `is_private=True` | Media returned, no rejection |
| HTTP 401/403 | Existing check fires before `_extract_media_item` (unchanged) |
| Login-wall redirect | Existing check fires before `_extract_media_item` (unchanged) |
