-- Add FCM token to profiles for push notifications (Step 22)
-- One device per user for MVP. Multi-device support is post-MVP (would need a separate devices table).
alter table public.profiles
  add column if not exists fcm_token text,
  add column if not exists fcm_token_updated_at timestamptz;

create index if not exists idx_profiles_fcm_token on public.profiles(fcm_token)
  where fcm_token is not null;
