import Foundation

/// Background API calls invoked by the notification action handler when the
/// user taps a category button on the FCM "Help us categorise this reel"
/// notification.
enum ReelCategoryAPI {
    /// Assigns `categoryName` to `reelId`, or moves the reel to uncategorised
    /// when `categoryName` is nil (user tapped the "Uncategorised" button).
    static func assign(reelId: String, categoryName: String?) {
        guard
            let defaults = UserDefaults(suiteName: AppConfig.appGroupID),
            let authToken = defaults.string(forKey: AppConfig.authTokenKey)
        else {
            print("[ReelCategoryAPI] skipping assign — no auth token")
            return
        }

        let url = AppConfig.backendBaseURL
            .appendingPathComponent("api/v1/reels")
            .appendingPathComponent(reelId)
            .appendingPathComponent("category")

        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("Bearer \(authToken)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        // {"category_name": "Fitness"} or {"category_name": null}
        let body: [String: Any?] = ["category_name": categoryName]
        request.httpBody = try? JSONSerialization.data(
            withJSONObject: body,
            options: [.fragmentsAllowed]
        )

        URLSession.shared.dataTask(with: request) { _, response, error in
            if let error = error {
                print("[ReelCategoryAPI] assign failed: \(error)")
                return
            }
            if let http = response as? HTTPURLResponse {
                print("[ReelCategoryAPI] assign HTTP \(http.statusCode)")
            }
        }.resume()
    }
}
