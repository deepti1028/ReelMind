# Step 22 — FCM Push Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Step 22 of the ingestion pipeline — push notifications via Firebase Cloud Messaging (FCM) for all terminal reel states, with iOS notification action buttons for the `pending_category` flow and a dedicated `CategoriseReelView` for in-app category selection.

**Architecture:** Backend gains `services/notifier.py` (Firebase Admin SDK wrapper, pure function, never pipeline-fatal) plus a new `PATCH /api/v1/profiles/fcm-token` endpoint. iOS gains notification action category registration, action handler dispatch, FCM token upload triggers, and a dedicated categorise screen. `send_push_notification()` gracefully no-ops if credentials are missing, so the pipeline remains testable end-to-end before APNs is verified on a real device.

**Tech Stack:** `firebase-admin` Python SDK (new dependency), Firebase Cloud Messaging, iOS `UserNotifications` framework, URLSession for background API calls from notification handlers.

**Context:**
- All backend commands run from `backend/` with `source venv/bin/activate`
- Tests: `pytest tests/ -v`
- Spec: `docs/superpowers/specs/2026-05-17-step22-fcm-design.md`
- `FIREBASE_SERVICE_ACCOUNT_JSON` is **already set** in local `backend/.env` (base64 of service account for project `reelmind-de362`) and in Render env vars
- The `.env.example` file has **already been updated** locally with a placeholder line for `FIREBASE_SERVICE_ACCOUNT_JSON` (working-tree change, not yet committed) — Task 1 commits it
- iOS verification is by Xcode build (`xcodebuild build` from CLI or ⌘B in Xcode). There is no XCTest suite — iOS changes are verified by build success and manual smoke tests.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `backend/requirements.txt` | Add `firebase-admin` |
| Modify | `backend/config.py` | Add `FIREBASE_SERVICE_ACCOUNT_JSON` config key |
| Modify | `backend/.env.example` | Commit pre-existing placeholder for the env var |
| Create | `backend/services/notifier.py` | Firebase Admin SDK send wrapper (pure function, graceful no-op) |
| Create | `backend/tests/test_notifier.py` | Unit tests for notifier (mocked firebase_admin) |
| Create | `backend/api/v1/profiles.py` | New router for profile-related endpoints |
| Create | `backend/tests/test_profiles_endpoint.py` | Tests for `PATCH /profiles/fcm-token` |
| Modify | `backend/api/v1/__init__.py` | Register profiles router |
| Modify | `backend/schemas/reel.py` | Add `FCMTokenRequest` Pydantic model |
| Modify | `backend/workers/tasks.py` | Fill 3 `# TODO Step 22` markers (Step 17 uncategorised, Step 19 ready, Step 19 pending_category) |
| Modify | `backend/workers/beat_tasks.py` | Fill 1 `# TODO Step 22` marker (per-expired-reel push) |
| Modify | `backend/api/v1/reels.py` | Fill 2 `# TODO Step 22` markers in PATCH `/category` (Path A + Path B) |
| Modify | `backend/tests/test_tasks_resilience.py` | Mock `send_push_notification` in Step 18+19 tests |
| Modify | `backend/tests/test_beat_tasks.py` | Mock notifier; adjust mock to include `fcm_token` on rows |
| Modify | `backend/tests/test_category_endpoint.py` | Mock notifier for Path A + Path B |
| Modify | `frontend/SupabaseManager.swift` | Add `AppConfig.backendBaseURL` constant |
| Create | `frontend/ProfileAPI.swift` | FCM token upload helper |
| Create | `frontend/ReelCategoryAPI.swift` | Background URLSession PATCH calls from notification handler |
| Modify | `frontend/ReelMindApp.swift` | Register `CATEGORISE` UNNotificationCategory; rewrite `didReceive response` handler; wire token upload in `didReceiveRegistrationToken` |
| Modify | `frontend/AuthSession.swift` | Wire FCM token upload trigger in `syncToken` |
| Create | `frontend/CategoriseReelView.swift` | Dedicated categorise screen for "Choose in App" |
| Modify | `frontend/RootView.swift` | Listen for `.categoriseReel` NotificationCenter post; present `CategoriseReelView` as full-screen modal |

---

## Task 1: Backend dependencies + config

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/config.py`
- Modify: `backend/.env.example` (already changed in working tree — just commit)

- [ ] **Step 1: Add `firebase-admin` to `backend/requirements.txt`**

Read `backend/requirements.txt` to see the current pinned versions. Add a new line at the bottom (preserve sort order if alphabetical, otherwise append at end):

```
firebase-admin==6.5.0
```

- [ ] **Step 2: Install locally**

```bash
cd backend && source venv/bin/activate && pip install firebase-admin==6.5.0
```

Expected: package installs successfully along with its `google-auth` etc. transitive deps.

- [ ] **Step 3: Add `FIREBASE_SERVICE_ACCOUNT_JSON` to `backend/config.py`**

Find this line in `backend/config.py`:
```python
    # Firebase
    FCM_SERVER_KEY = os.getenv("FCM_SERVER_KEY")
```

Replace with:
```python
    # Firebase
    FCM_SERVER_KEY = os.getenv("FCM_SERVER_KEY")  # legacy; unused — kept for now

    # Firebase Admin SDK service account (base64-encoded JSON) — Step 22 FCM push
    FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
```

- [ ] **Step 4: Smoke test import + config read**

```bash
cd backend && source venv/bin/activate && python -c "
import firebase_admin
from config import get_config
cfg = get_config()
print('firebase_admin version:', firebase_admin.__version__)
print('FIREBASE_SERVICE_ACCOUNT_JSON set:', bool(cfg.FIREBASE_SERVICE_ACCOUNT_JSON))
print('value length:', len(cfg.FIREBASE_SERVICE_ACCOUNT_JSON or ''))
"
```

Expected output:
```
firebase_admin version: 6.5.0
FIREBASE_SERVICE_ACCOUNT_JSON set: True
value length: 3176
```

- [ ] **Step 5: Run full test suite — no regressions from dependency addition**

```bash
cd backend && source venv/bin/activate && pytest tests/ -v
```

Expected: All 64 tests still pass.

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt backend/config.py backend/.env.example
git commit -m "feat: add firebase-admin dep + FIREBASE_SERVICE_ACCOUNT_JSON config"
```

---

## Task 2: `services/notifier.py` (TDD)

**Files:**
- Create: `backend/tests/test_notifier.py`
- Create: `backend/services/notifier.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_notifier.py`:

