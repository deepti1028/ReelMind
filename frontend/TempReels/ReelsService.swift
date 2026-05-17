import Foundation
import Supabase

struct ReelsService {
    static let shared = ReelsService()

    private var client: SupabaseClient { SupabaseManager.shared.client }

    /// Fetches the signed-in user's saved reels (newest first), excluding
    /// soft-deleted rows. RLS on the `reels` table is expected to scope
    /// rows to the authenticated user, but we also filter by user_id
    /// defensively in case RLS is disabled in some environment.
    func fetchReels() async throws -> [Reel] {
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
}
