import SwiftUI

enum OnboardingTheme {
    static let background = Color(red: 0.93, green: 0.91, blue: 0.97)
    static let backgroundDeep = Color(red: 0.88, green: 0.84, blue: 0.94)
    static let primary = Color(red: 0.24, green: 0.17, blue: 0.56)
    static let primaryDark = Color(red: 0.13, green: 0.09, blue: 0.30)
    static let cardSurface = Color.white
    static let iconBackground = Color(red: 0.91, green: 0.89, blue: 0.96)
    static let textPrimary = Color(red: 0.10, green: 0.10, blue: 0.18)
    static let textMuted = Color(red: 0.42, green: 0.42, blue: 0.54)
    static let divider = Color(red: 0.85, green: 0.83, blue: 0.92)

    static let serifTitle = Font.system(size: 40, weight: .bold, design: .serif)
    static let serifSection = Font.system(size: 32, weight: .bold, design: .serif)
    static let bodyText = Font.system(size: 16, weight: .regular)
    static let caption = Font.system(size: 13, weight: .medium)
}
