"""One-shot end-to-end tester: paste a reel URL, get metadata JSON + transcript.

Usage:
    cd backend && source venv/bin/activate
    python scripts/test_reel.py "<reel-url>"

What it does:
    1. Downloads the reel (services.downloader) — runs the full extraction
       pipeline including the FFmpeg audio-extraction fallback when needed.
    2. Transcribes the audio (services.transcriber) — Groq Whisper, with the
       mp3 transcode fallback on HTTP 400.
    3. Prints a JSON report on stdout.
    4. Cleans up the temp dir (audio + thumbnail files) on exit.

Exit codes:
    0 — success (download + transcribe both worked)
    1 — download failed
    2 — transcription failed (download succeeded; partial result still printed)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid

# Make `services` importable when running from backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.downloader import DownloadError, download_reel
from services.transcriber import TranscriptionError, transcribe_audio


def main() -> int:
    parser = argparse.ArgumentParser(description="End-to-end reel tester")
    parser.add_argument("url", help="Instagram reel URL")
    parser.add_argument(
        "--reel-id",
        default=f"cli-{uuid.uuid4().hex[:8]}",
        help="ID used to namespace local files (default: random)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show INFO-level logs from the pipeline as it runs",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )

    try:
        result = download_reel(args.url, args.reel_id, download_video=False)
    except DownloadError as exc:
        print(json.dumps({"status": "download_failed", "error": str(exc)}, indent=2))
        return 1

    meta = result.metadata
    report: dict = {
        "status": "ok",
        "url": args.url,
        "reel_id": args.reel_id,
        "metadata": {
            "shortcode": meta.shortcode,
            "creator_handle": meta.creator_handle,
            "creator_verified": meta.user.is_verified,
            "caption": meta.caption,
            "hashtags": meta.hashtags,
            "mentions": meta.mentions,
            "duration_seconds": meta.duration_seconds,
            "has_audio": meta.has_audio,
            "audio_codec": meta.audio_codec,
            "audio_bandwidth": meta.audio_bandwidth,
            "like_count": meta.like_count,
            "comment_count": meta.comment_count,
            "view_count": meta.view_count,
            "music": {
                "type": meta.music.audio_type,
                "title": meta.music.title,
                "artist": meta.music.artist,
            } if meta.music else None,
            "thumbnail_url": meta.thumbnail_url,
        },
        "local_files": {
            "audio_path": result.audio_path,
            "thumbnail_path": result.thumbnail_path,
            "temp_dir": result.temp_dir,
        },
        "transcription": None,
    }

    exit_code = 0
    try:
        if result.audio_path:
            transcription = transcribe_audio(result.audio_path, args.reel_id)
            report["transcription"] = {
                "language": transcription.language,
                "duration_seconds": transcription.duration_seconds,
                "has_audio": transcription.has_audio,
                "model": transcription.model,
                "char_count": len(transcription.text),
                "text": transcription.text,
            }
        else:
            report["transcription"] = {
                "skipped": "no audio extracted from this reel",
            }
    except TranscriptionError as exc:
        report["transcription"] = {
            "status": "failed",
            "is_retryable": exc.is_retryable,
            "http_status": exc.http_status,
            "error": str(exc),
        }
        exit_code = 2
    finally:
        _cleanup_temp_dir(result.temp_dir)

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return exit_code


def _cleanup_temp_dir(temp_dir: str) -> None:
    if not temp_dir or not os.path.exists(temp_dir):
        return
    try:
        for name in os.listdir(temp_dir):
            try:
                os.remove(os.path.join(temp_dir, name))
            except OSError:
                pass
        os.rmdir(temp_dir)
    except OSError:
        pass


if __name__ == "__main__":
    sys.exit(main())
