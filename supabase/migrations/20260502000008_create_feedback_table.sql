-- Feedback table
-- Thumbs up (+1) / thumbs down (-1) on assistant responses
-- One vote per user per message
create table if not exists public.feedback (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  message_id uuid not null references public.chat_messages(id) on delete cascade,
  rating smallint not null check (rating in (1, -1)),
  created_at timestamptz not null default now(),

  -- One vote per user per message
  unique(user_id, message_id)
);

-- Indexes
create index if not exists idx_feedback_user_id_message_id on public.feedback(user_id, message_id);
create index if not exists idx_feedback_message_id on public.feedback(message_id);

-- Enable RLS
alter table public.feedback enable row level security;