```python
"""Tests for services.notifier — Step 22 FCM push wrapper."""
from unittest.mock import MagicMock, patch

import pytest


@patch("services.notifier._get_firebase_app")
@patch("services.notifier.messaging")
def test_send_success_returns_true(mock_messaging, mock_get_app):
    mock_get_app.return_value = MagicMock()  # Firebase app is initialised
    mock_messaging.send.return_value = "projects/foo/messages/123"

    from services.notifier import send_push_notification
    result = send_push_notification(
        fcm_token="device-token-abc",
        title="Reel saved!",
        body="Categorised as Fitness",
        data={"reel_id": "reel-1", "status": "ready"},
    )
    assert result is True
    assert mock_messaging.send.call_count == 1


@patch("services.notifier._get_firebase_app")
def test_no_fcm_token_returns_false(mock_get_app):
    from services.notifier import send_push_notification
    result = send_push_notification(
        fcm_token=None,
        title="Reel saved",
        body="Body",
    )
    assert result is False
    mock_get_app.assert_not_called()  # short-circuits before Firebase init


@patch("services.notifier._get_firebase_app")
def test_missing_credentials_returns_false(mock_get_app):
    mock_get_app.return_value = None  # FIREBASE_SERVICE_ACCOUNT_JSON not set
    from services.notifier import send_push_notification
    result = send_push_notification(
        fcm_token="device-token-abc",
        title="Reel saved",
        body="Body",
    )
    assert result is False


@patch("services.notifier._get_firebase_app")
@patch("services.notifier.messaging")
def test_send_exception_returns_false(mock_messaging, mock_get_app):
    mock_get_app.return_value = MagicMock()
    mock_messaging.send.side_effect = Exception("APNs unreachable")

    from services.notifier import send_push_notification
    result = send_push_notification(
        fcm_token="device-token-abc",
        title="Reel saved",
        body="Body",
    )
    assert result is False  # never re-raises


@patch("services.notifier._get_firebase_app")
@patch("services.notifier.messaging")
def test_category_id_sets_apns_config(mock_messaging, mock_get_app):
    mock_get_app.return_value = MagicMock()
    mock_messaging.send.return_value = "ok"

    from services.notifier import send_push_notification
    send_push_notification(
        fcm_token="device-token-abc",
        title="Help us categorise this reel",
        body="Body",
        category_id="CATEGORISE",
    )

    # The Message instance passed to messaging.send should have an apns config
    # with category="CATEGORISE" inside its APNSPayload.aps.
    call_arg = mock_messaging.send.call_args.args[0]
    assert call_arg.apns is not None
    assert call_arg.apns.payload.aps.category == "CATEGORISE"


@patch("services.notifier._get_firebase_app")
@patch("services.notifier.messaging")
def test_no_category_id_no_apns_config(mock_messaging, mock_get_app):
    mock_get_app.return_value = MagicMock()
    mock_messaging.send.return_value = "ok"

    from services.notifier import send_push_notification
    send_push_notification(
        fcm_token="device-token-abc",
        title="Reel saved!",
        body="Categorised as Fitness",
    )

    call_arg = mock_messaging.send.call_args.args[0]
    assert call_arg.apns is None


@patch("services.notifier._get_firebase_app")
@patch("services.notifier.messaging")
def test_data_payload_passed_through(mock_messaging, mock_get_app):
    mock_get_app.return_value = MagicMock()
    mock_messaging.send.return_value = "ok"

    from services.notifier import send_push_notification
    send_push_notification(
        fcm_token="device-token-abc",
        title="t",
        body="b",
        data={"reel_id": "r1", "suggestions": '["Fitness","Nutrition"]'},
    )

    call_arg = mock_messaging.send.call_args.args[0]
    assert call_arg.data == {"reel_id": "r1", "suggestions": '["Fitness","Nutrition"]'}
```

- [ ] **Step 2: Run tests — verify they fail with ImportError**

```bash
cd backend && source venv/bin/activate && pytest tests/test_notifier.py -v
```

Expected: 7 tests FAIL with `ModuleNotFoundError: No module named 'services.notifier'`.

- [ ] **Step 3: Commit the test file as a spec**

```bash
git add backend/tests/test_notifier.py
git commit -m "test: add notifier tests (all failing — TDD red phase)"
```

- [ ] **Step 4: Implement `backend/services/notifier.py`**

```python
"""FCM push notifications via Firebase Admin SDK — Step 22 of the pipeline.

This wrapper is intentionally non-fatal: any failure (missing credentials,
missing token, transport error) is logged and converted to a False return.
Callers in workers/tasks.py, workers/beat_tasks.py, and api/v1/reels.py
treat the result as advisory — the reel is already in its correct terminal
state in the DB before a push is attempted.

Public surface:
    send_push_notification(fcm_token, title, body, data=None, category_id=None) -> bool
"""

from __future__ import annotations

import base64
import json
import logging

import firebase_admin
from firebase_admin import credentials, messaging

from config import get_config

logger = logging.getLogger(__name__)

_firebase_app: firebase_admin.App | None = None


def _get_firebase_app() -> firebase_admin.App | None:
    """Lazily initialize the Firebase Admin app.

    Returns None when FIREBASE_SERVICE_ACCOUNT_JSON is not configured
    (graceful no-op for environments without push set up).
    """
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    cfg = get_config()
    if not cfg.FIREBASE_SERVICE_ACCOUNT_JSON:
        # TODO: APNs setup required — add FIREBASE_SERVICE_ACCOUNT_JSON to env vars
        logger.warning("notifier | FIREBASE_SERVICE_ACCOUNT_JSON not set — FCM disabled")
        return None

    try:
        service_account = json.loads(base64.b64decode(cfg.FIREBASE_SERVICE_ACCOUNT_JSON))
        cred = credentials.Certificate(service_account)
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info("notifier | Firebase Admin SDK initialised")
        return _firebase_app
    except Exception as exc:
        logger.error("notifier | failed to initialise Firebase Admin SDK | %s", exc)
        return None


def send_push_notification(
    fcm_token: str | None,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
    category_id: str | None = None,
) -> bool:
    """Send a single FCM push. Never raises.

    Args:
        fcm_token:   Device FCM token. None → skips silently.
        title:       Notification title.
        body:        Notification body.
        data:        Optional string key-value data payload.
        category_id: iOS UNNotificationCategory identifier (e.g. "CATEGORISE")
                     — tells iOS which action buttons to show.

    Returns:
        True on send success, False on any skip or failure.
    """
    if not fcm_token:
        logger.warning("notifier | no fcm_token — skipping push title=%r", title)
        return False

    app = _get_firebase_app()
    if app is None:
        return False  # already logged at init

    apns_config: messaging.APNSConfig | None = None
    if category_id:
        apns_config = messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(category=category_id)
            )
        )

    message = messaging.Message(
        notification=messaging.Notification(title=title, body=body),
        data=data or {},
        apns=apns_config,
        token=fcm_token,
    )

    try:
        messaging.send(message, app=app)
        logger.info("notifier | push sent | title=%r", title)
        return True
    except Exception as exc:
        logger.error("notifier | push failed | title=%r | %s", title, exc)
        return False
```

- [ ] **Step 5: Run notifier tests — verify all 7 pass**

```bash
cd backend && source venv/bin/activate && pytest tests/test_notifier.py -v
```

Expected: `7 passed`.

- [ ] **Step 6: Run full test suite — no regressions**

