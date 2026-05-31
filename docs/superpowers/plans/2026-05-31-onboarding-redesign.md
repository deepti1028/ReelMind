# Onboarding Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the onboarding flow from 6 screens to 5 — removing a fake permission, a false loading state, and adding a focused notification permission screen, progress dots, and polished copy across every screen.

**Architecture:** Each screen is an independent SwiftUI View file. `OnboardingFlow.swift` owns the `OnboardingStep` enum and routing — removing `.organizing` from the enum is the only structural change to the router. All other changes are contained to individual screen files or new shared components.

**Tech Stack:** SwiftUI, Swift 5.9+, iOS 16+, Xcode. No test target is configured — verification is build + simulator.

---

## File Map

| Action | File |
|--------|------|
| Modify | `frontend/OnboardingFlow.swift` |
| Modify | `frontend/OnboardingSplashView.swift` |
| Modify | `frontend/OnboardingHowItWorksView.swift` |
| Modify | `frontend/OnboardingShareTutorialView.swift` |
| Modify | `frontend/OnboardingPermissionsView.swift` |
| Modify | `frontend/OnboardingCompleteView.swift` |
| Modify | `frontend/Views/Components/ReelCardView.swift` |
| **Create** | `frontend/OnboardingProgressDots.swift` |
| **Create** | `frontend/ProcessingOrb.swift` |
| **Delete** | `frontend/OnboardingOrganizingView.swift` |

---

## Task 1 — Remove `.organizing` from OnboardingFlow

**Files:**
- Modify: `frontend/OnboardingFlow.swift`

Tasks 1 and 2 are trust fixes. They ship first, independently of all polish work.

- [ ] Open `frontend/OnboardingFlow.swift`. Find the `OnboardingStep` enum and remove `.organizing`:

```swift
// Before
enum OnboardingStep: Int, CaseIterable {
    case splash
    case howItWorks
    case shareTutorial
    case permissions
    case organizing
    case complete
}

// After
enum OnboardingStep: Int, CaseIterable {
    case splash
    case howItWorks
    case shareTutorial
    case permissions
    case complete
}
```

- [ ] In the `switch step` block inside `var body`, remove the `.organizing` case entirely:

```swift
// Remove this block:
case .organizing:
    OnboardingOrganizingView(
        onBack: { back() },
        onSkip: { skip() },
        onContinue: { advance() }
    )
```

- [ ] Build: `⌘B` in Xcode. Expected: build succeeds. `OnboardingOrganizingView` will produce an "unused" warning — ignore it for now, it is deleted in Task 10.

- [ ] Commit:
```bash
git add frontend/OnboardingFlow.swift
git commit -m "fix: remove organizing step from onboarding — no reels exist at this point in the flow"
```

---

## Task 2 — Remove the fake Share Sheet Access permission row

**Files:**
- Modify: `frontend/OnboardingPermissionsView.swift`

The `Share Sheet Access` toggle presents a fake permission to users. iOS Share Extensions require no permission — they are available automatically on app install. This toggle currently opens a `ShareSheetPresenter` with dummy test text and sets an `@AppStorage` flag, but grants nothing real.

- [ ] Open `frontend/OnboardingPermissionsView.swift`. Remove the `@AppStorage` and `@State` properties for the Share Sheet demo:

```swift
// Remove both of these lines:
@AppStorage("shareSheetAcknowledged") private var shareSheetAcknowledged = false
@State private var showShareSheetDemo = false
```

- [ ] Remove the Share Sheet `PermissionRow` from the `VStack` in `body`:

```swift
// Remove this entire block:
PermissionRow(
    icon: "square.and.arrow.up",
    title: "Share Sheet Access",
    description: "Save reels without leaving Instagram.",
    isOn: shareSheetAcknowledged,
    statusText: nil,
    onToggle: { showShareSheetDemo = true }
)
```

- [ ] Remove the `.sheet` modifier that presented the Share Sheet demo:

```swift
// Remove this block:
.sheet(isPresented: $showShareSheetDemo) {
    ShareSheetPresenter(
        items: ["Try sharing this with ReelMind from your favorites!"],
        onDismiss: {
            shareSheetAcknowledged = true
            showShareSheetDemo = false
        }
    )
}
```

- [ ] Build: `⌘B`. Expected: build succeeds. The Permissions screen now shows only the Notifications row.

