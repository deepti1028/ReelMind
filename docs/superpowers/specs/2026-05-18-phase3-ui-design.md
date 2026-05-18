# Phase 3 UI Design Spec — ReelMind iOS

**Date:** 2026-05-18  
**Scope:** Full replacement of dev-mode `TempReels` views with production-quality SwiftUI screens  
**Theme:** Warm earth palette — light mode  
**Mockups:** `.superpowers/brainstorm/71349-1779093088/content/`

---

## 1. Color Palette

All new SwiftUI views use these semantic tokens, derived from the approved palette:

| Token | Hex | Usage |
|-------|-----|-------|
| `background` | `#fefae0` | Screen background, footer background |
| `surface` | `#faedcd` | Cards, input fields, banner, user card |
| `surfaceSecondary` | `#e9edc9` | Chips, icon backgrounds, toggle OFF, dividers |
| `border` | `#e5d5b8` | Card borders, row separators |
| `borderSubtle` | `#e9edc9` | Footer top border, header bottom border |
| `accent` | `#d4a373` | Active icons, creator handles, FAB, send button, toggles ON, phone frame |
| `accentDark` | `#9a6a35` | Avatar gradient end, hashtag tint |
| `sage` | `#ccd5ae` | Chip borders, secondary icon tint, watch-btn elements |
| `textPrimary` | `#2c1f0e` | Titles, body text, status bar |
| `textSecondary` | `#5a3e28` | Card names, AI message text |
| `textMuted` | `#9a7654` | Captions, subtitles, input placeholder |
| `textFaint` | `#b8956a` | Section labels, reel count, timestamps |
| `destructive` | `#cc4444` | Delete/trash icon |

**Avatar gradient:** `linear-gradient(135deg, #d4a373, #9a6a35)`  
**Thumbnail placeholder gradient:** `linear-gradient(160deg, #e9edc9, #ccd5ae)`

---

## 2. Navigation Structure

```
ContentView
  └── TabView (2 tabs, custom footer — no system TabView chrome)
        ├── Tab 0: LibraryView          ← "Library" with grid icon
        └── Tab 1: InboxView            ← "Inbox" with tray icon + badge
                                           (badge = count of uncategorised reels)

LibraryView
  └── NavigationLink → CategoryDetailView(category)

CategoryDetailView
  └── Sheet → ChatView(categoryId)        ← opened by floating FAB

ContentView (avatar tap)
  └── Sheet → SettingsView
```

No system `NavigationStack` chrome shown — all nav bars are custom-built.

---

## 3. Screen Specifications

### Screen 1 — Home (Library tab)

**File:** `screen-home-v3.html`

**Layout (top → bottom):**
1. **Status bar** — system, dark text
2. **Top bar** — "Your library" (28px bold, `textPrimary`) left; round avatar (36×36, gradient) right. Below title: `"42 reels saved"` in `textFaint` with the count in `accent`
3. **Banner** — `surface` card with `accent` dot + `"3 reels need a category"` text; taps → InboxView. Hidden when inbox count = 0
4. **"COLLECTIONS" section label** — 10px uppercase, `textFaint`
5. **2-column grid** — `LazyVGrid`, aspect-ratio 1:1 cards. Each card: large count (34px 800-weight `textPrimary`), category name (12px 600-weight `textSecondary`), last-updated subtitle (`textFaint`). Card background `surface`, border `border`, radius 16
6. **Footer** — custom, 2 tabs (see §5)

**Data binding:** categories list from Supabase, sorted by `updated_at` desc. Total count = sum of all category reel counts.

---

### Screen 2 — Inbox tab

**File:** `screen-home-v3.html` (right phone)

**Layout:**
1. Status bar
2. **Header** — "Needs a category" (26px bold), subtitle explaining low-confidence reels
3. **Reel list** — `ScrollView > VStack` of reel cards (see §6 Reel Card component)
4. Footer

**Empty state:** when inbox count = 0, show centered illustration + "All caught up" message.

**Category chip tap:** assigns the reel to that category, removes card from list with slide-out animation.

---

### Screen 3 — Category Detail

**File:** `screen-category-detail.html`

**Layout:**
1. Status bar
2. **Nav bar** — `accent`-coloured back chevron + "Back" text (13px 600-weight). No system nav bar
3. **Category header** — category name (26px bold `textPrimary`) left; `"24 reels saved"` right (`textFaint`, count in `accent`)
4. **Reel list** — `ScrollView`, reel cards without category chips (see §6)
5. **Floating chat FAB** — 44×44 circle, `accent` fill, chat-bubble SVG icon in white. `position: sticky` equivalent via `.overlay(alignment: .bottomTrailing)` with `padding(.bottom, 72)`. Taps → ChatView sheet
6. **Footer** — Library tab active

**Tap card → open URL:** `UIApplication.shared.open(reel.url)` — opens Instagram or browser.

---

### Screen 4a — Chat (empty state)

**File:** `screen-chat.html` (left phone)

**Presentation:** sheet over CategoryDetailView, full-screen on iPhone.

**Layout:**
1. Status bar
2. **Chat header** — left column: pill breadcrumb (`"● Skincare · Chat"` on `surfaceSecondary` / `sage` border, `textSecondary`) + category title (22px bold); right: close button (22×22 circle, `surface` fill, × icon)
3. **Empty body** — AI icon (40×40 circle, `surface` border), "What are you looking for?" heading, subtitle, "TRY ASKING" label, 3 prompt chips (`surface` card, `border`)
4. **Input bar** — `surface` rounded field + `accent` send button

