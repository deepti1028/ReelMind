-- When a user's profile is deleted, also delete their custom categories.
-- Previously ON DELETE SET NULL left orphaned rows (user_id=NULL, is_default=FALSE).
-- System defaults already have user_id=NULL so they are unaffected by this constraint.
ALTER TABLE public.categories
  DROP CONSTRAINT categories_user_id_fkey,
  ADD CONSTRAINT categories_user_id_fkey
    FOREIGN KEY (user_id)
    REFERENCES public.profiles(id)
    ON DELETE CASCADE;

-- Clean up any orphaned user-created categories from previous deletions.
DELETE FROM public.categories WHERE user_id IS NULL AND is_default = FALSE;
