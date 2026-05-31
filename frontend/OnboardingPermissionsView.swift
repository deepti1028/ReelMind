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
