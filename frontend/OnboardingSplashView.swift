import SwiftUI

struct OnboardingSplashView: View {
    let onContinue: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            Spacer()

            ZStack {
                Circle()
                    .fill(Color.white)
                    .frame(width: 140, height: 140)
                    .shadow(color: OnboardingTheme.primary.opacity(0.10), radius: 20, x: 0, y: 8)

                Image(systemName: "sparkles")
                    .font(.system(size: 56, weight: .semibold))
                    .foregroundColor(OnboardingTheme.primary)
            }

            Text("Your reels.\nFinally\nremembered.")
                .font(OnboardingTheme.serifTitle)
                .foregroundColor(OnboardingTheme.textPrimary)
                .multilineTextAlignment(.center)
                .padding(.top, 16)

            Text("Save Instagram reels. Ask questions.\nDiscover insights you didn't know you had.")
                .font(OnboardingTheme.bodyText)
                .foregroundColor(OnboardingTheme.textMuted)
                .multilineTextAlignment(.center)
                .padding(.top, 24)
                .padding(.horizontal, 24)

            Spacer()

            OnboardingPrimaryButton(title: "Get Started", action: onContinue)
                .padding(.horizontal, 24)
                .padding(.bottom, 40)
        }
    }
}
