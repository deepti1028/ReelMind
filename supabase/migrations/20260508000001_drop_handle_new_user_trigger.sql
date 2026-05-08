-- Drop the auto-profile-creation trigger.
--
-- Why: the trigger inserts into public.profiles, which has RLS enabled but no
-- INSERT policy. Without SECURITY DEFINER on the trigger function, every signup
-- fails with "Database error creating user." Rather than wrestle with RLS and
-- SECURITY DEFINER for a system trigger, we move profile lifecycle into the
-- backend.
--
-- New flow:
--   - Signup creates a row in auth.users only.
--   - The first time the backend handles an authenticated request from a user
--     (currently: POST /api/v1/reels), it upserts the corresponding row in
--     public.profiles using the service role key, which bypasses RLS by design.
--
-- This keeps profile creation idempotent, observable (in our backend logs),
-- and free of trigger/RLS coupling.

drop trigger if exists on_auth_user_created on auth.users;
drop function if exists public.handle_new_user();
