import Combine
import SwiftUI

@MainActor
final class ReelsViewModel: ObservableObject {
    enum LoadState: Equatable {
        case idle
        case loading
        case loaded([Reel])
        case error(String)
    }

    @Published private(set) var state: LoadState = .idle

    /// Loads reels from Supabase.
    /// - Parameter silent: when true and we already have a `.loaded` state,
    ///   keeps the current list visible instead of flashing the spinner.
    ///   Use this for foreground refreshes / pull-to-refresh.
    func load(silent: Bool = false) async {
        if case .loading = state { return }
        if !silent || isInitialLoad { state = .loading }
        do {
            let reels = try await ReelsService.shared.fetchReels()
            state = .loaded(reels)
        } catch {
            state = .error(error.localizedDescription)
        }
    }

    private var isInitialLoad: Bool {
        if case .loaded = state { return false }
        if case .error = state { return false }
        return true
    }
}

struct ReelsHomeView: View {
    @StateObject private var viewModel = ReelsViewModel()
    @EnvironmentObject private var auth: AuthSession
    @Environment(\.scenePhase) private var scenePhase
    @State private var showSignOutConfirm = false

    var body: some View {
        Group {
            switch viewModel.state {
            case .idle, .loading:
                loadingView
            case .loaded(let reels):
                if reels.isEmpty {
                    EmptyReelsView(
                        onAddReel: handleAddReel,
                        onMenu: handleMenu
                    )
                } else {
                    ReelsListView(reels: reels)
                }
            case .error(let message):
                errorView(message: message)
            }
        }
        .task { await viewModel.load() }
        .refreshable { await viewModel.load(silent: true) }
        .onChange(of: scenePhase) { _, newPhase in
            // The share extension runs in a separate process; when the user
            // returns to the app after sharing a reel we need to re-fetch
            // because `.task` only fires on first appear.
            if newPhase == .active {
                Task { await viewModel.load(silent: true) }
            }
        }
        .confirmationDialog(
            "Account",
            isPresented: $showSignOutConfirm,
            titleVisibility: .visible
        ) {
            Button("Sign Out", role: .destructive) {
                Task { try? await auth.signOut() }
            }
            Button("Cancel", role: .cancel) {}
        }
    }

    private var loadingView: some View {
        ZStack {
            ReelsTheme.surface.ignoresSafeArea()
            ProgressView()
                .tint(ReelsTheme.brandGreen)
        }
    }

    private func errorView(message: String) -> some View {
        ZStack {
            ReelsTheme.surface.ignoresSafeArea()
            VStack(spacing: 16) {
                Image(systemName: "exclamationmark.triangle")
                    .font(.system(size: 36))
                    .foregroundColor(ReelsTheme.brandGreen)
                Text("Couldn't load reels")
                    .font(.system(size: 18, weight: .semibold))
                Text(message)
                    .font(.footnote)
                    .foregroundColor(ReelsTheme.mutedText)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 32)
                Button("Try again") {
                    Task { await viewModel.load() }
                }
                .padding(.top, 4)
                .tint(ReelsTheme.brandGreen)
            }
        }
    }

    private func handleAddReel() {
        // Reels are added via the system share sheet (URL Sharing module).
    }

    private func handleMenu() {
        showSignOutConfirm = true
    }
}

#Preview {
    ReelsHomeView()
        .environmentObject(AuthSession())
}
