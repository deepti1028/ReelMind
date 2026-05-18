import Auth
import SwiftUI
import UIKit

struct SettingsView: View {
    @EnvironmentObject private var auth: AuthSession
    @Environment(\.dismiss) private var dismiss
    @StateObject private var notifManager = NotificationPermissionManager()
    @AppStorage("autoCategorise") private var autoCategorise = true

    var body: some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()
            VStack(spacing: 0) {
                pageHeader
                ScrollView {
                    VStack(spacing: 0) {
                        userCard
                            .padding(.horizontal, 14)
                            .padding(.bottom, 20)
                        librarySection
                            .padding(.horizontal, 14)
                            .padding(.bottom, 20)
                        savingSection
                            .padding(.horizontal, 14)
                            .padding(.bottom, 20)
                        privacySection
                            .padding(.horizontal, 14)
                    }
                }
            }
        }
        .task { await notifManager.refresh() }
    }

    // MARK: - Header

    private var pageHeader: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Account")
                .font(.system(size: 10, weight: .semibold))
                .foregroundColor(AppTheme.textFaint)
                .textCase(.uppercase)
                .kerning(1.2)
            HStack {
                Text("Settings")
                    .font(.system(size: 28, weight: .bold))
                    .foregroundColor(AppTheme.textPrimary)
                Spacer()
                Button("Sign out") {
                    Task { try? await auth.signOut() }
                }
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(AppTheme.destructive)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 20)
        .padding(.top, 6)
        .padding(.bottom, 14)
    }

    // MARK: - User card

    private var userCard: some View {
        HStack(spacing: 12) {
            Circle()
                .fill(AppTheme.avatarGradient)
                .frame(width: 42, height: 42)
                .overlay(
                    Text(auth.session?.user.email?.prefix(1).uppercased() ?? "?")
                        .font(.system(size: 17, weight: .bold))
                        .foregroundColor(.white)
                )
            VStack(alignment: .leading, spacing: 1) {
                Text(auth.session?.user.userMetadata["full_name"] as? String
                     ?? auth.session?.user.email ?? "—")
                    .font(.system(size: 15, weight: .bold))
                    .foregroundColor(AppTheme.textPrimary)
                Text(auth.session?.user.email ?? "")
                    .font(.system(size: 11))
                    .foregroundColor(AppTheme.textFaint)
            }
            Spacer()
            Button("Edit") {}
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(AppTheme.textMuted)
                .padding(.horizontal, 11)
                .padding(.vertical, 4)
                .background(AppTheme.surfaceSecondary)
                .clipShape(Capsule())
                .overlay(Capsule().stroke(AppTheme.sage, lineWidth: 1))
        }
        .padding(16)
        .background(AppTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(AppTheme.border, lineWidth: 1)
        )
    }

    // MARK: - Sections

    private var librarySection: some View {
        SettingsSection(title: "Library") {
            SettingsRow(icon: "square.grid.2x2", iconBg: AppTheme.surfaceSecondary,
                        label: "Manage categories") {
                Text("6").font(.system(size: 12)).foregroundColor(AppTheme.textFaint)
            }
            Divider().background(AppTheme.border)
            HStack {
                SettingsRowLeft(icon: "cpu", iconBg: AppTheme.surfaceSecondary,
                                label: "Auto-categorise")
                Spacer()
                Toggle("", isOn: $autoCategorise)
                    .tint(AppTheme.accent)
                    .labelsHidden()
                    .scaleEffect(0.85, anchor: .trailing)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 13)
        }
    }

    private var savingSection: some View {
        SettingsSection(title: "Saving") {
            Button {
                if let url = URL(string: UIApplication.openSettingsURLString) {
                    UIApplication.shared.open(url)
                }
            } label: {
                SettingsRow(icon: "square.and.arrow.up", iconBg: AppTheme.surfaceSecondary,
                            label: "Share sheet permissions") {
                    Text("Granted")
                        .font(.system(size: 12))
                        .foregroundColor(AppTheme.accent)
                }
            }
            .buttonStyle(.plain)
            Divider().background(AppTheme.border)
            HStack {
                SettingsRowLeft(icon: "bell", iconBg: AppTheme.surfaceSecondary,
                                label: "Save notifications")
                Spacer()
                Toggle("", isOn: Binding(
                    get: { notifManager.status == .authorized },
                    set: { _ in Task { await notifManager.requestOrOpenSettings() } }
                ))
                .tint(AppTheme.accent)
                .labelsHidden()
                .scaleEffect(0.85, anchor: .trailing)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 13)
        }
    }

    private var privacySection: some View {
        SettingsSection(title: "Privacy") {
            SettingsRow(icon: "lock.shield", iconBg: Color(r: 0xfa, g: 0xed, b: 0xcd),
                        label: "Data & privacy") {
                EmptyView()
            }
        }
    }
}

// MARK: - Reusable sub-components

private struct SettingsSection<Content: View>: View {
    let title: String
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.system(size: 10, weight: .semibold))
                .foregroundColor(AppTheme.textFaint)
                .textCase(.uppercase)
                .kerning(1.2)
                .padding(.leading, 4)

            VStack(spacing: 0) {
                content
            }
            .background(AppTheme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(AppTheme.border, lineWidth: 1)
            )
        }
    }
}

private struct SettingsRow<Trailing: View>: View {
    let icon: String
    let iconBg: Color
    let label: String
    @ViewBuilder let trailing: Trailing

    var body: some View {
        HStack(spacing: 10) {
            SettingsRowLeft(icon: icon, iconBg: iconBg, label: label)
            Spacer()
            trailing
            Image(systemName: "chevron.right")
                .font(.system(size: 12))
                .foregroundColor(AppTheme.textFaint)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 13)
    }
}

private struct SettingsRowLeft: View {
    let icon: String
    let iconBg: Color
    let label: String

    var body: some View {
        HStack(spacing: 10) {
            RoundedRectangle(cornerRadius: 7, style: .continuous)
                .fill(iconBg)
                .frame(width: 28, height: 28)
                .overlay(
                    Image(systemName: icon)
                        .font(.system(size: 13))
                        .foregroundColor(AppTheme.accentDark)
                )
            Text(label)
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(AppTheme.textPrimary)
        }
    }
}

#Preview {
    SettingsView()
        .environmentObject(AuthSession())
}
