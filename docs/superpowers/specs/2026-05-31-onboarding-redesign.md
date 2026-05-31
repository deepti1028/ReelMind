# Onboarding Redesign Spec
**Date:** 2026-05-31  
**Status:** Approved for implementation  
**Mockup:** `docs/mockups/onboarding-redesign.html`

---

## Problem

The current 6-screen onboarding has two critical trust issues and a false loading state that must be fixed before any cosmetic work:

1. **Screen 4 (Permissions)** presents "Share Sheet Access" as a grantable permission. iOS Share Extensions require no permission — they are available automatically on install. The toggle opens a `ShareSheetPresenter` with dummy test text, which confuses users and damages trust in the notification permission on the same screen.
2. **Screen 5 (Organizing)** shows "We're organizing your reels" with a pulsing animation. At onboarding time the user has zero reels. The copy is factually false and may trigger privacy anxiety ("Is it accessing my Instagram without asking?").

---

## Decision

**Remove 1 screen. Redesign 1 screen. Polish 4 screens.**

| # | Current Screen | Decision | Reason |
|---|----------------|----------|--------|
| 1 | Splash | Keep + polish copy | Strong hook, clean layout |
| 2 | How It Works | Keep + redesign layout/copy | Jargon-heavy, card-heavy — rewrite with row layout |
| 3 | Share Tutorial | Keep + polish CTA | Necessary education; CTA "Got it" → "I'm Ready" |
| 4 | Permissions | Redesign as Notification-only | Remove fake Share Sheet permission |
| 5 | Organizing | **Remove** | Zero reels exist; copy is false |
| 6 | Complete | Keep + polish copy/CTA | Good aspiration; CTA "Enter ReelMind" → "Open My Library" |

**New flow: 5 screens** (was 6)

```
Splash → How It Works → Share Tutorial → Notification Permission → Complete
```

The pulsing gradient sphere animation from the Organizing screen is **not discarded** — it moves to `LibraryView` as a per-reel processing state (shown on the reel card thumbnail while `status = "processing"`).

---

## Screens

### Screen 1 — Splash

**Goal:** Create immediate emotional resonance. Confirm the user made the right download decision in under 5 seconds.  
**User emotion:** Recognition → Curiosity  
**No navigation chrome.** No back, no skip, no progress dots.

**Copy:**
```
[✦ icon in caramel circle]

Your reels.
Finally remembered.

Save any Instagram reel. Ask questions later.
Your AI-powered second brain.

[ Get Started → ]
```

**Swift changes:** None. `OnboardingSplashView` subtitle line update only.
```swift
// Before
"Save Instagram reels. Ask questions.\nDiscover insights you didn't know you had."

// After
"Save any Instagram reel. Ask questions later.\nYour AI-powered second brain."
```

---

### Screen 2 — How It Works

**Goal:** Establish the mental model (Save → AI processes → Search). Remove anxiety about complexity.  
**User emotion:** Relief ("it's simple") → Growing excitement  
**Navigation:** Back button only. No Skip.

**Layout change:** Replace three scrollable `StepCard` components with a single non-scrolling card containing three `HowItWorksRow` entries — `HStack(spacing: 16)` with 44pt icon box left, title + body right, divided by hairline separators.

**Copy:**
```
HOW IT WORKS

Three steps to never lose a reel again

[⬆ icon]  Save from Instagram
           Share any reel to ReelMind the same way
           you'd share a link. Three taps.

[🧠 icon]  AI does the work
           We transcribe it, understand it, and organize
           it automatically. Nothing to set up.

[🔍 icon]  Find anything, anytime
           Ask in plain English. "That pasta recipe from
           last week." Done.

You choose what to save. We never collect anything automatically.

[ Show Me How → ]
```

**Trust micro-copy** ("You choose what to save...") replaces the need for a dedicated consent screen. It answers the privacy question at the moment the user has it.

---

### Screen 3 — Share Tutorial

**Goal:** Give users the one physical skill they need to activate — sharing from Instagram via the Share Sheet.  
**User emotion:** "I can do this right now."  
**Navigation:** Back button only. No Skip (education too important to bypass).

