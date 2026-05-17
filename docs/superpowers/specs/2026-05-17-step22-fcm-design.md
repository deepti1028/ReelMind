# Step 22 — FCM Push Notifications Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Step 22 of the ingestion pipeline — push notifications via Firebase Cloud Messaging (FCM) for all terminal reel states. Includes a `pending_category` notification with iOS action buttons (category suggestions), a dedicated `CategoriseReelView` for in-app categorisation, and FCM token upload from iOS to the backend.

**Architecture:** New `services/notifier.py` on the backend (Firebase Admin SDK, pure function, never pipeline-fatal). iOS changes in `AppDelegate` (notification category registration, action handler) and a new `CategoriseReelView`. FCM token uploaded on login and on token refresh. All APNs-dependent paths are mocked with graceful no-ops and clearly marked `# TODO: APNs setup required`.

**Tech Stack:** `firebase-admin` Python package (free), Firebase Cloud Messaging (free tier), iOS `UserNotifications` framework, iOS `URLSession` for background action API calls.

**APNs dependency:** End-to-end delivery to a real iOS device requires an APNs Auth Key (.p8) uploaded to Firebase Console. This requires a paid Apple Developer account. All code is implementable now; delivery can be tested with Firebase's test message tool (simulator) once credentials are available. See the APNs Backlog section at the bottom of this document.

---

## Files

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/services/notifier.py` | FCM send via Firebase Admin SDK |
| Create | `backend/tests/test_notifier.py` | Unit tests (mocked firebase_admin) |
| Modify | `backend/workers/tasks.py` | Fill all `# TODO Step 22` markers |
| Modify | `backend/workers/beat_tasks.py` | Fill timeout `# TODO Step 22` marker |
| Modify | `backend/api/v1/reels.py` | Fill PATCH endpoint `# TODO Step 22` markers + add `PATCH /profiles/fcm-token` |
| Modify | `backend/config.py` | Add `FIREBASE_SERVICE_ACCOUNT_JSON` config key |
| Modify | `backend/api/v1/reels.py` | Add `PATCH /api/v1/profiles/fcm-token` endpoint |
| Modify | `frontend/ReelMindApp.swift` | Register `CATEGORISE` notification category; handle action responses; upload FCM token |
| Create | `frontend/CategoriseReelView.swift` | Dedicated categorise screen opened from "Choose in App" button |
| Create | `frontend/ReelCategoryAPI.swift` | `URLSession`-based background API calls from notification handler |
| Create | `frontend/ProfileAPI.swift` | FCM token upload to backend |

---

## Notification Types

Five FCM notifications cover all terminal pipeline states:

| Trigger | Title | Body | iOS category_id | data keys |
|---------|-------|------|----------------|-----------|
| `status = ready` (auto-assigned, ≥70% confidence) | "Reel saved!" | "Categorised as {category_name}" | `nil` | `reel_id`, `status` |
| `status = pending_category` (low confidence) | "Help us categorise this reel" | "Your reel is saved — which fits best? Ignoring this saves it to Uncategorised." | `"CATEGORISE"` | `reel_id`, `suggestions` (JSON array string, up to 2 names) |
| User picks category via PATCH endpoint | "Reel categorised!" | "Moved to {category_name}" | `nil` | `reel_id`, `status` |
| Beat task timeout → `uncategorised` | "Reel saved" | "Added to Uncategorised — you can move it anytime" | `nil` | `reel_id`, `status` |
| Step 17 no-signal → `uncategorised` | "Reel saved" | "We couldn't categorise it — no audio or caption found" | `nil` | `reel_id`, `status` |

---

## `services/notifier.py` (Backend)

### Firebase Admin SDK initialization

Initialized once at module level via a singleton. Gracefully skips if credentials are missing:

```python
import base64
import json
import logging

import firebase_admin
from firebase_admin import credentials, messaging

from config import get_config

logger = logging.getLogger(__name__)

_firebase_app: firebase_admin.App | None = None


def _get_firebase_app() -> firebase_admin.App | None:
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app
    cfg = get_config()
    if not cfg.FIREBASE_SERVICE_ACCOUNT_JSON:
        # TODO: APNs setup required — add FIREBASE_SERVICE_ACCOUNT_JSON to env vars
        logger.warning("notifier | FIREBASE_SERVICE_ACCOUNT_JSON not set — FCM disabled")
        return None
    service_account = json.loads(base64.b64decode(cfg.FIREBASE_SERVICE_ACCOUNT_JSON))
    cred = credentials.Certificate(service_account)
    _firebase_app = firebase_admin.initialize_app(cred)
    return _firebase_app
```

