# Design: Private Reel & Non-Reel URL Rejection

**Date:** 2026-05-26  
**Status:** Approved

---

## Problem

1. Users can currently share any URL (stories, posts, non-Instagram links) to ReelMind — it gets inserted into the DB and sits as a failed reel with no helpful feedback.
2. Private reel URLs pass URL validation but fail during Celery download — they land as `status=failed` rows in the DB with a generic "Something went wrong" notification.
3. The user gets no notification in either case that clearly explains what went wrong.

**Goal:** Reject non-reel and private content at the earliest possible point, leave zero DB trace, and notify the user with a clear, descriptive message every time.

---

## Architecture

### Where each check happens

| Scenario | Detection point | DB row? | Notification path |
|---|---|---|---|
| Non-Instagram URL | `reels.py` (before insert) | Never created | Celery `notify_invalid_url` task + Extension label |
| Instagram but not a reel (story, post, IGTV) | `reels.py` (before insert) | Never created | Celery `notify_invalid_url` task + Extension label |
| Private reel (401/403 / login-wall) | `process_reel` Step 15 catch | Created → deleted | FCM push via `send_push_notification` |
| Private account flag in parsed JSON | `process_reel` post-download check | Created → deleted | FCM push via `send_push_notification` |
| Wrong `product_type` in parsed JSON | `process_reel` post-download check | Created → deleted | FCM push via `send_push_notification` |

---

## Changes

### 1. `backend/services/downloader.py`

Add `is_private_content: bool = False` to `DownloadError.__init__`.

Mark the following existing raises with `is_private_content=True`:
- HTTP 401/403 response (private reel / login required)
- Login-wall redirect (`/accounts/login` in response URL or `"LoginAndSignupPage"` in body)

### 2. `backend/api/v1/reels.py`

Add `_is_instagram_reel_url(url: str) -> str | None` helper. Returns `None` if valid, or a reason string (`"not_instagram"` / `"not_a_reel"`) if invalid.

Rules:
- Hostname must be `instagram.com` or `www.instagram.com` → else `"not_instagram"`
- Path must start with `/reel/` or `/reels/` → else `"not_a_reel"`

In `create_reel`, call this **before** the profiles upsert and reels upsert. On rejection:
- Dispatch `notify_invalid_url.delay(user_id, reason)`
- Raise `HTTPException(status_code=422, detail={"reason": reason, "message": <human string>})`

### 3. `backend/workers/tasks.py`

**New Celery task: `notify_invalid_url(user_id, reason)`**
- Fetches FCM token from `profiles`
- Sends FCM push with message based on reason:
  - `"not_instagram"` → "Can't save this" / "That doesn't look like an Instagram link. ReelMind only saves Instagram Reels."
  - `"not_a_reel"` → "Can't save this" / "That looks like a post or story, not a Reel. Find the Reel in Instagram and share it from there."
- Non-fatal: any DB/FCM failure is caught and logged.

**In `process_reel` — Step 15 catch block:**

Replace the existing `_handle_pipeline_error` call for `DownloadError` with a branch:
- If `exc.is_private_content`:
  - DELETE the reel row from DB
  - Send FCM push: "Can't save this" / "That's a private reel — ReelMind can only save Reels from public accounts."
  - Return early (no retry)
- Else: existing `_handle_pipeline_error` path (retry logic, generic failure push)

**In `process_reel` — after Step 15 (post-download checks), before Step 16:**

Check 1 — private account:
```python
if meta.user.is_private:
    supabase.table("reels").delete().eq("id", reel_id).execute()
    send_push_notification(fcm_token, "Can't save this",
        "That's a private reel — ReelMind can only save Reels from public accounts.",
        {"reel_id": reel_id, "status": "rejected_private"})
    return {"reel_id": reel_id, "status": "rejected_private"}
```

Check 2 — wrong product type:
```python
if meta.product_type and meta.product_type != "clips":
    supabase.table("reels").delete().eq("id", reel_id).execute()
    send_push_notification(fcm_token, "Can't save this",
        "That doesn't look like a Reel — ReelMind only saves Instagram Reels.",
        {"reel_id": reel_id, "status": "rejected_not_reel"})
    return {"reel_id": reel_id, "status": "rejected_not_reel"}
```

Both checks must happen inside the `try` block so the `finally` cleanup still runs.

### 4. `URL Sharing module/ShareViewController.swift`

**Add state:**
```swift
private var saveRejected = false
private var rejectMessage = "Not a Reel"
private var rejectSubtitle = "ReelMind only saves Instagram Reels"
```

**In `postURLToBackend` network callback:** Handle 422 alongside 200:
```swift
if status == 422 {
    // Parse reason from response body if possible, else use defaults
    DispatchQueue.main.async { [weak self] in
        guard let self else { return }
        self.saveRejected = true
        // Parse detail from JSON response body for specific message
        self.applyResultLabels()
    }
}
```

**In `applyResultLabels()`:** Add third branch for rejected state:
```swift
if saveRejected {
    savedTitleLabel.text = rejectMessage
    savedInfoLabel.text = rejectSubtitle
} else if duplicateSaveDetected { ... } else { ... }
```

---

## Notification messages (complete reference)

| Scenario | Title | Body |
|---|---|---|
| Not Instagram | "Can't save this" | "That doesn't look like an Instagram link. ReelMind only saves Instagram Reels." |
| Instagram but not a reel | "Can't save this" | "That looks like a post or story, not a Reel. Find the Reel in Instagram and share it from there." |
| Private reel (any detection point) | "Can't save this" | "That's a private reel — ReelMind can only save Reels from public accounts." |
| Wrong product_type | "Can't save this" | "That doesn't look like a Reel — ReelMind only saves Instagram Reels." |

---

## Error flow summary

```
User shares URL
    │
    ▼
reels.py: _is_instagram_reel_url()
    ├─ Not Instagram / not a reel → 422 + notify_invalid_url Celery task
    │                                        + Extension label update
    └─ Valid reel URL → insert row, dispatch process_reel
                            │
                            ▼
                        Step 15: download_reel()
                            ├─ DownloadError(is_private_content=True)
                            │       → DELETE row → FCM "private reel"
                            ├─ DownloadError(retryable) → retry / fail
                            └─ Success → check metadata
                                    ├─ user.is_private → DELETE row → FCM
                                    ├─ product_type != "clips" → DELETE row → FCM
                                    └─ OK → continue pipeline (Steps 16–22)
```

---

## Out of scope

- Rate-limited IP detection (already handled as retryable — no change)
- Offline queue drain in the main app (`pendingReelURLs`) — separate backlog item
- Showing rejection state persistently in the library UI — nothing to show since row is deleted
