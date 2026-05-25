import SwiftUI
import Auth
struct InboxView: View {
    @EnvironmentObject private var appVM: AppViewModel
    @EnvironmentObject private var auth: AuthSession

    @State private var reelToDelete: UUID?
    @State private var reelToReassign: Reel?
    @AppStorage("autoCategorise") private var autoCategorise = true
    @AppStorage("inboxBannerDismissed") private var bannerDismissed = false

    var body: some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()

            if !appVM.hasLoaded {
                InboxSkeletonContent()
                    .transition(.opacity)
            } else if appVM.inboxReels.isEmpty {
                emptyState
                    .transition(.opacity)
            } else {
                reelList
                    .transition(.opacity)
            }

            if appVM.isDeletingReel {
                Color.black.opacity(0.25).ignoresSafeArea()
                ProgressView()
                    .tint(AppTheme.accentDark)
                    .scaleEffect(1.2)
                    .padding(24)
                    .background(AppTheme.surface)
                    .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
            }
        }
        .animation(.easeOut(duration: 0.25), value: appVM.hasLoaded)
        .allowsHitTesting(!appVM.isDeletingReel)
        .alert("Delete Reel?", isPresented: Binding(
            get: { reelToDelete != nil },
            set: { if !$0 { reelToDelete = nil } }
        )) {
            Button("Cancel", role: .cancel) { reelToDelete = nil }
            Button("Delete", role: .destructive) {
                if let id = reelToDelete {
                    Task { await appVM.deleteReel(id) }
                }
                reelToDelete = nil
            }
        } message: {
            Text("Removed from your library. This cannot be undone.")
        }
        .sheet(item: $reelToReassign) { reel in
            ReassignCategorySheet(reel: reel)
                .environmentObject(appVM)
        }
    }

    private var reelList: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                header
                    .padding(.horizontal, 20)
                    .padding(.top, 8)
                    .padding(.bottom, 14)

                if !autoCategorise && !bannerDismissed {
                    AutoCategoriseBanner(
                        onDismiss: { bannerDismissed = true },
                        onSettings: { appVM.showSettings = true }
                    )
                    .padding(.horizontal, 14)
                    .padding(.bottom, 4)
                    .transition(.opacity)
                }

                LazyVStack(spacing: 10) {
                    ForEach(appVM.inboxReels) { reel in
                        InboxReelCard(
                            reel: reel,
                            categoryOptions: appVM.categorySummaries,
                            onAssign: { categoryId in
                                Task { await appVM.assignCategory(reelId: reel.id, categoryId: categoryId) }
                            },
                            onDelete: { reelToDelete = reel.id },
                            onReassign: { reelToReassign = reel }
                        )
                    }
                }
                .padding(.horizontal, 14)
            }
        }
        .refreshable { await appVM.load() }
    }

    private var header: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 5) {
                Text("Needs a category")
                    .font(.system(size: 26, weight: .bold))
                    .foregroundColor(AppTheme.textPrimary)
                Text("We weren't confident about these \(appVM.inboxCount) reels. Pick a category for them.")
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.textMuted)
                    .lineLimit(2)
            }
            Spacer()
            Button { appVM.showSettings = true } label: {
                Circle()
                    .fill(AppTheme.avatarGradient)
                    .frame(width: 36, height: 36)
                    .overlay(
                        Text(auth.session?.user.email?.prefix(1).uppercased() ?? "?")
                            .font(.system(size: 14, weight: .bold))
                            .foregroundColor(.white)
                    )
            }
            .buttonStyle(.plain)
        }
    }

    private var emptyState: some View {
        VStack(spacing: 16) {
            if !autoCategorise && !bannerDismissed {
                AutoCategoriseBanner(
                    onDismiss: { bannerDismissed = true },
                    onSettings: { appVM.showSettings = true }
                )
                .padding(.horizontal, 20)
            }
            VStack(spacing: 12) {
                Image(systemName: "checkmark.circle")
                    .font(.system(size: 44))
                    .foregroundColor(AppTheme.accent)
                Text("All caught up")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(AppTheme.textPrimary)
                Text("Every reel has been categorised.")
                    .font(.system(size: 13))
                    .foregroundColor(AppTheme.textMuted)
            }
        }
    }
}

private struct AutoCategoriseBanner: View {
    let onDismiss: () -> Void
    let onSettings: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 9) {
            Text("✦")
                .font(.system(size: 14))
                .foregroundColor(Color(r: 0x4a, g: 0x64, b: 0x28))
                .padding(.top, 1)

            VStack(alignment: .leading, spacing: 2) {
                Text("Want your saved Reels sorted automatically?")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(Color(r: 0x30, g: 0x40, b: 0x20))
                HStack(spacing: 0) {
                    Text("Turn on ")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(Color(r: 0x30, g: 0x40, b: 0x20))
                    Button("Auto-categorise") { onSettings() }
                        .font(.system(size: 11, weight: .bold))
                        .foregroundColor(AppTheme.accentDark)
                    Text(" in Settings.")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(Color(r: 0x30, g: 0x40, b: 0x20))
                }
            }

            Spacer()

            Button { onDismiss() } label: {
                Text("✕")
                    .font(.system(size: 13, weight: .light))
                    .foregroundColor(Color(r: 0x6a, g: 0x82, b: 0x40))
            }
        }
        .padding(12)
        .background(
            LinearGradient(
                colors: [
                    Color(r: 0xdd, g: 0xe8, b: 0xc4),
                    Color(r: 0xcc, g: 0xd5, b: 0xae),
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Color(r: 0xb8, g: 0xcc, b: 0x9a), lineWidth: 1)
        )
    }
}

#Preview {
    InboxView()
        .environmentObject(AppViewModel())
        .environmentObject(AuthSession())
}
