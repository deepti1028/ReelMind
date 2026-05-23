import Foundation

struct Category: Identifiable, Decodable, Hashable {
    let id: UUID
    let name: String
    let icon: String?
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, name, icon
        case createdAt = "created_at"
    }
}

struct CategorySummary: Identifiable, Hashable {
    let id: UUID
    let name: String
    let icon: String?
    let reelCount: Int
    let lastSavedAt: Date?
}
