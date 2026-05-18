# Steps 23–24: Category Assignment Design

**Steps:** 23 (iOS notification inline reply) + 24 (backend auto-create category)  
**Status:** ~85% already built. This spec covers the remaining gaps.  
**Date:** 2026-05-18

---

## Context

When the Llama classifier has low confidence on a reel, the pipeline sets `status = "pending_category"` and fires an FCM push asking the user to assign a category. Two entry points exist for the user to respond:

- **Entry A:** Action buttons directly on the FCM notification (no app open)
- **Entry B:** `CategoriseReelView` full-screen sheet (opens when user taps "Choose…" or taps the notification body)

Both paths converge on `PATCH /api/v1/reels/{id}/category`. The backend is the single authority: it resolves the name, creates the category if needed, assigns it, marks the reel `ready`, and fires a confirmation push.

---

## What Already Exists

| Component | File | State |
|---|---|---|
| Full-screen sheet UI | `frontend/CategoriseReelView.swift` | Done — suggestions, all-categories list, new-category text field |
| Background assign call | `frontend/ReelCategoryAPI.swift` | Done — fires `PATCH /reels/{id}/category` |
| RootView notification listener | `frontend/RootView.swift` | Done — listens for `categoriseReel`, presents sheet |
| CATEGORISE FCM category registered | `frontend/ReelMindApp.swift` | Done — action handler registered |
| Backend PATCH endpoint | `backend/api/v1/reels.py` | Done — assign existing + null path. Missing: auto-create |

---

## Gaps This Spec Closes

1. **Backend:** `PATCH` returns 422 when category name not found — needs auto-create branch.
2. **iOS bug:** `CategoriseReelView.createCategoryAndAssign()` writes directly to Supabase `categories` (bypasses backend, missing `user_id`) — needs to be replaced with a `ReelCategoryAPI.assign()` call.
3. **Notification buttons:** Verify suggestion action buttons + "Choose…" button are correctly registered and wired to the right handlers.

---

## Architecture

```
Entry A: FCM notification buttons
  [Suggestion button]  ──→  ReelCategoryAPI.assign(name)  ──→  PATCH /reels/{id}/category
  [Choose… button]     ──→  opens CategoriseReelView (Entry B)

Entry B: CategoriseReelView sheet
  [Tap existing]       ──→  ReelCategoryAPI.assign(name)  ──→  PATCH /reels/{id}/category
  [Type new + Add]     ──→  ReelCategoryAPI.assign(name)  ──→  PATCH /reels/{id}/category
  [Skip]               ──→  ReelCategoryAPI.assign(nil)   ──→  PATCH /reels/{id}/category
```

---

## Backend: `PATCH /api/v1/reels/{id}/category`

### Decision tree

```
category_name is None
  → set status = "uncategorised"  [existing]

category_name found (case-insensitive ilike match for this user or default)
  → assign existing category_id  [existing]

category_name NOT found
  → trim + title-case name        [NEW]
  → create row: user_id, name, is_default = false  [NEW]
  → assign new category_id        [NEW]

In all non-null paths:
  → set status = "ready", confidence = existing value
  → send push: "Added to {category_name}"
```

### Status guard

Only acts when `reel.status == "pending_category"`. Returns `409 Conflict` otherwise. This prevents double-assignment if the user taps two buttons simultaneously.

### Name normalisation (server-side)

- Strip leading/trailing whitespace
- Title-case: `"travel vlogs"` → `"Travel Vlogs"`
- If result is empty after trim → return `422`

### Case-insensitive deduplication

Before creating, query:
```sql
select id from categories
where (user_id = $uid or is_default = true)
  and lower(name) = lower($name)
limit 1
```
If found, use existing row. No duplicate created.

### Response

```json
{ "reel_id": "...", "status": "ready", "category": "Travel Vlogs", "created": true }
```

`created: true` when a new category was auto-created, `false` when an existing one was used.

---

## iOS: Notification Action Buttons

### Registration

The FCM `pending_category` payload carries `suggestions` (up to 3 names) and `reel_id`. Dynamic action buttons are registered when the notification arrives **and the app is in the foreground** (`UNUserNotificationCenterDelegate.userNotificationCenter(_:willPresent:)`):

