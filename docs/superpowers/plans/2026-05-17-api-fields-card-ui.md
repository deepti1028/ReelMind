# API Field Completeness & Reel Card UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose all `reels` DB columns through the backend schema and iOS model, fix the `create_reel` endpoint to use upsert semantics, join categories in the fetch query, and update `ReelCard` to display all available data with graceful fallback for unprocessed reels.

**Architecture:** iOS reads reels directly from Supabase (RLS-scoped, anon key) — no new FastAPI endpoints. FastAPI is only called by the share extension for `POST /api/v1/reels`. The iOS `ReelCard` renders a compact fallback when metadata is absent and a full card once the pipeline populates fields.

**Tech Stack:** Python 3.11 / FastAPI / Pydantic v2 / `supabase-py` (backend); Swift / SwiftUI / Supabase Swift SDK (iOS); PostgreSQL / PostgREST (database).

**Spec:** `docs/superpowers/specs/2026-05-16-api-fields-and-card-ui-design.md`

---

## Task 1: Complete `ReelResponse` Pydantic schema

**Files:**
- Modify: `backend/schemas/reel.py`

- [ ] **Step 1: Open `backend/schemas/reel.py` and replace the `ReelResponse` class**

  Current `ReelResponse` is missing `transcript`, `caption`, `hashtags`, `has_audio`, `retry_count`, `updated_at`. Replace the entire file with:

  ```python
  """Pydantic schemas for Reel-related requests and responses."""

  from datetime import datetime
  from typing import Optional
  from uuid import UUID

  from pydantic import BaseModel, Field, HttpUrl


  class ReelCreate(BaseModel):
      url: HttpUrl = Field(..., description="The Instagram reel URL")


  class ReelResponse(BaseModel):
      id: UUID
      url: str
      status: str
      category_id: Optional[UUID] = None
      creator_handle: Optional[str] = None
      thumbnail_url: Optional[str] = None
      transcript: Optional[str] = None
      caption: Optional[str] = None
      hashtags: list[str] = []
      summary: Optional[str] = None
      confidence: Optional[float] = None
      has_audio: Optional[bool] = None
      retry_count: Optional[int] = None
      created_at: datetime
      updated_at: datetime
  ```

- [ ] **Step 2: Verify schema parses correctly**

  From `backend/` with the virtualenv active:
  ```bash
  python -c "
  from schemas.reel import ReelResponse
  import uuid, datetime
  r = ReelResponse(
      id=uuid.uuid4(), url='https://example.com', status='queued',
      created_at=datetime.datetime.now(), updated_at=datetime.datetime.now()
  )
  print('OK:', r.model_dump())
  "
  ```
  Expected: prints a dict with all fields. Optional fields default to `None` / `[]`.

- [ ] **Step 3: Commit**

  ```bash
  git add backend/schemas/reel.py
  git commit -m "feat: add missing fields to ReelResponse schema"
  ```

---

## Task 2: Rewrite `create_reel` endpoint

**Files:**
- Modify: `backend/api/v1/reels.py`

Fixes five issues: exception-as-control-flow → upsert; full row on all paths; `url` from DB row; typed `response_model`; correct HTTP status (202 fresh / 200 duplicate).

