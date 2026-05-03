-- Reel chunks table — transcript chunks with embeddings
-- Each chunk gets its own embedding for RAG retrieval
-- Hard-deleted when parent reel is soft-deleted
create table if not exists public.reel_chunks (
  id uuid primary key default gen_random_uuid(),
  reel_id uuid not null references public.reels(id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  chunk_index smallint not null,
  content text not null,
  embedding vector(1536),
  created_at timestamptz not null default now()
);

-- Indexes
create index if not exists idx_reel_chunks_reel_id on public.reel_chunks(reel_id);
create index if not exists idx_reel_chunks_user_id on public.reel_chunks(user_id);
create index if not exists idx_reel_chunks_user_id_reel_id on public.reel_chunks(user_id, reel_id);

-- Vector similarity search index (ivfflat for faster ANN)
create index if not exists idx_reel_chunks_embedding on public.reel_chunks
using ivfflat (embedding vector_cosine_ops) with (lists = 100);

-- Enable RLS
alter table public.reel_chunks enable row level security;
