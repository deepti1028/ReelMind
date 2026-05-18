import SwiftUI

struct SignupView: View {
    @EnvironmentObject private var auth: AuthSession
    @Environment(\.dismiss) private var dismiss

    @State private var email = ""
    @State private var password = ""
    @State private var confirmPassword = ""
    @State private var isSubmitting = false
    @State private var errorMessage: String?
    @State private var infoMessage: String?

    var body: some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()

            VStack(spacing: 24) {
                Spacer()

                Text("Create an account")
                    .font(.system(size: 30, weight: .bold, design: .serif))
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
                        .textContentType(.newPassword)
                        .padding()
                        .background(AppTheme.surface)
                        .cornerRadius(12)
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(AppTheme.border, lineWidth: 0.5)
                        )

                    SecureField("Confirm Password", text: $confirmPassword)
                        .textContentType(.newPassword)
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
                } else if let infoMessage = infoMessage {
                    Text(infoMessage)
                        .font(.footnote)
                        .foregroundColor(AppTheme.textMuted)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                Button(action: submit) {
                    ZStack {
                        Text("SIGN UP")
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
                    Text("Already have an account?")
                        .foregroundColor(AppTheme.textMuted)
                    Button("Login") { dismiss() }
                        .foregroundColor(AppTheme.accentDark)
                        .fontWeight(.semibold)
                }
                .font(.footnote)

                Spacer()
            }
            .padding(.horizontal, 24)
        }
    }

    private var canSubmit: Bool {
        !email.trimmingCharacters(in: .whitespaces).isEmpty &&
        password.count >= 6 &&
        password == confirmPassword
    }

    private func submit() {
        errorMessage = nil
        infoMessage = nil
        guard password == confirmPassword else {
            errorMessage = "Passwords do not match"
            return
        }
        isSubmitting = true
        Task {
            do {
                try await auth.signUp(email: email, password: password)
                if auth.session == nil {
                    infoMessage = "Check your email to confirm your account, then log in."
                } else {
                    dismiss()
                }
            } catch {
                errorMessage = error.localizedDescription
            }
            isSubmitting = false
        }
    }
}
