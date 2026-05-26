import SwiftUI

struct FeedbackFormView: View {
    @Environment(\.dismiss) private var dismiss

    @State private var selectedType: FeedbackAPI.FeedbackType = .general
    @State private var message = ""
    @State private var isSending = false
    @State private var showSuccess = false
    @State private var showError = false

    private var canSend: Bool {
        !message.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !isSending
    }

    var body: some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()
            VStack(spacing: 0) {
                handle
                header
                ScrollView {
                    VStack(spacing: 0) {
                        typePicker
                            .padding(.horizontal, 14)
                            .padding(.bottom, 20)
                        messageField
                            .padding(.horizontal, 14)
                            .padding(.bottom, 24)
                        sendButton
                            .padding(.horizontal, 14)
                    }
                }
            }
            if showSuccess {
                successToast
            }
        }
        .alert("Couldn't send feedback", isPresented: $showError) {
            Button("OK", role: .cancel) {}
        } message: {
            Text("Something went wrong. Please try again.")
        }
    }

    // MARK: - Sub-views

    private var handle: some View {
        RoundedRectangle(cornerRadius: 2, style: .continuous)
            .fill(AppTheme.border)
            .frame(width: 36, height: 4)
            .padding(.top, 10)
            .padding(.bottom, 6)
    }

    private var header: some View {
        HStack {
            Text("Send Feedback")
                .font(.system(size: 17, weight: .bold))
                .foregroundColor(AppTheme.textPrimary)
            Spacer()
            Button("Cancel") { dismiss() }
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(AppTheme.accentDark)
        }
        .padding(.horizontal, 18)
        .padding(.bottom, 16)
    }

    private var typePicker: some View {
        FormSection(title: "Type") {
            HStack {
                Text("Feedback type")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(AppTheme.textPrimary)
                Spacer()
                Picker("", selection: $selectedType) {
                    ForEach(FeedbackAPI.FeedbackType.allCases, id: \.self) { t in
                        Text(t.rawValue).tag(t)
                    }
                }
                .pickerStyle(.menu)
                .tint(AppTheme.accentDark)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 13)
        }
    }

    private var messageField: some View {
        FormSection(title: "Message") {
            ZStack(alignment: .topLeading) {
                if message.isEmpty {
                    Text("Describe your feedback…")
                        .font(.system(size: 13))
                        .foregroundColor(AppTheme.textFaint)
                        .padding(.horizontal, 14)
                        .padding(.top, 14)
                        .allowsHitTesting(false)
                }
                TextEditor(text: $message)
                    .font(.system(size: 13))
                    .foregroundColor(AppTheme.textPrimary)
                    .scrollContentBackground(.hidden)
                    .background(Color.clear)
                    .frame(minHeight: 120)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 10)
                    .onChange(of: message) { _, newValue in
                        if newValue.count > 2000 {
                            message = String(newValue.prefix(2000))
                        }
                    }
            }
        }
    }

    private var sendButton: some View {
        Button {
            Task { await submitFeedback() }
        } label: {
            ZStack {
                AppTheme.buttonGradient
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                if isSending {
                    ProgressView().tint(.white)
                } else {
                    Text("Send")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundColor(.white)
                }
            }
            .frame(height: 50)
        }
        .disabled(!canSend)
    }

    private var successToast: some View {
        VStack {
            Spacer()
            Text("Feedback sent!")
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(.white)
                .padding(.horizontal, 20)
                .padding(.vertical, 12)
                .background(AppTheme.accentDark)
                .clipShape(Capsule())
                .padding(.bottom, 40)
        }
        .transition(.move(edge: .bottom).combined(with: .opacity))
    }

    // MARK: - Action

    private func submitFeedback() async {
        isSending = true
        do {
            try await FeedbackAPI.send(type: selectedType, message: message)
            withAnimation { showSuccess = true }
            try? await Task.sleep(for: .seconds(1.5))
            dismiss()
        } catch {
            showError = true
        }
        isSending = false
    }
}

// Mirrors the private SettingsSection in SettingsView.swift — duplicated
// intentionally to keep each file self-contained.
private struct FormSection<Content: View>: View {
    let title: String
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.system(size: 10, weight: .semibold))
                .foregroundColor(AppTheme.textFaint)
                .textCase(.uppercase)
                .kerning(1.2)
                .padding(.leading, 4)
            VStack(spacing: 0) {
                content
            }
            .background(AppTheme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(AppTheme.border, lineWidth: 1)
            )
        }
    }
}

#Preview {
    FeedbackFormView()
}
