# Thumbnail Permanent Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upload reel thumbnails to Supabase Storage during ingestion so `thumbnail_url` holds a permanent public URL instead of an expiring Instagram CDN URL.

**Architecture:** A new `services/storage.py` module handles the upload with exponential-backoff retry (3 retries: 2s→4s→8s) and falls back to the original Instagram CDN URL if all retries fail. `tasks.py` calls it as Step 15b, between download and the existing metadata `UPDATE`.

**Tech Stack:** supabase-py 2.9.1 (already installed), `time.sleep` for backoff (no new deps), pytest + `unittest.mock` for tests.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `supabase/migrations/20260530000003_thumbnails_bucket.sql` | Create | Public bucket + RLS read policy |
| `backend/services/storage.py` | Create | `upload_thumbnail()` — upload, retry, fallback, logs |
| `backend/tests/test_storage.py` | Create | Unit tests for `upload_thumbnail` |
| `backend/workers/tasks.py` | Modify | Import + Step 15b block + use permanent URL in UPDATE |
| `backend/tests/test_tasks_thumbnail_upload.py` | Create | Integration tests for Step 15b wiring |

---

## Task 1: Supabase Storage bucket migration

**Files:**
- Create: `supabase/migrations/20260530000003_thumbnails_bucket.sql`

- [ ] **Step 1: Write the migration**

```sql
-- supabase/migrations/20260530000003_thumbnails_bucket.sql
-- Public bucket for permanent thumbnail storage.
-- Writes use the service role key (bypasses RLS).
-- Reads are unauthenticated (iOS AsyncImage loads directly).

insert into storage.buckets (id, name, public)
values ('thumbnails', 'thumbnails', true)
on conflict (id) do nothing;

create policy "Public thumbnail read"
  on storage.objects for select
  using (bucket_id = 'thumbnails');
```

- [ ] **Step 2: Apply the migration**

```bash
cd /Users/deeptijain/Desktop/Deepti/Projects/ReelMind
supabase db push
```

Expected: migration applied with no errors.

- [ ] **Step 3: Verify bucket exists in Supabase dashboard**

Open Supabase → Storage → confirm `thumbnails` bucket is listed as Public.

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/20260530000003_thumbnails_bucket.sql
git commit -m "feat: add public thumbnails bucket to Supabase Storage"
```

---

## Task 2: `backend/services/storage.py` with tests (TDD)

**Files:**
- Create: `backend/services/storage.py`
- Create: `backend/tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_storage.py`:

```python
"""Tests for services.storage — Step 15b permanent thumbnail upload."""
from unittest.mock import MagicMock, mock_open, patch

import pytest


def _make_storage_mock(fail_count: int = 0):
    """Return a supabase mock whose upload fails `fail_count` times then succeeds."""
    mock_supabase = MagicMock()
    bucket = mock_supabase.storage.from_.return_value
    bucket.get_public_url.return_value = (
        "https://supabase.co/storage/v1/object/public/thumbnails/user-1/reel-1.jpg"
    )

    state = {"calls": 0}

    def upload_side_effect(*args, **kwargs):
        state["calls"] += 1
        if state["calls"] <= fail_count:
            raise Exception(f"StorageException: network error (call {state['calls']})")
        return MagicMock()

    bucket.upload.side_effect = upload_side_effect
    return mock_supabase


_PERMANENT_URL = (
    "https://supabase.co/storage/v1/object/public/thumbnails/user-1/reel-1.jpg"
)
_FALLBACK_URL = "https://scontent.cdninstagram.com/cdn/thumb.jpg"


@patch("services.storage.time.sleep")
@patch("services.storage.get_supabase")
@patch("builtins.open", mock_open(read_data=b"fake-image-bytes"))
def test_upload_success_returns_permanent_url(mock_get_supabase, mock_sleep):
    mock_get_supabase.return_value = _make_storage_mock(fail_count=0)

    from services.storage import upload_thumbnail

    result = upload_thumbnail(
        reel_id="reel-1",
        user_id="user-1",
        thumbnail_path="/tmp/reel-1.jpg",
        fallback_url=_FALLBACK_URL,
    )

    assert result == _PERMANENT_URL
    mock_sleep.assert_not_called()


