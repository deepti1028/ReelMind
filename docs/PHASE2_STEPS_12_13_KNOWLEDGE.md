# ReelMind — Phase 2 Steps 12 & 13 Knowledge Document

### The Share Extension: How a User Saves a Reel

*Written so anyone — Swift expert or otherwise — can pick up this code and understand exactly what happens when a user taps "Share → ReelMind" in Instagram.*

---

## The Big Picture

When a user is watching a reel inside Instagram and taps the system share sheet, our **Share Extension** is one of the apps that appears. The user taps "ReelMind" and our extension is activated by iOS as a tiny separate process.

Our extension has **one job, executed in 1.7 seconds**:

1. Slide a polished bottom sheet up from the bottom of the screen
2. Show a progress ring filling + "Saving..." text for 0.8s
3. Cross-fade to a checkmark + "Saved!" celebration
4. Slide the sheet back down and dismiss

The host app (Instagram) remains fully visible behind the sheet — no dim layer, no overlay. The view controller's view is `.clear` so iOS's natural extension presentation chrome is the only thing between the host and our sheet.

Behind the scenes during those 1.7s:
- Pull the reel URL out of whatever Instagram handed us
- Drop a copy of the URL into the App Group queue (so the main app can recover it)
- Fire `POST /api/v1/reels` to the backend (fire-and-forget)

**Crucially: the extension does NOT wait for the backend response.** All the heavy work (downloading the video, transcribing, classifying) happens asynchronously on the backend. By the time the user gets a push notification saying "Saved to Skincare", our extension has long since vanished.

| Step | What it covers |
|---|---|
| **12 (Swift)** | Build Share Extension capture flow — the UI + URL extraction + App Group write |
| **13 (Swift)** | POST URL to backend on share — the network call + auto dismiss |

We implemented both in the same file (`ShareViewController.swift`).

---

## Why a Share Extension at All?

A "Share Extension" is one of Apple's **App Extension** types. It's a separate executable bundled inside your app, run by iOS inside the host app's process space with strict memory and time budgets.

Two practical consequences:

1. **The Share Extension is a different target than the main app** — separate Swift module, own `Info.plist`, own bundle ID, own entitlements.
2. **The extension cannot directly talk to the main app at runtime** — they're separate processes. Communication happens via a *shared container* (App Groups).

---

## Prerequisite: App Groups

In `Signing & Capabilities` for **both** targets (`ReelMind` main app + `URL Sharing module` extension), enable the **App Groups** capability with identifier:

```
group.com.deepti.ReelMind
```

This must be byte-identical on both targets. Mismatch → `UserDefaults(suiteName:)` returns `nil` and writes silently fail. The constant `K.appGroupID` in `ShareViewController.swift` must match the entitlement.

---

## File Inventory

```
URL Sharing module/
├── ShareViewController.swift         ← entry point + UI + URL extraction + POST
├── Info.plist                        ← extension config (URL-only activation rule)
├── URL Sharing module.entitlements   ← App Groups entitlement
├── Assets.xcassets/                  ← AppIcon for the share sheet
└── Base.lproj/
    └── MainInterface.storyboard      ← references ShareViewController by name
```

The storyboard's view has a transparent background and references `ShareViewController` as the initial view controller's `customClass`. We set `view.backgroundColor = .clear` in `viewDidLoad` so only our two visual elements (backdrop + bottom sheet) are seen.

---

## The UI: Just a Bottom Sheet

A single visual element — the bottom sheet. No backdrop, no overlay. Host app (e.g. Instagram) stays fully visible behind. The view's background is `.clear` so iOS's natural chrome is whatever's above the sheet.

### Bottom Sheet specs

- Anchored to the bottom of the screen
- Height: **55% of screen** (was 40% — increased by 15 percentage points per spec)
- Background: `#1a1a1a` (near-black) — currently overridden to green for visual debugging
- Top corners rounded (20pt radius), bottom flush with screen edge
- Drop shadow above the sheet for depth
- Drag handle (36×4pt, `#444`) at the top — purely visual; no actual drag gesture wired up

### Making the host app visible behind the sheet

