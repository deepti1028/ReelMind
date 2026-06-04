# Guest Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let unauthenticated users enter a guest mode that bypasses login, satisfying App Store guideline 5.1.1(v), with chat as the only hard gate.

**Architecture:** Add an `isGuest` flag to `AuthSession` so `RootView` can route guests into `ContentView`. Guest sees the normal empty-library UI. Chat button in `CategoryDetailView` checks for a session before opening and shows a sign-in sheet if absent. Share extension checks for a JWT before POSTing — absent JWT = skip network call, show "Sign in to save your reels."

**Tech Stack:** SwiftUI, UIKit (share extension), Supabase Auth, App Group UserDefaults

---

## Files Modified

| File | Change |
|------|--------|
| `frontend/AuthSession.swift` | Add `isGuest`, `enterGuestMode()`, `clearGuestMode()` |
| `frontend/RootView.swift` | Route to `ContentView` when `session != nil \|\| isGuest` |
| `frontend/LoginView.swift` | Add "Continue without an account" link |
| `frontend/ContentView.swift` | `.onChange(of: auth.session)` reload on guest sign-in |
| `frontend/Views/CategoryDetailView.swift` | Chat gate sheet for guests |
| `URL Sharing module/ShareViewController.swift` | JWT check, skip POST, change label for guests |

---

### Task 1: AuthSession — guest flag

**Files:**
- Modify: `frontend/AuthSession.swift`

- [ ] **Step 1: Add `isGuest` published property**

  In `AuthSession`, after `@Published var isRecovering = false`, add:

  ```swift
  @Published private(set) var isGuest: Bool = UserDefaults.standard.bool(forKey: "isGuestMode")
  ```

- [ ] **Step 2: Add `enterGuestMode()` and `clearGuestMode()`**

  In the `// MARK: - Auth actions` section, before `func signIn(...)`, add:

  ```swift
  func enterGuestMode() {
      isGuest = true
      UserDefaults.standard.set(true, forKey: "isGuestMode")
  }

  private func clearGuestMode() {
      isGuest = false
      UserDefaults.standard.removeObject(forKey: "isGuestMode")
  }
  ```

- [ ] **Step 3: Clear guest mode on auth state changes**

  In the `authStateChanges` listener inside `bootstrap()`, find the existing `if event == .signedOut` block and update it, then add the `.signedIn` case:

  ```swift
  if event == .signedOut {
      self?.clearGuestMode()
      UserDefaults.standard.removeObject(forKey: "hasCompletedOnboarding")
      UserDefaults.standard.removeObject(forKey: "_onboardingStep")
  }
  if event == .signedIn {
      self?.clearGuestMode()
  }
  ```

- [ ] **Step 4: Commit**

  ```bash
  git add frontend/AuthSession.swift
  git commit -m "feat: add isGuest flag and enterGuestMode/clearGuestMode to AuthSession"
  ```

---

### Task 2: RootView — guest routing

**Files:**
- Modify: `frontend/RootView.swift`

- [ ] **Step 1: Update routing condition**

  Find:
  ```swift
  } else if auth.session != nil {
      ContentView()
  ```

  Replace with:
  ```swift
  } else if auth.session != nil || auth.isGuest {
      ContentView()
  ```

- [ ] **Step 2: Commit**

  ```bash
  git add frontend/RootView.swift
  git commit -m "feat: route guest users to ContentView in RootView"
  ```

---

### Task 3: LoginView — guest entry point

**Files:**
- Modify: `frontend/LoginView.swift`

- [ ] **Step 1: Add "Continue without an account" button**

  Find the `HStack` containing "New here?" and "Create an account" and the `.font(.footnote)` modifier below it:

  ```swift
                  HStack {
                      Spacer()
                      Text("New here?")
                          .foregroundColor(AppTheme.textMuted)
                      Button("Create an account") { showSignup = true }
                          .foregroundColor(AppTheme.accentDark)
                          .fontWeight(.semibold)
                      Spacer()
                  }
                  .font(.footnote)
  ```

  Add immediately after that `.font(.footnote)` line:

  ```swift
                  Button("Continue without an account") { auth.enterGuestMode() }
                      .font(.system(size: 13))
                      .foregroundColor(AppTheme.textFaint)
                      .frame(maxWidth: .infinity)
                      .padding(.top, 16)
  ```

- [ ] **Step 2: Commit**

  ```bash
  git add frontend/LoginView.swift
  git commit -m "feat: add Continue without an account button to LoginView"
  ```

