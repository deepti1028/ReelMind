# Private Reel & Non-Reel URL Rejection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject non-Instagram, non-reel, and private-account URLs at the earliest possible point, leave zero DB trace, and notify the user with a clear, descriptive FCM push every time.

**Architecture:** URL pattern validation in `reels.py` gates the DB insert; private-reel errors in the Celery pipeline trigger a row delete + FCM push; the Share Extension updates its labels on 422 responses using the existing duplicate-detection pattern.

**Tech Stack:** Python/FastAPI, Celery, Supabase, Firebase FCM, Swift/UIKit (Share Extension)

---

## File Map

| File | Change |
|---|---|
| `backend/services/downloader.py` | Add `is_private_content` flag to `DownloadError`; mark 401/403 and login-wall raises |
| `backend/api/v1/reels.py` | Add `_is_instagram_reel_url()` helper; wire 422 rejection before DB insert |
| `backend/workers/tasks.py` | Add `notify_invalid_url` task; add private-content branch in `process_reel` Step 15; add post-download `is_private` + `product_type` checks |
| `URL Sharing module/ShareViewController.swift` | Handle 422 response; update `applyResultLabels()` |
| `backend/tests/test_download_error.py` | New — unit tests for `DownloadError.is_private_content` |
| `backend/tests/test_reels_url_validation.py` | New — unit tests for `_is_instagram_reel_url` + endpoint 422 tests |
| `backend/tests/test_tasks_invalid_url.py` | New — unit tests for `notify_invalid_url` Celery task |
| `backend/tests/test_tasks_private_reel.py` | New — unit tests for private-content handling in `process_reel` |

---

### Task 1: Add `is_private_content` flag to `DownloadError`

**Files:**
- Modify: `backend/services/downloader.py` (lines 160–170 — `DownloadError` class and `_fetch_reel_html`)
- Test: `backend/tests/test_download_error.py` (create new)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_download_error.py`:

```python
from services.downloader import DownloadError


def test_download_error_is_private_content_defaults_false():
    err = DownloadError("some error")
    assert err.is_private_content is False


def test_download_error_is_private_content_can_be_set_true():
    err = DownloadError("private", is_private_content=True)
    assert err.is_private_content is True
    assert err.is_retryable is False


def test_download_error_all_flags():
    err = DownloadError("both", is_retryable=True, is_private_content=True)
    assert err.is_retryable is True
    assert err.is_private_content is True
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && source venv/bin/activate
pytest tests/test_download_error.py -v
```

Expected: `FAILED` — `DownloadError.__init__() got an unexpected keyword argument 'is_private_content'`

- [ ] **Step 3: Add `is_private_content` to `DownloadError`**

In `backend/services/downloader.py`, replace the `DownloadError` class (currently lines 160–170):

```python
class DownloadError(Exception):
    """Errors raised by the downloader.

    `is_retryable` mirrors the contract used by the Celery task in
    workers/tasks.py — transient (network) failures get retried, permanent
    failures (private/deleted/region-blocked) do not.

    `is_private_content` is True when the failure is specifically because the
    content is private or login-walled — the Celery task uses this to delete
    the reel row instead of marking it failed.
    """

    def __init__(
        self,
        message: str,
        *,
        is_retryable: bool = False,
        is_private_content: bool = False,
    ):
        super().__init__(message)
        self.is_retryable = is_retryable
        self.is_private_content = is_private_content
```

- [ ] **Step 4: Run to confirm tests pass**

```bash
pytest tests/test_download_error.py -v
```

Expected: 3 PASSED

- [ ] **Step 5: Mark the two private-content raise sites in `_fetch_reel_html`**

In `backend/services/downloader.py`, find the 401/403 raise (around line 318) and replace:

```python
    if resp.status_code in (401, 403):
        log.error(
            "fetch failed | status=%s | likely_cause=private reel, login-walled, "
            "or IG rate-limited this IP",
            resp.status_code,
        )
        raise DownloadError(
            f"Instagram HTTP {resp.status_code} — private reel / login required / IP rate-limited",
            is_retryable=False,
            is_private_content=True,
        )