- [ ] **Step 1: Replace the entire contents of `backend/api/v1/reels.py`**

  ```python
  """Reels endpoints — capture and processing pipeline entry."""

  from fastapi import APIRouter, Depends, Response, status

  from api.deps import get_current_user_id
  from schemas.reel import ReelCreate, ReelResponse
  from supabase_client import get_supabase
  from workers.tasks import process_reel

  router = APIRouter()


  @router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=ReelResponse)
  async def create_reel(
      payload: ReelCreate,
      user_id: str = Depends(get_current_user_id),
      response: Response,
  ):
      """Capture a reel URL and queue it for processing.

      Returns 202 when a Celery task is dispatched (fresh insert).
      Returns 200 when the URL already exists for this user (duplicate — no task queued).
      """
      supabase = get_supabase()
      url_str = str(payload.url)

      # Ensure a profile row exists for this user. Idempotent — service role
      # bypasses RLS. We do this here (rather than via a trigger on auth.users)
      # because Supabase triggers + RLS on public tables fight each other and
      # break signup. This upsert is cheap and runs at most once per new user.
      supabase.table("profiles").upsert(
          {"id": user_id},
          on_conflict="id",
          ignore_duplicates=True,
      ).execute()

      # Upsert the reel row. ON CONFLICT (user_id, url) DO NOTHING returns an
      # empty result set — result.data == [] signals a duplicate without using
      # exceptions for control flow.
      result = (
          supabase.table("reels")
          .upsert(
              {"user_id": user_id, "url": url_str, "status": "queued"},
              on_conflict="user_id,url",
              ignore_duplicates=True,
          )
          .execute()
      )

      if result.data:
          # Fresh insert — dispatch Celery task, return 202 (default).
          reel = result.data[0]
          process_reel.delay(reel["id"])
      else:
          # Duplicate URL — fetch the existing row in full, return 200.
          existing = (
              supabase.table("reels")
              .select("*")
              .eq("user_id", user_id)
              .eq("url", url_str)
              .single()
              .execute()
          )
          reel = existing.data
          response.status_code = status.HTTP_200_OK

      return reel
  ```

- [ ] **Step 2: Start the backend and verify the endpoint is reachable**

  In one terminal (from `backend/`, venv active):
  ```bash
  docker compose up -d
  celery -A workers.celery_app worker --loglevel=info &
  uvicorn main:app --reload --host 0.0.0.0 --port 8000
  ```

  In another terminal:
  ```bash
  curl -s http://localhost:8000/api/v1/health
  ```
  Expected: `{"status": "ok"}` (or similar — confirms server started).

- [ ] **Step 3: Verify OpenAPI schema reflects the new response model**

  ```bash
  curl -s http://localhost:8000/openapi.json | python -m json.tool | grep -A 30 '"ReelResponse"'
  ```
  Expected: JSON schema block listing all fields including `has_audio`, `transcript`, `hashtags`, `updated_at`.

- [ ] **Step 4: Commit**

  ```bash
  git add backend/api/v1/reels.py
  git commit -m "feat: rewrite create_reel with upsert, typed response, correct HTTP status"
  ```

---

## Task 3: Add `has_audio` and `CategoryInfo` to iOS Reel model

**Files:**
- Modify: `frontend/TempReels/Reel.swift`

- [ ] **Step 1: Replace the entire contents of `frontend/TempReels/Reel.swift`**

  ```swift
  import Foundation

  struct CategoryInfo: Decodable, Hashable {
      let name: String
  }

  struct Reel: Identifiable, Decodable, Hashable {
      let id: UUID
      let userId: UUID
      let categoryId: UUID?
      let url: String
      let creatorHandle: String?
      let thumbnailUrl: String?
      let transcript: String?
      let caption: String?
      let hashtags: [String]
      let summary: String?
      let confidence: Float?
      let hasAudio: Bool?
      let status: String
      let retryCount: Int?
      let deletedAt: Date?
      let createdAt: Date
      let updatedAt: Date
      let categories: CategoryInfo?

      enum CodingKeys: String, CodingKey {
          case id
          case userId = "user_id"
          case categoryId = "category_id"
          case url
          case creatorHandle = "creator_handle"
          case thumbnailUrl = "thumbnail_url"
          case transcript
          case caption
          case hashtags
          case summary
          case confidence
          case hasAudio = "has_audio"
          case status
          case retryCount = "retry_count"
          case deletedAt = "deleted_at"
          case createdAt = "created_at"
          case updatedAt = "updated_at"
          case categories
      }
  }
  ```

- [ ] **Step 2: Build in Xcode to verify no compiler errors**

  Press `⌘B`. Expected: Build succeeds with 0 errors.

