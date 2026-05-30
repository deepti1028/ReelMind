import SwiftUI

struct RootView: View {
    @EnvironmentObject private var auth: AuthSession
    @AppStorage("hasCompletedOnboarding") private var hasCompletedOnboarding = false

    @State private var categoriseTarget: CategoriseTarget? = nil

    /// Identifiable payload for the `.categoriseReel` sheet binding.
    private struct CategoriseTarget: Identifiable {
        let id = UUID()
        let reelId: String
        let suggestions: [String]
    }

    var body: some View {
        Group {
            if auth.isBootstrapping {
                ProgressView()
            } else if !hasCompletedOnboarding {
                OnboardingFlow()
            } else if auth.isRecovering {
                // Show the set-new-password screen directly as the root view.
                // Using a sheet here causes SwiftUI to drop it when the underlying
                // view (ContentView → LoginView) transitions simultaneously.
                ForgotPasswordView(initialState: .setNewPassword)
                    .environmentObject(auth)
            } else if auth.session != nil {
                ContentView()
            } else {
                LoginView()
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .categoriseReel)) { notification in
            guard
                let info = notification.userInfo,
                let reelId = info["reel_id"] as? String
            else { return }
            let suggestions = (info["suggestions"] as? [String]) ?? []
            categoriseTarget = CategoriseTarget(reelId: reelId, suggestions: suggestions)
        }
        .fullScreenCover(item: $categoriseTarget) { target in
            CategoriseReelView(reelId: target.reelId, suggestions: target.suggestions)
        }
    }
}
