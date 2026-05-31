# Thumbnail Caching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace bare `AsyncImage` calls with an `NSCache`-backed `CachedAsyncImage` and prefetch all thumbnails on app load so reel cards display instantly within a session.

**Architecture:** An `ImageCache` singleton (NSCache) is checked synchronously on each render; hits display immediately with zero loading state. On miss, `CachedAsyncImage` downloads and inserts into the cache. `AppViewModel.load()` fires a detached `TaskGroup` to prefetch all thumbnail URLs in parallel right after the Supabase fetch, so the cache is warm by the time the user interacts with the list.

**Tech Stack:** SwiftUI, UIKit (`UIImage`, `NSCache`), Swift Concurrency (`async/await`, `TaskGroup`)

---

## File Map

| File | Action |
|------|--------|
| `frontend/Services/ImageCache.swift` | Create |
| `frontend/Views/Components/CachedAsyncImage.swift` | Create |
| `frontend/ViewModels/AppViewModel.swift` | Modify — add `prefetchThumbnails` + call in `load()` |
| `frontend/Views/Components/ThumbnailView.swift` | Modify — swap `AsyncImage` → `CachedAsyncImage` |
| `frontend/Views/Components/ReelCardView.swift` | Modify — swap inline `AsyncImage` → `CachedAsyncImage` in `InboxReelCard` |

---

## Task 1: `ImageCache` singleton

**Files:**
- Create: `frontend/Services/ImageCache.swift`

- [ ] **Step 1: Create `ImageCache.swift`**

Create `frontend/Services/ImageCache.swift` with this exact content:

```swift
import UIKit

final class ImageCache {
    static let shared = ImageCache()
    private let cache = NSCache<NSString, UIImage>()

    private init() {
        cache.countLimit = 200
    }

    func image(for url: String) -> UIImage? {
        cache.object(forKey: url as NSString)
    }

    func insert(_ image: UIImage, for url: String) {
        cache.setObject(image, forKey: url as NSString)
    }
}
```

`countLimit = 200` means NSCache holds at most 200 images. Under memory pressure iOS evicts entries automatically — no manual eviction needed.

- [ ] **Step 2: Add file to Xcode target**

In Xcode, right-click `frontend/Services/` in the Project Navigator → "Add Files to ReelMind" → select `ImageCache.swift`. Make sure the "ReelMind" app target checkbox is ticked (not the share extension).

- [ ] **Step 3: Build to verify it compiles**

Press ⌘B. Expected: build succeeds with no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/Services/ImageCache.swift
git commit -m "feat: add NSCache-backed ImageCache singleton"
```

---

## Task 2: `CachedAsyncImage` view

**Files:**
- Create: `frontend/Views/Components/CachedAsyncImage.swift`

- [ ] **Step 1: Create `CachedAsyncImage.swift`**

Create `frontend/Views/Components/CachedAsyncImage.swift` with this exact content:

```swift
import SwiftUI

struct CachedAsyncImage<Content: View>: View {
    let urlString: String?
    @ViewBuilder let content: (AsyncImagePhase) -> Content

    @State private var phase: AsyncImagePhase = .empty

    var body: some View {
        content(phase)
            .task(id: urlString) {
                await load()
            }
    }

    @MainActor
    private func load() async {
        guard let str = urlString, let url = URL(string: str) else {
            phase = .empty
            return
        }
        if let cached = ImageCache.shared.image(for: str) {
            phase = .success(Image(uiImage: cached))
            return
        }
        phase = .empty
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            guard let uiImage = UIImage(data: data) else {
                phase = .failure(URLError(.cannotDecodeContentData))
                return
            }
            ImageCache.shared.insert(uiImage, for: str)
            phase = .success(Image(uiImage: uiImage))
        } catch {
            phase = .failure(error)
        }
    }
}
```

**How it works:**
- `@State private var phase` starts as `.empty` (shows placeholder)
- `.task(id: urlString)` re-runs `load()` whenever `urlString` changes — handles list cell recycling correctly
- Cache hit → `phase = .success(...)` synchronously, view re-renders with no loading flicker
- Cache miss → downloads, inserts, then sets `phase = .success(...)`
- `@MainActor` on `load()` ensures `phase` mutations always happen on the main thread

- [ ] **Step 2: Add file to Xcode target**

In Xcode, right-click `frontend/Views/Components/` → "Add Files to ReelMind" → select `CachedAsyncImage.swift`. Tick the "ReelMind" app target only.

- [ ] **Step 3: Build to verify it compiles**

Press ⌘B. Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/Views/Components/CachedAsyncImage.swift
git commit -m "feat: add CachedAsyncImage — NSCache-backed drop-in for AsyncImage"
```