- [ ] Commit:
```bash
git add frontend/OnboardingPermissionsView.swift
git commit -m "fix: remove fake Share Sheet Access permission row — Share Extensions need no permission grant on iOS"
```

---

## Task 3 — Create `OnboardingProgressDots` shared component

**Files:**
- Create: `frontend/OnboardingProgressDots.swift`

Screens 2–5 all need a 5-dot progress indicator. Screen 1 (Splash) gets no dots — it benefits from a clean, chrome-free first impression.

- [ ] Create `frontend/OnboardingProgressDots.swift` with this exact content:

```swift
import SwiftUI

/// Five-dot progress indicator shown on onboarding screens 2–5.
/// Pass `current` as the 0-indexed step number (splash = 0, howItWorks = 1, etc.).
struct OnboardingProgressDots: View {
    let current: Int
    var total: Int = 5

    var body: some View {
        HStack(spacing: 6) {
            ForEach(0..<total, id: \.self) { i in
                Capsule()
                    .fill(color(for: i))
                    .frame(width: width(for: i), height: 5)
                    .animation(.easeInOut(duration: 0.25), value: current)
            }
        }
        .padding(.top, 10)
    }

    private func color(for index: Int) -> Color {
        if index < current  { return OnboardingTheme.primary.opacity(0.45) }
        if index == current { return OnboardingTheme.primary }
        return OnboardingTheme.divider
    }

    private func width(for index: Int) -> CGFloat {
        index == current ? 18 : 5
    }
}

#Preview {
    VStack(spacing: 20) {
        OnboardingProgressDots(current: 0)
        OnboardingProgressDots(current: 1)
        OnboardingProgressDots(current: 3)
        OnboardingProgressDots(current: 4)
    }
    .padding()
    .background(OnboardingTheme.background)
}
```

- [ ] Build: `⌘B`. Expected: succeeds.

- [ ] Open the Canvas preview (`⌥⌘↩`). Verify four rows showing different active dot positions — the active dot is wider and caramel-colored, visited dots are faded caramel, future dots are the border color.

- [ ] Commit:
```bash
git add frontend/OnboardingProgressDots.swift
git commit -m "feat: add OnboardingProgressDots shared component for screens 2–5"
```

---

## Task 4 — Rebuild Notification Permission screen as single-focus layout

**Files:**
- Modify: `frontend/OnboardingPermissionsView.swift`

The screen is now stripped to the notification row only (Task 2). Replace the remaining `PermissionRow`-based layout with a focused, centered design: large bell icon with a pulsing ring, clear copy, privacy reassurance, two CTAs. No header, no back, no skip — this screen requires a deliberate choice.

- [ ] Replace the entire contents of `frontend/OnboardingPermissionsView.swift`:

```swift
import SwiftUI

struct OnboardingPermissionsView: View {
    let onContinue: () -> Void
    let onMaybeLater: () -> Void

    @StateObject private var notifications = NotificationPermissionManager()

    var body: some View {
        VStack(spacing: 0) {
            OnboardingProgressDots(current: 3)

            Spacer()

            // Bell icon with pulsing outer ring
            ZStack {
                Circle()
                    .fill(OnboardingTheme.primary.opacity(0.12))
                    .frame(width: 164, height: 164)
                    .modifier(PulsingRingModifier())

                Circle()
                    .fill(OnboardingTheme.iconBackground)
                    .frame(width: 136, height: 136)

                Image(systemName: "bell.badge.fill")
                    .font(.system(size: 52, weight: .semibold))
                    .foregroundColor(OnboardingTheme.primary)
            }

            // Title
            Text("Know the moment\nit's ready")
                .font(OnboardingTheme.serifTitle)
                .foregroundColor(OnboardingTheme.textPrimary)
                .multilineTextAlignment(.center)
                .padding(.top, 28)
                .padding(.horizontal, 24)

            // Body
            Text("After saving a reel, we'll send one notification when it's been transcribed and organized. One per reel. No spam, ever.")
                .font(OnboardingTheme.bodyText)
                .foregroundColor(OnboardingTheme.textMuted)
                .multilineTextAlignment(.center)
                .padding(.top, 16)
                .padding(.horizontal, 28)

            // Privacy reassurance
            HStack(alignment: .top, spacing: 8) {
                Image(systemName: "lock.fill")
                    .font(.system(size: 13))
                    .foregroundColor(OnboardingTheme.primary)
                    .padding(.top, 1)
                Text("Notifications only fire when you save something. You're always in control — turn off anytime in Settings.")
                    .font(.system(size: 13))
                    .foregroundColor(OnboardingTheme.textMuted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.horizontal, 28)
            .padding(.top, 16)

            Spacer()

            // CTAs
            VStack(spacing: 14) {
                OnboardingPrimaryButton(title: "Enable Notifications", trailingIcon: nil) {
                    Task { await notifications.requestOrOpenSettings() }
                    onContinue()
                }

                Button(action: onMaybeLater) {
                    Text("Not right now")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(OnboardingTheme.textMuted)
                }
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 40)
        }
        .task { await notifications.refresh() }
    }
}

// Pulsing outer ring — scales up and fades out on repeat
private struct PulsingRingModifier: ViewModifier {
    @State private var animating = false

    func body(content: Content) -> some View {
        content
            .scaleEffect(animating ? 1.15 : 0.85)
            .opacity(animating ? 0 : 0.7)
            .onAppear {
                withAnimation(.easeInOut(duration: 1.8).repeatForever(autoreverses: false)) {
                    animating = true
                }
            }
    }
}

#Preview {
    OnboardingPermissionsView(onContinue: {}, onMaybeLater: {})
        .background(OnboardingTheme.background)
}
```

