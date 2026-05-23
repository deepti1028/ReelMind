import Auth
import SwiftUI

struct LibraryView: View {
    @EnvironmentObject private var appVM: AppViewModel
    @EnvironmentObject private var auth: AuthSession
    var onInboxTap: () -> Void = {}

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                topBar
                    .padding(.horizontal, 20)
                    .padding(.top, 6)
                    .padding(.bottom, 12)

                if appVM.inboxCount > 0 {
                    inboxBanner
                        .padding(.horizontal, 14)
                        .padding(.bottom, 12)
                }

                if appVM.categorySummaries.isEmpty && appVM.inboxCount == 0 {
                    libraryEmptyState
                        .padding(.horizontal, 20)
                        .padding(.top, 20)
                } else if !appVM.categorySummaries.isEmpty {
                    Text("Collections")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(AppTheme.textFaint)
                        .textCase(.uppercase)
                        .kerning(1.2)
                        .padding(.horizontal, 20)
                        .padding(.bottom, 8)

                    CollageLayout(summaries: appVM.categorySummaries)
                        .padding(.horizontal, 14)
                }
            }
        }
        .refreshable { await appVM.load() }
        .background(AppTheme.background.ignoresSafeArea())
        .navigationBarHidden(true)
        .navigationDestination(for: CategorySummary.self) { summary in
            CategoryDetailView(summary: summary)
        }
    }

    // MARK: - Sub-views

    private var libraryEmptyState: some View {
        VStack(alignment: .leading, spacing: 24) {
            VStack(alignment: .leading, spacing: 10) {
                Image(systemName: "sparkles")
                    .font(.system(size: 36))
                    .foregroundColor(AppTheme.accent)
                    .padding(.bottom, 4)
                Text("Your library is empty")
                    .font(.system(size: 22, weight: .bold))
                    .foregroundColor(AppTheme.textPrimary)
                Text("Share reels from Instagram to build your personal collection.")
                    .font(.system(size: 14))
                    .foregroundColor(AppTheme.textMuted)
            }

            VStack(spacing: 0) {
                LibraryHowToStep(number: 1, text: "Open any reel in Instagram")
                Divider().background(AppTheme.border).padding(.leading, 42)
                LibraryHowToStep(number: 2, text: "Tap the Share button")
                Divider().background(AppTheme.border).padding(.leading, 42)
                LibraryHowToStep(number: 3, text: "Select ReelMind from the list")
            }
            .background(AppTheme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(AppTheme.border, lineWidth: 1)
            )
        }
    }

    private var topBar: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Your library")
                    .font(.system(size: 28, weight: .bold))
                    .foregroundColor(AppTheme.textPrimary)
                Text("\(appVM.totalCount) reels saved")
                    .font(.system(size: 13))
                    .foregroundColor(AppTheme.textFaint)
            }
            Spacer()
            Button { appVM.showSettings = true } label: {
                Circle()
                    .fill(AppTheme.avatarGradient)
                    .frame(width: 36, height: 36)
                    .overlay(
                        Text(auth.session?.user.email?.prefix(1).uppercased() ?? "?")
                            .font(.system(size: 14, weight: .bold))
                            .foregroundColor(.white)
                    )
            }
            .buttonStyle(.plain)
        }
    }

    private var inboxBanner: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(AppTheme.accent)
                .frame(width: 7, height: 7)
            (Text("\(appVM.inboxCount) reels")
                .fontWeight(.bold)
                .foregroundColor(AppTheme.accent)
            + Text(" need a category")
                .foregroundColor(AppTheme.textMuted))
            .font(.system(size: 12))
            Spacer()
            Text("›")
                .font(.system(size: 16))
                .foregroundColor(AppTheme.textFaint)
        }
        .padding(.horizontal, 13)
        .padding(.vertical, 10)
        .background(AppTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 13, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 13, style: .continuous)
                .stroke(AppTheme.border, lineWidth: 1)
        )
        .contentShape(Rectangle())
        .onTapGesture { onInboxTap() }
    }
}

// MARK: - How-to step

private struct LibraryHowToStep: View {
    let number: Int
    let text: String

    var body: some View {
        HStack(spacing: 12) {
            Text("\(number)")
                .font(.system(size: 12, weight: .bold))
                .foregroundColor(AppTheme.accent)
                .frame(width: 26, height: 26)
                .background(AppTheme.surfaceSecondary)
                .clipShape(Circle())
            Text(text)
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(AppTheme.textSecondary)
            Spacer()
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 13)
    }
}

// MARK: - Collage Layout

private struct CollageLayout: View {
    let summaries: [CategorySummary]

