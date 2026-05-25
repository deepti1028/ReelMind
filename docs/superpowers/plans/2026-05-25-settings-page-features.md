# Settings Page Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement delete account, functional auto-categorise toggle (end-to-end), and user card cleanup across the iOS app and FastAPI backend.

**Architecture:** Backend changes first (schema → Celery task → new endpoint), then iOS changes (Share Extension → Settings sync → InboxView banner → AuthSession → SettingsView UI). Each backend task is tested before the next begins. iOS tasks have no automated test framework so verification steps are manual Xcode builds.

**Tech Stack:** SwiftUI (iOS), FastAPI + Pydantic + Celery (backend), Supabase Python SDK (admin user deletion), App Group UserDefaults (iOS ↔ Share Extension shared state).

---

## File Map

| File | Change |
|---|---|
| `backend/schemas/reel.py` | Add `auto_categorise: bool = True` to `ReelCreate` |
| `backend/api/v1/reels.py` | Pass `auto_categorise` to `process_reel.delay()` |
| `backend/workers/tasks.py` | Accept `auto_categorise` param; skip steps 17–19 when `False` |
| `backend/api/v1/account.py` | **NEW** — `DELETE /account` endpoint |
| `backend/api/v1/__init__.py` | Register account router |
| `backend/tests/test_auto_categorise_task.py` | **NEW** — Celery task tests |
| `backend/tests/test_account_endpoint.py` | **NEW** — account endpoint tests |
| `URL Sharing module/ShareViewController.swift` | Read `autoCategorise` from App Group and pass in POST body |
| `frontend/Views/SettingsView.swift` | Sync `autoCategorise` onChange + user card cleanup + delete confirmation |
| `frontend/Views/InboxView.swift` | Dismissible sage green banner |
| `frontend/AuthSession.swift` | Add `deleteAccount()` method |

---

## Task 1: Add `auto_categorise` field to `ReelCreate` schema

**Files:**
- Modify: `backend/schemas/reel.py`
- Test: `backend/tests/test_auto_categorise_task.py` (created here, tests added in Task 2)

- [ ] **Step 1: Write a failing schema test**

Create `backend/tests/test_auto_categorise_task.py`:

```python
"""Tests for auto_categorise behaviour in schema and Celery task."""
from schemas.reel import ReelCreate


def test_reel_create_auto_categorise_defaults_true():
    r = ReelCreate(url="https://www.instagram.com/reel/ABC123/")
    assert r.auto_categorise is True


def test_reel_create_auto_categorise_can_be_false():
    r = ReelCreate(url="https://www.instagram.com/reel/ABC123/", auto_categorise=False)
    assert r.auto_categorise is False
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/test_auto_categorise_task.py::test_reel_create_auto_categorise_defaults_true -v
```

Expected: `AttributeError: 'ReelCreate' object has no attribute 'auto_categorise'` (or similar).

- [ ] **Step 3: Add the field to `ReelCreate`**

In `backend/schemas/reel.py`, change:

```python
class ReelCreate(BaseModel):
    url: HttpUrl = Field(..., description="The Instagram reel URL")
```

to:

```python
class ReelCreate(BaseModel):
    url: HttpUrl = Field(..., description="The Instagram reel URL")
    auto_categorise: bool = Field(True, description="When False, skip classification and land in Inbox")
```

- [ ] **Step 4: Run both schema tests — expect PASS**

```bash
python -m pytest tests/test_auto_categorise_task.py::test_reel_create_auto_categorise_defaults_true tests/test_auto_categorise_task.py::test_reel_create_auto_categorise_can_be_false -v
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/schemas/reel.py backend/tests/test_auto_categorise_task.py
git commit -m "feat: add auto_categorise field to ReelCreate schema"
```

---

## Task 2: Celery task skips classification when `auto_categorise=False`

**Files:**
- Modify: `backend/workers/tasks.py`
- Modify: `backend/tests/test_auto_categorise_task.py` (add task tests)

- [ ] **Step 1: Write the failing task tests**

Append to `backend/tests/test_auto_categorise_task.py`:

