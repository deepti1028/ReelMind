# Feedback Form Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Send feedback" row to SettingsView that opens a sheet where the user picks a type and writes a message, which is emailed to deepti.jain2810@gmail.com via the Resend API.

**Architecture:** A new `POST /api/v1/feedback` FastAPI endpoint uses `httpx` (already installed) to call the Resend REST API. On iOS, a new `FeedbackAPI.swift` helper (matching the pattern in `ReelCategoryAPI.swift`) posts to the endpoint, and `FeedbackFormView.swift` is a SwiftUI sheet wired into `SettingsView` via a new "Support" section.

**Tech Stack:** FastAPI + Pydantic + httpx (backend); SwiftUI + URLSession (iOS); Resend REST API (email delivery)

---

## File Map

**New files:**
- `backend/api/v1/feedback.py` — POST /api/v1/feedback endpoint + Pydantic model
- `backend/tests/test_feedback_endpoint.py` — endpoint tests
- `frontend/FeedbackAPI.swift` — async network helper (mirrors `ReelCategoryAPI.swift`)
- `frontend/Views/FeedbackFormView.swift` — SwiftUI sheet with type picker + message field

**Modified files:**
- `backend/api/deps.py` — add `CurrentUser` dataclass + `get_current_user` dep
- `backend/api/v1/__init__.py` — register feedback router
- `backend/.env.example` — document `RESEND_API_KEY`
- `frontend/Views/SettingsView.swift` — add `showFeedbackForm` state + Support section + `.sheet`

---

## Task 1: Add `CurrentUser` dep to `backend/api/deps.py`

**Files:**
- Modify: `backend/api/deps.py`
- Create: `backend/tests/test_feedback_endpoint.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_feedback_endpoint.py`:

```python
from api.deps import CurrentUser


def test_current_user_is_dataclass():
    user = CurrentUser(id="abc", email="a@b.com")
    assert user.id == "abc"
    assert user.email == "a@b.com"
```

- [ ] **Step 2: Run — expect ImportError**

```bash
cd backend && source venv/bin/activate
pytest tests/test_feedback_endpoint.py::test_current_user_is_dataclass -v
```
Expected: `ImportError: cannot import name 'CurrentUser' from 'api.deps'`

- [ ] **Step 3: Add `CurrentUser` dataclass and `get_current_user` dep to `backend/api/deps.py`**

Add these imports at the top of the existing imports block:

```python
from dataclasses import dataclass
```

Then append after the existing `get_current_user_id` function:

```python
@dataclass
class CurrentUser:
    id: str
    email: str


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> CurrentUser:
    """Verify a Supabase JWT and return the user's id and email."""
    token = credentials.credentials
    supabase = get_supabase()
    try:
        response = supabase.auth.get_user(token)
        if response.user is None:
            raise ValueError("no user in response")
        return CurrentUser(
            id=str(response.user.id),
            email=response.user.email or "",
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired auth token",
        )
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_feedback_endpoint.py::test_current_user_is_dataclass -v
```
Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/api/deps.py backend/tests/test_feedback_endpoint.py
git commit -m "feat: add CurrentUser dep to api/deps"
```

---

## Task 2: Create `backend/api/v1/feedback.py` endpoint

**Files:**
- Create: `backend/api/v1/feedback.py`
- Modify: `backend/tests/test_feedback_endpoint.py`

- [ ] **Step 1: Replace `backend/tests/test_feedback_endpoint.py` with the full test file**

Overwrite the entire file (the Task 1 dataclass test is preserved inside it):

```python
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import CurrentUser, get_current_user
from api.v1.feedback import router   # will cause ImportError until Task 2 Step 3


def test_current_user_is_dataclass():
    user = CurrentUser(id="abc", email="a@b.com")
    assert user.id == "abc"
    assert user.email == "a@b.com"


_app = FastAPI()
_app.include_router(router)
_app.dependency_overrides[get_current_user] = lambda: CurrentUser(
    id="user-test-uuid", email="tester@example.com"
)
client = TestClient(_app)

VALID_PAYLOAD = {"type": "Bug Report", "message": "Something is broken."}


@patch("api.v1.feedback.httpx.AsyncClient")
def test_send_feedback_success(mock_cls):
    mock_resp = MagicMock()
    mock_resp.is_success = True
    mock_cls.return_value.__aenter__.return_value.post.return_value = mock_resp
    resp = client.post("/feedback", json=VALID_PAYLOAD)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


@patch("api.v1.feedback.httpx.AsyncClient")
def test_send_feedback_resend_failure_returns_502(mock_cls):
    mock_resp = MagicMock()
    mock_resp.is_success = False
    mock_cls.return_value.__aenter__.return_value.post.return_value = mock_resp
    resp = client.post("/feedback", json=VALID_PAYLOAD)
    assert resp.status_code == 502


