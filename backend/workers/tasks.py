"""Celery task definitions.

`process_reel` is the single async task that runs the entire ingestion
pipeline for one reel. We deliberately keep all stages in one task so
that:
  - per-reel state lives in a single worker process (no inter-task DB
    polling)
  - retry semantics are uniform (one Celery task, one retry counter)
  - cleanup of the temp audio file is bounded by a single try/finally

Pipeline stages:
    Step 15 — download audio + metadata          (services/downloader.py)
    Step 16 — transcribe audio                   (services/transcriber.py)
    Step 17 — caption fallback (TODO)
    Step 18 — Llama classification (TODO)
    Step 19 — confidence routing (TODO)
    Step 20 — chunk + embed (TODO)
    Step 22 — FCM push (TODO)
"""

from __future__ import annotations

import logging
import os

from services.downloader import (
    DownloadError,
    DownloadResult,
    download_reel,
)
from services.transcriber import TranscriptionError, transcribe_audio
from supabase_client import get_supabase
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="workers.tasks.process_reel", bind=True, max_retries=3)
def process_reel(self, reel_id: str) -> dict:
    """Run the ingestion pipeline for a single reel."""
    log = logging.LoggerAdapter(logger, {"reel_id": reel_id})
    log.info(
        "process_reel start | retry=%s/%s",
        self.request.retries,
        self.max_retries,
    )

    supabase = get_supabase()
    download_result: DownloadResult | None = None

    try:
        # ------------------------------------------------------------------
        # Mark processing + fetch URL
        # ------------------------------------------------------------------
        log.info("marking status=processing")
        supabase.table("reels").update({
            "status": "processing",
            "retry_count": self.request.retries,
        }).eq("id", reel_id).execute()

        log.info("fetching reel row from DB")
        row = (
            supabase.table("reels")
            .select("url, user_id")
            .eq("id", reel_id)
            .single()
            .execute()
        )
        url = row.data["url"]
        log.info("reel url loaded | url=%s", url)

        # ------------------------------------------------------------------
        # Step 15 — download audio + metadata
        # ------------------------------------------------------------------
        log.info("step 15 | downloading reel")
        try:
            download_result = download_reel(url, reel_id)
        except DownloadError as exc:
            log.warning(
                "download failed | retryable=%s | %s", exc.is_retryable, exc
            )
            return _handle_pipeline_error(
                self, supabase, reel_id, exc, exc.is_retryable, log
            )

        meta = download_result.metadata
        log.info(
            "step 15 | persisting metadata | creator=@%s | hashtags=%d | "
            "caption_chars=%d | thumb=%s",
            meta.creator_handle,
            len(meta.hashtags),
            len(meta.caption or ""),
            bool(meta.thumbnail_url),
        )
        supabase.table("reels").update({
            "caption": meta.caption,
            "hashtags": meta.hashtags,
            "creator_handle": meta.creator_handle or None,
            "thumbnail_url": meta.thumbnail_url,
        }).eq("id", reel_id).execute()
        log.info("step 15 | metadata saved to DB")

        # ------------------------------------------------------------------
        # Step 16 — transcribe audio
        # ------------------------------------------------------------------
        if download_result.audio_path:
            log.info("step 16 | transcribing audio")
            try:
                transcription = transcribe_audio(
                    download_result.audio_path, reel_id
                )
            except TranscriptionError as exc:
                log.warning(
                    "transcription failed | retryable=%s | %s",
                    exc.is_retryable,
                    exc,
                )
                return _handle_pipeline_error(
                    self, supabase, reel_id, exc, exc.is_retryable, log
                )

            log.info(
                "step 16 | persisting transcript | chars=%d | has_audio=%s",
                len(transcription.text),
                transcription.has_audio,
            )
            supabase.table("reels").update({
                "transcript": transcription.text or None,
                "has_audio": transcription.has_audio,
            }).eq("id", reel_id).execute()
            log.info("step 16 | transcript saved to DB")
        else:
            # No audio URL was extractable — treat as silent reel. Step 17
            # (caption fallback) will eventually handle classification from
            # caption alone; for now we just record has_audio=false.
            log.info("step 16 | skipped — no audio URL on this reel")
            supabase.table("reels").update({"has_audio": False}).eq(
                "id", reel_id
            ).execute()

        # ------------------------------------------------------------------
        # Steps 17-22 — TODO (classification, embeddings, push)
        # ------------------------------------------------------------------
        # Until Step 18 lands, we leave the row in 'processing'. Once
        # classification + confidence routing exist, we'll set 'ready' or
        # 'uncategorised'. Marking 'ready' here would be a lie — the reel
        # is not yet usable for category browsing or search.

        log.info("process_reel done")
        return {
            "reel_id": reel_id,
            "status": "metadata_and_transcript_saved",
            "has_audio": (
                download_result.audio_path is not None
                and os.path.exists(download_result.audio_path)
            ),
        }

    finally:
        if download_result is not None:
            _cleanup(download_result, log)


def _handle_pipeline_error(
    task,
    supabase,
    reel_id: str,
    exc: Exception,
    is_retryable: bool,
    log: logging.LoggerAdapter,
) -> dict:
    """Schedule a Celery retry or mark the reel failed."""
    if is_retryable and task.request.retries < task.max_retries:
        countdown = 60 * (task.request.retries + 1)
        log.info("scheduling retry | countdown=%ss", countdown)
        raise task.retry(exc=exc, countdown=countdown)

    log.error("marking status=failed | %s", exc)
    supabase.table("reels").update({"status": "failed"}).eq(
        "id", reel_id
    ).execute()
    return {"reel_id": reel_id, "status": "failed", "error": str(exc)}


def _cleanup(result: DownloadResult, log: logging.LoggerAdapter) -> None:
    """Delete the temp dir created by services.downloader."""
    temp_dir = result.temp_dir
    if not temp_dir or not os.path.exists(temp_dir):
        return
    log.info("cleanup | removing temp_dir=%s", temp_dir)
    try:
        for name in os.listdir(temp_dir):
            try:
                os.remove(os.path.join(temp_dir, name))
            except OSError as exc:
                log.warning("could not remove %s: %s", name, exc)
        os.rmdir(temp_dir)
    except OSError as exc:
        log.warning("could not remove temp_dir %s: %s", temp_dir, exc)


@celery_app.task(name="workers.tasks.ping")
def ping() -> str:
    """Simple smoke test — verifies workers are alive."""
    return "pong"
