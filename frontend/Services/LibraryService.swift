import Foundation
import Supabase

struct LibraryService {
    static let shared = LibraryService()
    private var client: SupabaseClient { SupabaseManager.shared.client }

    /// All non-deleted reels for the signed-in user, newest first.
    func fetchAllReels() async throws -> [Reel] {
        let userId = try await client.auth.session.user.id
        return try await client
            .from("reels")
            .select("*, categories(name)")
            .eq("user_id", value: userId)
            .is("deleted_at", value: nil)
            .order("created_at", ascending: false)
            .execute()
            .value
    }

    /// All categories belonging to the signed-in user, alphabetically.
    func fetchCategories() async throws -> [Category] {
        return try await client
            .from("categories")
            .select("id, name, created_at")
            .order("name", ascending: true)
            .execute()
            .value
    }

    /// Reels for a single category, newest first.
    func fetchReelsByCategory(_ categoryId: UUID) async throws -> [Reel] {
        return try await client
            .from("reels")
            .select("*, categories(name)")
            .eq("category_id", value: categoryId)
            .is("deleted_at", value: nil)
            .order("created_at", ascending: false)
            .execute()
            .value
    }

    /// Soft-deletes a reel by setting deleted_at to now.
    func softDeleteReel(_ reelId: UUID) async throws {
        struct Payload: Encodable {
            let deletedAt: String
            enum CodingKeys: String, CodingKey { case deletedAt = "deleted_at" }
        }
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        try await client
            .from("reels")
            .update(Payload(deletedAt: iso.string(from: Date())))
            .eq("id", value: reelId)
            .execute()
    }

    /// Assigns a category to a reel (used in InboxView chip tap).
    func assignCategory(reelId: UUID, categoryId: UUID) async throws {
        struct Payload: Encodable {
            let categoryId: UUID
            enum CodingKeys: String, CodingKey { case categoryId = "category_id" }
        }
        try await client
            .from("reels")
            .update(Payload(categoryId: categoryId))
            .eq("id", value: reelId)
            .execute()
    }
}
