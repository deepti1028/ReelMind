import Auth
import Foundation
import Supabase

enum AppConfig {
    static let supabaseURL = URL(string: "https://rpdqnfhfrhnzifgfmsbj.supabase.co")!

    // Public anon key — safe to ship in client. Get yours from:
    // Supabase Dashboard → Project Settings → API → Project API keys → "anon public"
    static let supabaseAnonKey = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJwZHFuZmhmcmhuemlmZ2Ztc2JqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzc1Nzk1NzUsImV4cCI6MjA5MzE1NTU3NX0.I4g18tsh3-RN7XjsECWsLBZlFDgCnJBnFMEoLZ_Ii6o"

    static let backendBaseURL = URL(string: "https://reelmind-8paz.onrender.com")!

    // App Group identifier — must match what's in BOTH:
    //   1. Main app target's Signing & Capabilities → App Groups
    //   2. URL Sharing module target's Signing & Capabilities → App Groups
    //   3. The K.appGroupID constant in ShareViewController.swift
    static let appGroupID = "group.com.reelmind.app"

    // Key under which the access token is stored in App Group UserDefaults.
    // Read by the share extension to authenticate POST /api/v1/reels.
    static let authTokenKey = "supabaseAuthToken"
}

final class SupabaseManager {
    static let shared = SupabaseManager()

    let client: SupabaseClient

    private init() {
        client = SupabaseClient(
            supabaseURL: AppConfig.supabaseURL,
            supabaseKey: AppConfig.supabaseAnonKey,
            options: SupabaseClientOptions(
                auth: SupabaseClientOptions.AuthOptions(
                    redirectURL: URL(string: "com.reelmind.app://auth-callback"),
                    // Opt in to the corrected initial-session behavior
                    // (supabase-swift PR #822). Without this, the auth
                    // listener double-emits during bootstrap, causing the
                    // duplicate "token cleared/synced" events.
                    emitLocalSessionAsInitialSession: true
                )
            )
        )
    }
}