```bash
cd backend && source venv/bin/activate && pytest tests/ -v
```

Expected: 71 passed (was 64, +7 new).

- [ ] **Step 7: Commit**

```bash
git add backend/services/notifier.py
git commit -m "feat: add notifier service — Step 22 FCM push wrapper"
```

---

## Task 3: `PATCH /api/v1/profiles/fcm-token` endpoint (TDD)

**Files:**
- Modify: `backend/schemas/reel.py`
- Create: `backend/api/v1/profiles.py`
- Modify: `backend/api/v1/__init__.py`
- Create: `backend/tests/test_profiles_endpoint.py`

- [ ] **Step 1: Add `FCMTokenRequest` schema to `backend/schemas/reel.py`**

(The file is shared for reel + profile schemas — a separate `schemas/profile.py` is overkill at MVP scale.)

Append to `backend/schemas/reel.py`:
```python
class FCMTokenRequest(BaseModel):
    """Body for PATCH /api/v1/profiles/fcm-token."""
    fcm_token: str
```

(`BaseModel` is already imported in that file.)

- [ ] **Step 2: Write failing endpoint tests**

Create `backend/tests/test_profiles_endpoint.py`:

```python
"""Tests for PATCH /api/v1/profiles/fcm-token."""
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_client():
    """Build a minimal test app with auth overridden."""
    from api.deps import get_current_user_id
    from api.v1.profiles import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/profiles")
    app.dependency_overrides[get_current_user_id] = lambda: "user-test-id"
    return TestClient(app)


@patch("api.v1.profiles.get_supabase")
def test_token_upload_returns_ok(mock_get_supabase):
    db = MagicMock()
    db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
    mock_get_supabase.return_value = db

    client = _build_client()
    resp = client.patch(
        "/api/v1/profiles/fcm-token",
        json={"fcm_token": "device-token-abc"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@patch("api.v1.profiles.get_supabase")
def test_token_upload_writes_correct_payload(mock_get_supabase):
    db = MagicMock()
    db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
    mock_get_supabase.return_value = db

    client = _build_client()
    client.patch(
        "/api/v1/profiles/fcm-token",
        json={"fcm_token": "device-token-abc"},
    )

    # Defensive against column-name typos
    payload = db.table.return_value.update.call_args.args[0]
    assert payload["fcm_token"] == "device-token-abc"
    assert "fcm_token_updated_at" in payload  # timestamp set


@patch("api.v1.profiles.get_supabase")
def test_token_upload_scoped_to_authenticated_user(mock_get_supabase):
    db = MagicMock()
    db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()
    mock_get_supabase.return_value = db

    client = _build_client()
    client.patch(
        "/api/v1/profiles/fcm-token",
        json={"fcm_token": "device-token-abc"},
    )

    eq_call = db.table.return_value.update.return_value.eq.call_args
    assert eq_call.args == ("id", "user-test-id")


def test_missing_token_returns_422():
    """Pydantic rejects body without fcm_token."""
    client = _build_client()
    resp = client.patch("/api/v1/profiles/fcm-token", json={})
    assert resp.status_code == 422
```

- [ ] **Step 3: Run tests — verify all 4 fail**

```bash
cd backend && source venv/bin/activate && pytest tests/test_profiles_endpoint.py -v
```

Expected: All 4 FAIL — first three with `ModuleNotFoundError: No module named 'api.v1.profiles'`, fourth might also fail at import.

- [ ] **Step 4: Create `backend/api/v1/profiles.py`**

```python
"""Profile endpoints — FCM token registration (Step 22)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status

from api.deps import get_current_user_id
from schemas.reel import FCMTokenRequest
from supabase_client import get_supabase

router = APIRouter()


@router.patch("/fcm-token", status_code=status.HTTP_200_OK)
async def update_fcm_token(
    payload: FCMTokenRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Upload (or refresh) the device's FCM registration token.

    Called by iOS on token refresh and on login. Stores the token plus an
    updated timestamp on the user's profile row so Step 22 pushes can target
    the most recent device.
    """
    supabase = get_supabase()
    supabase.table("profiles").update({
        "fcm_token": payload.fcm_token,
        "fcm_token_updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", user_id).execute()
    return {"status": "ok"}
```

- [ ] **Step 5: Register the profiles router in `backend/api/v1/__init__.py`**

Find:
```python
from api.v1 import health, reels

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health.router, tags=["health"])
api_router.include_router(reels.router, prefix="/reels", tags=["reels"])
```

Replace with:
```python
from api.v1 import health, profiles, reels

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health.router, tags=["health"])
api_router.include_router(reels.router, prefix="/reels", tags=["reels"])
api_router.include_router(profiles.router, prefix="/profiles", tags=["profiles"])
```

- [ ] **Step 6: Run endpoint tests — verify all 4 pass**

```bash
cd backend && source venv/bin/activate && pytest tests/test_profiles_endpoint.py -v
```

Expected: `4 passed`.

- [ ] **Step 7: Run full test suite — no regressions**

```bash
cd backend && source venv/bin/activate && pytest tests/ -v
```

Expected: 75 passed (was 71, +4 new).

- [ ] **Step 8: Commit**

```bash
git add backend/schemas/reel.py backend/api/v1/profiles.py backend/api/v1/__init__.py backend/tests/test_profiles_endpoint.py
git commit -m "feat: add PATCH /api/v1/profiles/fcm-token endpoint"
```

---

## Task 4: Wire `send_push_notification` into all 6 TODO sites

**Files:**
- Modify: `backend/workers/tasks.py`
- Modify: `backend/workers/beat_tasks.py`
- Modify: `backend/api/v1/reels.py`
- Modify: `backend/tests/test_tasks_resilience.py`
- Modify: `backend/tests/test_beat_tasks.py`
- Modify: `backend/tests/test_category_endpoint.py`

### Step 4A — `workers/tasks.py` (3 TODO sites)

- [ ] **Step 1: Add notifier import**

Find at the top of `backend/workers/tasks.py`:
```python
from services.classifier import ClassificationError, ClassificationResult, classify_reel
```

Add immediately after:
```python
from services.notifier import send_push_notification
```

- [ ] **Step 2: Fill the Step 17 no-signal `# TODO Step 22` marker**

Find this `NoSignalError` handler block in `process_reel`:
```python
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
```

Replace with:
```python
        except NoSignalError:
            log.warning(
                "step 17 | no usable signal (transcript=None, caption=None, "
                "hashtags=[]) — marking uncategorised"
            )
            supabase.table("reels").update(
                {"status": "uncategorised"}
            ).eq("id", reel_id).execute()
            send_push_notification(
                fcm_token=_fcm_token,
                title="Reel saved",
                body="We couldn't categorise it — no audio or caption found",
                data={"reel_id": reel_id, "status": "uncategorised"},
            )
            return {"reel_id": reel_id, "status": "uncategorised"}
```

- [ ] **Step 3: Fill the Step 19 ready (auto-assigned) `# TODO Step 22` marker**