```

Find the login-wall redirect raise (around line 362) and replace:

```python
    if "/accounts/login" in resp.url or '"LoginAndSignupPage"' in resp.text:
        log.error(
            "fetch failed | status=200 | likely_cause=login-wall redirect "
            "(reel is private or IG demanding session)"
        )
        raise DownloadError(
            "Instagram redirected to login — reel is private or session required",
            is_retryable=False,
            is_private_content=True,
        )
```

- [ ] **Step 6: Re-run all download error tests to confirm still passing**

```bash
pytest tests/test_download_error.py -v
```

Expected: 3 PASSED

- [ ] **Step 7: Commit**

```bash
git add backend/services/downloader.py backend/tests/test_download_error.py
git commit -m "feat: add is_private_content flag to DownloadError"
```

---

### Task 2: Add `_is_instagram_reel_url` URL validator

**Files:**
- Modify: `backend/api/v1/reels.py`
- Test: `backend/tests/test_reels_url_validation.py` (create new)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_reels_url_validation.py`:

```python
from api.v1.reels import _is_instagram_reel_url


def test_valid_reel_url_with_www():
    assert _is_instagram_reel_url("https://www.instagram.com/reel/ABC123") is None


def test_valid_reel_url_no_www():
    assert _is_instagram_reel_url("https://instagram.com/reel/ABC123") is None


def test_valid_reels_plural_url():
    assert _is_instagram_reel_url("https://www.instagram.com/reels/ABC123") is None


def test_valid_reel_url_with_trailing_slash():
    assert _is_instagram_reel_url("https://www.instagram.com/reel/ABC123/") is None


def test_non_instagram_tiktok():
    assert _is_instagram_reel_url("https://tiktok.com/video/123") == "not_instagram"


def test_non_instagram_youtube():
    assert _is_instagram_reel_url("https://youtube.com/shorts/xyz") == "not_instagram"


def test_instagram_story():
    assert _is_instagram_reel_url("https://www.instagram.com/stories/username/123/") == "not_a_reel"


def test_instagram_post():
    assert _is_instagram_reel_url("https://www.instagram.com/p/ABC123/") == "not_a_reel"


def test_instagram_tv():
    assert _is_instagram_reel_url("https://www.instagram.com/tv/ABC123/") == "not_a_reel"


def test_instagram_profile():
    assert _is_instagram_reel_url("https://www.instagram.com/someuser/") == "not_a_reel"
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && source venv/bin/activate
pytest tests/test_reels_url_validation.py -v
```

Expected: `FAILED` — `ImportError: cannot import name '_is_instagram_reel_url'`

- [ ] **Step 3: Add `_is_instagram_reel_url` to `reels.py`**

In `backend/api/v1/reels.py`, add this function directly after the `_normalize_url` function (around line 25, before the `@router.post` decorator). `urlparse` is already imported at the top of the file.

```python
def _is_instagram_reel_url(url_str: str) -> str | None:
    """Returns None if the URL is a valid Instagram reel URL.

    Returns a reason string ('not_instagram' or 'not_a_reel') if it should
    be rejected before touching the database.
    """
    parsed = urlparse(url_str)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host != "instagram.com":
        return "not_instagram"
    path = parsed.path.rstrip("/")
    if not (path.startswith("/reel/") or path.startswith("/reels/")):
        return "not_a_reel"
    return None
```

- [ ] **Step 4: Run to confirm tests pass**

```bash
pytest tests/test_reels_url_validation.py -v
```

Expected: 10 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/api/v1/reels.py backend/tests/test_reels_url_validation.py
git commit -m "feat: add _is_instagram_reel_url URL validator"
```

---

### Task 3: Add `notify_invalid_url` Celery task

**Files:**
- Modify: `backend/workers/tasks.py`
- Test: `backend/tests/test_tasks_invalid_url.py` (create new)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_tasks_invalid_url.py`:

