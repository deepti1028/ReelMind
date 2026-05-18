import SwiftUI

struct InboxView: View {
    @EnvironmentObject private var appVM: AppViewModel

    var body: some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()

            if appVM.inboxReels.isEmpty {
                emptyState
            } else {
                reelList
            }
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
                            onDelete: {
                                Task { await appVM.deleteReel(reel.id) }
                            }
                        )
                    }
                }
                .padding(.horizontal, 14)
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text("Needs a category")
                .font(.system(size: 26, weight: .bold))
                .foregroundColor(AppTheme.textPrimary)
            Text("The AI wasn't confident about these \(appVM.inboxCount) reels. Pick a home for them.")
                .font(.system(size: 12))
                .foregroundColor(AppTheme.textMuted)
                .lineLimit(2)
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
}
