import SwiftUI

struct FooterTabBar: View {
    @Binding var selectedTab: Int
    let inboxCount: Int

    var body: some View {
        HStack(spacing: 0) {
            FooterTabButton(
                label: "Library",
                systemImage: selectedTab == 0 ? "square.grid.2x2.fill" : "square.grid.2x2",
                isActive: selectedTab == 0,
                badge: 0
            ) { selectedTab = 0 }

            FooterTabButton(
                label: "Inbox",
                systemImage: "tray.and.arrow.down",
                isActive: selectedTab == 1,
                badge: inboxCount
            ) { selectedTab = 1 }
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 8)
        .background(AppTheme.background)
        .overlay(alignment: .top) {
            Rectangle()
                .fill(AppTheme.borderSubtle)
                .frame(height: 1)
        }
    }
}

private struct FooterTabButton: View {
    let label: String
    let systemImage: String
    let isActive: Bool
    let badge: Int
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 3) {
                ZStack(alignment: .topTrailing) {
                    Image(systemName: systemImage)
                        .font(.system(size: 20))
                        .foregroundColor(isActive ? AppTheme.accent : AppTheme.textFaint)
                    if badge > 0 {
                        Text("\(min(badge, 99))")
                            .font(.system(size: 9, weight: .black))
                            .foregroundColor(.white)
                            .frame(width: 15, height: 15)
                            .background(AppTheme.accent)
                            .clipShape(Circle())
                            .offset(x: 9, y: -5)
                    }
                }
                Text(label)
                    .font(.system(size: 10, weight: .medium))
                    .foregroundColor(isActive ? AppTheme.accent : AppTheme.textFaint)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 4)
            .padding(.bottom, 8)
        }
        .buttonStyle(.plain)
    }
}

#Preview {
    VStack {
        Spacer()
        FooterTabBar(selectedTab: .constant(0), inboxCount: 3)
    }
    .background(AppTheme.background)
}
