-- Add has_audio flag to reels.
--
-- Why a dedicated boolean rather than relying on `transcript IS NULL`?
--   - A reel can have audio that Whisper transcribed to an empty string
--     (e.g., music-only without speech-to-text triggers). That's still "has audio".
--   - A reel can be silent on purpose (text-overlay only, ASMR-no-speech, etc.).
--     That's "no audio".
--   - Distinguishing these two cases is useful for: (a) UI badges so user knows
--     classification was caption-only, (b) analytics on what % of reels are audio-less,
--     (c) avoiding pointless retries on Whisper for known-silent reels.
--
-- Three states:
--   has_audio = TRUE   → Whisper extracted speech, transcript is non-empty
--   has_audio = FALSE  → reel had audio but Whisper returned empty (music-only or unintelligible)
--                        OR reel had no audio track at all
--   has_audio = NULL   → reel hasn't been processed yet (pre-Whisper)
--
-- The Celery worker sets this column when it runs Whisper in Step 16.

alter table public.reels
  add column if not exists has_audio boolean;

create index if not exists idx_reels_has_audio on public.reels(has_audio);
