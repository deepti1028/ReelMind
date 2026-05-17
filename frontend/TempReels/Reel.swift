import Foundation

struct CategoryInfo: Decodable, Hashable {
    let name: String
}

struct Reel: Identifiable, Decodable, Hashable {
    let id: UUID
    let userId: UUID
    let categoryId: UUID?
    let url: String
    let creatorHandle: String?
    let thumbnailUrl: String?
    let transcript: String?
    let caption: String?
    let hashtags: [String]
    let summary: String?
    let confidence: Float?
    let hasAudio: Bool?
    let status: String
    let retryCount: Int?
    let deletedAt: Date?
    let createdAt: Date
    let updatedAt: Date
    let categories: CategoryInfo?

    enum CodingKeys: String, CodingKey {
        case id
        case userId = "user_id"
        case categoryId = "category_id"
        case url
        case creatorHandle = "creator_handle"
        case thumbnailUrl = "thumbnail_url"
        case transcript
        case caption
        case hashtags
        case summary
        case confidence
        case hasAudio = "has_audio"
        case status
        case retryCount = "retry_count"
        case deletedAt = "deleted_at"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case categories
    }
}
