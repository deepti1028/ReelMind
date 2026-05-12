import SwiftUI
import UIKit

/// Presents the native iOS share sheet so the user can locate ReelMind
/// and pin it to their favorites. Used by the onboarding "Share Sheet
/// Access" toggle to make it functionally meaningful (not just decorative).
struct ShareSheetPresenter: UIViewControllerRepresentable {
    let items: [Any]
    let onDismiss: () -> Void

    func makeUIViewController(context: Context) -> UIActivityViewController {
        let controller = UIActivityViewController(activityItems: items, applicationActivities: nil)
        controller.completionWithItemsHandler = { _, _, _, _ in
            onDismiss()
        }
        return controller
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}