**Changes from current:**
- Eyebrow: `"THE SHARE SHEET"` → `"HOW TO SAVE"`
- Headline: `"Save with ease"` → `"From Instagram in 3 taps"`
- CTA: `"Got it"` → `"I'm Ready"`
- Add a pulsing caramel ring animation (`animation: pulse 1.8s infinite`) on the "Select ReelMind" row in `PhoneMockup`, delayed 0.8s after screen entry

**Copy:**
```
HOW TO SAVE

From Instagram in 3 taps

[Phone mockup showing reel + "Select ReelMind" row with pulsing ring]

① Open any reel in Instagram.
② Tap the Share button ↑
③ Select ReelMind.   ← (filled caramel circle, bold text)

[ I'm Ready ]
```

**Swift changes:** Minimal. In `OnboardingShareTutorialView`:
```swift
// CTA
OnboardingPrimaryButton(title: "I'm Ready", trailingIcon: nil, action: onContinue)

// Eyebrow
Text("HOW TO SAVE")

// Title
Text("From Instagram in 3 taps")
```

In `PhoneMockup`, add a pulsing ring around the share row:
```swift
// Wrap the share row in a ZStack with an animated RoundedRectangle stroke
.overlay(
    RoundedRectangle(cornerRadius: 14)
        .stroke(OnboardingTheme.primary, lineWidth: 2)
        .opacity(pulse ? 0 : 0.8)
        .scaleEffect(pulse ? 1.06 : 1.0)
)
.onAppear {
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) {
        withAnimation(.easeInOut(duration: 1.4).repeatForever(autoreverses: false)) {
            pulse = true
        }
    }
}
```

---

### Screen 4 — Notification Permission

**Goal:** Get notification permission with the highest possible acceptance rate.  
**User emotion:** Informed consent + trust  
**Navigation:** No header, no back, no skip. This screen requires a deliberate choice.

**Critical change:** Remove `PermissionRow` for "Share Sheet Access" entirely. This row presents a fake permission and is the primary trust-damaging element in the current flow.

The screen becomes single-purpose: one ask, one icon, one decision.

**Layout:** Centered, full-screen focus. No scroll.
```
[Progress dots: ●●●◉○]

[🔔 in 136pt caramel circle — pulsing ring animation]

Know the moment
it's ready

After saving a reel, we'll send one notification
when it's been transcribed and organized.
One per reel. No spam, ever.

Notifications only fire when you save something.
You're in control.

[ Enable Notifications ]
      Not right now
```

**Behavior:**
- "Enable Notifications" → triggers iOS system notification dialog (`notifications.requestOrOpenSettings()`)
- If granted → `advance()` to Complete
- If denied → `advance()` to Complete (Complete screen adds soft Settings nudge)
- "Not right now" → `advance()` to Complete, no dialog triggered

**Swift changes to `OnboardingPermissionsView`:**
```swift
// Remove entirely:
PermissionRow(
    icon: "square.and.arrow.up",
    title: "Share Sheet Access",
    ...
)

// Remove:
@AppStorage("shareSheetAcknowledged") private var shareSheetAcknowledged = false
@State private var showShareSheetDemo = false
.sheet(isPresented: $showShareSheetDemo) { ShareSheetPresenter(...) }

// Keep (notification row becomes the full screen):
// Rebuild as focused centered layout — no PermissionRow component needed
// New layout: VStack with icon ring, title, body, privacy line
// Primary CTA calls notifications.requestOrOpenSettings()
// Secondary "Not right now" calls onMaybeLater()
```

**Pre-frame value:** The copy "After saving a reel, we'll send one notification when it's been transcribed and organized" is the pre-frame before the iOS system dialog. This specificity (one notification per reel, tied to transcription completion) is what separates ~40% acceptance from ~65%.

---

### Screen 5 — Complete

**Goal:** Convert curiosity into first action. Show users what the product unlocks before they've used it.  
**User emotion:** Ready, confident, slightly excited  
**Navigation:** No back, no skip. Terminal screen.

**Changes:**
- Remove `"WELCOME HOME"` eyebrow — replace with single `✦` sparkle in caramel
- Add subtitle: `"Save your first reel and watch your library come to life."`
- Add fourth query row: `♡ "Reels I keep coming back to"`
- CTA: `"Enter ReelMind"` → `"Open My Library"`
- Add trust line below CTA: `"🔒 Private by default. Only you can see your library."`

