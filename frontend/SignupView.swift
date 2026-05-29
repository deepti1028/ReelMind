import SwiftUI

struct SignupView: View {
    @EnvironmentObject private var auth: AuthSession
    @Environment(\.dismiss) private var dismiss

    @State private var displayName = ""
    @State private var email = ""
    @State private var password = ""
    @State private var confirmPassword = ""
    @State private var isSubmitting = false
    @State private var errorMessage: String?
    @State private var infoMessage: String?
    @State private var showPassword = false
    @State private var showConfirmPassword = false

    var body: some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()

            ScrollView(showsIndicators: false) {
                VStack(alignment: .leading, spacing: 0) {

                    // Wordmark
                    HStack(spacing: 0) {
                        Text("Reel")
                            .font(.system(size: 34, weight: .bold, design: .serif))
                            .foregroundColor(AppTheme.textPrimary)
                        Text("Mind")
                            .font(.system(size: 34, weight: .bold, design: .serif))
                            .italic()
                            .foregroundColor(AppTheme.accentDark)
                    }
                    .padding(.bottom, 4)

                    Text("Your personal reel library.")
                        .font(.system(size: 13.5, weight: .regular, design: .serif))
                        .italic()
                        .foregroundColor(AppTheme.textMuted)
                        .padding(.bottom, 26)

                    Text("Create account")
                        .font(.system(size: 20, weight: .semibold, design: .serif))
                        .foregroundColor(AppTheme.textPrimary)
                        .padding(.bottom, 18)

                    // Fields
                    VStack(spacing: 12) {
                        LabeledAuthField(label: "DISPLAY NAME") {
                            TextField("", text: $displayName)
                                .textContentType(.name)
                                .autocapitalization(.words)
                                .disableAutocorrection(true)
                        }

                        LabeledAuthField(label: "EMAIL ADDRESS") {
                            TextField("", text: $email)
                                .textContentType(.emailAddress)
                                .keyboardType(.emailAddress)
                                .autocapitalization(.none)
                                .disableAutocorrection(true)
                        }

                        LabeledAuthField(label: "PASSWORD") {
                            HStack {
                                Group {
                                    if showPassword {
                                        TextField("", text: $password)
                                    } else {
                                        SecureField("", text: $password)
                                    }
                                }
                                .textContentType(.newPassword)
                                Button(action: { showPassword.toggle() }) {
                                    Image(systemName: showPassword ? "eye.slash" : "eye")
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
                    .padding(.bottom, 18)

                    if let errorMessage {
                        Text(errorMessage)
                            .font(.footnote)
                            .foregroundColor(AppTheme.destructive)
                            .padding(.bottom, 10)
                    } else if let infoMessage {
                        Text(infoMessage)
                            .font(.footnote)
                            .foregroundColor(AppTheme.textMuted)
                            .padding(.bottom, 10)
                    }

                    // Primary button
                    Button(action: submit) {
                        ZStack {
                            Text("Create account")
                                .font(.system(size: 16, weight: .semibold, design: .serif))
                                .foregroundColor(Color(r: 0xfd, g: 0xf4, b: 0xe3))
                                .opacity(isSubmitting ? 0 : 1)
                            if isSubmitting {
                                ProgressView().tint(Color(r: 0xfd, g: 0xf4, b: 0xe3))
                            }
                        }
                        .frame(maxWidth: .infinity)
                        .frame(height: 52)
                        .background(AppTheme.buttonGradient)
                        .clipShape(RoundedRectangle(cornerRadius: 14))
                        .shadow(color: AppTheme.accentDark.opacity(0.35), radius: 10, x: 0, y: 5)
                    }
                    .disabled(isSubmitting)
                    .padding(.bottom, 20)

                    SocialAuthDivider()
                        .padding(.bottom, 13)

                    VStack(spacing: 10) {
                        GoogleSignInButton {
                            errorMessage = nil
                            do { try await auth.signInWithGoogle() }
                            catch { errorMessage = error.localizedDescription }
                        }
                        AppleSignInButton {
                            errorMessage = nil
                            do { try await auth.signInWithApple() }
                            catch { errorMessage = error.localizedDescription }
                        }
                    }
                    .disabled(isSubmitting)
                    .padding(.bottom, 28)

                    HStack {
                        Spacer()
                        Text("Already a member?")
                            .foregroundColor(AppTheme.textMuted)
                        Button("Log in") { dismiss() }
                            .foregroundColor(AppTheme.accentDark)
                            .fontWeight(.semibold)
                        Spacer()
                    }
                    .font(.footnote)
                }
                .padding(.horizontal, 26)
                .padding(.top, 70)
                .padding(.bottom, 40)
            }
        }
    }

    private func submit() {
        errorMessage = nil
        infoMessage = nil
        let trimmedName = displayName.trimmingCharacters(in: .whitespaces)
        let trimmedEmail = email.trimmingCharacters(in: .whitespaces)
        guard !trimmedName.isEmpty else { errorMessage = "Please enter your display name."; return }
        guard !trimmedEmail.isEmpty else { errorMessage = "Please enter your email address."; return }
        guard password.count >= 6 else { errorMessage = "Password must be at least 6 characters."; return }
        guard password == confirmPassword else { errorMessage = "Passwords do not match."; return }
        isSubmitting = true
        Task {
            do {
                try await auth.signUp(email: trimmedEmail, password: password, displayName: trimmedName)
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
