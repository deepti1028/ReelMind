import SwiftUI

enum OnboardingStep: Int, CaseIterable {
    case splash
    case howItWorks
    case shareTutorial
    case permissions
    case complete
}

struct OnboardingFlow: View {
    @AppStorage("hasCompletedOnboarding") private var hasCompletedOnboarding = false
    @State private var step: OnboardingStep = .splash

    var body: some View {
        ZStack {
            OnboardingTheme.background.ignoresSafeArea()

            Group {
                switch step {
                case .splash:
                    OnboardingSplashView(onContinue: { advance() })
                case .howItWorks:
                    OnboardingHowItWorksView(
                        onBack: { back() },
                        onContinue: { advance() }
                    )
                case .shareTutorial:
                    OnboardingShareTutorialView(
                        onBack: { back() },
                        onContinue: { advance() }
                    )
                case .permissions:
                    OnboardingPermissionsView(
                        onContinue: { advance() },
                        onMaybeLater: { advance() }
                    )
                case .complete:
                    OnboardingCompleteView(onEnter: { finish() })
                }
            }
            .transition(.asymmetric(
                insertion: .move(edge: .trailing).combined(with: .opacity),
                removal: .move(edge: .leading).combined(with: .opacity)
            ))
        }
        .animation(.easeInOut(duration: 0.28), value: step)
    }

    private func advance() {
        guard let next = OnboardingStep(rawValue: step.rawValue + 1) else {
            finish()
            return
        }
        step = next
    }

    private func back() {
        guard let prev = OnboardingStep(rawValue: step.rawValue - 1) else { return }
        step = prev
    }

    private func skip() {
        step = .complete
    }

    private func finish() {
        hasCompletedOnboarding = true
    }
}

// MARK: - Shared header used across screens with back / skip

struct OnboardingHeader: View {
    let onBack: (() -> Void)?
    let onSkip: (() -> Void)?

    var body: some View {
        HStack {
            if let onBack = onBack {
                Button(action: onBack) {
                    Image(systemName: "arrow.left")
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundColor(OnboardingTheme.primary)
                }
            } else {
                Spacer().frame(width: 24)
            }

            Spacer()

            Text("ReelMind")
                .font(.system(size: 22, weight: .bold, design: .serif))
                .foregroundColor(OnboardingTheme.primary)

            Spacer()

            if let onSkip = onSkip {
                Button("Skip", action: onSkip)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(OnboardingTheme.primary)
            } else {
                Spacer().frame(width: 24)
            }
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 12)
        .overlay(
            Rectangle()
                .fill(OnboardingTheme.divider)
                .frame(height: 0.5),
            alignment: .bottom
        )
    }
}

// MARK: - Shared primary CTA button

struct OnboardingPrimaryButton: View {
    let title: String
    var trailingIcon: String? = "arrow.right"
    var background: Color = OnboardingTheme.primary
    var foreground: Color = .white
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                Text(title)
                    .font(.system(size: 18, weight: .semibold))
                if let trailingIcon = trailingIcon {
                    Image(systemName: trailingIcon)
                        .font(.system(size: 16, weight: .semibold))
                }
            }
            .foregroundColor(foreground)
            .frame(maxWidth: .infinity)
            .frame(height: 58)
            .background(background)
            .clipShape(Capsule())
            .shadow(color: background.opacity(0.25), radius: 12, x: 0, y: 6)
        }
    }
}
