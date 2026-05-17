import Foundation
import Supabase
import SwiftUI

struct CategoriseReelView: View {
    let reelId: String
    let suggestions: [String]
    @Environment(\.dismiss) private var dismiss

    @State private var reelThumbnailURL: URL? = nil
    @State private var reelCaption: String? = nil
    @State private var userCategories: [CategoryRow] = []
    @State private var newCategoryName: String = ""
    @State private var isLoading: Bool = true

    struct CategoryRow: Identifiable, Decodable, Hashable {
        let id: String
        let name: String
    }

    var body: some View {
        NavigationView {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    thumbnailHeader

                    if !suggestions.isEmpty {
                        Text("Suggested for you")
                            .font(.headline)
                        chipsRow(suggestions)
                    }

                    Divider()

                    Text("All your categories")
                        .font(.headline)
                    if isLoading {
                        ProgressView()
                    } else {
                        VStack(spacing: 8) {
                            ForEach(userCategories) { cat in
                                Button {
                                    assignAndDismiss(categoryName: cat.name)
                                } label: {
                                    HStack {
                                        Text(cat.name)
                                        Spacer()
                                    }
                                    .padding()
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .background(Color(.secondarySystemBackground))
                                    .cornerRadius(8)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }

                    Divider()

                    VStack(alignment: .leading, spacing: 8) {
                        Text("Create new category")
                            .font(.headline)
                        HStack {
                            TextField("e.g. Travel", text: $newCategoryName)
                                .textFieldStyle(.roundedBorder)
                            Button("Add") {
                                createCategoryAndAssign()
                            }
                            .disabled(newCategoryName.trimmingCharacters(in: .whitespaces).isEmpty)
                        }
                    }
                }
                .padding()
            }
            .navigationTitle("Categorise reel")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Skip") {
                        ReelCategoryAPI.assign(reelId: reelId, categoryName: nil)
                        dismiss()
                    }
                }
            }
            .task {
                await loadReelAndCategories()
            }
        }
    }

    @ViewBuilder
    private var thumbnailHeader: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let url = reelThumbnailURL {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .empty: ProgressView().frame(maxWidth: .infinity)
                    case .success(let image):
                        image.resizable().scaledToFit().cornerRadius(12)
                    case .failure:
                        Rectangle().fill(Color.gray.opacity(0.3)).frame(height: 200).cornerRadius(12)
                    @unknown default:
                        EmptyView()
                    }
                }
            }
            if let caption = reelCaption, !caption.isEmpty {
                Text(caption).font(.footnote).foregroundStyle(.secondary).lineLimit(3)
            }
        }
    }

    @ViewBuilder
    private func chipsRow(_ items: [String]) -> some View {
        HStack(spacing: 8) {
            ForEach(items, id: \.self) { name in
                Button {
                    assignAndDismiss(categoryName: name)
                } label: {
                    Text(name)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(Color.blue.opacity(0.15))
                        .foregroundStyle(.blue)
                        .cornerRadius(20)
                }
                .buttonStyle(.plain)
            }
        }
    }

    private func assignAndDismiss(categoryName: String?) {
        ReelCategoryAPI.assign(reelId: reelId, categoryName: categoryName)
        dismiss()
    }

    private func createCategoryAndAssign() {
        let trimmed = newCategoryName.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        Task {
            do {
                try await SupabaseManager.shared.client
                    .from("categories")
                    .insert(["name": trimmed])
                    .execute()
                await MainActor.run {
                    assignAndDismiss(categoryName: trimmed)
                }
            } catch {
                print("[CategoriseReelView] create category failed: \(error)")
            }
        }
    }

    private struct ReelMeta: Decodable {
        let thumbnail_url: String?
        let caption: String?
    }

    private func loadReelAndCategories() async {
        defer { isLoading = false }
        do {
            let reel: ReelMeta = try await SupabaseManager.shared.client
                .from("reels")
                .select("thumbnail_url, caption")
                .eq("id", value: reelId)
                .single()
                .execute()
                .value

            if let thumb = reel.thumbnail_url, let url = URL(string: thumb) {
                self.reelThumbnailURL = url
            }
            self.reelCaption = reel.caption

            let cats: [CategoryRow] = try await SupabaseManager.shared.client
                .from("categories")
                .select("id, name")
                .order("name", ascending: true)
                .execute()
                .value
            self.userCategories = cats
        } catch {
            print("[CategoriseReelView] load failed: \(error)")
        }
    }
}
