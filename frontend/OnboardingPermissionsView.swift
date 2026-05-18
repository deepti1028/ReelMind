import SwiftUI

struct OnboardingPermissionsView: View {
    let onContinue: () -> Void
    let onMaybeLater: () -> Void

    @AppStorage("shareSheetAcknowledged") private var shareSheetAcknowledged = false
    @StateObject private var notifications = NotificationPermissionManager()
    @State private var showShareSheetDemo = false

    var body: some View {
        VStack(spacing: 0) {
            Spacer().frame(height: 24)

            ZStack {
                Circle()
                    .fill(OnboardingTheme.iconBackground)
                    .frame(width: 120, height: 120)

                Image(systemName: "checkmark.shield.fill")
                    .font(.system(size: 48, weight: .semibold))
                    .foregroundColor(OnboardingTheme.primary)

                Circle()
                    .fill(OnboardingTheme.iconBackground)
                    .frame(width: 36, height: 36)
                    .overlay(
                        Image(systemName: "link")
                            .font(.system(size: 14, weight: .bold))
                            .foregroundColor(OnboardingTheme.primary)
                    )
                    .offset(x: 44, y: 38)
            }
            .padding(.top, 16)

            Text("Stay connected")
                .font(OnboardingTheme.serifTitle)
                .foregroundColor(OnboardingTheme.textPrimary)
                .padding(.top, 28)

            Spacer().frame(height: 28)

            VStack(spacing: 14) {
                PermissionRow(
                    icon: "square.and.arrow.up",
                    title: "Share Sheet Access",
                    description: "Save reels without leaving Instagram.",
                    isOn: shareSheetAcknowledged,
                    statusText: nil,
                    onToggle: { showShareSheetDemo = true }
                )

                PermissionRow(
                    icon: "bell.fill",
                    title: "Notifications",
                    description: notificationDescription,
                    isOn: notifications.status == .authorized,
                    statusText: notificationStatusText,
                    onToggle: {
                        Task { await notifications.requestOrOpenSettings() }
                    }
                )
            }
            .padding(.horizontal, 20)

            Spacer()

            VStack(spacing: 14) {
                OnboardingPrimaryButton(title: "Grant Access", trailingIcon: nil, action: onContinue)

                Button(action: onMaybeLater) {
                    Text("Maybe Later")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(OnboardingTheme.textMuted)
                }
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 32)
        }
        .task { await notifications.refresh() }
        .sheet(isPresented: $showShareSheetDemo) {
            ShareSheetPresenter(
                items: ["Try sharing this with ReelMind from your favorites!"],
                onDismiss: {
                    shareSheetAcknowledged = true
                    showShareSheetDemo = false
                }
            )
        }
    }

    private var notificationDescription: String {
        switch notifications.status {
        case .denied:
            return "Notifications are disabled. Tap the toggle to open Settings."
        default:
            return "Get alerted when your reels are ready and categorized."
        }
    }

    private var notificationStatusText: String? {
        switch notifications.status {
        case .denied: return "Tap to open Settings"
        default: return nil
        }
    }
}

private struct PermissionRow: View {
    let icon: String
    let title: String
    let description: String
    let isOn: Bool
    let statusText: String?
    let onToggle: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            ZStack {
                RoundedRectangle(cornerRadius: 10)
                    .fill(OnboardingTheme.iconBackground)
                    .frame(width: 44, height: 44)
                Image(systemName: icon)
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(OnboardingTheme.primary)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.system(size: 20, weight: .bold, design: .serif))
                    .foregroundColor(OnboardingTheme.textPrimary)

                Text(description)
                    .font(.system(size: 14))
                    .foregroundColor(OnboardingTheme.textMuted)
                    .fixedSize(horizontal: false, vertical: true)

                if let statusText = statusText {
                    Text(statusText)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(OnboardingTheme.primary)
                        .padding(.top, 2)
                }
            }

            Spacer()

            ToggleControl(isOn: isOn, action: onToggle)
        }
        .padding(16)
        .background(OnboardingTheme.cardSurface)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(OnboardingTheme.divider, lineWidth: 0.5)
        )
    }
}

private struct ToggleControl: View {
    let isOn: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            ZStack(alignment: isOn ? .trailing : .leading) {
                Capsule()
                    .fill(isOn ? OnboardingTheme.primary : AppTheme.border)
                    .frame(width: 50, height: 30)

                Circle()
                    .fill(Color.white)
                    .frame(width: 26, height: 26)
                    .padding(.horizontal, 2)
                    .shadow(color: .black.opacity(0.1), radius: 2, x: 0, y: 1)
            }
        }
        .animation(.easeInOut(duration: 0.2), value: isOn)
    }
}
