import SwiftUI

struct LoginView: View {
    @EnvironmentObject private var auth: AuthSession

    @State private var email = ""
    @State private var password = ""
    @State private var isSubmitting = false
    @State private var errorMessage: String?
    @State private var showSignup = false

    var body: some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()

            VStack(spacing: 24) {
                Spacer()

                Text("Login")
                    .font(.system(size: 36, weight: .bold, design: .serif))
                    .foregroundColor(AppTheme.textPrimary)
                    .frame(maxWidth: .infinity, alignment: .leading)

                VStack(spacing: 16) {
                    TextField("Email", text: $email)
                        .textContentType(.emailAddress)
                        .keyboardType(.emailAddress)
                        .autocapitalization(.none)
                        .disableAutocorrection(true)
                        .padding()
                        .background(AppTheme.surface)
                        .cornerRadius(12)
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(AppTheme.border, lineWidth: 0.5)
                        )

                    SecureField("Password", text: $password)
                        .textContentType(.password)
                        .padding()
                        .background(AppTheme.surface)
                        .cornerRadius(12)
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(AppTheme.border, lineWidth: 0.5)
                        )
                }

                if let errorMessage = errorMessage {
                    Text(errorMessage)
                        .font(.footnote)
                        .foregroundColor(AppTheme.destructive)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                Button(action: submit) {
                    ZStack {
                        Text("LOGIN")
                            .font(.system(size: 16, weight: .bold))
                            .foregroundColor(.white)
                            .opacity(isSubmitting ? 0 : 1)
                        if isSubmitting {
                            ProgressView()
                                .tint(.white)
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .frame(height: 54)
                    .background(AppTheme.accentDark)
                    .clipShape(Capsule())
                    .shadow(color: AppTheme.accentDark.opacity(0.25), radius: 10, x: 0, y: 5)
                }
                .disabled(isSubmitting || !canSubmit)

                HStack {
                    Text("Don't have an account?")
                        .foregroundColor(AppTheme.textMuted)
                    Button("Sign Up") { showSignup = true }
                        .foregroundColor(AppTheme.accentDark)
                        .fontWeight(.semibold)
                }
                .font(.footnote)

                Spacer()
            }
            .padding(.horizontal, 24)
        }
        .sheet(isPresented: $showSignup) {
            SignupView()
                .environmentObject(auth)
        }
    }

    private var canSubmit: Bool {
        !email.trimmingCharacters(in: .whitespaces).isEmpty &&
        !password.isEmpty
    }

    private func submit() {
        errorMessage = nil
        isSubmitting = true
        Task {
            do {
                try await auth.signIn(email: email, password: password)
            } catch {
                errorMessage = error.localizedDescription
            }
            isSubmitting = false
        }
    }
}
