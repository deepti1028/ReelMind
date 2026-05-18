import Auth
import Foundation

struct ReelSource: Decodable, Identifiable {
    var id: String { reelId }
    let reelId: String
    let creatorHandle: String?
    let thumbnailUrl: String?
    let caption: String?

    enum CodingKeys: String, CodingKey {
        case reelId = "reel_id"
        case creatorHandle = "creator_handle"
        case thumbnailUrl = "thumbnail_url"
        case caption
    }
}

struct ChatMessage: Decodable, Identifiable {
    let id: String
    let role: String
    let content: String
    let sources: [ReelSource]
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, role, content, sources
        case createdAt = "created_at"
    }
}

struct ChatService {
    static let shared = ChatService()

    private var baseURL: URL { AppConfig.backendBaseURL.appendingPathComponent("api/v1/chat") }

    private func authToken() async throws -> String {
        return try await SupabaseManager.shared.client.auth.session.accessToken
    }

    private func makeRequest(_ url: URL, method: String, body: Data? = nil) async throws -> URLRequest {
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.setValue("Bearer \(try await authToken())", forHTTPHeaderField: "Authorization")
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = body
        return req
    }

    private var decoder: JSONDecoder {
        let d = JSONDecoder()
        d.dateDecodingStrategy = .iso8601
        return d
    }

    /// Creates a new chat session scoped to a category. Returns the session ID.
    func createSession(categoryId: UUID) async throws -> String {
        let url = baseURL.appendingPathComponent("sessions")
        let body = try JSONEncoder().encode(["category_id": categoryId.uuidString])
        let req = try await makeRequest(url, method: "POST", body: body)
        let (data, _) = try await URLSession.shared.data(for: req)
        let result = try JSONDecoder().decode([String: String].self, from: data)
        guard let sessionId = result["session_id"] else {
            throw URLError(.badServerResponse)
        }
        return sessionId
    }

    /// Sends a user message and returns the AI reply with source reels.
    func sendMessage(sessionId: String, content: String) async throws -> ChatMessage {
        let url = baseURL.appendingPathComponent("sessions/\(sessionId)/messages")
        let body = try JSONEncoder().encode(["content": content])
        let req = try await makeRequest(url, method: "POST", body: body)
        let (data, _) = try await URLSession.shared.data(for: req)
        return try decoder.decode(ChatMessage.self, from: data)
    }

    /// Fetches all messages for a session, in chronological order.
    func fetchMessages(sessionId: String) async throws -> [ChatMessage] {
        let url = baseURL.appendingPathComponent("sessions/\(sessionId)/messages")
        let req = try await makeRequest(url, method: "GET")
        let (data, _) = try await URLSession.shared.data(for: req)
        return try decoder.decode([ChatMessage].self, from: data)
    }
}