```python
from unittest.mock import MagicMock, patch


def _make_profiles_db(fcm_token="test-fcm-token"):
    db = MagicMock()
    (
        db.table.return_value
        .select.return_value
        .eq.return_value
        .maybe_single.return_value
        .execute.return_value
        .data
    ) = {"fcm_token": fcm_token}
    return db


def test_notify_invalid_url_not_instagram_sends_push():
    from workers.tasks import notify_invalid_url

    with patch("workers.tasks.get_supabase", return_value=_make_profiles_db()):
        with patch("workers.tasks.send_push_notification") as mock_push:
            notify_invalid_url("user-1", "not_instagram")

    mock_push.assert_called_once()
    kwargs = mock_push.call_args[1]
    assert kwargs["title"] == "Can't save this"
    assert "Instagram" in kwargs["body"]
    assert kwargs["data"]["reason"] == "not_instagram"


def test_notify_invalid_url_not_a_reel_sends_push():
    from workers.tasks import notify_invalid_url

    with patch("workers.tasks.get_supabase", return_value=_make_profiles_db()):
        with patch("workers.tasks.send_push_notification") as mock_push:
            notify_invalid_url("user-1", "not_a_reel")

    mock_push.assert_called_once()
    kwargs = mock_push.call_args[1]
    assert kwargs["title"] == "Can't save this"
    assert "Reel" in kwargs["body"]
    assert kwargs["data"]["reason"] == "not_a_reel"


def test_notify_invalid_url_no_fcm_token_does_not_raise():
    from workers.tasks import notify_invalid_url

    db = MagicMock()
    (
        db.table.return_value
        .select.return_value
        .eq.return_value
        .maybe_single.return_value
        .execute.return_value
        .data
    ) = None

    with patch("workers.tasks.get_supabase", return_value=db):
        with patch("workers.tasks.send_push_notification") as mock_push:
            notify_invalid_url("user-1", "not_instagram")

    mock_push.assert_called_once()
    assert mock_push.call_args[1]["fcm_token"] is None


def test_notify_invalid_url_db_failure_does_not_raise():
    from workers.tasks import notify_invalid_url

    db = MagicMock()
    (
        db.table.return_value
        .select.return_value
        .eq.return_value
        .maybe_single.return_value
        .execute
        .side_effect
    ) = Exception("DB down")

    with patch("workers.tasks.get_supabase", return_value=db):
        with patch("workers.tasks.send_push_notification") as mock_push:
            notify_invalid_url("user-1", "not_instagram")

    mock_push.assert_called_once()
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && source venv/bin/activate
pytest tests/test_tasks_invalid_url.py -v
```

Expected: `FAILED` — `ImportError: cannot import name 'notify_invalid_url'`

- [ ] **Step 3: Add `notify_invalid_url` to `workers/tasks.py`**

In `backend/workers/tasks.py`, add this task after the `notify_duplicate_reel` task (around line 437, before the `ping` task):

```python
@celery_app.task(name="workers.tasks.notify_invalid_url")
def notify_invalid_url(user_id: str, reason: str) -> bool:
    """Send FCM push when a user submits a URL that isn't a public Instagram Reel.

    `reason` is 'not_instagram' or 'not_a_reel'. Non-fatal: any failure is
    caught and logged.
    """
    _MESSAGES = {
        "not_instagram": (
            "Can't save this",
            "That doesn't look like an Instagram link. ReelMind only saves Instagram Reels.",
        ),
        "not_a_reel": (
            "Can't save this",
            "That looks like a post or story, not a Reel. Find the Reel in Instagram and share it from there.",
        ),
    }
    supabase = get_supabase()
    _fcm_token: str | None = None
    try:
        _profile = (
            supabase.table("profiles")
            .select("fcm_token")
            .eq("id", user_id)
            .maybe_single()
            .execute()
        )
        if _profile.data:
            _fcm_token = _profile.data.get("fcm_token")
    except Exception as exc:
        logger.warning("notify_invalid_url | could not fetch fcm_token | %s", exc)

    title, body = _MESSAGES.get(
        reason,
        ("Can't save this", "ReelMind only saves Instagram Reels."),
    )
    return send_push_notification(
        fcm_token=_fcm_token,
        title=title,
        body=body,
        data={"type": "invalid_url", "reason": reason},
    )
```

- [ ] **Step 4: Run to confirm tests pass**

```bash
pytest tests/test_tasks_invalid_url.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/workers/tasks.py backend/tests/test_tasks_invalid_url.py
git commit -m "feat: add notify_invalid_url Celery task"
```

---

### Task 4: Wire 422 rejection into `create_reel` endpoint

**Files:**
- Modify: `backend/api/v1/reels.py`
- Test: `backend/tests/test_reels_url_validation.py` (extend existing)

