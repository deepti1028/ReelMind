import SwiftUI

struct OnboardingHowItWorksView: View {
    let onBack: () -> Void
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
    OnboardingHowItWorksView(onBack: {}, onContinue: {})
        .background(OnboardingTheme.background)
}