Find:
```python
            supabase.table("reels").update({
                "category_id": resolved_category_id,
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
```

Replace with:
```python
            supabase.table("reels").update({
                "category_id": resolved_category_id,
                "confidence": classification.confidence,
                "status": "ready",
            }).eq("id", reel_id).execute()
            send_push_notification(
                fcm_token=_fcm_token,
                title="Reel saved!",
                body=f"Categorised as {classification.category}",
                data={"reel_id": reel_id, "status": "ready"},
            )
            log.info("step 19 | status=ready")
            return {
                "reel_id": reel_id,
                "status": "ready",
                "category": classification.category,
            }
```

- [ ] **Step 4: Fill the Step 19 pending_category `# TODO Step 22` marker**

Find:
```python
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

Replace with:
```python
            import json as _json
            supabase.table("reels").update({
                "status": "pending_category",
                "suggested_categories": suggestions,
                "confidence": classification.confidence,
            }).eq("id", reel_id).execute()
            send_push_notification(
                fcm_token=_fcm_token,
                title="Help us categorise this reel",
                body="Your reel is saved — which fits best? Ignoring this saves it to Uncategorised.",
                data={
                    "reel_id": reel_id,
                    "suggestions": _json.dumps(suggestions),
                },
                category_id="CATEGORISE",
            )
            log.info("step 19 | status=pending_category")
            return {
                "reel_id": reel_id,
                "status": "pending_category",
                "suggestions": suggestions,
            }
```

### Step 4B — `workers/beat_tasks.py` (1 TODO site)

- [ ] **Step 5: Update beat_tasks to send per-expired-reel push**

Read `backend/workers/beat_tasks.py`. Add the notifier import after the existing `from supabase_client import get_supabase` line:
```python
from services.notifier import send_push_notification
```

Find the bulk-update result loop area in `expire_pending_categories`. After the bulk update completes, replace the existing `expired_ids = ... return ...` block:

```python
    expired_ids = [row["id"] for row in (result.data or [])]
    # TODO Step 22: FCM push per expired reel — "Saved to Uncategorised — you can move it anytime"
    #   Needs to fetch fcm_token per user_id for the rows in result.data.
    logger.info("beat | expire_pending_categories done | expired=%d", len(expired_ids))
    return {"expired": len(expired_ids), "reel_ids": expired_ids}
```

With:

```python
    expired_ids = []
    for row in (result.data or []):
        expired_ids.append(row["id"])
        profile = (
            supabase.table("profiles")
            .select("fcm_token")
            .eq("id", row["user_id"])
            .maybe_single()
            .execute()
        )
        fcm_token = (profile.data or {}).get("fcm_token") if profile.data else None
        send_push_notification(
            fcm_token=fcm_token,
            title="Reel saved",
            body="Added to Uncategorised — you can move it anytime",
            data={"reel_id": row["id"], "status": "uncategorised"},
        )

    logger.info("beat | expire_pending_categories done | expired=%d", len(expired_ids))
    return {"expired": len(expired_ids), "reel_ids": expired_ids}
```

### Step 4C — `api/v1/reels.py` (2 TODO sites)

- [ ] **Step 6: Add notifier import and fetch FCM token in PATCH /category**

In `backend/api/v1/reels.py`, find the existing imports:
```python
from api.deps import get_current_user_id
from schemas.reel import CategoryChoiceRequest, ReelCreate, ReelResponse
from supabase_client import get_supabase
from workers.tasks import process_reel
```

Add immediately after:
```python
from services.notifier import send_push_notification
```

Then in `update_reel_category`, find Path B (after the reel-row fetch and 409 guard):
```python
    # Path B — user tapped "Uncategorised"
    if payload.category_name is None:
        supabase.table("reels").update({
            "status": "uncategorised",
            "suggested_categories": [],
        }).eq("id", reel_id).execute()
        # TODO Step 22: FCM push — "Saved to Uncategorised — you can move it anytime"
        return {"reel_id": reel_id, "status": "uncategorised"}
```

Replace with:
```python
    # Fetch FCM token for outgoing push (used by both Path A and Path B)
    _profile = (
        supabase.table("profiles")
        .select("fcm_token")
        .eq("id", user_id)
        .maybe_single()
        .execute()
    )
    fcm_token = (_profile.data or {}).get("fcm_token") if _profile.data else None

    # Path B — user tapped "Uncategorised"
    if payload.category_name is None:
        supabase.table("reels").update({
            "status": "uncategorised",
            "suggested_categories": [],
        }).eq("id", reel_id).execute()
        send_push_notification(
            fcm_token=fcm_token,
            title="Reel saved",
            body="Added to Uncategorised — you can move it anytime",
            data={"reel_id": reel_id, "status": "uncategorised"},
        )
        return {"reel_id": reel_id, "status": "uncategorised"}
```

- [ ] **Step 7: Fill Path A `# TODO Step 22` marker**

Find:
```python
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

Replace with:
```python
    category_id = cat_rows.data[0]["id"]
    supabase.table("reels").update({
        "category_id": category_id,
        "confidence": 1.0,
        "status": "ready",
        "suggested_categories": [],
    }).eq("id", reel_id).execute()
    send_push_notification(
        fcm_token=fcm_token,
        title="Reel categorised!",
        body=f"Moved to {payload.category_name}",
        data={"reel_id": reel_id, "status": "ready"},
    )
    return {"reel_id": reel_id, "status": "ready", "category": payload.category_name}
```

### Step 4D — Update tests to mock the notifier

- [ ] **Step 8: Mock `send_push_notification` in `test_tasks_resilience.py`**

In `backend/tests/test_tasks_resilience.py`, every Step 18+19 test that runs the pipeline through Step 19 now hits `send_push_notification`. We patch it to a no-op `return False` (matches behaviour when no fcm_token set in mock).

Find each of the 4 Step 18+19 routing tests (`test_high_confidence_marks_ready`, `test_low_confidence_marks_pending_category`, `test_classification_retryable_error_triggers_retry`, `test_classification_non_retryable_error_marks_failed`). They all already use nested `with patch(...)` blocks for `download_reel`, `transcribe_audio`, etc. To each test, add one additional patch as the outermost wrap:

```python
    with patch("workers.tasks.send_push_notification", return_value=False) as _push:
        with patch("workers.tasks.get_supabase", return_value=mock_db):
            ...
```

For `test_high_confidence_marks_ready`, also add an assertion after the existing ones:
```python
    _push.assert_called_once()
    push_kwargs = _push.call_args.kwargs
    assert push_kwargs["title"] == "Reel saved!"
    assert "Fitness" in push_kwargs["body"]
```

For `test_low_confidence_marks_pending_category`:
```python
    _push.assert_called_once()
    push_kwargs = _push.call_args.kwargs
    assert push_kwargs["category_id"] == "CATEGORISE"
    assert push_kwargs["title"] == "Help us categorise this reel"
