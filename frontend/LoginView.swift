import SwiftUI

struct LoginView: View {
    @EnvironmentObject private var auth: AuthSession

    @State private var email = ""
    @State private var password = ""
    @State private var isSubmitting = false
    @State private var errorMessage: String?
    @State private var showSignup = false
    @State private var showPassword = false
    @State private var showForgotPassword = false

    var body: some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()

            ScrollView(showsIndicators: false) {
                VStack(alignment: .leading, spacing: 0) {

                    // Wordmark
                    HStack(spacing: 0) {
                        Text("Reel")
                            .font(.system(size: 38, weight: .bold, design: .serif))
                            .foregroundColor(AppTheme.textPrimary)
                        Text("Mind")
                            .font(.system(size: 38, weight: .bold, design: .serif))
                            .italic()
                            .foregroundColor(AppTheme.accentDark)
                    }
                    .padding(.bottom, 5)

                    Text("Save what inspires you.")
                        .font(.system(size: 14, weight: .regular, design: .serif))
                        .italic()
                        .foregroundColor(AppTheme.textMuted)
                        .padding(.bottom, 32)

                    Text("Welcome back")
                        .font(.system(size: 22, weight: .semibold, design: .serif))
                        .foregroundColor(AppTheme.textPrimary)
                        .padding(.bottom, 20)

                    // Fields
                    VStack(spacing: 14) {
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
                                .textContentType(.password)
                                Button(action: { showPassword.toggle() }) {
                                    Image(systemName: showPassword ? "eye.slash" : "eye")
                                        .foregroundColor(AppTheme.textMuted)
                                        .font(.system(size: 15))
                                }
                            }
                        }
                    }
                    .padding(.bottom, 10)

                    // Forgot password
                    HStack {
                        Spacer()
                        Button("Forgot password?") { showForgotPassword = true }
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(AppTheme.accentDark)
                    }
                    .padding(.bottom, 22)

                    if let errorMessage {
                        Text(errorMessage)
                            .font(.footnote)
                            .foregroundColor(AppTheme.destructive)
                            .padding(.bottom, 10)
                    }

                    // Primary button
                    Button(action: submit) {
                        ZStack {
                            Text("Log in")
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
                    .disabled(isSubmitting || !canSubmit)
                    .padding(.bottom, 22)

                    SocialAuthDivider()
                        .padding(.bottom, 14)

                    VStack(spacing: 11) {
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
                    .padding(.bottom, 32)

                    HStack {
                        Spacer()
                        Text("New here?")
                            .foregroundColor(AppTheme.textMuted)
                        Button("Create an account") { showSignup = true }
                            .foregroundColor(AppTheme.accentDark)
                            .fontWeight(.semibold)
                        Spacer()
                    }
                    .font(.footnote)
                }
                .padding(.horizontal, 26)
                .padding(.top, 80)
                .padding(.bottom, 40)
            }
        }
        .sheet(isPresented: $showSignup) {
            SignupView().environmentObject(auth)
        }
        .sheet(isPresented: $showForgotPassword) {
            ForgotPasswordView(initialState: .enterEmail, prefillEmail: email)
                .environmentObject(auth)
        }
    }

    private var canSubmit: Bool {
        !email.trimmingCharacters(in: .whitespaces).isEmpty && !password.isEmpty
    }

    private func submit() {
        errorMessage = nil
        isSubmitting = true
        Task {
            do { try await auth.signIn(email: email, password: password) }
            catch { errorMessage = error.localizedDescription }
            isSubmitting = false
        }
    }
}
