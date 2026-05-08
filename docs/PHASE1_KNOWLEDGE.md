# ReelMind — Phase 1 Knowledge Document
### How We Built the Foundation (Xcode + Supabase)

*Written for anyone who picks this up and wants to understand the why behind every decision.*

---

## The Big Picture

ReelMind is an iOS app that lets you save Instagram Reels, auto-categorise them with AI, and chat with your saved library. Before any of that magic works, we need:

1. An iOS app that can capture reel URLs (Xcode)
2. A database that stores everything securely (Supabase)
3. A backend that processes reels (FastAPI — coming in Phase 2)

Phase 1 is entirely **infrastructure plumbing**. No AI, no UI, no processing. Just making sure the pipes are in place and correctly connected before we turn on the water.

---

## How The Repo is Structured

```
ReelMind/                         ← Root of the whole project
├── frontend/                     ← iOS Xcode project (Swift + SwiftUI)
│   └── (Xcode project files)
├── backend/                      ← FastAPI Python backend
│   ├── config.py
│   ├── supabase_client.py
│   ├── .env.example
│   └── .gitignore
├── supabase/                     ← All database migrations
│   ├── migrations/
│   │   └── (10 SQL files)
│   └── README.md
|__ docs/
|   ├── ReelMind_Build_Plan/              ← Build plan + DB schema PDFs
│   ├── backlog.md                    ← Features deferred to future phases
│   ├── SETUP_CHECKLIST.md            ← What's done vs what's pending
│   └── PHASE1_KNOWLEDGE.md           ← This file
├── PRD/                          ← Product Requirements Document

```

**Why one repo for frontend + backend?**
We deliberately chose a monorepo (single git repository for both iOS and backend). This keeps everything in one place — you can grep across the whole codebase, keep migrations and code in sync, and avoid the coordination overhead of two separate repos. For a solo or small team build, this is the right call.

---

## Part 1: Xcode (Steps 1–3)

### What the User Did (Steps 1 & 2)
- **Created the Xcode project**: A new iOS app using SwiftUI lifecycle, targeting iOS 16+. This is the main app users download and open.
- **Created the Share Extension target**: A separate mini-app that lives inside the main app. When a user taps "Share" on a reel in Instagram and selects ReelMind, this extension catches the URL. It's the core capture mechanism.

### What Still Needs to Be Done (Step 3): App Groups

**The Problem:** The Share Extension and the main app are technically two separate processes. By default, they cannot talk to each other. When Instagram sends a reel URL to the Share Extension, the main app has no idea it happened.

**The Solution: App Groups**
App Groups is an Apple entitlement that creates a shared container — a shared folder both the main app and the Share Extension can read and write to. The Share Extension writes the captured URL into this shared folder, and the main app reads from it.

**How to set it up in Xcode:**
1. Select the **main app target** → Signing & Capabilities → `+` Capability → **App Groups**
2. Click `+` and create a group named: `group.com.reelmind.app` (or your bundle ID equivalent)
3. Select the **Share Extension target** → same steps, same group name
4. Both must use the **identical** group ID — this is what links them

Once set up, Swift code on both sides uses `UserDefaults(suiteName: "group.com.reelmind.app")` to share data.

---

## Part 2: Supabase Setup (Step 4)

### What is Supabase?
Supabase is a hosted PostgreSQL database with auth, storage, and real-time subscriptions built in. Think of it as Firebase but using real SQL. It's the source of truth for all user data.

### What We Created

**`backend/.env.example`** — Template file listing all required environment variables
```
SUPABASE_URL        → Your Supabase project URL
SUPABASE_ANON_KEY   → Public key (safe to use in iOS app)
SUPABASE_SERVICE_ROLE_KEY → Secret key (backend only, never in iOS)
GROQ_API_KEY        → For Whisper transcription + Llama classification (free tier)
REDIS_URL           → For background job queue
FCM_SERVER_KEY      → For push notifications
TAVILY_API_KEY      → For web search fallback
```

> **Note (2026-05-07):** We initially planned to use OpenAI (Whisper + embeddings) and Anthropic (Claude). We switched to Groq + `sentence-transformers` to stay on free tiers during MVP. See [DECISIONS.md](DECISIONS.md) for the rationale.

**Why two different keys?**
- **Anon key**: Safe for the iOS frontend. Limited by Row-Level Security (RLS). Even if someone extracts this from the app binary, they can only see their own data — the database enforces this.
- **Service role key**: Used only by the backend server. It bypasses RLS policies entirely. This lets the backend process any user's reel (transcription, embedding, etc.) without authentication friction. **Never put this in the iOS app.**

