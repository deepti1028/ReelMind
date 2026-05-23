# Social Auth & Display Name Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Google Sign In, Apple Sign In, and a required Display Name field to the ReelMind auth flow, saving display names to the `profiles` table for all three auth paths.

**Architecture:** A PostgreSQL trigger (`handle_new_user`, recreated with `SECURITY DEFINER`) fires once on `auth.users` INSERT and saves `raw_user_meta_data->>'full_name'` into `profiles.display_name`. Email/password signup passes the name via the Supabase SDK `data` param; Google and Apple pass it via OAuth metadata. The existing `authStateChanges` listener in `AuthSession` handles all sign-in methods transparently — no routing changes. Shared `SocialAuthButton` and `SocialAuthDivider` SwiftUI components are extracted into one file and reused by both LoginView and SignupView.

**Tech Stack:** Swift/SwiftUI, Supabase Swift SDK v2, PostgreSQL trigger with SECURITY DEFINER

---

## Critical Pre-Implementation Notes

1. **Migration number conflict:** `20260524000001` is already taken by `20260524000001_seed_default_category_icons.sql`. Use `20260524000002`.
2. **Trigger was intentionally dropped:** `20260508000001_drop_handle_new_user_trigger.sql` explains that the original trigger failed because it lacked `SECURITY DEFINER` — RLS blocks inserts from a non-privileged trigger context. The new migration **must** include `security definer` on the function.
3. **No test suite:** This iOS project has no automated test runner. "Build" steps use Xcode (⌘B). Verification is manual on device/simulator.

---

## File Map

| Action | File | What changes |
|--------|------|--------------|
| Create | `supabase/migrations/20260524000002_add_display_name_to_profiles.sql` | Adds `display_name` column; recreates trigger with SECURITY DEFINER |
| Modify | `frontend/SupabaseManager.swift` | Adds `redirectURL` to `AuthOptions` for Google OAuth callback |
| Modify | `frontend/AuthSession.swift` | Updates `signUp` signature; adds `signInWithGoogle`, `signInWithApple` |
| Create | `frontend/SocialAuthViews.swift` | `SocialAuthButton` + `SocialAuthDivider` shared components |
| Modify | `frontend/LoginView.swift` | Adds social divider + Apple/Google buttons below LOGIN |
| Modify | `frontend/SignupView.swift` | Adds Display Name field; adds social divider + Apple/Google buttons |

---

## Task 1: DB Migration — Add display_name + Recreate Trigger

**Files:**
- Create: `supabase/migrations/20260524000002_add_display_name_to_profiles.sql`

- [ ] **Step 1: Create the migration file**

Create `supabase/migrations/20260524000002_add_display_name_to_profiles.sql` with this exact content:

```sql
-- Add display_name to profiles.
--
-- Why SECURITY DEFINER: profiles has RLS enabled with no INSERT policy for
-- anonymous callers. A trigger without SECURITY DEFINER runs as the invoking
-- role (anon), which hits the RLS deny-all default and fails with
-- "Database error creating user." SECURITY DEFINER makes the function run as
-- its owner (postgres), bypassing RLS — same pattern used by Supabase's own
-- system triggers.
alter table public.profiles
  add column if not exists display_name text;

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, new.raw_user_meta_data->>'full_name')
  on conflict (id) do nothing;
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
```

- [ ] **Step 2: Apply migration**

```bash
cd /Users/deeptijain/Desktop/Deepti/Projects/ReelMind
supabase db push
```

Expected output: migration listed and applied with no error. If you see "trigger already exists", add `drop trigger if exists on_auth_user_created on auth.users;` before the `create trigger` line and re-run.

- [ ] **Step 3: Verify in Supabase Dashboard**

Open Supabase Dashboard → Table Editor → `profiles`. Confirm the `display_name` column is present (type: `text`, nullable).

- [ ] **Step 4: Commit**

```bash
git add supabase/migrations/20260524000002_add_display_name_to_profiles.sql
git commit -m "feat: add display_name to profiles; recreate handle_new_user trigger with SECURITY DEFINER"
```

---

## Task 2: SupabaseManager — Add OAuth Redirect URL

**Files:**
- Modify: `frontend/SupabaseManager.swift`