- [ ] **Step 3: Commit**

  ```bash
  git add frontend/TempReels/Reel.swift
  git commit -m "feat: add hasAudio, CategoryInfo, categories to Reel model"
  ```

---

## Task 4: Update `ReelsService` to join categories

**Files:**
- Modify: `frontend/TempReels/ReelsService.swift`

- [ ] **Step 1: Replace the `.select()` call with a category join**

  In `frontend/TempReels/ReelsService.swift`, change the `fetchReels()` method. Replace:

  ```swift
  .select()
  ```

  With:

  ```swift
  .select("*, categories(name)")
  ```

  The full updated method:

  ```swift
  func fetchReels() async throws -> [Reel] {
      let userId = try await client.auth.session.user.id
      return try await client
          .from("reels")
          .select("*, categories(name)")
          .eq("user_id", value: userId)
          .is("deleted_at", value: nil)
          .order("created_at", ascending: false)
          .execute()
          .value
  }
  ```

  PostgREST resolves the FK join on `category_id → categories.id` automatically. When `category_id` is null, Supabase returns `"categories": null` which Swift decodes to `nil`.

- [ ] **Step 2: Build in Xcode**

  Press `⌘B`. Expected: Build succeeds with 0 errors.

- [ ] **Step 3: Commit**

  ```bash
  git add frontend/TempReels/ReelsService.swift
  git commit -m "feat: join categories(name) in fetchReels query"
  ```

---

## Task 5: Update `ReelCard` UI

**Files:**
- Modify: `frontend/TempReels/ReelsListView.swift`

Four changes: minimal fallback when metadata absent; category chip below hashtags; `has_audio` badge replaces raw char-count in footer; `updated_at` shown when status is processing/failed.