```python
from unittest.mock import MagicMock, patch


def _make_supabase_mock():
    db = MagicMock()
    # .table("reels").select().eq().single().execute().data
    db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "url": "https://www.instagram.com/reel/ABC/",
        "user_id": "user-1",
        "status": "processing",
    }
    db.table.return_value.update.return_value.eq.return_value.execute.return_value = None
    db.table.return_value.upsert.return_value.execute.return_value = None
    # profiles for FCM token
    db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "url": "https://www.instagram.com/reel/ABC/",
        "user_id": "user-1",
        "status": "processing",
        "fcm_token": None,
    }
    return db


def _make_task_self():
    task_self = MagicMock()
    task_self.request.retries = 0
    task_self.max_retries = 3
    return task_self


def _make_download_result():
    r = MagicMock()
    r.audio_path = "/tmp/audio.m4a"
    r.temp_dir = "/tmp/reel_test"
    r.metadata.creator_handle = "testuser"
    r.metadata.hashtags = ["cooking"]
    r.metadata.caption = "My reel caption"
    r.metadata.thumbnail_url = None
    return r


def _make_transcription_result():
    t = MagicMock()
    t.text = "Hello world transcript"
    t.has_audio = True
    return t


def test_auto_categorise_false_skips_classify():
    """When auto_categorise=False, classify_reel is never called and status=ready with no category_id."""
    from workers.tasks import process_reel

    task_self = _make_task_self()
    mock_db = _make_supabase_mock()

    with patch("workers.tasks.get_supabase", return_value=mock_db), \
         patch("workers.tasks.download_reel", return_value=_make_download_result()), \
         patch("workers.tasks.transcribe_audio", return_value=_make_transcription_result()), \
         patch("workers.tasks.classify_reel") as mock_classify, \
         patch("workers.tasks.build_chunk_text", return_value=None), \
         patch("workers.tasks.send_push_notification"), \
         patch("os.path.exists", return_value=False):
        result = process_reel.run.__func__(task_self, "reel-123", False)

    mock_classify.assert_not_called()
    assert result["status"] == "ready"
    # Verify a DB update with status=ready and no category_id was made
    all_updates = [c.args[0] for c in mock_db.table.return_value.update.call_args_list]
    ready_updates = [u for u in all_updates if u.get("status") == "ready"]
    assert ready_updates, f"Expected at least one status=ready update, got: {all_updates}"
    assert all("category_id" not in u for u in ready_updates)


def test_auto_categorise_true_still_classifies():
    """When auto_categorise=True (default), classify_reel is called as normal."""
    from workers.tasks import process_reel

    task_self = _make_task_self()
    mock_db = _make_supabase_mock()

    classification = MagicMock()
    classification.category = "Cooking"
    classification.confidence = 0.95
    classification.alternatives = []

    # categories lookup for step 18
    mock_db.table.return_value.select.return_value.or_.return_value.execute.return_value.data = [
        {"id": "cat-1", "name": "Cooking"}
    ]

    with patch("workers.tasks.get_supabase", return_value=mock_db), \
         patch("workers.tasks.download_reel", return_value=_make_download_result()), \
         patch("workers.tasks.transcribe_audio", return_value=_make_transcription_result()), \
         patch("workers.tasks.classify_reel", return_value=classification) as mock_classify, \
         patch("workers.tasks.build_classification_signal", return_value=MagicMock(text="signal", source_summary="transcript")), \
         patch("workers.tasks.build_chunk_text", return_value=None), \
         patch("workers.tasks.send_push_notification"), \
         patch("os.path.exists", return_value=False):
        result = process_reel.run.__func__(task_self, "reel-123", True)

    mock_classify.assert_called_once()
```

- [ ] **Step 2: Run — expect FAIL**

```bash
python -m pytest tests/test_auto_categorise_task.py::test_auto_categorise_false_skips_classify tests/test_auto_categorise_task.py::test_auto_categorise_true_still_classifies -v
```