By default, iOS wraps a share extension's view inside chrome that has an opaque background — a white/grey rectangle that hides the host app entirely. Setting our own `view.backgroundColor = .clear` is necessary but not sufficient; the chrome's parent views are still opaque.

The fix is a **view-hierarchy transparency walk**: in `viewWillAppear`, we traverse up from `self.view` to the root and set every ancestor's `backgroundColor = .clear`. This is a known share-extension trick — it works on most iOS versions. Implementation:

```swift
private func clearAncestorBackgrounds() {
    var ancestor: UIView? = view
    while let v = ancestor {
        v.backgroundColor = .clear
        ancestor = v.superview
    }
}
```

**Caveat:** in the iOS Simulator with no real host app providing content, you'll still see white/grey because there's nothing to show through. To see the host content (e.g. an Instagram reel) behind the sheet, you have to test from an actual app sharing into ReelMind, ideally on a real device.

### Two states inside the sheet, swapped during the animation

| State | Duration | Contents |
|---|---|---|
| Saving | 0.0–0.8s | Circular progress ring (56×56pt, white over `#333` track) + "Saving..." (14pt semibold white) + "Reel added to ReelMind" (12pt `#999`) |
| Saved | 0.8s onwards | White circle (72×72pt) with black ✓ checkmark + "Saved!" (17pt bold) + "Reel added to your library" (12pt `#999`) |

Both containers share the same center constraints inside the sheet — they overlap visually, and we cross-fade between them via alpha.

**Initial alpha values are set at property declaration, not in `viewDidLoad`:**

```swift
private let savingContainer: UIView = {
    let v = UIView()
    v.alpha = 1   // visible from frame zero
    return v
}()

private let savedContainer: UIView = {
    let v = UIView()
    v.alpha = 0   // hidden from frame zero — never flashes alongside saving
    return v
}()
```

This was a real bug: previously `savedContainer.alpha = 0` was set in `viewDidAppear`, which fires *after* the view is first rendered. That meant for one frame the user saw both the saving subtitle ("Reel added to ReelMind") and the saved subtitle ("Reel added to your library") stacked on top of each other. Setting alpha at construction prevents the flash.

---

## Animation Timeline

| Time | What happens | How it's done |
|---|---|---|
| 0.0s | Sheet slides up | `UIView.animate` with `usingSpringWithDamping: 0.75` (cubic-bezier overshoot equivalent) |
| 0.0–0.8s | Progress ring fills | `CABasicAnimation` on `strokeEnd` of `CAShapeLayer`, ease-out |
| 0.8s | Saving content fades out | 0.2s alpha animation |
| 0.8s | Checkmark pops in | Spring `damping: 0.55` (gives 0→1.1→1 overshoot bounce) |
| 1.0s | "Saved!" title fades in | 0.4s with 0.2s delay |
| 1.1s | Subtitle fades in | 0.4s with 0.3s delay |
| 1.5s | `completeRequest()` | Hands off to iOS — chrome + sheet animate out together in a single smooth dismissal. No manual slide-down. |

**Important: the off-screen positioning happens in `viewDidLoad`, not `viewDidAppear`.** This was a bug we hit: setting the off-screen transform in `viewDidAppear` runs *after* the view's first frame is rendered, so the user briefly sees the sheet in its final position before it jumps off-screen and animates back. The fix is to apply the off-screen transform immediately in `viewDidLoad` using a hardcoded large offset (1500pt — guaranteed off-screen on any device, since we may not have accurate bounds at this point in the lifecycle).

**Equally important: the slide-up animation always starts in `viewWillAppear`, never `viewDidAppear`.** On real devices, iOS's share-extension chrome presentation takes ~0.5s. `viewDidAppear` only fires *after* that completes. If we kicked off the slide-up there, the user would see iOS's chrome appear, sit empty for half a second, and only then see our sheet slide up — a perceptible two-step entry.

The fix has two strategies, both starting in `viewWillAppear`:

