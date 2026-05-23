import SwiftUI

struct SocialAuthDivider: View {
    var body: some View {
        HStack(spacing: 12) {
            Rectangle()
                .fill(AppTheme.border)
                .frame(height: 0.5)
            Text("or")
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(AppTheme.textMuted)
            Rectangle()
                .fill(AppTheme.border)
                .frame(height: 0.5)
        }
    }
}

struct SocialAuthButton: View {
    let systemIcon: String?
    let textIcon: String?
    let label: String
    let action: () async -> Void

    @State private var isLoading = false

    init(systemIcon: String, label: String, action: @escaping () async -> Void) {
        self.systemIcon = systemIcon
        self.textIcon = nil
        self.label = label
        self.action = action
    }

    init(textIcon: String, label: String, action: @escaping () async -> Void) {
        self.systemIcon = nil
        self.textIcon = textIcon
        self.label = label
        self.action = action
    }

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
                    if let sys = systemIcon {
                        Image(systemName: sys)
                            .font(.system(size: 18))
                            .foregroundColor(AppTheme.textPrimary)
                    } else if let txt = textIcon {
                        Text(txt)
                            .font(.system(size: 18, weight: .semibold))
                            .foregroundColor(AppTheme.textPrimary)
                    }
                    Text(label)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(AppTheme.textPrimary)
                }
                .opacity(isLoading ? 0 : 1)

                if isLoading {
                    ProgressView()
                        .tint(AppTheme.textPrimary)
                }
            }
            .frame(maxWidth: .infinity)
            .frame(height: 54)
            .background(AppTheme.surface)
            .clipShape(Capsule())
            .overlay(Capsule().stroke(AppTheme.border, lineWidth: 0.5))
        }
        .disabled(isLoading)
    }
}