```
Actions:
  [Suggestion 0 label]   identifier: "PICK_0"
  [Suggestion 1 label]   identifier: "PICK_1"   (if suggestions.count >= 2)
  [Suggestion 2 label]   identifier: "PICK_2"   (if suggestions.count >= 3)
  [Choose…]              identifier: "CHOOSE"   foreground: true
Category ID: "CATEGORISE_<reel_id>"
```

Set `content.categoryIdentifier = "CATEGORISE_<reel_id>"` on the re-presented notification.

**Background / locked-screen constraint:** The `pending_category` push is a display push (it has `aps.alert`). When the app is backgrounded or the screen is locked, iOS delivers it directly to the system tray without waking the app — so dynamic category registration is not possible without a `UNNotificationServiceExtension`. **This is out of scope for this spec.** In the background case, the notification displays without action buttons; tapping the body opens the app → `CategoriseReelView` sheet via the existing `categoriseReel` NotificationCenter post. This is the primary path for most users (phone in pocket) and is fully functional.

### Action handler (existing, verify wiring)

```
PICK_0 / PICK_1 / PICK_2
  → read suggestions[index] from notification payload
  → ReelCategoryAPI.assign(reelId: reel_id, categoryName: suggestions[index])

CHOOSE
  → post NotificationCenter(.categoriseReel, userInfo: [reel_id, suggestions])
  → RootView presents CategoriseReelView
```

---

## iOS: `CategoriseReelView` Fix

### `createCategoryAndAssign()` — replace entirely

```swift
// REMOVE: direct Supabase write (missing user_id, bypasses backend)
// Task { try await supabase.from("categories").insert(...).execute() }

// REPLACE WITH:
private func createCategoryAndAssign() {
    let trimmed = newCategoryName.trimmingCharacters(in: .whitespaces)
    guard !trimmed.isEmpty else { return }
    assignAndDismiss(categoryName: trimmed)  // backend handles creation
}
```

`ReelCategoryAPI.assign()` already sends the name to `PATCH /reels/{id}/category`. With backend auto-create, no additional iOS code is needed.

---

## Error Handling

| Scenario | Behavior |
|---|---|
| Network failure — notification button path | Silent (fire-and-forget by design). Reel stays `pending_category`. User can re-open via sheet. |
| Network failure — sheet path | Show inline error banner in `CategoriseReelView`: "Couldn't save — tap to retry." Requires adding `@State private var assignError: String? = nil` and a `.alert` or red text below the Add button. |
| Reel already `ready` when PATCH arrives | Backend returns `409`. iOS ignores. |
| Empty / whitespace-only name | iOS disables the Add button. Backend returns `422` as safety net. |
| Duplicate name (case-insensitive) | Backend reuses existing category. No duplicate created. Response has `created: false`. |
| Suggestion index out of range | Action handler guards with `guard index < suggestions.count`. No-op if out of range. |

---

## Tests

### Backend — add to `backend/tests/test_category_endpoint.py`

- `test_patch_auto_creates_category_when_not_found` — sends a new name, asserts: new category row created with correct `user_id`, reel `status = "ready"`, response `created = true`
- `test_patch_case_insensitive_reuses_existing_category` — sends `"travel"` when `"Travel"` exists, asserts: no new row, response `created = false`
- `test_patch_title_cases_new_category_name` — sends `"travel vlogs"`, asserts stored name is `"Travel Vlogs"`
- `test_patch_returns_409_when_reel_already_ready`

### iOS — manual verification checklist

- [ ] Tap suggestion button on notification → app stays closed, reel appears in that category after push arrives
- [ ] Tap "Choose…" → `CategoriseReelView` sheet opens with correct reel + suggestions
- [ ] Type new category in sheet, tap Add → reel assigned, new category visible in list, no error
- [ ] Type existing category name (different case) in sheet → no duplicate created
- [ ] Tap Skip → reel moves to uncategorised
- [ ] Tap suggestion button while offline → silent failure, reel stays `pending_category`

---

## Files Changed

| File | Change |
|---|---|
| `backend/api/v1/reels.py` | Add auto-create branch + name normalisation to `update_reel_category` |
| `backend/tests/test_category_endpoint.py` | Add 4 new tests |
| `frontend/CategoriseReelView.swift` | Replace `createCategoryAndAssign()` body |
| `frontend/ReelMindApp.swift` | Add dynamic `UNNotificationCategory` registration in `willPresent`; verify `PICK_0/1/2` → `ReelCategoryAPI.assign` and `CHOOSE` → `categoriseReel` NotificationCenter post are wired in the action handler |
