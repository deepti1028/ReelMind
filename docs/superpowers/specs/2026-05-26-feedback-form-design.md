# Feedback Form — Design Spec
_2026-05-26_

## Overview

Add a "Send feedback" row to the Settings page. Tapping it opens a sheet where the user picks a feedback type and writes a message. Tapping Send posts to a new FastAPI endpoint, which emails the feedback to `deepti.jain2810@gmail.com` via the Resend API.

---

## iOS UI

### Settings page change

A new `SettingsSection` titled **"Support"** is added below the existing "Saving" section, containing a single row:

- Icon: `paperplane` SF Symbol
- Icon background: `AppTheme.surfaceSecondary` (#e9edc9, sage-green squircle)
- Icon color: `AppTheme.accentDark` (#9a6a35)
- Label: `"Send feedback"`
- Trailing: chevron (`›`)
- Action: sets `showFeedbackForm = true` → presents `FeedbackFormView` as a `.sheet`

### FeedbackFormView (new file)

A SwiftUI sheet with:

**Header**
- Title: "Send Feedback" (bold, `textPrimary`)
- Trailing "Cancel" button (`accentDark`) — dismisses sheet, discards input

**Type picker** — `SettingsSection`-style card with a `Picker` (`.menu` style):
- Options: `"Bug Report"`, `"Feature Request"`, `"General"`
- Default: `"General"`

**Message field** — multiline `TextEditor` inside a `SettingsSection`-style card:
- Placeholder: `"Describe your feedback…"` (shown when empty via `ZStack`)
- Min height: 120 pt
- Max length: 2000 characters enforced via `.onChange`

**Send button** — full-width, `AppTheme.buttonGradient` background, `cornerRadius 14`:
- Disabled and shows `ProgressView` while request is in-flight
- Disabled when `message.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty`

**State machine:** `idle → sending → (success | error)`
- `success`: `FeedbackFormView` sets `showSuccess = true`, displays a brief "Feedback sent!" overlay for 1.5 s, then auto-dismisses itself
- `error`: sheet stays open; error alert shown: "Couldn't send feedback. Please try again."

---

## Backend

### New file: `backend/api/v1/feedback.py`

**Route:** `POST /api/v1/feedback`

**Auth:** `Depends(get_current_user)` — authenticated users only (reuses existing dep from `api/deps.py`).

**Request body (Pydantic):**
```python
class FeedbackRequest(BaseModel):
    type: Literal["Bug Report", "Feature Request", "General"]
    message: str = Field(..., min_length=1, max_length=2000)
```

**Implementation:**
1. Build email payload:
   - `to`: `deepti.jain2810@gmail.com`
   - `from`: `onboarding@resend.dev` (Resend's built-in shared sender — works without domain verification, no extra setup required)
   - `subject`: `[ReelMind Feedback] {request.type}`
   - `text`: `f"From: {current_user.email}\n\n{request.message}"`
2. `httpx.post("https://api.resend.com/emails", headers={"Authorization": f"Bearer {RESEND_API_KEY}"}, json=payload)`
3. If Resend returns non-2xx → raise `HTTPException(status_code=502, detail="Failed to send feedback")`
4. Return `{"ok": True}`

**New env var:** `RESEND_API_KEY` — add to `backend/.env.example`, set on Render (both web service and worker, though only the web service uses it).

**Router registration:** include `feedback.router` in `backend/main.py` alongside existing routers.

---

## Error Handling

| Scenario | Backend | iOS |
|---|---|---|
| Empty message | 422 Pydantic validation | Send button disabled (client-side guard) |
| Resend API failure | 502 | Error alert, sheet stays open |
| Network timeout / no connection | URLSession error | Same error alert |
| Unauthenticated | 401 | Cannot occur — Settings is only reachable when logged in |

---

## Dependencies

- No new iOS dependencies
- No new Python packages (`httpx` already in `requirements.txt`)
- New external service: [Resend](https://resend.com) (free tier: 3,000 emails/month)
- New env var: `RESEND_API_KEY`

---

## Out of Scope

- Attachment / screenshot upload
- In-app feedback history
- Rate limiting on the endpoint
- Email threading / reply tracking
