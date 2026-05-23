# Category Icons + Home Screen Layout

**Date:** 2026-05-23

---

## Overview

Two features:
1. **Icon picker** — Users can pick an icon when creating or renaming a category. Shown on every category card and manage row. Default icon is `bookmark` when none selected.
2. **Home screen collage layout** — Replace the flat 2-column grid in `LibraryView` with a collage layout that mirrors `home_screen_concepts.html`: full-width hero card + alternating wide/narrow rows. Reel count shown as a faint watermark.

---

## Feature 1 — Category Icon Picker

### Database

New migration: add `icon TEXT` column to `public.categories`, nullable, no default.

```sql
ALTER TABLE public.categories ADD COLUMN icon TEXT;
```

Null in the DB is treated as `"bookmark"` in the app. No backfill needed.

### Swift Models

`Category` (Models/Category.swift):
- Add `let icon: String?`
- Add `"icon"` to `CodingKeys`

`CategorySummary` (Models/Category.swift):
- Add `let icon: String?`
- Display value: `summary.icon ?? "bookmark"`

`AppViewModel` — `categorySummaries` builder must include `icon` when constructing `CategorySummary` from `Category`.

### Icon Catalog

26 SF Symbol names (index → symbolName):

| # | Name | SF Symbol |
|---|------|-----------|
| 1 | Recipes | `fork.knife` |
| 2 | Fitness | `dumbbell` |
| 3 | Travel | `airplane` |
| 4 | Fashion | `bag` |
| 5 | Beauty | `sparkles` |
| 6 | Skincare | `drop` |
| 7 | Home Decor | `house` |
| 8 | DIY & Crafts | `scissors` |
| 9 | Comedy | `face.smiling` |
| 10 | Music | `music.note` |
| 11 | Dance | `headphones` |
| 12 | Motivation | `bolt` |
| 13 | Business | `briefcase` |
| 14 | Finance | `banknote` |
| 15 | Tech & AI | `cpu` |
| 16 | Art | `paintpalette` |
| 17 | Photography | `camera` |
| 18 | Nature | `leaf` |
| 19 | Wellness | `heart` |
| 20 | Parenting | `figure.and.child.holdinghands` |
| 21 | Pets | `pawprint` |
| 22 | Books | `book.open` |
| 23 | Gaming | `gamecontroller` |
| 24 | Education | `graduationcap` |
| 25 | Sports | `trophy` |
| 26 | Default (catch-all) | `bookmark` |

A shared constant `CategoryIcons.all: [String]` holds all 26 symbol names in order.

### Icon Picker UI Component

`CategoryIconPicker` — a reusable SwiftUI view:
- Shows a 5-column grid of all 26 icons
- Each cell: SF Symbol centered in a rounded square, tonal fill on selection
- Selected icon gets a filled accent background; others use `surfaceSecondary`
- Binding: `@Binding var selectedIcon: String`

### ManageCategoriesView — Create & Rename

The current system `.alert` for both create and rename is replaced by a `.sheet` presenting `CategoryFormSheet`.

`CategoryFormSheet`:
- One input row: `[icon button (SF Symbol)] [TextField "Collection name"]`
- Tapping the icon button toggles `CategoryIconPicker` inline below the row
- Save / Create button in the sheet toolbar (disabled when name is empty)
- On dismiss without save: no changes
- `selectedIcon` defaults to `"bookmark"`; saved alongside the name

`LibraryService.createCategory(name:icon:)` — add `icon` parameter, include in `Payload`.
`LibraryService.renameCategory(id:newName:icon:)` — add `icon` parameter, include in `Payload`.

`CategoryManageRow`: replace hardcoded `folder` SF Symbol with `Image(systemName: category.icon ?? "bookmark")`.

### CategoriseReelView — Create New Category Section

The existing HStack `[TextField] [Add button]` becomes:
`[icon button (SF Symbol)] [TextField "e.g. Travel"] [Add button]`

Tapping the icon button toggles `CategoryIconPicker` inline below the row (same pattern as `CategoryFormSheet`).

`createCategoryAndAssign()` passes `selectedIcon` to `ReelCategoryAPI` / `LibraryService`.

`ReelCategoryAPI.assignAsync` already creates-or-fetches by name; update it to also pass `icon` on creation.

`loadReelAndCategories()` currently selects `id, name` from `categories` — update to `id, name, icon`. Update `CategoryRow` struct to include `let icon: String?`.

---

## Feature 2 — Home Screen Collage Layout

### Layout Algorithm

Categories are sorted by `reelCount` descending before layout.

```
n = total category count

n == 1:  [hero]                                     (1 full-width)
n == 2:  [hero]                                     (1 full-width)
         [card2]                                    (1 full-width)
n == 3:  [hero]                                     (1 full-width)
         [card2 wide | card3 narrow]                (2/3 + 1/3)
n == 4:  [hero]                                     (1 full-width)
         [card2]                                    (1 full-width)
         [card3 wide | card4 narrow]                (2/3 + 1/3)
n == 5:  [hero]                                     (1 full-width)
         [card2 wide | card3 narrow]                (2/3 + 1/3)
         [card4 narrow | card5 wide]                (1/3 + 2/3)
n >= 6:  [hero]
         then consume remaining in pairs:
           if remaining count is odd → one full-width solo card first, then pairs
           pairs alternate: even pair index → wide+narrow, odd → narrow+wide
```

