import SwiftUI

struct OnboardingCompleteView: View {
    let onEnter: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            Spacer().frame(height: 40)

            VStack(spacing: 8) {
                Text("WELCOME HOME")
                    .font(.system(size: 13, weight: .semibold))
                    .tracking(2)
                    .foregroundColor(OnboardingTheme.primary)

                Text("Your second\nbrain is ready")
                    .font(OnboardingTheme.serifTitle)
                    .foregroundColor(OnboardingTheme.textPrimary)
                    .multilineTextAlignment(.center)
                    .padding(.top, 8)
            }
            .padding(.horizontal, 24)

            Spacer().frame(height: 36)

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
                SampleQueryRow(icon: "bookmark", text: "\"Productivity tips I bookmarked\"")
                SampleQueryRow(icon: "fork.knife", text: "\"Pasta recipes\"")
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

            OnboardingPrimaryButton(
                title: "Enter ReelMind",
                background: OnboardingTheme.primaryDark,
                action: onEnter
            )
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