- [ ] Build: `⌘B`. Expected: succeeds. `PermissionRow` and `ToggleControl` in the file are now unreferenced — that's fine, they will disappear when the file is fully replaced.

- [ ] Open Canvas preview. Verify: no header, bell icon visible, pulsing ring animation plays, "Enable Notifications" and "Not right now" are both visible without scrolling, progress dots show dot 4 active.

- [ ] Commit:
```bash
git add frontend/OnboardingPermissionsView.swift
git commit -m "redesign: Notification Permission screen — single-ask, centered layout, pulsing icon, privacy reassurance"
```

---

## Task 5 — Redesign How It Works screen

**Files:**
- Modify: `frontend/OnboardingHowItWorksView.swift`

Replace three scrollable `StepCard` components (each with a step number, large icon, title, body) with a compact single card containing three `HowItWorksRow` entries separated by hairline dividers. Remove "Skip". Add progress dots. Add trust micro-copy.

- [ ] Replace the entire contents of `frontend/OnboardingHowItWorksView.swift`:

```swift
import SwiftUI

struct OnboardingHowItWorksView: View {
    let onBack: () -> Void
    let onSkip: () -> Void
    let onContinue: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            // Back only — no Skip on this screen
            OnboardingHeader(onBack: onBack, onSkip: nil)

            OnboardingProgressDots(current: 1)

            VStack(spacing: 0) {
                // Eyebrow + title
                VStack(alignment: .leading, spacing: 6) {
                    Text("HOW IT WORKS")
                        .font(.system(size: 11, weight: .semibold))
                        .tracking(2)
                        .foregroundColor(OnboardingTheme.primary)

                    Text("Three steps to never\nlose a reel again")
                        .font(OnboardingTheme.serifSection)
                        .foregroundColor(OnboardingTheme.textPrimary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 24)
                .padding(.top, 20)
                .padding(.bottom, 16)

                // Three rows in one card
                VStack(spacing: 0) {
                    HowItWorksRow(
                        icon: "square.and.arrow.up",
                        title: "Save from Instagram",
                        body: "Share any reel to ReelMind the same way you'd share a link. Three taps."
                    )
                    Divider()
                        .background(OnboardingTheme.divider)
                        .padding(.horizontal, 16)
                    HowItWorksRow(
                        icon: "brain.head.profile",
                        title: "AI does the work",
                        body: "We transcribe it, understand it, and organize it automatically. Nothing to set up."
                    )
                    Divider()
                        .background(OnboardingTheme.divider)
                        .padding(.horizontal, 16)
                    HowItWorksRow(
                        icon: "magnifyingglass",
                        title: "Find anything, anytime",
                        body: "Ask in plain English. \"That pasta recipe from last week.\" Done."
                    )
                }
                .background(Color.white)
                .clipShape(RoundedRectangle(cornerRadius: 18))
                .overlay(
                    RoundedRectangle(cornerRadius: 18)
                        .stroke(OnboardingTheme.divider, lineWidth: 0.5)
                )
                .shadow(color: OnboardingTheme.primary.opacity(0.05), radius: 10, x: 0, y: 4)
                .padding(.horizontal, 20)

                // Trust micro-copy
                Text("You choose what to save. We never collect anything automatically.")
                    .font(.system(size: 12))
                    .foregroundColor(OnboardingTheme.textMuted)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
                    .padding(.top, 14)
            }

            Spacer()

            OnboardingPrimaryButton(title: "Show Me How", action: onContinue)
                .padding(.horizontal, 24)
                .padding(.bottom, 32)
        }
    }
}

private struct HowItWorksRow: View {
    let icon: String
    let title: String
    let body: String

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            ZStack {
                RoundedRectangle(cornerRadius: 11)
                    .fill(OnboardingTheme.iconBackground)
                    .frame(width: 44, height: 44)
                Image(systemName: icon)
                    .font(.system(size: 19, weight: .semibold))
                    .foregroundColor(OnboardingTheme.primary)
            }
            .padding(.top, 2)

            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.system(size: 16, weight: .bold, design: .serif))
                    .foregroundColor(OnboardingTheme.textPrimary)
                Text(body)
                    .font(.system(size: 13))
                    .foregroundColor(OnboardingTheme.textMuted)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer()
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
    }
}

#Preview {
    OnboardingHowItWorksView(onBack: {}, onSkip: {}, onContinue: {})
        .background(OnboardingTheme.background)
}
```

