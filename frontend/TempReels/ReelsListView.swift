import SwiftUI

struct ReelsListView: View {
    let reels: [Reel]
    var onSearch: () -> Void = {}

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            topBar

            VStack(alignment: .leading, spacing: 6) {
                Text("Stored Reels")
                    .font(.system(size: 32, weight: .bold))
                    .foregroundColor(ReelsTheme.brandGreen)
                Text("\(reels.count) saved · pull to refresh")
                    .font(.system(size: 13))
                    .foregroundColor(ReelsTheme.mutedText)
            }
            .padding(.horizontal, 24)
            .padding(.top, 8)
            .padding(.bottom, 16)

            ScrollView {
                LazyVStack(spacing: 12) {
                    ForEach(reels) { reel in
                        ReelCard(reel: reel)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
            }
        }
        .background(ReelsTheme.surface.ignoresSafeArea())
    }

    private var topBar: some View {
        HStack {
            Text("Reel Mind")
                .font(.system(size: 22, weight: .bold))
                .foregroundColor(ReelsTheme.brandGreen)
            Spacer()
            Button(action: onSearch) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundColor(ReelsTheme.brandGreen)
            }
        }
        .padding(.horizontal, 24)
        .padding(.vertical, 14)
    }
}

// MARK: - Card

private struct ReelCard: View {
    let reel: Reel

    private static let dateFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "MMM d, HH:mm"
        return f
    }()

    private var hasMetadata: Bool {
        reel.thumbnailUrl != nil ||
        reel.creatorHandle != nil ||
        !(reel.caption?.isEmpty ?? true) ||
        !reel.hashtags.isEmpty
    }

    var body: some View {
        Group {
            if hasMetadata {
                fullCard
            } else {
                compactCard
            }
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(Color.white)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(Color.black.opacity(0.06), lineWidth: 1)
        )
    }

    // Full card — shown once pipeline has populated metadata fields.
    private var fullCard: some View {
        HStack(alignment: .top, spacing: 12) {
            ThumbnailView(url: reel.thumbnailUrl)

            VStack(alignment: .leading, spacing: 6) {
                headerRow
                if let caption = reel.caption, !caption.isEmpty {
                    Text(caption)
                        .font(.system(size: 13))
                        .foregroundColor(.black.opacity(0.78))
                        .lineLimit(2)
                        .multilineTextAlignment(.leading)
                }
                if !reel.hashtags.isEmpty {
                    HashtagChips(tags: reel.hashtags)
                }
                if let categoryName = reel.categories?.name {
                    CategoryChip(name: categoryName)
                }
                footerRow
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    // Compact card — shown while reel is queued and metadata is absent.
    private var compactCard: some View {
        HStack(spacing: 8) {
            StatusPill(status: reel.status)
            Text(URL(string: reel.url)?.host ?? reel.url)
                .font(.system(size: 13))
                .foregroundColor(ReelsTheme.mutedText)
                .lineLimit(1)
            Spacer()
            Text(ReelCard.dateFormatter.string(from: reel.createdAt))
                .font(.system(size: 11))
                .foregroundColor(ReelsTheme.mutedText)
        }
    }

    private var headerRow: some View {
        HStack(spacing: 6) {
            Text(reel.creatorHandle.map { "@\($0)" } ?? "@unknown")
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(ReelsTheme.brandGreen)
                .lineLimit(1)
            Spacer(minLength: 4)
            StatusPill(status: reel.status)
        }
    }

    private var footerRow: some View {
        HStack(spacing: 8) {
            Text(ReelCard.dateFormatter.string(from: reel.createdAt))
                .font(.system(size: 11))
                .foregroundColor(ReelsTheme.mutedText)

            if let hasAudio = reel.hasAudio {
                Text("·")
                    .font(.system(size: 11))
                    .foregroundColor(ReelsTheme.mutedText)
                Image(systemName: hasAudio ? "waveform" : "doc.text")
                    .font(.system(size: 10))
                    .foregroundColor(ReelsTheme.mutedText)
                Text(hasAudio ? "transcript" : "caption-only")
                    .font(.system(size: 11))
                    .foregroundColor(ReelsTheme.mutedText)
            }

            if reel.status == "processing" || reel.status == "failed" {
                Text("·")
                    .font(.system(size: 11))
                    .foregroundColor(ReelsTheme.mutedText)
                Text("updated \(ReelCard.dateFormatter.string(from: reel.updatedAt))")
                    .font(.system(size: 11))
                    .foregroundColor(ReelsTheme.mutedText)
            }
        }
        .padding(.top, 2)
    }
}

// MARK: - Thumbnail

private struct ThumbnailView: View {
    let url: String?

    var body: some View {
        Group {
            if let urlString = url, let url = URL(string: urlString) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .empty:
                        placeholder.overlay(ProgressView().scaleEffect(0.7))
                    case .success(let image):
                        image
                            .resizable()
                            .aspectRatio(contentMode: .fill)
                    case .failure:
                        placeholder.overlay(
                            Image(systemName: "photo")
                                .foregroundColor(ReelsTheme.mutedText)
                        )
                    @unknown default:
                        placeholder
                    }
                }
            } else {
                placeholder.overlay(
                    Image(systemName: "photo")
                        .foregroundColor(ReelsTheme.mutedText)
                )
            }
        }
        .frame(width: 72, height: 110)
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private var placeholder: some View {
        RoundedRectangle(cornerRadius: 10, style: .continuous)
            .fill(ReelsTheme.cardBackground)
    }
}

