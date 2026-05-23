import Auth
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
    /// Excludes default categories — used by ManageCategoriesView where edit/delete are exposed.
    func fetchCategories() async throws -> [Category] {
        return try await client
            .from("categories")
            .select("id, name, icon, created_at, is_default")
            .eq("is_default", value: false)
            .order("name", ascending: true)
            .execute()
            .value
    }

    /// All categories visible to the user (own + system defaults), alphabetically.
    /// Used by AppViewModel to build home-screen summaries — reels can be assigned to default categories.
    func fetchAllVisibleCategories() async throws -> [Category] {
        return try await client
            .from("categories")
            .select("id, name, icon, created_at, is_default")
            .order("name", ascending: true)
            .execute()
            .value
    }

    /// System-wide default categories (is_default = true), alphabetically.
    func fetchDefaultCategories() async throws -> [Category] {
        return try await client
            .from("categories")
            .select("id, name, icon, created_at, is_default")
            .eq("is_default", value: true)
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

    /// Creates a new user-owned category and returns it.
    func createCategory(name: String, icon: String) async throws -> Category {
        let userId = try await client.auth.session.user.id
        struct Payload: Encodable {
            let name: String
            let icon: String
            let userId: UUID
            let isDefault: Bool
            enum CodingKeys: String, CodingKey {
                case name, icon
                case userId = "user_id"
                case isDefault = "is_default"
            }
        }
        return try await client
            .from("categories")
            .insert(Payload(name: name, icon: icon, userId: userId, isDefault: false))
            .select()
            .single()
            .execute()
            .value
    }

    /// Renames an existing category.
    func renameCategory(id: UUID, newName: String, icon: String) async throws {
        struct Payload: Encodable {
            let name: String
            let icon: String
        }
        try await client
            .from("categories")
            .update(Payload(name: newName, icon: icon))
            .eq("id", value: id)
            .execute()
    }

    /// Deletes a category row. Reels in this category will have category_id set to null by the DB cascade.
    func deleteCategory(id: UUID) async throws {
        try await client
            .from("categories")
            .delete()
            .eq("id", value: id)
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
