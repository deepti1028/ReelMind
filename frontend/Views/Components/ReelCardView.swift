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
                HStack(alignment: .top, spacing: 12) {
                    inboxThumbnail
                        .padding(.vertical, 10)

                    VStack(alignment: .leading, spacing: 5) {
                        (Text("@").foregroundColor(AppTheme.accent)
                            + Text(reel.creatorHandle ?? "unknown").foregroundColor(AppTheme.accentDark))
                            .font(.system(size: 13, weight: .bold))
                            .lineLimit(1)

                        HStack(spacing: 4) {
                            Image(systemName: "clock")
                                .font(.system(size: 9))
                                .foregroundColor(AppTheme.textFaint)
                            Text("Saved \(reel.createdAt.timeAgoString())")
                                .font(.system(size: 10, weight: .medium))
                                .foregroundColor(AppTheme.textFaint)
                        }

                        if let caption = reel.caption, !caption.isEmpty {
                            Text(caption)
                                .font(.system(size: 11))
                                .foregroundColor(AppTheme.textMuted)
                                .lineLimit(3)
                                .lineSpacing(1.5)
                        }

                        if !reel.hashtags.isEmpty {
                            HStack(spacing: 5) {
                                ForEach(reel.hashtags.prefix(3), id: \.self) { tag in
                                    Text("#\(tag)")
                                        .lineLimit(1)
                                        .truncationMode(.tail)
                                        .font(.system(size: 10, weight: .medium))
                                        .foregroundColor(AppTheme.accentDark)
                                        .padding(.horizontal, 7)
                                        .padding(.vertical, 3)
                                        .background(AppTheme.accent.opacity(0.12))
                                        .clipShape(Capsule())
                                        .frame(maxWidth: 90)
                                }
                            }
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .topLeading)
                    .padding(.vertical, 12)
                }
                .padding(.horizontal, 12)

                Rectangle()
                    .fill(AppTheme.border)
                    .frame(height: 1)
                    .padding(.leading, 12)

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
                    .padding(.vertical, 9)
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

    // Thumbnail with no fixed height — stretches to match the content column
    private var inboxThumbnail: some View {
        Group {
            if let str = reel.thumbnailUrl, let url = URL(string: str) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let image):
                        image.resizable().scaledToFill().clipped()
                    case .empty:
                        inboxThumbnailPlaceholder
                            .overlay(ProgressView().scaleEffect(0.6).tint(AppTheme.textFaint))
                    default:
                        inboxThumbnailPlaceholder
                    }
                }
            } else {
                inboxThumbnailPlaceholder
            }
        }
        .frame(width: 72)
        .frame(maxHeight: .infinity)
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private var inboxThumbnailPlaceholder: some View {
        ZStack {
            AppTheme.surface
            Circle()
                .fill(AppTheme.accent.opacity(0.06))
                .frame(width: 60, height: 60)
                .offset(x: 14, y: -10)
            Circle()
                .fill(AppTheme.sage.opacity(0.18))
                .frame(width: 32, height: 32)
                .offset(x: -16, y: 14)
            Image(systemName: "movieclapper")
                .font(.system(size: 20, weight: .light))
                .foregroundColor(AppTheme.textFaint.opacity(0.7))
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
            HStack(alignment: .center, spacing: 12) {
                ThumbnailView(urlString: reel.thumbnailUrl, width: 90, height: 130)

                VStack(alignment: .leading, spacing: 0) {
                    // Creator — bold and unmissable
                    (Text("@").foregroundColor(AppTheme.accent)
                        + Text(reel.creatorHandle ?? "unknown").foregroundColor(AppTheme.accentDark))
                        .font(.system(size: 14, weight: .bold))
                        .lineLimit(1)

                    Spacer().frame(height: 6)

                    // Caption — fixed-height area so all cards align regardless of content
                    Group {
                        if let caption = reel.caption, !caption.isEmpty {
                            Text(caption)
                                .font(.system(size: 12))
                                .foregroundColor(AppTheme.textMuted)
                                .lineLimit(3)
                                .lineSpacing(1.5)
                        } else {
                            Color.clear
                        }
                    }
                    .frame(maxWidth: .infinity, minHeight: 50, alignment: .topLeading)

                    // Hashtags — only when present, no layout penalty when absent
                    if !reel.hashtags.isEmpty {
                        Spacer().frame(height: 6)
                        HStack(spacing: 5) {
                            ForEach(reel.hashtags.prefix(3), id: \.self) { tag in
                                Text("#\(tag)")
                                    .font(.system(size: 10, weight: .medium))
                                    .foregroundColor(AppTheme.accentDark)
                                    .padding(.horizontal, 7)
                                    .padding(.vertical, 3)
                                    .background(AppTheme.accent.opacity(0.12))
                                    .clipShape(Capsule())
                            }
                        }
                    }

                    Spacer(minLength: 8)

                    // Time footer — anchored to bottom of card
                    if isContentUnavailable {
                        Label("Content may be unavailable", systemImage: "exclamationmark.triangle")
                            .font(.system(size: 10))
                            .foregroundColor(AppTheme.destructive.opacity(0.75))
                    } else {
                        HStack(spacing: 4) {
                            Image(systemName: "clock")
                                .font(.system(size: 9))
                                .foregroundColor(AppTheme.textFaint)
                            Text("Saved \(reel.createdAt.timeAgoString())")
                                .font(.system(size: 10, weight: .medium))
                                .foregroundColor(AppTheme.textFaint)
                        }
                    }
                }
                .padding(.vertical, 12)
                .frame(maxWidth: .infinity, minHeight: 130, alignment: .topLeading)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
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