**Prompt chip tap:** pre-fills input field.

---

### Screen 4b — Chat (active conversation)

**File:** `screen-chat.html` (right phone)

Same header + input bar as 4a. Conversation area:

- **User message bubble** — right-aligned, `surface` bg, `border` stroke, rounded 16/4px corners
- **AI response block** — left-aligned. Label row: `accent` dot + "ReelMind" in `accent` 10px uppercase. Text bubble: white bg, `borderSubtle` border, rounded 4/16/16/16px corners
- **Inline reel cards** — horizontal `ScrollView` below AI text. Each card: 130px wide, `surface` bg, gradient thumbnail (80px tall), creator handle in `accent`, caption (2-line clamp), "Watch reel" button (`surfaceSecondary` bg, `sage` border)

**Backend:** `POST /sessions` → `POST /messages` → `GET /messages` (Steps 19–22 pipeline). Session scoped to a `category_id`.

---

### Screen 5 — Settings

**File:** `screen-settings.html`

**Presentation:** sheet from avatar tap on Home screen. No footer.

**Layout:**
1. Status bar
2. **Page header** — "ACCOUNT" super-label (10px uppercase `textFaint`); title row: "Settings" (28px bold `textPrimary`) + "Sign out" (red text button) right-aligned
3. **User card** — `surface` card with gradient avatar, name, email, "Edit" button (`surfaceSecondary` bg, `sage` border)
4. **LIBRARY section:**
   - Manage categories → row with count + chevron (navigates to category management sheet, out of scope for Phase 3)
   - Auto-categorise → toggle (persisted in `@AppStorage("autoCategorise")`, default ON)
5. **SAVING section:**
   - Share sheet permissions → row showing "Granted" in `accent`, taps → iOS Settings URL
   - Save notifications → toggle (wired to `NotificationPermissionManager`, default ON)
6. **PRIVACY section:**
   - Data & privacy → row with chevron (stub — no destination in Phase 3)

**Section groups:** `surface` bg, `border` stroke, 14px radius. Row separators `border` color.

---

## 4. Footer Component

Shared across LibraryView, InboxView, CategoryDetailView.

```
HStack {
  FooterTab(icon: gridIcon, label: "Library", isActive: selectedTab == 0)
  FooterTab(icon: inboxIcon, label: "Inbox",   isActive: selectedTab == 1, badge: inboxCount)
}
.background(Color("background"))
.overlay(top: Divider color("borderSubtle"))
.frame(height: 56 + safeAreaBottom)
```

**Icons (SVG → SF Symbol equivalents):**
- Library: `square.grid.2x2.fill` — filled when active (`accent`), outline when inactive (`textFaint`)
- Inbox: `tray.and.arrow.down` — stroked, `accent` when active, `textFaint` when inactive

**Badge:** small `accent`-fill circle (15×15) top-right of inbox icon, showing uncategorised count. Hidden when count = 0.

---

## 5. Reel Card Component

Used in both InboxView and CategoryDetailView. Two variants:

**Inbox variant** (with category chips):
```
VStack {
  HStack(alignment: .top) {
    thumbnail (54×80, radius 8, placeholder gradient)
    VStack {
      HStack { creatorHandle (accent, 12px bold) ; TrashButton }
      caption (2-line clamp, 11px, textMuted)
    }
  }
  .padding(11, 12, 0, 12)
  
  categoryChipRow (HStack, scrollable, padding 9/12/11/12)
}
.background(surface)
.cornerRadius(14)
.overlay(border)
```

**Category detail variant** (with hashtags, no chips, time + watch hint footer):
```
VStack {
  HStack(alignment: .top) {
    thumbnail (58×88)
    VStack {
      HStack { creatorHandle ; TrashButton }
      caption (2-line clamp)
      hashtagRow
    }
  }
  
  HStack {
    timeAgo (textFaint, 10px)
    Spacer()
    watchHint ("↗ tap to watch", textFaint, 10px)
  }
  .padding(.horizontal, 12).padding(.bottom, 10)
}
```

**Trash button:** `#cc4444` trash SVG, 15×15. Tap → confirmation then `DELETE /reels/{id}`.

**Thumbnail:** `AsyncImage` loading from `reel.thumbnailUrl`. Placeholder = gradient `#e9edc9 → #ccd5ae`.

---

## 6. Out of Scope (Phase 3)

- Manage categories screen (Settings → Manage categories row is present but navigates nowhere)
- Data & privacy screen (row present, no destination)
- Share sheet permissions deep-link (row taps to iOS Settings URL)
- Onboarding, Login, Signup screens (unchanged)
- Push notification delivery (FCM wiring done in pipeline, not UI)

---

## 7. Files to Create / Replace

| New file | Replaces |
|----------|----------|
| `frontend/Views/LibraryView.swift` | `frontend/TempReels/TempReelsView.swift` |
| `frontend/Views/InboxView.swift` | new |
| `frontend/Views/CategoryDetailView.swift` | new |
| `frontend/Views/ChatView.swift` | new |
| `frontend/Views/SettingsView.swift` | new |
| `frontend/Views/Components/ReelCard.swift` | new |
| `frontend/Views/Components/FooterTabBar.swift` | new |
| `frontend/Theme/ReelsTheme.swift` | replace entire file with new palette tokens |

`ContentView.swift` updated to wire the new tab bar and sheet presentations.