def test_send_feedback_empty_message_returns_422():
    resp = client.post("/feedback", json={"type": "General", "message": ""})
    assert resp.status_code == 422


def test_send_feedback_invalid_type_returns_422():
    resp = client.post("/feedback", json={"type": "Other", "message": "hi"})
    assert resp.status_code == 422


@patch("api.v1.feedback.httpx.AsyncClient")
def test_email_body_contains_user_email(mock_cls):
    mock_resp = MagicMock()
    mock_resp.is_success = True
    mock_cls.return_value.__aenter__.return_value.post.return_value = mock_resp
    client.post("/feedback", json=VALID_PAYLOAD)
    call_kwargs = mock_cls.return_value.__aenter__.return_value.post.call_args.kwargs
    assert "tester@example.com" in call_kwargs["json"]["text"]


@patch("api.v1.feedback.httpx.AsyncClient")
def test_email_subject_contains_type(mock_cls):
    mock_resp = MagicMock()
    mock_resp.is_success = True
    mock_cls.return_value.__aenter__.return_value.post.return_value = mock_resp
    client.post("/feedback", json=VALID_PAYLOAD)
    call_kwargs = mock_cls.return_value.__aenter__.return_value.post.call_args.kwargs
    assert call_kwargs["json"]["subject"] == "[ReelMind Feedback] Bug Report"


@patch("api.v1.feedback.httpx.AsyncClient")
def test_no_resend_key_returns_500(mock_cls, monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    resp = client.post("/feedback", json=VALID_PAYLOAD)
    assert resp.status_code == 500
```

- [ ] **Step 2: Run — expect ImportError**

```bash
pytest tests/test_feedback_endpoint.py -v
```
Expected: `ImportError: cannot import name 'router' from 'api.v1.feedback'`

- [ ] **Step 3: Create `backend/api/v1/feedback.py`**

```python
"""Feedback endpoint — emails user feedback to the app owner via Resend."""

import os
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.deps import CurrentUser, get_current_user

router = APIRouter()

_RESEND_URL = "https://api.resend.com/emails"
_FEEDBACK_TO = "deepti.jain2810@gmail.com"
_FEEDBACK_FROM = "onboarding@resend.dev"


class FeedbackRequest(BaseModel):
    type: Literal["Bug Report", "Feature Request", "General"]
    message: str = Field(..., min_length=1, max_length=2000)


@router.post("/feedback", status_code=status.HTTP_200_OK)
async def send_feedback(
    body: FeedbackRequest,
    user: CurrentUser = Depends(get_current_user),
):
    api_key = os.getenv("RESEND_API_KEY", "")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Feedback service not configured",
        )

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _RESEND_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "from": _FEEDBACK_FROM,
                "to": [_FEEDBACK_TO],
                "subject": f"[ReelMind Feedback] {body.type}",
                "text": f"From: {user.email}\n\n{body.message}",
            },
        )

    if not resp.is_success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to send feedback",
        )

    return {"ok": True}
```

- [ ] **Step 4: Run — expect all PASS**

```bash
pytest tests/test_feedback_endpoint.py -v
```
Expected: 7 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/api/v1/feedback.py backend/tests/test_feedback_endpoint.py
git commit -m "feat: add POST /api/v1/feedback endpoint via Resend"
```

---

## Task 3: Register router and document env var

**Files:**
- Modify: `backend/api/v1/__init__.py`
- Modify: `backend/.env.example`

- [ ] **Step 1: Register feedback router in `backend/api/v1/__init__.py`**

Change the import line from:
```python
from api.v1 import account, chat, health, profiles, reels
```
To:
```python
from api.v1 import account, chat, feedback, health, profiles, reels
```

Add after `api_router.include_router(account.router, tags=["account"])`:
```python
api_router.include_router(feedback.router, tags=["feedback"])
```

- [ ] **Step 2: Add `RESEND_API_KEY` to `backend/.env.example`**

Add after the `FIREBASE_SERVICE_ACCOUNT_JSON` block:
```
# Resend API (for in-app feedback emails — set on the web service only)
# Get key at https://resend.com/api-keys
RESEND_API_KEY=your_resend_api_key_here
```

- [ ] **Step 3: Verify route appears in API docs**

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
Open http://localhost:8000/docs — confirm `POST /api/v1/feedback` is listed under the "feedback" tag.

- [ ] **Step 4: Commit**

```bash
git add backend/api/v1/__init__.py backend/.env.example
git commit -m "feat: register feedback router; document RESEND_API_KEY env var"
```

---

## Task 4: iOS — Create `FeedbackAPI.swift`

