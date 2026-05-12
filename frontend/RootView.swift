import SwiftUI

struct RootView: View {
    @EnvironmentObject private var auth: AuthSession
    @AppStorage("hasCompletedOnboarding") private var hasCompletedOnboarding = false

    var body: some View {
        Group {
            if auth.isBootstrapping {
                ProgressView()
            } else if !hasCompletedOnboarding {
                OnboardingFlow()
            } else if auth.session != nil {
                ContentView()
            } else {
                LoginView()
            }
        }
    }
}
