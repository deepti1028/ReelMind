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
                        image.resizable().scaledToFill()
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
        AppTheme.thumbnailGradient
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
