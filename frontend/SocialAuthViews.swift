import SwiftUI

struct SocialAuthDivider: View {
    var body: some View {
        HStack(spacing: 12) {
            Rectangle()
                .fill(AppTheme.border)
                .frame(height: 0.5)
            Text("or continue with")
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(AppTheme.textMuted)
                .fixedSize()
            Rectangle()
                .fill(AppTheme.border)
                .frame(height: 0.5)
        }
    }
}

struct LabeledAuthField<Field: View>: View {
    let label: String
    @ViewBuilder let field: () -> Field

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label)
                .font(.system(size: 10, weight: .semibold))
                .tracking(1.4)
                .foregroundColor(AppTheme.textMuted)
            field()
                .foregroundColor(AppTheme.textPrimary)
                .tint(AppTheme.accentDark)
                .padding(.horizontal, 16)
                .frame(height: 52)
                .background(AppTheme.surface)
                .cornerRadius(12)
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .stroke(AppTheme.border, lineWidth: 0.5)
                )
        }
    }
}

struct GoogleSignInButton: View {
    let action: () async -> Void
    @State private var isLoading = false

    var body: some View {
        Button {
            guard !isLoading else { return }
            Task {
                isLoading = true
                await action()
                isLoading = false
            }
        } label: {
            ZStack {
                HStack(spacing: 10) {
                    Image("google-logo")
                        .resizable()
                        .renderingMode(.original)
                        .scaledToFit()
                        .frame(width: 20, height: 20)
                    Text("Continue with Google")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(Color(red: 0.235, green: 0.251, blue: 0.263))
                }
                .opacity(isLoading ? 0 : 1)

                if isLoading {
                    ProgressView()
                        .tint(Color(red: 0.235, green: 0.251, blue: 0.263))
                }
            }
            .frame(maxWidth: .infinity)
            .frame(height: 52)
            .background(.white)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(Color(red: 0.855, green: 0.851, blue: 0.878), lineWidth: 1)
            )
            .shadow(color: .black.opacity(0.04), radius: 3, x: 0, y: 1)
        }
        .disabled(isLoading)
    }
}

struct AppleSignInButton: View {
    let action: () async -> Void
    @State private var isLoading = false

    var body: some View {
        Button {
            guard !isLoading else { return }
            Task {
                isLoading = true
                await action()
                isLoading = false
            }
        } label: {
            ZStack {
                HStack(spacing: 10) {
                    Image(systemName: "apple.logo")
                        .font(.system(size: 18))
                        .foregroundColor(.white)
                    Text("Continue with Apple")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(.white)
                }
                .opacity(isLoading ? 0 : 1)

                if isLoading {
                    ProgressView().tint(.white)
                }
            }
            .frame(maxWidth: .infinity)
            .frame(height: 52)
            .background(Color.black)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .shadow(color: .black.opacity(0.18), radius: 8, x: 0, y: 4)
        }
        .disabled(isLoading)
    }
}
