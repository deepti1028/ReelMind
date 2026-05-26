import SwiftUI

struct CategoryIconPicker: View {
    @Binding var selectedIcon: String
    @Binding var isShowing: Bool

    static let icons: [String] = [
        "fork.knife", "dumbbell", "airplane", "bag", "sparkles",
        "drop", "house", "scissors", "face.smiling", "music.note",
        "headphones", "bolt", "briefcase", "banknote", "cpu",
        "paintpalette", "camera", "leaf", "heart", "figure.and.child.holdinghands",
        "pawprint", "book", "gamecontroller", "graduationcap", "trophy",
        "bookmark"
    ]

    private let columns = Array(repeating: GridItem(.flexible()), count: 5)

    var body: some View {
        LazyVGrid(columns: columns, spacing: 10) {
            ForEach(Self.icons, id: \.self) { symbol in
                Button {
                    selectedIcon = symbol
                    isShowing = false
                } label: {
                    Image(systemName: symbol)
                        .font(.system(size: 18))
                        .frame(width: 44, height: 44)
                        .foregroundColor(selectedIcon == symbol ? .white : AppTheme.accentDark)
                        .background(selectedIcon == symbol
                            ? AppTheme.accent
                            : AppTheme.surfaceSecondary)
                        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.vertical, 8)
    }
}
