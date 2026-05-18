import SwiftUI
import Combine

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
    @StateObject private var viewModel = CategoryDetailViewModel()
    @Environment(\.dismiss) private var dismiss
    @State private var showChat = false

    var body: some View {
        ZStack(alignment: .bottomTrailing) {
            AppTheme.background.ignoresSafeArea()

            ScrollView {
                LazyVStack(spacing: 10) {
                    ForEach(viewModel.reels) { reel in
                        DetailReelCard(
                            reel: reel,
                            onDelete: {
                                Task {
                                    await viewModel.deleteReel(reel.id)
                                    await appVM.load(silent: true)
                                }
                            },
                            onTap: {
                                guard let url = URL(string: reel.url) else { return }
                                UIApplication.shared.open(url)
                            }
                        )
                    }
                }
                .padding(.horizontal, 14)
                .padding(.top, 4)
                .padding(.bottom, 80)
            }

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
            .padding(.trailing, 16)
            .padding(.bottom, 16)
        }
        .navigationBarBackButtonHidden(true)
        .toolbar {
            ToolbarItem(placement: .navigationBarLeading) {
                backButton
            }
            ToolbarItem(placement: .principal) {
                reelCountLabel
            }
        }
        .navigationTitle(summary.name)
        .navigationBarTitleDisplayMode(.large)
        .task { await viewModel.load(categoryId: summary.id) }
        .sheet(isPresented: $showChat) {
            ChatView(categoryId: summary.id, categoryName: summary.name)
        }
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

    private var reelCountLabel: some View {
        Text("\(viewModel.reels.count) reels saved")
            .font(.system(size: 12))
            .foregroundColor(AppTheme.textFaint)
    }
}