Expected: `TypeError: process_reel() takes 2 positional arguments but 3 were given` (or similar — the task doesn't accept `auto_categorise` yet).

- [ ] **Step 3: Add `auto_categorise` param and early-exit branch to `process_reel`**

In `backend/workers/tasks.py`, change the function signature:

```python
@celery_app.task(name="workers.tasks.process_reel", bind=True, max_retries=3)
def process_reel(self, reel_id: str, auto_categorise: bool = True) -> dict:
```

Then, after the line `_transcript_text = transcription.text if transcription is not None else None` (just before the existing Step 17 block), insert this early-exit branch:

```python
        # ------------------------------------------------------------------
        # Auto-categorise off — skip classification, land in Inbox
        # ------------------------------------------------------------------
        if not auto_categorise:
            log.info("auto_categorise=False — skipping classification, landing in Inbox")
            _chunk_text = build_chunk_text(
                transcript=_transcript_text,
                caption=meta.caption,
                hashtags=meta.hashtags,
            )
            if _chunk_text:
                log.info("step 20 | embedding | chars=%d", len(_chunk_text))
                try:
                    _embedding = embed_document(_chunk_text)
                    supabase.table("reel_chunks").upsert({
                        "reel_id": reel_id,
                        "user_id": reel_data["user_id"],
                        "chunk_index": 0,
                        "content": _chunk_text,
                        "embedding": _embedding,
                    }).execute()
                    log.info("step 20 | chunk stored")
                except EmbeddingError as exc:
                    log.warning("step 20 | embedding failed (non-fatal) | %s", exc)
            supabase.table("reels").update({"status": "ready"}).eq("id", reel_id).execute()
            send_push_notification(
                fcm_token=_fcm_token,
                title="Reel saved!",
                body="It's waiting in your Inbox.",
                data={"reel_id": reel_id, "status": "ready"},
            )
            return {"reel_id": reel_id, "status": "ready", "auto_categorise": False}
```

- [ ] **Step 4: Run task tests — expect PASS**

```bash
python -m pytest tests/test_auto_categorise_task.py -v
```

Expected: `4 passed` (2 schema + 2 task tests).

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
python -m pytest --tb=short -q
```

Expected: all existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add backend/workers/tasks.py backend/tests/test_auto_categorise_task.py
git commit -m "feat: auto_categorise=False skips classification in pipeline"
```

---

## Task 3: Reels endpoint passes `auto_categorise` to Celery

**Files:**
- Modify: `backend/api/v1/reels.py`

- [ ] **Step 1: Update `process_reel.delay()` call**

In `backend/api/v1/reels.py`, find:

```python
    if result.data:
        # Fresh insert — dispatch Celery task, return 202 (default).
        reel = result.data[0]
        process_reel.delay(reel["id"])
```

Replace with:

```python
    if result.data:
        # Fresh insert — dispatch Celery task, return 202 (default).
        reel = result.data[0]
        process_reel.delay(reel["id"], payload.auto_categorise)
```

- [ ] **Step 2: Run the existing reels endpoint tests**

```bash
python -m pytest tests/ -k "reel" -v --tb=short
```

Expected: all reel-related tests still pass.

- [ ] **Step 3: Commit**

```bash
git add backend/api/v1/reels.py
git commit -m "feat: pass auto_categorise from POST /reels to Celery task"
```

---

## Task 4: `DELETE /account` endpoint

**Files:**
- Create: `backend/api/v1/account.py`
- Modify: `backend/api/v1/__init__.py`
- Create: `backend/tests/test_account_endpoint.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_account_endpoint.py`:

```python
"""Tests for DELETE /api/v1/account."""
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import pytest


def _make_app():
    from api.deps import get_current_user_id
    from api.v1.account import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_user_id] = lambda: "user-test-id"
    return app


def test_delete_account_returns_204():
    """Successful deletion returns 204 No Content."""
    client = TestClient(_make_app())
    mock_db = MagicMock()

    with patch("api.v1.account.get_supabase", return_value=mock_db):
        response = client.delete(
            "/api/v1/account",
            headers={"Authorization": "Bearer fake-token"},
        )

    assert response.status_code == 204
    assert response.content == b""


def test_delete_account_calls_admin_delete_user():
    """admin.delete_user is called with the authenticated user's ID."""
    client = TestClient(_make_app())
    mock_db = MagicMock()

    with patch("api.v1.account.get_supabase", return_value=mock_db):
        client.delete(
            "/api/v1/account",
            headers={"Authorization": "Bearer fake-token"},
        )

    mock_db.auth.admin.delete_user.assert_called_once_with("user-test-id")
```

- [ ] **Step 2: Run — expect FAIL**

```bash
python -m pytest tests/test_account_endpoint.py -v
```

Expected: `ModuleNotFoundError: No module named 'api.v1.account'`.

- [ ] **Step 3: Create `backend/api/v1/account.py`**

```python
"""Account management endpoints."""

from fastapi import APIRouter, Depends, status

from api.deps import get_current_user_id
from supabase_client import get_supabase

router = APIRouter()


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(user_id: str = Depends(get_current_user_id)):
    """Permanently delete the authenticated user's account.

    Uses the service-role Supabase client to call auth.admin.delete_user,
    which cascades to profiles → reels → reel_chunks via FK ON DELETE CASCADE.
    """
    supabase = get_supabase()
    supabase.auth.admin.delete_user(user_id)
```

- [ ] **Step 4: Register the router in `backend/api/v1/__init__.py`**

Change:

```python
from api.v1 import chat, health, profiles, reels

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health.router, tags=["health"])
api_router.include_router(reels.router, prefix="/reels", tags=["reels"])
api_router.include_router(profiles.router, prefix="/profiles", tags=["profiles"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
```

to:

```python
from api.v1 import account, chat, health, profiles, reels

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health.router, tags=["health"])
api_router.include_router(reels.router, prefix="/reels", tags=["reels"])
api_router.include_router(profiles.router, prefix="/profiles", tags=["profiles"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(account.router, tags=["account"])
```

- [ ] **Step 5: Run account endpoint tests — expect PASS**

```bash
python -m pytest tests/test_account_endpoint.py -v
```

Expected: `2 passed`.

- [ ] **Step 6: Run full test suite**

```bash
python -m pytest --tb=short -q
```

Expected: all tests pass.

- [ ] **Step 7: Smoke test the endpoint is registered (start server briefly)**

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 &
sleep 2
curl -s http://localhost:8000/openapi.json | python -m json.tool | grep -A2 '"\/api\/v1\/account"'
kill %1
```

Expected output includes `"delete"` under `/api/v1/account`.

- [ ] **Step 8: Commit**

```bash
git add backend/api/v1/account.py backend/api/v1/__init__.py backend/tests/test_account_endpoint.py
git commit -m "feat: add DELETE /api/v1/account endpoint for account deletion"
```

---

## Task 5: Share Extension reads and passes `auto_categorise`

**Files:**
- Modify: `URL Sharing module/ShareViewController.swift`

- [ ] **Step 1: Add `readAutoCategorise()` helper and update `postURLToBackend`**

In `ShareViewController.swift`, add a new constant key in the `K` enum (after `authTokenKey`):

```swift
static let autoCategoriseKey = "autoCategorise"
```

Add a new private method after `readAuthToken()`:

```swift
private func readAutoCategorise() -> Bool {
    let value = UserDefaults(suiteName: K.appGroupID)?
        .object(forKey: K.autoCategoriseKey)
    // Default true: if the key was never written (user hasn't opened Settings yet),
    // behave as if auto-categorise is on.
    if let boolValue = value as? Bool {
        return boolValue
    }
    return true
}
```

In `handleURL(_:)`, update the call to `postURLToBackend` to pass the preference:

```swift
private func handleURL(_ url: URL) {
    Log.event("handleURL invoked for: \(url.absoluteString)")
    writeURLToAppGroup(url)
    let token = readAuthToken()
    let autoCategorise = readAutoCategorise()
    postURLToBackend(url: url, authToken: token, autoCategorise: autoCategorise)
}
```

Update `postURLToBackend` signature and body dict:

```swift
private func postURLToBackend(url: URL, authToken: String, autoCategorise: Bool) {
    guard let apiURL = URL(string: "\(K.backendBaseURL)/api/v1/reels") else {
        Log.error("Invalid backend URL constant — \(K.backendBaseURL)")
        return
    }

    var request = URLRequest(url: apiURL)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.setValue("Bearer \(authToken)", forHTTPHeaderField: "Authorization")
    request.timeoutInterval = 10
    let bodyDict: [String: Any] = [
        "url": url.absoluteString,
        "auto_categorise": autoCategorise,
    ]
    request.httpBody = try? JSONSerialization.data(withJSONObject: bodyDict)

    Log.net("➡️  POST \(apiURL.absoluteString)")
    Log.net("    Body: url=\(url.absoluteString) auto_categorise=\(autoCategorise)")
    // ... rest of the method unchanged
```

- [ ] **Step 2: Build in Xcode — expect no errors**

Open `ReelMind.xcworkspace`, select the `URL Sharing module` target, press ⌘B.

Expected: Build Succeeded.

- [ ] **Step 3: Commit**

```bash
git add "URL Sharing module/ShareViewController.swift"
git commit -m "feat: share extension reads auto_categorise preference and passes to backend"
```

---

## Task 6: SettingsView syncs `autoCategorise` to App Group UserDefaults

**Files:**
- Modify: `frontend/Views/SettingsView.swift`

- [ ] **Step 1: Add `onChange` and initial sync in `SettingsView`**

In `SettingsView`, the `body` currently ends with:

```swift
        .task { await notifManager.refresh() }
```

Replace that `.task` with:

```swift
        .task {
            await notifManager.refresh()
            // Ensure the share extension always has the current preference,
            // even before the user ever visits Settings.
            UserDefaults(suiteName: AppConfig.appGroupID)?
                .set(autoCategorise, forKey: "autoCategorise")
        }
        .onChange(of: autoCategorise) { _, newValue in
            UserDefaults(suiteName: AppConfig.appGroupID)?
                .set(newValue, forKey: "autoCategorise")
            if newValue {
                // User turned auto-categorise back on — reset banner so it
                // shows again if they later turn it off.
                UserDefaults.standard.set(false, forKey: "inboxBannerDismissed")
            }
        }
```

- [ ] **Step 2: Build in Xcode — expect no errors**

Press ⌘B on the main `ReelMind` target.

Expected: Build Succeeded.

- [ ] **Step 3: Verify manually**

Run on simulator (⌘R). Navigate to Settings. Toggle Auto-categorise off. Open a debugger console and verify:

```
po UserDefaults(suiteName: "group.com.reelmind.app")?.bool(forKey: "autoCategorise")
// Expected: false
```

Toggle it back on, verify the value returns `true`.

- [ ] **Step 4: Commit**

```bash
git add frontend/Views/SettingsView.swift
git commit -m "feat: sync autoCategorise toggle to App Group UserDefaults"
```

---

## Task 7: InboxView dismissible sage banner

**Files:**
- Modify: `frontend/Views/InboxView.swift`

- [ ] **Step 1: Add state and the `AutoCategoriseBanner` component**

At the top of `InboxView`, add two stored properties:

```swift
@AppStorage("autoCategorise") private var autoCategorise = true
@AppStorage("inboxBannerDismissed") private var bannerDismissed = false
```

At the bottom of `InboxView.swift` (after the `#Preview`), add the private banner component:

```swift
private struct AutoCategoriseBanner: View {
    let onDismiss: () -> Void
    let onSettings: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 9) {
            Text("✦")
                .font(.system(size: 14))
                .foregroundColor(Color(r: 0x4a, g: 0x64, b: 0x28))
                .padding(.top, 1)

            VStack(alignment: .leading, spacing: 2) {
                Text("Want your saved Reels sorted automatically?")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(Color(r: 0x30, g: 0x40, b: 0x20))
                HStack(spacing: 0) {
                    Text("Turn on ")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(Color(r: 0x30, g: 0x40, b: 0x20))
                    Button("Auto-categorise") { onSettings() }
                        .font(.system(size: 11, weight: .bold))
                        .foregroundColor(AppTheme.accentDark)
                    Text(" in Settings.")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(Color(r: 0x30, g: 0x40, b: 0x20))
                }
            }

            Spacer()

            Button { onDismiss() } label: {
                Text("✕")
                    .font(.system(size: 13, weight: .light))
                    .foregroundColor(Color(r: 0x6a, g: 0x82, b: 0x40))
            }
        }
        .padding(12)
        .background(
            LinearGradient(
                colors: [
                    Color(r: 0xdd, g: 0xe8, b: 0xc4),
                    Color(r: 0xcc, g: 0xd5, b: 0xae),
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Color(r: 0xb8, g: 0xcc, b: 0x9a), lineWidth: 1)
        )
    }
}
```

- [ ] **Step 2: Insert the banner in `reelList`**

In `InboxView.reelList`, after the `header` padding block and before `LazyVStack`, add:

```swift
if !autoCategorise && !bannerDismissed {
    AutoCategoriseBanner(
        onDismiss: { bannerDismissed = true },
        onSettings: { appVM.showSettings = true }
    )
    .padding(.horizontal, 14)
    .padding(.bottom, 4)
    .transition(.opacity)
}
```

- [ ] **Step 3: Insert the banner in `emptyState`**

Replace `emptyState` with:

```swift
private var emptyState: some View {
    VStack(spacing: 16) {
        if !autoCategorise && !bannerDismissed {
            AutoCategoriseBanner(
                onDismiss: { bannerDismissed = true },
                onSettings: { appVM.showSettings = true }
            )
            .padding(.horizontal, 20)
        }
        VStack(spacing: 12) {
            Image(systemName: "checkmark.circle")
                .font(.system(size: 44))
                .foregroundColor(AppTheme.accent)
            Text("All caught up")
                .font(.system(size: 18, weight: .semibold))
                .foregroundColor(AppTheme.textPrimary)
            Text("Every reel has been categorised.")
                .font(.system(size: 13))
                .foregroundColor(AppTheme.textMuted)
        }
    }
}
```

- [ ] **Step 4: Build and run — verify banner manually**

Run on simulator. In Settings, toggle Auto-categorise off. Navigate to Inbox. Expected:
- Banner appears in sage green with the message and ✕ button
- Tapping ✕ dismisses the banner (it should not reappear after navigating away and back)
- Tapping "Auto-categorise" in the message opens the Settings sheet
- Toggling auto-categorise back ON in Settings, then OFF again should show the banner again

- [ ] **Step 5: Commit**

```bash
git add frontend/Views/InboxView.swift
git commit -m "feat: dismissible auto-categorise info banner in InboxView"
```

---

## Task 8: `AuthSession.deleteAccount()` method

**Files:**
- Modify: `frontend/AuthSession.swift`

- [ ] **Step 1: Add `deleteAccount()` to `AuthSession`**

In `frontend/AuthSession.swift`, after the existing `signOut()` method, add:

```swift
func deleteAccount() async throws {
    guard let token = session?.accessToken else {
        throw URLError(.userAuthenticationRequired)
    }
    var request = URLRequest(
        url: AppConfig.backendBaseURL.appendingPathComponent("/api/v1/account")
    )
    request.httpMethod = "DELETE"
    request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    request.timeoutInterval = 15
    let (_, response) = try await URLSession.shared.data(for: request)
    guard let http = response as? HTTPURLResponse, http.statusCode == 204 else {
        throw URLError(.badServerResponse)
    }
    // The authStateChanges listener fires automatically when Supabase
    // invalidates the session server-side. No explicit signOut() needed.
}
```

- [ ] **Step 2: Build in Xcode — expect no errors**

Press ⌘B.

Expected: Build Succeeded.

- [ ] **Step 3: Commit**

```bash
git add frontend/AuthSession.swift
git commit -m "feat: add deleteAccount() to AuthSession"
```

---

## Task 9: SettingsView user card cleanup + delete account confirmation

**Files:**
- Modify: `frontend/Views/SettingsView.swift`

- [ ] **Step 1: Add state variables for delete flow**

At the top of `SettingsView` (alongside `@StateObject private var notifManager`), add:

```swift
@State private var showDeleteConfirmation = false
@State private var isDeletingAccount = false
@State private var deleteError: String? = nil
```

- [ ] **Step 2: Replace `userCard` computed property**

Find the entire `private var userCard: some View { ... }` block and replace it:

```swift
private var userCard: some View {
    HStack(spacing: 12) {
        Circle()
            .fill(AppTheme.avatarGradient)
            .frame(width: 42, height: 42)
            .overlay(
                Text(auth.session?.user.email?.prefix(1).uppercased() ?? "?")
                    .font(.system(size: 17, weight: .bold))
                    .foregroundColor(.white)
            )
        VStack(alignment: .leading, spacing: 2) {
            Text(auth.session?.user.userMetadata["full_name"] as? String ?? "—")
                .font(.system(size: 15, weight: .bold))
                .foregroundColor(AppTheme.textPrimary)
            Text(auth.session?.user.email ?? "—")
                .font(.system(size: 11))
                .foregroundColor(AppTheme.textFaint)
        }
        Spacer()
        Button {
            showDeleteConfirmation = true
        } label: {
            Image(systemName: "trash")
                .font(.system(size: 14))
                .foregroundColor(AppTheme.destructive)
        }
        .buttonStyle(.plain)
    }
    .padding(16)
    .background(AppTheme.surface)
    .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    .overlay(
        RoundedRectangle(cornerRadius: 16, style: .continuous)
            .stroke(AppTheme.border, lineWidth: 1)
    )
}
```

- [ ] **Step 3: Attach confirmation alert and loading overlay to the main ZStack**

The `body` currently returns a `ZStack`. Add `.alert` and an overlay for the loading state. Change the closing of the ZStack's `VStack` block to include the alert and loading overlay. The full body becomes:

```swift
var body: some View {
    ZStack {
        AppTheme.background.ignoresSafeArea()
        VStack(spacing: 0) {
            pageHeader
            ScrollView {
                VStack(spacing: 0) {
                    userCard
                        .padding(.horizontal, 14)
                        .padding(.bottom, 20)
                    librarySection
                        .padding(.horizontal, 14)
                        .padding(.bottom, 20)
                    savingSection
                        .padding(.horizontal, 14)
                        .padding(.bottom, 20)
                }
            }
        }

        if isDeletingAccount {
            Color.black.opacity(0.25).ignoresSafeArea()
            ProgressView()
                .tint(AppTheme.accentDark)
                .scaleEffect(1.2)
                .padding(24)
                .background(AppTheme.surface)
                .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        }
    }
    .alert("Delete your account?", isPresented: $showDeleteConfirmation) {
        Button("Delete account", role: .destructive) {
            Task {
                isDeletingAccount = true
                do {
                    try await auth.deleteAccount()
                } catch {
                    deleteError = "Something went wrong. Please try again."
                }
                isDeletingAccount = false
            }
        }
        Button("Cancel", role: .cancel) {}
    } message: {
        Text("All your reels, categories and data will be permanently removed. This cannot be undone.")
    }
    .alert("Couldn't delete account", isPresented: Binding(
        get: { deleteError != nil },
        set: { if !$0 { deleteError = nil } }
    )) {
        Button("OK", role: .cancel) {}
    } message: {
        Text(deleteError ?? "")
    }
    .task {
        await notifManager.refresh()
        UserDefaults(suiteName: AppConfig.appGroupID)?
            .set(autoCategorise, forKey: "autoCategorise")
    }
    .onChange(of: autoCategorise) { _, newValue in
        UserDefaults(suiteName: AppConfig.appGroupID)?
            .set(newValue, forKey: "autoCategorise")
        if newValue {
            UserDefaults.standard.set(false, forKey: "inboxBannerDismissed")
        }
    }
}
```

> **Note:** This replaces the `body` entirely and consolidates the `.task` and `.onChange` modifiers from Task 6 here. If Task 6 was already committed with those modifiers in a different location, move them here and remove the duplicates.

- [ ] **Step 4: Build in Xcode — expect no errors**

Press ⌘B.

Expected: Build Succeeded with no warnings about duplicate modifiers.

- [ ] **Step 5: Manual verification**

Run on simulator (⌘R):

1. Navigate to Settings.
2. Confirm the user card shows the display name on line 1 and email on line 2. No Edit button.
3. Confirm the trash icon appears on the right.
4. Tap the trash icon — confirmation alert should appear with "Delete account" (destructive red) and "Cancel".
5. Tap Cancel — nothing happens.
6. Tap trash again, tap "Delete account" — loading spinner overlay appears. *(Full end-to-end requires the backend to be running; the spinner will dismiss automatically once the server responds or an error appears.)*

- [ ] **Step 6: Commit**

```bash
git add frontend/Views/SettingsView.swift
git commit -m "feat: user card cleanup and delete account confirmation in SettingsView"
```

---

## Self-Review Checklist

- [x] Spec §1 (User card): Edit button removed, name + email shown, trash icon → Task 9 ✓
- [x] Spec §2 (Auto-categorise iOS): App Group sync → Task 6 ✓; Share Extension → Task 5 ✓; banner → Task 7 ✓; banner reset on toggle-on → Task 6 & 9 ✓
- [x] Spec §2 (Auto-categorise backend): Schema field → Task 1 ✓; Celery skip → Task 2 ✓; endpoint passthrough → Task 3 ✓
- [x] Spec §3 (Delete account): `AuthSession.deleteAccount()` → Task 8 ✓; SettingsView UI → Task 9 ✓; backend endpoint → Task 4 ✓
- [x] No TBDs or placeholders — all code blocks are complete
- [x] `get_current_user_id` used consistently (returns `str`) — Task 4 matches `api/deps.py` signature
- [x] `bannerDismissed` key `"inboxBannerDismissed"` consistent between Task 7 (`@AppStorage`) and Task 6/9 (`UserDefaults.standard.set`)
- [x] `AppConfig.appGroupID` used in Tasks 5, 6, 9 — matches existing constant in `SupabaseManager.swift`
