-- Chat sessions table
-- One session per conversation thread
-- category_id = NULL means global search (cross-category)
create table if not exists public.chat_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  category_id uuid references public.categories(id) on delete set null,
  title text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Indexes
create index if not exists idx_chat_sessions_user_id on public.chat_sessions(user_id);
create index if not exists idx_chat_sessions_user_id_updated_at_desc on public.chat_sessions(user_id, updated_at desc);
create index if not exists idx_chat_sessions_user_id_category_id on public.chat_sessions(user_id, category_id);

-- Enable RLS
alter table public.chat_sessions enable row level security;

-- Trigger to auto-update updated_at
create trigger chat_sessions_updated_at
before update on public.chat_sessions
for each row
execute function public.set_updated_at();