---

## Task 3: Prefetch thumbnails in `AppViewModel`

**Files:**
- Modify: `frontend/ViewModels/AppViewModel.swift`

Current `load()` ends with:
```swift
inboxReels  = reels.filter { $0.categoryId == nil }
totalCount  = reels.count
```

- [ ] **Step 1: Add `prefetchThumbnails` method to `AppViewModel`**

Add this private method inside `AppViewModel`, after the `assignCategory` method:

```swift
private func prefetchThumbnails(_ reels: [Reel]) {
    let urls = Set(reels.compactMap(\.thumbnailUrl))
        .filter { ImageCache.shared.image(for: $0) == nil }
    guard !urls.isEmpty else { return }
    Task {
        await withTaskGroup(of: Void.self) { group in
            for urlString in urls {
                group.addTask {
                    guard let url = URL(string: urlString),
                          let (data, _) = try? await URLSession.shared.data(from: url),
                          let image = UIImage(data: data) else { return }
                    ImageCache.shared.insert(image, for: urlString)
                }
            }
        }
    }
}
```

**Key details:**
- `Set(...)` deduplicates — no double-downloading if two reels share a thumbnail
- `.filter { ImageCache.shared.image(for: $0) == nil }` skips already-cached images (idempotent on silent refresh)
- `Task { ... }` is detached from `load()` — it does not block `load()` returning
- Individual task failures are silently dropped (`try?`) — prefetch is best-effort

- [ ] **Step 2: Call `prefetchThumbnails` at the end of `load()`'s `do` block**

In the `do` block inside `load()`, after `totalCount = reels.count`, add:

```swift
prefetchThumbnails(reels)
```

The complete `do` block should now look like:

```swift
do {
    async let reelsFetch    = LibraryService.shared.fetchAllReels()
    async let catsFetch     = LibraryService.shared.fetchAllVisibleCategories()
    let (reels, categories) = try await (reelsFetch, catsFetch)

    let grouped = Dictionary(
        grouping: reels.filter { $0.categoryId != nil },
        by: { $0.categoryId! }
    )
    categorySummaries = categories
        .map { cat -> CategorySummary in
            let catReels = grouped[cat.id] ?? []
            return CategorySummary(
                id: cat.id,
                name: cat.name,
                icon: cat.icon,
                reelCount: catReels.count,
                lastSavedAt: catReels.first?.createdAt,
                isDefault: cat.isDefault
            )
        }
        .filter { $0.reelCount > 0 }
        .sorted { ($0.lastSavedAt ?? .distantPast) > ($1.lastSavedAt ?? .distantPast) }

    inboxReels  = reels.filter { $0.categoryId == nil }
    totalCount  = reels.count
    prefetchThumbnails(reels)
} catch {
    print("[AppViewModel] load failed: \(error)")
}
```

- [ ] **Step 3: Build to verify it compiles**

