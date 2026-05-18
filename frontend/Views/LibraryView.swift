import SwiftUI

struct LibraryView: View {
    @EnvironmentObject private var appVM: AppViewModel
    @EnvironmentObject private var auth: AuthSession

    private let columns = [GridItem(.flexible()), GridItem(.flexible())]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                topBar
                    .padding(.horizontal, 20)
                    .padding(.top, 6)
                    .padding(.bottom, 12)

                if appVM.inboxCount > 0 {
                    inboxBanner
                        .padding(.horizontal, 14)
                        .padding(.bottom, 12)
                }

                Text("Collections")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(AppTheme.textFaint)
                    .textCase(.uppercase)
                    .kerning(1.2)
                    .padding(.horizontal, 20)
                    .padding(.bottom, 8)

                LazyVGrid(columns: columns, spacing: 9) {
                    ForEach(appVM.categorySummaries) { summary in
                        NavigationLink(value: summary) {
                            CategoryCard(summary: summary)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 14)
            }
        }
        .background(AppTheme.background.ignoresSafeArea())
        .navigationBarHidden(true)
        .navigationDestination(for: CategorySummary.self) { summary in
            CategoryDetailView(summary: summary)
        }
    }

    // MARK: - Sub-views

    private var topBar: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Your library")
                    .font(.system(size: 28, weight: .bold))
                    .foregroundColor(AppTheme.textPrimary)
                Text("\(appVM.totalCount) reels saved")
                    .font(.system(size: 13))
                    .foregroundColor(AppTheme.textFaint)
            }
            Spacer()
            Button { appVM.showSettings = true } label: {
                Circle()
                    .fill(AppTheme.avatarGradient)
                    .frame(width: 36, height: 36)
                    .overlay(
                        Text(auth.session?.user.email?.prefix(1).uppercased() ?? "?")
                            .font(.system(size: 14, weight: .bold))
                            .foregroundColor(.white)
                    )
            }
            .buttonStyle(.plain)
        }
    }

    private var inboxBanner: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(AppTheme.accent)
                .frame(width: 7, height: 7)
            (Text("\(appVM.inboxCount) reels")
                .fontWeight(.bold)
                .foregroundColor(AppTheme.accent)
            + Text(" need a category")
                .foregroundColor(AppTheme.textMuted))
            .font(.system(size: 12))
            Spacer()
            Text("›")
                .font(.system(size: 16))
                .foregroundColor(AppTheme.textFaint)
        }
        .padding(.horizontal, 13)
        .padding(.vertical, 10)
        .background(AppTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 13, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 13, style: .continuous)
                .stroke(AppTheme.border, lineWidth: 1)
        )
    }
}

// MARK: - Category card

private struct CategoryCard: View {
    let summary: CategorySummary

    var body: some View {
        VStack(alignment: .leading) {
            Text("\(summary.reelCount)")
                .font(.system(size: 34, weight: .heavy))
                .foregroundColor(AppTheme.textPrimary)
            Spacer()
            VStack(alignment: .leading, spacing: 2) {
                Text(summary.name)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(AppTheme.textSecondary)
                    .lineLimit(1)
                if let date = summary.lastSavedAt {
                    Text("Updated \(date.timeAgoString())")
                        .font(.system(size: 10))
                        .foregroundColor(AppTheme.textFaint)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .aspectRatio(1, contentMode: .fit)
        .background(AppTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(AppTheme.border, lineWidth: 1)
        )
    }
}

#Preview {
    NavigationStack {
        LibraryView()
    }
    .environmentObject(AppViewModel())
    .environmentObject(AuthSession())
}