```

For `test_classification_retryable_error_triggers_retry` and `test_classification_non_retryable_error_marks_failed`: no extra assertion needed — the patch just keeps the test running. (For retryable, classification fails before push; for non-retryable, _handle_pipeline_error marks failed before push — no push sent.)

Also: the `test_transcription_failure_does_not_mark_reel_failed` test already runs through Step 18+19 — it needs the same `send_push_notification` patch.

- [ ] **Step 9: Mock notifier in `test_beat_tasks.py` and add `fcm_token` fetch behaviour**

The bulk update now triggers per-reel profile fetch + push. Update `_make_supabase_mock` in `backend/tests/test_beat_tasks.py` to also wire the profile fetch chain.

Read the current `_make_supabase_mock` and replace it with this version (it now also routes a `profiles` lookup):

```python
def _make_supabase_mock(updated_rows: list[dict]):
    """Supabase mock returning updated_rows for the bulk update execute(),
    plus a per-user fcm_token fetch for each updated row."""
    mock_db = MagicMock()

    # bulk update chain
    (
        mock_db.table.return_value
        .update.return_value
        .eq.return_value
        .lt.return_value
        .execute.return_value
        .data
    ) = updated_rows

    # profile fetch chain (returns no fcm_token by default)
    (
        mock_db.table.return_value
        .select.return_value
        .eq.return_value
        .maybe_single.return_value
        .execute.return_value
        .data
    ) = {"fcm_token": None}

    return mock_db
```

Then at the top of `test_beat_tasks.py`, wrap each test's call to `expire_pending_categories()` in a `patch("workers.beat_tasks.send_push_notification", return_value=False)` context, e.g.:

```python
@patch("workers.beat_tasks.get_supabase")
def test_stale_reels_transitioned(mock_get_supabase):
    updated = [
        {"id": "reel-1", "user_id": "user-1"},
        {"id": "reel-2", "user_id": "user-2"},
    ]
    mock_db = _make_supabase_mock(updated)
    mock_get_supabase.return_value = mock_db

    from workers.beat_tasks import expire_pending_categories
    with patch("workers.beat_tasks.send_push_notification", return_value=False) as _push:
        result = expire_pending_categories()

    assert result["expired"] == 2
    assert _push.call_count == 2  # one push per expired reel
```

Apply the same `with patch(...)` wrap to every other test in the file. Where the test previously had `result = expire_pending_categories()`, move it inside the `with` block.

- [ ] **Step 10: Mock notifier in `test_category_endpoint.py`**

In `backend/tests/test_category_endpoint.py`, every test that calls `client.patch(...)/category` now hits `send_push_notification`. Add the patch around each call.

The simplest pattern: add a class-level `@patch("api.v1.reels.send_push_notification", return_value=False)` to the relevant test functions, OR wrap each `client.patch` call in `with patch(...)`. Use the same `with patch` pattern as the other test files for consistency.

Also: the existing `_make_supabase_patch_mock` does NOT route a `profiles` table call. The endpoint now does `.table("profiles").select("fcm_token").eq("id", user_id).maybe_single().execute()` before deciding the path. Extend the mock:

Find:
```python
    db.table.return_value.update.return_value.eq.return_value.execute.return_value = None
    return db
```

Replace with:
```python
    # Profile fetch for FCM token (returns None — no token configured in tests)
    (
        db.table.return_value
        .select.return_value
        .eq.return_value
        .maybe_single.return_value
        .execute.return_value
        .data
    ) = {"fcm_token": None}

    db.table.return_value.update.return_value.eq.return_value.execute.return_value = None
    return db
```

NOTE: the `db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value` chain may collide with the reel-fetch chain `.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value`. They branch at the second call after `eq.return_value` — one continues with `.eq`, the other with `.maybe_single`. Since `MagicMock` attributes are separate (`.eq.return_value` is one attribute, `.maybe_single.return_value` is another), the two chains are isolated. The test should still pass.

Then wrap the `client.patch` calls. For example in `test_assign_category_marks_ready`:

```python
@patch("api.v1.reels.get_supabase")
def test_assign_category_marks_ready(mock_get_supabase):
    mock_get_supabase.return_value = _make_supabase_patch_mock(
        category_id="cat-uuid-fitness"
    )
    with patch("api.v1.reels.send_push_notification", return_value=False) as _push:
        resp = client.patch(
            f"/api/v1/reels/{REEL_ID}/category",
            json={"category_name": "Fitness"},
        )
    assert resp.status_code == 200
    ...
    _push.assert_called_once()
    push_kwargs = _push.call_args.kwargs
    assert push_kwargs["title"] == "Reel categorised!"
```

Apply the `with patch(...)` wrap (and a matching `_push.assert_called_once()` if relevant) to `test_assign_category_marks_ready` and `test_null_category_name_marks_uncategorised`. The error-path tests (404/409/422) don't reach the push call, but it's safe to wrap them anyway.

### Step 4E — Verify and commit

- [ ] **Step 11: Run the full test suite — verify 75 still pass**

```bash
cd backend && source venv/bin/activate && pytest tests/ -v
```

Expected: All 75 tests pass.

- [ ] **Step 12: Smoke test the Celery + endpoint imports together**

```bash
cd backend && source venv/bin/activate && python -c "
from workers.tasks import process_reel
from workers.beat_tasks import expire_pending_categories
from services.notifier import send_push_notification
from api.v1.profiles import router as profiles_router
from api.v1.reels import router as reels_router
print('imports OK')
"
```

Expected: `imports OK`.

- [ ] **Step 13: Commit**

```bash
git add backend/workers/tasks.py backend/workers/beat_tasks.py backend/api/v1/reels.py backend/tests/test_tasks_resilience.py backend/tests/test_beat_tasks.py backend/tests/test_category_endpoint.py
git commit -m "feat: wire FCM push notifications into all 6 pipeline sites"
```

---

## Task 5: iOS — `AppConfig.backendBaseURL` + `ProfileAPI.swift` + `ReelCategoryAPI.swift`

**Files:**
- Modify: `frontend/SupabaseManager.swift`
- Create: `frontend/ProfileAPI.swift`
- Create: `frontend/ReelCategoryAPI.swift`

- [ ] **Step 1: Find the backend URL currently used by the share extension**

```bash
grep -rn "backendBaseURL\|K\.backendBaseURL" /Users/deeptijain/Desktop/Deepti/Projects/ReelMind --include="*.swift"
```

Note the URL value — it will be re-used. This is typically the Render URL (e.g. `https://reelmind-api.onrender.com`) or an ngrok URL in dev.

- [ ] **Step 2: Add `backendBaseURL` to `AppConfig` in `frontend/SupabaseManager.swift`**

In `frontend/SupabaseManager.swift`, find the `AppConfig` enum and add a new property:

