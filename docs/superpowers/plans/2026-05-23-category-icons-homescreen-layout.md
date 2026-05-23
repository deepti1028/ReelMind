# Category Icons + Home Screen Collage Layout — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an icon picker to category create/rename flows and replace the flat 2-column grid on the home screen with a collage layout matching `home_screen_concepts.html`.

**Architecture:** A new `icon TEXT` column on the `categories` table propagates through `LibraryService` → `Category` model → `CategorySummary` → UI. The home screen's `LazyVGrid` is replaced by a `CollageLayout` view that applies a deterministic layout algorithm (hero + alternating wide/narrow pairs) and renders cards with a tonal background, SF Symbol icon, and watermark count.

**Tech Stack:** Swift/SwiftUI, Supabase (PostgreSQL + Swift SDK), SF Symbols.

**Spec:** `docs/superpowers/specs/2026-05-23-category-icons-homescreen-layout-design.md`

---

## File Map

| Status | Path | Responsibility |
|--------|------|----------------|
| **Create** | `supabase/migrations/20260523000001_add_icon_to_categories.sql` | Add `icon` column |
| **Modify** | `frontend/Models/Category.swift` | Add `icon: String?` to both model types |
| **Modify** | `frontend/Services/LibraryService.swift` | Include `icon` in fetch/create/rename |
| **Modify** | `frontend/ViewModels/AppViewModel.swift` | Pass `icon` when building `CategorySummary` |
| **Modify** | `frontend/Theme/AppTheme.swift` | Add card background + icon color arrays |
| **Create** | `frontend/Views/CategoryIconPicker.swift` | Reusable 5-col icon grid, 26 SF Symbols |
| **Modify** | `frontend/Views/ManageCategoriesView.swift` | Replace system alerts with sheet + icon picker |
| **Modify** | `frontend/CategoriseReelView.swift` | Add icon button to create-new-category row |
| **Modify** | `frontend/Views/LibraryView.swift` | Replace `LazyVGrid`+`CategoryCard` with `CollageLayout` |

---

## Task 1: DB Migration — add `icon` column

**Files:**
- Create: `supabase/migrations/20260523000001_add_icon_to_categories.sql`

- [ ] **Step 1: Create the migration file**

```sql
-- supabase/migrations/20260523000001_add_icon_to_categories.sql
ALTER TABLE public.categories ADD COLUMN icon TEXT;
```

- [ ] **Step 2: Apply the migration**

```bash
cd /path/to/ReelMind
supabase db push
```

Expected output: migration applied with no errors.

- [ ] **Step 3: Verify the column exists**

```bash
supabase db diff
```

Expected: no diff (migration was applied cleanly).

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/20260523000001_add_icon_to_categories.sql
git commit -m "feat: add icon column to categories table"
```

---

## Task 2: Update Swift Models

**Files:**
- Modify: `frontend/Models/Category.swift`

- [ ] **Step 1: Replace the entire file content**

```swift
import Foundation

struct Category: Identifiable, Decodable, Hashable {
    let id: UUID
    let name: String
    let icon: String?
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, name, icon
        case createdAt = "created_at"
    }
}

