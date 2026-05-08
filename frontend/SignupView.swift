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
        VStack(spacing: 24) {
            Spacer()

            Text("Create an account")
                .font(.system(size: 28, weight: .bold))
                .frame(maxWidth: .infinity, alignment: .leading)

            VStack(spacing: 16) {
                TextField("Email", text: $email)
                    .textContentType(.emailAddress)
                    .keyboardType(.emailAddress)
                    .autocapitalization(.none)
                    .disableAutocorrection(true)
                    .padding()
                    .background(Color(.systemGray6))
                    .cornerRadius(8)

                SecureField("Password", text: $password)
                    .textContentType(.newPassword)
                    .padding()
                    .background(Color(.systemGray6))
                    .cornerRadius(8)

                SecureField("Confirm Password", text: $confirmPassword)
                    .textContentType(.newPassword)
                    .padding()
                    .background(Color(.systemGray6))
                    .cornerRadius(8)
            }

            if let errorMessage = errorMessage {
                Text(errorMessage)
                    .font(.footnote)
                    .foregroundColor(.red)
                    .frame(maxWidth: .infinity, alignment: .leading)
            } else if let infoMessage = infoMessage {
                Text(infoMessage)
                    .font(.footnote)
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }

            Button(action: submit) {
                ZStack {
                    Text("SIGN UP")
                        .font(.system(size: 16, weight: .bold))
                        .foregroundColor(.black)
                        .opacity(isSubmitting ? 0 : 1)
                    if isSubmitting {
                        ProgressView()
                    }
                }
                .frame(maxWidth: .infinity)
                .frame(height: 50)
                .background(Color.yellow)
                .cornerRadius(8)
            }
            .disabled(isSubmitting || !canSubmit)

            HStack {
                Text("Already have an account?")
                    .foregroundColor(.secondary)
                Button("Login") { dismiss() }
                    .foregroundColor(.orange)
                    .fontWeight(.semibold)
            }
            .font(.footnote)

            Spacer()
        }
        .padding(.horizontal, 24)
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
                // If Supabase returns no session, email confirmation is on.
                // Tell the user to check their inbox; auth state listener will
                // promote them once they confirm + sign in.
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
