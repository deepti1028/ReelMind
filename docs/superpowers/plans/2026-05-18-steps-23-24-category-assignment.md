# Steps 23-24: Category Assignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the two remaining gaps in the category-assignment flow: (1) backend auto-creates a category when the user types a new name, and (2) `CategoriseReelView` stops writing to Supabase directly and lets the backend handle creation.

**Architecture:** Both entry points (FCM notification buttons + full-screen sheet) already call `PATCH /api/v1/reels/{id}/category`. The backend endpoint currently returns 422 for unknown names — we extend it to normalise the name (trim + title-case), do a case-insensitive lookup, and create the category if it doesn't exist. The iOS sheet's `createCategoryAndAssign()` is simplified to a single call to `ReelCategoryAPI.assignAsync()`, which is a new async wrapper around the existing fire-and-forget helper.

**Tech Stack:** Python 3.9, FastAPI, supabase-py, pytest (backend); Swift 5.9, SwiftUI, URLSession async/await (iOS)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/api/v1/reels.py` | Modify | Add name normalisation + case-insensitive lookup + auto-create branch to `update_reel_category` |
| `backend/tests/test_category_endpoint.py` | Modify | Update existing mock chain; delete stale 422 test; add 3 auto-create tests |
| `frontend/ReelCategoryAPI.swift` | Modify | Add `assignAsync` (async/await version that throws on failure) |
| `frontend/CategoriseReelView.swift` | Modify | Replace `createCategoryAndAssign()` body; add `@State var assignError`; wire error alert |

> **Not changed:** `ReelMindApp.swift` notification action handler is already correctly wired (CAT_0/CAT_1 → `ReelCategoryAPI.assign`, CHOOSE_IN_APP → `categoriseReel` post, UNCATEGORISED → `assign(nil)`). Static button labels ("Suggestion 1/2") are acceptable — dynamic labels require a `UNNotificationServiceExtension` which is out of scope per the spec.

---

## Task 1: Backend — Auto-Create Category (TDD)

**Files:**
- Modify: `backend/tests/test_category_endpoint.py`
- Modify: `backend/api/v1/reels.py`

**Context:** `update_reel_category` in `reels.py` currently looks up categories with `.eq("name", payload.category_name)` (exact match). We're changing this to `.ilike("name", normalised_name)` (case-insensitive). This breaks the existing mock helper `_make_supabase_patch_mock` which sets up `.eq.return_value.or_` — we must update it to `.ilike.return_value.or_`. We also delete `test_unknown_category_name_returns_422` because the behaviour changes to auto-create.

---

- [ ] **Step 1: Write the three new failing tests — append to `backend/tests/test_category_endpoint.py`**

```python
# ---------------------------------------------------------------------------
# Auto-create tests (Task 1)
# ---------------------------------------------------------------------------

def _make_supabase_auto_create_mock(category_found=False, new_cat_id="new-cat-uuid"):
    """Table-routing mock that supports the auto-create branch in update_reel_category."""
    reels_mock = MagicMock()
    categories_mock = MagicMock()
    profiles_mock = MagicMock()

    # Reel fetch: .select().eq(id).eq(user_id).maybe_single().execute().data
    reel_row = {
        "id": REEL_ID,
        "user_id": "user-test-id",
        "status": "pending_category",
        "suggested_categories": ["Fitness"],
    }
    (
        reels_mock.select.return_value
        .eq.return_value.eq.return_value
        .maybe_single.return_value.execute.return_value.data
    ) = reel_row
    reels_mock.update.return_value.eq.return_value.execute.return_value = None

    # Profile fetch for FCM token
    (
        profiles_mock.select.return_value
        .eq.return_value.maybe_single.return_value.execute.return_value.data
    ) = {"fcm_token": None}

    # Category lookup: .select().ilike(name).or_(...).execute().data
    cat_data = [{"id": "existing-cat-id", "name": "Travel"}] if category_found else []
    (
        categories_mock.select.return_value
        .ilike.return_value.or_.return_value.execute.return_value.data
    ) = cat_data

    # Category insert (auto-create path)
    categories_mock.insert.return_value.execute.return_value.data = [
        {"id": new_cat_id, "name": "Travel Vlogs"}
    ]

    db = MagicMock()

    def _table(name):
        if name == "reels":
            return reels_mock
        if name == "categories":
            return categories_mock
        if name == "profiles":
            return profiles_mock
        return MagicMock()

    db.table.side_effect = _table
    return db