### Public function

```python
def send_push_notification(
    fcm_token: str | None,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
    category_id: str | None = None,
) -> bool:
    """Send an FCM push notification to one device.

    Returns True on success, False on skip or failure.
    Never raises — notification failure is never pipeline-fatal.

    Args:
        fcm_token:   Device FCM token. None → skips silently.
        title:       Notification title.
        body:        Notification body text.
        data:        Optional string key-value data payload (reel_id, etc.).
        category_id: iOS UNNotificationCategory identifier (e.g. "CATEGORISE").
    """
    if not fcm_token:
        logger.warning("notifier | no fcm_token — skipping push")
        return False

    app = _get_firebase_app()
    if app is None:
        return False  # credentials not configured, already logged at init

    apns_config = None
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
        logger.error("notifier | push failed | %s", exc)
        return False
```

### Error handling

Notification failure is **never pipeline-fatal**. The reel is already in its correct terminal state in the DB before `send_push_notification` is called. All failure modes return `False` and log — they never raise.

| Condition | Behaviour |
|-----------|-----------|
| `fcm_token` is `None` | Log warning, return `False` |
| `FIREBASE_SERVICE_ACCOUNT_JSON` not set | Log warning at init, return `False` |
| `messaging.send()` raises any exception | Log error, return `False` |

---

## Backend: `config.py` addition

```python
# Firebase Admin SDK (Step 22 FCM push)
FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")  # base64-encoded JSON
```

Add to `.env.example`:
```
# Firebase Admin SDK service account (base64-encoded JSON) — required for FCM push (Step 22)
# TODO: APNs setup required — download from Firebase Console → Project Settings → Service Accounts
FIREBASE_SERVICE_ACCOUNT_JSON=
```

---

## Backend: FCM token endpoint

`PATCH /api/v1/profiles/fcm-token`

Called by iOS on login and on token refresh.

**Request body:**
```json
{"fcm_token": "eXaMpLeT0k3n..."}
```

**Steps:**
1. Auth via `deps.py`
2. Update `profiles` row:
   ```python
   {"fcm_token": fcm_token, "fcm_token_updated_at": datetime.now(timezone.utc)}
   ```
3. Return `200 {"status": "ok"}`

---

## Backend: Filling `# TODO Step 22` markers in `tasks.py`

### Fetch FCM token once near the top of `process_reel` (after fetching reel row)

```python
profile_row = supabase.table("profiles").select("fcm_token").eq(
    "id", reel_data["user_id"]
).single().execute()
fcm_token: str | None = profile_row.data.get("fcm_token")
```

### Step 19 — `ready` (auto-assigned)

```python
send_push_notification(
    fcm_token=fcm_token,
    title="Reel saved!",
    body=f"Categorised as {classification.category}",
    data={"reel_id": reel_id, "status": "ready"},
)
```

### Step 19 — `pending_category`

```python
import json as _json
send_push_notification(
    fcm_token=fcm_token,
    title="Help us categorise this reel",
    body="Your reel is saved — which fits best? Ignoring this saves it to Uncategorised.",
    data={
        "reel_id": reel_id,
        "suggestions": _json.dumps(suggestions),  # ["Fitness", "Nutrition"]
    },
    category_id="CATEGORISE",
)
```

### Step 17 — `uncategorised` (no signal)

```python
send_push_notification(
    fcm_token=fcm_token,
    title="Reel saved",
    body="We couldn't categorise it — no audio or caption found",
    data={"reel_id": reel_id, "status": "uncategorised"},
)
```

---

## Backend: Filling `# TODO Step 22` in `beat_tasks.py`

Per expired reel, after updating status to `uncategorised`:

