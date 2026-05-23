-- Add display_name to profiles.
--
-- Why SECURITY DEFINER: profiles has RLS enabled with no INSERT policy for
-- anonymous callers. A trigger without SECURITY DEFINER runs as the invoking
-- role (anon), which hits the RLS deny-all default and fails with
-- "Database error creating user." SECURITY DEFINER makes the function run as
-- its owner (postgres), bypassing RLS — same pattern used by Supabase's own
-- system triggers.
alter table public.profiles
  add column if not exists display_name text;

drop trigger if exists on_auth_user_created on auth.users;

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, new.raw_user_meta_data->>'full_name')
  on conflict (id) do nothing;
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
