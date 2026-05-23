import SwiftUI

// MARK: - Base block

struct SkeletonBlock: View {
    var cornerRadius: CGFloat = 7
    @State private var on = false

    var body: some View {
        RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
            .fill(on ? AppTheme.border : AppTheme.surfaceSecondary)
            .onAppear {
                withAnimation(.easeInOut(duration: 0.95).repeatForever(autoreverses: true)) {
                    on = true
                }
            }
    }
}

// MARK: - Library skeleton (content inside LibraryView's ScrollView)

struct LibrarySkeletonContent: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Top bar
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 6) {
                    SkeletonBlock(cornerRadius: 8)
                        .frame(width: 148, height: 28)
                    SkeletonBlock(cornerRadius: 5)
                        .frame(width: 92, height: 13)
                }
                Spacer()
                SkeletonBlock(cornerRadius: 18)
                    .frame(width: 36, height: 36)
            }
            .padding(.horizontal, 20)
            .padding(.top, 6)
            .padding(.bottom, 24)

            // "Collections" label
            SkeletonBlock(cornerRadius: 4)
                .frame(width: 68, height: 10)
                .padding(.horizontal, 20)
                .padding(.bottom, 10)

            // Collage card skeletons
            VStack(spacing: 7) {
                // Row 1: full-width solo
                SkeletonBlock(cornerRadius: 14)
                    .frame(maxWidth: .infinity)
                    .frame(height: 116)

                // Row 2: wide-left pair
                GeometryReader { geo in
                    HStack(spacing: 7) {
                        let wide   = (geo.size.width - 7) * 2 / 3
                        let narrow = (geo.size.width - 7) * 1 / 3
                        SkeletonBlock(cornerRadius: 14).frame(width: wide,   height: 116)
                        SkeletonBlock(cornerRadius: 14).frame(width: narrow, height: 116)
                    }
                }
                .frame(height: 116)

                // Row 3: wide-right pair
                GeometryReader { geo in
                    HStack(spacing: 7) {
                        let wide   = (geo.size.width - 7) * 2 / 3
                        let narrow = (geo.size.width - 7) * 1 / 3
                        SkeletonBlock(cornerRadius: 14).frame(width: narrow, height: 116)
                        SkeletonBlock(cornerRadius: 14).frame(width: wide,   height: 116)
                    }
                }
                .frame(height: 116)
            }
            .padding(.horizontal, 14)
        }
    }
}

// MARK: - Inbox skeleton (standalone scrollable view)

struct InboxSkeletonContent: View {
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                // Header
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 6) {
                        SkeletonBlock(cornerRadius: 8)
                            .frame(width: 168, height: 26)
                        SkeletonBlock(cornerRadius: 5)
                            .frame(width: 220, height: 12)
                    }
                    Spacer()
                    SkeletonBlock(cornerRadius: 18)
                        .frame(width: 36, height: 36)
                }
                .padding(.horizontal, 20)
                .padding(.top, 8)
                .padding(.bottom, 18)

                // Card skeletons
                VStack(spacing: 10) {
                    ForEach(0..<5, id: \.self) { _ in
                        InboxCardSkeleton()
                    }
                }
                .padding(.horizontal, 14)
            }
        }
    }
}

private struct InboxCardSkeleton: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .top, spacing: 10) {
                SkeletonBlock(cornerRadius: 8)
                    .frame(width: 54, height: 80)

                VStack(alignment: .leading, spacing: 6) {
                    SkeletonBlock(cornerRadius: 5)
                        .frame(width: 96, height: 12)
                    SkeletonBlock(cornerRadius: 5)
                        .frame(maxWidth: .infinity)
                        .frame(height: 11)
                    SkeletonBlock(cornerRadius: 5)
                        .frame(width: 130, height: 11)
                }
                .padding(.top, 2)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.horizontal, 12)
            .padding(.top, 11)
            .padding(.bottom, 10)

            HStack(spacing: 6) {
                SkeletonBlock(cornerRadius: 13).frame(width: 68, height: 26)
                SkeletonBlock(cornerRadius: 13).frame(width: 80, height: 26)
                SkeletonBlock(cornerRadius: 13).frame(width: 60, height: 26)
            }
            .padding(.horizontal, 12)
            .padding(.bottom, 11)
        }
        .background(AppTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(AppTheme.border, lineWidth: 1)
        )
    }
}