@patch("api.v1.reels.get_supabase")
@patch("api.v1.reels.send_push_notification", return_value=False)
def test_patch_auto_creates_category_when_not_found(_push, mock_get_supabase):
    """Unknown category name → auto-creates row, marks reel ready, returns created=True."""
    db = _make_supabase_auto_create_mock(category_found=False, new_cat_id="new-cat-uuid")
    mock_get_supabase.return_value = db

    resp = client.patch(
        f"/api/v1/reels/{REEL_ID}/category",
        json={"category_name": "Travel Vlogs"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["created"] is True

    # Verify insert was called on categories table with correct user_id
    cat_insert_call = db.table("categories").insert.call_args.args[0]
    assert cat_insert_call["user_id"] == "user-test-id"
    assert cat_insert_call["is_default"] is False

    # Verify reel was updated to ready
    reels_update_call = db.table("reels").update.call_args.args[0]
    assert reels_update_call["status"] == "ready"
    assert reels_update_call["category_id"] == "new-cat-uuid"


@patch("api.v1.reels.get_supabase")
@patch("api.v1.reels.send_push_notification", return_value=False)
def test_patch_case_insensitive_reuses_existing_category(_push, mock_get_supabase):
    """Lowercase name that matches existing category → reuses it, no insert, created=False."""
    db = _make_supabase_auto_create_mock(category_found=True)
    mock_get_supabase.return_value = db

    resp = client.patch(
        f"/api/v1/reels/{REEL_ID}/category",
        json={"category_name": "travel"},  # lowercase
    )

    assert resp.status_code == 200
    assert resp.json()["created"] is False

    # Verify insert was NOT called
    db.table("categories").insert.assert_not_called()


@patch("api.v1.reels.get_supabase")
@patch("api.v1.reels.send_push_notification", return_value=False)
def test_patch_title_cases_new_category_name(_push, mock_get_supabase):
    """Input 'travel vlogs' → stored as 'Travel Vlogs' (title-cased)."""
    db = _make_supabase_auto_create_mock(category_found=False)
    mock_get_supabase.return_value = db

    client.patch(
        f"/api/v1/reels/{REEL_ID}/category",
        json={"category_name": "travel vlogs"},
    )

    cat_insert_call = db.table("categories").insert.call_args.args[0]
    assert cat_insert_call["name"] == "Travel Vlogs"
```

---

- [ ] **Step 2: Run the three new tests to verify they fail**

```bash
cd /Users/deeptijain/Desktop/Deepti/Projects/ReelMind/backend && source venv/bin/activate && \
pytest tests/test_category_endpoint.py::test_patch_auto_creates_category_when_not_found \
       tests/test_category_endpoint.py::test_patch_case_insensitive_reuses_existing_category \
       tests/test_category_endpoint.py::test_patch_title_cases_new_category_name -v
```

Expected: all 3 fail. `test_patch_auto_creates_category_when_not_found` should fail with status 422 (current behaviour). The other two will fail due to missing `created` field or wrong mock chain.

---

- [ ] **Step 3: Update the existing `_make_supabase_patch_mock` helper — change `.eq` to `.ilike` in the category chain, and delete `test_unknown_category_name_returns_422`**

In `backend/tests/test_category_endpoint.py`, find `_make_supabase_patch_mock` and replace the category lookup block:

```python
# OLD — delete this block:
# Category lookup: .table("categories").select(...).eq(name).or_(...).execute()
if category_id:
    cat_rows = [{"id": category_id, "name": "Fitness"}]
else:
    cat_rows = []
(
    db.table.return_value
    .select.return_value
    .eq.return_value
    .or_.return_value
    .execute.return_value
    .data
) = cat_rows

# NEW — replace with:
# Category lookup: .table("categories").select(...).ilike(name).or_(...).execute()
if category_id:
    cat_rows = [{"id": category_id, "name": "Fitness"}]
else:
    cat_rows = []
(
    db.table.return_value
    .select.return_value
    .ilike.return_value
    .or_.return_value
    .execute.return_value
    .data
) = cat_rows
```

Then delete the entire `test_unknown_category_name_returns_422` test function (behaviour changed: unknown names now auto-create rather than 422).

---

- [ ] **Step 4: Implement the auto-create branch in `backend/api/v1/reels.py`**

Replace the entire Path A block in `update_reel_category` (from `# Path A — user picked a specific category` to the end of the function):

```python
    # Path A — user picked a specific category
    # Normalise name: strip whitespace and title-case so "travel vlogs" → "Travel Vlogs"
    normalised_name = payload.category_name.strip().title()
    if not normalised_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Category name cannot be empty",
        )

    # Case-insensitive lookup: finds "Travel" even if user sent "travel"
    cat_rows = (
        supabase.table("categories")
        .select("id, name")
        .ilike("name", normalised_name)
        .or_(f"user_id.eq.{user_id},user_id.is.null")
        .execute()
    )

    created = False
    if cat_rows.data:
        category_id = cat_rows.data[0]["id"]
    else:
        # Auto-create: category doesn't exist for this user
        new_cat = supabase.table("categories").insert({
            "user_id": user_id,
            "name": normalised_name,
            "is_default": False,
        }).execute()
        category_id = new_cat.data[0]["id"]
        created = True

    supabase.table("reels").update({
        "category_id": category_id,
        "confidence": 1.0,
        "status": "ready",
        "suggested_categories": [],
    }).eq("id", reel_id).execute()

    send_push_notification(
        fcm_token=fcm_token,
        title="Reel categorised!",
        body=f"Added to {normalised_name}",
        data={"reel_id": reel_id, "status": "ready"},
    )
    return {
        "reel_id": reel_id,
        "status": "ready",
        "category": normalised_name,
        "created": created,
    }
```

---

- [ ] **Step 5: Run the full test suite to verify all tests pass with no regressions**

```bash
cd /Users/deeptijain/Desktop/Deepti/Projects/ReelMind/backend && source venv/bin/activate && \
pytest tests/ -v 2>&1 | tail -20
```

Expected: all tests pass. The three new auto-create tests should now be green. The existing `test_assign_category_marks_ready` and `test_null_category_name_marks_uncategorised` should still pass with the updated mock.

---

- [ ] **Step 6: Commit**

```bash
cd /Users/deeptijain/Desktop/Deepti/Projects/ReelMind && \
git add backend/api/v1/reels.py backend/tests/test_category_endpoint.py && \
git commit -m "feat: auto-create category on PATCH /reels/{id}/category when name not found"
```

---

## Task 2: iOS — `ReelCategoryAPI` Async Wrapper

**Files:**
- Modify: `frontend/ReelCategoryAPI.swift`

Add an `assignAsync` method that uses `URLSession.shared.data(for:)` (async/await) and throws on network error or non-2xx response. The existing fire-and-forget `assign()` is kept unchanged — it's still used by the notification action handler in `ReelMindApp.swift`.

---

- [ ] **Step 1: Add `assignAsync` to `frontend/ReelCategoryAPI.swift`**

Open `frontend/ReelCategoryAPI.swift` and add after the closing brace of `assign()`:

```swift
    /// Async version of `assign` — throws on network failure or non-2xx HTTP status.
    /// Used by CategoriseReelView where the sheet can show an error to the user.
    static func assignAsync(reelId: String, categoryName: String?) async throws {
        guard
            let defaults = UserDefaults(suiteName: AppConfig.appGroupID),
            let authToken = defaults.string(forKey: AppConfig.authTokenKey)
        else {
            throw URLError(.userAuthenticationRequired)
        }

        let url = AppConfig.backendBaseURL
            .appendingPathComponent("api/v1/reels")
            .appendingPathComponent(reelId)
            .appendingPathComponent("category")

        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("Bearer \(authToken)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body: [String: Any?] = ["category_name": categoryName]
        request.httpBody = try? JSONSerialization.data(
            withJSONObject: body,
            options: [.fragmentsAllowed]
        )

        let (_, response) = try await URLSession.shared.data(for: request)
        guard
            let http = response as? HTTPURLResponse,
            (200...299).contains(http.statusCode)
        else {
            throw URLError(.badServerResponse)
        }
    }
```

The full file should look like:

```swift
import Foundation

enum ReelCategoryAPI {
    /// Fire-and-forget assign — used by the notification action handler (background, no UI).
    static func assign(reelId: String, categoryName: String?) {
        guard
            let defaults = UserDefaults(suiteName: AppConfig.appGroupID),
            let authToken = defaults.string(forKey: AppConfig.authTokenKey)
        else {
            print("[ReelCategoryAPI] skipping assign — no auth token")
            return
        }

        let url = AppConfig.backendBaseURL
            .appendingPathComponent("api/v1/reels")
            .appendingPathComponent(reelId)
            .appendingPathComponent("category")

        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("Bearer \(authToken)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body: [String: Any?] = ["category_name": categoryName]
        request.httpBody = try? JSONSerialization.data(
            withJSONObject: body,
            options: [.fragmentsAllowed]
        )

        URLSession.shared.dataTask(with: request) { _, response, error in
            if let error = error {
                print("[ReelCategoryAPI] assign failed: \(error)")
                return
            }
            if let http = response as? HTTPURLResponse {
                print("[ReelCategoryAPI] assign HTTP \(http.statusCode)")
            }
        }.resume()
    }

    /// Async version of `assign` — throws on network failure or non-2xx HTTP status.
    /// Used by CategoriseReelView where the sheet can show an error to the user.
    static func assignAsync(reelId: String, categoryName: String?) async throws {
        guard
            let defaults = UserDefaults(suiteName: AppConfig.appGroupID),
            let authToken = defaults.string(forKey: AppConfig.authTokenKey)
        else {
            throw URLError(.userAuthenticationRequired)
        }

        let url = AppConfig.backendBaseURL
            .appendingPathComponent("api/v1/reels")
            .appendingPathComponent(reelId)
            .appendingPathComponent("category")

        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("Bearer \(authToken)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body: [String: Any?] = ["category_name": categoryName]
        request.httpBody = try? JSONSerialization.data(
            withJSONObject: body,
            options: [.fragmentsAllowed]
        )

        let (_, response) = try await URLSession.shared.data(for: request)
        guard
            let http = response as? HTTPURLResponse,
            (200...299).contains(http.statusCode)
        else {
            throw URLError(.badServerResponse)
        }
    }
}
```

---

- [ ] **Step 2: Commit**

```bash
cd /Users/deeptijain/Desktop/Deepti/Projects/ReelMind && \
git add frontend/ReelCategoryAPI.swift && \
git commit -m "feat: add ReelCategoryAPI.assignAsync for sheet error handling"
```

---

## Task 3: iOS — Fix `CategoriseReelView`

**Files:**
- Modify: `frontend/CategoriseReelView.swift`

Three changes:
1. Add `@State private var assignError: Bool = false`
2. Replace `createCategoryAndAssign()` body — remove Supabase write, just call `assignAndDismiss`
3. Replace `assignAndDismiss` with an async Task that uses `assignAsync` and sets `assignError` on failure
4. Add `.alert` for the error state

---

- [ ] **Step 1: Update `CategoriseReelView.swift` — add error state, fix both methods, add alert**

At the top of the `CategoriseReelView` struct, with the existing `@State` properties, add:

```swift
@State private var assignError: Bool = false
```

Replace the `assignAndDismiss` method:

```swift
// OLD:
private func assignAndDismiss(categoryName: String?) {
    ReelCategoryAPI.assign(reelId: reelId, categoryName: categoryName)
    dismiss()
}

// NEW:
private func assignAndDismiss(categoryName: String?) {
    Task {
        do {
            try await ReelCategoryAPI.assignAsync(reelId: reelId, categoryName: categoryName)
            await MainActor.run { dismiss() }
        } catch {
            await MainActor.run { assignError = true }
        }
    }
}
```

Replace the `createCategoryAndAssign` method (remove the entire Supabase Task block):

```swift
// OLD:
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

// NEW:
private func createCategoryAndAssign() {
    let trimmed = newCategoryName.trimmingCharacters(in: .whitespaces)
    guard !trimmed.isEmpty else { return }
    assignAndDismiss(categoryName: trimmed)
}
```

Add the error alert to the `body`'s `NavigationView` by chaining after `.task { await loadReelAndCategories() }`:

```swift
.alert("Couldn't save", isPresented: $assignError) {
    Button("OK") { assignError = false }
} message: {
    Text("Please check your connection and try again.")
}
```

The updated `body` should end like:

```swift
.navigationTitle("Categorise reel")
.navigationBarTitleDisplayMode(.inline)
.toolbar {
    ToolbarItem(placement: .navigationBarTrailing) {
        Button("Skip") {
            assignAndDismiss(categoryName: nil)
        }
    }
}
.task {
    await loadReelAndCategories()
}
.alert("Couldn't save", isPresented: $assignError) {
    Button("OK") { assignError = false }
} message: {
    Text("Please check your connection and try again.")
}
```

---

- [ ] **Step 2: Build in Xcode — verify no compiler errors**

Open `ReelMind.xcworkspace` in Xcode and press `⌘B`. Expected: build succeeds with 0 errors.

---

- [ ] **Step 3: Manual smoke test checklist**

With the backend running locally (`uvicorn main:app --reload --port 8000`, Redis up, Celery running), and a reel in `pending_category` state:

- [ ] Open `CategoriseReelView` for a `pending_category` reel → type a **new** category name (one that doesn't exist) → tap Add → reel moves to ready, new category appears in the list on next open
- [ ] Type an **existing** category name in different case (e.g. "fitness" when "Fitness" exists) → tap Add → reel moves to ready, no duplicate category created
- [ ] Tap an existing category from the list → reel moves to ready
- [ ] Tap Skip → reel moves to uncategorised
- [ ] Kill network (turn off WiFi/data), tap a category → alert "Couldn't save" appears → tap OK → sheet remains open

---

- [ ] **Step 4: Commit**

```bash
cd /Users/deeptijain/Desktop/Deepti/Projects/ReelMind && \
git add frontend/CategoriseReelView.swift && \
git commit -m "fix: remove direct Supabase write in CategoriseReelView, add error handling"
```