```python
profile_row = supabase.table("profiles").select("fcm_token").eq(
    "id", row["user_id"]
).single().execute()
send_push_notification(
    fcm_token=profile_row.data.get("fcm_token"),
    title="Reel saved",
    body="Added to Uncategorised — you can move it anytime",
    data={"reel_id": row["id"], "status": "uncategorised"},
)
```

---

## Backend: Filling `# TODO Step 22` in `api/v1/reels.py` PATCH endpoint

**Path A (user picked a category):**
```python
send_push_notification(
    fcm_token=fcm_token,
    title="Reel categorised!",
    body=f"Moved to {category_name}",
    data={"reel_id": reel_id, "status": "ready"},
)
```

**Path B (user tapped "Uncategorised"):**
```python
send_push_notification(
    fcm_token=fcm_token,
    title="Reel saved",
    body="Added to Uncategorised — you can move it anytime",
    data={"reel_id": reel_id, "status": "uncategorised"},
)
```

---

## iOS: `ReelMindApp.swift` changes

### 1. Register `CATEGORISE` notification category on launch

Add inside `application(_:didFinishLaunchingWithOptions:)` after existing Firebase setup:

```swift
let actions: [UNNotificationAction] = [
    UNNotificationAction(
        identifier: "CAT_0",
        title: "Suggestion 1",   // generic — real name read from data payload at runtime
        options: []              // background — does not open app
    ),
    UNNotificationAction(
        identifier: "CAT_1",
        title: "Suggestion 2",
        options: []
    ),
    UNNotificationAction(
        identifier: "CHOOSE_IN_APP",
        title: "Choose / Create Category",
        options: [.foreground]   // opens app
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

Note: iOS binds action **titles** at registration time. The actual category names ("Fitness", "Nutrition") come from the FCM `data.suggestions` payload — the action handler reads them and uses the correct name when calling the backend.

### 2. Handle action button taps

Replace the existing empty `didReceive response` implementation:

```swift
func userNotificationCenter(
    _ center: UNUserNotificationCenter,
    didReceive response: UNNotificationResponse,
    withCompletionHandler completionHandler: @escaping () -> Void
) {
    let userInfo = response.notification.request.content.userInfo
    guard let reelId = userInfo["reel_id"] as? String else {
        completionHandler(); return
    }

    let suggestions = parseSuggestions(from: userInfo)  // parses data.suggestions JSON string

    switch response.actionIdentifier {
    case "CAT_0" where suggestions.count > 0:
        ReelCategoryAPI.shared.assign(reelId: reelId, categoryName: suggestions[0])
    case "CAT_1" where suggestions.count > 1:
        ReelCategoryAPI.shared.assign(reelId: reelId, categoryName: suggestions[1])
    case "UNCATEGORISED":
        ReelCategoryAPI.shared.assign(reelId: reelId, categoryName: nil)
    case "CHOOSE_IN_APP":
        // App is foregrounding — post to NotificationCenter so RootView can navigate
        NotificationCenter.default.post(
            name: .categoriseReel,
            object: nil,
            userInfo: ["reel_id": reelId, "suggestions": suggestions]
        )
    default:
        break
    }
    completionHandler()
}

private func parseSuggestions(from userInfo: [AnyHashable: Any]) -> [String] {
    guard
        let raw = userInfo["suggestions"] as? String,
        let data = raw.data(using: .utf8),
        let suggestions = try? JSONDecoder().decode([String].self, from: data)
    else { return [] }
    return suggestions
}
```

Add to a `Notification.Name` extension:
```swift
extension Notification.Name {
    static let categoriseReel = Notification.Name("categoriseReel")
}
```

### 3. FCM token upload — two triggers

**Trigger 1:** In `messaging(_:didReceiveRegistrationToken:)`:
```swift
func messaging(_ messaging: Messaging, didReceiveRegistrationToken fcmToken: String?) {
    guard let token = fcmToken else { return }
    UserDefaults.standard.set(token, forKey: "fcmToken")
    // Upload immediately if an auth token exists in UserDefaults (user is logged in).
    // AuthSession is an @EnvironmentObject and not accessible here directly — use
    // the auth token stored in UserDefaults by AuthSession as the logged-in signal.
    if UserDefaults.standard.string(forKey: "supabaseAuthToken") != nil {
        ProfileAPI.shared.uploadFCMToken(token)
    }
}
```

**Trigger 2:** In `AuthSession` when session is established (wherever `self.session = session` is set):
```swift
// After setting self.session = session and mirroring token to UserDefaults
if let fcmToken = UserDefaults.standard.string(forKey: "fcmToken") {
    ProfileAPI.shared.uploadFCMToken(fcmToken)
}
```

---

## iOS: `ReelCategoryAPI.swift`

Background `URLSession` calls from the notification action handler (runs while app is briefly woken in background):

```swift
final class ReelCategoryAPI {
    static let shared = ReelCategoryAPI()