The Google OAuth flow uses `ASWebAuthenticationSession`. Supabase needs a registered redirect URL so the in-app browser hands control back to the app when auth completes. The URL scheme `com.reelmind.app` must also be registered in the app target's URL Types (Task 6) and in the Supabase Dashboard (Task 7).

- [ ] **Step 1: Add `redirectURL` to `AuthOptions`**

In `frontend/SupabaseManager.swift`, replace the `SupabaseClient(...)` initializer call:

```swift
client = SupabaseClient(
    supabaseURL: AppConfig.supabaseURL,
    supabaseKey: AppConfig.supabaseAnonKey,
    options: SupabaseClientOptions(
        auth: SupabaseClientOptions.AuthOptions(
            redirectURL: URL(string: "com.reelmind.app://auth-callback"),
            emitLocalSessionAsInitialSession: true
        )
    )
)
```

- [ ] **Step 2: Build (⌘B in Xcode)**

Expected: compiles without errors. If `redirectURL` is not a property of `AuthOptions` in your SDK version, check the Supabase Swift SDK changelog — it may be at the top-level `SupabaseClientOptions` instead.

- [ ] **Step 3: Commit**

```bash
git add frontend/SupabaseManager.swift
git commit -m "feat: add OAuth redirect URL to Supabase client"
```

---

## Task 3: AuthSession — Update signUp + Add Social Sign-In Methods

**Files:**
- Modify: `frontend/AuthSession.swift`

**What changes and why:**
- `signUp` gains a `displayName` parameter and passes `data: ["full_name": AnyJSON.string(displayName)]` to the Supabase SDK. The `handle_new_user` trigger reads this from `raw_user_meta_data->>'full_name'` and writes it into `profiles.display_name`.
- `signInWithGoogle()` calls `signInWithOAuth(provider: .google)`. Supabase opens an `ASWebAuthenticationSession` using the `redirectURL` set in Task 2.
- `signInWithApple()` calls `client.auth.signInWithApple()`. Supabase wraps `ASAuthorizationController` internally and presents the native Apple sheet. Apple sends `fullName` only on the first authorization ever — the trigger saves it then. On subsequent logins the `profiles` row already exists; `on conflict (id) do nothing` leaves `display_name` intact.
- The `authStateChanges` listener and `syncToken` require no changes — they fire for all sign-in paths.

- [ ] **Step 1: Replace the `// MARK: - Auth actions` section**

In `frontend/AuthSession.swift`, replace from `// MARK: - Auth actions` to the end of the class (the closing `}`):

```swift
    // MARK: - Auth actions

    func signIn(email: String, password: String) async throws {
        try await SupabaseManager.shared.client.auth.signIn(
            email: email,
            password: password
        )
    }

    func signUp(email: String, password: String, displayName: String) async throws {
        try await SupabaseManager.shared.client.auth.signUp(
            email: email,
            password: password,
            data: ["full_name": AnyJSON.string(displayName)]
        )
    }

    func signInWithGoogle() async throws {
        try await SupabaseManager.shared.client.auth.signInWithOAuth(
            provider: .google
        )
    }

    func signInWithApple() async throws {
        try await SupabaseManager.shared.client.auth.signInWithApple()
    }

    func signOut() async throws {
        try await SupabaseManager.shared.client.auth.signOut()
    }
}
```

**Note on `AnyJSON`:** The Supabase Swift SDK re-exports `AnyJSON` from its internal helpers package. `AnyJSON.string(_:)` constructs a JSON string value. If your SDK version uses a different type (e.g., `AnyCodable`), check the `signUp` method signature in Xcode's autocomplete — the `data` parameter type is authoritative.

**Note on `signInWithOAuth`:** If Xcode reports that `signInWithOAuth` returns a non-discardable value, add `@discardableResult` or assign the result to `_`.

**Note on `signInWithApple`:** If the SDK's `signInWithApple()` requires parameters (idToken, nonce) in your version, you will need to add an `ASAuthorizationController` wrapper. Check the Supabase Swift SDK release notes — versions ≥ 2.5 include a no-argument `signInWithApple()` convenience method.

- [ ] **Step 2: Build (⌘B in Xcode)**

