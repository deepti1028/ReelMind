import SwiftUI

struct ContentView: View {
    @StateObject private var appVM = AppViewModel()
    @EnvironmentObject private var auth: AuthSession
    @Environment(\.scenePhase) private var scenePhase
    @State private var selectedTab = 0

    var body: some View {
        ZStack {
            NavigationStack {
                LibraryView(onInboxTap: { selectedTab = 1 })
            }
            .opacity(selectedTab == 0 ? 1 : 0)
            .allowsHitTesting(selectedTab == 0)

            InboxView()
                .opacity(selectedTab == 1 ? 1 : 0)
                .allowsHitTesting(selectedTab == 1)
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            FooterTabBar(selectedTab: $selectedTab, inboxCount: appVM.inboxCount)
        }
        .background(AppTheme.background.ignoresSafeArea())
        .environmentObject(appVM)
        .task { await appVM.load() }
        .onChange(of: scenePhase) { _, phase in
            if phase == .active { Task { await appVM.load(silent: true) } }
        }
        .sheet(isPresented: $appVM.showSettings) {
            NavigationStack {
                SettingsView()
                    .environmentObject(auth)
                    .environmentObject(appVM)
            }
        }
    }
}

#Preview {
    ContentView()
        .environmentObject(AuthSession())
}
