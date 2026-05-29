# Forgot Password Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the forgot password flow — a sheet to request a reset email and a sheet to set a new password after the deep link fires.

**Architecture:** One new file `ForgotPasswordView.swift` holds both screens via an internal state enum (`enterEmail` / `setNewPassword`). `AuthSession` gains three additions: an `isRecovering` flag (set when Supabase fires `.passwordRecovery`), `resetPassword(email:)`, and `updatePassword(_:)`. `LoginView` wires the existing empty button. `RootView` intercepts the recovery session and presents the password-update sheet.

**Tech Stack:** SwiftUI, Supabase Swift SDK (`Auth` module), `AppTheme` / `LabeledAuthField` (existing shared UI primitives)

---

## File Map

| Action | File | What changes |
|---|---|---|
| Modify | `frontend/AuthSession.swift` | Add `isRecovering`, `resetPassword`, `updatePassword`, detect `.passwordRecovery` event |
| Create | `frontend/ForgotPasswordView.swift` | Both screens (`enterEmail` + `setNewPassword`) in a single sheet |
| Modify | `frontend/LoginView.swift` | Wire button + add sheet |
| Modify | `frontend/RootView.swift` | Block routing to ContentView during recovery + add recovery sheet |

---

## Task 1: Add auth methods to `AuthSession`

**Files:**
- Modify: `frontend/AuthSession.swift`

### Context

`authStateChanges` currently ignores the event (`for await (_, newSession)`). We need to capture it to detect `.passwordRecovery`. We also need two new public methods.

- [ ] **Step 1: Capture the event in `authStateChanges`**

In `AuthSession.swift`, find the `bootstrap()` method. Change the `for await` loop from ignoring the event to capturing it, and set `isRecovering = true` when the event is `.passwordRecovery`.

Replace:
```swift
listenerTask = Task { [weak self] in
    for await (_, newSession) in SupabaseManager.shared.client.auth.authStateChanges {
        await MainActor.run {
            self?.session = newSession
            self?.syncToken(newSession?.accessToken)
            if let userId = newSession?.user.id.uuidString {
                self?.handleOnboardingTracking(for: userId)
            }
        }
    }
}
```

With:
```swift
listenerTask = Task { [weak self] in
    for await (event, newSession) in SupabaseManager.shared.client.auth.authStateChanges {
        await MainActor.run {
            self?.session = newSession
            self?.syncToken(newSession?.accessToken)
            if event == .passwordRecovery {
                self?.isRecovering = true
            }
            if let userId = newSession?.user.id.uuidString {
                self?.handleOnboardingTracking(for: userId)
            }
        }
    }
}
```

- [ ] **Step 2: Add `isRecovering` published property**

Directly below the existing `@Published var isBootstrapping = true` line, add:

```swift
@Published var isRecovering = false
```

- [ ] **Step 3: Add `resetPassword` and `updatePassword` methods**

In `AuthSession.swift`, add these two methods in the `// MARK: - Auth actions` section, after `signUp`:

```swift
func resetPassword(email: String) async throws {
    try await SupabaseManager.shared.client.auth.resetPasswordForEmail(
        email,
        redirectTo: URL(string: "com.reelmind.app://auth-callback")
    )
}

func updatePassword(_ newPassword: String) async throws {
    try await SupabaseManager.shared.client.auth.update(
        user: UserAttributes(password: newPassword)
    )
    isRecovering = false
}
```

- [ ] **Step 4: Build to verify**

In Xcode press **⌘B**. Expected: build succeeds with no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/AuthSession.swift
git commit -m "feat: add isRecovering, resetPassword, and updatePassword to AuthSession"
```

---

## Task 2: Create `ForgotPasswordView.swift`

**Files:**
- Create: `frontend/ForgotPasswordView.swift`

### Context

This is a sheet with two screens controlled by `ForgotPasswordState`. It uses `AppTheme`, `LabeledAuthField`, and the same primary button style as `LoginView` (gradient background, `Color(r:g:b:)` initializer, serif font). It receives `auth` via `@EnvironmentObject`.

`enterEmail` screen: email field, "Send reset link" button, confirmation message after success.  
`setNewPassword` screen: two password fields with show/hide toggles, live mismatch error, "Update password" button.

- [ ] **Step 1: Create the file**

Create `frontend/ForgotPasswordView.swift` with this content:

```swift
import SwiftUI

