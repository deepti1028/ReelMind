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
    Step 17 — build classification signal        (services/signal_builder.py)
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
from services.embedder import EmbeddingError, build_chunk_text, embed_document
from services.signal_builder import NoSignalError, build_classification_signal
from services.classifier import ClassificationError, ClassificationResult, classify_reel
from services.notifier import send_push_notification
from services.transcriber import TranscriptionError, TranscriptionResult, transcribe_audio
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
            .select("url, user_id, status")
            .eq("id", reel_id)
            .single()
            .execute()
        )
        reel_data = row.data
        url = reel_data["url"]
        log.info("reel url loaded | url=%s | current_status=%s", url, reel_data.get("status"))

        # Guard: if the reel is already in a terminal success state (e.g. from a
        # duplicate task dispatch), skip processing entirely.
        if reel_data.get("status") == "ready":
            log.info("reel already ready — skipping duplicate task dispatch")
            return {"reel_id": reel_id, "status": "already_ready"}

        # FCM token — fetched once for Step 22 pushes. Non-critical: a fetch
        # failure or missing profile row should not abort the pipeline.
        _fcm_token: str | None = None
        try:
            _profile = (
                supabase.table("profiles")
                .select("fcm_token")
                .eq("id", reel_data["user_id"])
                .single()
                .execute()
            )
            if _profile.data:
                _fcm_token = _profile.data.get("fcm_token")
        except Exception as exc:
            log.warning("could not fetch fcm_token | %s", exc)

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
        transcription: TranscriptionResult | None = None
        if download_result.audio_path:
            log.info("step 16 | transcribing audio")
            try:
                transcription = transcribe_audio(
                    download_result.audio_path, reel_id
                )
            except TranscriptionError as exc:
                log.warning(
                    "transcription failed | retryable=%s | retries=%s/%s | %s",
                    exc.is_retryable,
                    self.request.retries,
                    self.max_retries,
                    exc,
                )
                if exc.is_retryable and self.request.retries < self.max_retries:
                    countdown = 60 * (self.request.retries + 1)
                    log.info("scheduling transcription retry | countdown=%ss", countdown)
                    raise self.retry(exc=exc, countdown=countdown)

                # Out of retries or non-retryable codec error — graceful degradation.
                # Pipeline continues with has_audio=False; Steps 17-22 will
                # classify from caption + hashtags alone.
                log.warning(
                    "step 16 | graceful degradation — transcription failed, "
                    "continuing pipeline with caption-only signal"
                )
                supabase.table("reels").update(
                    {"has_audio": False, "transcript": None}
                ).eq("id", reel_id).execute()
                log.info("step 16 | has_audio=False saved — pipeline continues")
            else:
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
        # Step 17 — build classification signal
        # ------------------------------------------------------------------
        _transcript_text = transcription.text if transcription is not None else None

        try:
            signal = build_classification_signal(
                transcript=_transcript_text,
                caption=meta.caption,
                hashtags=meta.hashtags,
            )
            log.info(
                "step 17 | signal built | sources=%s | chars=%d",
                signal.source_summary,
                len(signal.text),
            )
        except NoSignalError:
            log.warning(
                "step 17 | no usable signal (transcript=None, caption=None, "
                "hashtags=[]) — marking uncategorised"
            )
            supabase.table("reels").update(
                {"status": "uncategorised"}
            ).eq("id", reel_id).execute()
            send_push_notification(
                fcm_token=_fcm_token,
                title="Reel saved",
                body="We couldn't categorise it — no audio or caption found",
                data={"reel_id": reel_id, "status": "uncategorised"},
            )
            return {"reel_id": reel_id, "status": "uncategorised"}

        # ------------------------------------------------------------------
        # Step 20 — embed reel content + store chunk
        # ------------------------------------------------------------------
        _chunk_text = build_chunk_text(
            transcript=_transcript_text,
            caption=meta.caption,
            hashtags=meta.hashtags,
        )
        if _chunk_text:
            log.info("step 20 | embedding | chars=%d", len(_chunk_text))
            try:
                _embedding = embed_document(_chunk_text)
            except EmbeddingError as exc:
                log.warning(
                    "step 20 | embedding failed | retryable=%s | %s",
                    exc.is_retryable,
                    exc,
                )
                return _handle_pipeline_error(
                    self, supabase, reel_id, exc, exc.is_retryable, log
                )
            supabase.table("reel_chunks").upsert({
                "reel_id": reel_id,
                "user_id": reel_data["user_id"],
                "chunk_index": 0,
                "content": _chunk_text,
                "embedding": _embedding,
            }).execute()
            log.info("step 20 | chunk stored")
        else:
            log.warning("step 20 | no content to embed — skipping")

        # ------------------------------------------------------------------
        # Step 18 — fetch categories + call Llama classifier
        # ------------------------------------------------------------------
        log.info("step 18 | fetching categories for user=%s", reel_data["user_id"])
        _cat_rows = (
            supabase.table("categories")
            .select("id, name")
            .or_(f"user_id.eq.{reel_data['user_id']},user_id.is.null")
            .execute()
        )
        category_db_map = {row["name"]: row["id"] for row in _cat_rows.data}
        category_names = list(category_db_map.keys())

        log.info("step 18 | classifying | categories=%d", len(category_names))
        try:
            classification = classify_reel(
                transcript=_transcript_text,
                caption=meta.caption,
                hashtags=meta.hashtags,
                categories=category_names,
            )
            log.info(
                "step 18 | done | category=%s | confidence=%.2f | alternatives=%s",
                classification.category,
                classification.confidence,
                classification.alternatives,
            )
        except ClassificationError as exc:
            log.warning(
                "step 18 | classification error | retryable=%s | %s",
                exc.is_retryable,
                exc,
            )
            return _handle_pipeline_error(
                self, supabase, reel_id, exc, exc.is_retryable, log
            )

        # ------------------------------------------------------------------
        # Step 19 — confidence routing
        # ------------------------------------------------------------------
        _CONFIDENCE_THRESHOLD = 0.70

        resolved_category_id = category_db_map.get(classification.category)
        if classification.confidence >= _CONFIDENCE_THRESHOLD and resolved_category_id:
            log.info(
                "step 19 | auto-assigning | confidence=%.2f >= %.2f",
                classification.confidence,
                _CONFIDENCE_THRESHOLD,
            )
            supabase.table("reels").update({
                "category_id": resolved_category_id,
                "confidence": classification.confidence,
                "status": "ready",
            }).eq("id", reel_id).execute()
            send_push_notification(
                fcm_token=_fcm_token,
                title="Reel saved!",
                body=f"Categorised as {classification.category}",
                data={"reel_id": reel_id, "status": "ready"},
            )
            log.info("step 19 | status=ready")
            return {
                "reel_id": reel_id,
                "status": "ready",
                "category": classification.category,
            }
        else:
            suggestions = [classification.category] + classification.alternatives[:2]
            if resolved_category_id is None and classification.confidence >= _CONFIDENCE_THRESHOLD:
                log.warning(
                    "step 19 | category=%s not in DB map — routing to pending_category",
                    classification.category,
                )
            else:
                log.info(
                    "step 19 | low confidence=%.2f — pending_category | suggestions=%s",
                    classification.confidence,
                    suggestions,
                )
            supabase.table("reels").update({
                "status": "pending_category",
                "suggested_categories": suggestions,
                "confidence": classification.confidence,
            }).eq("id", reel_id).execute()
            import json as _json
            send_push_notification(
                fcm_token=_fcm_token,
                title="Help us categorise this reel",
                body="Your reel is saved — which fits best? Ignoring this saves it to Uncategorised.",
                data={
                    "reel_id": reel_id,
                    "suggestions": _json.dumps(suggestions),
                },
                category_id="CATEGORISE",
            )
            log.info("step 19 | status=pending_category")
            return {
                "reel_id": reel_id,
                "status": "pending_category",
                "suggestions": suggestions,
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
