import SwiftUI

struct OnboardingHowItWorksView: View {
    let onBack: () -> Void
    let onSkip: () -> Void
    let onContinue: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            OnboardingHeader(onBack: onBack, onSkip: onSkip)

            ScrollView {
                VStack(spacing: 20) {
                    VStack(spacing: 12) {
                        Text("How it works")
                            .font(OnboardingTheme.serifSection)
                            .foregroundColor(OnboardingTheme.textPrimary)
                            .frame(maxWidth: .infinity, alignment: .leading)

                        Text("Turn your ephemeral scrolling into a permanent, searchable intelligence base in three simple steps.")
                            .font(OnboardingTheme.bodyText)
                            .foregroundColor(OnboardingTheme.textMuted)
                            .multilineTextAlignment(.center)
                    }
                    .padding(.top, 16)
                    .padding(.horizontal, 24)

                    StepCard(
                        index: 1,
                        icon: "square.and.arrow.up",
                        title: "Save from Instagram",
                        description: "Share any reel directly to ReelMind via the native share sheet. No links to copy."
                    )

                    StepCard(
                        index: 2,
                        icon: "brain.head.profile",
                        title: "AI understands it",
                        description: "We transcribe, categorize, and index every detail. Your content becomes instantly organized."
                    )

                    StepCard(
                        index: 3,
                        icon: "magnifyingglass",
                        title: "Ask anything",
                        description: "Find any reel using natural language search, just like asking a knowledgeable assistant.",
                        footer: AnyView(
                            HStack(spacing: 8) {
                                Image(systemName: "sparkles")
                                    .font(.system(size: 12))
                                Text("\"Find the reel about dopamine and focus\"")
                                    .font(.system(size: 13, weight: .regular).italic())
                            }
                            .foregroundColor(OnboardingTheme.primary)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 10)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(OnboardingTheme.iconBackground)
                            .clipShape(RoundedRectangle(cornerRadius: 10))
                        )
                    )
                }
                .padding(.horizontal, 20)
                .padding(.bottom, 24)
            }

            OnboardingPrimaryButton(title: "Continue", action: onContinue)
                .padding(.horizontal, 24)
                .padding(.bottom, 32)
        }
    }
}

private struct StepCard: View {
    let index: Int
    let icon: String
    let title: String
    let description: String
    var footer: AnyView? = nil

    var body: some View {
        VStack(spacing: 14) {
            Text("\(index)")
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(OnboardingTheme.primary)
                .frame(width: 28, height: 28)
                .background(OnboardingTheme.iconBackground)
                .clipShape(Circle())

            ZStack {
                Circle()
                    .fill(OnboardingTheme.iconBackground)
                    .frame(width: 56, height: 56)
                Image(systemName: icon)
                    .font(.system(size: 22, weight: .semibold))
                    .foregroundColor(OnboardingTheme.primary)
            }

            Text(title)
                .font(.system(size: 22, weight: .bold, design: .serif))
                .foregroundColor(OnboardingTheme.textPrimary)

            Text(description)
                .font(OnboardingTheme.bodyText)
                .foregroundColor(OnboardingTheme.textMuted)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 12)

            if let footer = footer {
                footer.padding(.top, 4)
            }
        }
        .padding(.vertical, 22)
        .padding(.horizontal, 18)
        .frame(maxWidth: .infinity)
        .background(OnboardingTheme.cardSurface)
        .clipShape(RoundedRectangle(cornerRadius: 18))
        .overlay(
            RoundedRectangle(cornerRadius: 18)
                .stroke(OnboardingTheme.divider, lineWidth: 0.5)
        )
        .shadow(color: OnboardingTheme.primary.opacity(0.05), radius: 10, x: 0, y: 4)
    }
}
