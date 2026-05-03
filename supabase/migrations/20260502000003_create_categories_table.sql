-- Categories table
-- Stores both 6 seeded defaults (user_id = NULL) and user-created ones
create table if not exists public.categories (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.profiles(id) on delete set null,
  name text not null,
  is_default boolean not null default false,
  created_at timestamptz not null default now(),

  -- Unique per user: (user_id, name)
  unique(user_id, name)
);

-- Indexes
create index if not exists idx_categories_user_id on public.categories(user_id);
create index if not exists idx_categories_user_id_name on public.categories(user_id, name);

-- Enable RLS
alter table public.categories enable row level security;