**Files:**
- Create: `frontend/FeedbackAPI.swift`

- [ ] **Step 1: Create `frontend/FeedbackAPI.swift`**

Follows the exact same pattern as `frontend/ReelCategoryAPI.swift` — reads auth token from App Group UserDefaults, fires async URLSession request.

```swift
import Foundation

enum FeedbackAPI {
    enum FeedbackType: String, CaseIterable {
        case bugReport      = "Bug Report"
        case featureRequest = "Feature Request"
        case general        = "General"
    }

    static func send(type: FeedbackType, message: String) async throws {
        guard
            let defaults = UserDefaults(suiteName: AppConfig.appGroupID),
            let authToken = defaults.string(forKey: AppConfig.authTokenKey)
        else {
            throw URLError(.userAuthenticationRequired)
        }

        let url = AppConfig.backendBaseURL.appendingPathComponent("api/v1/feedback")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(authToken)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode([
            "type": type.rawValue,
            "message": message,
        ])

        let (_, response) = try await URLSession.shared.data(for: request)
        guard
            let http = response as? HTTPURLResponse,
            (200...299).contains(http.statusCode)
        else {
            throw URLError(.badServerResponse)
        }
    }
}
```

- [ ] **Step 2: Add file to Xcode target**

In Xcode: right-click the `ReelMind` group in the navigator → "Add Files to ReelMind" → select `FeedbackAPI.swift`. Ensure only the "ReelMind" target checkbox is checked (not the Share Extension).

- [ ] **Step 3: Build (⌘B) — expect zero errors**

- [ ] **Step 4: Commit**

```bash
git add frontend/FeedbackAPI.swift
git commit -m "feat: add FeedbackAPI async send helper"
```

---

## Task 5: iOS — Create `FeedbackFormView.swift`

**Files:**
- Create: `frontend/Views/FeedbackFormView.swift`

- [ ] **Step 1: Create `frontend/Views/FeedbackFormView.swift`**

