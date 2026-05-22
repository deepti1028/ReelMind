# Manage Categories — Edit, Delete & Create Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the broken edit/delete buttons in ManageCategoriesView, hide default system categories, and add a working "create collection" flow with a call-to-action empty state.

**Architecture:** Two files only. `LibraryService.fetchCategories` gets a one-line server-side filter that strips `is_default = true` rows. `ManageCategoriesView` replaces two broken `.alert` modifiers with a single `ActiveAlert` enum-driven alert covering rename, delete, and create — plus a `+` toolbar button and an updated empty state with AppTheme-correct colors.

**Tech Stack:** SwiftUI (iOS 16+), Supabase Swift client, AppTheme color system

---

### Task 1: Filter default categories in LibraryService

**Files:**
- Modify: `frontend/Services/LibraryService.swift`

- [ ] **Step 1: Add `is_default` filter to `fetchCategories`**

Open `frontend/Services/LibraryService.swift`. Find `fetchCategories` (currently lines 22–30):

```swift
func fetchCategories() async throws -> [Category] {
    return try await client
        .from("categories")
        .select("id, name, created_at")
        .order("name", ascending: true)
        .execute()
        .value
}
```

Replace with:

```swift
func fetchCategories() async throws -> [Category] {
    return try await client
        .from("categories")
        .select("id, name, created_at")
        .eq("is_default", value: false)
        .order("name", ascending: true)
        .execute()
        .value
}
```

- [ ] **Step 2: Build the project**

In Xcode: **Product → Build** (⌘B).  
Expected: build succeeds, zero errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/Services/LibraryService.swift
git commit -m "fix: exclude default categories from fetchCategories"
```

---

### Task 2: Refactor ManageCategoriesView — enum, single alert, all three actions

**Files:**
- Modify: `frontend/Views/ManageCategoriesView.swift`

This task removes the two stale `@State` vars and the two broken `.alert` modifiers. It replaces them with a single `ActiveAlert` enum and one `.alert` binding that handles rename, delete, and create in one place. `addCategory()` is also added here because `alertActions` references it — the compiler requires it to exist before Task 3 adds the `+` button.

- [ ] **Step 1: Replace state variables**

At the top of `ManageCategoriesView`, find and remove these three vars:

```swift
@State private var editingCategory: Category?
@State private var editName = ""
@State private var categoryToDelete: Category?
```

Replace them with:

```swift
@State private var activeAlert: ActiveAlert?
@State private var editName = ""
@State private var newCategoryName = ""
```

`errorMessage` and `isLoading` stay unchanged.

- [ ] **Step 2: Add the `ActiveAlert` enum**

Immediately after the `@State` block (still inside `ManageCategoriesView`, before `var body`), add:

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

- [ ] **Step 3: Add computed helpers for alert title and content**

Add these four computed properties after the enum (still before `var body`):

```swift
private var alertTitle: String {
    switch activeAlert {
    case .rename:        return "Rename Collection"
    case .confirmDelete: return "Delete Collection?"
    case .create:        return "New Collection"
    case nil:            return ""
    }
}

private var renameTarget: Category? {
    guard case .rename(let cat) = activeAlert else { return nil }
    return cat
}

private var deleteTarget: Category? {
    guard case .confirmDelete(let cat) = activeAlert else { return nil }
    return cat
}

