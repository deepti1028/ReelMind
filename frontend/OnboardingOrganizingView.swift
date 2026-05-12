import SwiftUI

struct OnboardingOrganizingView: View {
    let onBack: () -> Void
    let onSkip: () -> Void
    let onContinue: () -> Void

    @State private var pulse = false

    var body: some View {
        VStack(spacing: 0) {
            OnboardingHeader(onBack: onBack, onSkip: onSkip)

            Spacer()

            ZStack {
                Circle()
                    .fill(OnboardingTheme.primary.opacity(0.12))
                    .frame(width: pulse ? 220 : 180, height: pulse ? 220 : 180)
                    .blur(radius: 4)

                Circle()
                    .fill(
                        LinearGradient(
                            colors: [
                                OnboardingTheme.primary,
                                OnboardingTheme.primaryDark
                            ],
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
                    .shadow(color: OnboardingTheme.primary.opacity(0.4), radius: 16, x: 0, y: 8)
            }
            .onAppear {
                withAnimation(.easeInOut(duration: 1.4).repeatForever(autoreverses: true)) {
                    pulse = true
                }
            }

            Text("Organizing your library")
                .font(OnboardingTheme.serifSection)
                .foregroundColor(OnboardingTheme.textPrimary)
                .multilineTextAlignment(.leading)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.top, 60)
                .padding(.horizontal, 24)

            Text("We're currently transcribing and indexing your reels. This happens in the background so you can keep exploring.")
                .font(OnboardingTheme.bodyText)
                .foregroundColor(OnboardingTheme.textMuted)
                .multilineTextAlignment(.center)
                .padding(.top, 16)
                .padding(.horizontal, 32)

            Spacer()

            OnboardingPrimaryButton(title: "Next", trailingIcon: nil, action: onContinue)
                .padding(.horizontal, 24)
                .padding(.bottom, 32)
        }
    }
}