`FormSection` is a private struct that mirrors the `SettingsSection` in `SettingsView.swift` (which is `private` and can't be shared cross-file). Duplicating it here keeps each file self-contained.

```swift
import SwiftUI

struct FeedbackFormView: View {
    @Environment(\.dismiss) private var dismiss

    @State private var selectedType: FeedbackAPI.FeedbackType = .general
    @State private var message = ""
    @State private var isSending = false
    @State private var showSuccess = false
    @State private var showError = false

    private var canSend: Bool {
        !message.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !isSending
    }

    var body: some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()
            VStack(spacing: 0) {
                handle
                header
                ScrollView {
                    VStack(spacing: 0) {
                        typePicker
                            .padding(.horizontal, 14)
                            .padding(.bottom, 20)
                        messageField
                            .padding(.horizontal, 14)
                            .padding(.bottom, 24)
                        sendButton
                            .padding(.horizontal, 14)
                    }
                }
            }
            if showSuccess {
                successToast
            }
        }
        .alert("Couldn't send feedback", isPresented: $showError) {
            Button("OK", role: .cancel) {}
        } message: {
            Text("Something went wrong. Please try again.")
        }
    }

    // MARK: - Sub-views

    private var handle: some View {
        RoundedRectangle(cornerRadius: 2, style: .continuous)
            .fill(AppTheme.border)
            .frame(width: 36, height: 4)
            .padding(.top, 10)
            .padding(.bottom, 6)
    }

    private var header: some View {
        HStack {
            Text("Send Feedback")
                .font(.system(size: 17, weight: .bold))
                .foregroundColor(AppTheme.textPrimary)
            Spacer()
            Button("Cancel") { dismiss() }
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(AppTheme.accentDark)
        }
        .padding(.horizontal, 18)
        .padding(.bottom, 16)
    }

    private var typePicker: some View {
        FormSection(title: "Type") {
            HStack {
                Text("Feedback type")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(AppTheme.textPrimary)
                Spacer()
                Picker("", selection: $selectedType) {
                    ForEach(FeedbackAPI.FeedbackType.allCases, id: \.self) { t in
                        Text(t.rawValue).tag(t)
                    }
                }
                .pickerStyle(.menu)
                .tint(AppTheme.accentDark)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 13)
        }
    }

    private var messageField: some View {
        FormSection(title: "Message") {
            ZStack(alignment: .topLeading) {
                if message.isEmpty {
                    Text("Describe your feedback…")
                        .font(.system(size: 13))
                        .foregroundColor(AppTheme.textFaint)
                        .padding(.horizontal, 14)
                        .padding(.top, 14)
                        .allowsHitTesting(false)
                }
                TextEditor(text: $message)
                    .font(.system(size: 13))
                    .foregroundColor(AppTheme.textPrimary)
                    .scrollContentBackground(.hidden)
                    .background(Color.clear)
                    .frame(minHeight: 120)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 10)
                    .onChange(of: message) { _, newValue in
                        if newValue.count > 2000 {
                            message = String(newValue.prefix(2000))
                        }
                    }
            }
        }
    }

    private var sendButton: some View {
        Button {
            Task { await submitFeedback() }
        } label: {
            ZStack {
                AppTheme.buttonGradient
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                if isSending {
                    ProgressView().tint(.white)
                } else {
                    Text("Send")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(.white)
                }
            }
            .frame(height: 50)
        }
        .disabled(!canSend)
    }

    private var successToast: some View {
        VStack {
            Spacer()
            Text("Feedback sent!")
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(.white)
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
                .background(AppTheme.accentDark)
                .clipShape(Capsule())
                .padding(.bottom, 40)
        }
        .transition(.move(edge: .bottom).combined(with: .opacity))
    }

    // MARK: - Action

    private func submitFeedback() async {
        isSending = true
        do {
            try await FeedbackAPI.send(type: selectedType, message: message)
            withAnimation { showSuccess = true }
            try? await Task.sleep(for: .seconds(1.5))
            dismiss()
        } catch {
            showError = true
        }
        isSending = false
    }
}

// Mirrors the private SettingsSection in SettingsView.swift — duplicated
// intentionally to keep each file self-contained.
private struct FormSection<Content: View>: View {
    let title: String
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.system(size: 10, weight: .semibold))
                .foregroundColor(AppTheme.textFaint)
                .textCase(.uppercase)
                .kerning(1.2)
                .padding(.leading, 4)
            VStack(spacing: 0) {
                content
            }
            .background(AppTheme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(AppTheme.border, lineWidth: 1)
            )
        }
    }
}

#Preview {
    FeedbackFormView()
}
```

- [ ] **Step 2: Add file to Xcode target**

In Xcode: right-click the `Views` group → "Add Files to ReelMind" → select `FeedbackFormView.swift`. Ensure only the "ReelMind" target is checked.

- [ ] **Step 3: Build (⌘B) — expect zero errors**

- [ ] **Step 4: Commit**

```bash
git add frontend/Views/FeedbackFormView.swift
git commit -m "feat: add FeedbackFormView sheet"
```

---

## Task 6: iOS — Wire `FeedbackFormView` into `SettingsView`

**Files:**
- Modify: `frontend/Views/SettingsView.swift`

- [ ] **Step 1: Add `showFeedbackForm` state**

In `SettingsView`, after the line `@State private var deleteError: String? = nil` (line 14), add:

```swift
@State private var showFeedbackForm = false
```

- [ ] **Step 2: Add `supportSection` computed property**

After the closing brace of `savingSection` (around line 214), add:

```swift
private var supportSection: some View {
    SettingsSection(title: "Support") {
        Button {
            showFeedbackForm = true
        } label: {
            SettingsRow(icon: "paperplane", iconBg: AppTheme.surfaceSecondary,
                        label: "Send feedback") {
                EmptyView()
            }
        }
        .buttonStyle(.plain)
    }
}
```

- [ ] **Step 3: Add `supportSection` to the scroll view body**

In `body`, after the `savingSection` block (the `.padding(.bottom, 20)` after `savingSection`), add:

```swift
supportSection
    .padding(.horizontal, 14)
    .padding(.bottom, 20)
```

- [ ] **Step 4: Add `.sheet` modifier**

After the last `.alert` modifier (the "Couldn't delete account" alert, around line 68), add:

```swift
.sheet(isPresented: $showFeedbackForm) {
    FeedbackFormView()
}
```

- [ ] **Step 5: Build and run (⌘R)**

Navigate to Settings. Verify:
1. A "Support" section with a "Send feedback" row (paperplane icon, sage squircle, chevron) appears below "Saving"
2. Tapping the row presents `FeedbackFormView` as a bottom sheet
3. "Cancel" dismisses the sheet
4. Send button is disabled when message is empty
5. Send button shows a spinner while the request is in-flight
6. On success: toast appears, sheet auto-dismisses after ~1.5 s
7. On network failure (airplane mode): error alert appears, sheet stays open

- [ ] **Step 6: Commit**

```bash
git add frontend/Views/SettingsView.swift
git commit -m "feat: wire FeedbackFormView into SettingsView support section"
```

---

## Post-deploy: Set `RESEND_API_KEY` on Render

After deploying the backend:
1. Sign up at https://resend.com and create an API key
2. In Render dashboard → `reelmind-api` web service → Environment → add `RESEND_API_KEY=re_...`
3. Redeploy the service
4. Send a test feedback from the app and confirm the email arrives at deepti.jain2810@gmail.com
