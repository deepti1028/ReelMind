import SwiftUI

struct CachedAsyncImage<Content: View>: View {
    let urlString: String?
    @ViewBuilder let content: (AsyncImagePhase) -> Content

    @State private var phase: AsyncImagePhase = .empty

    var body: some View {
        content(phase)
            .task(id: urlString) {
                await load()
            }
    }

    @MainActor
    private func load() async {
        guard let str = urlString, let url = URL(string: str) else {
            phase = .empty
            return
        }
        if let cached = ImageCache.shared.image(for: str) {
            phase = .success(Image(uiImage: cached))
            return
        }
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            guard let uiImage = UIImage(data: data) else {
                phase = .failure(URLError(.cannotDecodeContentData))
                return
            }
            ImageCache.shared.insert(uiImage, for: str)
            phase = .success(Image(uiImage: uiImage))
        } catch {
            guard !(error is CancellationError),
                  (error as? URLError)?.code != .cancelled else { return }
            phase = .failure(error)
        }
    }
}
