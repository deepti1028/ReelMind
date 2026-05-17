import Foundation

/// Uploads the device's FCM registration token to the backend.
/// Used on FCM token refresh and on successful login.
enum ProfileAPI {
    static func uploadFCMToken(_ token: String) {
        guard
            let defaults = UserDefaults(suiteName: AppConfig.appGroupID),
            let authToken = defaults.string(forKey: AppConfig.authTokenKey)
        else {
            print("[ProfileAPI] skipping FCM token upload — no auth token in App Group defaults")
            return
        }

        let url = AppConfig.backendBaseURL.appendingPathComponent("api/v1/profiles/fcm-token")
        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("Bearer \(authToken)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONEncoder().encode(["fcm_token": token])

        URLSession.shared.dataTask(with: request) { _, response, error in
            if let error = error {
                print("[ProfileAPI] uploadFCMToken failed: \(error)")
                return
            }
            if let http = response as? HTTPURLResponse {
                print("[ProfileAPI] uploadFCMToken HTTP \(http.statusCode)")
            }
        }.resume()
    }
}
