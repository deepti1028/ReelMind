# Manage Categories — Edit & Delete Fix

**Date:** 2026-05-23  
**Status:** Approved

---

## Problem

Two bugs prevent the edit and delete buttons in `ManageCategoriesView` from working:

1. **Edit alert never shows.** The view has two `.alert` modifiers on the same `ZStack`. SwiftUI only reliably processes one alert per view — the delete alert wins and suppresses the rename alert entirely.

2. **Delete silently does nothing.** `LibraryService.fetchCategories` returns both user-created categories and default system categories (`is_default = true`, `user_id = NULL`). When a user taps delete on a default category, the Supabase RLS policy (`user_id = auth.uid()`) blocks the operation silently — no error is thrown, the list reloads, and the category is still there.

---

## Design

### Approach: Single alert enum + server-side default-category filter

#### 1. Filter defaults in `LibraryService` (server-side)

In `fetchCategories`, add `.eq("is_default", value: false)` to the Supabase query. Default system categories never reach the view. No model changes needed.

**File:** `frontend/Services/LibraryService.swift`  
**Change:** One line — add `.eq("is_default", value: false)` before `.order(...)`.

#### 2. Replace dual `.alert` modifiers with a single enum-driven alert

Introduce a private enum in `ManageCategoriesView`:

```swift
private enum ActiveAlert: Identifiable {
    case rename(Category)
    case confirmDelete(Category)
    var id: String {
        switch self {
        case .rename(let c):        return "rename-\(c.id)"
        case .confirmDelete(let c): return "delete-\(c.id)"
        }
    }
}
```

Replace the two `@State` vars (`editingCategory`, `categoryToDelete`) and both `.alert` modifiers with:

```swift
@State private var activeAlert: ActiveAlert?
```

Single `.alert(item: $activeAlert)` that switches on the enum case to render either the rename text-field alert or the delete confirmation alert.

The `onEdit` and `onDelete` callbacks in `CategoryManageRow` set `activeAlert = .rename(cat)` and `activeAlert = .confirmDelete(cat)` respectively.

**File:** `frontend/Views/ManageCategoriesView.swift`  
**Change:** Remove `editingCategory`, `categoryToDelete`. Add `activeAlert`. Replace two `.alert` modifiers with one.

---

## Scope

- Two files touched: `LibraryService.swift`, `ManageCategoriesView.swift`
- No backend changes, no migration, no new files
- `rename()` and `delete()` async functions are already correct — no changes needed there
- No change to `AppViewModel`, `Category` model, or any other view

---

## Success criteria

1. Tapping the pencil button shows the "Rename Collection" alert with a pre-filled text field.
2. Saving a new name updates the category in Supabase and the list refreshes with the new name.
3. Tapping the trash button shows the "Delete Collection?" confirmation.
4. Confirming deletion removes the category from Supabase and it disappears from the list.
5. Default system categories (Fitness, Food & Drink, etc.) do not appear in the Manage Categories list.
6. Error messages surface correctly if a Supabase call fails.