@patch("services.storage.time.sleep")
@patch("services.storage.get_supabase")
@patch("builtins.open", mock_open(read_data=b"fake-image-bytes"))
def test_upload_retries_on_failure_then_succeeds(mock_get_supabase, mock_sleep):
    """Fails twice, succeeds on 3rd attempt — returns permanent URL, slept twice."""
    mock_get_supabase.return_value = _make_storage_mock(fail_count=2)

    from services.storage import upload_thumbnail

    result = upload_thumbnail(
        reel_id="reel-1",
        user_id="user-1",
        thumbnail_path="/tmp/reel-1.jpg",
        fallback_url=_FALLBACK_URL,
    )

    assert result == _PERMANENT_URL
    assert mock_sleep.call_count == 2


@patch("services.storage.time.sleep")
@patch("services.storage.get_supabase")
@patch("builtins.open", mock_open(read_data=b"fake-image-bytes"))
def test_upload_all_retries_exhausted_returns_fallback(mock_get_supabase, mock_sleep):
    """All 4 attempts fail — returns fallback CDN URL, slept 3 times."""
    mock_get_supabase.return_value = _make_storage_mock(fail_count=99)

    from services.storage import upload_thumbnail

    result = upload_thumbnail(
        reel_id="reel-1",
        user_id="user-1",
        thumbnail_path="/tmp/reel-1.jpg",
        fallback_url=_FALLBACK_URL,
    )

    assert result == _FALLBACK_URL
    assert mock_sleep.call_count == 3  # 3 sleeps between 4 attempts


@patch("services.storage.time.sleep")
@patch("services.storage.get_supabase")
@patch("builtins.open", mock_open(read_data=b"fake-image-bytes"))
def test_upload_all_retries_exhausted_no_fallback_returns_none(
    mock_get_supabase, mock_sleep
):
    """All attempts fail with no fallback_url provided — returns None."""
    mock_get_supabase.return_value = _make_storage_mock(fail_count=99)

    from services.storage import upload_thumbnail

    result = upload_thumbnail(
        reel_id="reel-1",
        user_id="user-1",
        thumbnail_path="/tmp/reel-1.jpg",
        fallback_url=None,
    )

    assert result is None


@patch("services.storage.time.sleep")
@patch("services.storage.get_supabase")
@patch("builtins.open", mock_open(read_data=b"fake-image-bytes"))
def test_storage_path_uses_user_and_reel_ids(mock_get_supabase, mock_sleep):
    """Upload path is '{user_id}/{reel_id}.jpg'."""
    mock_supabase = _make_storage_mock(fail_count=0)
    mock_get_supabase.return_value = mock_supabase

    from services.storage import upload_thumbnail

    upload_thumbnail(
        reel_id="reel-abc",
        user_id="user-xyz",
        thumbnail_path="/tmp/reel-abc.jpg",
        fallback_url=None,
    )

    upload_call = mock_supabase.storage.from_.return_value.upload.call_args
    assert upload_call.kwargs["path"] == "user-xyz/reel-abc.jpg"
```

- [ ] **Step 2: Run tests to confirm they fail (module not found)**

```bash
cd /Users/deeptijain/Desktop/Deepti/Projects/ReelMind/backend && source venv/bin/activate
python -m pytest tests/test_storage.py -v
```

Expected: `ModuleNotFoundError: No module named 'services.storage'`

- [ ] **Step 3: Implement `backend/services/storage.py`**

```python
"""Supabase Storage helpers — permanent thumbnail upload (Step 15b)."""
from __future__ import annotations

import logging
import time

from supabase_client import get_supabase

log = logging.getLogger(__name__)

_BUCKET = "thumbnails"
_MAX_ATTEMPTS = 4  # 1 initial + 3 retries; delays: 2s → 4s → 8s


