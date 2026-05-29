# Forgot Password — Design Spec

**Date:** 2026-05-30  
**Status:** Approved  

---

## Overview

Implement the "Forgot password?" button on `LoginView`. The flow has two parts:

1. **Email entry** — user requests a reset link (sheet presented from `LoginView`)
2. **Password update** — user sets a new password after tapping the email link (sheet presented from `RootView` on deep link callback)

Both parts live in a single new file: `ForgotPasswordView.swift`, with an internal state enum controlling which screen is shown.

---

## Architecture

### New file: `ForgotPasswordView.swift`

```swift
enum ForgotPasswordState {
    case enterEmail
    case setNewPassword
}
```

- Initialized with either state
- `enterEmail` state: email input field, "Send reset link" button, confirmation message after success
- `setNewPassword` state: new password field + confirm password field (both with show/hide toggle), "Update password" button

### `AuthSession` additions

| Addition | Purpose |
|---|---|
| `@Published var isRecovering: Bool = false` | Set to `true` when Supabase fires `.passwordRecovery` in `authStateChanges` |
| `func resetPassword(email: String) async throws` | Calls `supabase.auth.resetPasswordForEmail(email)` |
| `func updatePassword(_ newPassword: String) async throws` | Calls `supabase.auth.update(user: UserAttributes(password: newPassword))`; sets `isRecovering = false` on success |

### `LoginView` changes

- Add `@State private var showForgotPassword = false`
- Wire the existing empty "Forgot password?" button action to `showForgotPassword = true`
- Add `.sheet(isPresented: $showForgotPassword) { ForgotPasswordView(initialState: .enterEmail, prefillEmail: email) }`
- Pass `email` from the login field as a pre-fill so the user doesn't retype it

### `RootView` changes

- Add `.sheet(isPresented: $auth.isRecovering) { ForgotPasswordView(initialState: .setNewPassword) }`
- **Important:** `isRecovering` must be checked before routing to `ContentView`. When `isRecovering = true`, hold the user on the login screen (don't route to `ContentView`) and let the sheet present there. This prevents a visible flash of `ContentView` before the sheet appears.

---

## Data Flow

```
1. User taps "Forgot password?" on LoginView
2. Sheet opens in `enterEmail` state (email pre-filled if typed)
3. User taps "Send reset link" → auth.resetPassword(email:) called
4. Supabase emails the reset link (silently succeeds even if email not found)
5. Sheet shows confirmation: "Check your inbox — we sent a reset link to [email]"
6. User dismisses sheet → back on LoginView, can log in normally

── user opens email and taps the reset link ──

7. App opens via deep link: com.reelmind.app://auth-callback
8. Supabase SDK fires .passwordRecovery in authStateChanges
9. AuthSession sets isRecovering = true
10. RootView presents ForgotPasswordView in `setNewPassword` state
11. User enters new password + confirm → taps "Update password"
12. auth.updatePassword(_:) called → success
13. isRecovering = false → sheet dismisses → user is logged in (Supabase establishes full session)
```

---

## Screen Details

### `enterEmail` screen

- Email text field (`textContentType: .emailAddress`, pre-filled from `LoginView` if available)
- "Send reset link" primary button — disabled until field is non-empty
- After success: button replaced with confirmation message, sheet stays open for user to dismiss manually
- Error display: inline, below the button (network errors, rate limits)

### `setNewPassword` screen

- New password field with show/hide eye toggle (`textContentType: .newPassword`)
- Confirm password field with show/hide eye toggle (`textContentType: .newPassword`)
- "Update password" primary button — disabled until both fields are non-empty and match
- No password strength requirements
- Error display: inline, below the button (mismatch validation, Supabase errors like expired token)

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| Network error on send | Inline error below button |
| Supabase rate limit | Inline error below button |
| Passwords don't match | "Passwords don't match" shown live once confirm field is non-empty and differs from new password; button stays disabled |
| Either password field empty | Button disabled (no error shown) |
| Expired recovery token | Supabase returns error → show "This link has expired. Request a new one." |
| User dismisses `setNewPassword` sheet | `isRecovering = false`, sheet dismissed; since a recovery session is a valid Supabase session, `RootView` routes them to `ContentView` (they are authenticated) |

---

## What's NOT in scope

- Password strength meter or minimum length enforcement
- Blocking the user if they dismiss the reset sheet without completing
- Any backend changes (Supabase handles email delivery natively)
