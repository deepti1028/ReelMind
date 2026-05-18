import SwiftUI

struct OnboardingShareTutorialView: View {
    let onBack: () -> Void
    let onSkip: () -> Void
    let onContinue: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            OnboardingHeader(onBack: onBack, onSkip: onSkip)

            ScrollView {
                VStack(spacing: 24) {
                    VStack(spacing: 8) {
                        Text("THE SHARE SHEET")
                            .font(.system(size: 13, weight: .semibold))
                            .tracking(2)
                            .foregroundColor(OnboardingTheme.primary)

                        Text("Save with ease")
                            .font(OnboardingTheme.serifSection)
                            .foregroundColor(OnboardingTheme.textPrimary)
                    }
                    .padding(.top, 16)

                    PhoneMockup()
                        .padding(.horizontal, 24)

                    VStack(spacing: 18) {
                        TutorialStep(index: 1, text: "Open any reel.")
                        TutorialStep(index: 2, text: "Tap Share", trailingIcon: "square.and.arrow.up")
                        TutorialStep(index: 3, text: "Select ReelMind.", isHighlighted: true)
                    }
                    .padding(.top, 8)
                    .padding(.horizontal, 32)
                }
                .padding(.bottom, 24)
            }

            OnboardingPrimaryButton(title: "Got it", trailingIcon: nil, action: onContinue)
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
                    .font(.system(size: 18, weight: .medium))
                    .foregroundColor(OnboardingTheme.textPrimary)

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

private struct PhoneMockup: View {
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
                ZStack {
                    RoundedRectangle(cornerRadius: 28)
                        .fill(LinearGradient(
                            colors: [AppTheme.accentDark, AppTheme.accent],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        ))
                        .frame(width: 130, height: 200)

                    VStack {
                        Spacer()
                        ZStack {
                            Circle()
                                .fill(Color.white.opacity(0.2))
                                .frame(width: 60, height: 60)
                            Image(systemName: "play.fill")
                                .font(.system(size: 22))
                                .foregroundColor(.white)
                        }
                        Spacer()
                    }
                }
                .padding(.top, -10)

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
                .shadow(color: OnboardingTheme.primary.opacity(0.12), radius: 10, x: 0, y: 4)
                .padding(.top, 14)
                .padding(.horizontal, 16)
            }
        }
    }
}