Expected: compiles without errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/AuthSession.swift
git commit -m "feat: update signUp to accept displayName; add signInWithGoogle and signInWithApple"
```

---

## Task 4: Create Shared Social Auth UI Components

**Files:**
- Create: `frontend/SocialAuthViews.swift`

Both `LoginView` and `SignupView` use identical social buttons and divider. Extract them once here.

**Styling spec from design doc:**
- Button: capsule shape, height 54, `AppTheme.surface` background, `AppTheme.border` stroke 0.5pt, `AppTheme.textPrimary` text, `.semibold` weight, size 16
- Apple icon: SF Symbol `apple.logo` at size 18
- Google icon: plain "G" text at size 18, `.semibold`
- Divider: thin `AppTheme.border` lines with "or" label in `AppTheme.textMuted`

- [ ] **Step 1: Create `frontend/SocialAuthViews.swift`**

```swift
import SwiftUI

struct SocialAuthDivider: View {
    var body: some View {
        HStack(spacing: 12) {
            Rectangle()
                .fill(AppTheme.border)
                .frame(height: 0.5)
            Text("or")
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(AppTheme.textMuted)
            Rectangle()
                .fill(AppTheme.border)
                .frame(height: 0.5)
        }
    }
}

struct SocialAuthButton: View {
    let systemIcon: String?
    let textIcon: String?
    let label: String
    let action: () async -> Void

    @State private var isLoading = false

    init(systemIcon: String, label: String, action: @escaping () async -> Void) {
        self.systemIcon = systemIcon
        self.textIcon = nil
        self.label = label
        self.action = action
    }

    init(textIcon: String, label: String, action: @escaping () async -> Void) {
        self.systemIcon = nil
        self.textIcon = textIcon
        self.label = label
        self.action = action
    }

    var body: some View {
        Button {
            guard !isLoading else { return }
            Task {
                isLoading = true
                await action()
                isLoading = false
            }
        } label: {
            ZStack {
                HStack(spacing: 10) {
                    if let sys = systemIcon {
                        Image(systemName: sys)
                            .font(.system(size: 18))
                            .foregroundColor(AppTheme.textPrimary)
                    } else if let txt = textIcon {
                        Text(txt)
                            .font(.system(size: 18, weight: .semibold))
                            .foregroundColor(AppTheme.textPrimary)
                    }
                    Text(label)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(AppTheme.textPrimary)
                }
                .opacity(isLoading ? 0 : 1)

                if isLoading {
                    ProgressView()
                        .tint(AppTheme.textPrimary)
                }
            }
            .frame(maxWidth: .infinity)
            .frame(height: 54)
            .background(AppTheme.surface)
            .clipShape(Capsule())
            .overlay(Capsule().stroke(AppTheme.border, lineWidth: 0.5))
        }
        .disabled(isLoading)
    }
}
```

- [ ] **Step 2: Add file to Xcode project**

In Xcode: right-click the `frontend` group → "Add Files to ReelMind" → select `SocialAuthViews.swift`. Ensure the ReelMind target checkbox is checked.

- [ ] **Step 3: Build (⌘B in Xcode)**

Expected: compiles without errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/SocialAuthViews.swift
git commit -m "feat: add SocialAuthButton and SocialAuthDivider shared components"
```

---

## Task 5: LoginView — Add Social Buttons

**Files:**
- Modify: `frontend/LoginView.swift`

Add the "or" divider and Apple/Google buttons below the LOGIN button. Error handling: each button's async action catches errors from `auth.signInWithApple()` / `auth.signInWithGoogle()` and writes to `errorMessage`.

- [ ] **Step 1: Add `@State private var errorMessage` for social errors if not already tracked**

`LoginView` already has `@State private var errorMessage: String?`. No new state needed.

- [ ] **Step 2: Replace the full body of `LoginView.swift`**