1. **Preferred: `transitionCoordinator?.animate(alongsideTransition:)`** — hooks our animation into the same animation block iOS uses for its chrome. Both move in lockstep. Works when iOS exposes the coordinator (some iOS versions / contexts do, some don't).

2. **Fallback: fire the spring animation directly in `viewWillAppear`** — share extensions on most iOS versions don't expose a `transitionCoordinator`. In that case we just kick off `UIView.animate(...)` ourselves. Because `viewWillAppear` fires *during* iOS's chrome presentation (not after, like `viewDidAppear`), our 0.35s spring runs in parallel with the chrome animation. Both arrive in place at roughly the same time.

Either path: the slide-up never waits for `viewDidAppear`. Empirically the fallback is what fires for most users (the warning we used to log "No transitionCoordinator available" was misleading — it implied we'd wait for `viewDidAppear`, which we now never do).

The animation only runs if URL extraction succeeds. If extraction fails (rare — iOS only activates us when there's a URL), we dismiss immediately without animation rather than show a fake "Saved!".

---

## Walkthrough: `ShareViewController.swift`

### The Logger

A small `Log` enum produces colorful, leveled logs visible in Xcode's debug console when running the extension scheme:

```swift
private enum Log {
    static func debug(_:)   // 🔍 [DEBUG]
    static func info(_:)    // ℹ️  [INFO]
    static func warn(_:)    // ⚠️  [WARN]
    static func error(_:)   // ❌ [ERROR]
    static func success(_:) // ✅ [SUCCESS]
    static func event(_:)   // 🎬 [EVENT]    — lifecycle milestones
    static func net(_:)     // 🌐 [NET]      — network activity
}
```

Logs are sprinkled throughout: viewDidLoad/viewDidAppear, attachment loading, App Group writes, auth token reads, network request/response (with status, latency, body preview), and dismiss. Read the console while debugging to see the entire flow narrate itself.

### Constants

```swift
private enum K {
    static let appGroupID = "group.com.deepti.ReelMind"
    static let backendBaseURL = "https://reelmind-api.onrender.com"
    static let pendingURLsKey = "pendingReelURLs"
    static let authTokenKey = "supabaseAuthToken"

    static let sheetHeightRatio: CGFloat = 0.55
    static let backdropAlpha: CGFloat = 0.4

    static let slideUpDuration: TimeInterval = 0.4
    static let slideDownDuration: TimeInterval = 0.4
    static let progressFillDuration: TimeInterval = 0.8
    static let savingToSavedAt: TimeInterval = 0.8
    static let slideDownAt: TimeInterval = 1.3
    static let dismissAt: TimeInterval = 1.7
}
```

### `viewDidLoad`

Sets `view.backgroundColor = .clear` (transparent — only backdrop and sheet are visible), builds the UI hierarchy in z-order: backdrop → bottom sheet → drag handle → saving container → saved container.

### `viewDidAppear`

- Lays out the view, then translates the bottom sheet off-screen (`y += sheetHeight + 50`) — this is the starting state for the slide-up animation
- Calls `extractAndHandleURL()` — the work begins

### `extractAndHandleURL()`

Pulls URLs out of `extensionContext.inputItems`. Each item has `attachments`, which are `NSItemProvider` instances. We try `public.url` first, fall back to `public.plain-text`.

- `loadItem(forTypeIdentifier:)` is async — we use a `DispatchGroup` to wait for the callback before proceeding
- `break outer` bails out the moment we find one usable attachment
- On `group.notify(queue: .main)`:
  - URL found → `handleURL(url)` does the work + `runFullAnimation()` plays the visual flow
  - No URL → `finish()` immediately (no animation, honest dismiss)

### `handleURL(_:)`

Two synchronous, fast actions:
1. `writeURLToAppGroup(url)` — append to the App Group queue, dedup if already present
2. `postURLToBackend(url:authToken:)` — fire-and-forget HTTPS POST

Once these are kicked off, the visual animation starts.

### `writeURLToAppGroup(_:)` & `readAuthToken()`

App Group `UserDefaults` reads/writes. The `if !queue.contains` check dedups within the queue.

**⚠️ Honest caveat:** The "main app drains the queue on next launch" logic is **not yet implemented**. Today, the queue is a write-only scaffold. If the network POST fails, the URL is effectively lost.

### `postURLToBackend(...)`

Standard `URLSession.dataTask`, with rich logging around it:

```swift
Log.net("➡️  POST \(apiURL.absoluteString)")
Log.net("    Headers: Content-Type=application/json, Authorization=Bearer ...")
Log.net("    Body: [\"url\": \"...\"]")

let startTime = Date()
URLSession.shared.dataTask(with: request) { data, response, error in
    let elapsed = String(format: "%.0f", Date().timeIntervalSince(startTime) * 1000)
    // logs response status, latency, body preview
}.resume()
```

Status codes get differentiated emoji (✅ 2xx, ⚠️ 4xx, ❌ 5xx). Response bodies are truncated to 500 chars to keep logs readable. Total request latency in ms.

### `runFullAnimation()`

Four phases via `DispatchQueue.main.asyncAfter`:

```swift
// Phase 1: Slide up + backdrop fade in (now)
UIView.animate(... usingSpringWithDamping: 0.75 ...) {
    self.bottomSheet.transform = .identity
    self.backdropView.alpha = K.backdropAlpha
}

// Progress ring fill (now → 0.8s)
CABasicAnimation(keyPath: "strokeEnd")  fromValue: 0  toValue: 1

// Phase 2: Cross-fade to saved state (at 0.8s)
DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) { transitionToSavedState() }

// Phase 3: Slide down + backdrop fade out (at 1.3s)
DispatchQueue.main.asyncAfter(deadline: .now() + 1.3) { runExitAnimation() }

// Phase 4: Dismiss (at 1.7s)
DispatchQueue.main.asyncAfter(deadline: .now() + 1.7) { finish() }
```

### `transitionToSavedState()`

- Fades saving content out (alpha → 0, 0.2s)
- Reveals saved container (alpha → 1)
- Pops the checkmark in: starts at scale 0.001, springs to identity with `damping: 0.55`
- Fades title in at 0.2s delay, subtitle at 0.3s delay (staggered like CSS keyframes)

### `runExitAnimation()`

```swift
clearAncestorBackgrounds()  // defensive: iOS may have reset them mid-lifecycle

UIView.animate(withDuration: 0.4, delay: 0, options: .curveEaseIn) {
    self.bottomSheet.transform = CGAffineTransform(translationX: 0, y: ...) // off-screen
    self.bottomSheet.alpha = 0  // cross-fade to mask any "white reveal" seam
}
```

Two important details here:

1. **`clearAncestorBackgrounds()` is called again at exit.** The same hack we run in `viewWillAppear` — iOS sometimes resets ancestor view backgrounds during state transitions, which would cause the area vacated by the sheet to flash white during the slide-down.

2. **Sheet alpha fades to 0 alongside the slide-down.** Without this, you see a gap between our slide-down ending and iOS's own dismiss animation taking over — the empty area where the sheet was briefly shows iOS's white/grey chrome (or simulator background). Cross-fading the sheet hides that seam.

### `finish()`

`extensionContext?.completeRequest(returningItems: [], completionHandler: nil)`

Tells iOS we're done. iOS animates our view away and reactivates Instagram.

---

## The Activation Rule (Info.plist)

```xml
<key>NSExtensionActivationRule</key>
<dict>
    <key>NSExtensionActivationSupportsWebURLWithMaxCount</key>
    <integer>1</integer>
</dict>
```

ReelMind only appears in the share sheet when exactly one web URL is being shared.

A future enhancement (in backlog): restrict to **Instagram only** by filtering on host app bundle ID.

---

## Edge Cases

| Scenario | Behavior |
|---|---|
| Instagram shares as `public.url` | ✅ Direct extraction |
| Shares as `public.plain-text` containing a URL | ✅ Fallback path |
| Non-Instagram app sharing a URL | ✅ Same code path |
| Same reel shared twice rapidly | ✅ App Group dedup + backend UNIQUE constraint |
| Shared before logging in | ✅ POST goes out with empty bearer token, backend rejects 401 |
| Shared with no internet | ⚠️ POST silently fails; URL is in App Group queue but no drain logic yet |
| 10 reels shared back-to-back | ✅ Each invocation appends to the queue |
| No URL in attachments (rare) | ✅ Dismiss immediately, no fake "Saved!" |

---

## What's NOT Done Here

- **Reading auth token from Keychain** — Step 25; for now App Group `UserDefaults` only
- **Draining the App Group queue** — main app launch flow doesn't exist yet
- **Restricting activation to Instagram only** — backlog item
- **Error UI when no URL is found** — currently silent dismiss; backlog
- **Drag-to-dismiss on the bottom sheet** — drag handle is purely visual

---

## How to Verify

1. Configure App Groups in Xcode for both `ReelMind` and `URL Sharing module` targets with `group.com.deepti.ReelMind`
2. Optionally seed a fake auth token in the main app:
   ```swift
   UserDefaults(suiteName: "group.com.deepti.ReelMind")?
       .set("test-token", forKey: "supabaseAuthToken")
   ```
3. Run the `URL Sharing module` scheme; choose Instagram or Safari as the host
4. Share any URL
5. Verify:
   - Backdrop fades in (dim but not blackout)
   - Bottom sheet slides up smoothly, takes ~55% of screen
   - "Saving..." with progress ring for 0.8s
   - Checkmark pops, "Saved!" with subtitle for 0.5s
   - Sheet slides back down, backdrop fades, extension dismisses at ~1.7s
   - Console shows the full narrative — every step logged
   - URL appears in:
     ```swift
     UserDefaults(suiteName: "group.com.deepti.ReelMind")?
         .stringArray(forKey: "pendingReelURLs")
     ```
   - Backend logs show `POST /api/v1/reels` arrived (will 401 with fake token)

---

## Key Design Decisions Summary

| Decision | What we chose | Why |
|---|---|---|
| Communication: extension ↔ main app | App Group `UserDefaults` queue | Standard Apple pattern, minimal entitlements |
| Persist before POST | Yes | Reliability scaffolding (drain logic to come) |
| Wait for POST response? | No (fire-and-forget) | Latency, memory, UX |
| UI framework | Pure UIKit | Simpler than SwiftUI bridging at this scale |
| Backdrop dim layer | None — host app stays visible | User wants no dim |
| Host transparency | Walk view hierarchy in `viewWillAppear`, clear all ancestor backgrounds | iOS chrome is opaque by default; setting only our own view to `.clear` isn't enough |
| Bottom sheet height | 55% of screen | 40% + 15% per design spec; gives room for both states comfortably |
| Off-screen positioning | In `viewDidLoad` (not `viewDidAppear`) | Avoids one-frame flash where the sheet shows in final position before sliding |
| Slide-up timing | `transitionCoordinator.animate(alongsideTransition:)` in `viewWillAppear` | Syncs with iOS's chrome presentation so both arrive together; eliminates the ~0.5s perceptible delay we saw on real devices |
| Slide-down on exit | None — just `completeRequest()`, let iOS handle dismissal | Manual slide-down ahead of iOS's chrome dismissal exposes a "white reveal" gap. Letting iOS animate the chrome and our sheet out together in one motion looks clean. |
| Exit animation | Slide-down + alpha fade simultaneously | Cross-fading hides the seam between our slide-down and iOS's dismiss; without the fade, white briefly shows where the sheet was |
| State alpha defaults | Set at property declaration | Prevents one-frame flash where both states briefly visible |
| Animation total duration | 1.7s | Long enough to read "Saved!", short enough to feel snappy |
| Checkmark animation | Spring damping 0.55 | Bouncy overshoot like CSS `cubic-bezier(0.175, 0.885, 0.32, 1.275)` |
| Activation rule | URL-only | Don't pollute share sheet for non-URL content |
| Logging | Custom emoji-prefixed `Log` enum | Visible in Xcode debug console; easy to follow flow |
| Backend URL | Hard-coded constant | One change point; environment switching is Phase 3+ |

---

*ReelMind Phase 2 Knowledge Doc — Steps 12 & 13 — v1.3 (updated 2026-05-06)*
