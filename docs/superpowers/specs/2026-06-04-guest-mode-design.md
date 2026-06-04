# Guest Mode — App Store 5.1.1(v) Compliance

**Date:** 2026-06-04
**Rejection reason:** Guideline 5.1.1(v) — app required login before accessing any feature.
**Fix:** Let users enter a guest mode that bypasses login. Gate only the chat feature (the account-dependent differentiator) behind sign-in.

---

## Scope

Five changes across four files. No new views created except a chat gate overlay.

---

## 1. AuthSession — guest flag

Add `isGuest: Bool` as a `@Published` property backed by `UserDefaults("isGuestMode")`.

- `enterGuestMode()` — sets flag to `true`, persists to UserDefaults.
- `clearGuestMode()` — sets flag to `false`, removes from UserDefaults.
- Call `clearGuestMode()` inside the existing `authStateChanges` listener on `.signedIn` and `.signedOut` events.

No other changes to `AuthSession`.

---

## 2. RootView — routing

Change the routing condition from:

```
session != nil → ContentView
```

to:

```
session != nil || isGuest → ContentView
```

No other routing changes.

---

## 3. LoginView — guest entry point

Add a plain text link at the very bottom of the scroll content, below the "New here? Create an account" row:

> "Continue without an account →"

Style: `AppTheme.textFaint`, font size 13, centered. Tapping calls `auth.enterGuestMode()`.

---

## 4. CategoryDetailView — chat gate

Inside `CategoryDetailView`, if `auth.session == nil` (guest), show a full-screen overlay instead of the chat UI:

- Icon: `lock.open` or `bubble.left.and.bubble.right`
- Heading: "Sign in to chat with your reels"
- Body: "Chat is powered by your saved reels. Create a free account to get started."
- Two buttons: "Sign In" and "Create Account" — both open `LoginView` as a `.sheet`

Since guests have no categories and therefore can never navigate here naturally, this is a safety net for deep links and future features.

---

## 5. Share extension (ShareViewController) — auth check

At the start of the share flow, before any animation or network call:

1. Read the JWT from App Group UserDefaults (`group.com.reelmind.app` / `supabaseAuthToken` key).
2. **If JWT is present:** proceed exactly as today (POST to backend, animate "Saved!").
3. **If JWT is absent:** skip the `URLSession` POST entirely (Celery is never triggered), then run the existing slide-up animation but replace the "Saved!" label text with **"Sign in to save your reels."**

The animation still plays so the UX feels intentional. The Celery pipeline is never started because the POST never happens.

---

## Data flow — guest sign-in from within the app

1. Guest taps avatar → Settings opens (unchanged).
2. Or guest taps "Sign In / Create Account" in the chat gate overlay → `LoginView` sheet.
3. User authenticates → `authStateChanges` fires `.signedIn` → `clearGuestMode()` called → `isGuest = false`.
4. `RootView` re-evaluates: `session != nil` is now true, `ContentView` stays mounted.
5. `ContentView` gets a new `.onChange(of: auth.session)` modifier that calls `appVM.load()` when session becomes non-nil — because `ContentView` is already mounted for guests, `.task` won't re-fire on sign-in.

---

## What does NOT change

- `LibraryView` empty state — guest sees the identical view an authenticated user with 0 reels sees.
- Avatar button and Settings — no changes, works the same for guests.
- `InboxView` — no changes.
- `AppViewModel.load()` — no changes; Supabase RLS returns empty arrays for unauthenticated requests, `hasLoaded` is set, empty state renders correctly.
- Backend — no changes; the 401 guard already exists but is never reached because the extension skips the POST.

---

## Files changed

| File | Change |
|------|--------|
| `frontend/AuthSession.swift` | Add `isGuest`, `enterGuestMode()`, `clearGuestMode()` |
| `frontend/RootView.swift` | `session != nil \|\| isGuest` routing |
| `frontend/LoginView.swift` | "Continue without an account" link |
| `frontend/ContentView.swift` | `.onChange(of: auth.session)` to reload library on guest sign-in |
| `frontend/Views/CategoryDetailView.swift` | Chat gate overlay for guests |
| `URL Sharing module/ShareViewController.swift` | JWT check before POST + label text change |