```swift
import SwiftUI

struct LoginView: View {
    @EnvironmentObject private var auth: AuthSession

    @State private var email = ""
    @State private var password = ""
    @State private var isSubmitting = false
    @State private var errorMessage: String?
    @State private var showSignup = false

    var body: some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()

            VStack(spacing: 24) {
                Spacer()

                Text("Login")
                    .font(.system(size: 36, weight: .bold, design: .serif))
                    .foregroundColor(AppTheme.textPrimary)
                    .frame(maxWidth: .infinity, alignment: .leading)

                VStack(spacing: 16) {
                    TextField("Email", text: $email)
                        .textContentType(.emailAddress)
                        .keyboardType(.emailAddress)
                        .autocapitalization(.none)
                        .disableAutocorrection(true)
                        .foregroundColor(AppTheme.textPrimary)
                        .tint(AppTheme.accent)
                        .padding()
                        .background(AppTheme.surface)
                        .cornerRadius(12)
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(AppTheme.border, lineWidth: 0.5)
                        )

                    SecureField("Password", text: $password)
                        .textContentType(.password)
                        .foregroundColor(AppTheme.textPrimary)
                        .tint(AppTheme.accent)
                        .padding()
                        .background(AppTheme.surface)
                        .cornerRadius(12)
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(AppTheme.border, lineWidth: 0.5)
                        )
                }

                if let errorMessage = errorMessage {
                    Text(errorMessage)
                        .font(.footnote)
                        .foregroundColor(AppTheme.destructive)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                Button(action: submit) {
                    ZStack {
                        Text("LOGIN")
                            .font(.system(size: 16, weight: .bold))
                            .foregroundColor(.white)
                            .opacity(isSubmitting ? 0 : 1)
                        if isSubmitting {
                            ProgressView()
                                .tint(.white)
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .frame(height: 54)
                    .background(AppTheme.accentDark)
                    .clipShape(Capsule())
                    .shadow(color: AppTheme.accentDark.opacity(0.25), radius: 10, x: 0, y: 5)
                }
                .disabled(isSubmitting || !canSubmit)

                SocialAuthDivider()

                VStack(spacing: 12) {
                    SocialAuthButton(systemIcon: "apple.logo", label: "Continue with Apple") {
                        errorMessage = nil
                        do {
                            try await auth.signInWithApple()
                        } catch {
                            errorMessage = error.localizedDescription
                        }
                    }

                    SocialAuthButton(textIcon: "G", label: "Continue with Google") {
                        errorMessage = nil
                        do {
                            try await auth.signInWithGoogle()
                        } catch {
                            errorMessage = error.localizedDescription
                        }
                    }
                }
                .disabled(isSubmitting)

                HStack {
                    Text("Don't have an account?")
                        .foregroundColor(AppTheme.textMuted)
                    Button("Sign Up") { showSignup = true }
                        .foregroundColor(AppTheme.accentDark)
                        .fontWeight(.semibold)
                }
                .font(.footnote)

                Spacer()
            }
            .padding(.horizontal, 24)
        }
        .sheet(isPresented: $showSignup) {
            SignupView()
                .environmentObject(auth)
        }
    }

    private var canSubmit: Bool {
        !email.trimmingCharacters(in: .whitespaces).isEmpty &&
        !password.isEmpty
    }

    private func submit() {
        errorMessage = nil
        isSubmitting = true
        Task {
            do {
                try await auth.signIn(email: email, password: password)
            } catch {
                errorMessage = error.localizedDescription
            }
            isSubmitting = false
        }
    }
}
```

- [ ] **Step 3: Build (⌘B in Xcode)**

Expected: compiles without errors.

- [ ] **Step 4: Run on simulator, verify layout**

Launch the app → reach LoginView. Confirm:
- LOGIN button appears as before
- "or" divider appears below
- Apple button appears below divider (AppTheme.surface background, AppTheme.textPrimary text, no black)
- Google button appears below Apple button (same styling, "G" text icon)

- [ ] **Step 5: Commit**

```bash
git add frontend/LoginView.swift
git commit -m "feat: add Apple and Google sign-in buttons to LoginView"
```

---

## Task 6: SignupView — Add Display Name Field + Social Buttons

**Files:**
- Modify: `frontend/SignupView.swift`

Display Name is the first field (above Email), required. `canSubmit` enforces it. `submit()` calls the updated `auth.signUp(email:password:displayName:)`. Social buttons appear below SIGN UP, identical to LoginView.

- [ ] **Step 1: Replace the full body of `SignupView.swift`**

