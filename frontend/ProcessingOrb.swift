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
