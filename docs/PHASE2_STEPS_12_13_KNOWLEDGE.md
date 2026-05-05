# ReelMind — Phase 2 Steps 12 & 13 Knowledge Document

### The Share Extension: How a User Saves a Reel

*Written so anyone — Swift expert or otherwise — can pick up this code and understand exactly what happens when a user taps "Share → ReelMind" in Instagram.*

---

## The Big Picture

When a user is watching a reel inside Instagram and taps the system share sheet, our **Share Extension** is one of the apps that appears. The user taps "ReelMind" and our extension is activated by iOS as a tiny separate process.

Our extension has **one job, executed in under a second**:

1. Show a polite "Saving..." spinner so the user knows something is happening
2. Pull the reel URL out of whatever Instagram handed us
3. Drop a copy of the URL into a shared container so the main app can recover it later
4. Fire a `POST /api/v1/reels` to the backend so processing can start immediately
5. Get out of the way

**Crucially: the extension does NOT wait for the backend response.** It dismisses immediately. All the heavy work (downloading the video, transcribing, classifying) happens asynchronously on the backend. By the time the user gets a push notification saying "Saved to Skincare", our extension has long since vanished.

Steps 12 and 13 of the build plan together implement this entire flow.

| Step | What it covers |
|---|---|
| **12 (Swift)** | Build Share Extension capture flow — the UI + URL extraction + App Group write |
| **13 (Swift)** | POST URL to backend on share — the network call + immediate dismiss |

We implemented both in the same files because they're really one continuous flow. Splitting them across separate files would have been an artificial seam.

---

## Why a Share Extension at All?

This is worth understanding before reading any code.

A "Share Extension" is one of Apple's **App Extension** types. From the user's perspective, it's the icon that appears in the iOS share sheet alongside Messages, Mail, AirDrop, etc. From the developer's perspective, it's a separate executable bundled inside your app.

Why separate? Because Instagram (the host app) is what's running when the user taps share. Apple cannot launch your full app, hand it the URL, and let it process — that would be slow and disorienting. Instead, iOS runs a tiny sandboxed version of your code (the extension) **inside Instagram's process space**, with a strict memory budget and a strict time budget.

This has two practical consequences for us:

1. **The Share Extension is a different target than the main app.** It's a separate Swift module, with its own `Info.plist`, its own bundle ID, its own entitlements. It cannot import code from the main app unless we deliberately share it (e.g. via a framework).
2. **The extension cannot directly talk to the main app at runtime.** They're separate processes. The only way to communicate is via a *shared container* — a folder both processes can read and write. Apple's mechanism for this is **App Groups**.

Both of these consequences shape the code we wrote.

---

## Prerequisite: App Groups (Step 3)

This is **the one manual thing the user must do in Xcode** that no amount of code can do for them.

In `Signing & Capabilities` for **both** targets:
- Main app target: `ReelMind`
- Extension target: `URL Sharing module`

…the developer must enable the **App Groups** capability and add a group identifier:

```
group.com.reelmind.app
```

This must be **byte-identical** on both targets. If they differ — even by one character — `UserDefaults(suiteName:)` returns `nil` and our code silently does nothing. There is no error, no crash, no log line. It just doesn't work.

The string `"group.com.reelmind.app"` is hard-coded in `ShareViewController.swift` as `K.appGroupID`. If the actual group ID in Xcode differs, **change the constant to match** — don't try to change Xcode to match the constant, because the entitlement system is what gates access to the shared container.

---

## File Inventory

Two Swift files inside `URL Sharing module/`:

```
URL Sharing module/
├── ShareViewController.swift   ← entry point; iOS instantiates this
├── SavingView.swift            ← the SwiftUI "Saving..." UI
├── Info.plist                  ← extension config (unchanged)
└── Base.lproj/
    └── MainInterface.storyboard ← references ShareViewController by name
```

