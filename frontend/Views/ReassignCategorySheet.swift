import SwiftUI

struct ReassignCategorySheet: View {
    let reel: Reel
    var onComplete: () -> Void = {}

    @EnvironmentObject private var appVM: AppViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var newCategoryName = ""
    @State private var isWorking = false
    @State private var errorMessage: String?

    var body: some View {
        VStack(spacing: 0) {
            dragHandle

            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    headerSection
                        .padding(.horizontal, 20)
                        .padding(.top, 8)
                        .padding(.bottom, 20)

                    categoryList
                        .padding(.horizontal, 14)

                    newCategoryRow
                        .padding(.horizontal, 14)
                        .padding(.top, 12)
                        .padding(.bottom, 32)
                }
            }
        }
        .background(AppTheme.background.ignoresSafeArea())
        .overlay(alignment: .top) {
            if let msg = errorMessage {
                Text(msg)
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.destructive)
                    .padding(.horizontal, 20)
                    .padding(.top, 52)
            }
        }
    }

    // MARK: - Sub-views

    private var dragHandle: some View {
        RoundedRectangle(cornerRadius: 2.5)
            .fill(AppTheme.border)
            .frame(width: 36, height: 4)
            .padding(.top, 10)
            .padding(.bottom, 6)
    }

    private var headerSection: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Move to collection")
                .font(.system(size: 20, weight: .bold))
                .foregroundColor(AppTheme.textPrimary)
            if let handle = reel.creatorHandle {
                Text("@\(handle)")
                    .font(.system(size: 12))
                    .foregroundColor(AppTheme.textMuted)
                    .lineLimit(1)
            }
        }
    }

    private var categoryList: some View {
        VStack(spacing: 8) {
            ForEach(appVM.categorySummaries) { cat in
                let isCurrent = reel.categoryId == cat.id
                Button {
                    guard !isCurrent else { return }
                    assign(categoryId: cat.id)
                } label: {
                    HStack {
                        Text(cat.name)
                            .font(.system(size: 14, weight: isCurrent ? .semibold : .medium))
                            .foregroundColor(isCurrent ? AppTheme.accent : AppTheme.textPrimary)
                        Spacer()
                        Text("\(cat.reelCount) reels")
                            .font(.system(size: 11))
                            .foregroundColor(AppTheme.textFaint)
                        if isCurrent {
                            Image(systemName: "checkmark")
                                .font(.system(size: 11, weight: .semibold))
                                .foregroundColor(AppTheme.accent)
                        }
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 12)
                    .background(AppTheme.surface)
                    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .stroke(isCurrent ? AppTheme.accent : AppTheme.border, lineWidth: isCurrent ? 1.5 : 1)
                    )
                }
                .buttonStyle(.plain)
                .disabled(isWorking)
            }
        }
    }

    private var newCategoryRow: some View {
        HStack(spacing: 8) {
            TextField("New collection name…", text: $newCategoryName)
                .font(.system(size: 13))
                .foregroundColor(AppTheme.textPrimary)
                .tint(AppTheme.accent)
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
                .background(AppTheme.surface)
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .stroke(AppTheme.border, lineWidth: 1)
                )

            Button(action: createAndAssign) {
                Group {
                    if isWorking {
                        ProgressView().tint(.white)
                    } else {
                        Text("Add")
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundColor(.white)
                    }
                }
                .frame(width: 52, height: 38)
                .background(newCategoryName.trimmingCharacters(in: .whitespaces).isEmpty ? AppTheme.accent.opacity(0.4) : AppTheme.accent)
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            }
            .disabled(newCategoryName.trimmingCharacters(in: .whitespaces).isEmpty || isWorking)
            .buttonStyle(.plain)
        }
    }

    // MARK: - Actions

    private func assign(categoryId: UUID) {
        isWorking = true
        errorMessage = nil
        Task {
            do {
                try await LibraryService.shared.assignCategory(reelId: reel.id, categoryId: categoryId)
                await appVM.load(silent: true)
                onComplete()
                dismiss()
            } catch {
                errorMessage = "Failed to move reel. Please try again."
            }
            isWorking = false
        }
    }

    private func createAndAssign() {
        let name = newCategoryName.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty else { return }
        isWorking = true
        errorMessage = nil
        Task {
            do {
                let newCategory = try await LibraryService.shared.createCategory(name: name)
                try await LibraryService.shared.assignCategory(reelId: reel.id, categoryId: newCategory.id)
                await appVM.load(silent: true)
                onComplete()
                dismiss()
            } catch {
                errorMessage = "Failed to create collection. Please try again."
            }
            isWorking = false
        }
    }
}
