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

    /// Async version of `assign` — throws on network failure or non-2xx HTTP status.
    /// Used by CategoriseReelView where the sheet can show an error to the user.
    static func assignAsync(reelId: String, categoryName: String?) async throws {
        guard
            let defaults = UserDefaults(suiteName: AppConfig.appGroupID),
            let authToken = defaults.string(forKey: AppConfig.authTokenKey)
        else {
            throw URLError(.userAuthenticationRequired)
        }

        let url = AppConfig.backendBaseURL
            .appendingPathComponent("api/v1/reels")
            .appendingPathComponent(reelId)
            .appendingPathComponent("category")

        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("Bearer \(authToken)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body: [String: Any?] = ["category_name": categoryName]
        request.httpBody = try? JSONSerialization.data(
            withJSONObject: body,
            options: [.fragmentsAllowed]
        )

        let (_, response) = try await URLSession.shared.data(for: request)
        guard
            let http = response as? HTTPURLResponse,
            (200...299).contains(http.statusCode)
        else {
            throw URLError(.badServerResponse)
        }
    }
}