enum ForgotPasswordState {
    case enterEmail, setNewPassword
}

struct ForgotPasswordView: View {
    @EnvironmentObject private var auth: AuthSession

    @State private var state: ForgotPasswordState
    @State private var email: String
    @State private var newPassword = ""
    @State private var confirmPassword = ""
    @State private var showNewPassword = false
    @State private var showConfirmPassword = false
    @State private var isSubmitting = false
    @State private var errorMessage: String?
    @State private var didSendEmail = false

    init(initialState: ForgotPasswordState, prefillEmail: String = "") {
        _state = State(initialValue: initialState)
        _email = State(initialValue: prefillEmail)
    }

    var body: some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()
            ScrollView(showsIndicators: false) {
                VStack(alignment: .leading, spacing: 0) {
                    if state == .enterEmail {
                        enterEmailContent
                    } else {
                        setNewPasswordContent
                    }
                }
                .padding(.horizontal, 26)
                .padding(.top, 60)
                .padding(.bottom, 40)
            }
        }
    }

    // MARK: - Enter Email

    @ViewBuilder
    private var enterEmailContent: some View {
        Text("Reset password")
            .font(.system(size: 22, weight: .semibold, design: .serif))
            .foregroundColor(AppTheme.textPrimary)
            .padding(.bottom, 8)

        Text("Enter your email and we'll send you a link to reset your password.")
            .font(.system(size: 14, weight: .regular, design: .serif))
            .foregroundColor(AppTheme.textMuted)
            .padding(.bottom, 28)

        LabeledAuthField(label: "EMAIL ADDRESS") {
            TextField("", text: $email)
                .textContentType(.emailAddress)
                .keyboardType(.emailAddress)
                .autocapitalization(.none)
                .disableAutocorrection(true)
        }
        .padding(.bottom, 22)

        if let errorMessage {
            Text(errorMessage)
                .font(.footnote)
                .foregroundColor(AppTheme.destructive)
                .padding(.bottom, 10)
        }

        if didSendEmail {
            HStack(spacing: 8) {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundColor(.green)
                Text("Check your inbox — we sent a reset link to \(email)")
                    .font(.system(size: 14))
                    .foregroundColor(AppTheme.textPrimary)
            }
        } else {
            Button(action: sendResetEmail) {
                ZStack {
                    Text("Send reset link")
                        .font(.system(size: 17, weight: .semibold, design: .serif))
                        .foregroundColor(Color(r: 0xfd, g: 0xf4, b: 0xe3))
                        .opacity(isSubmitting ? 0 : 1)
                    if isSubmitting {
                        ProgressView().tint(Color(r: 0xfd, g: 0xf4, b: 0xe3))
                    }
                }
                .frame(maxWidth: .infinity)
                .frame(height: 54)
                .background(AppTheme.buttonGradient)
                .clipShape(RoundedRectangle(cornerRadius: 14))
                .shadow(color: AppTheme.accentDark.opacity(0.35), radius: 12, x: 0, y: 6)
            }
            .disabled(isSubmitting || email.trimmingCharacters(in: .whitespaces).isEmpty)
        }
    }

    // MARK: - Set New Password

    @ViewBuilder
    private var setNewPasswordContent: some View {
        Text("Set new password")
            .font(.system(size: 22, weight: .semibold, design: .serif))
            .foregroundColor(AppTheme.textPrimary)
            .padding(.bottom, 8)

        Text("Choose a new password for your account.")
            .font(.system(size: 14, weight: .regular, design: .serif))
            .foregroundColor(AppTheme.textMuted)
            .padding(.bottom, 28)

        VStack(spacing: 14) {
            LabeledAuthField(label: "NEW PASSWORD") {
                HStack {
                    Group {
                        if showNewPassword {
                            TextField("", text: $newPassword)
                        } else {
                            SecureField("", text: $newPassword)
                        }
                    }
                    .textContentType(.newPassword)
                    Button(action: { showNewPassword.toggle() }) {
                        Image(systemName: showNewPassword ? "eye.slash" : "eye")
                            .foregroundColor(AppTheme.textMuted)
                            .font(.system(size: 15))
                    }
                }
            }

            LabeledAuthField(label: "CONFIRM PASSWORD") {
                HStack {
                    Group {
                        if showConfirmPassword {
                            TextField("", text: $confirmPassword)
                        } else {
                            SecureField("", text: $confirmPassword)
                        }
                    }
                    .textContentType(.newPassword)
                    Button(action: { showConfirmPassword.toggle() }) {
                        Image(systemName: showConfirmPassword ? "eye.slash" : "eye")
                            .foregroundColor(AppTheme.textMuted)
                            .font(.system(size: 15))
                    }
                }
            }
        }
        .padding(.bottom, 10)

        if !confirmPassword.isEmpty && newPassword != confirmPassword {
            Text("Passwords don't match")
                .font(.footnote)
                .foregroundColor(AppTheme.destructive)
                .padding(.bottom, 10)
        }

        if let errorMessage {
            Text(errorMessage)
                .font(.footnote)
                .foregroundColor(AppTheme.destructive)
                .padding(.bottom, 10)
        }

        Button(action: updatePassword) {
            ZStack {
                Text("Update password")
                    .font(.system(size: 17, weight: .semibold, design: .serif))
                    .foregroundColor(Color(r: 0xfd, g: 0xf4, b: 0xe3))
                    .opacity(isSubmitting ? 0 : 1)
                if isSubmitting {
                    ProgressView().tint(Color(r: 0xfd, g: 0xf4, b: 0xe3))
                }
            }
            .frame(maxWidth: .infinity)
            .frame(height: 54)
            .background(AppTheme.buttonGradient)
            .clipShape(RoundedRectangle(cornerRadius: 14))
            .shadow(color: AppTheme.accentDark.opacity(0.35), radius: 12, x: 0, y: 6)
        }
        .disabled(isSubmitting || !canUpdatePassword)
    }

    private var canUpdatePassword: Bool {
        !newPassword.isEmpty && !confirmPassword.isEmpty && newPassword == confirmPassword
    }

    // MARK: - Actions

    private func sendResetEmail() {
        errorMessage = nil
        isSubmitting = true
        Task {
            do {
                try await auth.resetPassword(email: email.trimmingCharacters(in: .whitespaces))
                didSendEmail = true
            } catch {
                errorMessage = error.localizedDescription
            }
            isSubmitting = false
        }
    }

    private func updatePassword() {
        errorMessage = nil
        isSubmitting = true
        Task {
            do {
                try await auth.updatePassword(newPassword)
                // auth.isRecovering is set to false inside updatePassword —
                // RootView's binding will auto-dismiss this sheet
            } catch {
                errorMessage = error.localizedDescription
            }
            isSubmitting = false
        }
    }
}
```

- [ ] **Step 2: Build to verify**

Press **⌘B**. Expected: build succeeds.

- [ ] **Step 3: Manual smoke test — enterEmail screen**

Run the app (**⌘R**), navigate to `LoginView`, tap "Forgot password?". Expected: sheet does not present yet (the button is still empty — that's wired in Task 3). Confirm the project builds cleanly.

- [ ] **Step 4: Commit**

```bash
git add frontend/ForgotPasswordView.swift
git commit -m "feat: add ForgotPasswordView with enterEmail and setNewPassword states"
```

---

## Task 3: Wire `LoginView`

**Files:**
- Modify: `frontend/LoginView.swift`

### Context

`LoginView` already has the button at line 76 with an empty action `{ }`. We add `showForgotPassword` state, wire the action, and attach the sheet. The `email` field state is already in scope at `@State private var email = ""` (line 6), so it can be passed directly as `prefillEmail`.

- [ ] **Step 1: Add `showForgotPassword` state**

In `LoginView.swift`, after the existing `@State private var showPassword = false` line (line 11), add:

```swift
@State private var showForgotPassword = false
```

- [ ] **Step 2: Wire the button action**

Find the existing empty button (line 76):
```swift
Button("Forgot password?") { }
```

Replace with:
```swift
Button("Forgot password?") { showForgotPassword = true }
```

- [ ] **Step 3: Add the sheet modifier**

Find the existing sheet at the bottom of `LoginView.swift`:
```swift
.sheet(isPresented: $showSignup) {
    SignupView().environmentObject(auth)
}
```

Add a second sheet modifier directly after it:
```swift
.sheet(isPresented: $showForgotPassword) {
    ForgotPasswordView(initialState: .enterEmail, prefillEmail: email)
        .environmentObject(auth)
}
```

- [ ] **Step 4: Build and manually test**

Press **⌘B**, then **⌘R**.
- Tap "Forgot password?" → sheet slides up showing "Reset password" title and email field.
- If you had already typed an email in the login field, it should be pre-filled in the sheet.
- Swipe down → sheet dismisses → back on `LoginView`, login works normally.
- Tap "Forgot password?" again, enter a valid email, tap "Send reset link" → button shows spinner → confirmation message appears ("Check your inbox…").
- Tapping "Send reset link" with an empty email → button should remain disabled.

- [ ] **Step 5: Commit**

```bash
git add frontend/LoginView.swift
git commit -m "feat: wire Forgot password button and sheet in LoginView"
```

---

## Task 4: Wire `RootView` for recovery deep link

**Files:**
- Modify: `frontend/RootView.swift`

### Context

When the user taps the password reset link in their email, Supabase fires `.passwordRecovery` in `authStateChanges`, which sets `auth.isRecovering = true` and also sets `auth.session` (a recovery-scoped session). Without this task, `RootView` would route straight to `ContentView` before the sheet has a chance to present — causing a visible flash. We fix this by adding `&& !auth.isRecovering` to the `ContentView` routing condition, and attaching the recovery sheet to the `Group`.

- [ ] **Step 1: Block routing to `ContentView` during recovery**

In `RootView.swift`, find:
```swift
} else if auth.session != nil {
    ContentView()
}
```

Replace with:
```swift
} else if auth.session != nil && !auth.isRecovering {
    ContentView()
}
```

- [ ] **Step 2: Add a computed binding for `isRecovering`**

In `RootView`, add this computed property below `@State private var categoriseTarget`:

```swift
private var isRecoveringBinding: Binding<Bool> {
    Binding(
        get: { auth.isRecovering },
        set: { auth.isRecovering = $0 }
    )
}
```

This is needed because `@EnvironmentObject` doesn't expose `$property` bindings directly; we construct one manually. When the user swipes to dismiss the sheet, SwiftUI calls the setter with `false`, which clears `auth.isRecovering`.

- [ ] **Step 3: Attach the recovery sheet**

In `RootView.swift`, find the existing `.fullScreenCover` modifier:
```swift
.fullScreenCover(item: $categoriseTarget) { target in
    CategoriseReelView(reelId: target.reelId, suggestions: target.suggestions)
}
```

Add the recovery sheet directly after it:
```swift
.sheet(isPresented: isRecoveringBinding) {
    ForgotPasswordView(initialState: .setNewPassword)
        .environmentObject(auth)
}
```

- [ ] **Step 4: Build to verify**

Press **⌘B**. Expected: build succeeds with no errors or warnings.

- [ ] **Step 5: Manual test — full reset flow**

> **Note:** Testing the deep link requires a real device or simulator with a mail client. If testing on simulator, you can trigger `.passwordRecovery` by opening `com.reelmind.app://auth-callback#type=recovery&...` directly in Safari on the simulator, or use a test account with access to the email.

