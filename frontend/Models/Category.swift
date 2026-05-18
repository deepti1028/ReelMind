import Foundation

/// Decoded directly from the `categories` Supabase table.
struct Category: Identifiable, Decodable, Hashable {
    let id: UUID
    let name: String
    let createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id, name
        case createdAt = "created_at"
    }
}

/// View-layer summary: a category merged with its reel count + last-saved date.
/// Must be Hashable to work with NavigationLink(value:).
struct CategorySummary: Identifiable, Hashable {
    let id: UUID
    let name: String
    let reelCount: Int
    let lastSavedAt: Date?
}