- [ ] Build: `⌘B`. `StepCard` is now unused in this file — that's fine, the struct will be gone once the file is replaced.

- [ ] Open Canvas preview. Verify: three-row card with no scroll visible on a standard iPhone frame, trust line below the card, "Show Me How" CTA, no "Skip" button in the header.

- [ ] Commit:
```bash
git add frontend/OnboardingHowItWorksView.swift
git commit -m "redesign: How It Works — row layout replaces StepCards, plain-language copy, trust micro-copy, no Skip"
```

---

## Task 6 — Polish Share Tutorial screen

**Files:**
- Modify: `frontend/OnboardingShareTutorialView.swift`

Three targeted changes: (1) eyebrow and headline copy, (2) CTA copy, (3) pulsing caramel ring on the "Select ReelMind" row in the phone mockup. Remove Skip.

- [ ] Replace the entire contents of `frontend/OnboardingShareTutorialView.swift`:

```swift
import SwiftUI

struct OnboardingShareTutorialView: View {
    let onBack: () -> Void
    let onSkip: () -> Void
    let onContinue: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            // Back only — no Skip, this education is too important to bypass
            OnboardingHeader(onBack: onBack, onSkip: nil)

            OnboardingProgressDots(current: 2)

            ScrollView {
                VStack(spacing: 24) {
                    VStack(spacing: 8) {
                        Text("HOW TO SAVE")
                            .font(.system(size: 13, weight: .semibold))
                            .tracking(2)
                            .foregroundColor(OnboardingTheme.primary)

                        Text("From Instagram in 3 taps")
                            .font(OnboardingTheme.serifSection)
                            .foregroundColor(OnboardingTheme.textPrimary)
                    }
                    .padding(.top, 16)

                    SharePhoneMockup()
                        .padding(.horizontal, 24)

                    VStack(spacing: 18) {
                        TutorialStep(index: 1, text: "Open any reel in Instagram.")
                        TutorialStep(index: 2, text: "Tap Share", trailingIcon: "square.and.arrow.up")
                        TutorialStep(index: 3, text: "Select ReelMind.", isHighlighted: true)
                    }
                    .padding(.top, 8)
                    .padding(.horizontal, 32)
                }
                .padding(.bottom, 24)
            }

            OnboardingPrimaryButton(title: "I'm Ready", trailingIcon: nil, action: onContinue)
                .padding(.horizontal, 24)
                .padding(.bottom, 32)
        }
    }
}

private struct TutorialStep: View {
    let index: Int
    let text: String
    var trailingIcon: String? = nil
    var isHighlighted: Bool = false

    var body: some View {
        HStack(spacing: 18) {
            Text("\(index)")
                .font(.system(size: 16, weight: .semibold))
                .foregroundColor(isHighlighted ? .white : OnboardingTheme.primary)
                .frame(width: 36, height: 36)
                .background(isHighlighted ? OnboardingTheme.primary : OnboardingTheme.iconBackground)
                .clipShape(Circle())

            HStack(spacing: 6) {
                Text(text)
                    .font(.system(size: 18, weight: isHighlighted ? .bold : .medium))
                    .foregroundColor(isHighlighted ? OnboardingTheme.primary : OnboardingTheme.textPrimary)
                if let icon = trailingIcon {
                    Image(systemName: icon)
                        .font(.system(size: 16, weight: .medium))
                        .foregroundColor(OnboardingTheme.textPrimary)
                }
            }

            Spacer()
        }
    }
}

private struct SharePhoneMockup: View {
    @State private var pulse = false

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 24)
                .fill(OnboardingTheme.cardSurface)
                .frame(height: 260)
                .overlay(
                    RoundedRectangle(cornerRadius: 24)
                        .stroke(OnboardingTheme.divider, lineWidth: 0.5)
                )

            VStack(spacing: 0) {
                // Reel thumbnail
                ZStack {
                    RoundedRectangle(cornerRadius: 28)
                        .fill(LinearGradient(
                            colors: [AppTheme.accentDark, AppTheme.accent],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        ))
                        .frame(width: 130, height: 200)

                    ZStack {
                        Circle()
                            .fill(Color.white.opacity(0.2))
                            .frame(width: 60, height: 60)
                        Image(systemName: "play.fill")
                            .font(.system(size: 22))
                            .foregroundColor(.white)
                    }
                }
                .padding(.top, -10)

                // ReelMind share row with pulsing ring
                HStack(spacing: 10) {
                    ZStack {
                        RoundedRectangle(cornerRadius: 8)
                            .fill(OnboardingTheme.primary)
                            .frame(width: 36, height: 36)
                        Image(systemName: "sparkles")
                            .font(.system(size: 16, weight: .bold))
                            .foregroundColor(.white)
                    }
                    Text("Select ReelMind")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(OnboardingTheme.textPrimary)
                    Spacer()
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 12)
                .background(Color.white)
                .clipShape(RoundedRectangle(cornerRadius: 14))
                .overlay(
                    RoundedRectangle(cornerRadius: 14)
                        .stroke(OnboardingTheme.primary, lineWidth: 2)
                        .opacity(pulse ? 0 : 0.9)
                        .scaleEffect(pulse ? 1.06 : 1.0)
                        .animation(.easeInOut(duration: 1.4).repeatForever(autoreverses: false), value: pulse)
                )
                .shadow(color: OnboardingTheme.primary.opacity(0.12), radius: 10, x: 0, y: 4)
                .padding(.top, 14)
                .padding(.horizontal, 16)
            }
        }
        .onAppear {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) {
                pulse = true
            }
        }
    }
}

#Preview {
    OnboardingShareTutorialView(onBack: {}, onSkip: {}, onContinue: {})
        .background(OnboardingTheme.background)
}
```

