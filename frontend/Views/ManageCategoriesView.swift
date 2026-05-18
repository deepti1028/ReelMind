import SwiftUI

struct ManageCategoriesView: View {
    @EnvironmentObject private var appVM: AppViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var categories: [Category] = []
    @State private var isLoading = false
    @State private var editingCategory: Category?
    @State private var editName = ""
    @State private var categoryToDelete: Category?
    @State private var errorMessage: String?

    var body: some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()

            if isLoading && categories.isEmpty {
                ProgressView()
                    .tint(AppTheme.accent)
            } else if categories.isEmpty {
                emptyState
            } else {
                categoryList
            }
        }
        .navigationTitle("Collections")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                if isLoading { ProgressView().scaleEffect(0.8).tint(AppTheme.accent) }
            }
        }
        .task { await load() }
        .alert("Rename Collection", isPresented: Binding(
            get: { editingCategory != nil },
            set: { if !$0 { editingCategory = nil } }
        )) {
            TextField("Collection name", text: $editName)
            Button("Cancel", role: .cancel) { editingCategory = nil }
            Button("Save") {
                if let cat = editingCategory {
                    Task { await rename(cat) }
                }
            }
            .disabled(editName.trimmingCharacters(in: .whitespaces).isEmpty)
        }
        .alert("Delete Collection?", isPresented: Binding(
            get: { categoryToDelete != nil },
            set: { if !$0 { categoryToDelete = nil } }
        )) {
            Button("Cancel", role: .cancel) { categoryToDelete = nil }
            Button("Delete", role: .destructive) {
                if let cat = categoryToDelete {
                    Task { await delete(cat) }
                }
            }
        } message: {
            Text("Reels in this collection will be moved to your inbox.")
        }
    }

    // MARK: - Sub-views

    private var categoryList: some View {
        ScrollView {
            VStack(spacing: 0) {
                if let msg = errorMessage {
                    Text(msg)
                        .font(.system(size: 12))
                        .foregroundColor(AppTheme.destructive)
                        .padding(.horizontal, 20)
                        .padding(.top, 12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                LazyVStack(spacing: 0) {
                    ForEach(categories) { cat in
                        CategoryManageRow(
                            category: cat,
                            reelCount: appVM.categorySummaries.first(where: { $0.id == cat.id })?.reelCount ?? 0,
                            onEdit: {
                                editName = cat.name
                                editingCategory = cat
                            },
                            onDelete: { categoryToDelete = cat }
                        )

                        if cat.id != categories.last?.id {
                            Divider()
                                .background(AppTheme.border)
                                .padding(.leading, 54)
                        }
                    }
                }
                .background(AppTheme.surface)
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(AppTheme.border, lineWidth: 1)
                )
                .padding(.horizontal, 14)
                .padding(.top, 16)
            }
            .padding(.bottom, 32)
        }
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "folder")
                .font(.system(size: 40))
                .foregroundColor(AppTheme.accent.opacity(0.6))
            Text("No collections yet")
                .font(.system(size: 17, weight: .semibold))
                .foregroundColor(AppTheme.textPrimary)
            Text("Save and categorise a reel to create your first collection.")
                .font(.system(size: 13))
                .foregroundColor(AppTheme.textMuted)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 40)
        }
    }

    // MARK: - Actions

    private func load() async {
        isLoading = true
        do {
            categories = try await LibraryService.shared.fetchCategories()
        } catch {
            errorMessage = "Failed to load collections."
        }
        isLoading = false
    }

    private func rename(_ cat: Category) async {
        let trimmed = editName.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        editingCategory = nil
        do {
            try await LibraryService.shared.renameCategory(id: cat.id, newName: trimmed)
            await appVM.load(silent: true)
            await load()
        } catch {
            errorMessage = "Failed to rename collection."
        }
    }

    private func delete(_ cat: Category) async {
        categoryToDelete = nil
        do {
            try await LibraryService.shared.deleteCategory(id: cat.id)
            await appVM.load(silent: true)
            await load()
        } catch {
            errorMessage = "Failed to delete collection."
        }
    }
}

// MARK: - Row

private struct CategoryManageRow: View {
    let category: Category
    let reelCount: Int
    let onEdit: () -> Void
    let onDelete: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(AppTheme.surfaceSecondary)
                .frame(width: 34, height: 34)
                .overlay(
                    Image(systemName: "folder")
                        .font(.system(size: 14))
                        .foregroundColor(AppTheme.accentDark)
                )

            VStack(alignment: .leading, spacing: 2) {
                Text(category.name)
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(AppTheme.textPrimary)
                Text("\(reelCount) reel\(reelCount == 1 ? "" : "s")")
                    .font(.system(size: 11))
                    .foregroundColor(AppTheme.textFaint)
            }

            Spacer()

            Button {
                onEdit()
            } label: {
                Image(systemName: "pencil")
                    .font(.system(size: 13))
                    .foregroundColor(AppTheme.textMuted)
                    .frame(width: 32, height: 32)
                    .background(AppTheme.surfaceSecondary)
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            }
            .buttonStyle(.plain)

            Button {
                onDelete()
            } label: {
                Image(systemName: "trash")
                    .font(.system(size: 13))
                    .foregroundColor(AppTheme.destructive)
                    .frame(width: 32, height: 32)
                    .background(AppTheme.destructive.opacity(0.08))
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
    }
}