    private var sorted: [CategorySummary] {
        summaries.sorted { $0.reelCount > $1.reelCount }
    }

    private struct LayoutRow {
        let items: [CategorySummary]
        let colorIndices: [Int]
        let isSolo: Bool
        let pairIndex: Int
    }

    private var rows: [LayoutRow] {
        let items = sorted
        guard !items.isEmpty else { return [] }

        var result: [LayoutRow] = []

        result.append(LayoutRow(items: [items[0]], colorIndices: [0], isSolo: true, pairIndex: 0))
        guard items.count > 1 else { return result }

        var remaining = Array(items.dropFirst())
        var nextColor = 1
        var pairIdx = 0

        // Odd remainder: prepend one full-width solo before pairing
        if remaining.count % 2 == 1 {
            result.append(LayoutRow(items: [remaining.removeFirst()], colorIndices: [nextColor], isSolo: true, pairIndex: 0))
            nextColor += 1
        }

        while remaining.count >= 2 {
            let pair = [remaining.removeFirst(), remaining.removeFirst()]
            result.append(LayoutRow(items: pair, colorIndices: [nextColor, nextColor + 1], isSolo: false, pairIndex: pairIdx))
            nextColor += 2
            pairIdx += 1
        }

        return result
    }

    var body: some View {
        VStack(spacing: 7) {
            ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                rowView(row)
            }
        }
    }

    @ViewBuilder
    private func rowView(_ row: LayoutRow) -> some View {
        if row.isSolo {
            cardLink(row.items[0], colorIndex: row.colorIndices[0], isNarrow: false)
        } else {
            let isWideFirst = row.pairIndex % 2 == 0
            GeometryReader { geo in
                HStack(spacing: 7) {
                    let gap: CGFloat = 7
                    let wide = (geo.size.width - gap) * 2 / 3
                    let narrow = (geo.size.width - gap) * 1 / 3
                    if isWideFirst {
                        cardLink(row.items[0], colorIndex: row.colorIndices[0], isNarrow: false)
                            .frame(width: wide)
                        cardLink(row.items[1], colorIndex: row.colorIndices[1], isNarrow: true)
                            .frame(width: narrow)
                    } else {
                        cardLink(row.items[0], colorIndex: row.colorIndices[0], isNarrow: true)
                            .frame(width: narrow)
                        cardLink(row.items[1], colorIndex: row.colorIndices[1], isNarrow: false)
                            .frame(width: wide)
                    }
                }
            }
            .frame(height: 116)
        }
    }

    private func cardLink(_ summary: CategorySummary, colorIndex: Int, isNarrow: Bool) -> some View {
        NavigationLink(value: summary) {
            CategoryCard(summary: summary, colorIndex: colorIndex, isNarrow: isNarrow)
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Category Card

private struct CategoryCard: View {
    let summary: CategorySummary
    let colorIndex: Int
    var isNarrow: Bool = false

    private var bgColor: Color { AppTheme.cardBackgrounds[colorIndex % 10] }
    private var iconColor: Color { AppTheme.cardIconColors[colorIndex % 10] }
    private var iconSize: CGFloat { isNarrow ? 20 : 26 }
    private var wmFontSize: CGFloat { isNarrow ? 48 : 68 }
    private var wmOffset: CGFloat { isNarrow ? 8 : 12 }
    private var nameFontSize: CGFloat { isNarrow ? 12 : 13 }

    var body: some View {
        ZStack(alignment: .bottomTrailing) {
            bgColor

            Text("\(summary.reelCount)")
                .font(.system(size: wmFontSize, weight: .heavy))
                .foregroundColor(AppTheme.textPrimary.opacity(0.065))
                .offset(x: 3, y: wmOffset)
                .allowsHitTesting(false)

            VStack(alignment: .leading, spacing: 0) {
                Image(systemName: summary.icon ?? "bookmark")
                    .font(.system(size: iconSize))
                    .foregroundColor(iconColor)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)

                VStack(alignment: .leading, spacing: 2) {
                    Text(summary.name)
                        .font(.system(size: nameFontSize, weight: .bold))
                        .foregroundColor(AppTheme.textPrimary)
                        .lineLimit(1)
                    if let date = summary.lastSavedAt {
                        Text("Updated \(date.timeAgoString())")
                            .font(.system(size: 8.5))
                            .foregroundColor(AppTheme.textFaint)
                    }
                }
            }
            .padding(11)
        }
        .frame(maxWidth: .infinity)
        .frame(height: 116)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(Color.black.opacity(0.055), lineWidth: 1)
        )
    }
}

#Preview {
    NavigationStack {
        LibraryView()
    }
    .environmentObject(AppViewModel())
    .environmentObject(AuthSession())
}