```swift
enum AppConfig {
    static let supabaseURL = URL(string: "https://rpdqnfhfrhnzifgfmsbj.supabase.co")!

    // ... (existing supabaseAnonKey etc.)

    // Backend base URL — must match the URL hardcoded in URL Sharing module/Constants.swift.
    // Update both places when the Render URL changes.
    static let backendBaseURL = URL(string: "<paste the URL from Step 1>")!

    // ... (existing appGroupID, authTokenKey)
}
```

Place the new constant near the top of `AppConfig`, just under `supabaseAnonKey`.

- [ ] **Step 3: Create `frontend/ProfileAPI.swift`**

```swift
import Foundation

/// Uploads the device's FCM registration token to the backend.
/// Used on FCM token refresh and on successful login.
enum ProfileAPI {
    static func uploadFCMToken(_ token: String) {
        guard
            let defaults = UserDefaults(suiteName: AppConfig.appGroupID),
            let authToken = defaults.string(forKey: AppConfig.authTokenKey)
        else {
            print("[ProfileAPI] skipping FCM token upload — no auth token in App Group defaults")
            return
        }

        let url = AppConfig.backendBaseURL.appendingPathComponent("api/v1/profiles/fcm-token")
        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("Bearer \(authToken)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONEncoder().encode(["fcm_token": token])

        URLSession.shared.dataTask(with: request) { _, response, error in
            if let error = error {
                print("[ProfileAPI] uploadFCMToken failed: \(error)")
                return
            }
            if let http = response as? HTTPURLResponse {
                print("[ProfileAPI] uploadFCMToken HTTP \(http.statusCode)")
            }
        }.resume()
    }
}
```

- [ ] **Step 4: Create `frontend/ReelCategoryAPI.swift`**

```swift
import Foundation

/// Background API calls invoked by the notification action handler when the
/// user taps a category button on the FCM "Help us categorise this reel"
/// notification. The system wakes the app briefly to handle the action; we
/// use URLSession.shared (which supports background completion).
enum ReelCategoryAPI {
    /// Assigns `categoryName` to `reelId`, or moves the reel to uncategorised
    /// when `categoryName` is nil (user tapped the "Uncategorised" button).
    static func assign(reelId: String, categoryName: String?) {
        guard
            let defaults = UserDefaults(suiteName: AppConfig.appGroupID),
            let authToken = defaults.string(forKey: AppConfig.authTokenKey)
        else {
            print("[ReelCategoryAPI] skipping assign — no auth token")
            return
        }

        let url = AppConfig.backendBaseURL
            .appendingPathComponent("api/v1/reels")
            .appendingPathComponent(reelId)
            .appendingPathComponent("category")

        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("Bearer \(authToken)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        // {"category_name": "Fitness"} or {"category_name": null}
        let body: [String: Any?] = ["category_name": categoryName]
        request.httpBody = try? JSONSerialization.data(
            withJSONObject: body,
            options: [.fragmentsAllowed]
        )

        URLSession.shared.dataTask(with: request) { _, response, error in
            if let error = error {
                print("[ReelCategoryAPI] assign failed: \(error)")
                return
            }
            if let http = response as? HTTPURLResponse {
                print("[ReelCategoryAPI] assign HTTP \(http.statusCode)")
            }
        }.resume()
    }
}
```

- [ ] **Step 5: Build the iOS project to verify it compiles**

Open `ReelMind.xcworkspace` in Xcode → ⌘B (Build).

Expected: build succeeds. Both new files appear in the file navigator. (If the files don't appear in the project, add them via Xcode → File → Add Files to "ReelMind"… → select `ProfileAPI.swift` and `ReelCategoryAPI.swift` → make sure the **ReelMind** main app target is checked, not the URL Sharing module target.)

- [ ] **Step 6: Commit**

```bash
git add frontend/SupabaseManager.swift frontend/ProfileAPI.swift frontend/ReelCategoryAPI.swift
git commit -m "feat: add AppConfig.backendBaseURL + ProfileAPI + ReelCategoryAPI helpers"
```

---

## Task 6: iOS — Register `CATEGORISE` UNNotificationCategory

**Files:**
- Modify: `frontend/ReelMindApp.swift`

- [ ] **Step 1: Add notification category registration in `didFinishLaunchingWithOptions`**

In `frontend/ReelMindApp.swift`, find the `AppDelegate.application(_:didFinishLaunchingWithOptions:)` method. After the existing `UNUserNotificationCenter.current().delegate = self` line and BEFORE the `UNUserNotificationCenter.current().getNotificationSettings { ... }` block, insert:

```swift
        // Register the CATEGORISE notification category — used by Step 22 FCM
        // notifications that include category-suggestion action buttons.
        let actions: [UNNotificationAction] = [
            UNNotificationAction(
                identifier: "CAT_0",
                title: "Suggestion 1",         // generic label — real name read from data payload at handler time
                options: []                     // background — does not open app
            ),
            UNNotificationAction(
                identifier: "CAT_1",
                title: "Suggestion 2",
                options: []
            ),
            UNNotificationAction(
                identifier: "CHOOSE_IN_APP",
                title: "Choose / Create Category",
                options: [.foreground]          // opens app
            ),
            UNNotificationAction(
                identifier: "UNCATEGORISED",
                title: "Uncategorised",
                options: []
            ),
        ]
        let categoriseCategory = UNNotificationCategory(
            identifier: "CATEGORISE",
            actions: actions,
            intentIdentifiers: [],
            options: []
        )
        UNUserNotificationCenter.current().setNotificationCategories([categoriseCategory])
```

- [ ] **Step 2: Build the project**

Open Xcode → ⌘B.

Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/ReelMindApp.swift
git commit -m "feat: register CATEGORISE UNNotificationCategory with 4 action buttons"
```

---

## Task 7: iOS — Rewrite `didReceive response` handler

**Files:**
- Modify: `frontend/ReelMindApp.swift`

- [ ] **Step 1: Add `Notification.Name` extension for `.categoriseReel`**

In `frontend/ReelMindApp.swift`, at the very top after the imports (before the `class AppDelegate` declaration), add:

```swift
extension Notification.Name {
    /// Posted by the AppDelegate notification handler when the user taps
    /// the "Choose / Create Category" foreground action on a pending_category
    /// FCM notification. RootView listens for this and presents CategoriseReelView.
    static let categoriseReel = Notification.Name("categoriseReel")
}
```

- [ ] **Step 2: Replace the existing `didReceive response` handler**

Find the current implementation in `frontend/ReelMindApp.swift`:
```swift
    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse, withCompletionHandler completionHandler: @escaping () -> Void) {
        let userInfo = response.notification.request.content.userInfo
        print("User tapped notification: \(userInfo)")
        completionHandler()
    }