```swift
import SwiftUI

struct SignupView: View {
    @EnvironmentObject private var auth: AuthSession
    @Environment(\.dismiss) private var dismiss

    @State private var displayName = ""
    @State private var email = ""
    @State private var password = ""
    @State private var confirmPassword = ""
    @State private var isSubmitting = false
    @State private var errorMessage: String?
    @State private var infoMessage: String?

    var body: some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()

            VStack(spacing: 24) {
                Spacer()

                Text("Create an account")
                    .font(.system(size: 30, weight: .bold, design: .serif))
                    .foregroundColor(AppTheme.textPrimary)
                    .frame(maxWidth: .infinity, alignment: .leading)

                VStack(spacing: 16) {
                    TextField("Display Name", text: $displayName)
                        .textContentType(.name)
                        .autocapitalization(.words)
                        .disableAutocorrection(true)
                        .foregroundColor(AppTheme.textPrimary)
                        .tint(AppTheme.accent)
                        .padding()
                        .background(AppTheme.surface)
                        .cornerRadius(12)
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(AppTheme.border, lineWidth: 0.5)
                        )

                    TextField("Email", text: $email)
                        .textContentType(.emailAddress)
                        .keyboardType(.emailAddress)
                        .autocapitalization(.none)
                        .disableAutocorrection(true)
                        .foregroundColor(AppTheme.textPrimary)
                        .tint(AppTheme.accent)
                        .padding()
                        .background(AppTheme.surface)
                        .cornerRadius(12)
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(AppTheme.border, lineWidth: 0.5)
                        )

                    SecureField("Password", text: $password)
                        .textContentType(.newPassword)
                        .foregroundColor(AppTheme.textPrimary)
                        .tint(AppTheme.accent)
                        .padding()
                        .background(AppTheme.surface)
                        .cornerRadius(12)
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(AppTheme.border, lineWidth: 0.5)
                        )

                    SecureField("Confirm Password", text: $confirmPassword)
                        .textContentType(.newPassword)
                        .foregroundColor(AppTheme.textPrimary)
                        .tint(AppTheme.accent)
                        .padding()
                        .background(AppTheme.surface)
                        .cornerRadius(12)
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(AppTheme.border, lineWidth: 0.5)
                        )
                }

                if let errorMessage = errorMessage {
                    Text(errorMessage)
                        .font(.footnote)
                        .foregroundColor(AppTheme.destructive)
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else if let infoMessage = infoMessage {
                    Text(infoMessage)
                        .font(.footnote)
                        .foregroundColor(AppTheme.textMuted)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                Button(action: submit) {
                    ZStack {
                        Text("SIGN UP")
                            .font(.system(size: 16, weight: .bold))
                            .foregroundColor(.white)
                            .opacity(isSubmitting ? 0 : 1)
                        if isSubmitting {
                            ProgressView()
                                .tint(.white)
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .frame(height: 54)
                    .background(AppTheme.accentDark)
                    .clipShape(Capsule())
                    .shadow(color: AppTheme.accentDark.opacity(0.25), radius: 10, x: 0, y: 5)
                }
                .disabled(isSubmitting || !canSubmit)

                SocialAuthDivider()

                VStack(spacing: 12) {
                    SocialAuthButton(systemIcon: "apple.logo", label: "Continue with Apple") {
                        errorMessage = nil
                        do {
                            try await auth.signInWithApple()
                        } catch {
                            errorMessage = error.localizedDescription
                        }
                    }

                    SocialAuthButton(textIcon: "G", label: "Continue with Google") {
                        errorMessage = nil
                        do {
                            try await auth.signInWithGoogle()
                        } catch {
                            errorMessage = error.localizedDescription
                        }
                    }
                }
                .disabled(isSubmitting)

                HStack {
                    Text("Already have an account?")
                        .foregroundColor(AppTheme.textMuted)
                    Button("Login") { dismiss() }
                        .foregroundColor(AppTheme.accentDark)
                        .fontWeight(.semibold)
                }
                .font(.footnote)

                Spacer()
            }
            .padding(.horizontal, 24)
        }
    }

    private var canSubmit: Bool {
        !displayName.trimmingCharacters(in: .whitespaces).isEmpty &&
        !email.trimmingCharacters(in: .whitespaces).isEmpty &&
        password.count >= 6 &&
        password == confirmPassword
    }

    private func submit() {
        errorMessage = nil
        infoMessage = nil
        guard password == confirmPassword else {
            errorMessage = "Passwords do not match"
            return
        }
        isSubmitting = true
        Task {
            do {
                try await auth.signUp(email: email, password: password, displayName: displayName)
                if auth.session == nil {
                    infoMessage = "Check your email to confirm your account, then log in."
                } else {
                    dismiss()
                }
            } catch {
                errorMessage = error.localizedDescription
            }
            isSubmitting = false
        }
    }
}
```

