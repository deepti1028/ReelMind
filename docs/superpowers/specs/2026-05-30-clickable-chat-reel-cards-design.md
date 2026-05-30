# Clickable Chat Reel Cards — Design Spec

**Date:** 2026-05-30  
**Status:** Approved  

---

## Problem

Reel cards shown below AI responses in `ChatView` display a "Watch reel" label but are not tappable. The `ReelSource` model returned by the chat API omits the Instagram `url`, so the client has no way to open the reel.

---

## Goal

Make each inline reel card in the chat tap-to-open, launching the reel in Instagram exactly as `InboxReelCard` and `DetailReelCard` already do.

---

## Approach

Thread the reel `url` through the existing data pipeline — SQL function → RAG service → backend API model → iOS model — then wrap the card in a `Button`. No new files, no new services, no extra network calls.

---

## Changes

### 1. SQL Migration — `match_reel_chunks`

**File:** `supabase/migrations/20260530000000_add_url_to_match_reel_chunks.sql`

Add `url text` to the `returns table` clause and `r.url` to the `SELECT` list. Uses `CREATE OR REPLACE` — non-destructive, no downtime.

```sql
create or replace function match_reel_chunks(...)
returns table (
    reel_id        uuid,
    content        text,
    similarity     float,
    creator_handle text,
    thumbnail_url  text,
    caption        text,
    url            text        -- added
)
language sql as $$
    select
        rc.reel_id,
        rc.content,
        1 - (rc.embedding <=> query_embedding) as similarity,
        r.creator_handle,
        r.thumbnail_url,
        r.caption,
        r.url                  -- added
    from reel_chunks rc
    join reels r on r.id = rc.reel_id
    ...
$$;
```

### 2. RAG Service — `services/rag.py`

In the `answer()` return value, add `"url"` to each source dict:

```python
"sources": [
    {
        "reel_id": str(r["reel_id"]),
        "creator_handle": r.get("creator_handle"),
        "thumbnail_url": r.get("thumbnail_url"),
        "caption": r.get("caption"),
        "url": r.get("url"),   # added
    }
    for r in chunks
],
```

### 3. Backend API Model — `api/v1/chat.py`

Add `url` to the `ReelSource` Pydantic model:

```python
class ReelSource(BaseModel):
    reel_id: str
    creator_handle: Optional[str] = None
    thumbnail_url: Optional[str] = None
    caption: Optional[str] = None
    url: Optional[str] = None   # added
```

The field flows automatically into the JSON response and into the `chat_messages.sources` JSONB column — no DB migration needed for that table.

### 4. iOS Model — `ChatService.swift`

Add `url` to `ReelSource`:

```swift
struct ReelSource: Decodable, Identifiable {
    var id: String { reelId }
    let reelId: String
    let creatorHandle: String?
    let thumbnailUrl: String?
    let caption: String?
    let url: String?            // added

    enum CodingKeys: String, CodingKey {
        case reelId = "reel_id"
        case creatorHandle = "creator_handle"
        case thumbnailUrl = "thumbnail_url"
        case caption
        case url                // added
    }
}
```

### 5. iOS Chat UI — `ChatView.swift`

In `inlineReels()`, wrap the card `VStack` in a `Button`. Mirror the `DetailReelCard` pattern — guard against nil URL, track open failure with local state:

```swift
private func inlineReels(_ sources: [ReelSource]) -> some View {
    ScrollView(.horizontal, showsIndicators: false) {
        HStack(spacing: 8) {
            ForEach(sources) { source in
                ChatReelCard(source: source)
            }
        }
    }
}
```

Extract the card into a small private struct `ChatReelCard` (inside `ChatView.swift`) that holds `@State private var openFailed = false` and wraps the existing layout in a `Button`:

```swift
private struct ChatReelCard: View {
    let source: ReelSource
    @State private var openFailed = false

    private var reelURL: URL? { source.url.flatMap(URL.init) }

    var body: some View {
        Button {
            guard let url = reelURL else { openFailed = true; return }
            UIApplication.shared.open(url, options: [:]) { success in
                if !success { openFailed = true }
            }
        } label: {
            // existing VStack layout, unchanged
            // "Watch reel" label remains as the visual affordance
        }
        .buttonStyle(.plain)
    }
}
```

---

## Error Handling

- If `source.url` is nil (e.g. older cached messages stored before this change), `openFailed` is set to `true`. The card renders normally; no crash.
- If `UIApplication.open` returns `false` (Instagram not installed), `openFailed` is set to `true`. No visual change required — same behaviour as `DetailReelCard`.

---

---

## Card Visual Design — `ChatReelCard`

**Aesthetic direction:** "Story Frame" — portrait-oriented card that mirrors the shape of an Instagram Reel. Full-bleed thumbnail, warm gradient scrim, creator name overlaid at the bottom. Feels native to the reel format.

### Layout

```
┌──────────────────┐  ← 90 × 130 pt, radius 14
│                  │
│   [thumbnail]    │  full-bleed, scaledToFill
│                  │
│ ┌──────────────┐ │  ← instagram badge, top-right
│ │  ig icon     │ │     ultraThinMaterial circle, 12 pt icon
│ └──────────────┘ │
│                  │
│                  │
│ gradient scrim   │  ← warm dark gradient, top 40% → bottom
│                  │
│ @creator         │  ← "@" in AppTheme.accent, name in white, size 10 semibold
└──────────────────┘
```

### Specs

| Property | Value |
|---|---|
| Size | 90 × 130 pt (portrait) |
| Corner radius | 14 |
| Thumbnail | `AsyncImage`, `scaledToFill`, clipped |
| Gradient scrim | `AppTheme.textPrimary`-based warm dark → clear, starts at 40% |
| Creator label | `@` in `AppTheme.accent`, handle in `.white`, size 10 semibold, 8pt leading padding, 9pt bottom |
| Instagram badge | `Image("instagram-logo")` 12 pt, 5pt padding, `ultraThinMaterial` circle, 7pt from top-right corner |
| Press animation | Spring scale to 0.94, response 0.22s, damping 0.65 via custom `ButtonStyle` |
| Placeholder | `AppTheme.surfaceSecondary` + layered circles + `movieclapper` icon |
| Border | `AppTheme.border`, 1pt |

### Tap action

`UIApplication.shared.open(url)` — guard against nil URL; no `openFailed` state needed since the card has no error indicator (compact size makes it impractical).

### Implementation location

`ChatReelCard` and `ReelCardPressStyle` are private structs at the bottom of `ChatView.swift`. No new file needed.

---

## What Does NOT Change

- The "Watch reel" label text and styling — unchanged.
- Card dimensions, thumbnail, creator, caption layout — unchanged.
- `chat_messages` table schema — `sources` is already JSONB; adding a new key requires no migration.
- `InboxReelCard` and `DetailReelCard` — untouched.

---

## Rollout

1. Apply Supabase migration (`supabase db push`)
2. Deploy backend (Render auto-deploys on push to main)
3. Release iOS build

Old messages stored in `chat_messages.sources` without `url` will decode `url` as `nil` and the card will render without a tap action — safe fallback.