def upload_thumbnail(
    reel_id: str,
    user_id: str,
    thumbnail_path: str,
    fallback_url: str | None = None,
) -> str | None:
    """Upload a local thumbnail file to Supabase Storage.

    Returns the permanent public URL on success, or fallback_url after
    exhausting retries (which may itself be None).
    """
    storage_path = f"{user_id}/{reel_id}.jpg"
    log.info(
        "storage | uploading thumbnail | reel_id=%s | local_path=%s | storage_path=%s",
        reel_id,
        thumbnail_path,
        storage_path,
    )

    with open(thumbnail_path, "rb") as fh:
        file_bytes = fh.read()

    supabase = get_supabase()

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            supabase.storage.from_(_BUCKET).upload(
                path=storage_path,
                file=file_bytes,
                file_options={"content-type": "image/jpeg", "upsert": "true"},
            )
            public_url: str = supabase.storage.from_(_BUCKET).get_public_url(
                storage_path
            )
            log.info(
                "storage | upload success | reel_id=%s | public_url=%s",
                reel_id,
                public_url,
            )
            return public_url
        except Exception as exc:
            backoff = 2**attempt  # 2, 4, 8 seconds
            if attempt < _MAX_ATTEMPTS:
                log.warning(
                    "storage | upload attempt failed (%d/%d) | reel_id=%s"
                    " | error=%s | retrying in %ds",
                    attempt,
                    _MAX_ATTEMPTS,
                    reel_id,
                    exc,
                    backoff,
                )
                time.sleep(backoff)
            else:
                log.warning(
                    "storage | upload attempt failed (%d/%d) | reel_id=%s"
                    " | error=%s | falling back to CDN URL",
                    attempt,
                    _MAX_ATTEMPTS,
                    reel_id,
                    exc,
                )

    log.warning(
        "storage | all retries exhausted | reel_id=%s | using fallback_url=%s",
        reel_id,
        fallback_url,
    )
    return fallback_url
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
python -m pytest tests/test_storage.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/storage.py backend/tests/test_storage.py
git commit -m "feat: add storage service for permanent thumbnail upload (Step 15b)"
```

---

## Task 3: Wire `upload_thumbnail` into `workers/tasks.py`

**Files:**
- Create: `backend/tests/test_tasks_thumbnail_upload.py`
- Modify: `backend/workers/tasks.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_tasks_thumbnail_upload.py`:

```python
"""Tests for Step 15b — thumbnail upload wired into workers/tasks.py."""
from unittest.mock import MagicMock, patch, call

import pytest


def _make_supabase_mock(user_id: str = "user-1"):
    mock_db = MagicMock()
    # .table(...).select(...).eq(...).single().execute().data
    select_result = (
        mock_db.table.return_value
        .select.return_value
        .eq.return_value
        .single.return_value
        .execute.return_value
    )
    select_result.data = {
        "url": "https://instagram.com/reel/ABC/",
        "user_id": user_id,
        "status": "queued",
        "fcm_token": None,
    }
    mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
        None
    )
    mock_db.table.return_value.delete.return_value.eq.return_value.execute.return_value = (
        None
    )
    return mock_db


def _make_task_self(retries: int = 0, max_retries: int = 3):
    task_self = MagicMock()
    task_self.request.retries = retries
    task_self.max_retries = max_retries
    from celery.exceptions import Retry
    task_self.retry.side_effect = Retry()
    return task_self


def _make_download_result(thumbnail_path: str | None = "/tmp/reel-1.jpg"):
    result = MagicMock()
    result.audio_path = None
    result.temp_dir = "/tmp/reel_test"
    result.thumbnail_path = thumbnail_path
    result.metadata.creator_handle = "testuser"
    result.metadata.hashtags = []
    result.metadata.caption = "test caption"
    result.metadata.thumbnail_url = "https://scontent.cdninstagram.com/cdn/thumb.jpg"
    result.metadata.user.is_private = False
    result.metadata.product_type = "clips"
    return result


_PERMANENT_URL = (
    "https://supabase.co/storage/v1/object/public/thumbnails/user-1/reel-1.jpg"
)
_CDN_URL = "https://scontent.cdninstagram.com/cdn/thumb.jpg"


def test_step15b_calls_upload_thumbnail_and_stores_permanent_url():
    """When thumbnail_path is present, upload_thumbnail is called and the
    permanent URL it returns is stored in the DB — not the original CDN URL."""
    from workers.tasks import process_reel
    from services.signal_builder import NoSignalError

    mock_db = _make_supabase_mock()

    with (
        patch("workers.tasks.get_supabase", return_value=mock_db),
        patch("workers.tasks.download_reel", return_value=_make_download_result()),
        patch("workers.tasks.upload_thumbnail", return_value=_PERMANENT_URL) as mock_upload,
        patch("workers.tasks.build_classification_signal", side_effect=NoSignalError("no signal")),
    ):
        process_reel(_make_task_self(), reel_id="reel-1")

    mock_upload.assert_called_once_with(
        reel_id="reel-1",
        user_id="user-1",
        thumbnail_path="/tmp/reel-1.jpg",
        fallback_url=_CDN_URL,
    )

    update_payloads = [
        c.args[0]
        for c in mock_db.table.return_value.update.call_args_list
        if c.args and "thumbnail_url" in c.args[0]
    ]
    assert len(update_payloads) == 1, f"Expected 1 thumbnail_url update, got: {update_payloads}"
    assert update_payloads[0]["thumbnail_url"] == _PERMANENT_URL


