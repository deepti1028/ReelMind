-- Reels table — core table for saved reels
-- Soft-deleted via deleted_at
create table if not exists public.reels (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  category_id uuid references public.categories(id) on delete set null,
  url text not null,
  creator_handle text,
  thumbnail_url text,
  transcript text,
  caption text,
  hashtags text[] default '{}',
  summary text,
  confidence float4,
  status text not null default 'queued',
  retry_count smallint default 0,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  -- Unique per user
  unique(user_id, url)
);

-- Indexes
create index if not exists idx_reels_user_id on public.reels(user_id);
create index if not exists idx_reels_user_id_category_id on public.reels(user_id, category_id);
create index if not exists idx_reels_status on public.reels(status);
create index if not exists idx_reels_deleted_at on public.reels(deleted_at);
create index if not exists idx_reels_created_at_desc on public.reels(created_at desc);

-- Enable RLS
alter table public.reels enable row level security;

-- Trigger to auto-update updated_at
create trigger reels_updated_at
before update on public.reels
for each row
execute function public.set_updated_at();