- [ ] **Step 1: Write the failing endpoint tests**

Append to `backend/tests/test_reels_url_validation.py`:

```python
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from main import app
from api.deps import get_current_user_id


async def _mock_user_id():
    return "user-1"


def test_create_reel_422_for_non_instagram_url():
    app.dependency_overrides[get_current_user_id] = _mock_user_id
    client = TestClient(app)

    with patch("api.v1.reels.notify_invalid_url") as mock_task:
        mock_task.delay = MagicMock()
        response = client.post(
            "/api/v1/reels",
            json={"url": "https://tiktok.com/video/123", "auto_categorise": True},
        )

    app.dependency_overrides.clear()
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["reason"] == "not_instagram"
    assert "Instagram" in detail["message"]
    mock_task.delay.assert_called_once_with("user-1", "not_instagram")


def test_create_reel_422_for_instagram_story():
    app.dependency_overrides[get_current_user_id] = _mock_user_id
    client = TestClient(app)

    with patch("api.v1.reels.notify_invalid_url") as mock_task:
        mock_task.delay = MagicMock()
        response = client.post(
            "/api/v1/reels",
            json={
                "url": "https://www.instagram.com/stories/someuser/123/",
                "auto_categorise": True,
            },
        )

    app.dependency_overrides.clear()
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["reason"] == "not_a_reel"
    mock_task.delay.assert_called_once_with("user-1", "not_a_reel")
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && source venv/bin/activate
pytest tests/test_reels_url_validation.py::test_create_reel_422_for_non_instagram_url tests/test_reels_url_validation.py::test_create_reel_422_for_instagram_story -v
```

Expected: `FAILED` — endpoint returns 202 or 500 (validation guard not yet added, so request proceeds past URL check)

- [ ] **Step 3: Update the import in `reels.py` to include `notify_invalid_url`**

In `backend/api/v1/reels.py`, replace:

```python
from workers.tasks import notify_duplicate_reel, process_reel
```

with:

```python
from workers.tasks import notify_duplicate_reel, notify_invalid_url, process_reel
```

- [ ] **Step 4: Add the 422 guard in `create_reel`**

In `backend/api/v1/reels.py`, in `create_reel`, add immediately after the line `url_str = _normalize_url(str(payload.url))` (around line 40):

```python
    rejection_reason = _is_instagram_reel_url(url_str)
    if rejection_reason:
        notify_invalid_url.delay(user_id, rejection_reason)
        _rejection_messages = {
            "not_instagram": "That doesn't look like an Instagram link. ReelMind only saves Instagram Reels.",
            "not_a_reel": "That looks like a post or story, not a Reel. Find the Reel in Instagram and share it from there.",
        }
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "reason": rejection_reason,
                "message": _rejection_messages[rejection_reason],
            },
        )
```

- [ ] **Step 5: Run the endpoint tests**

```bash
pytest tests/test_reels_url_validation.py -v
```

Expected: 12 PASSED (10 unit + 2 endpoint)

- [ ] **Step 6: Run the full test suite to check for regressions**

```bash
pytest --tb=short -q
```

Expected: All previously passing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add backend/api/v1/reels.py backend/tests/test_reels_url_validation.py
git commit -m "feat: reject non-reel URLs at API level with 422 + FCM notification"
```

---

### Task 5: Handle private content in `process_reel`

**Files:**
- Modify: `backend/workers/tasks.py`
- Test: `backend/tests/test_tasks_private_reel.py` (create new)

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_tasks_private_reel.py`:

```python
from unittest.mock import MagicMock, patch

from services.downloader import DownloadError


def _make_supabase_mock(url="https://www.instagram.com/reel/ABC/"):
    db = MagicMock()
    (
        db.table.return_value
        .select.return_value
        .eq.return_value
        .single.return_value
        .execute.return_value
        .data
    ) = {"url": url, "user_id": "user-1", "status": "processing"}
    db.table.return_value.update.return_value.eq.return_value.execute.return_value = None
    db.table.return_value.delete.return_value.eq.return_value.execute.return_value = None
    return db


def _make_task_self(retries=0):
    task_self = MagicMock()
    task_self.request.retries = retries
    task_self.max_retries = 3
    return task_self


def _make_download_result(is_private=False, product_type="clips"):
    r = MagicMock()
    r.audio_path = None
    r.temp_dir = "/tmp/reel_test"
    r.metadata.creator_handle = "testuser"
    r.metadata.hashtags = []
    r.metadata.caption = "Test caption"
    r.metadata.thumbnail_url = None
    r.metadata.user.is_private = is_private
    r.metadata.product_type = product_type
    return r


def test_private_content_download_error_deletes_row_and_notifies():
    """DownloadError(is_private_content=True) → row deleted, FCM push, no retry."""
    from workers.tasks import process_reel

    task_self = _make_task_self()
    mock_db = _make_supabase_mock()

    with patch("workers.tasks.get_supabase", return_value=mock_db):
        with patch(
            "workers.tasks.download_reel",
            side_effect=DownloadError("private", is_private_content=True),
        ):
            with patch("workers.tasks.send_push_notification") as mock_push:
                result = process_reel(task_self, "reel-123")

    mock_db.table.return_value.delete.return_value.eq.return_value.execute.assert_called_once()
    mock_push.assert_called_once()
    assert mock_push.call_args[1]["title"] == "Can't save this"
    assert "private" in mock_push.call_args[1]["body"].lower()
    assert result["status"] == "rejected_private"


def test_non_retryable_download_error_without_private_flag_marks_failed():
    """DownloadError(is_private_content=False) → existing failed path, row NOT deleted."""
    from workers.tasks import process_reel

    # retries=3 == max_retries → _handle_pipeline_error skips retry, marks failed
    task_self = _make_task_self(retries=3)
    mock_db = _make_supabase_mock()

    with patch("workers.tasks.get_supabase", return_value=mock_db):
        with patch(
            "workers.tasks.download_reel",
            side_effect=DownloadError("404", is_retryable=False),
        ):
            with patch("workers.tasks.send_push_notification"):
                # _handle_pipeline_error calls send_push_notification — must be mocked
                process_reel(task_self, "reel-123")

    mock_db.table.return_value.delete.return_value.eq.return_value.execute.assert_not_called()


def test_is_private_flag_in_metadata_deletes_row_and_notifies():
    """metadata.user.is_private=True → row deleted, private FCM push."""
    from workers.tasks import process_reel

    task_self = _make_task_self()
    mock_db = _make_supabase_mock()

    with patch("workers.tasks.get_supabase", return_value=mock_db):
        with patch(
            "workers.tasks.download_reel",
            return_value=_make_download_result(is_private=True, product_type="clips"),
        ):
            with patch("workers.tasks.send_push_notification") as mock_push:
                result = process_reel(task_self, "reel-123")

    mock_db.table.return_value.delete.return_value.eq.return_value.execute.assert_called_once()
    mock_push.assert_called_once()
    assert mock_push.call_args[1]["title"] == "Can't save this"
    assert "private" in mock_push.call_args[1]["body"].lower()
    assert result["status"] == "rejected_private"


def test_wrong_product_type_deletes_row_and_notifies():
    """metadata.product_type='feed' → row deleted, not-a-reel FCM push."""
    from workers.tasks import process_reel

    task_self = _make_task_self()
    mock_db = _make_supabase_mock()

    with patch("workers.tasks.get_supabase", return_value=mock_db):
        with patch(
            "workers.tasks.download_reel",
            return_value=_make_download_result(is_private=False, product_type="feed"),
        ):
            with patch("workers.tasks.send_push_notification") as mock_push:
                result = process_reel(task_self, "reel-123")

    mock_db.table.return_value.delete.return_value.eq.return_value.execute.assert_called_once()
    mock_push.assert_called_once()
    assert mock_push.call_args[1]["title"] == "Can't save this"
    assert result["status"] == "rejected_not_reel"


def test_valid_public_reel_does_not_delete_row():
    """product_type='clips', is_private=False → pipeline continues, row NOT deleted."""
    from workers.tasks import process_reel

    task_self = _make_task_self()
    mock_db = _make_supabase_mock()

    with patch("workers.tasks.get_supabase", return_value=mock_db):
        with patch(
            "workers.tasks.download_reel",
            return_value=_make_download_result(is_private=False, product_type="clips"),
        ):
            with patch("workers.tasks.transcribe_audio", side_effect=Exception("stop")):
                try:
                    process_reel(task_self, "reel-123")
                except Exception:
                    pass

    mock_db.table.return_value.delete.return_value.eq.return_value.execute.assert_not_called()


def test_none_product_type_does_not_delete_row():
    """product_type=None (unknown) → pipeline continues, row NOT deleted."""
    from workers.tasks import process_reel

    task_self = _make_task_self()
    mock_db = _make_supabase_mock()

    with patch("workers.tasks.get_supabase", return_value=mock_db):
        with patch(
            "workers.tasks.download_reel",
            return_value=_make_download_result(is_private=False, product_type=None),
        ):
            with patch("workers.tasks.transcribe_audio", side_effect=Exception("stop")):
                try:
                    process_reel(task_self, "reel-123")
                except Exception:
                    pass

    mock_db.table.return_value.delete.return_value.eq.return_value.execute.assert_not_called()
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd backend && source venv/bin/activate
pytest tests/test_tasks_private_reel.py -v
```