```

Replace with:
```swift
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let userInfo = response.notification.request.content.userInfo
        guard let reelId = userInfo["reel_id"] as? String else {
            print("[AppDelegate] notification action with no reel_id — ignoring")
            completionHandler()
            return
        }

        let suggestions = Self.parseSuggestions(from: userInfo)

        switch response.actionIdentifier {
        case "CAT_0" where suggestions.count > 0:
            ReelCategoryAPI.assign(reelId: reelId, categoryName: suggestions[0])
        case "CAT_1" where suggestions.count > 1:
            ReelCategoryAPI.assign(reelId: reelId, categoryName: suggestions[1])
        case "UNCATEGORISED":
            ReelCategoryAPI.assign(reelId: reelId, categoryName: nil)
        case "CHOOSE_IN_APP":
            // App is foregrounding — RootView listens for this and presents CategoriseReelView
            NotificationCenter.default.post(
                name: .categoriseReel,
                object: nil,
                userInfo: [
                    "reel_id": reelId,
                    "suggestions": suggestions,
                ]
            )
        default:
            // Plain tap (no specific action) or unknown identifier — fall through
            break
        }
        completionHandler()
    }

    /// Parse the JSON-string `suggestions` field from the FCM data payload.
    /// FCM data values are always strings; the backend serialises the list
    /// with json.dumps before sending.
    private static func parseSuggestions(from userInfo: [AnyHashable: Any]) -> [String] {
        guard
            let raw = userInfo["suggestions"] as? String,
            let data = raw.data(using: .utf8),
            let suggestions = try? JSONDecoder().decode([String].self, from: data)
        else {
            return []
        }
        return suggestions
    }
```

- [ ] **Step 3: Build the project**

Open Xcode → ⌘B.

Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/ReelMindApp.swift
git commit -m "feat: dispatch FCM notification action buttons to ReelCategoryAPI or CategoriseReelView"
```

---

## Task 8: iOS — Wire FCM token upload triggers

**Files:**
- Modify: `frontend/ReelMindApp.swift`
- Modify: `frontend/AuthSession.swift`

There are two trigger points:
- **A:** FCM token refresh — in `AppDelegate.messaging(_:didReceiveRegistrationToken:)`. If user is logged in, upload immediately.
- **B:** User just logged in — in `AuthSession.syncToken`. If an FCM token exists in UserDefaults, upload.

This covers the race where the FCM token may refresh before the user logs in, or vice versa.

- [ ] **Step 1: Update `AppDelegate.messaging(_:didReceiveRegistrationToken:)`**

In `frontend/ReelMindApp.swift`, find:
```swift
    func messaging(_ messaging: Messaging, didReceiveRegistrationToken fcmToken: String?) {
        print("FCM Token: \(fcmToken ?? "No token")")
        // Send this token to your backend for storing user's FCM token
        if let token = fcmToken {
            UserDefaults.standard.set(token, forKey: "fcmToken")
        }
    }
```

Replace with:
```swift
    func messaging(_ messaging: Messaging, didReceiveRegistrationToken fcmToken: String?) {
        print("FCM Token: \(fcmToken ?? "No token")")
        guard let token = fcmToken else { return }

        // Cache locally so a later AuthSession.syncToken can upload if the
        // user logs in after the FCM token has refreshed.
        UserDefaults.standard.set(token, forKey: "fcmToken")

        // Upload immediately if an auth token is already present in App
        // Group defaults (i.e. user is already logged in this session).
        let groupDefaults = UserDefaults(suiteName: AppConfig.appGroupID)
        if groupDefaults?.string(forKey: AppConfig.authTokenKey) != nil {
            ProfileAPI.uploadFCMToken(token)
        }
    }
```

- [ ] **Step 2: Update `AuthSession.syncToken` to upload FCM token on login**

In `frontend/AuthSession.swift`, find the `syncToken` method:
```swift
    private func syncToken(_ token: String?) {
        guard let defaults = UserDefaults(suiteName: AppConfig.appGroupID) else {
            print("[AuthSession] could not open App Group defaults — check entitlement \(AppConfig.appGroupID)")
            return
        }
        if let token = token {
            defaults.set(token, forKey: AppConfig.authTokenKey)
            print("[AuthSession] token synced to App Group (\(token.count) chars)")
        } else {
            defaults.removeObject(forKey: AppConfig.authTokenKey)
            print("[AuthSession] token cleared from App Group")
        }
    }
```

Replace with:
```swift
    private func syncToken(_ token: String?) {
        guard let defaults = UserDefaults(suiteName: AppConfig.appGroupID) else {
            print("[AuthSession] could not open App Group defaults — check entitlement \(AppConfig.appGroupID)")
            return
        }
        if let token = token {
            defaults.set(token, forKey: AppConfig.authTokenKey)
            print("[AuthSession] token synced to App Group (\(token.count) chars)")

            // If an FCM token was cached before login, push it to the backend now.
            if let fcmToken = UserDefaults.standard.string(forKey: "fcmToken") {
                ProfileAPI.uploadFCMToken(fcmToken)
            }
        } else {
            defaults.removeObject(forKey: AppConfig.authTokenKey)
            print("[AuthSession] token cleared from App Group")
        }
    }
```

- [ ] **Step 3: Build the project**

Open Xcode → ⌘B.

Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/ReelMindApp.swift frontend/AuthSession.swift
git commit -m "feat: upload FCM token to backend on token refresh and on login"
```

---

## Task 9: iOS — `CategoriseReelView.swift` + RootView listener

**Files:**
- Create: `frontend/CategoriseReelView.swift`
- Modify: `frontend/RootView.swift`

The view is presented as a full-screen modal whenever `RootView` receives a `.categoriseReel` post (from the foreground "Choose / Create Category" action). It fetches the reel's thumbnail + caption from Supabase, shows suggestion chips, the full user-category list, and a "Create new category" inline form.

- [ ] **Step 1: Create `frontend/CategoriseReelView.swift`**

```swift
import Foundation
import Supabase
import SwiftUI

struct CategoriseReelView: View {
    let reelId: String
    let suggestions: [String]
    @Environment(\.dismiss) private var dismiss

    @State private var reelThumbnailURL: URL? = nil
    @State private var reelCaption: String? = nil
    @State private var userCategories: [CategoryRow] = []
    @State private var newCategoryName: String = ""
    @State private var isLoading: Bool = true

    struct CategoryRow: Identifiable, Decodable, Hashable {
        let id: String
        let name: String
    }

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    thumbnailHeader

                    if !suggestions.isEmpty {
                        Text("Suggested for you")
                            .font(.headline)
                        chipsRow(suggestions)
                    }

                    Divider()

