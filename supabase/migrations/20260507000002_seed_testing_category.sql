-- Seed a "Testing" default category (development convenience).
--
-- Purpose: during development we want a place to dump test reels so we can
-- inspect rows, verify the Whisper transcription quality, classification
-- confidence, etc., without polluting the real lifestyle categories.
--
-- This is intentionally a default category (user_id = NULL, is_default = TRUE)
-- so it's visible to every user. Before public launch we will either:
--   (a) drop this row via a new migration, or
--   (b) add a `is_internal` flag to categories and hide it from non-dev users.
--
-- Tracked for removal in docs/backlog.md.

insert into public.categories (id, user_id, name, is_default, created_at)
values
  (gen_random_uuid(), null, 'Testing', true, now())
on conflict do nothing;