Expected: Several FAILs — `delete` is not called where expected, wrong return status.

- [ ] **Step 3: Replace the DownloadError catch in `process_reel` Step 15**

In `backend/workers/tasks.py`, find the Step 15 `except DownloadError` block (around line 110–116):

```python
        except DownloadError as exc:
            log.warning(
                "download failed | retryable=%s | %s", exc.is_retryable, exc
            )
            return _handle_pipeline_error(
                self, supabase, reel_id, exc, exc.is_retryable, log, _fcm_token
            )
```

Replace with:

```python
        except DownloadError as exc:
            log.warning(
                "download failed | retryable=%s | private=%s | %s",
                exc.is_retryable,
                exc.is_private_content,
                exc,
            )
            if exc.is_private_content:
                log.warning("step 15 | private content — deleting reel row | reel_id=%s", reel_id)
                supabase.table("reels").delete().eq("id", reel_id).execute()
                send_push_notification(
                    fcm_token=_fcm_token,
                    title="Can't save this",
                    body="That's a private reel — ReelMind can only save Reels from public accounts.",
                    data={"type": "rejected_private"},
                )
                return {"reel_id": reel_id, "status": "rejected_private"}
            return _handle_pipeline_error(
                self, supabase, reel_id, exc, exc.is_retryable, log, _fcm_token
            )
```

- [ ] **Step 4: Add post-download checks after the Step 15 metadata persist block**

In `backend/workers/tasks.py`, find this line (around line 133):

```python
        log.info("step 15 | metadata saved to DB")
```

Insert the following block immediately after it (before the `# Step 16` comment):

```python
        # Post-download guards — private account or wrong content type means
        # zero trace: delete the row and push a descriptive notification.
        if meta.user.is_private:
            log.warning(
                "step 15 | private account | creator=@%s — deleting row",
                meta.creator_handle,
            )
            supabase.table("reels").delete().eq("id", reel_id).execute()
            send_push_notification(
                fcm_token=_fcm_token,
                title="Can't save this",
                body="That's a private reel — ReelMind can only save Reels from public accounts.",
                data={"type": "rejected_private"},
            )
            return {"reel_id": reel_id, "status": "rejected_private"}

        if meta.product_type and meta.product_type != "clips":
            log.warning(
                "step 15 | wrong product_type=%s | creator=@%s — deleting row",
                meta.product_type,
                meta.creator_handle,
            )
            supabase.table("reels").delete().eq("id", reel_id).execute()
            send_push_notification(
                fcm_token=_fcm_token,
                title="Can't save this",
                body="That doesn't look like a Reel — ReelMind only saves Instagram Reels.",
                data={"type": "rejected_not_reel"},
            )
            return {"reel_id": reel_id, "status": "rejected_not_reel"}
```

- [ ] **Step 5: Run all private reel tests**

```bash
pytest tests/test_tasks_private_reel.py -v
```

Expected: 6 PASSED

- [ ] **Step 6: Run the full test suite**

```bash
pytest --tb=short -q
```

