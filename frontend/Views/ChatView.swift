import SwiftUI
import Combine

@MainActor
private final class ChatViewModel: ObservableObject {
    @Published var messages: [ChatMessage] = []
    @Published var isLoading = false
    @Published var inputText = ""
    private var sessionId: String?

    let categoryId: UUID

    init(categoryId: UUID) {
        self.categoryId = categoryId
    }

    func startSession() async {
        do {
            sessionId = try await ChatService.shared.createSession(categoryId: categoryId)
        } catch {
            print("[ChatViewModel] createSession failed: \(error)")
        }
    }

    func send() async {
        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, let sessionId else { return }
        inputText = ""
        isLoading = true
        let userMsg = ChatMessage(
            id: UUID().uuidString,
            role: "user",
            content: text,
            sources: [],
            createdAt: Date()
        )
        messages.append(userMsg)
        do {
            let reply = try await ChatService.shared.sendMessage(sessionId: sessionId, content: text)
            messages.append(reply)
        } catch {
            print("[ChatViewModel] sendMessage failed: \(error)")
        }
        isLoading = false
    }

    func sendPrompt(_ prompt: String) async {
        inputText = prompt
        await send()
    }
}

// MARK: - Main view

struct ChatView: View {
    let categoryId: UUID
    let categoryName: String
    @Environment(\.dismiss) private var dismiss
    @StateObject private var viewModel: ChatViewModel