- [ ] Build: `⌘B`. Expected: succeeds. The old `PhoneMockup` private struct is now replaced by `SharePhoneMockup`.

- [ ] Open Canvas preview. Verify: eyebrow reads "HOW TO SAVE", headline reads "From Instagram in 3 taps", CTA reads "I'm Ready", no Skip button, pulsing ring appears on "Select ReelMind" row after ~0.8s.

- [ ] Commit:
```bash
git add frontend/OnboardingShareTutorialView.swift
git commit -m "polish: Share Tutorial — copy, no Skip, pulsing ring on ReelMind share row"
```

---

## Task 7 — Polish Splash subtitle copy

**Files:**
- Modify: `frontend/OnboardingSplashView.swift`

Single line change. The current subtitle introduces "insights" as a second value prop before the user understands the first. The new copy is cleaner and introduces the AI angle directly.

- [ ] Open `frontend/OnboardingSplashView.swift`. Find and replace the subtitle `Text`:

```swift
// Before — line ~27
Text("Save Instagram reels. Ask questions.\nDiscover insights you didn't know you had.")

// After
Text("Save any Instagram reel. Ask questions later.\nYour AI-powered second brain.")
```

- [ ] Build: `⌘B`.

- [ ] Commit:
```bash
git add frontend/OnboardingSplashView.swift
git commit -m "polish: Splash subtitle — cleaner copy, introduces AI angle directly"
```

