import Foundation

enum FeedbackAPI {
    enum FeedbackType: String, CaseIterable {
        case bugReport      = "Bug Report"
        case featureRequest = "Feature Request"
        case general        = "General"
    }

    static func send(type: FeedbackType, message: String) async throws {
        guard
            let defaults = UserDefaults(suiteName: AppConfig.appGroupID),
            let authToken = defaults.string(forKey: AppConfig.authTokenKey)
        else {
            throw URLError(.userAuthenticationRequired)
        }

        let url = AppConfig.backendBaseURL.appendingPathComponent("api/v1/feedback")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("Bearer \(authToken)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode([
            "type": type.rawValue,
            "message": message,
        ])

        let (_, response) = try await URLSession.shared.data(for: request)
        guard
            let http = response as? HTTPURLResponse,
            (200...299).contains(http.statusCode)
        else {
            throw URLError(.badServerResponse)
        }
    }
}
