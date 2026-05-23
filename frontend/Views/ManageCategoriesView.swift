import SwiftUI

struct ManageCategoriesView: View {
    @EnvironmentObject private var appVM: AppViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var categories: [Category] = []
    @State private var isLoading = false
    @State private var activeAlert: ActiveAlert?
    @State private var editName = ""
    @State private var newCategoryName = ""
    @State private var errorMessage: String?

    private enum ActiveAlert: Identifiable {
        case rename(Category)
        case confirmDelete(Category)
        case create
        var id: String {
            switch self {
            case .rename(let c):        return "rename-\(c.id)"
            case .confirmDelete(let c): return "delete-\(c.id)"
            case .create:               return "create"
            }
        }
    }

    private var alertTitle: String {
        switch activeAlert {
        case .rename:        return "Rename Collection"
        case .confirmDelete: return "Delete Collection?"
        case .create:        return "New Collection"
        case nil:            return ""
        }
    }

    private var renameTarget: Category? {
        guard case .rename(let cat) = activeAlert else { return nil }
        return cat
    }

    private var deleteTarget: Category? {
        guard case .confirmDelete(let cat) = activeAlert else { return nil }
        return cat
    }

    @ViewBuilder
    private var alertActions: some View {
        if let cat = renameTarget {
            TextField("Collection name", text: $editName)
            Button("Cancel", role: .cancel) { activeAlert = nil }
            Button("Save") { Task { await rename(cat) } }
                .disabled(editName.trimmingCharacters(in: .whitespaces).isEmpty)
        } else if let cat = deleteTarget {
            Button("Cancel", role: .cancel) { activeAlert = nil }
            Button("Delete", role: .destructive) { Task { await delete(cat) } }
        } else {
            TextField("Collection name", text: $newCategoryName)
            Button("Cancel", role: .cancel) { activeAlert = nil }
            Button("Create") { Task { await addCategory() } }
                .disabled(newCategoryName.trimmingCharacters(in: .whitespaces).isEmpty)
        }
    }

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
                if isLoading {
                    ProgressView().scaleEffect(0.8).tint(AppTheme.accent)
                } else {
                    Button {
                        newCategoryName = ""
                        activeAlert = .create
                    } label: {
                        Image(systemName: "plus")
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundColor(AppTheme.accentDark)
                    }
                }
            }
        }
        .task { await load() }
        .alert(alertTitle, isPresented: Binding(
            get: { activeAlert != nil },
            set: { if !$0 { activeAlert = nil } }
        )) {
            alertActions
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
                                activeAlert = .rename(cat)
                            },
                            onDelete: { activeAlert = .confirmDelete(cat) }
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
        VStack(spacing: 16) {
            Image(systemName: "folder.badge.plus")
                .font(.system(size: 44))
                .foregroundColor(AppTheme.accent)

            VStack(spacing: 6) {
                Text("No collections yet")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundColor(AppTheme.textPrimary)
                Text("Tap + to create your first collection.")
                    .font(.system(size: 13))
                    .foregroundColor(AppTheme.textMuted)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 260)
            }

            Button {
                newCategoryName = ""
                activeAlert = .create
            } label: {
                Text("Create collection")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(AppTheme.textPrimary)
                    .padding(.horizontal, 24)
                    .padding(.vertical, 10)
                    .background(AppTheme.accent)
                    .clipShape(Capsule())
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 40)
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
        activeAlert = nil
        do {
            try await LibraryService.shared.renameCategory(id: cat.id, newName: trimmed)
            await appVM.load(silent: true)
            await load()
        } catch {
            errorMessage = "Failed to rename collection."
        }
    }

    private func delete(_ cat: Category) async {
        activeAlert = nil
        do {
            try await LibraryService.shared.deleteCategory(id: cat.id)
            await appVM.load(silent: true)
            await load()
        } catch {
            errorMessage = "Failed to delete collection."
        }
    }

    private func addCategory() async {
        let trimmed = newCategoryName.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        activeAlert = nil
        do {
            _ = try await LibraryService.shared.createCategory(name: trimmed)
            await appVM.load(silent: true)
            await load()
        } catch {
            errorMessage = "Failed to create collection."
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
