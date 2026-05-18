import Combine
import Foundation
import UIKit
import UserNotifications

@MainActor
final class NotificationPermissionManager: ObservableObject {
    enum Status {
        case notDetermined
        case authorized
        case denied
    }

    @Published private(set) var status: Status = .notDetermined

    func refresh() async {
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        switch settings.authorizationStatus {
        case .authorized, .provisional, .ephemeral:
            status = .authorized
        case .denied:
            status = .denied
        case .notDetermined:
            status = .notDetermined
        @unknown default:
            status = .notDetermined
        }
    }

    /// Request system permission. If already denied, opens Settings instead.
    func requestOrOpenSettings() async {
        await refresh()
        switch status {
        case .notDetermined:
            do {
                let granted = try await UNUserNotificationCenter.current()
                    .requestAuthorization(options: [.alert, .sound, .badge])
                status = granted ? .authorized : .denied
                if granted {
                    UIApplication.shared.registerForRemoteNotifications()
                }
            } catch {
                status = .denied
            }
        case .denied:
            if let url = URL(string: UIApplication.openSettingsURLString) {
                await UIApplication.shared.open(url)
            }
        case .authorized:
            break
        }
    }
}