---

### Task 4: ContentView — reload on guest sign-in

**Files:**
- Modify: `frontend/ContentView.swift`

**Why:** `ContentView` is already mounted when a guest signs in via a modal sheet, so `.task` won't re-fire. Without this change the library stays empty even after authentication.

- [ ] **Step 1: Add session change handler**

  Find the existing `.onChange(of: scenePhase)` modifier:

  ```swift
          .onChange(of: scenePhase) { _, phase in
              if phase == .active { Task { await appVM.load(silent: true) } }
          }
  ```

  Add immediately after it:

  ```swift
          .onChange(of: auth.session) { _, newSession in
              if newSession != nil { Task { await appVM.load() } }
          }
  ```

- [ ] **Step 2: Commit**

  ```bash
  git add frontend/ContentView.swift
  git commit -m "feat: reload library in ContentView when guest authenticates"
  ```

---

### Task 5: CategoryDetailView — chat gate for guests

**Files:**
- Modify: `frontend/Views/CategoryDetailView.swift`

**Why:** Chat queries the user's saved reel embeddings — it is inherently account-based. Guests who reach this screen (e.g. via a deep link) must be prompted to sign in before chat opens.

- [ ] **Step 1: Add `showSignInForChat` state**

  In `CategoryDetailView`, after `@State private var showChat = false`, add:

  ```swift
  @State private var showSignInForChat = false
  ```

- [ ] **Step 2: Update `chatButton` to gate on session**

  Find the `chatButton` computed property:

  ```swift
  private var chatButton: some View {
      Button { showChat = true } label: {
  ```

  Replace the action:

  ```swift
  private var chatButton: some View {
      Button {
          if auth.session != nil {
              showChat = true
          } else {
              showSignInForChat = true
          }
      } label: {
  ```

- [ ] **Step 3: Add the guest gate sheet and its view**

  After the existing `.sheet(item: $reelToReassign)` modifier (the last modifier before the closing `}`), add:

  ```swift
          .sheet(isPresented: $showSignInForChat) {
              ChatGuestGateView()
                  .environmentObject(auth)
          }
  ```

  Then, after the closing `}` of `CategoryDetailView` (below the last `// MARK:` sub-view), add the gate view as a private struct in the same file:

  ```swift
  private struct ChatGuestGateView: View {
      @EnvironmentObject private var auth: AuthSession
      @Environment(\.dismiss) private var dismiss
      @State private var showLogin = false

      var body: some View {
          VStack(spacing: 24) {
              Spacer()

              Image(systemName: "bubble.left.and.bubble.right")
                  .font(.system(size: 48))
                  .foregroundColor(AppTheme.accent)

              VStack(spacing: 8) {
                  Text("Sign in to chat with your reels")
                      .font(.system(size: 22, weight: .bold))
                      .foregroundColor(AppTheme.textPrimary)
                      .multilineTextAlignment(.center)
                  Text("Chat is powered by your saved reels. Create a free account to get started.")
                      .font(.system(size: 14))
                      .foregroundColor(AppTheme.textMuted)
                      .multilineTextAlignment(.center)
                      .padding(.horizontal, 32)
              }

              VStack(spacing: 12) {
                  Button(action: { showLogin = true }) {
                      Text("Sign In or Create Account")
                          .font(.system(size: 16, weight: .semibold, design: .serif))
                          .foregroundColor(Color(r: 0xfd, g: 0xf4, b: 0xe3))
                          .frame(maxWidth: .infinity)
                          .frame(height: 52)
                          .background(AppTheme.buttonGradient)
                          .clipShape(RoundedRectangle(cornerRadius: 14))
                          .shadow(color: AppTheme.accentDark.opacity(0.3), radius: 10, x: 0, y: 5)
                  }

                  Button("Not now") { dismiss() }
                      .font(.system(size: 14))
                      .foregroundColor(AppTheme.textFaint)
              }
              .padding(.horizontal, 26)

              Spacer()
          }
          .background(AppTheme.background.ignoresSafeArea())
          .sheet(isPresented: $showLogin) {
              LoginView().environmentObject(auth)
          }
      }
  }
  ```

- [ ] **Step 4: Commit**

  ```bash
  git add "frontend/Views/CategoryDetailView.swift"
  git commit -m "feat: add guest chat gate to CategoryDetailView"
  ```

---

