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
            HStack(spacing: 10) {
                ForEach(sources) { source in
                    ChatReelCard(source: source)
                }
            }
            .padding(.vertical, 2)
        }
    }

    private var typingIndicator: some View {
        TypingDotsView()
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

private struct TypingDotsView: View {
    @State private var phase = 0

    var body: some View {
        HStack(spacing: 4) {
            ForEach(0..<3, id: \.self) { i in
                Circle()
                    .fill(AppTheme.textFaint)
                    .frame(width: 6, height: 6)
                    .scaleEffect(phase == i ? 1.4 : 1.0)
                    .animation(
                        .easeInOut(duration: 0.4).repeatForever(autoreverses: true).delay(Double(i) * 0.15),
                        value: phase == i
                    )
            }
        }
        .onAppear { animateDots() }
    }

    private func animateDots() {
        Timer.scheduledTimer(withTimeInterval: 0.45, repeats: true) { _ in
            phase = (phase + 1) % 3
        }
    }
}

// MARK: - Chat Reel Card

private struct ChatReelCard: View {
    let source: ReelSource

    private static let cardW: CGFloat = 90
    private static let cardH: CGFloat = 130

    private var reelURL: URL? { source.url.flatMap { URL(string: $0) } }

    var body: some View {
        Button {
            guard let url = reelURL else { return }
            UIApplication.shared.open(url)
        } label: {
            ZStack(alignment: .bottom) {
                thumbnailLayer
                gradientScrim
                creatorRow
                instaBadge
            }
            .frame(width: Self.cardW, height: Self.cardH)
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(AppTheme.border, lineWidth: 1)
            )
        }
        .buttonStyle(ReelCardPressStyle())
    }

    private var thumbnailLayer: some View {
        Group {
            if let str = source.thumbnailUrl, let url = URL(string: str) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let img):
                        img.resizable().scaledToFill()
                    case .empty:
                        cardPlaceholder
                            .overlay(ProgressView().scaleEffect(0.55).tint(AppTheme.textFaint))
                    default:
                        cardPlaceholder
                    }
                }
            } else {
                cardPlaceholder
            }
        }
        .frame(width: Self.cardW, height: Self.cardH)
        .clipped()
    }

    private var cardPlaceholder: some View {
        ZStack {
            AppTheme.surfaceSecondary
            Circle()
                .fill(AppTheme.accent.opacity(0.07))
                .frame(width: 80, height: 80)
                .offset(x: 18, y: -20)
            Circle()
                .fill(AppTheme.sage.opacity(0.20))
                .frame(width: 44, height: 44)
                .offset(x: -20, y: 24)
            Image(systemName: "movieclapper")
                .font(.system(size: 22, weight: .light))
                .foregroundColor(AppTheme.textFaint.opacity(0.65))
        }
    }

    private var gradientScrim: some View {
        LinearGradient(
            colors: [.clear, Color(red: 0.17, green: 0.12, blue: 0.05).opacity(0.82)],
            startPoint: .init(x: 0.5, y: 0.4),
            endPoint: .bottom
        )
        .frame(width: Self.cardW, height: Self.cardH)
        .allowsHitTesting(false)
    }

    private var creatorRow: some View {
        HStack(spacing: 2) {
            Text("@")
                .font(.system(size: 10, weight: .bold))
                .foregroundColor(AppTheme.accent)
            Text(source.creatorHandle ?? "unknown")
                .font(.system(size: 10, weight: .semibold))
                .foregroundColor(.white)
                .lineLimit(1)
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 8)
        .padding(.bottom, 9)
        .frame(maxWidth: .infinity, alignment: .bottomLeading)
        .allowsHitTesting(false)
    }

    private var instaBadge: some View {
        VStack {
            HStack {
                Spacer()
                Image("instagram-logo")
                    .resizable()
                    .scaledToFit()
                    .frame(width: 12, height: 12)
                    .padding(5)
                    .background(.ultraThinMaterial)
                    .clipShape(Circle())
            }
            Spacer()
        }
        .padding(7)
        .allowsHitTesting(false)
    }
}

private struct ReelCardPressStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? 0.94 : 1.0)
            .animation(.spring(response: 0.22, dampingFraction: 0.65), value: configuration.isPressed)
    }
}

#Preview {
    ChatView(categoryId: UUID(), categoryName: "Skincare")
}