struct CategorySummary: Identifiable, Hashable {
    let id: UUID
    let name: String
    let icon: String?
    let reelCount: Int
    let lastSavedAt: Date?
}
```

- [ ] **Step 2: Build the project in Xcode (⌘B)**

Expected: build succeeds. The compiler will flag every call site that constructs a `CategorySummary` without `icon` — there is exactly one, in `AppViewModel`. Fix it in Task 4.

- [ ] **Step 3: Commit**

```bash
git add frontend/Models/Category.swift
git commit -m "feat: add icon field to Category and CategorySummary models"
```

---

## Task 3: Update LibraryService

**Files:**
- Modify: `frontend/Services/LibraryService.swift`

- [ ] **Step 1: Update `fetchCategories` to select the icon column**

Replace:
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

With:
```swift
func fetchCategories() async throws -> [Category] {
    return try await client
        .from("categories")
        .select("id, name, icon, created_at")
        .eq("is_default", value: false)
        .order("name", ascending: true)
        .execute()
        .value
}
```

- [ ] **Step 2: Update `createCategory` to accept and persist `icon`**

Replace:
```swift
func createCategory(name: String) async throws -> Category {
    let userId = try await client.auth.session.user.id
    struct Payload: Encodable {
        let name: String
        let userId: UUID
        let isDefault: Bool
        enum CodingKeys: String, CodingKey {
            case name
            case userId = "user_id"
            case isDefault = "is_default"
        }
    }
    return try await client
        .from("categories")
        .insert(Payload(name: name, userId: userId, isDefault: false))
        .select()
        .single()
        .execute()
        .value
}
```

With:
```swift
func createCategory(name: String, icon: String) async throws -> Category {
    let userId = try await client.auth.session.user.id
    struct Payload: Encodable {
        let name: String
        let icon: String
        let userId: UUID
        let isDefault: Bool
        enum CodingKeys: String, CodingKey {
            case name, icon
            case userId = "user_id"
            case isDefault = "is_default"
        }
    }
    return try await client
        .from("categories")
        .insert(Payload(name: name, icon: icon, userId: userId, isDefault: false))
        .select()
        .single()
        .execute()
        .value
}
```

- [ ] **Step 3: Update `renameCategory` to accept and persist `icon`**

Replace:
```swift
func renameCategory(id: UUID, newName: String) async throws {
    struct Payload: Encodable { let name: String }
    try await client
        .from("categories")
        .update(Payload(name: newName))
        .eq("id", value: id)
        .execute()
}
```

With:
```swift
func renameCategory(id: UUID, newName: String, icon: String) async throws {
    struct Payload: Encodable {
        let name: String
        let icon: String
    }
    try await client
        .from("categories")
        .update(Payload(name: newName, icon: icon))
        .eq("id", value: id)
        .execute()
}
```

- [ ] **Step 4: Build (⌘B)**

Expected: build succeeds. Call sites for `createCategory` and `renameCategory` in `ManageCategoriesView` will now have compiler errors about missing `icon` argument — fix those in Task 7.

- [ ] **Step 5: Commit**

```bash
git add frontend/Services/LibraryService.swift
git commit -m "feat: add icon param to LibraryService create/rename/fetch"
```

---

## Task 4: Update AppViewModel

**Files:**
- Modify: `frontend/ViewModels/AppViewModel.swift`

- [ ] **Step 1: Pass `icon` when constructing `CategorySummary`**

In `AppViewModel.load()`, replace:
```swift
categorySummaries = categories
    .map { cat -> CategorySummary in
        let catReels = grouped[cat.id] ?? []
        return CategorySummary(
            id: cat.id,
            name: cat.name,
            reelCount: catReels.count,
            lastSavedAt: catReels.first?.createdAt
        )
    }
    .sorted { ($0.lastSavedAt ?? .distantPast) > ($1.lastSavedAt ?? .distantPast) }
```

With:
```swift
categorySummaries = categories
    .map { cat -> CategorySummary in
        let catReels = grouped[cat.id] ?? []
        return CategorySummary(
            id: cat.id,
            name: cat.name,
            icon: cat.icon,
            reelCount: catReels.count,
            lastSavedAt: catReels.first?.createdAt
        )
    }
    .sorted { ($0.lastSavedAt ?? .distantPast) > ($1.lastSavedAt ?? .distantPast) }
```

- [ ] **Step 2: Build (⌘B)**

Expected: build succeeds with no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/ViewModels/AppViewModel.swift
git commit -m "feat: propagate category icon through AppViewModel"
```

---

## Task 5: Add Card Color Arrays to AppTheme

**Files:**
- Modify: `frontend/Theme/AppTheme.swift`

- [ ] **Step 1: Add the two color arrays at the end of the `AppTheme` enum body**

Insert before the closing `}` of `enum AppTheme`:
```swift
    // Card palette — 10 tonal backgrounds from home_screen_concepts.html
    static let cardBackgrounds: [Color] = [
        Color(r: 0xfa, g: 0xed, b: 0xcd), // warm surface
        Color(r: 0xe9, g: 0xed, b: 0xc9), // sage light
        Color(r: 0xcc, g: 0xd5, b: 0xae), // sage medium
        Color(r: 0xf3, g: 0xe8, b: 0xd0), // warm cream
        Color(r: 0xdd, g: 0xe6, b: 0xc8), // cool sage
        Color(r: 0xf8, g: 0xf3, b: 0xe4), // pale cream
        Color(r: 0xe4, g: 0xec, b: 0xcc), // pale sage
        Color(r: 0xf0, g: 0xe4, b: 0xcc), // warm peach
        Color(r: 0xd8, g: 0xe2, b: 0xb8), // strong sage
        Color(r: 0xf5, g: 0xee, b: 0xdd), // lightest cream
    ]

    // Tonal icon colors — darker shade paired with each card background
    static let cardIconColors: [Color] = [
        Color(r: 0x8a, g: 0x60, b: 0x38),
        Color(r: 0x5a, g: 0x6a, b: 0x34),
        Color(r: 0x48, g: 0x5a, b: 0x30),
        Color(r: 0x8a, g: 0x68, b: 0x40),
        Color(r: 0x52, g: 0x70, b: 0x44),
        Color(r: 0x7a, g: 0x68, b: 0x48),
        Color(r: 0x4e, g: 0x68, b: 0x38),
        Color(r: 0x8a, g: 0x60, b: 0x40),
        Color(r: 0x42, g: 0x60, b: 0x30),
        Color(r: 0x7a, g: 0x68, b: 0x50),
    ]
```