Test the happy path:
1. Run app, navigate to `LoginView`.
2. Tap "Forgot password?", enter your test account email, tap "Send reset link".
3. Open the reset email and tap the link.
4. App should open with the "Set new password" sheet on top of `LoginView` (not `ContentView`).
5. Enter a new password in both fields — "Update password" button stays disabled until they match.
6. Mistype confirm password → "Passwords don't match" appears live.
7. Fix to match → button enables, tap "Update password" → sheet auto-dismisses → you land in the app (authenticated).
8. Sign out, try logging in with the new password → success.

Test dismiss without completing:
1. Repeat steps 1–4.
2. Swipe the "Set new password" sheet down without tapping "Update password".
3. Expected: sheet dismisses, `isRecovering` is cleared, `RootView` routes to `ContentView` (you are logged in with the recovery session).

- [ ] **Step 6: Commit**

```bash
git add frontend/RootView.swift
git commit -m "feat: handle password recovery deep link in RootView"
```

---

## Supabase Dashboard Note

Supabase's "Reset Password" email template must include `{{ .ConfirmationURL }}` pointing to your app's redirect URL. If the deep link doesn't fire, check:

**Supabase Dashboard → Authentication → URL Configuration → Redirect URLs**  
Add `com.reelmind.app://auth-callback` if it's not already listed.

**Authentication → Email Templates → Reset Password**  
Confirm the template link uses `{{ .ConfirmationURL }}`.

This is a one-time dashboard config step — no code change needed.
