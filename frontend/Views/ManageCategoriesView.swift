import SwiftUI

struct ManageCategoriesView: View {
    @EnvironmentObject private var appVM: AppViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var categories: [Category] = []
    @State private var isLoading = false
    @State private var errorMessage: String?

    // Delete confirmation
    @State private var deleteTarget: Category?

    // Create / rename sheet
    @State private var showFormSheet = false
    @State private var formTarget: Category?   // nil = create, non-nil = rename
    @State private var formName = ""
    @State private var formIcon = "bookmark"
    @State private var showIconPicker = false

    var body: some View {
        ZStack {
            AppTheme.background.ignoresSafeArea()

            if isLoading && categories.isEmpty {
                ProgressView().tint(AppTheme.accent)
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
                        formTarget = nil
                        formName = ""
                        formIcon = "bookmark"
                        showIconPicker = false
                        showFormSheet = true
                    } label: {
                        Image(systemName: "plus")
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundColor(AppTheme.accentDark)
                    }
                }
            }
        }
        .task { await load() }
        .alert("Delete Collection?", isPresented: Binding(
            get: { deleteTarget != nil },
            set: { if !$0 { deleteTarget = nil } }
        )) {
            Button("Cancel", role: .cancel) { deleteTarget = nil }
            Button("Delete", role: .destructive) {
                if let cat = deleteTarget { Task { await delete(cat) } }
            }
        }
        .sheet(isPresented: $showFormSheet) {
            CategoryFormSheet(
                target: formTarget,
                name: $formName,
                icon: $formIcon,
                showIconPicker: $showIconPicker,
                onSave: { Task { await saveForm() } }
            )
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
                                formTarget = cat
                                formName = cat.name
                                formIcon = cat.icon ?? "bookmark"
                                showIconPicker = false
                                showFormSheet = true
                            },
                            onDelete: { deleteTarget = cat }
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
                formTarget = nil
                formName = ""
                formIcon = "bookmark"
                showIconPicker = false
                showFormSheet = true
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

    private func saveForm() async {
        let trimmed = formName.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        showFormSheet = false
        if let cat = formTarget {
            await rename(cat, newName: trimmed, newIcon: formIcon)
        } else {
            await addCategory(name: trimmed, icon: formIcon)
        }
    }

    private func rename(_ cat: Category, newName: String, newIcon: String) async {
        do {
            try await LibraryService.shared.renameCategory(id: cat.id, newName: newName, icon: newIcon)
            await appVM.load(silent: true)
            await load()
        } catch {
            errorMessage = "Failed to rename collection."
        }
    }

    private func delete(_ cat: Category) async {
        deleteTarget = nil
        do {
            try await LibraryService.shared.deleteCategory(id: cat.id)
            await appVM.load(silent: true)
            await load()
        } catch {
            errorMessage = "Failed to delete collection."
        }
    }

    private func addCategory(name: String, icon: String) async {
        do {
            _ = try await LibraryService.shared.createCategory(name: name, icon: icon)
            await appVM.load(silent: true)
            await load()
        } catch {
            errorMessage = "Failed to create collection."
        }
    }
}

// MARK: - Form Sheet

private struct CategoryFormSheet: View {
    let target: Category?
    @Binding var name: String
    @Binding var icon: String
    @Binding var showIconPicker: Bool
    let onSave: () -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 10) {
                    Button {
                        showIconPicker.toggle()
                    } label: {
                        Image(systemName: icon)
                            .font(.system(size: 18))
                            .frame(width: 40, height: 40)
                            .foregroundColor(AppTheme.accentDark)
                            .background(AppTheme.surfaceSecondary)
                            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                    }
                    .buttonStyle(.plain)

                    TextField("Collection name", text: $name)
                        .font(.system(size: 15))
                        .padding(.horizontal, 12)
                        .padding(.vertical, 10)
                        .background(AppTheme.surfaceSecondary)
                        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                }

                if showIconPicker {
                    CategoryIconPicker(selectedIcon: $icon, isShowing: $showIconPicker)
                }

                Spacer()
            }
            .padding(20)
            .background(AppTheme.background.ignoresSafeArea())
            .navigationTitle(target == nil ? "New Collection" : "Rename Collection")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") { dismiss() }
                        .foregroundColor(AppTheme.accentDark)
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(target == nil ? "Create" : "Save") { onSave() }
                        .fontWeight(.semibold)
                        .foregroundColor(AppTheme.accentDark)
                        .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
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
                    Image(systemName: category.icon ?? "bookmark")
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

            Button { onEdit() } label: {
                Image(systemName: "pencil")
                    .font(.system(size: 13))
                    .foregroundColor(AppTheme.textMuted)
                    .frame(width: 32, height: 32)
                    .background(AppTheme.surfaceSecondary)
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            }
            .buttonStyle(.plain)

            Button { onDelete() } label: {
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