def test_step15b_skips_upload_when_no_thumbnail_path():
    """When thumbnail_path is None, upload_thumbnail is NOT called and the
    original CDN URL (or None) is used in the DB update."""
    from workers.tasks import process_reel
    from services.signal_builder import NoSignalError

    mock_db = _make_supabase_mock()
    download_result = _make_download_result(thumbnail_path=None)
    download_result.metadata.thumbnail_url = None  # no URL either

    with (
        patch("workers.tasks.get_supabase", return_value=mock_db),
        patch("workers.tasks.download_reel", return_value=download_result),
        patch("workers.tasks.upload_thumbnail") as mock_upload,
        patch("workers.tasks.build_classification_signal", side_effect=NoSignalError("no signal")),
    ):
        process_reel(_make_task_self(), reel_id="reel-1")

    mock_upload.assert_not_called()

    update_payloads = [
        c.args[0]
        for c in mock_db.table.return_value.update.call_args_list
        if c.args and "thumbnail_url" in c.args[0]
    ]
    assert len(update_payloads) == 1
    assert update_payloads[0]["thumbnail_url"] is None
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_tasks_thumbnail_upload.py -v
```

Expected: `ImportError: cannot import name 'upload_thumbnail' from 'workers.tasks'` (not imported yet).

- [ ] **Step 3: Add import to `workers/tasks.py`**

In `backend/workers/tasks.py`, add to the existing imports block (after the other `from services.*` imports):

```python
from services.storage import upload_thumbnail
```

- [ ] **Step 4: Add Step 15b block in `workers/tasks.py`**

Find this block (around line 132):

```python
        meta = download_result.metadata
        log.info(
            "step 15 | persisting metadata | creator=@%s | hashtags=%d | "
            "caption_chars=%d | thumb=%s",
            meta.creator_handle,
            len(meta.hashtags),
            len(meta.caption or ""),
            bool(meta.thumbnail_url),
        )
        supabase.table("reels").update({
            "caption": meta.caption,
            "hashtags": meta.hashtags,
            "creator_handle": meta.creator_handle or None,
            "thumbnail_url": meta.thumbnail_url,
        }).eq("id", reel_id).execute()
        log.info("step 15 | metadata saved to DB")
```

Replace it with:

```python
        meta = download_result.metadata
        log.info(
            "step 15 | persisting metadata | creator=@%s | hashtags=%d | "
            "caption_chars=%d | thumb=%s",
            meta.creator_handle,
            len(meta.hashtags),
            len(meta.caption or ""),
            bool(meta.thumbnail_url),
        )

        # ------------------------------------------------------------------
        # Step 15b — upload thumbnail to permanent Supabase Storage
        # ------------------------------------------------------------------
        permanent_thumb_url = meta.thumbnail_url  # Instagram CDN URL as default fallback
        if download_result.thumbnail_path:
            log.info(
                "step 15b | uploading thumbnail to storage | reel_id=%s", reel_id
            )
            permanent_thumb_url = upload_thumbnail(
                reel_id=reel_id,
                user_id=reel_data["user_id"],
                thumbnail_path=download_result.thumbnail_path,
                fallback_url=meta.thumbnail_url,
            )
            log.info(
                "step 15b | thumbnail url resolved | reel_id=%s | url=%s",
                reel_id,
                permanent_thumb_url,
            )
        else:
            log.warning(
                "step 15b | no thumbnail_path, skipping storage upload | reel_id=%s",
                reel_id,
            )

        supabase.table("reels").update({
            "caption": meta.caption,
            "hashtags": meta.hashtags,
            "creator_handle": meta.creator_handle or None,
            "thumbnail_url": permanent_thumb_url,
        }).eq("id", reel_id).execute()
        log.info("step 15 | metadata saved to DB")
```

- [ ] **Step 5: Run the new tests**

```bash
python -m pytest tests/test_tasks_thumbnail_upload.py -v
```

Expected: both tests PASS.

- [ ] **Step 6: Run the full test suite to check for regressions**

```bash
python -m pytest tests/ -v
```

Expected: all existing tests still PASS (the only change to tasks.py is adding Step 15b; existing mocks set `thumbnail_path` on the download result mock so the new branch is exercised but doesn't break anything).

- [ ] **Step 7: Commit**

```bash
git add backend/workers/tasks.py backend/tests/test_tasks_thumbnail_upload.py
git commit -m "feat: wire thumbnail upload into pipeline as Step 15b"
```
