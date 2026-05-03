# Supabase Migrations

All database schema changes are managed through SQL migrations in the `/migrations` folder.

## Applying Migrations

### Prerequisites
1. Install Supabase CLI: `brew install supabase/tap/supabase` (on macOS)
2. Set up your project credentials

### Apply All Migrations
```bash
cd /Users/deeptijain/Documents/Deepti/ReelMind
supabase migration up
```

### Create a New Migration
```bash
supabase migration new <migration_name>
```

This creates a new timestamped file in `/migrations/`.

## Migration Files

All migrations are named with timestamp + descriptive name:

1. **20260502000001** — Enable pgvector extension
2. **20260502000002** — Create profiles table + triggers
3. **20260502000003** — Create categories table
4. **20260502000004** — Create reels table
5. **20260502000005** — Create reel_chunks table
6. **20260502000006** — Create chat_sessions table
7. **20260502000007** — Create chat_messages table
8. **20260502000008** — Create feedback table
9. **20260502000009** — Create RLS policies
10. **20260502000010** — Seed default categories (Skincare, Haircare, Bodycare, Fitness, Nutrition, Fashion)

## RLS Policies

All tables have row-level security enabled. Current policies enforce:
- **Basic isolation**: Users see only their own data
- **Service role bypass**: Backend (authenticated with service role key) can access all data for processing
- **Default categories**: Visible to all users, but unmodifiable by non-admins

See migration 20260502000009 for detailed RLS policies.

## Important: Never Skip Migrations

**Rule**: All database changes must go through migrations. Never execute raw SQL on the database.

This ensures:
- Reproducible schema across environments
- Clear audit trail of changes
- Easy rollback capability
- Team collaboration on schema changes
