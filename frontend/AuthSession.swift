import Auth
import AuthenticationServices
import Combine
import Foundation
import Supabase

// Bridges ASAuthorizationController's delegate callbacks to async/await.
// Stored on AuthSession to stay alive for the duration of the sign-in flow.
private final class AppleSignInCoordinator: NSObject,
    ASAuthorizationControllerDelegate,
    ASAuthorizationControllerPresentationContextProviding
{
    var continuation: CheckedContinuation<ASAuthorizationAppleIDCredential, Error>?

    func presentationAnchor(for controller: ASAuthorizationController) -> ASPresentationAnchor {
        UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .first?.keyWindow ?? UIWindow()
    }

    func authorizationController(controller: ASAuthorizationController,
                                 didCompleteWithAuthorization authorization: ASAuthorization) {
        if let credential = authorization.credential as? ASAuthorizationAppleIDCredential {
            continuation?.resume(returning: credential)
        } else {
            continuation?.resume(throwing: NSError(domain: "AppleSignIn", code: -1,
                userInfo: [NSLocalizedDescriptionKey: "Unexpected credential type"]))
        }
        continuation = nil
    }

    func authorizationController(controller: ASAuthorizationController,
                                 didCompleteWithError error: Error) {
        continuation?.resume(throwing: error)
        continuation = nil
    }
}

@MainActor
final class AuthSession: ObservableObject {
    @Published var session: Session?
    @Published var isBootstrapping = true

    private var listenerTask: Task<Void, Never>?
    private var appleSignInCoordinator: AppleSignInCoordinator?

    init() {
        Task { await bootstrap() }
    }

    deinit {
        listenerTask?.cancel()
    }

    private func bootstrap() async {
        // Try to restore an existing session (Supabase SDK persists tokens
        // in its own keychain-backed storage between launches).
        let restored = try? await SupabaseManager.shared.client.auth.session
        self.session = restored
        syncToken(restored?.accessToken)
        self.isBootstrapping = false

        // Listen for sign-in / sign-out / token-refresh events forever.
        listenerTask = Task { [weak self] in
            for await (_, newSession) in SupabaseManager.shared.client.auth.authStateChanges {
                await MainActor.run {
                    self?.session = newSession
                    self?.syncToken(newSession?.accessToken)
                }
            }
        }
    }

    // Mirror the access token into App Group UserDefaults so the share
    // extension can pick it up. On sign-out, remove it.
    private func syncToken(_ token: String?) {
        guard let defaults = UserDefaults(suiteName: AppConfig.appGroupID) else {
            print("[AuthSession] could not open App Group defaults — check entitlement \(AppConfig.appGroupID)")
            return
        }
        if let token = token {
            defaults.set(token, forKey: AppConfig.authTokenKey)
            print("[AuthSession] token synced to App Group (\(token.count) chars)")

            // If an FCM token was cached before login, push it to the backend now.
            if let fcmToken = UserDefaults.standard.string(forKey: "fcmToken") {
                ProfileAPI.uploadFCMToken(fcmToken)
            }
        } else {
            defaults.removeObject(forKey: AppConfig.authTokenKey)
            print("[AuthSession] token cleared from App Group")
        }
    }

    // MARK: - Auth actions

    func signIn(email: String, password: String) async throws {
        try await SupabaseManager.shared.client.auth.signIn(
            email: email,
            password: password
        )
    }

    func signUp(email: String, password: String, displayName: String) async throws {
        try await SupabaseManager.shared.client.auth.signUp(
            email: email,
            password: password,
            data: ["full_name": AnyJSON.string(displayName)]
        )
    }

    func signInWithGoogle() async throws {
        try await SupabaseManager.shared.client.auth.signInWithOAuth(
            provider: .google,
            queryParams: [("prompt", "select_account")]
        )
    }

    func signInWithApple() async throws {
        let coordinator = AppleSignInCoordinator()
        appleSignInCoordinator = coordinator

        let credential = try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<ASAuthorizationAppleIDCredential, Error>) in
            coordinator.continuation = continuation
            let request = ASAuthorizationAppleIDProvider().createRequest()
            request.requestedScopes = [.fullName, .email]
            let controller = ASAuthorizationController(authorizationRequests: [request])
            controller.delegate = coordinator
            controller.presentationContextProvider = coordinator
            controller.performRequests()
        }
        appleSignInCoordinator = nil

        guard let tokenData = credential.identityToken,
              let idToken = String(data: tokenData, encoding: .utf8) else {
            throw NSError(domain: "AppleSignIn", code: -1,
                          userInfo: [NSLocalizedDescriptionKey: "Missing identity token"])
        }

        try await SupabaseManager.shared.client.auth.signInWithIdToken(
            credentials: OpenIDConnectCredentials(provider: .apple, idToken: idToken)
        )
    }

    func signOut() async throws {
        try await SupabaseManager.shared.client.auth.signOut()
    }
}
