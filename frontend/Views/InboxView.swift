import SwiftUI
import Auth
struct InboxView: View {
    @EnvironmentObject private var appVM: AppViewModel
    @EnvironmentObject private var auth: AuthSession

    @State private var reelToDelete: UUID?
    @State private var reelToReassign: Reel?

    var body: some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()

            if appVM.inboxReels.isEmpty {
                emptyState
            } else {
                reelList
            }
        }
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
                Text("The AI wasn't confident about these \(appVM.inboxCount) reels. Pick a home for them.")
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

#Preview {
    InboxView()
        .environmentObject(AppViewModel())
        .environmentObject(AuthSession())
}
