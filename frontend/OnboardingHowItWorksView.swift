import SwiftUI

struct OnboardingHowItWorksView: View {
    let onBack: () -> Void
    let onContinue: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            OnboardingHeader(onBack: onBack, onSkip: nil)

            OnboardingProgressDots(current: 1)

            ScrollView {
                VStack(spacing: 28) {
                    VStack(spacing: 8) {
                        Text("HOW IT WORKS")
                            .font(.system(size: 13, weight: .semibold))
                            .tracking(2)
                            .foregroundColor(OnboardingTheme.primary)

                        Text("Your reel brain\nin four steps")
                            .font(OnboardingTheme.serifSection)
                            .foregroundColor(OnboardingTheme.textPrimary)
                            .multilineTextAlignment(.center)
                    }
                    .padding(.top, 16)

                    VStack(spacing: 16) {
                        HowItWorksCard(
                            icon: "square.and.arrow.up",
                            title: "Share a reel",
                            detail: "Tap Share in Instagram and pick ReelMind — done in seconds."
                        )
                        HowItWorksCard(
                            icon: "waveform",
                            title: "Transcribed instantly",
                            detail: "The audio is transcribed so every word is searchable."
                        )
                        HowItWorksCard(
                            icon: "tag",
                            title: "Auto-categorised",
                            detail: "AI reads the caption and transcript and picks the right category."
                        )
                        HowItWorksCard(
                            icon: "bubble.left.and.text.bubble.right",
                            title: "Ask anything",
                            detail: "Chat with your saved reels. Find that recipe, quote, or tip instantly."
                        )
                    }
                    .padding(.horizontal, 24)
                }
                .padding(.bottom, 24)
            }

            OnboardingPrimaryButton(title: "Next", action: onContinue)
                .padding(.horizontal, 24)
                .padding(.bottom, 32)
        }
    }
}

private struct HowItWorksCard: View {
    let icon: String
    let title: String
    let detail: String

    var body: some View {
        HStack(alignment: .top, spacing: 16) {
            ZStack {
                RoundedRectangle(cornerRadius: 12)
                    .fill(OnboardingTheme.iconBackground)
                    .frame(width: 44, height: 44)
                Image(systemName: icon)
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundColor(OnboardingTheme.primary)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(OnboardingTheme.textPrimary)
                Text(detail)
                    .font(.system(size: 14, weight: .regular))
                    .foregroundColor(OnboardingTheme.textMuted)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer()
        }
        .padding(16)
        .background(OnboardingTheme.cardSurface)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(OnboardingTheme.divider, lineWidth: 0.5)
        )
    }
}

#Preview {
    OnboardingHowItWorksView(onBack: {}, onContinue: {})
        .background(OnboardingTheme.background)
}
