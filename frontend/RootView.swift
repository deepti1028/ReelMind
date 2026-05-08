import SwiftUI

struct RootView: View {
    @EnvironmentObject private var auth: AuthSession

    var body: some View {
        Group {
            if auth.isBootstrapping {
                ProgressView()
            } else if auth.session != nil {
                ContentView()
            } else {
                LoginView()
            }
        }
    }
}