// MARK: - Status pill

private struct StatusPill: View {
    let status: String

    var body: some View {
        Text(status)
            .font(.system(size: 10, weight: .semibold))
            .foregroundColor(foreground)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(background)
            .clipShape(Capsule())
            .lineLimit(1)
    }

    private var background: Color {
        switch status {
        case "queued":         return Color.gray.opacity(0.15)
        case "processing":     return Color.orange.opacity(0.18)
        case "ready":          return ReelsTheme.lightGreenTint
        case "uncategorised":  return Color.blue.opacity(0.15)
        case "failed":         return Color.red.opacity(0.15)
        default:               return Color.gray.opacity(0.15)
        }
    }

    private var foreground: Color {
        switch status {
        case "queued":         return Color.gray
        case "processing":     return Color.orange
        case "ready":          return ReelsTheme.brandGreen
        case "uncategorised":  return Color.blue
        case "failed":         return Color.red
        default:               return Color.gray
        }
    }
}

// MARK: - Category chip

private struct CategoryChip: View {
    let name: String

    var body: some View {
        Text(name)
            .font(.system(size: 10, weight: .medium))
            .foregroundColor(.gray)
            .padding(.horizontal, 7)
            .padding(.vertical, 3)
            .background(Color.gray.opacity(0.12))
            .clipShape(Capsule())
            .lineLimit(1)
    }
}

// MARK: - Hashtag chips

private struct HashtagChips: View {
    let tags: [String]
    private let maxVisible = 3

    var body: some View {
        HStack(spacing: 6) {
            ForEach(Array(tags.prefix(maxVisible)), id: \.self) { tag in
                Text("#\(tag)")
                    .font(.system(size: 10, weight: .medium))
                    .foregroundColor(ReelsTheme.brandGreen)
                    .padding(.horizontal, 7)
                    .padding(.vertical, 3)
                    .background(ReelsTheme.lightGreenTint.opacity(0.55))
                    .clipShape(Capsule())
                    .lineLimit(1)
            }
            if tags.count > maxVisible {
                Text("+\(tags.count - maxVisible)")
                    .font(.system(size: 10, weight: .medium))
                    .foregroundColor(ReelsTheme.mutedText)
            }
        }
    }
}

#Preview {
    ReelsListView(reels: [])
}