### Task 6: ShareViewController — skip POST for unauthenticated users

**Files:**
- Modify: `URL Sharing module/ShareViewController.swift`

**Why:** Without a JWT the backend returns 401 and the reel is never saved, but the extension currently still fires the POST and always shows "Saved!". Guests get a false success message. Fix: check for the JWT before doing anything network-related; if absent, skip the POST, set a flag, and show "Sign in to save your reels" in the result label.

- [ ] **Step 1: Add `isGuestSave` flag**

  In the `// MARK: - Idempotency flags` section, after `private var saveRejected = false`, add:

  ```swift
  // Set to true when no auth token is present — skips POST and shows sign-in message.
  private var isGuestSave = false
  ```

- [ ] **Step 2: Move auth check to the top of `handleURL` and skip POST + queue write when absent**

  Find the current `handleURL` method:

  ```swift
  private func handleURL(_ url: URL) {
      Log.event("handleURL invoked for: \(url.absoluteString)")
      writeURLToAppGroup(url)
      let token = readAuthToken()
      let autoCategorise = readAutoCategorise()
      postURLToBackend(url: url, authToken: token, autoCategorise: autoCategorise)
  }
  ```

  Replace with:

  ```swift
  private func handleURL(_ url: URL) {
      Log.event("handleURL invoked for: \(url.absoluteString)")
      let token = readAuthToken()
      guard !token.isEmpty else {
          Log.warn("No auth token — guest: skipping POST and queue write")
          isGuestSave = true
          return
      }
      writeURLToAppGroup(url)
      let autoCategorise = readAutoCategorise()
      postURLToBackend(url: url, authToken: token, autoCategorise: autoCategorise)
  }
  ```

- [ ] **Step 3: Add guest case to `applyResultLabels()`**

  Find the current `applyResultLabels()` method:

  ```swift
  private func applyResultLabels() {
      if saveRejected {
          savedTitleLabel.text = rejectTitle
          savedInfoLabel.text = rejectSubtitle
      } else if duplicateSaveDetected {
          savedTitleLabel.text = "Already saved"
          savedInfoLabel.text = "Check your ReelMind library"
      } else {
          savedTitleLabel.text = "Saved!"
          savedInfoLabel.text = "Reel added to ReelMind"
      }
  }
  ```

  Replace with:

  ```swift
  private func applyResultLabels() {
      if isGuestSave {
          savedTitleLabel.text = "Sign in to save your reels"
          savedInfoLabel.text = "Open ReelMind to create an account"
      } else if saveRejected {
          savedTitleLabel.text = rejectTitle
          savedInfoLabel.text = rejectSubtitle
      } else if duplicateSaveDetected {
          savedTitleLabel.text = "Already saved"
          savedInfoLabel.text = "Check your ReelMind library"
      } else {
          savedTitleLabel.text = "Saved!"
          savedInfoLabel.text = "Reel added to ReelMind"
      }
  }
  ```

- [ ] **Step 4: Commit**

  ```bash
  git add "URL Sharing module/ShareViewController.swift"
  git commit -m "feat: skip POST and show sign-in message in share extension for unauthenticated users"
  ```

---

## Manual Verification Checklist

After all tasks are complete, verify in the iOS simulator or device:

- [ ] **Guest entry:** Fresh launch → complete onboarding → `LoginView` shows "Continue without an account" at the bottom → tapping it lands on `LibraryView` showing the normal empty-library state (sparkles, how-to steps)
- [ ] **Guest settings:** Avatar button → Settings opens normally (same as authenticated)
- [ ] **Guest → sign in:** From any sign-in entry point (Settings, chat gate) → authenticate → library reloads with user's data
- [ ] **Chat gate:** Navigate to a category (requires an authenticated account with reels, or deep link) → chat button → gate sheet appears with "Sign in to chat with your reels" → tapping "Sign In or Create Account" opens LoginView sheet
- [ ] **Share extension (guest):** Share an Instagram reel URL while no account is logged in → extension slide-up animates → shows "Sign in to save your reels" (not "Saved!") → nothing added to Supabase
- [ ] **Share extension (authenticated):** Share an Instagram reel URL while logged in → shows "Saved!" as before
- [ ] **Guest mode cleared on sign-in:** After signing in as guest, `isGuest` is `false` and `UserDefaults` key `isGuestMode` is removed
- [ ] **Guest mode cleared on sign-out:** Sign out from a real account → `isGuest` is `false`
