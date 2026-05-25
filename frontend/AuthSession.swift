import Auth
import AuthenticationServices
import CryptoKit
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

        let rawNonce = randomNonceString()
        let hashedNonce = sha256(rawNonce)

        let credential = try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<ASAuthorizationAppleIDCredential, Error>) in
            coordinator.continuation = continuation
            let request = ASAuthorizationAppleIDProvider().createRequest()
            request.requestedScopes = [.fullName, .email]
            request.nonce = hashedNonce
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
            credentials: OpenIDConnectCredentials(provider: .apple, idToken: idToken, nonce: rawNonce)
        )
    }

    private func randomNonceString(length: Int = 32) -> String {
        let charset = Array("0123456789ABCDEFGHIJKLMNOPQRSTUVXYZabcdefghijklmnopqrstuvwxyz-._")
        var result = ""
        var remainingLength = length
        while remainingLength > 0 {
            let randoms: [UInt8] = (0 ..< 16).map { _ in
                var random: UInt8 = 0
                _ = SecRandomCopyBytes(kSecRandomDefault, 1, &random)
                return random
            }
            randoms.forEach { random in
                if remainingLength == 0 { return }
                if random < charset.count {
                    result.append(charset[Int(random)])
                    remainingLength -= 1
                }
            }
        }
        return result
    }

    private func sha256(_ input: String) -> String {
        let inputData = Data(input.utf8)
        let hashed = SHA256.hash(data: inputData)
        return hashed.compactMap { String(format: "%02x", $0) }.joined()
    }

    func signOut() async throws {
        try await SupabaseManager.shared.client.auth.signOut()
    }

    func deleteAccount() async throws {
        guard let token = session?.accessToken else {
            throw URLError(.userAuthenticationRequired)
        }
        var request = URLRequest(
            url: AppConfig.backendBaseURL.appendingPathComponent("/api/v1/account")
        )
        request.httpMethod = "DELETE"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.timeoutInterval = 15
        let (_, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 204 else {
            throw URLError(.badServerResponse)
        }
        // The authStateChanges listener fires automatically when Supabase
        // invalidates the session server-side. No explicit signOut() needed.
    }
}
