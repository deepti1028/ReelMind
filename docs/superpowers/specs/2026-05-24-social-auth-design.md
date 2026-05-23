# Social Auth & Display Name — Design Spec

**Date:** 2026-05-24  
**Status:** Approved

---

## Overview

Add Google Sign In and Apple Sign In to the existing email/password auth flow, and add a required Display Name field to the email/password signup form. Display names for social auth users are pulled automatically from OAuth metadata via a Supabase DB trigger.

---

## Scope

1. Google Sign In (Supabase OAuth — in-app browser via ASWebAuthenticationSession)
2. Apple Sign In (Supabase native — system sheet via ASAuthorizationAppleIDButton)
3. Required Display Name field on email/password SignupView
4. Display Name auto-saved from Google/Apple OAuth metadata via DB trigger
5. UI follows existing AppTheme (warm cream/caramel) — no brand colors for social buttons

---

## Database

### Migration: `supabase/migrations/20260524000001_add_display_name_to_profiles.sql`

```sql
alter table public.profiles
  add column display_name text;

create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, new.raw_user_meta_data->>'full_name');
  return new;
end;
$$ language plpgsql;
```

The trigger fires once — on `INSERT` into `auth.users` — which happens at:
- Email/password signup (iOS passes `full_name` via `data` param)
- First-ever Google OAuth login
- First-ever Apple Sign In (Apple sends name only on first authorization)

On subsequent logins the trigger does not fire; `display_name` is already in `profiles`.

---

## AuthSession Changes

### New / updated methods

**`signUp(email:password:displayName:)`**  
Updated to pass `data: ["full_name": displayName]` so the trigger reads it.

**`signInWithGoogle()`**  
Calls `signInWithOAuth(provider: .google)` — opens ASWebAuthenticationSession. Supabase handles the redirect back via the registered URL scheme.

**`signInWithApple()`**  
Calls Supabase SDK's `signInWithApple()` — presents the native Apple authorization sheet.

Existing `authStateChanges` listener and `syncToken` require no changes — they handle any sign-in method transparently.

---

## SupabaseManager Changes

Add `redirectURL` to the Supabase client options:

```swift
redirectURL: URL(string: "com.reelmind.app://auth-callback")
```

This URL scheme must be registered in the app's Info.plist.

---

## iOS UI

### LoginView

Existing email/password fields and LOGIN button remain unchanged. Below the LOGIN button:

```
──── or ────

[ 􀣰  Continue with Apple  ]
[ G   Continue with Google ]
```

Both social buttons:
- Capsule shape, height 54 (matches LOGIN button)
- Background: `AppTheme.surface`
- Border: `AppTheme.border` stroke, 0.5pt
- Text: `AppTheme.textPrimary`, weight `.semibold`, size 16
- SF Symbol `apple.logo` for Apple; plain "G" text for Google

### SignupView

Display Name added as the first field, above Email. Field is required — `canSubmit` includes `!displayName.trimmingCharacters(in: .whitespaces).isEmpty`.

```
[ Display Name      ]   ← new, required
[ Email             ]
[ Password          ]
[ Confirm Password  ]

[ SIGN UP ]

──── or ────

[ 􀣰  Continue with Apple  ]
[ G   Continue with Google ]
```

Social buttons on SignupView behave identically to LoginView — Supabase creates the account on first OAuth use.

---

## Supabase Dashboard Configuration

Must be done manually before testing:

1. **Authentication → Providers → Google**: add Client ID + Client Secret from Google Cloud Console
2. **Authentication → Providers → Apple**: add Service ID, Team ID, Key ID, private key from Apple Developer portal
3. **Authentication → URL Configuration**: add `com.reelmind.app://auth-callback` as an allowed redirect URL

---

## Info.plist Changes

Register the URL scheme so the app handles the Google OAuth redirect:

```xml
<key>CFBundleURLTypes</key>
<array>
  <dict>
    <key>CFBundleURLSchemes</key>
    <array>
      <string>com.reelmind.app</string>
    </array>
  </dict>
</array>
```

---

## Backend (FastAPI / Celery)

No changes required. The profile upsert in `reels.py` ensures the row exists but does not touch `display_name`. The DB trigger handles name population for all auth paths.

---

## Out of Scope

- Fetching/displaying `display_name` elsewhere in the app (SettingsView, etc.) — separate task
- Username uniqueness enforcement
- Profile avatar from Google OAuth metadata