- [ ] **Step 1: Replace the entire `ReelCard` private struct and its sub-views**

  In `frontend/TempReels/ReelsListView.swift`, find the `// MARK: - Card` section and replace everything from `private struct ReelCard` through the end of `private struct HashtagChips` with:

  ```swift
  // MARK: - Card

  private struct ReelCard: View {
      let reel: Reel

      private static let dateFormatter: DateFormatter = {
          let f = DateFormatter()
          f.dateFormat = "MMM d, HH:mm"
          return f
      }()

      private var hasMetadata: Bool {
          reel.thumbnailUrl != nil ||
          reel.creatorHandle != nil ||
          !(reel.caption?.isEmpty ?? true) ||
          !reel.hashtags.isEmpty
      }

      var body: some View {
          Group {
              if hasMetadata {
                  fullCard
              } else {
                  compactCard
              }
          }
          .padding(12)
          .background(
              RoundedRectangle(cornerRadius: 16, style: .continuous)
                  .fill(Color.white)
          )
          .overlay(
              RoundedRectangle(cornerRadius: 16, style: .continuous)
                  .stroke(Color.black.opacity(0.06), lineWidth: 1)
          )
      }

      // Full card — shown once pipeline has populated metadata fields.
      private var fullCard: some View {
          HStack(alignment: .top, spacing: 12) {
              ThumbnailView(url: reel.thumbnailUrl)

              VStack(alignment: .leading, spacing: 6) {
                  headerRow
                  if let caption = reel.caption, !caption.isEmpty {
                      Text(caption)
                          .font(.system(size: 13))
                          .foregroundColor(.black.opacity(0.78))
                          .lineLimit(2)
                          .multilineTextAlignment(.leading)
                  }
                  if !reel.hashtags.isEmpty {
                      HashtagChips(tags: reel.hashtags)
                  }
                  if let categoryName = reel.categories?.name {
                      CategoryChip(name: categoryName)
                  }
                  footerRow
              }
              .frame(maxWidth: .infinity, alignment: .leading)
          }
      }

      // Compact card — shown while reel is queued and metadata is absent.
      private var compactCard: some View {
          HStack(spacing: 8) {
              StatusPill(status: reel.status)
              Text(URL(string: reel.url)?.host ?? reel.url)
                  .font(.system(size: 13))
                  .foregroundColor(ReelsTheme.mutedText)
                  .lineLimit(1)
              Spacer()
              Text(ReelCard.dateFormatter.string(from: reel.createdAt))
                  .font(.system(size: 11))
                  .foregroundColor(ReelsTheme.mutedText)
          }
      }

      private var headerRow: some View {
          HStack(spacing: 6) {
              Text(reel.creatorHandle.map { "@\($0)" } ?? "@unknown")
                  .font(.system(size: 14, weight: .semibold))
                  .foregroundColor(ReelsTheme.brandGreen)
                  .lineLimit(1)
              Spacer(minLength: 4)
              StatusPill(status: reel.status)
          }
      }

      private var footerRow: some View {
          HStack(spacing: 8) {
              Text(ReelCard.dateFormatter.string(from: reel.createdAt))
                  .font(.system(size: 11))
                  .foregroundColor(ReelsTheme.mutedText)

              if let hasAudio = reel.hasAudio {
                  Text("·")
                      .font(.system(size: 11))
                      .foregroundColor(ReelsTheme.mutedText)
                  Image(systemName: hasAudio ? "waveform" : "doc.text")
                      .font(.system(size: 10))
                      .foregroundColor(ReelsTheme.mutedText)
                  Text(hasAudio ? "transcript" : "caption-only")
                      .font(.system(size: 11))
                      .foregroundColor(ReelsTheme.mutedText)
              }

              if reel.status == "processing" || reel.status == "failed" {
                  Text("·")
                      .font(.system(size: 11))
                      .foregroundColor(ReelsTheme.mutedText)
                  Text("updated \(ReelCard.dateFormatter.string(from: reel.updatedAt))")
                      .font(.system(size: 11))
                      .foregroundColor(ReelsTheme.mutedText)
              }
          }
          .padding(.top, 2)
      }
  }

  // MARK: - Thumbnail

  private struct ThumbnailView: View {
      let url: String?

      var body: some View {
          Group {
              if let urlString = url, let url = URL(string: urlString) {
                  AsyncImage(url: url) { phase in
                      switch phase {
                      case .empty:
                          placeholder.overlay(ProgressView().scaleEffect(0.7))
                      case .success(let image):
                          image
                              .resizable()
                              .aspectRatio(contentMode: .fill)
                      case .failure:
                          placeholder.overlay(
                              Image(systemName: "photo")
                                  .foregroundColor(ReelsTheme.mutedText)
                          )
                      @unknown default:
                          placeholder
                      }
                  }
              } else {
                  placeholder.overlay(
                      Image(systemName: "photo")
                          .foregroundColor(ReelsTheme.mutedText)
                  )
              }
          }
          .frame(width: 72, height: 110)
          .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
      }

      private var placeholder: some View {
          RoundedRectangle(cornerRadius: 10, style: .continuous)
              .fill(ReelsTheme.cardBackground)
      }
  }

  // MARK: - Status pill

  private struct StatusPill: View {
      let status: String

      var body: some View {
          Text(status)
              .font(.system(size: 10, weight: .semibold))
              .foregroundColor(foreground)
              .padding(.horizontal, 8)
              .padding(.vertical, 3)
              .background(background)
              .clipShape(Capsule())
              .lineLimit(1)
      }

      private var background: Color {
          switch status {
          case "queued":         return Color.gray.opacity(0.15)
          case "processing":     return Color.orange.opacity(0.18)
          case "ready":          return ReelsTheme.lightGreenTint
          case "uncategorised":  return Color.blue.opacity(0.15)
          case "failed":         return Color.red.opacity(0.15)
          default:               return Color.gray.opacity(0.15)
          }
      }

      private var foreground: Color {
          switch status {
          case "queued":         return Color.gray
          case "processing":     return Color.orange
          case "ready":          return ReelsTheme.brandGreen
          case "uncategorised":  return Color.blue
          case "failed":         return Color.red
          default:               return Color.gray
          }
      }
  }

  // MARK: - Category chip

  private struct CategoryChip: View {
      let name: String

      var body: some View {
          Text(name)
              .font(.system(size: 10, weight: .medium))
              .foregroundColor(.gray)
              .padding(.horizontal, 7)
              .padding(.vertical, 3)
              .background(Color.gray.opacity(0.12))
              .clipShape(Capsule())
              .lineLimit(1)
      }
  }

  // MARK: - Hashtag chips

  private struct HashtagChips: View {
      let tags: [String]
      private let maxVisible = 3

      var body: some View {
          HStack(spacing: 6) {
              ForEach(Array(tags.prefix(maxVisible)), id: \.self) { tag in
                  Text("#\(tag)")
                      .font(.system(size: 10, weight: .medium))
                      .foregroundColor(ReelsTheme.brandGreen)
                      .padding(.horizontal, 7)
                      .padding(.vertical, 3)
                      .background(ReelsTheme.lightGreenTint.opacity(0.55))
                      .clipShape(Capsule())
                      .lineLimit(1)
              }
              if tags.count > maxVisible {
                  Text("+\(tags.count - maxVisible)")
                      .font(.system(size: 10, weight: .medium))
                      .foregroundColor(ReelsTheme.mutedText)
              }
          }
      }
  }
  ```

