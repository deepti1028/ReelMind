"""Audio transcription via Groq Whisper.

Step 16 of the build plan. Takes the audio file produced by
services.downloader and returns plain transcript text.

Public surface:
    transcribe_audio(audio_path, reel_id) -> TranscriptionResult
    TranscriptionResult, TranscriptionError (with is_retryable flag)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from groq import APIError, APITimeoutError, Groq
from groq import RateLimitError, APIConnectionError

from config import get_config

logger = logging.getLogger(__name__)

# Groq's whisper-large-v3-turbo: ~7x faster and cheaper than the non-turbo
# variant, with marginally lower accuracy. For 5-60s reels the quality
# difference is negligible and the latency win is meaningful in a
# user-waiting pipeline.
_WHISPER_MODEL = "whisper-large-v3-turbo"

# Groq Whisper rejects files >25MB. Reels rarely exceed 3MB of audio so this
# is mostly defensive — if we ever hit it the right fix is to transcode at
# lower bitrate, not silently truncate.
_MAX_FILE_BYTES = 25 * 1024 * 1024


@dataclass
class TranscriptionResult:
    text: str  # may be empty for silent / music-only reels
    has_audio: bool  # True iff text.strip() != ""
    language: str | None  # ISO code Whisper detected, e.g. "en"
    duration_seconds: float | None
    model: str


class TranscriptionError(Exception):
    """Errors raised by the transcriber.

    ``is_retryable`` mirrors the contract used by services.downloader so the
    Celery task can apply the same retry logic to either failure source.
    """

    def __init__(self, message: str, *, is_retryable: bool = False):
        super().__init__(message)
        self.is_retryable = is_retryable


def transcribe_audio(audio_path: str, reel_id: str) -> TranscriptionResult:
    """Transcribe a local audio file with Groq Whisper.

    Args:
        audio_path: Local filesystem path to the audio file (m4a, mp3, wav, etc.).
        reel_id: Caller-supplied identifier for log correlation.

    Returns:
        TranscriptionResult with text, language, duration, and ``has_audio`` flag.

    Raises:
        TranscriptionError: With ``is_retryable`` set so the worker knows
            whether to retry the whole pipeline.
    """
    log = _bound_logger(reel_id)
    log.info("transcribe_audio start | path=%s", audio_path)

    if not os.path.exists(audio_path):
        log.error(
            "transcribe failed | likely_cause=audio file vanished between "
            "Step 15 download and Step 16 (cleanup race or worker restart) "
            "| path=%s",
            audio_path,
        )
        raise TranscriptionError(
            f"audio file not found: {audio_path}", is_retryable=False
        )

    file_size = os.path.getsize(audio_path)
    log.info("audio file ready | bytes=%s", file_size)

    if file_size == 0:
        log.error(
            "transcribe failed | likely_cause=audio download wrote 0 bytes "
            "(IG CDN returned empty response or DASH manifest gave a bad URL) "
            "| path=%s",
            audio_path,
        )
        raise TranscriptionError(
            "audio file is empty (0 bytes)", is_retryable=False
        )
    if file_size > _MAX_FILE_BYTES:
        log.error(
            "transcribe failed | likely_cause=audio file exceeds Groq's 25MB "
            "upload limit (transcoding to lower bitrate would be needed) "
            "| bytes=%s | limit=%s",
            file_size,
            _MAX_FILE_BYTES,
        )
        raise TranscriptionError(
            f"audio file too large for Groq ({file_size} bytes > "
            f"{_MAX_FILE_BYTES}); transcoding would be needed",
            is_retryable=False,
        )

    config = get_config()
    if not config.GROQ_API_KEY:
        log.error(
            "transcribe failed | likely_cause=GROQ_API_KEY env var not set "
            "(check backend/.env locally or Render env vars in production)"
        )
        raise TranscriptionError(
            "GROQ_API_KEY not configured", is_retryable=False
        )

    client = Groq(api_key=config.GROQ_API_KEY)

    log.info("calling Groq Whisper | model=%s", _WHISPER_MODEL)
    try:
        with open(audio_path, "rb") as fh:
            response = client.audio.transcriptions.create(
                file=(os.path.basename(audio_path), fh.read()),
                model=_WHISPER_MODEL,
                response_format="verbose_json",
                temperature=0.0,
            )
    except RateLimitError as exc:
        log.warning(
            "Groq error | status=429 | retryable=True | likely_cause=free-tier "
            "rate limit hit, will back off | reason=%s",
            exc,
        )
        raise TranscriptionError(
            f"Groq rate limit (HTTP 429): {exc}", is_retryable=True
        ) from exc
    except APITimeoutError as exc:
        log.warning(
            "Groq error | status=timeout | retryable=True | likely_cause=Groq "
            "took too long to respond (server load or large audio) | reason=%s",
            exc,
        )
        raise TranscriptionError(
            f"Groq timeout: {exc}", is_retryable=True
        ) from exc
    except APIConnectionError as exc:
        log.warning(
            "Groq error | status=connection | retryable=True | likely_cause="
            "network blip between worker and Groq (DNS, TLS, or socket reset) "
            "| reason=%s",
            exc,
        )
        raise TranscriptionError(
            f"Groq connection error: {exc}", is_retryable=True
        ) from exc
    except APIError as exc:
        # Groq raises APIError for HTTP 4xx/5xx. 5xx → retry, 4xx → don't.
        status = getattr(exc, "status_code", None)
        is_retryable = bool(status and status >= 500)
        # Specific 4xx causes worth surfacing directly:
        if status == 401:
            cause = "invalid GROQ_API_KEY (regenerate at console.groq.com)"
        elif status == 400:
            cause = "Groq rejected the request — likely unsupported audio codec or malformed file"
        elif status == 413:
            cause = "audio payload too large (Groq enforces 25 MB)"
        elif status and status >= 500:
            cause = "Groq server-side issue, will retry"
        else:
            cause = "Groq client-side error, NOT retrying"
        log.error(
            "Groq error | status=%s | retryable=%s | likely_cause=%s | reason=%s",
            status,
            is_retryable,
            cause,
            exc,
        )
        raise TranscriptionError(
            f"Groq API error (HTTP {status}): {cause}: {exc}",
            is_retryable=is_retryable,
        ) from exc

    # Extract fields from the verbose_json response. The Groq SDK returns
    # an object with .text, .language, .duration; we tolerate dict shape too
    # in case the SDK changes.
    text = _attr(response, "text", default="") or ""
    language = _attr(response, "language", default=None)
    duration = _attr(response, "duration", default=None)
    try:
        duration_seconds = float(duration) if duration is not None else None
    except (TypeError, ValueError):
        duration_seconds = None

    transcript = text.strip()
    has_audio = bool(transcript)

    log.info(
        "transcription done | language=%s | duration=%ss | chars=%d | has_audio=%s",
        language,
        duration_seconds,
        len(transcript),
        has_audio,
    )
    if not has_audio:
        log.info("Whisper returned empty text — treating as music-only / silent reel")

    return TranscriptionResult(
        text=transcript,
        has_audio=has_audio,
        language=language,
        duration_seconds=duration_seconds,
        model=_WHISPER_MODEL,
    )


def _attr(obj, name: str, default=None):
    """Read ``name`` whether ``obj`` is a Pydantic model or a dict."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _bound_logger(reel_id: str) -> logging.LoggerAdapter:
    return logging.LoggerAdapter(logger, {"reel_id": reel_id})


# ---------------------------------------------------------------------------
# CLI for ad-hoc testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )

    if len(sys.argv) < 2:
        print("usage: python -m services.transcriber <audio_path> [reel_id]")
        sys.exit(2)

    cli_path = sys.argv[1]
    cli_reel_id = sys.argv[2] if len(sys.argv) > 2 else "cli-test"
    cli_result = transcribe_audio(cli_path, cli_reel_id)

    print("\n--- result ---")
    print(f"language:  {cli_result.language}")
    print(f"duration:  {cli_result.duration_seconds}s")
    print(f"has_audio: {cli_result.has_audio}")
    print(f"transcript:\n{cli_result.text}")