A note on the storyboard: it already existed when we started, and it references `ShareViewController` as the initial view controller's `customClass`. We deliberately **kept** the storyboard rather than switching to `NSExtensionPrincipalClass`, because:

- The storyboard has `customModuleProvider="target"`, which means it auto-resolves the class from the extension's own module — no module-name string to maintain.
- The storyboard's view has a transparent background (`alpha=0`), which we override in `viewDidLoad` with `view.backgroundColor = .systemBackground`. This was a one-line fix vs. modifying the storyboard XML.

So the boot sequence is:
1. iOS reads `Info.plist` → sees `NSExtensionMainStoryboard = MainInterface`
2. Loads `MainInterface.storyboard` → finds initial view controller with `customClass="ShareViewController"`
3. Looks up `ShareViewController` in our module
4. Instantiates it and calls `viewDidLoad`

No magic, just Apple's standard storyboard plumbing.

---

## Walkthrough: `ShareViewController.swift`

The whole file is ~150 lines. Let's go through it in execution order.

### The constants block

```swift
private enum K {
    static let appGroupID = "group.com.reelmind.app"
    static let backendBaseURL = "https://reelmind-api.onrender.com"
    static let pendingURLsKey = "pendingReelURLs"
    static let authTokenKey = "supabaseAuthToken"
    static let dismissDelay: TimeInterval = 0.8
}
```

Five things, all worth understanding:

| Constant | Purpose |
|---|---|
| `appGroupID` | The shared-container identifier. Must match the Xcode entitlement on both targets exactly. |
| `backendBaseURL` | Production backend URL. The service name `reelmind-api` comes from `render.yaml` (see Steps 14-15 doc). For local dev you'd swap this for `http://<your-ngrok-url>` or similar. |
| `pendingURLsKey` | The `UserDefaults` key under which we store an array of unsent URLs as a backup queue (see "App Group Persistence" below). |
| `authTokenKey` | Where we expect the main app to have stashed the user's Supabase JWT after login. The extension can't run a login flow — it relies on the main app to write this token first. |
| `dismissDelay` | We wait 0.8 s before calling `completeRequest`. Two reasons: (a) gives the user enough time to read the "Saving..." message so the experience doesn't feel jarring, and (b) gives `URLSession` enough time to actually flush bytes onto the network before the extension is killed. |

### `viewDidLoad`

```swift
override func viewDidLoad() {
    super.viewDidLoad()
    embedSavingUI()
    extractAndHandleURL()
}
```

Two operations, both kicked off the moment the view loads. We don't wait for `viewDidAppear` — that would add ~50ms latency for no benefit, since the extension's view is presented modally and animates in regardless.

### `embedSavingUI()` — the SwiftUI host

This is the only piece of UIKit-to-SwiftUI bridging in the file:

```swift
let host = UIHostingController(rootView: SavingView())
addChild(host)
host.view.frame = view.bounds
host.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
view.addSubview(host.view)
host.didMove(toParent: self)
```

