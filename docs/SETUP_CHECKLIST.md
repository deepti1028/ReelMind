# ReelMind Phase 1 — Setup Checklist

## ✅ Completed

### Database & Migrations (Step 5-6)
- [x] Created Supabase native migrations (10 files)
  - pgvector extension enabled
  - All 7 tables created (profiles, categories, reels, reel_chunks, chat_sessions, chat_messages, feedback)
  - All indexes created
  - All triggers created (auto-update timestamps, profile creation on signup)
  - All RLS policies implemented
  - 6 default categories seeded
- [x] Created migration documentation (`supabase/README.md`)
- [x] Migration files stored in `/supabase/migrations/`

### Backend Configuration (Step 4)
- [x] Created `/backend` folder structure
- [x] Backend config (`backend/config.py`) — reads from .env
- [x] Supabase client (`backend/supabase_client.py`) — uses service role key
- [x] `.env.example` template with all required credentials
- [x] `.gitignore` to prevent committing secrets

### Project Documentation
- [x] Created `backlog.md` with deferred features
- [x] Saved preferences to memory
- [x] Created setup checklist (this file)

---

## 🔲 Remaining Tasks (Steps 3, 4, 7)

### Step 3: Xcode Configuration
- [ ] **Configure App Groups entitlement**
  - Main app target: Enable "App Groups" capability
  - Share Extension target: Enable "App Groups" capability
  - Both must use same group ID (e.g., `group.com.reelmind.app`)
  - Create `Config.swift` to share group ID

### Step 4: Supabase Project Setup
- [ ] **Apply migrations to Supabase project**
  ```bash
  cd /Users/deeptijain/Documents/Deepti/ReelMind
  supabase migration up
  ```
  This will create all tables, indexes, triggers, and RLS policies

### Step 7: Backend Configuration
- [ ] **Create `.env` file in `/backend` folder**
  - Copy from `.env.example`
  - Fill in actual values:
    - Anon key: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJwZHFuZmhmcmhuemlmZ2Ztc2JqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzc1Nzk1NzUsImV4cCI6MjA5MzE1NTU3NX0.I4g18tsh3-RN7XjsECWsLBZlFDgCnJBnFMEoLZ_Ii6o`
    - Service role key: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJwZHFuZmhmcmhuemlmZ2Ztc2JqIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3Nzc3OTU3NSwiZXhwIjoyMDkzMTU1NTc1fQ.DRf7uDeYRik004lZNGyCQHolqTE7XHz9VcvkNscxwbw`
    - Other API keys (OpenAI, Redis URL, etc.)

### Frontend Configuration (Step 3-4)
- [ ] **Create `frontend/Config.swift`** with Supabase credentials
  - Xcode project already created
  - Share Extension already created
  - Need to add Config.swift with URL + anon key
  - Share both with backend via App Groups

---

## 📋 Migration Files Summary

```
supabase/migrations/
├── 20260502000001_init_pgvector_extension.sql
├── 20260502000002_create_profiles_table.sql
├── 20260502000003_create_categories_table.sql
├── 20260502000004_create_reels_table.sql
├── 20260502000005_create_reel_chunks_table.sql
├── 20260502000006_create_chat_sessions_table.sql
├── 20260502000007_create_chat_messages_table.sql
├── 20260502000008_create_feedback_table.sql
├── 20260502000009_create_rls_policies.sql
└── 20260502000010_seed_default_categories.sql
```

---
## Daily workflow of backednd
# Tab 1
cd ~/Desktop/Deepti/Projects/ReelMind/backend
docker-compose up -d              # Redis
source venv/bin/activate
uvicorn main:app --reload          # FastAPI

# Tab 2
cd ~/Desktop/Deepti/Projects/ReelMind/backend
source venv/bin/activate
celery -A workers.celery_app worker --loglevel=info

# Tab 3
ngrok http 8000
# Copy new ngrok URL → update ShareViewController.swift → rebuild iOS

## 🔐 Security Reminders

- ✅ Credentials stored in `.env`, not in code
- ✅ `.env` added to `.gitignore`
- ✅ `.env.example` provided for team reference
- ✅ RLS policies enforce user isolation
- ✅ Service role key used for backend only (never in frontend)
- ✅ Anon key used in frontend/mobile (safe for public)

---

## Next Steps After Setup

1. Apply migrations to Supabase
2. Create and fill `.env` file
3. Configure Xcode App Groups
4. Move to Step 8: Scaffold FastAPI backend
