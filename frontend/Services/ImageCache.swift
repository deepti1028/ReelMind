import UIKit

final class ImageCache {
    static let shared = ImageCache()
    private let cache = NSCache<NSString, UIImage>()

    private init() {
        cache.countLimit = 200
    }

    func image(for url: String) -> UIImage? {
        cache.object(forKey: url as NSString)
    }

    func insert(_ image: UIImage, for url: String) {
        cache.setObject(image, forKey: url as NSString)
    }
}
