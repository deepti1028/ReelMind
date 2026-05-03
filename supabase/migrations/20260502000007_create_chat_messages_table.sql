-- Chat messages table
-- One row per message turn (user or assistant)
-- sources JSONB stores reel/web results backing the response
create table if not exists public.chat_messages (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.chat_sessions(id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  sources jsonb,
  created_at timestamptz not null default now()
);

-- Indexes
create index if not exists idx_chat_messages_session_id on public.chat_messages(session_id);
create index if not exists idx_chat_messages_session_id_created_at_asc on public.chat_messages(session_id, created_at asc);

-- Enable RLS
alter table public.chat_messages enable row level security;
