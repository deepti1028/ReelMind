import SwiftUI

struct ThumbnailView: View {
    let urlString: String?
    var width: CGFloat = 54
    var height: CGFloat = 80

    var body: some View {
        Group {
            if let str = urlString, let url = URL(string: str) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .empty:
                        placeholder
                            .overlay(ProgressView().scaleEffect(0.6).tint(AppTheme.textFaint))
                    case .success(let image):
                        image
                            .resizable()
                            .scaledToFill()
                            .frame(width: width, height: height)
                            .clipped()
                    case .failure:
                        placeholder
                    @unknown default:
                        placeholder
                    }
                }
            } else {
                placeholder
            }
        }
        .frame(width: width, height: height)
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
    }

    private var placeholder: some View {
        ZStack {
            AppTheme.surface
            // Subtle ink-splatter texture feel via layered circles
            Circle()
                .fill(AppTheme.accent.opacity(0.06))
                .frame(width: width * 1.1, height: width * 1.1)
                .offset(x: width * 0.22, y: -height * 0.18)
            Circle()
                .fill(AppTheme.sage.opacity(0.18))
                .frame(width: width * 0.55, height: width * 0.55)
                .offset(x: -width * 0.28, y: height * 0.22)
            // Clapperboard icon
            Image(systemName: "movieclapper")
                .font(.system(size: min(width, height) * 0.30, weight: .light))
                .foregroundColor(AppTheme.textFaint.opacity(0.7))
        }
    }
}

#Preview {
    HStack(spacing: 12) {
        ThumbnailView(urlString: nil)
        ThumbnailView(urlString: nil, width: 58, height: 88)
    }
    .padding()
    .background(AppTheme.background)
}
