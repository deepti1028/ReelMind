import SwiftUI

enum OnboardingTheme {
    static let background     = AppTheme.background        // #fefae0 warm cream
    static let backgroundDeep = AppTheme.surface           // #faedcd warm surface
    static let primary        = AppTheme.accent            // #d4a373 caramel
    static let primaryDark    = AppTheme.accentDark        // #9a6a35 dark caramel
    static let cardSurface    = Color.white
    static let iconBackground = AppTheme.surfaceSecondary  // #e9edc9 sage tint
    static let textPrimary    = AppTheme.textPrimary       // #2c1f0e dark brown
    static let textMuted      = AppTheme.textMuted         // #9a7654 muted brown
    static let divider        = AppTheme.border            // #e5d5b8 warm border

    static let serifTitle   = Font.system(size: 40, weight: .bold, design: .serif)
    static let serifSection = Font.system(size: 32, weight: .bold, design: .serif)
    static let bodyText     = Font.system(size: 16, weight: .regular)
    static let caption      = Font.system(size: 13, weight: .medium)
}