    func assign(reelId: String, categoryName: String?) {
        guard let token = UserDefaults.standard.string(forKey: "supabaseAuthToken"),
              let url = URL(string: "\(K.backendBaseURL)/api/v1/reels/\(reelId)/category")
        else { return }

        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body: [String: Any?] = ["category_name": categoryName]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        URLSession.shared.dataTask(with: request).resume()
    }
}
```

---

## iOS: `ProfileAPI.swift`

```swift
final class ProfileAPI {
    static let shared = ProfileAPI()

    func uploadFCMToken(_ token: String) {
        guard let authToken = UserDefaults.standard.string(forKey: "supabaseAuthToken"),
              let url = URL(string: "\(K.backendBaseURL)/api/v1/profiles/fcm-token")
        else { return }

        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("Bearer \(authToken)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONEncoder().encode(["fcm_token": token])

        URLSession.shared.dataTask(with: request).resume()
    }
}
```

---

## iOS: `CategoriseReelView.swift`

Presented as a full-screen modal from `RootView` when it receives the `.categoriseReel` notification. `RootView` listens with `.onReceive(NotificationCenter.default.publisher(for: .categoriseReel))`.

On appear, the view fetches the reel row from Supabase using `reel_id` (to get `thumbnail_url`, `caption`). The `suggestions` array is passed in directly from the notification payload — no extra fetch needed for those.

**Layout:**
1. Reel thumbnail (loaded from `thumbnail_url` fetched on appear) + caption snippet
2. "Suggested for you" section — chips for each suggestion name
3. Divider + scrollable list of all user categories (fetched from Supabase on appear)
4. "Create new category" button → inline text field → POST to categories endpoint → then assign
5. Tapping any chip or category → `ReelCategoryAPI.shared.assign()` → dismiss modal

---

## Testing Strategy

### `tests/test_notifier.py` (mock `firebase_admin.messaging`)

| Test | What it verifies |
|------|-----------------|
| `test_send_success_returns_true` | `messaging.send()` called, returns `True` |
| `test_no_fcm_token_returns_false` | `fcm_token=None` → `False`, no send |
| `test_missing_credentials_returns_false` | `FIREBASE_SERVICE_ACCOUNT_JSON` unset → `False` |
| `test_send_exception_returns_false` | `messaging.send()` raises → `False`, no re-raise |
| `test_category_id_sets_apns_config` | `category_id="CATEGORISE"` → APNSConfig in message |
| `test_no_category_id_no_apns_config` | `category_id=None` → no APNSConfig |

---

## APNs Backlog — Required Before End-to-End Push Works

The following steps are blocked until a paid Apple Developer account is available:

- [ ] Generate an APNs Auth Key (.p8) in Apple Developer Console → Keys section
- [ ] Upload .p8 key to Firebase Console → Project Settings → Cloud Messaging → Apple app configuration
- [ ] Note the Key ID and Team ID — required during upload
- [ ] Download Firebase service account JSON from Firebase Console → Project Settings → Service Accounts → Generate new private key
- [ ] Base64-encode the JSON: `base64 -i service-account.json | pbcopy`
- [ ] Add `FIREBASE_SERVICE_ACCOUNT_JSON=<base64 string>` to `backend/.env` and Render dashboard
- [ ] Test end-to-end: save a reel, watch Celery logs, verify notification arrives on device
- [ ] Remove `firebase-admin` from the "optional" section of `requirements.txt` (if added there) and make it required

Until these are done, `send_push_notification()` returns `False` gracefully and logs a warning. All other pipeline behaviour (DB writes, status transitions) works normally.
