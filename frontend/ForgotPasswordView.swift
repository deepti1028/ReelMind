import SwiftUI

enum ForgotPasswordState {
    case enterEmail, setNewPassword
}

struct ForgotPasswordView: View {
    @EnvironmentObject private var auth: AuthSession

    @State private var state: ForgotPasswordState
    @State private var email: String
    @State private var newPassword = ""
    @State private var confirmPassword = ""
    @State private var showNewPassword = false
    @State private var showConfirmPassword = false
    @State private var isSubmitting = false
    @State private var errorMessage: String?
    @State private var didSendEmail = false

    init(initialState: ForgotPasswordState, prefillEmail: String = "") {
        _state = State(initialValue: initialState)
        _email = State(initialValue: prefillEmail)
    }

    var body: some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()
            ScrollView(showsIndicators: false) {
                VStack(alignment: .leading, spacing: 0) {
                    if state == .enterEmail {
                        enterEmailContent
                    } else {
                        setNewPasswordContent
                    }
                }
                .padding(.horizontal, 26)
                .padding(.top, 60)
                .padding(.bottom, 40)
            }
        }
    }

    // MARK: - Enter Email

    @ViewBuilder
    private var enterEmailContent: some View {
        Text("Reset password")
            .font(.system(size: 22, weight: .semibold, design: .serif))
            .foregroundColor(AppTheme.textPrimary)
            .padding(.bottom, 8)

        Text("Enter your email and we'll send you a link to reset your password.")
            .font(.system(size: 14, weight: .regular, design: .serif))
            .foregroundColor(AppTheme.textMuted)
            .padding(.bottom, 28)

        LabeledAuthField(label: "EMAIL ADDRESS") {
            TextField("", text: $email)
                .textContentType(.emailAddress)
                .keyboardType(.emailAddress)
                .autocapitalization(.none)
                .disableAutocorrection(true)
        }
        .padding(.bottom, 22)

        if let errorMessage {
            Text(errorMessage)
                .font(.footnote)
                .foregroundColor(AppTheme.destructive)
                .padding(.bottom, 10)
        }

        if didSendEmail {
            HStack(spacing: 8) {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundColor(.green)
                Text("Check your inbox — we sent a reset link to \(email)")
                    .font(.system(size: 14))
                    .foregroundColor(AppTheme.textPrimary)
            }
        } else {
            Button(action: sendResetEmail) {
                ZStack {
                    Text("Send reset link")
                        .font(.system(size: 17, weight: .semibold, design: .serif))
                        .foregroundColor(Color(r: 0xfd, g: 0xf4, b: 0xe3))
                        .opacity(isSubmitting ? 0 : 1)
                    if isSubmitting {
                        ProgressView().tint(Color(r: 0xfd, g: 0xf4, b: 0xe3))
                    }
                }
                .frame(maxWidth: .infinity)
                .frame(height: 54)
                .background(AppTheme.buttonGradient)
                .clipShape(RoundedRectangle(cornerRadius: 14))
                .shadow(color: AppTheme.accentDark.opacity(0.35), radius: 12, x: 0, y: 6)
            }
            .disabled(isSubmitting || email.trimmingCharacters(in: .whitespaces).isEmpty)
        }
    }

    // MARK: - Set New Password

    @ViewBuilder
    private var setNewPasswordContent: some View {
        Text("Set new password")
            .font(.system(size: 22, weight: .semibold, design: .serif))
            .foregroundColor(AppTheme.textPrimary)
            .padding(.bottom, 8)

        Text("Choose a new password for your account.")
            .font(.system(size: 14, weight: .regular, design: .serif))
            .foregroundColor(AppTheme.textMuted)
            .padding(.bottom, 28)

        VStack(spacing: 14) {
            LabeledAuthField(label: "NEW PASSWORD") {
                HStack {
                    Group {
                        if showNewPassword {
                            TextField("", text: $newPassword)
                        } else {
                            SecureField("", text: $newPassword)
                        }
                    }
                    .textContentType(.newPassword)
                    Button(action: { showNewPassword.toggle() }) {
                        Image(systemName: showNewPassword ? "eye.slash" : "eye")
                            .foregroundColor(AppTheme.textMuted)
                            .font(.system(size: 15))
                    }
                }
            }

            LabeledAuthField(label: "CONFIRM PASSWORD") {
                HStack {
                    Group {
                        if showConfirmPassword {
                            TextField("", text: $confirmPassword)
                        } else {
                            SecureField("", text: $confirmPassword)
                        }
                    }
                    .textContentType(.newPassword)
                    Button(action: { showConfirmPassword.toggle() }) {
                        Image(systemName: showConfirmPassword ? "eye.slash" : "eye")
                            .foregroundColor(AppTheme.textMuted)
                            .font(.system(size: 15))
                    }
                }
            }
        }
        .padding(.bottom, 10)

        if !confirmPassword.isEmpty && newPassword != confirmPassword {
            Text("Passwords don't match")
                .font(.footnote)
                .foregroundColor(AppTheme.destructive)
                .padding(.bottom, 10)
        }

        if let errorMessage {
            Text(errorMessage)
                .font(.footnote)
                .foregroundColor(AppTheme.destructive)
                .padding(.bottom, 10)
        }

        Button(action: updatePassword) {
            ZStack {
                Text("Update password")
                    .font(.system(size: 17, weight: .semibold, design: .serif))
                    .foregroundColor(Color(r: 0xfd, g: 0xf4, b: 0xe3))
                    .opacity(isSubmitting ? 0 : 1)
                if isSubmitting {
                    ProgressView().tint(Color(r: 0xfd, g: 0xf4, b: 0xe3))
                }
            }
            .frame(maxWidth: .infinity)
            .frame(height: 54)
            .background(AppTheme.buttonGradient)
            .clipShape(RoundedRectangle(cornerRadius: 14))
            .shadow(color: AppTheme.accentDark.opacity(0.35), radius: 12, x: 0, y: 6)
        }
        .disabled(isSubmitting || !canUpdatePassword)
    }

    private var canUpdatePassword: Bool {
        !newPassword.isEmpty && !confirmPassword.isEmpty && newPassword == confirmPassword
    }

    // MARK: - Actions

    private func sendResetEmail() {
        errorMessage = nil
        isSubmitting = true
        Task {
            do {
                try await auth.resetPassword(email: email.trimmingCharacters(in: .whitespaces))
                didSendEmail = true
            } catch {
                errorMessage = error.localizedDescription
            }
            isSubmitting = false
        }
    }

    private func updatePassword() {
        errorMessage = nil
        isSubmitting = true
        Task {
            do {
                try await auth.updatePassword(newPassword)
                // auth.isRecovering is set to false inside updatePassword —
                // RootView's binding will auto-dismiss this sheet
            } catch {
                errorMessage = error.localizedDescription
            }
            isSubmitting = false
        }
    }
}