---

## Task 8 — Polish Complete screen

**Files:**
- Modify: `frontend/OnboardingCompleteView.swift`

Five changes: (1) replace "WELCOME HOME" eyebrow with a sparkles icon, (2) add subtitle below the headline, (3) add a fourth sample query row, (4) update CTA from "Enter ReelMind" to "Open My Library", (5) add a trust lock line below the CTA. Add progress dots.

- [ ] Replace the entire contents of `frontend/OnboardingCompleteView.swift`:

```swift
import SwiftUI

struct OnboardingCompleteView: View {
    let onEnter: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            OnboardingProgressDots(current: 4)

            Spacer().frame(height: 28)

            // Sparkle icon + headline + subtitle (left-aligned)
            VStack(alignment: .leading, spacing: 8) {
                Image(systemName: "sparkles")
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundColor(OnboardingTheme.primary)

                Text("Your second\nbrain is ready.")
                    .font(OnboardingTheme.serifTitle)
                    .foregroundColor(OnboardingTheme.textPrimary)

                Text("Save your first reel and watch your library come to life.")
                    .font(OnboardingTheme.bodyText)
                    .foregroundColor(OnboardingTheme.textMuted)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 24)

            Spacer().frame(height: 28)

            // Sample queries card
            VStack(spacing: 14) {
                HStack {
                    Image(systemName: "sparkles")
                        .font(.system(size: 20, weight: .bold))
                        .foregroundColor(OnboardingTheme.primary)
                    Text("Ask about anything you've saved")
                        .font(.system(size: 18, weight: .semibold, design: .serif))
                        .foregroundColor(OnboardingTheme.textMuted)
                        .lineLimit(1)
                }
                .padding(.bottom, 8)

                Divider()

                SampleQueryRow(icon: "clock.arrow.circlepath", text: "\"Skincare routines from last month\"")
                SampleQueryRow(icon: "bookmark",               text: "\"Productivity tips I bookmarked\"")
                SampleQueryRow(icon: "fork.knife",             text: "\"Pasta recipes\"")
                SampleQueryRow(icon: "heart",                  text: "\"Reels I keep coming back to\"")
            }
            .padding(20)
            .background(OnboardingTheme.cardSurface)
            .clipShape(RoundedRectangle(cornerRadius: 18))
            .overlay(
                RoundedRectangle(cornerRadius: 18)
                    .stroke(OnboardingTheme.divider, lineWidth: 0.5)
            )
            .shadow(color: OnboardingTheme.primary.opacity(0.06), radius: 12, x: 0, y: 6)
            .padding(.horizontal, 20)

            Spacer()

            // CTA + trust line
            VStack(spacing: 12) {
                OnboardingPrimaryButton(
                    title: "Open My Library",
                    background: OnboardingTheme.primaryDark,
                    action: onEnter
                )

                HStack(spacing: 5) {
                    Image(systemName: "lock.fill")
                        .font(.system(size: 11))
                    Text("Private by default. Only you can see your library.")
                        .font(.system(size: 12))
                }
                .foregroundColor(OnboardingTheme.textMuted)
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 40)
        }
    }
}

private struct SampleQueryRow: View {
    let icon: String
    let text: String

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: icon)
                .font(.system(size: 18, weight: .semibold))
                .foregroundColor(OnboardingTheme.primary)
                .frame(width: 24)

            Text(text)
                .font(.system(size: 16))
                .foregroundColor(OnboardingTheme.textPrimary)

            Spacer()
        }
        .padding(14)
        .background(OnboardingTheme.iconBackground.opacity(0.4))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

#Preview {
    OnboardingCompleteView(onEnter: {})
        .background(OnboardingTheme.background)
}
```

- [ ] Build: `⌘B`. Expected: succeeds.

- [ ] Open Canvas preview. Verify: sparkles icon at top (no "WELCOME HOME" text), subtitle visible below headline, 4 query rows, "Open My Library" CTA, lock icon + trust line at bottom, progress dots show all 5 visited.

- [ ] Commit:
```bash
git add frontend/OnboardingCompleteView.swift
git commit -m "polish: Complete screen — subtitle, 4th query row, 'Open My Library' CTA, trust lock line"
```

