# Manage Categories — Edit, Delete & Create

**Date:** 2026-05-23  
**Status:** Approved

---

## Problem

Three issues with `ManageCategoriesView`:

1. **Edit alert never shows.** Two `.alert` modifiers on the same `ZStack` — SwiftUI only reliably processes one per view. The delete alert wins and the rename alert is suppressed entirely.

2. **Delete silently does nothing.** `LibraryService.fetchCategories` returns both user-created and default system categories (`is_default = true`, `user_id = NULL`). Deleting a default fails silently via RLS (`user_id = auth.uid()`), the list reloads, and the row is still there.

3. **No way to create a category from this screen.** No "Add" button exists. The screen is read-only with broken actions.

---

## Design

### Approach: Single alert enum + server-side filter + add button + rich empty state

#### 1. Filter defaults in `LibraryService` (server-side)

Add `.eq("is_default", value: false)` to `fetchCategories`. Default system categories never reach the view. No model changes needed.

**File:** `frontend/Services/LibraryService.swift`  
**Change:** One line before `.order(...)`.

#### 2. Single enum-driven alert (fixes both edit and delete)

Expand the alert enum to cover three cases — rename, delete confirmation, and create:

```swift
private enum ActiveAlert: Identifiable {
    case rename(Category)
    case confirmDelete(Category)
    case create
    var id: String {
        switch self {
        case .rename(let c):        return "rename-\(c.id)"
        case .confirmDelete(let c): return "delete-\(c.id)"
        case .create:               return "create"
        }
    }
}
```

Replace `editingCategory`, `categoryToDelete`, and both `.alert` modifiers with:

```swift
@State private var activeAlert: ActiveAlert?
@State private var newCategoryName = ""   // used by .create case
```

A single `.alert(item: $activeAlert)` switches on the case:
- `.rename(cat)` → "Rename Collection" alert with pre-filled `$editName` TextField + Save/Cancel
- `.confirmDelete(cat)` → "Delete Collection?" confirmation with Delete (destructive)/Cancel
- `.create` → "New Collection" alert with empty `$newCategoryName` TextField + Create/Cancel

`CategoryManageRow` callbacks set `activeAlert = .rename(cat)` and `activeAlert = .confirmDelete(cat)`.  
The new `+` toolbar button sets `activeAlert = .create` (after clearing `newCategoryName = ""`).

**File:** `frontend/Views/ManageCategoriesView.swift`

#### 3. Add Category button (navigation bar)

A `+` button in the `.navigationBarTrailing` toolbar position. Tapping it clears `newCategoryName` and sets `activeAlert = .create`. On save, calls `LibraryService.shared.createCategory(name:)` (already implemented), then `appVM.load(silent: true)` + `load()` to refresh.

**Styling:** Matches the existing toolbar pattern — `ProgressView` already occupies `.navigationBarTrailing` during loading, so the `+` button appears only when not loading.

#### 4. Empty state — user has no collections

When `categories.isEmpty` after load, show a dedicated empty state instead of the current generic one. The new empty state is a call-to-action:

**Layout (centered, vertical stack):**
- SF Symbol `folder.badge.plus` at 44pt, colored `AppTheme.accent` (#d4a373)
- Title: `"No collections yet"` — `AppTheme.textPrimary` (#2c1f0e), 17pt semibold
- Subtitle: `"Tap + to create your first collection."` — `AppTheme.textMuted` (#9a7654), 13pt, centered, max width 260pt
- Primary button: `"Create collection"` capsule — background `AppTheme.accent`, label `AppTheme.textPrimary` (dark brown on warm tan = high contrast, not white), 14pt semibold. Tapping it triggers the same `.create` alert as the toolbar button.

**File:** `frontend/Views/ManageCategoriesView.swift` — replace `emptyState` computed var.

#### 5. Text color audit

All text in `ManageCategoriesView` and `CategoryManageRow` must use AppTheme colors:

| Element | Color token | Hex |
|---|---|---|
| Category name | `AppTheme.textPrimary` | `#2c1f0e` (dark brown) |
| Reel count sub-label | `AppTheme.textFaint` | `#b8956a` (muted warm) |
| Error message | `AppTheme.destructive` | `#cc4444` (red) |
| Empty state title | `AppTheme.textPrimary` | `#2c1f0e` |
| Empty state subtitle | `AppTheme.textMuted` | `#9a7654` |
| Create button label | `AppTheme.textPrimary` | `#2c1f0e` (on accent bg) |

No raw `.white` or `.primary` anywhere in the view.

---

## Scope

- **Two files changed:** `LibraryService.swift`, `ManageCategoriesView.swift`
- No backend changes, no migration, no new files
- `rename()` and `delete()` async functions are already correct — no changes there
- `createCategory(name:)` in `LibraryService` is already implemented — no changes there
- No change to `AppViewModel`, `Category` model, or any other view

---

## Success criteria

1. Tapping the pencil button shows the "Rename Collection" alert with a pre-filled text field.
2. Saving a new name updates the category in Supabase and the list refreshes.
3. Tapping the trash button shows "Delete Collection?" — confirming removes it from the list.
4. Default system categories (Fitness, Food & Drink, etc.) do not appear in the list.
5. Tapping `+` (toolbar) or "Create collection" (empty state) shows the "New Collection" alert.
6. Creating a category saves it to Supabase and it appears in the list immediately.
7. When the user has no user-created categories, the call-to-action empty state is shown.
8. No text uses raw `.white` or `.primary`; all colors come from `AppTheme`.
9. Error messages surface if any Supabase call fails.
