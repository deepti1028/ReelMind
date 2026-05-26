-- Remove the "Testing" default category added during development.
-- See 20260507000002_seed_testing_category.sql for context.

delete from public.categories
where name = 'Testing'
  and is_default = true
  and user_id is null;
