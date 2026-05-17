-- Add suggested_categories to reels for pending_category FCM flow (Step 22)
-- Stores the category names shown to the user as FCM notification buttons.
ALTER TABLE public.reels
ADD COLUMN IF NOT EXISTS suggested_categories text[] DEFAULT '{}';
