-- Resize from 1536 (OpenAI placeholder) to 384 (bge-small-en-v1.5 actual output)
drop index if exists idx_reel_chunks_embedding;

alter table public.reel_chunks
  alter column embedding type vector(384);

create index idx_reel_chunks_embedding on public.reel_chunks
  using ivfflat (embedding vector_cosine_ops) with (lists = 50);