- [ ] **Step 2: Build (⌘B)**

Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/Theme/AppTheme.swift
git commit -m "feat: add card background and icon color palettes to AppTheme"
```

---

## Task 6: Create CategoryIconPicker Component

**Files:**
- Create: `frontend/Views/CategoryIconPicker.swift`

- [ ] **Step 1: Create the file**

```swift
import SwiftUI

struct CategoryIconPicker: View {
    @Binding var selectedIcon: String
    @Binding var isShowing: Bool

    static let icons: [String] = [
        "fork.knife", "dumbbell", "airplane", "bag", "sparkles",
        "drop", "house", "scissors", "face.smiling", "music.note",
        "headphones", "bolt", "briefcase", "banknote", "cpu",
        "paintpalette", "camera", "leaf", "heart", "figure.and.child.holdinghands",
        "pawprint", "book.open", "gamecontroller", "graduationcap", "trophy",
        "bookmark"
    ]

    private let columns = Array(repeating: GridItem(.flexible()), count: 5)

    var body: some View {
        LazyVGrid(columns: columns, spacing: 10) {
            ForEach(Self.icons, id: \.self) { symbol in
                Button {
                    selectedIcon = symbol
                    isShowing = false
                } label: {
                    Image(systemName: symbol)
                        .font(.system(size: 18))
                        .frame(width: 44, height: 44)
                        .foregroundColor(selectedIcon == symbol ? .white : AppTheme.accentDark)
                        .background(selectedIcon == symbol
                            ? AppTheme.accent
                            : AppTheme.surfaceSecondary)
                        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.vertical, 8)
    }
}
```

- [ ] **Step 2: Build (⌘B)**

Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/Views/CategoryIconPicker.swift
git commit -m "feat: add CategoryIconPicker component with 26 SF Symbols"
```

---

## Task 7: Rewrite ManageCategoriesView

**Files:**
- Modify: `frontend/Views/ManageCategoriesView.swift`

- [ ] **Step 1: Replace the entire file with the new sheet-based implementation**

```swift
import SwiftUI

struct ManageCategoriesView: View {
    @EnvironmentObject private var appVM: AppViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var categories: [Category] = []
    @State private var isLoading = false
    @State private var errorMessage: String?

    // Delete confirmation
    @State private var deleteTarget: Category?

    // Create / rename sheet
    @State private var showFormSheet = false
    @State private var formTarget: Category?   // nil = create, non-nil = rename
    @State private var formName = ""
    @State private var formIcon = "bookmark"
    @State private var showIconPicker = false

    var body: some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()

            if isLoading && categories.isEmpty {
                ProgressView().tint(AppTheme.accent)
            } else if categories.isEmpty {
                emptyState
            } else {
                categoryList
            }
        }
        .navigationTitle("Collections")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                if isLoading {
                    ProgressView().scaleEffect(0.8).tint(AppTheme.accent)
                } else {
                    Button {
                        formTarget = nil
                        formName = ""
                        formIcon = "bookmark"
                        showIconPicker = false
                        showFormSheet = true
                    } label: {
                        Image(systemName: "plus")
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundColor(AppTheme.accentDark)
                    }
                }
            }
        }
        .task { await load() }
        .alert("Delete Collection?", isPresented: Binding(
            get: { deleteTarget != nil },
            set: { if !$0 { deleteTarget = nil } }
        )) {
            Button("Cancel", role: .cancel) { deleteTarget = nil }
            Button("Delete", role: .destructive) {
                if let cat = deleteTarget { Task { await delete(cat) } }
            }
        }
        .sheet(isPresented: $showFormSheet) {
            CategoryFormSheet(
                target: formTarget,
                name: $formName,
                icon: $formIcon,
                showIconPicker: $showIconPicker,
                onSave: { Task { await saveForm() } }
            )
        }
    }

    // MARK: - Sub-views

    private var categoryList: some View {
        ScrollView {
            VStack(spacing: 0) {
                if let msg = errorMessage {
                    Text(msg)
                        .font(.system(size: 12))
                        .foregroundColor(AppTheme.destructive)
                        .padding(.horizontal, 20)
                        .padding(.top, 12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                LazyVStack(spacing: 0) {
                    ForEach(categories) { cat in
                        CategoryManageRow(
                            category: cat,
                            reelCount: appVM.categorySummaries.first(where: { $0.id == cat.id })?.reelCount ?? 0,
                            onEdit: {
                                formTarget = cat
                                formName = cat.name
                                formIcon = cat.icon ?? "bookmark"
                                showIconPicker = false
                                showFormSheet = true
                            },
                            onDelete: { deleteTarget = cat }
                        )

                        if cat.id != categories.last?.id {
                            Divider()
                                .background(AppTheme.border)
                                .padding(.leading, 54)
                        }
                    }
                }
                .background(AppTheme.surface)
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(AppTheme.border, lineWidth: 1)
                )
                .padding(.horizontal, 14)
                .padding(.top, 16)
            }
            .padding(.bottom, 32)
        }
    }

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
                formTarget = nil
                formName = ""
                formIcon = "bookmark"
                showIconPicker = false
                showFormSheet = true
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

    // MARK: - Actions

    private func load() async {
        isLoading = true
        do {
            categories = try await LibraryService.shared.fetchCategories()
        } catch {
            errorMessage = "Failed to load collections."
        }
        isLoading = false
    }

    private func saveForm() async {
        let trimmed = formName.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        showFormSheet = false
        if let cat = formTarget {
            await rename(cat, newName: trimmed, newIcon: formIcon)
        } else {
            await addCategory(name: trimmed, icon: formIcon)
        }
    }

    private func rename(_ cat: Category, newName: String, newIcon: String) async {
        do {
            try await LibraryService.shared.renameCategory(id: cat.id, newName: newName, icon: newIcon)
            await appVM.load(silent: true)
            await load()
        } catch {
            errorMessage = "Failed to rename collection."
        }
    }

    private func delete(_ cat: Category) async {
        deleteTarget = nil
        do {
            try await LibraryService.shared.deleteCategory(id: cat.id)
            await appVM.load(silent: true)
            await load()
        } catch {
            errorMessage = "Failed to delete collection."
        }
    }

    private func addCategory(name: String, icon: String) async {
        do {
            _ = try await LibraryService.shared.createCategory(name: name, icon: icon)
            await appVM.load(silent: true)
            await load()
        } catch {
            errorMessage = "Failed to create collection."
        }
    }
}

// MARK: - Form Sheet

private struct CategoryFormSheet: View {
    let target: Category?
    @Binding var name: String
    @Binding var icon: String
    @Binding var showIconPicker: Bool
    let onSave: () -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 10) {
                    Button {
                        showIconPicker.toggle()
                    } label: {
                        Image(systemName: icon)
                            .font(.system(size: 18))
                            .frame(width: 40, height: 40)
                            .foregroundColor(AppTheme.accentDark)
                            .background(AppTheme.surfaceSecondary)
                            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                    }
                    .buttonStyle(.plain)

                    TextField("Collection name", text: $name)
                        .font(.system(size: 15))
                        .padding(.horizontal, 12)
                        .padding(.vertical, 10)
                        .background(AppTheme.surfaceSecondary)
                        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                }

                if showIconPicker {
                    CategoryIconPicker(selectedIcon: $icon, isShowing: $showIconPicker)
                }

                Spacer()
            }
            .padding(20)
            .background(AppTheme.background.ignoresSafeArea())
            .navigationTitle(target == nil ? "New Collection" : "Rename Collection")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") { dismiss() }
                        .foregroundColor(AppTheme.accentDark)
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(target == nil ? "Create" : "Save") { onSave() }
                        .fontWeight(.semibold)
                        .foregroundColor(AppTheme.accentDark)
                        .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
        }
    }
}

// MARK: - Row

private struct CategoryManageRow: View {
    let category: Category
    let reelCount: Int
    let onEdit: () -> Void
    let onDelete: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(AppTheme.surfaceSecondary)
                .frame(width: 34, height: 34)
                .overlay(
                    Image(systemName: category.icon ?? "bookmark")
                        .font(.system(size: 14))
                        .foregroundColor(AppTheme.accentDark)
                )

            VStack(alignment: .leading, spacing: 2) {
                Text(category.name)
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(AppTheme.textPrimary)
                Text("\(reelCount) reel\(reelCount == 1 ? "" : "s")")
                    .font(.system(size: 11))
                    .foregroundColor(AppTheme.textFaint)
            }

            Spacer()

            Button { onEdit() } label: {
                Image(systemName: "pencil")
                    .font(.system(size: 13))
                    .foregroundColor(AppTheme.textMuted)
                    .frame(width: 32, height: 32)
                    .background(AppTheme.surfaceSecondary)
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            }
            .buttonStyle(.plain)

            Button { onDelete() } label: {
                Image(systemName: "trash")
                    .font(.system(size: 13))
                    .foregroundColor(AppTheme.destructive)
                    .frame(width: 32, height: 32)
                    .background(AppTheme.destructive.opacity(0.08))
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
    }
}
```

- [ ] **Step 2: Build (⌘B)**

Expected: build succeeds.

- [ ] **Step 3: Run in simulator — test create flow**

1. Go to Settings → Collections → tap `+`
2. Sheet appears with `bookmark` icon button + name field
3. Tap the icon button → 26-icon grid appears
4. Tap an icon → grid collapses, button updates
5. Enter a name → tap Create → sheet dismisses, new category appears in list with correct icon

- [ ] **Step 4: Test rename flow**

1. Tap the pencil on an existing row → sheet appears pre-filled with name and icon
2. Change icon and/or name → tap Save → row updates

- [ ] **Step 5: Test delete flow**

1. Tap the trash icon → system alert with "Delete Collection?"
2. Tap Delete → row removed

- [ ] **Step 6: Commit**

```bash
git add frontend/Views/ManageCategoriesView.swift
git commit -m "feat: replace alert-based create/rename with sheet + icon picker in ManageCategoriesView"
```

---

## Task 8: Update CategoriseReelView

**Files:**
- Modify: `frontend/CategoriseReelView.swift`

- [ ] **Step 1: Update `CategoryRow` to include `icon`**

Replace:
```swift
struct CategoryRow: Identifiable, Decodable, Hashable {
    let id: String
    let name: String
}
```

With:
```swift
struct CategoryRow: Identifiable, Decodable, Hashable {
    let id: String
    let name: String
    let icon: String?
}
```

- [ ] **Step 2: Add icon state variables**

Add two `@State` properties after `@State private var isLoading: Bool = true`:
```swift
@State private var selectedCreateIcon: String = "bookmark"
@State private var showCreateIconPicker: Bool = false
```

- [ ] **Step 3: Update the categories query to select `icon`**

In `loadReelAndCategories()`, replace:
```swift
let cats: [CategoryRow] = try await SupabaseManager.shared.client
    .from("categories")
    .select("id, name")
    .order("name", ascending: true)
    .execute()
    .value
```

With:
```swift
let cats: [CategoryRow] = try await SupabaseManager.shared.client
    .from("categories")
    .select("id, name, icon")
    .order("name", ascending: true)
    .execute()
    .value
```

- [ ] **Step 4: Replace the "Create new category" section in `body`**

Replace:
```swift
VStack(alignment: .leading, spacing: 8) {
    Text("Create new category")
        .font(.headline)
    HStack {
        TextField("e.g. Travel", text: $newCategoryName)
            .textFieldStyle(.roundedBorder)
        Button("Add") {
            createCategoryAndAssign()
        }
        .disabled(newCategoryName.trimmingCharacters(in: .whitespaces).isEmpty)
    }
}
```

With:
```swift
VStack(alignment: .leading, spacing: 8) {
    Text("Create new category")
        .font(.headline)
    HStack {
        Button {
            showCreateIconPicker.toggle()
        } label: {
            Image(systemName: selectedCreateIcon)
                .font(.system(size: 16))
                .frame(width: 36, height: 36)
                .background(Color(.secondarySystemBackground))
                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                .foregroundColor(.primary)
        }
        .buttonStyle(.plain)

        TextField("e.g. Travel", text: $newCategoryName)
            .textFieldStyle(.roundedBorder)

        Button("Add") {
            createCategoryAndAssign()
        }
        .disabled(newCategoryName.trimmingCharacters(in: .whitespaces).isEmpty)
    }

    if showCreateIconPicker {
        CategoryIconPicker(selectedIcon: $selectedCreateIcon, isShowing: $showCreateIconPicker)
    }
}
```

- [ ] **Step 5: Replace `createCategoryAndAssign()` to use LibraryService directly**

Replace:
```swift
private func createCategoryAndAssign() {
    let trimmed = newCategoryName.trimmingCharacters(in: .whitespaces)
    guard !trimmed.isEmpty else { return }
    assignAndDismiss(categoryName: trimmed)
}
```

With:
```swift
private func createCategoryAndAssign() {
    let trimmed = newCategoryName.trimmingCharacters(in: .whitespaces)
    guard !trimmed.isEmpty else { return }
    showCreateIconPicker = false
    Task {
        do {
            let cat = try await LibraryService.shared.createCategory(name: trimmed, icon: selectedCreateIcon)
            guard let reelUUID = UUID(uuidString: reelId) else { return }
            try await LibraryService.shared.assignCategory(reelId: reelUUID, categoryId: cat.id)
            await MainActor.run { dismiss() }
        } catch {
            await MainActor.run { assignError = true }
        }
    }
}
```

- [ ] **Step 6: Build (⌘B)**

Expected: build succeeds.

- [ ] **Step 7: Test in simulator**

1. Open an inbox reel that needs a category
2. In the "Create new category" section: tap the icon button → picker appears, select an icon
3. Enter a name → tap Add → reel gets assigned + sheet dismisses
4. Verify the new category appears in Collections list with the chosen icon

- [ ] **Step 8: Commit**

```bash
git add frontend/CategoriseReelView.swift
git commit -m "feat: add icon picker to CategoriseReelView create-new-category flow"
```

---

## Task 9: Rewrite LibraryView — CollageLayout + New CategoryCard

**Files:**
- Modify: `frontend/Views/LibraryView.swift`

- [ ] **Step 1: Replace the entire file**

```swift
import Auth
import SwiftUI

struct LibraryView: View {
    @EnvironmentObject private var appVM: AppViewModel
    @EnvironmentObject private var auth: AuthSession
    var onInboxTap: () -> Void = {}

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                topBar
                    .padding(.horizontal, 20)
                    .padding(.top, 6)
                    .padding(.bottom, 12)

                if appVM.inboxCount > 0 {
                    inboxBanner
                        .padding(.horizontal, 14)
                        .padding(.bottom, 12)
                }

                if appVM.categorySummaries.isEmpty && appVM.inboxCount == 0 {
                    libraryEmptyState
                        .padding(.horizontal, 20)
                        .padding(.top, 20)
                } else if !appVM.categorySummaries.isEmpty {
                    Text("Collections")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(AppTheme.textFaint)
                        .textCase(.uppercase)
                        .kerning(1.2)
                        .padding(.horizontal, 20)
                        .padding(.bottom, 8)

                    CollageLayout(summaries: appVM.categorySummaries)
                        .padding(.horizontal, 14)
                }
            }
        }
        .refreshable { await appVM.load() }
        .background(AppTheme.background.ignoresSafeArea())
        .navigationBarHidden(true)
        .navigationDestination(for: CategorySummary.self) { summary in
            CategoryDetailView(summary: summary)
        }
    }

    // MARK: - Sub-views

    private var libraryEmptyState: some View {
        VStack(alignment: .leading, spacing: 24) {
            VStack(alignment: .leading, spacing: 10) {
                Image(systemName: "sparkles")
                    .font(.system(size: 36))
                    .foregroundColor(AppTheme.accent)
                    .padding(.bottom, 4)
                Text("Your library is empty")
                    .font(.system(size: 22, weight: .bold))
                    .foregroundColor(AppTheme.textPrimary)
                Text("Share reels from Instagram to build your personal collection.")
                    .font(.system(size: 14))
                    .foregroundColor(AppTheme.textMuted)
            }

            VStack(spacing: 0) {
                LibraryHowToStep(number: 1, text: "Open any reel in Instagram")
                Divider().background(AppTheme.border).padding(.leading, 42)
                LibraryHowToStep(number: 2, text: "Tap the Share button")
                Divider().background(AppTheme.border).padding(.leading, 42)
                LibraryHowToStep(number: 3, text: "Select ReelMind from the list")
            }
            .background(AppTheme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(AppTheme.border, lineWidth: 1)
            )
        }
    }

    private var topBar: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Your library")
                    .font(.system(size: 28, weight: .bold))
                    .foregroundColor(AppTheme.textPrimary)
                Text("\(appVM.totalCount) reels saved")
                    .font(.system(size: 13))
                    .foregroundColor(AppTheme.textFaint)
            }
            Spacer()
            Button { appVM.showSettings = true } label: {
                Circle()
                    .fill(AppTheme.avatarGradient)
                    .frame(width: 36, height: 36)
                    .overlay(
                        Text(auth.session?.user.email?.prefix(1).uppercased() ?? "?")
                            .font(.system(size: 14, weight: .bold))
                            .foregroundColor(.white)
                    )
            }
            .buttonStyle(.plain)
        }
    }

    private var inboxBanner: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(AppTheme.accent)
                .frame(width: 7, height: 7)
            (Text("\(appVM.inboxCount) reels")
                .fontWeight(.bold)
                .foregroundColor(AppTheme.accent)
            + Text(" need a category")
                .foregroundColor(AppTheme.textMuted))
            .font(.system(size: 12))
            Spacer()
            Text("›")
                .font(.system(size: 16))
                .foregroundColor(AppTheme.textFaint)
        }
        .padding(.horizontal, 13)
        .padding(.vertical, 10)
        .background(AppTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 13, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 13, style: .continuous)
                .stroke(AppTheme.border, lineWidth: 1)
        )
        .contentShape(Rectangle())
        .onTapGesture { onInboxTap() }
    }
}

// MARK: - How-to step

private struct LibraryHowToStep: View {
    let number: Int
    let text: String

    var body: some View {
        HStack(spacing: 12) {
            Text("\(number)")
                .font(.system(size: 12, weight: .bold))
                .foregroundColor(AppTheme.accent)
                .frame(width: 26, height: 26)
                .background(AppTheme.surfaceSecondary)
                .clipShape(Circle())
            Text(text)
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(AppTheme.textSecondary)
            Spacer()
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 13)
    }
}

// MARK: - Collage Layout

private struct CollageLayout: View {
    let summaries: [CategorySummary]

    private var sorted: [CategorySummary] {
        summaries.sorted { $0.reelCount > $1.reelCount }
    }

    private struct LayoutRow {
        let items: [CategorySummary]
        let colorIndices: [Int]
        let isSolo: Bool
        let pairIndex: Int  // alternates 0=wide+narrow, 1=narrow+wide, ...
    }

    private var rows: [LayoutRow] {
        let items = sorted
        guard !items.isEmpty else { return [] }

        var result: [LayoutRow] = []

        // Always a hero row first
        result.append(LayoutRow(items: [items[0]], colorIndices: [0], isSolo: true, pairIndex: 0))
        guard items.count > 1 else { return result }

        var remaining = Array(items.dropFirst())
        var nextColor = 1
        var pairIdx = 0

        // Odd remainder: prepend one full-width solo before pairing
        if remaining.count % 2 == 1 {
            result.append(LayoutRow(items: [remaining.removeFirst()], colorIndices: [nextColor], isSolo: true, pairIndex: 0))
            nextColor += 1
        }

        // Pair up the rest
        while remaining.count >= 2 {
            let pair = [remaining.removeFirst(), remaining.removeFirst()]
            result.append(LayoutRow(items: pair, colorIndices: [nextColor, nextColor + 1], isSolo: false, pairIndex: pairIdx))
            nextColor += 2
            pairIdx += 1
        }

        return result
    }

    var body: some View {
        VStack(spacing: 7) {
            ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                rowView(row)
            }
        }
    }

    @ViewBuilder
    private func rowView(_ row: LayoutRow) -> some View {
        if row.isSolo {
            cardLink(row.items[0], colorIndex: row.colorIndices[0], isNarrow: false)
        } else {
            let isWideFirst = row.pairIndex % 2 == 0
            GeometryReader { geo in
                HStack(spacing: 7) {
                    let gap: CGFloat = 7
                    let wide = (geo.size.width - gap) * 2 / 3
                    let narrow = (geo.size.width - gap) * 1 / 3
                    if isWideFirst {
                        cardLink(row.items[0], colorIndex: row.colorIndices[0], isNarrow: false)
                            .frame(width: wide)
                        cardLink(row.items[1], colorIndex: row.colorIndices[1], isNarrow: true)
                            .frame(width: narrow)
                    } else {
                        cardLink(row.items[0], colorIndex: row.colorIndices[0], isNarrow: true)
                            .frame(width: narrow)
                        cardLink(row.items[1], colorIndex: row.colorIndices[1], isNarrow: false)
                            .frame(width: wide)
                    }
                }
            }
            .frame(height: 116)
        }
    }

    private func cardLink(_ summary: CategorySummary, colorIndex: Int, isNarrow: Bool) -> some View {
        NavigationLink(value: summary) {
            CategoryCard(summary: summary, colorIndex: colorIndex, isNarrow: isNarrow)
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Category Card

private struct CategoryCard: View {
    let summary: CategorySummary
    let colorIndex: Int
    var isNarrow: Bool = false

    private var bgColor: Color { AppTheme.cardBackgrounds[colorIndex % 10] }
    private var iconColor: Color { AppTheme.cardIconColors[colorIndex % 10] }
    private var iconSize: CGFloat { isNarrow ? 20 : 26 }
    private var wmFontSize: CGFloat { isNarrow ? 48 : 68 }
    private var wmOffset: CGFloat { isNarrow ? 8 : 12 }
    private var nameFontSize: CGFloat { isNarrow ? 12 : 13 }

    var body: some View {
        ZStack(alignment: .bottomTrailing) {
            bgColor

            // Watermark count — faint, slightly overflows bottom-right (clipped)
            Text("\(summary.reelCount)")
                .font(.system(size: wmFontSize, weight: .heavy))
                .foregroundColor(AppTheme.textPrimary.opacity(0.065))
                .offset(x: 3, y: wmOffset)
                .allowsHitTesting(false)

            // Icon + name stack
            VStack(alignment: .leading, spacing: 0) {
                Image(systemName: summary.icon ?? "bookmark")
                    .font(.system(size: iconSize))
                    .foregroundColor(iconColor)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)

                VStack(alignment: .leading, spacing: 2) {
                    Text(summary.name)
                        .font(.system(size: nameFontSize, weight: .bold))
                        .foregroundColor(AppTheme.textPrimary)
                        .lineLimit(1)
                    if let date = summary.lastSavedAt {
                        Text("Updated \(date.timeAgoString())")
                            .font(.system(size: 8.5))
                            .foregroundColor(AppTheme.textFaint)
                    }
                }
            }
            .padding(11)
        }
        .frame(maxWidth: .infinity)
        .frame(height: 116)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(Color.black.opacity(0.055), lineWidth: 1)
        )
    }
}

#Preview {
    NavigationStack {
        LibraryView()
    }
    .environmentObject(AppViewModel())
    .environmentObject(AuthSession())
}
```

- [ ] **Step 2: Build (⌘B)**

Expected: build succeeds.

- [ ] **Step 3: Run in simulator — verify layout with 1 category**

Expected: one full-width card (116pt tall) with icon top-left, name bottom-left, faint count watermark bottom-right.

- [ ] **Step 4: Add a second category and verify layout**

Expected: two full-width cards stacked vertically (each 116pt).

- [ ] **Step 5: Add a third category and verify layout**

Expected: one full-width hero card, then one row with wide card (2/3) + narrow card (1/3).

- [ ] **Step 6: Add fourth and fifth categories and verify**

4 categories: hero / full-width / wide+narrow.
5 categories: hero / wide+narrow / narrow+wide.

- [ ] **Step 7: Verify watermark is faint and clipped at card edges**

The count number should be barely visible at bottom-right, slightly cut off at the card boundary.

- [ ] **Step 8: Commit**

```bash
git add frontend/Views/LibraryView.swift
git commit -m "feat: replace LazyVGrid with CollageLayout and redesign CategoryCard with icon + watermark"
```

---

## Self-Review Notes

- All 9 tasks map directly to spec requirements.
- `Color+Hex` not needed — `AppTheme` already uses `Color(r:g:b:)`.
- `AppViewModel` sort order (by `lastSavedAt`) is intentionally unchanged; `CollageLayout` sorts by `reelCount` independently for display only.
- `CategoriseReelView.createCategoryAndAssign` now uses `LibraryService` directly (bypassing `ReelCategoryAPI`) — this is correct because `ReelCategoryAPI.assignAsync` creates-or-fetches by name without icon support. The existing "select existing category" path in `CategoriseReelView` still uses `ReelCategoryAPI.assignAsync` unchanged.
- The `reelId: String` → `UUID` conversion in Task 8 Step 5 uses `UUID(uuidString:)` with a guard — safe, as the reel ID always comes from Supabase and is always a valid UUID string.