---

## Task 9 — Create `ProcessingOrb` and integrate in reel cards

**Files:**
- Create: `frontend/ProcessingOrb.swift`
- Modify: `frontend/Views/Components/ReelCardView.swift`

The pulsing sphere from the removed Organizing screen is reused here as the thumbnail placeholder shown while a reel has `status == "queued"` or `status == "processing"`. `Reel.status` is a `String` (see `frontend/TempReels/Reel.swift`). The two card variants that show thumbnails are `InboxReelCard` and `DetailReelCard`, both in `ReelCardView.swift`.

**Step A: Create ProcessingOrb**

- [ ] Create `frontend/ProcessingOrb.swift`:

```swift
import SwiftUI

/// Animated pulsing gradient sphere — shown as thumbnail placeholder
/// while a reel is queued or processing.
/// Extracted from OnboardingOrganizingView.
struct ProcessingOrb: View {
    @State private var pulse = false

    var body: some View {
        ZStack {
            Circle()
                .fill(OnboardingTheme.primary.opacity(0.12))
                .frame(
                    width: pulse ? 220 : 180,
                    height: pulse ? 220 : 180
                )
                .blur(radius: 4)

            Circle()
                .fill(
                    LinearGradient(
                        colors: [OnboardingTheme.primary, OnboardingTheme.primaryDark],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .frame(width: 130, height: 130)
                .overlay(
                    Circle()
                        .fill(
                            RadialGradient(
                                colors: [Color.white.opacity(0.35), .clear],
                                center: .topLeading,
                                startRadius: 4,
                                endRadius: 60
                            )
                        )
                        .frame(width: 130, height: 130)
                )
                .shadow(
                    color: OnboardingTheme.primary.opacity(0.4),
                    radius: 16, x: 0, y: 8
                )
        }
        .onAppear {
            withAnimation(.easeInOut(duration: 1.4).repeatForever(autoreverses: true)) {
                pulse = true
            }
        }
    }
}

#Preview {
    ProcessingOrb()
        .frame(width: 220, height: 220)
        .background(OnboardingTheme.background)
}
```

- [ ] Build: `⌘B`. Expected: succeeds.

**Step B: Integrate in `InboxReelCard`**

The `inboxThumbnail` computed property in `InboxReelCard` (line ~119 in `ReelCardView.swift`) currently checks only for `thumbnailUrl`. Add a status check before the URL check:

- [ ] In `frontend/Views/Components/ReelCardView.swift`, find `private var inboxThumbnail: some View` and replace its `Group { ... }` content:

```swift
// Before — the Group block inside inboxThumbnail:
Group {
    if let str = reel.thumbnailUrl, let url = URL(string: str) {
        AsyncImage(url: url) { phase in
            switch phase {
            case .success(let image):
                image.resizable().scaledToFill().clipped()
            case .empty:
                inboxThumbnailPlaceholder
                    .overlay(ProgressView().scaleEffect(0.6).tint(AppTheme.textFaint))
            default:
                inboxThumbnailPlaceholder
            }
        }
    } else {
        inboxThumbnailPlaceholder
    }
}

// After — status check added first:
Group {
    if reel.status == "queued" || reel.status == "processing" {
        ProcessingOrb()
    } else if let str = reel.thumbnailUrl, let url = URL(string: str) {
        AsyncImage(url: url) { phase in
            switch phase {
            case .success(let image):
                image.resizable().scaledToFill().clipped()
            case .empty:
                inboxThumbnailPlaceholder
                    .overlay(ProgressView().scaleEffect(0.6).tint(AppTheme.textFaint))
            default:
                inboxThumbnailPlaceholder
            }
        }
    } else {
        inboxThumbnailPlaceholder
    }
}
```

**Step C: Integrate in `DetailReelCard`**

`DetailReelCard` uses `ThumbnailView(urlString: reel.thumbnailUrl, width: 90, height: 130)` directly (line ~180).

- [ ] In `frontend/Views/Components/ReelCardView.swift`, find the `ThumbnailView(urlString: reel.thumbnailUrl, width: 90, height: 130)` call inside `DetailReelCard.body` and wrap it:

```swift
// Before:
ThumbnailView(urlString: reel.thumbnailUrl, width: 90, height: 130)

// After:
Group {
    if reel.status == "queued" || reel.status == "processing" {
        ProcessingOrb()
            .frame(width: 90, height: 130)
            .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
    } else {
        ThumbnailView(urlString: reel.thumbnailUrl, width: 90, height: 130)
    }
}
```

- [ ] Build: `⌘B`. Expected: succeeds with no errors.

- [ ] Open Canvas preview for `ReelCardView.swift`. Verify the preview still renders correctly for cards with non-processing status.

- [ ] Commit:
```bash
git add frontend/ProcessingOrb.swift frontend/Views/Components/ReelCardView.swift
git commit -m "feat: ProcessingOrb shown as thumbnail placeholder for queued/processing reels"
```

---

## Task 10 — Delete `OnboardingOrganizingView.swift`

**Files:**
- Delete: `frontend/OnboardingOrganizingView.swift`

The file is now fully unused — removed from `OnboardingFlow` in Task 1 and its animation extracted to `ProcessingOrb` in Task 9.

- [ ] In Xcode's Project Navigator, right-click `OnboardingOrganizingView.swift` → **Delete** → **Move to Trash** (not just "Remove Reference").

- [ ] Build: `⌘B`. Expected: succeeds with no reference errors.

- [ ] Commit:
```bash
git commit -m "chore: delete OnboardingOrganizingView — removed from flow, animation lives in ProcessingOrb"
```

---

## Task 11 — End-to-end flow verification

No code changes — verification only.

- [ ] Reset onboarding state so the flow triggers on next launch. In the Xcode debug console (while paused or via a debug action):
```swift
UserDefaults.standard.removeObject(forKey: "hasCompletedOnboarding")
```
Or: in the simulator, **Device → Erase All Content and Settings**.

- [ ] Run the app: `⌘R` on iPhone 15 Pro simulator (or physical device).

- [ ] Walk all 5 screens and verify:

| Screen | What to verify |
|--------|---------------|
| **Splash** | Subtitle reads "Save any Instagram reel. Ask questions later. / Your AI-powered second brain." No chrome. |
| **How It Works** | Header shows back arrow only (no Skip). Progress dot 2 active. Three rows in a single card, no scroll on iPhone 15 Pro. Trust line below card. CTA reads "Show Me How". |
| **Share Tutorial** | Eyebrow "HOW TO SAVE". Headline "From Instagram in 3 taps". Progress dot 3 active. Back button only (no Skip). Pulsing ring appears on "Select ReelMind" row ~0.8s after screen loads. CTA reads "I'm Ready". |
| **Notification Permission** | No header, no back, no skip. Progress dot 4 active. Bell icon with pulsing outer ring. Body copy mentions "One per reel. No spam, ever." Two CTAs: "Enable Notifications" and "Not right now". |
| **Complete** | Sparkle icon (no "WELCOME HOME" text). Subtitle "Save your first reel…" present. 4 query rows including "Reels I keep coming back to". CTA reads "Open My Library". Lock trust line visible. |

- [ ] Tap "Not right now" on the Notification screen. Verify: advances to Complete without triggering iOS permission dialog.

- [ ] Re-run the flow and tap "Enable Notifications". Verify: iOS system notification permission dialog appears.

- [ ] Tap "Open My Library" on the Complete screen. Verify: transitions to `ContentView` (`LibraryView`).

- [ ] If any issues found, fix inline and commit:
```bash
git add -p
git commit -m "fix: onboarding verification corrections"
```

---

## Commit log summary (expected order)

```
fix: remove organizing step from onboarding — no reels exist at this point in the flow
fix: remove fake Share Sheet Access permission row — Share Extensions need no permission grant on iOS
feat: add OnboardingProgressDots shared component for screens 2–5
redesign: Notification Permission screen — single-ask, centered layout, pulsing icon, privacy reassurance
redesign: How It Works — row layout replaces StepCards, plain-language copy, trust micro-copy, no Skip
polish: Share Tutorial — copy, no Skip, pulsing ring on ReelMind share row
polish: Splash subtitle — cleaner copy, introduces AI angle directly
polish: Complete screen — subtitle, 4th query row, 'Open My Library' CTA, trust lock line
feat: ProcessingOrb shown as thumbnail placeholder for queued/processing reels
chore: delete OnboardingOrganizingView — removed from flow, animation lives in ProcessingOrb
```