**`backend/config.py`** — Python class that reads `.env` values into typed attributes. Every other backend file imports from here instead of calling `os.getenv()` directly. Centralized config = one place to change, nothing breaks.

**`backend/supabase_client.py`** — Creates the Supabase Python client singleton using the service role key. Any backend file that needs to talk to the database imports `get_supabase()` from here.

**`backend/.gitignore`** — Ensures `.env` is never committed to git. The `.env.example` file is committed (it has no real values), but the actual `.env` file with real secrets is always local only.

---

## Part 3: Database Design (Step 5)

### Why Supabase Native Migrations?

We considered two approaches:

| Approach | How it works | Why we rejected it |
|---|---|---|
| **Alembic (Python/FastAPI)** | ORM generates SQL, applies it via Python | More moving parts, Supabase features don't auto-work |
| **Supabase Native Migrations (SQL files)** | Raw SQL files applied by Supabase CLI | ✅ Fewer bugs, simpler, full Supabase compatibility |

We chose Supabase native because:
- SQL migrations are the ground truth — no ORM translation layer between what you write and what executes
- Supabase features (RLS, triggers, pgvector indexes) all work exactly as documented
- Any AI that generates SQL for Supabase produces code that works directly without translation
- Long-term, fewer "why is the ORM generating wrong SQL" debugging sessions

**Rule:** Every database change must go through a migration file. Never directly run SQL in the Supabase dashboard and call it done.

### The 7 Tables (What They Are & Why)

All migrations live in `supabase/migrations/` as timestamped SQL files, executed in order.

---

#### Table 1: `profiles`
*File: `20260502000002_create_profiles_table.sql`*

**What it is:** One row per user. An extension of Supabase's built-in `auth.users` table.

