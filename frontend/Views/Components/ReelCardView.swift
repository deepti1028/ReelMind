import SwiftUI

// MARK: - Inbox variant (thumbnail + creator + caption + category chips)

struct InboxReelCard: View {
    let reel: Reel
    let categoryOptions: [CategorySummary]
    let onAssign: (UUID) -> Void
    let onDelete: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .top, spacing: 10) {
                ThumbnailView(urlString: reel.thumbnailUrl, width: 54, height: 80)
                VStack(alignment: .leading, spacing: 4) {
                    HStack(alignment: .top) {
                        Text(reel.creatorHandle.map { "@\($0)" } ?? "@unknown")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(AppTheme.accent)
                            .lineLimit(1)
                        Spacer()
                        Button(action: onDelete) {
                            Image(systemName: "trash")
                                .font(.system(size: 13))
                                .foregroundColor(AppTheme.destructive)
                        }
                        .buttonStyle(.plain)
                    }
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
                    ForEach(categoryOptions.prefix(4)) { cat in
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
                    if categoryOptions.count > 4 {
                        Text("+\(categoryOptions.count - 4)")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundColor(AppTheme.textFaint)
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
}

// MARK: - Detail variant (thumbnail + creator + caption + hashtags + time footer)

struct DetailReelCard: View {
    let reel: Reel
    let onDelete: () -> Void
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            VStack(alignment: .leading, spacing: 0) {
                HStack(alignment: .top, spacing: 10) {
                    ThumbnailView(urlString: reel.thumbnailUrl, width: 58, height: 88)
                    VStack(alignment: .leading, spacing: 5) {
                        HStack(alignment: .top) {
                            Text(reel.creatorHandle.map { "@\($0)" } ?? "@unknown")
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundColor(AppTheme.accent)
                                .lineLimit(1)
                            Spacer()
                            Button(action: onDelete) {
                                Image(systemName: "trash")
                                    .font(.system(size: 13))
                                    .foregroundColor(AppTheme.destructive)
                            }
                            .buttonStyle(.plain)
                        }
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
                    Label("tap to watch", systemImage: "arrow.up.forward")
                        .font(.system(size: 10))
                        .foregroundColor(AppTheme.textFaint)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
            }
            .background(AppTheme.surface)
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(AppTheme.border, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}
