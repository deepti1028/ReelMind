# ReelMind — Architectural Decisions Log

Append-only record of significant decisions. When you change your mind, add a new entry rather than editing an old one — context matters.

---

## 2026-05-07: Use Groq + sentence-transformers instead of OpenAI/Anthropic

**Decision:** All AI services that previously assumed OpenAI Whisper, OpenAI text-embedding-3-small, and Anthropic Claude are now backed by:

| Need | Old (paid) | New (free tier) |
|---|---|---|
| Audio transcription | OpenAI Whisper API ($0.006/min) | **Groq `whisper-large-v3`** (free tier) |
| Embeddings | OpenAI `text-embedding-3-small` (1536 dims, paid) | **`sentence-transformers`** running locally in Celery worker |
| Classification | Anthropic Claude (paid) | **Groq Llama 3.3 70B** (free tier) |

**Why:** MVP cost containment. Both OpenAI and Anthropic charge per-call; for a project at our stage with no revenue, free tiers are sufficient and let us iterate without thinking about per-reel cost.

**Trade-offs we're accepting:**
- Groq's free tier has rate limits (currently ~30 req/min on Whisper, ~14k tokens/min on Llama). Beyond that the request is throttled. Plenty for development; may need to revisit at scale.
- `sentence-transformers` runs the embedding model in-process, which means a one-time ~100 MB model download and CPU compute per call. Slower than an API but $0 forever.
- Groq is a single point of failure for both transcription and classification. Acceptable for MVP; we can shard later if needed.

**Embedding dimension:** `sentence-transformers/all-MiniLM-L6-v2` produces 384-dimensional embeddings, not 1536. The `reel_chunks.embedding` column type is currently `vector(1536)` per the original migrations. **We must update the column to `vector(384)` (or whatever model we pick) before Step 20 implementation.** This is a cheap migration since no production data exists yet.

**Env vars:**
- Removed: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`
- Added: `GROQ_API_KEY`
- `sentence-transformers` doesn't need a key.

**Code state at time of decision:** No real OpenAI/Anthropic API calls had been written yet — the services folder was empty, only stubs existed. All changes were in config files (`.env.example`, `config.py`, `render.yaml`, `requirements.txt`) plus knowledge docs. When `services/transcriber.py` and `services/classifier.py` get implemented in Phase 2, they'll use Groq from day one.

**How to revisit:** if free-tier limits become a problem at scale, options in order of effort:
1. Pay for Groq's higher tier
2. Switch transcription back to OpenAI Whisper (proven, expensive)
3. Self-host Whisper on a GPU instance
4. Switch classification to a smaller fine-tuned model

---

## 2026-05-07: Caption + hashtags are compulsory inputs to classification, not a fallback

**Decision:** The classifier (Groq Llama, Step 18) always receives caption + hashtags + transcript as input, regardless of whether Whisper produced a transcript. Previously the design framed caption + hashtags as a *fallback* — used only when Whisper returned empty. They are now treated as *first-class signal* equal to the transcript.

**Why:** Caption text and hashtags carry the strongest classification signal in many reels — a creator literally writing "BEST CHOCOLATE CAKE RECIPE 🍰 #baking #dessert" is unambiguous, even if the audio is music-only. Treating them as a fallback wastes signal. The previous Phase 2 Steps 16-18 doc already noted this informally; this entry makes it the formal policy.

**What changed in code/data:**
- (Future) `services/classifier.py` will always include caption + hashtags in the prompt context.
- The naming of the "caption fallback" Step 17 in plan/docs is misleading; will rename or rephrase to "always-extracted metadata".

## 2026-05-07: Add `has_audio` flag to reels table

**Decision:** Add a boolean `has_audio` column to the `reels` table.

**Why:** "No transcript" is ambiguous — could mean (a) the reel had no audio track, (b) audio was music-only with no speech, (c) Whisper failed transiently. We want to distinguish "this reel has no audio to transcribe" (permanent state) from "we tried and got nothing" so we can:
- Show users a UI badge ("classified from caption only")
- Skip Whisper retries for known-silent reels
- Track analytics on what fraction of saved reels are audio-less

**Three states:**
- `TRUE` → Whisper extracted speech, transcript is non-empty
- `FALSE` → reel had no audio OR Whisper returned empty (music-only / unintelligible)
- `NULL` → not yet processed

**Migration:** [`supabase/migrations/20260507000001_add_has_audio_to_reels.sql`](../supabase/migrations/20260507000001_add_has_audio_to_reels.sql).

## 2026-05-07: Add a "Testing" default category for development

**Decision:** Add a `Testing` default category to the seed data so we can dump test reels there during development without polluting the real lifestyle categories.

**Why:** During Phase 2 verification, we want to ingest a few reels and inspect transcript quality, classification confidence, embeddings, etc. Having a category specifically for this keeps the real default categories clean.

**Migration:** [`supabase/migrations/20260507000002_seed_testing_category.sql`](../supabase/migrations/20260507000002_seed_testing_category.sql). Tracked in `backlog.md` for removal before public launch.
