import Foundation
import UIKit

// Re-enables the swipe-back gesture on any NavigationController even when
// navigationBarBackButtonHidden(true) is used to show a custom back button.
extension UINavigationController: UIGestureRecognizerDelegate {
    override open func viewDidLoad() {
        super.viewDidLoad()
        interactivePopGestureRecognizer?.delegate = self
    }

    public func gestureRecognizerShouldBegin(_ gestureRecognizer: UIGestureRecognizer) -> Bool {
        viewControllers.count > 1
    }
}

extension Date {
    /// Returns a human-readable relative string: "5m ago", "2h ago", "3 days ago", "1 week ago".
    func timeAgoString() -> String {
        let seconds = Date().timeIntervalSince(self)
        switch seconds {
        case ..<3600:   return "\(max(1, Int(seconds / 60)))m ago"
        case ..<86400:  return "\(Int(seconds / 3600))h ago"
        case ..<604800: return "\(Int(seconds / 86400)) days ago"
        default:        return "\(Int(seconds / 604800)) weeks ago"
        }
    }
}