General rule for remaining after hero:
- odd count remaining → prepend one full-width, then pair the rest
- even count remaining → pair directly

Pairs alternate starting with wide+narrow (index 0), then narrow+wide (index 1), etc.

### CategoryCard Redesign

`CategoryCard` is rewritten. It accepts `summary: CategorySummary` and `colorIndex: Int` (its position in the sorted list, used to pick palette color).

Visual spec:
- **Background**: tonal color from 10-color palette, picked by `colorIndex % 10`
- **Icon**: `Image(systemName: summary.icon ?? "bookmark")`, 28×28pt, top-left at (11, 11), tonal icon color (darker shade of bg)
- **Name**: bottom-left, font `.system(size: 14, weight: .bold)`, `AppTheme.textPrimary`, 1 line
- **Date**: bottom-left below name, font `.system(size: 8.5)`, `AppTheme.textFaint`, "Updated X ago" (hidden if `lastSavedAt == nil`)
- **Watermark count**: `Text("\(summary.reelCount)")`, font `.system(size: 68, weight: .heavy)`, `AppTheme.textPrimary.opacity(0.065)`, positioned absolute bottom-right (offset right: -4, bottom: -14), clipped to card bounds
- **Border**: 1pt `AppTheme.border.opacity(0.55)` overlay on rounded rect
- **Corner radius**: 14pt

Heights:
- Hero / full-width solo cards: 120pt
- Row cards (wide or narrow): 116pt

### 10-Color Palette

```swift
static let cardBackgrounds: [Color] = [
    Color(hex: "#faedcd"), // warm surface
    Color(hex: "#e9edc9"), // sage light
    Color(hex: "#ccd5ae"), // sage medium
    Color(hex: "#f3e8d0"), // warm cream
    Color(hex: "#dde6c8"), // cool sage
    Color(hex: "#f8f3e4"), // pale cream
    Color(hex: "#e4eccc"), // pale sage
    Color(hex: "#f0e4cc"), // warm peach
    Color(hex: "#d8e2b8"), // strong sage
    Color(hex: "#f5eedd"), // lightest cream
]
```

Tonal icon colors (paired with backgrounds, same index):
```swift
static let iconColors: [Color] = [
    Color(hex: "#8a6038"),
    Color(hex: "#5a6a34"),
    Color(hex: "#485a30"),
    Color(hex: "#8a6840"),
    Color(hex: "#527044"),
    Color(hex: "#7a6848"),
    Color(hex: "#4e6838"),
    Color(hex: "#8a6040"),
    Color(hex: "#426030"),
    Color(hex: "#7a6850"),
]
```

### LibraryView Changes

Remove `let columns = [GridItem(.flexible()), GridItem(.flexible())]` and `LazyVGrid`.

Replace with `CollageLayout(summaries: appVM.categorySummaries)` — a new private view that:
1. Sorts input by `reelCount` descending (independent of `AppViewModel`'s lastSavedAt sort — do not change `AppViewModel`)
2. Applies the layout algorithm above
3. Renders rows as `VStack(spacing: 7)` with full-width cards or `HStack(spacing: 7)` for 2-card rows
4. Passes `colorIndex` (position in the reelCount-sorted list) to each `CategoryCard`
5. Wraps each card in `NavigationLink(value: summary)`

The `.padding(.horizontal, 14)` wrapper stays the same as current grid padding.

---

## Data Flow Summary

```
categories table
  + icon TEXT (nullable)
        ↓
LibraryService.fetchCategories()  →  [Category(id, name, icon, createdAt)]
        ↓
AppViewModel.categorySummaries    →  [CategorySummary(id, name, icon, reelCount, lastSavedAt)]
        ↓
CollageLayout  →  CategoryCard(summary, colorIndex)
                   • icon SF Symbol top-left
                   • name + date bottom-left
                   • count watermark bottom-right
```

---

## Files Touched

| File | Change |
|------|--------|
| `supabase/migrations/20260523000001_add_icon_to_categories.sql` | new migration |
| `frontend/Models/Category.swift` | add `icon` field to `Category` + `CategorySummary` |
| `frontend/Views/LibraryView.swift` | replace `LazyVGrid` + `CategoryCard` with `CollageLayout` + new card |
| `frontend/Views/ManageCategoriesView.swift` | replace `.alert` with sheet, add icon picker |
| `frontend/CategoriseReelView.swift` | add icon button to create-new-category row |
| `frontend/Services/LibraryService.swift` | add `icon` to create/rename payloads and fetch select |
| `frontend/ViewModels/AppViewModel.swift` | pass `icon` when building `CategorySummary` |
| `frontend/Views/CategoryIconPicker.swift` | new shared component |
| `frontend/Extensions/Color+Hex.swift` | new (if not already present) — hex color init |
