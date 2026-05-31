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