- [ ] **Step 2: Build in Xcode**

  Press `⌘B`. Expected: Build succeeds with 0 errors. If `ReelsTheme.cardBackground` or any other color token is missing, check `ReelsTheme` definition in the project and use an equivalent (e.g. `Color(.systemGray6)`).

- [ ] **Step 3: Run the app in the simulator and verify card rendering**

  - Reels that are newly queued (no metadata) → compact card: status pill + instagram.com + timestamp
  - Reels that have been processed (have thumbnail/caption/hashtags) → full card with thumbnail, creator, chips, footer
  - Reels with `has_audio = true` → footer shows "waveform transcript"
  - Reels with `has_audio = false` → footer shows "doc.text caption-only"
  - Reels in `processing` or `failed` status → footer shows "updated MMM d, HH:mm"
  - Reels with a category assigned → grey category chip below hashtags

- [ ] **Step 4: Commit**

  ```bash
  git add frontend/TempReels/ReelsListView.swift
  git commit -m "feat: update ReelCard with fallback, category chip, has_audio badge, updated_at"
  ```

---

## Self-Review

**Spec coverage:**
- ✅ `ReelResponse` missing fields → Task 1
- ✅ `create_reel` duplicate path selects only `id, status` → Task 2
- ✅ Exception-as-control-flow → Task 2 (upsert)
- ✅ `url` from DB not request → Task 2
- ✅ `response_model=ReelResponse` → Task 2
- ✅ HTTP 200 for duplicates → Task 2
- ✅ `has_audio: Bool?` in Reel model → Task 3
- ✅ `CategoryInfo` + `categories` in Reel model → Task 3
- ✅ `select("*, categories(name)")` in fetchReels → Task 4
- ✅ Minimal fallback card → Task 5
- ✅ Category chip → Task 5
- ✅ `has_audio` badge replaces char-count → Task 5
- ✅ `updated_at` when processing/failed → Task 5

**Placeholder scan:** No TBDs, TODOs, or vague steps. All steps include complete code.

**Type consistency:**
- `CategoryInfo` defined in Task 3, referenced in Task 5 (`reel.categories?.name`) ✅
- `hasAudio` defined in Task 3, referenced in Task 5 (`reel.hasAudio`) ✅
- `updatedAt` defined in Task 3 (as `updatedAt`, CodingKey `updated_at`), referenced in Task 5 (`reel.updatedAt`) ✅
- `ReelResponse` defined in Task 1, imported in Task 2 ✅
