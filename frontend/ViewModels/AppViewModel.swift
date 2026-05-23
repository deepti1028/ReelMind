import Combine
import SwiftUI

@MainActor
final class AppViewModel: ObservableObject {
    @Published private(set) var categorySummaries: [CategorySummary] = []
    @Published private(set) var inboxReels: [Reel] = []
    @Published private(set) var totalCount: Int = 0
    @Published var showSettings = false

    private var isLoading = false

    var inboxCount: Int { inboxReels.count }

    /// Loads categories + reels, computes summaries. Call once on ContentView.task.
    /// Pass silent: true for background refreshes to avoid a spinner flash.
    func load(silent: Bool = false) async {
        guard !isLoading else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            async let reelsFetch    = LibraryService.shared.fetchAllReels()
            async let catsFetch     = LibraryService.shared.fetchCategories()
            let (reels, categories) = try await (reelsFetch, catsFetch)

            let grouped = Dictionary(
                grouping: reels.filter { $0.categoryId != nil },
                by: { $0.categoryId! }
            )
            categorySummaries = categories
                .map { cat -> CategorySummary in
                    let catReels = grouped[cat.id] ?? []
                    return CategorySummary(
                        id: cat.id,
                        name: cat.name,
                        icon: cat.icon,
                        reelCount: catReels.count,
                        lastSavedAt: catReels.first?.createdAt
                    )
                }
                .filter { $0.reelCount > 0 }
                .sorted { ($0.lastSavedAt ?? .distantPast) > ($1.lastSavedAt ?? .distantPast) }

            inboxReels  = reels.filter { $0.categoryId == nil }
            totalCount  = reels.count
        } catch {
            print("[AppViewModel] load failed: \(error)")
        }
    }

    /// Soft-deletes a reel then refreshes.
    func deleteReel(_ reelId: UUID) async {
        do {
            try await LibraryService.shared.softDeleteReel(reelId)
            await load(silent: true)
        } catch {
            print("[AppViewModel] deleteReel failed: \(error)")
        }
    }

    /// Assigns a category to an inbox reel then refreshes.
    func assignCategory(reelId: UUID, categoryId: UUID) async {
        do {
            try await LibraryService.shared.assignCategory(reelId: reelId, categoryId: categoryId)
            await load(silent: true)
        } catch {
            print("[AppViewModel] assignCategory failed: \(error)")
        }
    }
}
