import Auth
import Combine
import SwiftUI
import UIKit

@MainActor
private final class CategoryDetailViewModel: ObservableObject {
    @Published var reels: [Reel] = []
    @Published var isLoading = false

    func load(categoryId: UUID) async {
        guard !isLoading else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            reels = try await LibraryService.shared.fetchReelsByCategory(categoryId)
        } catch {
            print("[CategoryDetailViewModel] load failed: \(error)")
        }
    }

    func deleteReel(_ reelId: UUID) async {
        do {
            try await LibraryService.shared.softDeleteReel(reelId)
            reels.removeAll { $0.id == reelId }
        } catch {
            print("[CategoryDetailViewModel] deleteReel failed: \(error)")
        }
    }
}

struct CategoryDetailView: View {
    let summary: CategorySummary
    @EnvironmentObject private var appVM: AppViewModel
    @EnvironmentObject private var auth: AuthSession
    @StateObject private var viewModel = CategoryDetailViewModel()
    @Environment(\.dismiss) private var dismiss
    @State private var showChat = false
    @State private var reelToDelete: UUID?
    @State private var reelToReassign: Reel?

    var body: some View {
        // ZStack positions the chat FAB inside the safe-area frame.
        // Background is a modifier (not a ZStack child) so the ZStack sizes
        // to the safe area — keeping the button above the tab bar.
        ZStack(alignment: .bottomTrailing) {
            ScrollView {
                LazyVStack(spacing: 10) {
                    categoryHeader
                        .padding(.horizontal, 20)
                        .padding(.top, 4)
                        .padding(.bottom, 8)

                    if viewModel.reels.isEmpty && !viewModel.isLoading {
                        categoryEmptyState
                            .padding(.horizontal, 14)
                    } else {
                        ForEach(viewModel.reels) { reel in
                            DetailReelCard(
                                reel: reel,
                                onDelete: { reelToDelete = reel.id },
                                onReassign: { reelToReassign = reel }
                            )
                        }
                    }
                }
                .padding(.horizontal, 14)
                .padding(.bottom, 80)
            }
            .refreshable { await viewModel.load(categoryId: summary.id) }

            chatButton
                .padding(.trailing, 16)
                .padding(.bottom, 16)
        }
        .background(AppTheme.background.ignoresSafeArea())
        .navigationBarBackButtonHidden(true)
        .navigationTitle("")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarLeading) {
                backButton
            }
            ToolbarItem(placement: .navigationBarTrailing) {
                profileButton
            }
        }
        .task { await viewModel.load(categoryId: summary.id) }
        .sheet(isPresented: $showChat) {
            ChatView(categoryId: summary.id, categoryName: summary.name)
        }
        .alert("Delete Reel?", isPresented: Binding(
            get: { reelToDelete != nil },
            set: { if !$0 { reelToDelete = nil } }
        )) {
            Button("Cancel", role: .cancel) { reelToDelete = nil }
            Button("Delete", role: .destructive) {
                if let id = reelToDelete {
                    Task {
                        await viewModel.deleteReel(id)
                        await appVM.load(silent: true)
                    }
                }
                reelToDelete = nil
            }
        } message: {
            Text("Removed from your library. This cannot be undone.")
        }
        .sheet(item: $reelToReassign) { reel in
            ReassignCategorySheet(reel: reel, onComplete: {
                Task { await viewModel.load(categoryId: summary.id) }
            })
            .environmentObject(appVM)
        }
    }

    // MARK: - Sub-views

    private var categoryEmptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "film.stack")
                .font(.system(size: 40))
                .foregroundColor(AppTheme.accent.opacity(0.6))
            Text("Nothing here yet")
                .font(.system(size: 17, weight: .semibold))
                .foregroundColor(AppTheme.textPrimary)
            Text("Share a reel from Instagram and assign it to \(summary.name) to get started.")
                .font(.system(size: 13))
                .foregroundColor(AppTheme.textMuted)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 16)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 60)
    }

    private var categoryHeader: some View {
        Text(summary.name)
            .font(.system(size: 28, weight: .bold))
            .foregroundColor(AppTheme.textPrimary)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var backButton: some View {
        Button { dismiss() } label: {
            HStack(spacing: 4) {
                Image(systemName: "chevron.left")
                    .font(.system(size: 13, weight: .semibold))
                Text("Back")
                    .font(.system(size: 13, weight: .semibold))
            }
            .foregroundColor(AppTheme.accent)
        }
    }

    private var profileButton: some View {
        Button { appVM.showSettings = true } label: {
            Circle()
                .fill(AppTheme.avatarGradient)
                .frame(width: 32, height: 32)
                .overlay(
                    Text(auth.session?.user.email?.prefix(1).uppercased() ?? "?")
                        .font(.system(size: 13, weight: .bold))
                        .foregroundColor(.white)
                )
        }
        .buttonStyle(.plain)
    }

    private var chatButton: some View {
        Button { showChat = true } label: {
            Circle()
                .fill(AppTheme.accent)
                .frame(width: 44, height: 44)
                .overlay(
                    Image(systemName: "bubble.left.and.bubble.right")
                        .font(.system(size: 18))
                        .foregroundColor(.white)
                )
                .shadow(color: AppTheme.accent.opacity(0.45), radius: 8, y: 4)
        }
        .buttonStyle(.plain)
    }
}
