-- supabase/migrations/20260530000003_thumbnails_bucket.sql
-- Public bucket for permanent thumbnail storage.
-- Writes use the service role key (bypasses RLS).
-- Reads are unauthenticated (iOS AsyncImage loads directly).

insert into storage.buckets (id, name, public)
values ('thumbnails', 'thumbnails', true)
on conflict (id) do nothing;

create policy "Public thumbnail read"
  on storage.objects for select
  using (bucket_id = 'thumbnails');