Press ⌘B. Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/ViewModels/AppViewModel.swift
git commit -m "feat: prefetch all reel thumbnails into ImageCache on load"
```

---

## Task 4: Swap `AsyncImage` in `ThumbnailView`

**Files:**
- Modify: `frontend/Views/Components/ThumbnailView.swift`

Current `body` has:
```swift
Group {
    if let str = urlString, let url = URL(string: str) {
        AsyncImage(url: url) { phase in
            switch phase {
            case .empty:
                placeholder
                    .overlay(ProgressView().scaleEffect(0.6).tint(AppTheme.textFaint))
            case .success(let image):
                image
                    .resizable()
                    .scaledToFill()
                    .frame(width: width, height: height)
                    .clipped()
            case .failure:
                placeholder
            @unknown default:
                placeholder
            }
        }
    } else {
        placeholder
    }
}
```

- [ ] **Step 1: Replace the `Group { if let ... AsyncImage ... } else { ... }` block**

Replace the entire `Group { ... }` block in `body` with:

```swift
Group {
    CachedAsyncImage(urlString: urlString) { phase in
        switch phase {
        case .empty:
            placeholder
                .overlay(ProgressView().scaleEffect(0.6).tint(AppTheme.textFaint))
        case .success(let image):
            image
                .resizable()
                .scaledToFill()
                .frame(width: width, height: height)
                .clipped()
        case .failure:
            placeholder
        @unknown default:
            placeholder
        }
    }
}
```

`CachedAsyncImage` handles the `urlString == nil` case internally (stays in `.empty`), so the outer `if let` guard is no longer needed.

- [ ] **Step 2: Build to verify it compiles**

Press ⌘B. Expected: build succeeds.

- [ ] **Step 3: Run in simulator and verify**

Press ⌘R. Open the app, navigate to any screen showing `ThumbnailView` (e.g. `CategoryDetailView`). On first load you should see the placeholder briefly, then the thumbnail. Navigate away and back — the thumbnail should appear instantly with no spinner.

- [ ] **Step 4: Commit**

```bash
git add frontend/Views/Components/ThumbnailView.swift
git commit -m "feat: swap ThumbnailView to use CachedAsyncImage"
```

---

## Task 5: Swap `AsyncImage` in `InboxReelCard`

**Files:**
- Modify: `frontend/Views/Components/ReelCardView.swift`

The `inboxThumbnail` computed property currently contains:

```swift
private var inboxThumbnail: some View {
    Group {
        if let str = reel.thumbnailUrl, let url = URL(string: str) {
            AsyncImage(url: url) { phase in
                switch phase {
                case .success(let image):
                    image.resizable().scaledToFill().clipped()
                case .empty:
                    inboxThumbnailPlaceholder
                        .overlay(ProgressView().scaleEffect(0.6).tint(AppTheme.textFaint))
                default:
                    inboxThumbnailPlaceholder
                }
            }
        } else {
            inboxThumbnailPlaceholder
        }
    }
    .frame(width: 72)
    .frame(maxHeight: .infinity)
    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
}
```

- [ ] **Step 1: Replace the `Group { if let ... AsyncImage ... } else { ... }` block in `inboxThumbnail`**

Replace only the `Group { ... }` (before `.frame(width: 72)`) with:

```swift
private var inboxThumbnail: some View {
    Group {
        CachedAsyncImage(urlString: reel.thumbnailUrl) { phase in
            switch phase {
            case .success(let image):
                image.resizable().scaledToFill().clipped()
            case .empty:
                inboxThumbnailPlaceholder
                    .overlay(ProgressView().scaleEffect(0.6).tint(AppTheme.textFaint))
            default:
                inboxThumbnailPlaceholder
            }
        }
    }
    .frame(width: 72)
    .frame(maxHeight: .infinity)
    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
}
```

- [ ] **Step 2: Build to verify it compiles**

Press ⌘B. Expected: build succeeds.

- [ ] **Step 3: Run in simulator and verify end-to-end**

Press ⌘R.

1. Open the app — you should see inbox reel cards with placeholders briefly on first load.
2. Tap a category, come back to the Inbox — thumbnails should display instantly (already in NSCache from prefetch).
3. Save a new reel via share sheet, return to the app — the new reel's thumbnail may show a spinner on first appearance (it was added after the initial prefetch), then cache on next render.

- [ ] **Step 4: Commit**

```bash
git add frontend/Views/Components/ReelCardView.swift
git commit -m "feat: swap InboxReelCard to use CachedAsyncImage"
```
