-- Set SF Symbol icons on the 6 seeded default categories.
-- These rows predate the icon column (added 20260523) so icon is NULL.
UPDATE public.categories
SET icon = CASE name
  WHEN 'Skincare'   THEN 'sparkles'
  WHEN 'Haircare'   THEN 'scissors'
  WHEN 'Bodycare'   THEN 'drop'
  WHEN 'Fitness'    THEN 'dumbbell'
  WHEN 'Nutrition'  THEN 'fork.knife'
  WHEN 'Fashion'    THEN 'bag'
  ELSE 'bookmark'
END
WHERE is_default = true;
