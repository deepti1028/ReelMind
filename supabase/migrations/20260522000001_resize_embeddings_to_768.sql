-- supabase/migrations/20260522000001_resize_embeddings_to_768.sql
-- Wipe all reel data (clean slate — migrating from bge-small-en-v1.5 384-dim to
-- text-embedding-004 768-dim; existing embeddings are incompatible)
truncate table public.reel_chunks cascade;
truncate table public.reels cascade;

-- Resize embedding column from 384 to 768
drop index if exists idx_reel_chunks_embedding;

alter table public.reel_chunks
  alter column embedding type vector(768);

create index idx_reel_chunks_embedding on public.reel_chunks
  using ivfflat (embedding vector_cosine_ops) with (lists = 50);

-- Update match_reel_chunks to accept 768-dim query vector
create or replace function match_reel_chunks(
    query_embedding vector(768),
    p_user_id       uuid,
    p_category_id   uuid,
    p_creator       text    default null,
    match_count     int     default 10,
    threshold       float   default 0.3
)
returns table (
    reel_id        uuid,
    content        text,
    similarity     float,
    creator_handle text,
    thumbnail_url  text,
    caption        text
)
language sql as $$
    select
        rc.reel_id,
        rc.content,
        1 - (rc.embedding <=> query_embedding) as similarity,
        r.creator_handle,
        r.thumbnail_url,
        r.caption
    from reel_chunks rc
    join reels r on r.id = rc.reel_id
    where rc.user_id = p_user_id
      and r.category_id = p_category_id
      and r.status = 'ready'
      and (p_creator is null
           or r.creator_handle ilike '%' || p_creator || '%')
      and 1 - (rc.embedding <=> query_embedding) > threshold
    order by rc.embedding <=> query_embedding
    limit match_count;
$$;
