import SwiftUI

enum AppTheme {
    // Backgrounds
    static let background        = Color(r: 0xfe, g: 0xfa, b: 0xe0) // #fefae0
    static let surface           = Color(r: 0xfa, g: 0xed, b: 0xcd) // #faedcd
    static let surfaceSecondary  = Color(r: 0xe9, g: 0xed, b: 0xc9) // #e9edc9
    static let border            = Color(r: 0xe5, g: 0xd5, b: 0xb8) // #e5d5b8
    static let borderSubtle      = Color(r: 0xe9, g: 0xed, b: 0xc9) // #e9edc9

    // Accent
    static let accent            = Color(r: 0xd4, g: 0xa3, b: 0x73) // #d4a373
    static let accentDark        = Color(r: 0x9a, g: 0x6a, b: 0x35) // #9a6a35
    static let sage              = Color(r: 0xcc, g: 0xd5, b: 0xae) // #ccd5ae

    // Text
    static let textPrimary       = Color(r: 0x2c, g: 0x1f, b: 0x0e) // #2c1f0e
    static let textSecondary     = Color(r: 0x5a, g: 0x3e, b: 0x28) // #5a3e28
    static let textMuted         = Color(r: 0x9a, g: 0x76, b: 0x54) // #9a7654
    static let textFaint         = Color(r: 0xb8, g: 0x95, b: 0x6a) // #b8956a

    // Destructive
    static let destructive       = Color(r: 0xcc, g: 0x44, b: 0x44) // #cc4444

    // Gradients
    static var avatarGradient: LinearGradient {
        LinearGradient(colors: [accent, accentDark],
                       startPoint: .topLeading, endPoint: .bottomTrailing)
    }
    static var thumbnailGradient: LinearGradient {
        LinearGradient(colors: [surfaceSecondary, sage],
                       startPoint: .topLeading, endPoint: .bottomTrailing)
    }
}

extension Color {
    init(r: UInt8, g: UInt8, b: UInt8) {
        self.init(red: Double(r) / 255, green: Double(g) / 255, blue: Double(b) / 255)
    }
}