We use `UIHostingController` (not `NSHostingController`, that's macOS) to wrap a SwiftUI view inside a UIKit view controller. The container parent-child dance (`addChild`, `didMove(toParent:)`) is required by UIKit's view-controller hierarchy rules — without it, lifecycle events don't propagate correctly.

`autoresizingMask` is the old-school equivalent of pinning all four edges. We use it instead of Auto Layout because (a) it's one line, and (b) the hosting view's intrinsic content size is its full bounds anyway, so layout constraints would be overkill.

### `extractAndHandleURL()` — the heart of Step 12

This is where we pull the URL out of whatever Instagram (or any other app) handed us. iOS gives us this through `extensionContext?.inputItems`, which is an `[NSExtensionItem]`. Each item has `attachments`, which is an `[NSItemProvider]`. Each provider can vend data of one or more types (UTIs).

**What does Instagram actually share?** In our testing:
- Most reels arrive as `public.url` (a `URL` object)
- Occasionally as `public.plain-text` (a `String` containing the URL)

We handle both, with `public.url` preferred because it's already typed:

```swift
if provider.hasItemConformingToTypeIdentifier(UTType.url.identifier) {
    group.enter()
    provider.loadItem(forTypeIdentifier: UTType.url.identifier) { data, _ in
        if let url = data as? URL { extracted = url }
        group.leave()
    }
    break outer
}
```

A few things worth noting:

- **`loadItem(forTypeIdentifier:)` is asynchronous.** It calls back on a background queue. That's why we use a `DispatchGroup` — to wait for the callback before proceeding.
- **`break outer` is intentional.** The `outer:` label on the loop lets us bail out the moment we find a single URL. We don't process multiple attachments — just the first usable one.
- **`extracted` is captured weakly via the dispatch group's `notify(queue: .main)` block**, ensuring we hop back to the main thread before touching UI or `extensionContext`.

If neither type matches, we just call `finish()` to dismiss empty-handed. No error UI — there's nothing the user could do anyway, and showing an error after they tapped share would be hostile.

### `handleURL(_:)` — the bridge between Step 12 and Step 13

Once we have a URL, three things happen, in this order:

```swift
private func handleURL(_ url: URL) {
    writeURLToAppGroup(url)                                         // Step 12
    postURLToBackend(url: url, authToken: readAuthToken())          // Step 13

    DispatchQueue.main.asyncAfter(deadline: .now() + K.dismissDelay) {
        [weak self] in self?.finish()
    }
}
```

The order matters:

1. **Write to App Group first.** This is synchronous and durable. Even if the extension is killed mid-network-call, the URL is safely persisted. The main app drains this queue on next launch as a safety net (see below).
2. **Fire the POST.** Asynchronous, fire-and-forget. We don't even hold a reference to the data task — once `.resume()` is called, `URLSession` retains it internally for the duration of the request.
3. **Schedule the dismiss.** 0.8 seconds later, we call `extensionContext?.completeRequest(...)`, which tells iOS we're done.

### `writeURLToAppGroup(_:)` — Step 12 finale

```swift
private func writeURLToAppGroup(_ url: URL) {
    guard let defaults = UserDefaults(suiteName: K.appGroupID) else { return }
    var queue = defaults.stringArray(forKey: K.pendingURLsKey) ?? []
    let str = url.absoluteString
    if !queue.contains(str) { queue.append(str) }
    defaults.set(queue, forKey: K.pendingURLsKey)
}
```

Why a queue (an array of strings) rather than just one URL?

Imagine the user shares three reels in rapid succession before opening the main app. Without a queue, each call would overwrite the previous URL — losing two of the three. With an array, all three accumulate, and the main app can drain them all on next launch.

The `if !queue.contains(str)` check is cheap dedup — if the user shares the same reel twice in a row (a real thing that happens), we don't need two copies. The backend has a stronger duplicate guard at the database level (UNIQUE constraint on `(user_id, url)`), so this is just a nicety, not a correctness requirement.

`UserDefaults.synchronize()` is **not** called. It's a no-op since iOS 12 — Apple deprecated the explicit sync call because the OS now handles it automatically. Some old tutorials still call it, but it does nothing.

### `postURLToBackend(...)` — Step 13

```swift
var request = URLRequest(url: apiURL)
request.httpMethod = "POST"
request.setValue("application/json", forHTTPHeaderField: "Content-Type")
request.setValue("Bearer \(authToken)", forHTTPHeaderField: "Authorization")
request.timeoutInterval = 10

request.httpBody = try? JSONSerialization.data(
    withJSONObject: ["url": url.absoluteString]
)

URLSession.shared.dataTask(with: request) { _, _, _ in }.resume()
```

A few intentional choices:

- **`Bearer \(authToken)`** — the token is whatever the main app stored after the user logged in via Supabase Auth. If the user has never logged in, `authToken` is `""` and we send `"Bearer "` as the header value. The backend will reject this with 401 (see Steps 14-15 doc). That's the correct behavior — if the user isn't logged in, the save shouldn't succeed.
- **`timeoutInterval = 10`** — generous but bounded. We don't want a stuck request keeping the URLSession task alive in the background.
- **`JSONSerialization` over `JSONEncoder`** — using a `Codable` struct here would mean defining a `RequestBody` type for one field. `JSONSerialization` with a dictionary literal is shorter and equally type-safe in this case.
- **The completion handler ignores everything: `{ _, _, _ in }`** — fire-and-forget. The extension is going to be torn down in 0.8s anyway, so we have nothing useful to do with the response. If the server is down or returns 500, the URL is still safely in the App Group queue, and the main app will retry from there.

### `finish()` — saying goodbye to iOS

```swift
private func finish() {
    extensionContext?.completeRequest(returningItems: [], completionHandler: nil)
}
```

This is the magic call that tells iOS "we're done, please dismiss our UI." The `returningItems: []` is for extensions that hand modified content back to the host app (e.g. Markup on a photo); we have nothing to return. iOS will animate our view away and reactivate Instagram.

---

## Walkthrough: `SavingView.swift`

This is a 20-line SwiftUI view. Nothing clever:

```swift
struct SavingView: View {
    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "bookmark.fill")
                .font(.system(size: 40))
                .foregroundColor(.purple)

            ProgressView()
                .scaleEffect(1.3)

            Text("Saving to ReelMind...")
                .font(.headline)

            Text("You can leave this screen")
                .font(.subheadline)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(.systemBackground))
    }
}
```

The `"You can leave this screen"` subtitle is deliberate UX. Without it, users will sit and watch the spinner, expecting it to "complete." Telling them they can leave makes the 0.8-second wait feel intentional rather than a hang.

`Color(.systemBackground)` adapts automatically to dark mode — `.white` would have been a bug.

---

## The Two-Tier Reliability Story

There's a subtle but important architectural decision baked into Steps 12 & 13: **the URL is written to the App Group before the network call, not after.**

This creates a two-tier delivery mechanism:

| Tier | Mechanism | Failure mode |
|---|---|---|
| **Fast path** | `POST /api/v1/reels` directly from the extension | Network down, server down, auth expired |
| **Slow path (safety net)** | App Group queue → main app drains on launch | Only fails if device storage is corrupt |

If the fast path succeeds, the slow path is redundant — the main app on next launch sees the URL in the queue, asks the backend "do you already know about this?", gets a 409 Conflict (see Step 14), and quietly discards the queue entry. No duplicate processing.

If the fast path fails, the slow path saves us. The user shared a reel, we wrote it to App Group, and even though the POST went into the void, the next time they open the main app it'll pick up the queue and retry the POST.

This pattern — **persist locally before attempting the network call** — is one of the most important reliability patterns for share extensions. It's the iOS equivalent of an outbox pattern in distributed systems.

**Note:** the "main app drains the App Group queue" code is *not yet implemented* — it's listed as Phase 3 work because the main app's launch flow doesn't exist yet. But the data is ready and waiting whenever that code is written.

---

## Why Fire-and-Forget Instead of Awaiting?

A common alternative design would be: **await the POST response, show success/error UI based on the result, then dismiss.**

We deliberately did not do this. Reasons:

1. **The user has already moved on mentally.** They're watching reels — they don't want to babysit a "Saving..." spinner for 3 seconds. The dismiss should be near-instant.
2. **Network latency is unpredictable.** A 4G connection in a basement could take 8+ seconds for a single POST. Waiting that long inside a Share Extension violates Apple's HIG and may cause iOS to kill us anyway.
3. **The extension has limited memory.** The shorter it lives, the less risk of an OOM kill. Fire-and-forget keeps the extension lifetime tight.
4. **The actual work happens server-side.** Even if our POST succeeded synchronously, all we'd be confirming is "the URL was queued." The user doesn't really care about that — they care that the reel ends up in their library, and that's a push notification that comes minutes later (Step 22).

So: silent dismiss, with a push notification later carrying the real success signal.

---

## Edge Cases We Handle

| Scenario | Behavior |
|---|---|
| Instagram shares as `public.url` | ✅ Direct extraction |
| Instagram shares as `public.plain-text` containing a URL | ✅ Fallback path |
| User shares from a non-Instagram app | ✅ Same code path — we accept any URL. Backend will fail later if it can't be processed, and that's fine. |
| User shares the same reel twice rapidly | ✅ App Group dedup (in-array check) + backend UNIQUE constraint (Step 14) |
| User shares before logging in | ✅ POST goes out with empty `Bearer` token, backend rejects 401, App Group queue still holds the URL for retry |
| User shares with no internet | ✅ POST silently fails, App Group queue holds the URL for the main app to retry |
| User shares 10 reels back-to-back | ✅ Each invocation appends to the queue — none are lost |
| Instagram shares neither URL nor text | ⚠️ Extension dismisses with no action. No error UI. |

---

## What's NOT Done Here (for clarity)

These are explicitly *not* part of Steps 12 & 13 and live in later phases:

- **Reading auth token from Keychain.** Right now we read from App Group `UserDefaults`. The plan (Step 25) is for the main app to log in via Supabase Auth, store the JWT in Keychain, and *also* mirror it into App Group `UserDefaults` so the extension can read it. The mirror is necessary because Keychain access groups require additional entitlement setup that we haven't done yet.
- **Draining the App Group queue.** As noted above, this is Phase 3 main-app work.
- **Showing success/failure UI inside the extension.** The plan calls for a single push notification (Step 22) instead.
- **Restricting the activation rule.** Right now `Info.plist` uses `TRUEPREDICATE` — the extension shows up for *any* shared content. Eventually we should restrict to URL-bearing items only, but it's harmless during development and makes testing easier.

---

## How to Verify This Code Works

A minimal smoke test:

1. **Configure App Groups in Xcode** (the manual step).
2. **In the main app** (or temporarily in any test code), write a fake auth token:
   ```swift
   UserDefaults(suiteName: "group.com.reelmind.app")?
       .set("test-token", forKey: "supabaseAuthToken")
   ```
3. **Run the extension** by Cmd-clicking the `URL Sharing module` scheme and selecting Instagram (or Safari) as the host.
4. **Share any URL** from the host app to ReelMind.
5. **Verify**:
   - The "Saving..." UI appears for ~0.8 s and dismisses
   - The URL ends up in the App Group queue:
     ```swift
     UserDefaults(suiteName: "group.com.reelmind.app")?
         .stringArray(forKey: "pendingReelURLs")  // should contain the URL
     ```
   - The backend logs show a `POST /api/v1/reels` arrived (will 401 with the fake token, but the request reaches the server — that's what we're verifying)

---

## Key Design Decisions Summary

| Decision | What we chose | Why |
|---|---|---|
| Communication: extension ↔ main app | App Group `UserDefaults` queue | Standard Apple pattern, no extra entitlements beyond App Groups |
| Persist before POST | Yes | Reliability — survives network failures and process kills |
| Wait for POST response? | No (fire-and-forget) | Latency, memory, UX — user doesn't need to watch the spinner |
| UI framework inside extension | SwiftUI via `UIHostingController` | Consistent with main app; trivial to maintain |
| Dismiss delay | 0.8 s | Long enough to read "Saving...", short enough to feel snappy, long enough for `URLSession` to flush bytes |
| Dedup at extension level | In-array check in App Group write | Cheap; defensive layer above DB UNIQUE constraint |
| Activation rule | `TRUEPREDICATE` (accept all) | Easier dev/test; can tighten later |
| Backend URL | Hard-coded constant | One change point if Render service moves; environment-specific URL switching is Phase 3+ |

---

*ReelMind Phase 2 Knowledge Doc — Steps 12 & 13 — v1.0*