    init(categoryId: UUID, categoryName: String) {
        self.categoryId = categoryId
        self.categoryName = categoryName
        _viewModel = StateObject(wrappedValue: ChatViewModel(categoryId: categoryId))
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().background(AppTheme.borderSubtle)

            if viewModel.messages.isEmpty {
                emptyState
            } else {
                messageList
            }

            inputBar
        }
        .background(AppTheme.background.ignoresSafeArea())
        .task { await viewModel.startSession() }
    }

    // MARK: Header

    private var header: some View {
        HStack(alignment: .center) {
            VStack(alignment: .leading, spacing: 5) {
                HStack(spacing: 5) {
                    Circle()
                        .fill(AppTheme.accent)
                        .frame(width: 7, height: 7)
                    Text("\(categoryName) · Chat")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(AppTheme.textSecondary)
                        .kerning(0.5)
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 3)
                .background(AppTheme.surfaceSecondary)
                .clipShape(Capsule())
                .overlay(Capsule().stroke(AppTheme.sage, lineWidth: 1))

                Text(categoryName)
                    .font(.system(size: 22, weight: .bold))
                    .foregroundColor(AppTheme.textPrimary)
            }
            Spacer()
            Button { dismiss() } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 9, weight: .bold))
                    .foregroundColor(AppTheme.textMuted)
                    .frame(width: 22, height: 22)
                    .background(AppTheme.surface)
                    .clipShape(Circle())
                    .overlay(Circle().stroke(AppTheme.border, lineWidth: 1))
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 18)
        .padding(.top, 10)
        .padding(.bottom, 14)
    }

    // MARK: Empty state

    private let prompts = [
        "sunscreen for oily skin under ₹500",
        "retinol routine for beginners",
        "best niacinamide serums"
    ]

    private var emptyState: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                Circle()
                    .fill(AppTheme.surface)
                    .overlay(Circle().stroke(AppTheme.border, lineWidth: 1))
                    .frame(width: 40, height: 40)
                    .overlay(
                        Image(systemName: "cpu")
                            .font(.system(size: 16))
                            .foregroundColor(AppTheme.accent)
                    )
                    .padding(.bottom, 16)

                Text("What are you looking for?")
                    .font(.system(size: 24, weight: .bold))
                    .foregroundColor(AppTheme.textPrimary)
                    .padding(.bottom, 8)

                Text("I've read every reel in your \(categoryName.lowercased()) collection. Ask anything specific.")
                    .font(.system(size: 13))
                    .foregroundColor(AppTheme.textMuted)
                    .lineLimit(3)
                    .padding(.bottom, 24)

                Text("TRY ASKING")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(AppTheme.textFaint)
                    .kerning(1)
                    .padding(.bottom, 10)

                ForEach(prompts, id: \.self) { prompt in
                    Button { Task { await viewModel.sendPrompt(prompt) } } label: {
                        Text(prompt)
                            .font(.system(size: 13))
                            .foregroundColor(AppTheme.textSecondary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(14)
                            .background(AppTheme.surface)
                            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                            .overlay(
                                RoundedRectangle(cornerRadius: 10, style: .continuous)
                                    .stroke(AppTheme.border, lineWidth: 1)
                            )
                    }
                    .buttonStyle(.plain)
                    .padding(.bottom, 8)
                }
            }
            .padding(.horizontal, 18)
            .padding(.top, 28)
        }
    }

    // MARK: Message list

    private var messageList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    ForEach(viewModel.messages) { msg in
                        if msg.role == "user" {
                            userBubble(msg.content)
                                .id(msg.id)
                        } else {
                            aiBubble(msg)
                                .id(msg.id)
                        }
                    }
                    if viewModel.isLoading {
                        typingIndicator
                    }
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 14)
            }
            .onChange(of: viewModel.messages.count) { _, _ in
                if let last = viewModel.messages.last {
                    withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                }
            }
        }
    }

    private func userBubble(_ text: String) -> some View {
        HStack {
            Spacer(minLength: 60)
            Text(text)
                .font(.system(size: 13))
                .foregroundColor(AppTheme.textPrimary)
                .padding(.horizontal, 13)
                .padding(.vertical, 10)
                .background(AppTheme.surface)
                .clipShape(
                    UnevenRoundedRectangle(
                        topLeadingRadius: 16, bottomLeadingRadius: 16,
                        bottomTrailingRadius: 4, topTrailingRadius: 16
                    )
                )
                .overlay(
                    UnevenRoundedRectangle(
                        topLeadingRadius: 16, bottomLeadingRadius: 16,
                        bottomTrailingRadius: 4, topTrailingRadius: 16
                    )
                    .stroke(AppTheme.border, lineWidth: 1)
                )
        }
    }

    private func aiBubble(_ msg: ChatMessage) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Circle()
                    .fill(AppTheme.surfaceSecondary)
                    .overlay(Circle().stroke(AppTheme.sage, lineWidth: 1))
                    .frame(width: 16, height: 16)
                    .overlay(
                        Circle().fill(AppTheme.accent).frame(width: 6, height: 6)
                    )
                Text("ReelMind")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(AppTheme.accent)
                    .textCase(.uppercase)
                    .kerning(0.5)
            }
            Text(msg.content)
                .font(.system(size: 12))
                .foregroundColor(AppTheme.textSecondary)
                .lineSpacing(4)
                .padding(13)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.white)
                .clipShape(
                    UnevenRoundedRectangle(
                        topLeadingRadius: 4, bottomLeadingRadius: 16,
                        bottomTrailingRadius: 16, topTrailingRadius: 16
                    )
                )
                .overlay(
                    UnevenRoundedRectangle(
                        topLeadingRadius: 4, bottomLeadingRadius: 16,
                        bottomTrailingRadius: 16, topTrailingRadius: 16
                    )
                    .stroke(AppTheme.borderSubtle, lineWidth: 1)
                )

            if !msg.sources.isEmpty {
                inlineReels(msg.sources)
            }
        }
    }

    private func inlineReels(_ sources: [ReelSource]) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(sources) { source in
                    VStack(alignment: .leading, spacing: 0) {
                        ThumbnailView(urlString: source.thumbnailUrl, width: 130, height: 80)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(source.creatorHandle.map { "@\($0)" } ?? "@unknown")
                                .font(.system(size: 10, weight: .semibold))
                                .foregroundColor(AppTheme.accent)
                            if let caption = source.caption {
                                Text(caption)
                                    .font(.system(size: 10))
                                    .foregroundColor(AppTheme.textMuted)
                                    .lineLimit(2)
                                    .padding(.bottom, 6)
                            }
                            Text("Watch reel")
                                .font(.system(size: 10, weight: .semibold))
                                .foregroundColor(AppTheme.textSecondary)
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 5)
                                .background(AppTheme.surfaceSecondary)
                                .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
                                .overlay(
                                    RoundedRectangle(cornerRadius: 7, style: .continuous)
                                        .stroke(AppTheme.sage, lineWidth: 1)
                                )
                        }
                        .padding(.horizontal, 8)
                        .padding(.top, 7)
                        .padding(.bottom, 8)
                    }
                    .frame(width: 130)
                    .background(AppTheme.surface)
                    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .stroke(AppTheme.border, lineWidth: 1)
                    )
                }
            }
        }
    }

    private var typingIndicator: some View {
        HStack(spacing: 4) {
            ForEach(0..<3, id: \.self) { _ in
                Circle()
                    .fill(AppTheme.textFaint)
                    .frame(width: 6, height: 6)
            }
        }
        .padding(12)
        .background(Color.white)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    // MARK: Input bar

    private var inputBar: some View {
        HStack(spacing: 8) {
            TextField("Ask anything about \(categoryName.lowercased())...",
                      text: $viewModel.inputText)
                .font(.system(size: 13))
                .foregroundColor(AppTheme.textPrimary)
                .padding(.horizontal, 14)
                .padding(.vertical, 9)
                .background(AppTheme.surface)
                .clipShape(Capsule())
                .overlay(Capsule().stroke(AppTheme.border, lineWidth: 1))
                .submitLabel(.send)
                .onSubmit { Task { await viewModel.send() } }

            Button { Task { await viewModel.send() } } label: {
                Image(systemName: "arrow.up")
                    .font(.system(size: 14, weight: .bold))
                    .foregroundColor(.white)
                    .frame(width: 34, height: 34)
                    .background(AppTheme.accent)
                    .clipShape(Circle())
            }
            .buttonStyle(.plain)
            .disabled(viewModel.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        .padding(.horizontal, 14)
        .padding(.top, 10)
        .padding(.bottom, 22)
        .background(AppTheme.background)
        .overlay(alignment: .top) {
            Rectangle().fill(AppTheme.borderSubtle).frame(height: 1)
        }
    }
}

#Preview {
    ChatView(categoryId: UUID(), categoryName: "Skincare")
}
