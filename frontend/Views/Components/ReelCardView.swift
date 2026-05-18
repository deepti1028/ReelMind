import SwiftUI

// MARK: - Inbox variant (thumbnail + creator + caption + category chips)

struct InboxReelCard: View {
    let reel: Reel
    let categoryOptions: [CategorySummary]
    let onAssign: (UUID) -> Void
    let onDelete: () -> Void
    let onReassign: () -> Void

    private var reelURL: URL? { URL(string: reel.url) }

    var body: some View {
        Button {
            guard let url = reelURL else { return }
            UIApplication.shared.open(url)
        } label: {
            VStack(alignment: .leading, spacing: 0) {
                HStack(alignment: .top, spacing: 10) {
                    ThumbnailView(urlString: reel.thumbnailUrl, width: 54, height: 80)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(reel.creatorHandle.map { "@\($0)" } ?? "@unknown")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(AppTheme.accent)
                            .lineLimit(1)
                        if let caption = reel.caption, !caption.isEmpty {
                            Text(caption)
                                .font(.system(size: 11))
                                .foregroundColor(AppTheme.textMuted)
                                .lineLimit(2)
                        }
                    }
                }
                .padding(.horizontal, 12)
                .padding(.top, 11)
                .padding(.bottom, 8)

                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(categoryOptions.prefix(3)) { cat in
                            Button { onAssign(cat.id) } label: {
                                Text(cat.name)
                                    .font(.system(size: 11, weight: .medium))
                                    .foregroundColor(AppTheme.textSecondary)
                                    .padding(.horizontal, 10)
                                    .padding(.vertical, 4)
                                    .background(AppTheme.surfaceSecondary)
                                    .clipShape(Capsule())
                                    .overlay(Capsule().stroke(AppTheme.sage, lineWidth: 1))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal, 12)
                    .padding(.bottom, 11)
                }
            }
            .background(AppTheme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(AppTheme.border, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .contextMenu {
            Button { onReassign() } label: {
                Label("Assign Category", image: "reassign-icon")
            }
            Button {
                guard let url = reelURL else { return }
                UIApplication.shared.open(url)
            } label: {
                Label("Open in Instagram", image: "instagram-logo")
            }
            Button(role: .destructive) { onDelete() } label: {
                Label("Delete Reel", systemImage: "trash")
            }
        }
    }
}

// MARK: - Detail variant (thumbnail + creator + caption + hashtags + time footer)

struct DetailReelCard: View {
    let reel: Reel
    let onDelete: () -> Void
    let onReassign: () -> Void

    @State private var openFailed = false

    private var reelURL: URL? { URL(string: reel.url) }
    private var isContentUnavailable: Bool { reelURL == nil || openFailed }

    var body: some View {
        Button {
            guard let url = reelURL else { openFailed = true; return }
            UIApplication.shared.open(url, options: [:]) { success in
                if !success { openFailed = true }
            }
        } label: {
            VStack(alignment: .leading, spacing: 0) {
                HStack(alignment: .top, spacing: 10) {
                    ThumbnailView(urlString: reel.thumbnailUrl, width: 58, height: 88)
                    VStack(alignment: .leading, spacing: 5) {
                        Text(reel.creatorHandle.map { "@\($0)" } ?? "@unknown")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(AppTheme.accent)
                            .lineLimit(1)
                        if let caption = reel.caption, !caption.isEmpty {
                            Text(caption)
                                .font(.system(size: 11))
                                .foregroundColor(AppTheme.textMuted)
                                .lineLimit(2)
                        }
                        if !reel.hashtags.isEmpty {
                            HStack(spacing: 5) {
                                ForEach(reel.hashtags.prefix(3), id: \.self) { tag in
                                    Text("#\(tag)")
                                        .font(.system(size: 10, weight: .medium))
                                        .foregroundColor(AppTheme.accentDark)
                                        .padding(.horizontal, 7)
                                        .padding(.vertical, 2)
                                        .background(AppTheme.accent.opacity(0.12))
                                        .clipShape(Capsule())
                                }
                            }
                        }
                    }
                }
                .padding(.horizontal, 12)
                .padding(.top, 11)

                HStack {
                    Text(reel.createdAt.timeAgoString())
                        .font(.system(size: 10))
                        .foregroundColor(AppTheme.textFaint)
                    Spacer()
                    if isContentUnavailable {
                        Label("Content may be unavailable", systemImage: "exclamationmark.triangle")
                            .font(.system(size: 10))
                            .foregroundColor(AppTheme.destructive.opacity(0.75))
                    } else {
                        Label("tap to watch", systemImage: "arrow.up.forward")
                            .font(.system(size: 10))
                            .foregroundColor(AppTheme.textFaint)
                    }
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
            }
            .background(AppTheme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(isContentUnavailable ? AppTheme.destructive.opacity(0.3) : AppTheme.border, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .contextMenu {
            Button { onReassign() } label: {
                Label("Reassign Category", image: "reassign-icon")
            }
            Button {
                guard let url = reelURL else { return }
                UIApplication.shared.open(url)
            } label: {
                Label("Open in Instagram", image: "instagram-logo")
            }
            Button(role: .destructive) { onDelete() } label: {
                Label("Delete Reel", systemImage: "trash")
            }
        }
    }
}