@ViewBuilder
private var alertActions: some View {
    if let cat = renameTarget {
        TextField("Collection name", text: $editName)
        Button("Cancel", role: .cancel) { activeAlert = nil }
        Button("Save") { Task { await rename(cat) } }
            .disabled(editName.trimmingCharacters(in: .whitespaces).isEmpty)
    } else if let cat = deleteTarget {
        Button("Cancel", role: .cancel) { activeAlert = nil }
        Button("Delete", role: .destructive) { Task { await delete(cat) } }
    } else {
        // .create case — also shown when no other case matches while alert is presented
        TextField("Collection name", text: $newCategoryName)
        Button("Cancel", role: .cancel) { activeAlert = nil }
        Button("Create") { Task { await addCategory() } }
            .disabled(newCategoryName.trimmingCharacters(in: .whitespaces).isEmpty)
    }
}
```

- [ ] **Step 4: Replace the two `.alert` modifiers with one**

In `var body`, find and delete both of these blocks entirely:

```swift
.alert("Rename Collection", isPresented: Binding(
    get: { editingCategory != nil },
    set: { if !$0 { editingCategory = nil } }
)) {
    TextField("Collection name", text: $editName)
    Button("Cancel", role: .cancel) { editingCategory = nil }
    Button("Save") {
        if let cat = editingCategory {
            Task { await rename(cat) }
        }
    }
    .disabled(editName.trimmingCharacters(in: .whitespaces).isEmpty)
}
.alert("Delete Collection?", isPresented: Binding(
    get: { categoryToDelete != nil },
    set: { if !$0 { categoryToDelete = nil } }
)) {
    Button("Cancel", role: .cancel) { categoryToDelete = nil }
    Button("Delete", role: .destructive) {
        if let cat = categoryToDelete {
            Task { await delete(cat) }
        }
    }
} message: {
    Text("Reels in this collection will be moved to your inbox.")
}
```

Replace with this single modifier (add after `.task { await load() }`):

```swift
.alert(alertTitle, isPresented: Binding(
    get: { activeAlert != nil },
    set: { if !$0 { activeAlert = nil } }
)) {
    alertActions
}
```

- [ ] **Step 5: Update `CategoryManageRow` callbacks**

Inside `categoryList`, find the `CategoryManageRow(...)` initializer call and change its `onEdit` and `onDelete` closures to:

```swift
CategoryManageRow(
    category: cat,
    reelCount: appVM.categorySummaries.first(where: { $0.id == cat.id })?.reelCount ?? 0,
    onEdit: {
        editName = cat.name
        activeAlert = .rename(cat)
    },
    onDelete: { activeAlert = .confirmDelete(cat) }
)
```

- [ ] **Step 6: Update `rename()` and `delete()` to clear `activeAlert`**

Find `rename(_ cat: Category)` and replace `editingCategory = nil` with `activeAlert = nil`:

```swift
private func rename(_ cat: Category) async {
    let trimmed = editName.trimmingCharacters(in: .whitespaces)
    guard !trimmed.isEmpty else { return }
    activeAlert = nil
    do {
        try await LibraryService.shared.renameCategory(id: cat.id, newName: trimmed)
        await appVM.load(silent: true)
        await load()
    } catch {
        errorMessage = "Failed to rename collection."
    }
}
```

Find `delete(_ cat: Category)` and replace `categoryToDelete = nil` with `activeAlert = nil`:

```swift
private func delete(_ cat: Category) async {
    activeAlert = nil
    do {
        try await LibraryService.shared.deleteCategory(id: cat.id)
        await appVM.load(silent: true)
        await load()
    } catch {
        errorMessage = "Failed to delete collection."
    }
}
```

- [ ] **Step 7: Add `addCategory()` function**

After `delete()`, add:

```swift
private func addCategory() async {
    let trimmed = newCategoryName.trimmingCharacters(in: .whitespaces)
    guard !trimmed.isEmpty else { return }
    activeAlert = nil
    do {
        _ = try await LibraryService.shared.createCategory(name: trimmed)
        await appVM.load(silent: true)
        await load()
    } catch {
        errorMessage = "Failed to create collection."
    }
}
```

- [ ] **Step 8: Build the project**

In Xcode: ⌘B.  
Expected: build succeeds with zero errors. No references to `editingCategory` or `categoryToDelete` should remain.

If the build fails with "use of unresolved identifier 'editingCategory'", grep for any remaining reference:

```bash
grep -n "editingCategory\|categoryToDelete" frontend/Views/ManageCategoriesView.swift
```

Fix any remaining occurrences.

- [ ] **Step 9: Smoke-test edit and delete on simulator**

Run on simulator (⌘R). Go to **Settings → Manage Categories**.

If no user-created categories exist yet, the screen will show an empty state (generic for now — updated in Task 4). You can create one via the app or Supabase dashboard for testing.

With at least one user-created category visible:
- Tap pencil → "Rename Collection" alert must appear with the current name pre-filled → rename → list refreshes with new name ✓
- Tap trash → "Delete Collection?" confirmation must appear → confirm → row disappears ✓
- Default system categories (Fitness, Food & Drink, etc.) must **not** appear in the list ✓

- [ ] **Step 10: Commit**

```bash
git add frontend/Views/ManageCategoriesView.swift
git commit -m "fix: replace dual alerts with single enum-driven alert; fix edit/delete actions"
```

---

### Task 3: Add the + (Create Collection) toolbar button

**Files:**
- Modify: `frontend/Views/ManageCategoriesView.swift`

- [ ] **Step 1: Replace the toolbar item with a + button**

In `var body`, find the existing `.toolbar` modifier:

```swift
.toolbar {
    ToolbarItem(placement: .navigationBarTrailing) {
        if isLoading { ProgressView().scaleEffect(0.8).tint(AppTheme.accent) }
    }
}
```

Replace it with:

```swift
.toolbar {
    ToolbarItem(placement: .navigationBarTrailing) {
        if isLoading {
            ProgressView().scaleEffect(0.8).tint(AppTheme.accent)
        } else {
            Button {
                newCategoryName = ""
                activeAlert = .create
            } label: {
                Image(systemName: "plus")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(AppTheme.accentDark)
            }
        }
    }
}
```

- [ ] **Step 2: Build the project**

In Xcode: ⌘B.  
Expected: build succeeds, zero errors.

- [ ] **Step 3: Smoke-test create on simulator**

Run on simulator (⌘R). Go to **Settings → Manage Categories**.

- Tap `+` in the top-right corner → "New Collection" alert appears with an empty text field ✓
- Type a name → "Create" button becomes enabled ✓
- Tap "Create" → new category appears in the list ✓
- Tap `+` without typing → "Create" button is disabled/greyed out ✓

- [ ] **Step 4: Commit**

```bash
git add frontend/Views/ManageCategoriesView.swift
git commit -m "feat: add + toolbar button to create new collection"
```

---

### Task 4: Replace empty state with call-to-action design

**Files:**
- Modify: `frontend/Views/ManageCategoriesView.swift`

- [ ] **Step 1: Replace the `emptyState` computed var**

Find the existing `emptyState` var:

```swift
private var emptyState: some View {
    VStack(spacing: 12) {
        Image(systemName: "folder")
            .font(.system(size: 40))
            .foregroundColor(AppTheme.accent.opacity(0.6))
        Text("No collections yet")
            .font(.system(size: 17, weight: .semibold))
            .foregroundColor(AppTheme.textPrimary)
        Text("Save and categorise a reel to create your first collection.")
            .font(.system(size: 13))
            .foregroundColor(AppTheme.textMuted)
            .multilineTextAlignment(.center)
            .padding(.horizontal, 40)
    }
}
```

Replace it with:

```swift
private var emptyState: some View {
    VStack(spacing: 16) {
        Image(systemName: "folder.badge.plus")
            .font(.system(size: 44))
            .foregroundColor(AppTheme.accent)

        VStack(spacing: 6) {
            Text("No collections yet")
                .font(.system(size: 17, weight: .semibold))
                .foregroundColor(AppTheme.textPrimary)
            Text("Tap + to create your first collection.")
                .font(.system(size: 13))
                .foregroundColor(AppTheme.textMuted)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 260)
        }

        Button {
            newCategoryName = ""
            activeAlert = .create
        } label: {
            Text("Create collection")
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(AppTheme.textPrimary)
                .padding(.horizontal, 24)
                .padding(.vertical, 10)
                .background(AppTheme.accent)
                .clipShape(Capsule())
        }
        .buttonStyle(.plain)
    }
    .padding(.horizontal, 40)
}
```

- [ ] **Step 2: Build the project**

In Xcode: ⌘B.  
Expected: build succeeds, zero errors.

- [ ] **Step 3: Verify empty state and text colors**

Run on simulator (⌘R). Go to **Settings → Manage Categories** with zero user-created categories.

Visual checks:
- `folder.badge.plus` icon in warm tan (`AppTheme.accent` #d4a373) ✓
- "No collections yet" in dark brown (`AppTheme.textPrimary` #2c1f0e) — **not white** ✓
- "Tap + to create..." in muted brown (`AppTheme.textMuted` #9a7654) ✓
- "Create collection" capsule: warm tan background, dark brown text — **not white** ✓

Text color audit — confirm no raw `.white` or `.primary` anywhere in the file:

```bash
grep -n "\.white\|Color\.primary\|foregroundColor(.primary)" frontend/Views/ManageCategoriesView.swift
```

Expected: no output (zero matches).

Tap "Create collection" from the empty state → same "New Collection" alert as the `+` toolbar button ✓. After creating, the list appears and the empty state disappears ✓.

- [ ] **Step 4: Commit**

```bash
git add frontend/Views/ManageCategoriesView.swift
git commit -m "feat: add CTA empty state with AppTheme colors to ManageCategoriesView"
```

---

### Final verification checklist

After all four tasks are complete, run through every success criterion from the spec:

- [ ] Pencil button → "Rename Collection" alert with pre-filled name → save updates the list
- [ ] Trash button → "Delete Collection?" → confirm removes the row
- [ ] Default system categories (Fitness, Food & Drink, etc.) are absent from the list
- [ ] `+` toolbar button → "New Collection" alert → create adds a row
- [ ] "Create collection" empty-state button triggers same alert
- [ ] Empty state shows when user has no user-created categories
- [ ] No text is white or `.primary` — all colors from `AppTheme`
- [ ] Error messages appear for any failed Supabase call (test by enabling airplane mode mid-action)