**Copy:**
```
✦

Your second
brain is ready.

Save your first reel and watch your library come to life.

┌─────────────────────────────────────┐
│ ✦ Ask about anything you've saved   │
│ ─────────────────────────────────── │
│ ⏱ "Skincare routines from last month" │
│ 🔖 "Productivity tips I bookmarked"   │
│ 🍴 "Pasta recipes"                    │
│ ♡  "Reels I keep coming back to"      │
└─────────────────────────────────────┘

[ Open My Library → ]

🔒 Private by default. Only you can see your library.
```

---

## OnboardingFlow.swift changes

```swift
// Remove .organizing from the enum
enum OnboardingStep: Int, CaseIterable {
    case splash
    case howItWorks
    case shareTutorial
    case permissions   // now Notification-only
    case complete
}

// Remove the organizing case from the switch:
// case .organizing:
//     OnboardingOrganizingView(...)
```

This is the only structural change required. Everything else is within individual screen files.

---

## Progress Indicator

Add 5-dot progress indicator to screens 2–5 (not screen 1 — splash benefits from the cinematic no-chrome treatment).

```swift
// Shared component — add to OnboardingFlow.swift or new OnboardingProgressDots.swift
struct OnboardingProgressDots: View {
    let total: Int
    let current: Int  // 0-indexed

    var body: some View {
        HStack(spacing: 6) {
            ForEach(0..<total, id: \.self) { i in
                Capsule()
                    .fill(i <= current ? OnboardingTheme.primary : OnboardingTheme.divider)
                    .frame(width: i == current ? 18 : 5, height: 5)
                    .opacity(i < current ? 0.45 : 1.0)
                    .animation(.easeInOut(duration: 0.25), value: current)
            }
        }
        .padding(.top, 10)
    }
}
```

---

## Trust & Privacy

No dedicated consent screen. Privacy is communicated through micro-copy distributed across the flow:

| Screen | Micro-copy | Purpose |
|--------|-----------|---------|
| How It Works | "You choose what to save. We never collect anything automatically." | Explicit opt-in model |
| Notification | "Notifications only fire when you save something. You're in control." | Notification scope |
| Complete | "🔒 Private by default. Only you can see your library." | Data ownership |

This distributed pattern outperforms a dedicated consent screen because each line is contextually relevant at the moment the user reads it, and it doesn't interrupt the emotional arc with a legal-feeling wall of text.

---

## Reuse: Organizing Screen Animation

`OnboardingOrganizingView` is removed from the flow but its visual (pulsing gradient sphere) is preserved for use in `LibraryView`.

When a reel has `status = "queued"` or `status = "processing"`, the reel card's thumbnail area should show the pulsing sphere instead of a blank state. This is the correct context for that animation — it is truthful (processing is actually happening), and it makes the pipeline's progress visible to the user.

```swift
// In reel card thumbnail area
if reel.status == .queued || reel.status == .processing {
    ProcessingOrb()  // extract from OnboardingOrganizingView
} else {
    AsyncImage(url: reel.thumbnailURL) { ... }
}
```

---

## Implementation Order

Priority order — fix trust issues first, polish second:

1. **Remove `OnboardingStep.organizing`** from `OnboardingFlow.swift` — one line, eliminates the false loading state
2. **Remove Share Sheet Access row** from `OnboardingPermissionsView` — eliminates fake permission
3. **Rebuild Notification Permission screen** — focused single-ask layout, new copy
4. **Update How It Works** — replace `StepCard` with row layout, new copy
5. **Polish Share Tutorial** — eyebrow, headline, CTA copy + pulsing ring on mockup
6. **Add `OnboardingProgressDots`** — shared component, add to screens 2–5
7. **Polish Complete screen** — copy changes, new CTA, trust line
8. **Extract `ProcessingOrb`** — move animation to `LibraryView` reel card

Items 1 and 2 can ship independently as a hotfix. Items 3–8 ship together as the full redesign.

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Onboarding completion rate | >78% (from est. ~52%) | `hasCompletedOnboarding = true` events |
| Notification grant rate | >55% | iOS permission grant events |
| First reel saved within 24h | >45% of completions | Supabase `reels` insert within 24h of onboarding |
| Skip rate on Share Tutorial | <5% | Skip button tap events |
