-- Row-Level Security Policies
-- Basic isolation: users see only their own data
-- Service role (backend) bypasses RLS for processing

-- ============================================================================
-- PROFILES TABLE
-- ============================================================================

-- Users can view their own profile
create policy "Users can view own profile"
on public.profiles for select
using (auth.uid() = id);

-- Users can update their own profile
create policy "Users can update own profile"
on public.profiles for update
using (auth.uid() = id);

-- ============================================================================
-- CATEGORIES TABLE
-- ============================================================================

-- Users can see default categories + their own custom categories
create policy "Users can view default and own categories"
on public.categories for select
using (is_default = true or user_id = auth.uid());

-- Users can create categories
create policy "Users can create categories"
on public.categories for insert
with check (auth.uid() = user_id);

-- Users can update their own categories
create policy "Users can update own categories"
on public.categories for update
using (user_id = auth.uid());

-- Users can delete their own categories
create policy "Users can delete own categories"
on public.categories for delete
using (user_id = auth.uid());

-- ============================================================================
-- REELS TABLE
-- ============================================================================

-- Users can view their own reels (not soft-deleted)
create policy "Users can view own active reels"
on public.reels for select
using (user_id = auth.uid() and deleted_at is null);

-- Users can view their deleted reels (for recovery UI or history)
create policy "Users can view own deleted reels"
on public.reels for select
using (user_id = auth.uid() and deleted_at is not null);

-- Users can create reels
create policy "Users can create reels"
on public.reels for insert
with check (auth.uid() = user_id);

-- Users can update their own reels
create policy "Users can update own reels"
on public.reels for update
using (auth.uid() = user_id);

-- Users can delete (soft-delete) their own reels
create policy "Users can delete own reels"
on public.reels for delete
using (auth.uid() = user_id);

-- ============================================================================
-- REEL_CHUNKS TABLE
-- ============================================================================

-- Users can view chunks of their own reels
create policy "Users can view own reel chunks"
on public.reel_chunks for select
using (user_id = auth.uid());

-- Users can create chunks (during processing)
create policy "Users can create reel chunks"
on public.reel_chunks for insert
with check (auth.uid() = user_id);

-- Users can update their own chunks
create policy "Users can update own reel chunks"
on public.reel_chunks for update
using (auth.uid() = user_id);

-- Users can delete their own chunks
create policy "Users can delete own reel chunks"
on public.reel_chunks for delete
using (auth.uid() = user_id);

-- ============================================================================
-- CHAT_SESSIONS TABLE
-- ============================================================================

-- Users can view their own sessions
create policy "Users can view own chat sessions"
on public.chat_sessions for select
using (user_id = auth.uid());

-- Users can create sessions
create policy "Users can create chat sessions"
on public.chat_sessions for insert
with check (auth.uid() = user_id);

-- Users can update their own sessions
create policy "Users can update own chat sessions"
on public.chat_sessions for update
using (auth.uid() = user_id);

-- Users can delete their own sessions
create policy "Users can delete own chat sessions"
on public.chat_sessions for delete
using (auth.uid() = user_id);

-- ============================================================================
-- CHAT_MESSAGES TABLE
-- ============================================================================

-- Users can view messages in their own sessions
create policy "Users can view messages in own sessions"
on public.chat_messages for select
using (session_id in (
  select id from public.chat_sessions where user_id = auth.uid()
));

-- Users can create messages in their own sessions
create policy "Users can create messages in own sessions"
on public.chat_messages for insert
with check (session_id in (
  select id from public.chat_sessions where user_id = auth.uid()
));

-- Users can update their own messages
create policy "Users can update own messages"
on public.chat_messages for update
using (session_id in (
  select id from public.chat_sessions where user_id = auth.uid()
));

-- Users can delete their own messages
create policy "Users can delete own messages"
on public.chat_messages for delete
using (session_id in (
  select id from public.chat_sessions where user_id = auth.uid()
));

-- ============================================================================
-- FEEDBACK TABLE
-- ============================================================================

-- Users can view their own feedback
create policy "Users can view own feedback"
on public.feedback for select
using (user_id = auth.uid());

-- Users can create feedback on messages from their sessions
create policy "Users can create feedback"
on public.feedback for insert
with check (
  auth.uid() = user_id and
  message_id in (
    select cm.id from public.chat_messages cm
    join public.chat_sessions cs on cm.session_id = cs.id
    where cs.user_id = auth.uid()
  )
);

-- Users can update their own feedback
create policy "Users can update own feedback"
on public.feedback for update
using (auth.uid() = user_id);

-- Users can delete their own feedback
create policy "Users can delete own feedback"
on public.feedback for delete
using (auth.uid() = user_id);
