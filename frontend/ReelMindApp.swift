//
//  ReelMindApp.swift
//  ReelMind
//
//  Created by Deepti Jain on 01/05/26.
//

import Firebase
import FirebaseMessaging
import Supabase
import SwiftUI
import UserNotifications

extension Notification.Name {
    /// Posted when the user taps the "Choose / Create Category" foreground action
    /// on a pending_category FCM notification. RootView listens and presents CategoriseReelView.
    static let categoriseReel = Notification.Name("categoriseReel")
}

class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate, MessagingDelegate {
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey : Any]? = nil) -> Bool {
        // 20 MB memory / 150 MB disk — AsyncImage uses URLSession.shared which reads URLCache.shared.
        URLCache.shared = URLCache(memoryCapacity: 20_000_000, diskCapacity: 150_000_000)

        // Configure Firebase
        FirebaseApp.configure()

        // Set up messaging delegate
        Messaging.messaging().delegate = self

        // Notification permission is requested explicitly from the onboarding
        // permissions screen, not on launch. We still set the delegate here so
        // foreground / tap callbacks work once permission is granted.
        UNUserNotificationCenter.current().delegate = self

        // Register the CATEGORISE notification category for Step 22 FCM push notifications.
        let categoriseActions: [UNNotificationAction] = [
            UNNotificationAction(
                identifier: "CAT_0",
                title: "Suggestion 1",
                options: []
            ),
            UNNotificationAction(
                identifier: "CAT_1",
                title: "Suggestion 2",
                options: []
            ),
            UNNotificationAction(
                identifier: "CHOOSE_IN_APP",
                title: "Choose / Create Category",
                options: [.foreground]
            ),
            UNNotificationAction(
                identifier: "UNCATEGORISED",
                title: "Uncategorised",
                options: []
            ),
        ]
        let categoriseCategory = UNNotificationCategory(
            identifier: "CATEGORISE",
            actions: categoriseActions,
            intentIdentifiers: [],
            options: []
        )
        UNUserNotificationCenter.current().setNotificationCategories([categoriseCategory])

        // If permission was already granted in a previous session, register
        // for remote notifications so the FCM token is refreshed.
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            if settings.authorizationStatus == .authorized {
                DispatchQueue.main.async {
                    UIApplication.shared.registerForRemoteNotifications()
                }
            }
        }

        return true
    }

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        Messaging.messaging().apnsToken = deviceToken
    }

    func messaging(_ messaging: Messaging, didReceiveRegistrationToken fcmToken: String?) {
        print("FCM Token: \(fcmToken ?? "No token")")
        guard let token = fcmToken else { return }

        // Cache locally so AuthSession.syncToken can upload if user logs in after token refreshes.
        UserDefaults.standard.set(token, forKey: "fcmToken")

        // Upload immediately if auth token is already in App Group defaults (user already logged in).
        let groupDefaults = UserDefaults(suiteName: AppConfig.appGroupID)
        if groupDefaults?.string(forKey: AppConfig.authTokenKey) != nil {
            ProfileAPI.uploadFCMToken(token)
        }
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification, withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        let userInfo = notification.request.content.userInfo
        print("Notification received in foreground: \(userInfo)")
        completionHandler([.banner, .sound, .badge])
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let userInfo = response.notification.request.content.userInfo
        guard let reelId = userInfo["reel_id"] as? String else {
            print("[AppDelegate] notification action with no reel_id — ignoring")
            completionHandler()
            return
        }

        let suggestions = Self.parseSuggestions(from: userInfo)

        switch response.actionIdentifier {
        case "CAT_0" where suggestions.count > 0:
            ReelCategoryAPI.assign(reelId: reelId, categoryName: suggestions[0])
        case "CAT_1" where suggestions.count > 1:
            ReelCategoryAPI.assign(reelId: reelId, categoryName: suggestions[1])
        case "UNCATEGORISED":
            ReelCategoryAPI.assign(reelId: reelId, categoryName: nil)
        case "CHOOSE_IN_APP":
            NotificationCenter.default.post(
                name: .categoriseReel,
                object: nil,
                userInfo: [
                    "reel_id": reelId,
                    "suggestions": suggestions,
                ]
            )
        default:
            break
        }
        completionHandler()
    }

    private static func parseSuggestions(from userInfo: [AnyHashable: Any]) -> [String] {
        guard
            let raw = userInfo["suggestions"] as? String,
            let data = raw.data(using: .utf8),
            let suggestions = try? JSONDecoder().decode([String].self, from: data)
        else {
            return []
        }
        return suggestions
    }
}

@main
struct ReelMindApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var auth = AuthSession()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(auth)
                .onOpenURL { url in
                    print("[DeepLink] onOpenURL fired")
                    print("[DeepLink] full URL: \(url.absoluteString)")
                    print("[DeepLink] scheme: \(url.scheme ?? "nil")")
                    print("[DeepLink] host: \(url.host ?? "nil")")
                    print("[DeepLink] path: \(url.path)")
                    print("[DeepLink] query: \(url.query ?? "nil")")
                    print("[DeepLink] fragment: \(url.fragment ?? "nil")")
                    // SDK PKCE path only emits .signedIn, never .passwordRecovery.
                    // Detect the recovery callback by its unique host and set the
                    // flag before handle(url) signs the user in.
                    if url.host == "reset-password" {
                        auth.isRecovering = true
                    }
                    SupabaseManager.shared.client.auth.handle(url)
                    print("[DeepLink] handle(url) called")
                }
        }
    }
}