- [ ] **Step 2: Build (⌘B in Xcode)**

Expected: compiles without errors.

- [ ] **Step 3: Run on simulator, verify layout**

Tap "Sign Up" from LoginView. Confirm:
- Display Name field appears first (above Email)
- SIGN UP button stays disabled until all four fields are filled and passwords match
- "or" divider and Apple/Google buttons appear below SIGN UP

- [ ] **Step 4: Commit**

```bash
git add frontend/SignupView.swift
git commit -m "feat: add Display Name field and social buttons to SignupView"
```

---

## Task 7: Info.plist — Register URL Scheme for Google OAuth Redirect

**Context:** ASWebAuthenticationSession (used by Supabase's `signInWithOAuth`) needs the app to handle the `com.reelmind.app://` URL scheme. This tells iOS to redirect back to the app after the Google OAuth web flow completes. **This is done through Xcode's GUI, not by editing a file directly.**

- [ ] **Step 1: Open target Info in Xcode**

In Xcode: select the `ReelMind` project in the navigator → select the `ReelMind` target → click the **Info** tab → scroll down to **URL Types**.

- [ ] **Step 2: Add URL scheme**

Click the **+** button under URL Types. Fill in:
- **Identifier:** `com.reelmind.app`
- **URL Schemes:** `com.reelmind.app`
- Leave Role as Editor (default)

- [ ] **Step 3: Build (⌘B in Xcode)**

Expected: compiles. The URL scheme is now registered and Xcode has written it into the app's Info.plist automatically.

- [ ] **Step 4: Commit the xcodeproj changes**

Xcode modifies the `.xcodeproj` file when you add URL types. Stage and commit those changes:

```bash
git add ReelMind.xcodeproj
git commit -m "feat: register com.reelmind.app URL scheme for OAuth redirect"
```

---

## Task 8: Supabase Dashboard Manual Configuration

**These steps must be completed before testing social auth on a device. They cannot be done in code.**

- [ ] **Step 1: Enable Google OAuth provider**

Supabase Dashboard → Authentication → Providers → Google:
1. Toggle **Enable Google provider** on
2. Paste **Client ID** from Google Cloud Console (OAuth 2.0 Client ID, iOS type)
3. Paste **Client Secret**
4. Save

To get Google credentials: Google Cloud Console → APIs & Services → Credentials → Create OAuth client ID → iOS → enter bundle ID `com.reelmind.app`.

- [ ] **Step 2: Enable Apple Sign In provider**

Supabase Dashboard → Authentication → Providers → Apple:
1. Toggle **Enable Apple provider** on
2. Paste **Service ID**, **Team ID**, **Key ID**, and **Private Key** from Apple Developer portal
3. Save

To get Apple credentials: developer.apple.com → Certificates, IDs & Profiles → Keys → create a Sign In with Apple key.

- [ ] **Step 3: Add redirect URL**

Supabase Dashboard → Authentication → URL Configuration → Redirect URLs → Add:

```
com.reelmind.app://auth-callback
```

Save.

---

## Post-Implementation Smoke Test

After all tasks are complete, verify end-to-end on a physical device (Google OAuth requires a real device for ASWebAuthenticationSession in many Supabase SDK versions):

- [ ] **Email/password signup with Display Name:** Sign up with a new email. Check Supabase Dashboard → profiles table — confirm the new row has `display_name` set to what you typed.
- [ ] **Google Sign In:** Tap "Continue with Google" on LoginView. Complete the Google OAuth flow. Confirm session is established (app navigates to ContentView). Check profiles table — `display_name` should be populated from Google account name.
- [ ] **Apple Sign In (first time):** Tap "Continue with Apple" on LoginView. Complete Apple authorization. Check profiles table — `display_name` should be the name Apple sent.
- [ ] **Apple Sign In (subsequent):** Sign out and tap "Continue with Apple" again. Confirm sign-in succeeds and `display_name` in profiles is unchanged.