                    Text("All your categories")
                        .font(.headline)
                    if isLoading {
                        ProgressView()
                    } else {
                        VStack(spacing: 8) {
                            ForEach(userCategories) { cat in
                                Button {
                                    assignAndDismiss(categoryName: cat.name)
                                } label: {
                                    HStack {
                                        Text(cat.name)
                                        Spacer()
                                    }
                                    .padding()
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .background(Color(.secondarySystemBackground))
                                    .cornerRadius(8)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }

                    Divider()

                    VStack(alignment: .leading, spacing: 8) {
                        Text("Create new category")
                            .font(.headline)
                        HStack {
                            TextField("e.g. Travel", text: $newCategoryName)
                                .textFieldStyle(.roundedBorder)
                            Button("Add") {
                                createCategoryAndAssign()
                            }
                            .disabled(newCategoryName.trimmingCharacters(in: .whitespaces).isEmpty)
                        }
                    }
                }
                .padding()
            }
            .navigationTitle("Categorise reel")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Skip") {
                        ReelCategoryAPI.assign(reelId: reelId, categoryName: nil)
                        dismiss()
                    }
                }
            }
            .task {
                await loadReelAndCategories()
            }
        }
    }

    @ViewBuilder
    private var thumbnailHeader: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let url = reelThumbnailURL {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .empty: ProgressView().frame(maxWidth: .infinity)
                    case .success(let image):
                        image.resizable().scaledToFit().cornerRadius(12)
                    case .failure:
                        Rectangle().fill(Color.gray.opacity(0.3)).frame(height: 200).cornerRadius(12)
                    @unknown default:
                        EmptyView()
                    }
                }
            }
            if let caption = reelCaption, !caption.isEmpty {
                Text(caption).font(.footnote).foregroundStyle(.secondary).lineLimit(3)
            }
        }
    }

    @ViewBuilder
    private func chipsRow(_ items: [String]) -> some View {
        HStack(spacing: 8) {
            ForEach(items, id: \.self) { name in
                Button {
                    assignAndDismiss(categoryName: name)
                } label: {
                    Text(name)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(Color.blue.opacity(0.15))
                        .foregroundStyle(.blue)
                        .cornerRadius(20)
                }
                .buttonStyle(.plain)
            }
        }
    }

    private func assignAndDismiss(categoryName: String?) {
        ReelCategoryAPI.assign(reelId: reelId, categoryName: categoryName)
        dismiss()
    }

    private func createCategoryAndAssign() {
        let trimmed = newCategoryName.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        Task {
            do {
                try await SupabaseManager.shared.client
                    .from("categories")
                    .insert(["name": trimmed])
                    .execute()
                await MainActor.run {
                    assignAndDismiss(categoryName: trimmed)
                }
            } catch {
                print("[CategoriseReelView] create category failed: \(error)")
            }
        }
    }

    private struct ReelMeta: Decodable {
        let thumbnail_url: String?
        let caption: String?
    }

    private func loadReelAndCategories() async {
        defer { isLoading = false }
        do {
            // Fetch reel row for thumbnail + caption
            let reel: ReelMeta = try await SupabaseManager.shared.client
                .from("reels")
                .select("thumbnail_url, caption")
                .eq("id", value: reelId)
                .single()
                .execute()
                .value

            if let thumb = reel.thumbnail_url, let url = URL(string: thumb) {
                self.reelThumbnailURL = url
            }
            self.reelCaption = reel.caption

            // Fetch all user categories (default + user-created)
            let cats: [CategoryRow] = try await SupabaseManager.shared.client
                .from("categories")
                .select("id, name")
                .order("name", ascending: true)
                .execute()
                .value
            self.userCategories = cats
        } catch {
            print("[CategoriseReelView] load failed: \(error)")
        }
    }
}
```

- [ ] **Step 2: Modify `frontend/RootView.swift` to listen for `.categoriseReel`**

Replace the entire contents of `frontend/RootView.swift` with:

```swift
import SwiftUI

struct RootView: View {
    @EnvironmentObject private var auth: AuthSession
    @AppStorage("hasCompletedOnboarding") private var hasCompletedOnboarding = false

    @State private var categoriseTarget: CategoriseTarget? = nil

    /// Identifiable payload for the `.categoriseReel` sheet binding.
    private struct CategoriseTarget: Identifiable {
        let id = UUID()
        let reelId: String
        let suggestions: [String]
    }

    var body: some View {
        Group {
            if auth.isBootstrapping {
                ProgressView()
            } else if !hasCompletedOnboarding {
                OnboardingFlow()
            } else if auth.session != nil {
                ContentView()
            } else {
                LoginView()
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .categoriseReel)) { notification in
            guard
                let info = notification.userInfo,
                let reelId = info["reel_id"] as? String
            else { return }
            let suggestions = (info["suggestions"] as? [String]) ?? []
            categoriseTarget = CategoriseTarget(reelId: reelId, suggestions: suggestions)
        }
        .fullScreenCover(item: $categoriseTarget) { target in
            CategoriseReelView(reelId: target.reelId, suggestions: target.suggestions)
        }
    }
}
```

- [ ] **Step 3: Build the project**

Open Xcode → ⌘B.

Expected: build succeeds. (If `AnyJSON` doesn't compile in `CategoriseReelView`, adjust per the note in Step 1.)

- [ ] **Step 4: Add the new files to the Xcode project (if not auto-added)**

Open Xcode → File menu → Add Files to "ReelMind"… → select `CategoriseReelView.swift` if it's not already in the project navigator → ensure **ReelMind** target (not URL Sharing module) is checked.

- [ ] **Step 5: Commit**

```bash
git add frontend/CategoriseReelView.swift frontend/RootView.swift
git commit -m "feat: add CategoriseReelView + RootView listener for foreground category action"
```

---

## Final Verification

- [ ] **Run the complete backend test suite**

```bash
cd backend && source venv/bin/activate && pytest tests/ -v
```

Expected: 75 tests pass, 0 failures.

- [ ] **Smoke test the backend imports**

```bash
cd backend && source venv/bin/activate && python -c "
from workers.tasks import process_reel
from workers.beat_tasks import expire_pending_categories
from services.notifier import send_push_notification
from api.v1.profiles import router as profiles_router
from api.v1.reels import router as reels_router
from schemas.reel import FCMTokenRequest, CategoryChoiceRequest
print('All imports OK')
"
```

Expected:
```
All imports OK
```

- [ ] **iOS build verification**

Open `ReelMind.xcworkspace` in Xcode → ⌘B (Build). Expected: build succeeds with no errors.

- [ ] **Manual end-to-end smoke test (real device required)**

The following requires a real iPhone with the app installed via Xcode + a paid Apple Developer account (already done by user, per session context):

1. Launch the app, log in, accept notification permission when prompted
2. Check Xcode console for the line `FCM Token: <long-string>`
3. Verify the backend received the token: `SELECT fcm_token, fcm_token_updated_at FROM profiles WHERE id = '<your_user_id>';` should show the token
4. Send a test push from Firebase Console → Messaging → Send test message → paste the FCM token
5. Verify the notification arrives on the device
6. Save a real Instagram reel via the share extension
7. Wait for the Celery pipeline to complete (~30 seconds for a small reel)
8. Verify a "Reel saved!" notification arrives
9. For a deliberately-ambiguous reel (silent video with no caption / minimal hashtags), verify a "Help us categorise this reel" notification arrives with action buttons
10. Tap one of the category suggestion buttons; verify the reel's category updates in the app
11. Save another ambiguous reel, don't respond; wait 1+ hour; verify Celery Beat expires it to `uncategorised` and a follow-up FCM arrives
