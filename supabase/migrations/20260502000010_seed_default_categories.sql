-- Seed 6 default categories
-- These are system-wide and available to all users
insert into public.categories (id, user_id, name, is_default, created_at)
values
  (gen_random_uuid(), null, 'Skincare', true, now()),
  (gen_random_uuid(), null, 'Haircare', true, now()),
  (gen_random_uuid(), null, 'Bodycare', true, now()),
  (gen_random_uuid(), null, 'Fitness', true, now()),
  (gen_random_uuid(), null, 'Nutrition', true, now()),
  (gen_random_uuid(), null, 'Fashion', true, now())
on conflict do nothing;