Expected: All previously passing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add backend/workers/tasks.py backend/tests/test_tasks_private_reel.py
git commit -m "feat: delete reel row and notify user for private/non-reel content"
```

---

### Task 6: Handle 422 in Share Extension

**Files:**
- Modify: `URL Sharing module/ShareViewController.swift`
- No automated tests — verify manually

- [ ] **Step 1: Add rejection state properties**

In `ShareViewController.swift`, find the `duplicateSaveDetected` property (around line 139):

```swift
    // Set to true when the backend returns HTTP 200 (duplicate reel).
    // Read by applyResultLabels() to choose the right heading and subtitle.
    private var duplicateSaveDetected = false
```

Add two new properties directly below it:

```swift
    // Set to true when the backend returns HTTP 422 (invalid URL).
    private var saveRejected = false
    private var rejectTitle = "Not a Reel"
    private var rejectSubtitle = "ReelMind only saves Instagram Reels"
```

- [ ] **Step 2: Handle 422 in the network callback**

In `postURLToBackend`, find the `if status == 200` block (around line 495):

```swift
                if status == 200 {
                    DispatchQueue.main.async { [weak self] in
                        guard let self else { return }
                        self.duplicateSaveDetected = true
                        self.applyResultLabels()
                        Log.info("Duplicate reel — labels updated to 'Already saved'")
                    }
                }
```

Add a new block immediately after it:

```swift
                if status == 422 {
                    DispatchQueue.main.async { [weak self] in
                        guard let self else { return }
                        self.saveRejected = true
                        if let data = data,
                           let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                           let detail = json["detail"] as? [String: Any],
                           let reason = detail["reason"] as? String {
                            switch reason {
                            case "not_instagram":
                                self.rejectTitle = "Not Instagram"
                                self.rejectSubtitle = "ReelMind only saves Instagram Reels"
                            case "not_a_reel":
                                self.rejectTitle = "Not a Reel"
                                self.rejectSubtitle = "Open the Reel in Instagram and try again"
                            default:
                                break
                            }
                        }
                        self.applyResultLabels()
                        Log.warn("URL rejected by backend (422) — labels updated to '\(self.rejectTitle)'")
                    }
                }
```

- [ ] **Step 3: Update `applyResultLabels()` to handle the rejected state**

Find `applyResultLabels()` (around line 514):

```swift
    private func applyResultLabels() {
        if duplicateSaveDetected {
            savedTitleLabel.text = "Already saved"
            savedInfoLabel.text = "Check your ReelMind library"
        } else {
            savedTitleLabel.text = "Saved!"
            savedInfoLabel.text = "Reel added to ReelMind"
        }
    }
```

Replace with:

```swift
    private func applyResultLabels() {
        if saveRejected {
            savedTitleLabel.text = rejectTitle
            savedInfoLabel.text = rejectSubtitle
        } else if duplicateSaveDetected {
            savedTitleLabel.text = "Already saved"
            savedInfoLabel.text = "Check your ReelMind library"
        } else {
            savedTitleLabel.text = "Saved!"
            savedInfoLabel.text = "Reel added to ReelMind"
        }
    }
```

- [ ] **Step 4: Manual test — share a TikTok URL**

1. Build and run the app on device/simulator (⌘R in Xcode).
2. Open Safari, navigate to any TikTok URL.
3. Tap the share button → select ReelMind.
4. The sheet should slide up, show the spinner briefly, then transition to the saved state showing **"Not Instagram"** / *"ReelMind only saves Instagram Reels"*.
5. An FCM push notification should also arrive with title "Can't save this".

- [ ] **Step 5: Manual test — share an Instagram story link**

1. Open Instagram, find a story, tap the share icon → Copy Link.
2. Open Notes, paste the link, tap it so Safari opens it, then share → ReelMind.
3. Sheet should show **"Not a Reel"** / *"Open the Reel in Instagram and try again"*.
4. FCM push with same message should arrive.

- [ ] **Step 6: Manual test — share a valid public reel**

Confirm the existing happy path still shows **"Saved!"** / *"Reel added to ReelMind"*.

- [ ] **Step 7: Commit**

```bash
git add "URL Sharing module/ShareViewController.swift"
git commit -m "feat: update Share Extension labels for 422 URL rejection"
```

---

## Final Regression Check

- [ ] Run the full backend test suite one last time:

```bash
cd backend && source venv/bin/activate
pytest --tb=short -q
```

Expected: All tests pass.
