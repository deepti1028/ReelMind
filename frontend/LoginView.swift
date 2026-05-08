import SwiftUI

struct LoginView: View {
    @EnvironmentObject private var auth: AuthSession

    @State private var email = ""
    @State private var password = ""
    @State private var isSubmitting = false
    @State private var errorMessage: String?
    @State private var showSignup = false

    var body: some View {
        VStack(spacing: 24) {
            Spacer()

            Text("Login")
                .font(.system(size: 32, weight: .bold))
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
                    .textContentType(.password)
                    .padding()
                    .background(Color(.systemGray6))
                    .cornerRadius(8)
            }

            if let errorMessage = errorMessage {
                Text(errorMessage)
                    .font(.footnote)
                    .foregroundColor(.red)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }

            Button(action: submit) {
                ZStack {
                    Text("LOGIN")
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
                Text("Don't have an account?")
                    .foregroundColor(.secondary)
                Button("Sign Up") { showSignup = true }
                    .foregroundColor(.orange)
                    .fontWeight(.semibold)
            }
            .font(.footnote)

            Spacer()
        }
        .padding(.horizontal, 24)
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
