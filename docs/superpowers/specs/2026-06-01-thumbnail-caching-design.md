# Thumbnail Caching — Design Spec
**Date:** 2026-06-01  
**Status:** Approved

---

## Problem

`ThumbnailView` and `InboxReelCard` both use bare `AsyncImage` with no caching layer. Every time either view renders it fires a fresh network request, causing a multi-second loading spinner on every app open. The user wants reel cards to appear complete (thumbnail visible) as soon as the list renders.

## Constraints

- Same-session caching only — no background app refresh, no cold-start requirement
- Zero new dependencies — no CocoaPods additions
- iOS frontend only — no backend or schema changes

---

## Architecture

Three new/modified pieces:

```
Services/ImageCache.swift               ← new
Views/Components/CachedAsyncImage.swift ← new
ViewModels/AppViewModel.swift           ← small addition
Views/Components/ThumbnailView.swift    ← swap AsyncImage
Views/Components/ReelCardView.swift     ← swap AsyncImage
```

---

## Components

### `ImageCache` (`Services/ImageCache.swift`)

A singleton wrapping `NSCache<NSString, UIImage>`.

- `countLimit = 200` — covers any realistic reel library; NSCache evicts under memory pressure automatically
- `image(for url: String) -> UIImage?` — synchronous read
- `insert(_ image: UIImage, for url: String)` — synchronous write

No byte limit configured explicitly; NSCache uses system memory pressure signals.

### `CachedAsyncImage` (`Views/Components/CachedAsyncImage.swift`)

A SwiftUI view, drop-in replacement for `AsyncImage`.

**Parameters:** `urlString: String?`, `width: CGFloat`, `height: CGFloat`, optional `content: (Image) -> some View` closure to support both fixed-frame (`ThumbnailView`) and stretchy-height (`InboxReelCard`) use cases.

**Behaviour:**
1. On appear, checks `ImageCache` synchronously.
2. Cache hit → renders `Image(uiImage:)` immediately, zero loading state.
3. Cache miss → shows placeholder, downloads via `URLSession.shared.data(from:)`, inserts into cache, re-renders.
4. Uses `.task(id: urlString)` so the download cancels and restarts correctly when a list cell is recycled.
5. Download or decode failure → falls back to placeholder silently.

### `prefetchThumbnails` (`AppViewModel`)

A private method called at the end of `load()` after the Supabase fetch completes.

- Collects all non-nil `thumbnailUrl` values from `reels`, deduplicates
- Skips URLs already present in `ImageCache` (idempotent)
- Fires a `Task { withTaskGroup(...) }` — detached so it does not block `load()` from returning and showing the UI
- Each child task: `URLSession.shared.data(from:)` → decode `UIImage` → `ImageCache.insert()`
- Failures are silently swallowed — prefetch is best-effort

---

## Data Flow

```
App opens
    │
    ▼
ContentView.task → AppViewModel.load()
    │
    ├─ Supabase fetch (reels + categories)  ~200ms
    │
    ├─ UI renders list (placeholders shown briefly)
    │
    └─ prefetchThumbnails(reels)  ← fires immediately, non-blocking
            │
            └─ TaskGroup: parallel URLSession downloads → ImageCache
                    │
                    └─ CachedAsyncImage: cache hit on next render
                       → displays image with zero flicker
```

**Timing reality:** The list renders in ~1 frame (~16ms). A thumbnail download takes 200–500ms. So on the very first load within a session, placeholders appear briefly. On every subsequent navigation to the same screen, all images display instantly from `NSCache`.

---

## Files Changed

| File | Change |
|------|--------|
| `frontend/Services/ImageCache.swift` | New — NSCache singleton |
| `frontend/Views/Components/CachedAsyncImage.swift` | New — cache-aware image view |
| `frontend/Views/Components/ThumbnailView.swift` | Swap `AsyncImage` → `CachedAsyncImage` |
| `frontend/Views/Components/ReelCardView.swift` | Swap inline `AsyncImage` → `CachedAsyncImage` |
| `frontend/ViewModels/AppViewModel.swift` | Add `prefetchThumbnails` + call in `load()` |

## Out of Scope

- Disk persistence across cold starts
- Background app refresh
- Any new pod/SPM dependency
- Backend or database changes
