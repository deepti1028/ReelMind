# Settings Page Features — Design Spec
**Date:** 2026-05-25

---

## Overview

Three improvements to the Settings page and Inbox view:

1. **User card** — show name + email, remove the Edit button, add a delete account icon
2. **Auto-categorise toggle** — make it functional end-to-end (iOS → Share Extension → backend)
3. **Delete account** — a full account deletion flow backed by a new backend endpoint

---

## 1. User Card

### Current state
- Shows name (from `userMetadata["full_name"]`) with email as fallback, then email below it
- Has a non-functional "Edit" button on the right

### Changes
- Remove the "Edit" button entirely
- Ensure name AND email are always shown as two separate lines (name bold, email faint) — the existing code already does this, just clean up the fallback so name never shows the email as a substitute
- Add a small trash icon button (`trash` SF Symbol) on the right, in `AppTheme.destructive` colour, no background capsule
- Tapping it triggers a standard iOS `.confirmationDialog` or `.alert` with a destructive "Delete account" action and a "Cancel" action

---

## 2. Auto-Categorise Toggle

### Goal
When the toggle is off, newly saved reels land in the Inbox with no category assigned. The backend skips classification entirely for those reels.

### iOS — Settings

`@AppStorage("autoCategorise")` already exists in `SettingsView`. No UI change needed to the toggle itself.

Add an `onChange` handler: when the value changes, write it to the App Group UserDefaults so the Share Extension can read it. When the user turns auto-categorise back ON, also reset the inbox banner dismissed state so the banner won't re-appear.

```swift
.onChange(of: autoCategorise) { _, newValue in
    UserDefaults(suiteName: AppConfig.appGroupID)?
        .set(newValue, forKey: "autoCategorise")
    if newValue {
        // banner is no longer relevant — reset so it shows again if toggled off later
        UserDefaults.standard.set(false, forKey: "inboxBannerDismissed")
    }
}
```

Also write the initial value on `SettingsView.task` (in case the extension reads before the user ever opens Settings).

### iOS — Share Extension (`ShareViewController`)

Read the preference from App Group UserDefaults before building the POST body:

```swift
let autoCategorise = UserDefaults(suiteName: K.appGroupID)?
    .bool(forKey: "autoCategorise") ?? true
```

Add `auto_categorise: autoCategorise` to the JSON POST body sent to `POST /api/v1/reels`.

### Backend — `POST /api/v1/reels` (`api/v1/reels.py`)

Accept a new optional field `auto_categorise: bool = True` in the request body.

Pass it through to the Celery task: `process_reel.delay(reel_id, auto_categorise=auto_categorise)`.

### Backend — Celery task (`workers/tasks.py`)

`process_reel` receives `auto_categorise: bool = True`.

When `auto_categorise=False`, skip steps 17–19 (build classification signal, classify, confidence routing). Set `status = "ready"` with no `categoryId`. Continue to step 20 (embeddings) and step 22 (push notification) as normal.

### iOS — InboxView

Add a dismissible info banner that shows when `autoCategorise == false` AND the user has not yet dismissed it.

**Dismissed state:** `@AppStorage("inboxBannerDismissed") private var bannerDismissed = false`. Reset to `false` when auto-categorise is turned back on (via `onChange` in SettingsView).

**Visual:** Sage green card (`#dde8c4 → #ccd5ae` gradient, border `#b8cc9a`), `✦` icon, dismiss `✕` button top-right.

**Message:** "Want your saved Reels sorted automatically? Turn on **Auto-categorise** in Settings."

"Auto-categorise" is a `Button` styled as inline text that sets `appVM.showSettings = true` to open the settings sheet.

**Placement:** Between the page header and the reel list (inside `reelList`, above the `LazyVStack`). Also show in the empty state view when `autoCategorise == false` and `inboxReels.isEmpty`.

---

## 3. Delete Account

### iOS — `AuthSession`

Add a new method:

```swift
func deleteAccount() async throws {
    guard let token = session?.accessToken else { return }
    var req = URLRequest(url: AppConfig.backendBaseURL.appending(path: "/api/v1/account"))
    req.httpMethod = "DELETE"
    req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    let (_, response) = try await URLSession.shared.data(for: req)
    guard (response as? HTTPURLResponse)?.statusCode == 204 else {
        throw URLError(.badServerResponse)
    }
    // Auth state listener fires automatically — no explicit signOut needed
}
```

### iOS — `SettingsView`

Replace the Edit button in `userCard` with a trash icon button:

```swift
Button { showDeleteConfirmation = true } label: {
    Image(systemName: "trash")
        .font(.system(size: 14))
        .foregroundColor(AppTheme.destructive)
}
```

Add `@State private var showDeleteConfirmation = false` and `@State private var isDeletingAccount = false`.

Attach a `.confirmationDialog` (or `.alert`) to the view:

```
Title: "Delete your account?"
Message: "All your reels, categories and data will be permanently removed. This cannot be undone."
Actions: "Delete account" (destructive), "Cancel"
```

On confirm:

```swift
isDeletingAccount = true
do {
    try await auth.deleteAccount()
} catch {
    // show error alert
}
isDeletingAccount = false
```

Show a `ProgressView` overlay while `isDeletingAccount` is true.

On success the `authStateChanges` listener in `AuthSession` fires, `session` becomes `nil`, and `RootView` navigates back to login automatically.

### Backend — new endpoint (`api/v1/account.py`)

```
DELETE /api/v1/account
Auth: Bearer JWT (verified via existing api/deps.py get_current_user)
Response: 204 No Content
```

Implementation:

```python
@router.delete("/account", status_code=204)
async def delete_account(user=Depends(get_current_user)):
    supabase_admin.auth.admin.delete_user(str(user.id))
```

`supabase_admin` is a `SupabaseClient` initialised with `SUPABASE_SERVICE_ROLE_KEY` (already used elsewhere in the backend). Deleting the auth user cascades to `profiles → reels → reel_chunks`, `categories` (user-created), `chat_sessions`, `chat_messages`, and `feedback` via existing FK `ON DELETE CASCADE` constraints.

Thumbnail files in Supabase Storage are left as orphaned files — acceptable since they are already per-reel-id (user-unique) and the storage cost is negligible.

Register the router in `main.py` alongside the existing reels router.

### Data integrity note

Two users saving the same Instagram reel URL each get their own `reels` row (URL is unique per user, not globally). `reel_chunks` references `reels.id`, so embeddings are also per-user. Deleting one user's auth record never touches another user's data.

---

## Out of scope

- Editing user profile (name, email, password) — Edit button is removed without replacement
- Recovering a deleted account
- Retroactively moving already-categorised reels to inbox when auto-categorise is turned off (only new reels are affected)