**Why it exists:** Supabase handles authentication in its own `auth.users` table (you don't control it). But you need somewhere to store extra user data — profile info, preferences, etc. `profiles` is that place, linked to `auth.users` by the same UUID.

**The magic:** A database trigger runs automatically on every new signup:
```sql
-- When a new user is added to auth.users, create their profile automatically
create trigger on_auth_user_created
after insert on auth.users
for each row execute function public.handle_new_user();
```
No backend code needed — the database handles it.

---

#### Table 2: `categories`
*File: `20260502000003_create_categories_table.sql`*

**What it is:** Stores the 6 default categories (Skincare, Haircare, Bodycare, Fitness, Nutrition, Fashion) and any custom categories users create.

**The clever design:**
- Default categories have `user_id = NULL` and `is_default = TRUE`
- User-created categories have `user_id = <their UUID>` and `is_default = FALSE`
- Query to get categories for any user: `WHERE user_id = $uid OR is_default = TRUE`
- If a user deletes their account, the default categories survive (`ON DELETE SET NULL`)

---

#### Table 3: `reels`
*File: `20260502000004_create_reels_table.sql`*

**What it is:** The main table. Every saved reel is one row here.

**Key design decisions:**
- `status` field tracks the processing pipeline: `queued → processing → ready` (or `failed`, `uncategorised`)
- `deleted_at` is a soft delete — we set a timestamp instead of deleting the row. This means deleted reels still appear in chat history source references (marked as deleted)
- `(user_id, url)` has a UNIQUE constraint — you can't save the same reel twice
- `confidence` stores the AI's confidence in its category assignment (0.0–1.0)

---

#### Table 4: `reel_chunks`
*File: `20260502000005_create_reel_chunks_table.sql`*

**What it is:** Each reel's transcript is split into ~200-token chunks. Each chunk gets its own row here with its embedding vector.

**Why chunks instead of one big vector?**
When you ask a question, we search for relevant chunks (not whole reels). A reel about skincare might have 10 chunks — the AI finds the 2-3 most relevant ones and uses those as context for its answer. This is the RAG (Retrieval-Augmented Generation) approach.

**The vector column:**
```sql
embedding vector(1536)
```
This stores the 1536-dimensional vector from OpenAI's `text-embedding-3-small` model. We need pgvector extension (migration 1) for this column type to exist.

**The vector index:**
```sql
create index using ivfflat (embedding vector_cosine_ops) with (lists = 100);
```
IVFFlat is an Approximate Nearest Neighbor (ANN) index — it makes vector similarity search fast even with millions of chunks.

**`user_id` is denormalised here (copied from `reels`):** We could join `reel_chunks → reels` to get the user, but putting `user_id` directly on each chunk means vector similarity queries can filter by user without an extra join. Performance matters when searching millions of vectors.

---

#### Table 5: `chat_sessions`
*File: `20260502000006_create_chat_sessions_table.sql`*

**What it is:** One row per conversation thread.

`category_id = NULL` means it's a global search (searches across all categories). A non-null `category_id` means the chat is scoped to that category (e.g., "Ask about Skincare").

Sessions persist across app restarts — users can scroll back through old conversations.

---

#### Table 6: `chat_messages`
*File: `20260502000007_create_chat_messages_table.sql`*

**What it is:** One row per message turn — user questions and AI responses.

The `sources` column is JSONB (flexible JSON stored in the database):
```json
[
  {
    "type": "library",
    "reel_id": "...",
    "creator_handle": "@skincareexpert",
    "thumbnail_url": "...",
    "extract": "The relevant chunk text...",
    "url": "https://instagram.com/reel/..."
  }
]
```
This is what drives the "rich cards" shown below AI responses in the iOS app — the data is stored right on the message.

`role` has a CHECK constraint enforcing only `'user'` or `'assistant'` — the database itself rejects invalid values.

---

#### Table 7: `feedback`
*File: `20260502000008_create_feedback_table.sql`*

**What it is:** Thumbs up (+1) / thumbs down (-1) on AI responses. One vote per user per message.

Used for quality metrics — tracking which responses users find helpful vs. not.

---

## Part 4: pgvector Extension (Step 6)

*File: `20260502000001_init_pgvector_extension.sql`*

```sql
create extension if not exists vector;
```

One line, but critically important. Without this, the `vector(1536)` column type in `reel_chunks` doesn't exist and the migration fails. This is why it's migration #1 — everything that comes after depends on it.

pgvector is what lets PostgreSQL store and search high-dimensional vectors. Supabase ships it but doesn't enable it by default.

---

## Part 5: Row-Level Security (Step 7)

*File: `20260502000009_create_rls_policies.sql`*

### What is RLS?
Row-Level Security is a PostgreSQL feature where the database itself enforces access rules — not your application code. Even if your backend has a bug and tries to return someone else's data, the database silently filters it out.

### Our Approach: Basic Isolation + Service Role Bypass

**Basic Isolation** — Users can only see their own rows:
```sql
-- Example: Users can only select their own reels
create policy "Users can view own active reels"
on public.reels for select
using (user_id = auth.uid() and deleted_at is null);
```
`auth.uid()` is a Supabase function that returns the currently authenticated user's UUID. If there's no logged-in user, it returns NULL and nothing matches.

**Service Role Bypass** — The backend bypasses all RLS:
When the backend connects to Supabase using the service role key, PostgreSQL automatically skips all RLS policies. This is by design — the backend needs to process any user's reel (transcribe it, embed it, classify it) without impersonating users. This is safe because the service role key is never exposed to users.

**Categories special case:**
```sql
-- Default categories are visible to everyone (they have no owner)
create policy "Users can view default and own categories"
on public.categories for select
using (is_default = true or user_id = auth.uid());
```

### What's in the Backlog
Advanced RLS features (sharing between users, public profiles, collaboration) are deferred to Phase 2+. They're tracked in `backlog.md` so we don't forget them.

---

## Part 6: Default Categories Seed (Step 5b)

*File: `20260502000010_seed_default_categories.sql`*

```sql
insert into public.categories (user_id, name, is_default)
values
  (null, 'Skincare', true),
  (null, 'Haircare', true),
  ...
```

This runs once when migrations are applied and populates the 6 default categories. `ON CONFLICT DO NOTHING` makes it safe to run multiple times.

---

## Key Decisions Summary

| Decision | What We Chose | Why |
|---|---|---|
| Migration tool | Supabase native SQL migrations | Fewer bugs, simpler, full Supabase compatibility |
| Repo structure | Monorepo (frontend + backend together) | Easier coordination for a small team |
| Auth | Supabase Auth (Email + Google) | Built-in, no custom auth server needed |
| RLS approach | Basic isolation now, advanced later | Ship faster, upgrade path tracked in backlog |
| Backend DB auth | Service role key (bypasses RLS) | Backend needs to process any user's data |
| iOS DB auth | Anon key (limited by RLS) | Safe for client-side, database enforces isolation |
| Embeddings | `sentence-transformers` (local, free) | No per-call cost; runs in Celery worker. Dim may change from 1536 — see DECISIONS.md |
| Vector search | ivfflat ANN index | Fast approximate search at scale |
| Reel deletion | Soft delete (`deleted_at`) | Chat history can still reference deleted reels |

---

## What's Left in Phase 1

1. **App Groups (Xcode)** — Enable entitlement on both targets in Xcode, use same group ID
2. **Apply migrations** — Run `supabase migration up` to create all tables in the live Supabase project
3. **Create `.env`** — Copy from `.env.example`, fill in real credentials
4. **Config.swift** — Supabase URL + anon key in the iOS project (never commit this)

---

*ReelMind Phase 1 Knowledge Doc — v1.0 — May 2026*
