import SwiftUI

struct EmptyReelsView: View {
    var onAddReel: () -> Void = {}
    var onMenu: () -> Void = {}

    var body: some View {
        VStack(spacing: 0) {

            Spacer(minLength: 24)

            illustration

            Text("Your Archive is Empty")
                .font(.system(size: 26, weight: .bold))
                .foregroundColor(ReelsTheme.surface)
                .padding(.top, 28)

            Text("Start saving your favorite reels to see\nthem here. Build your personal\ncollection of inspiration.")
                .font(.system(size: 16))
                .foregroundColor(ReelsTheme.mutedText)
                .multilineTextAlignment(.center)
                .padding(.top, 12)
                .padding(.horizontal, 24)

                .padding(.horizontal, 32)
                .padding(.top, 32)

            Spacer(minLength: 24)
        }
        .background(ReelsTheme.surface.ignoresSafeArea())
    }

    private var topBar: some View {
        HStack {
            Button(action: onMenu) {
                Image(systemName: "line.3.horizontal")
                    .font(.system(size: 22, weight: .semibold))
                    .foregroundColor(ReelsTheme.brandGreen)
            }
            Spacer()
            Text("Reel Mind")
                .font(.system(size: 22, weight: .bold))
                .foregroundColor(ReelsTheme.brandGreen)
            Spacer()
            Button(action: onAddReel) {
                Image(systemName: "plus.circle")
                    .font(.system(size: 24, weight: .regular))
                    .foregroundColor(ReelsTheme.brandGreen)
            }
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 12)
    }

    private var illustration: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [
                            Color(red: 0.97, green: 0.97, blue: 0.96),
                            Color(red: 0.86, green: 0.92, blue: 0.94)
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .frame(width: 240, height: 240)

            Image(systemName: "tray")
                .resizable()
                .scaledToFit()
                .frame(width: 120, height: 120)
                .foregroundStyle(ReelsTheme.brandGreen.opacity(0.65))
        }
    }


    private func tabItem(icon: String, title: String, isActive: Bool) -> some View {
        VStack(spacing: 4) {
            ZStack {
                if isActive {
                    Capsule()
                        .fill(ReelsTheme.lightGreenTint)
                        .frame(width: 56, height: 32)
                }
                Image(systemName: icon)
                    .font(.system(size: 18, weight: .regular))
                    .foregroundColor(ReelsTheme.brandGreen)
            }
            Text(title)
                .font(.system(size: 11, weight: .semibold))
                .tracking(0.6)
                .foregroundColor(.primary.opacity(0.85))
        }
        .frame(maxWidth: .infinity)
    }
}

#Preview {
    EmptyReelsView()
}
