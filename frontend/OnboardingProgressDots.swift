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
