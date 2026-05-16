"""FFmpeg auto-detection and media utilities.

Uses imageio-ffmpeg's bundled binary first (available after pip install,
no system dependency), then falls back to a system ffmpeg on PATH.
"""
from __future__ import annotations

import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)


class FFmpegError(Exception):
    def __init__(self, message: str, *, is_retryable: bool = False):
        super().__init__(message)
        self.is_retryable = is_retryable


def get_ffmpeg_exe() -> str:
    """Return path to an ffmpeg binary.

    Priority:
      1. imageio-ffmpeg bundled binary (installed via pip, cross-platform)
      2. System ffmpeg on PATH

    Raises FFmpegError if neither is available.
    """
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        logger.debug("using imageio-ffmpeg bundled binary | path=%s", exe)
        return exe
    except Exception as exc:
        logger.debug("imageio-ffmpeg unavailable: %s", exc)

    system = shutil.which("ffmpeg")
    if system:
        logger.debug("using system ffmpeg | path=%s", system)
        return system

    raise FFmpegError(
        "ffmpeg not found — run: pip install imageio-ffmpeg  "
        "(or install ffmpeg via your OS package manager)",
        is_retryable=False,
    )


def is_ffmpeg_available() -> bool:
    """Return True if an ffmpeg binary can be located and executed."""
    try:
        exe = get_ffmpeg_exe()
        result = subprocess.run(
            [exe, "-version"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


from pathlib import Path


def extract_audio_from_video(video_path: str, output_path: str) -> None:
    """Extract audio track from a video file.

    Tries stream-copy first (no re-encode, fastest). If the container
    is incompatible, re-encodes to AAC 128kbps. Raises FFmpegError if
    both attempts fail.
    """
    exe = get_ffmpeg_exe()
    out = Path(output_path)

    # Attempt 1: stream copy (lossless, fast)
    cmd_copy = [exe, "-y", "-i", video_path, "-vn", "-acodec", "copy", output_path]
    logger.info("extracting audio | src=%s | dst=%s | mode=stream-copy", video_path, output_path)
    result = subprocess.run(cmd_copy, capture_output=True, text=True, timeout=120)
    if result.returncode == 0 and out.exists() and out.stat().st_size > 0:
        logger.info("audio extraction done | bytes=%d", out.stat().st_size)
        return

    logger.warning(
        "stream-copy failed (returncode=%d) — retrying with AAC re-encode | stderr=...%s",
        result.returncode,
        (result.stderr or "")[-300:],
    )

    # Attempt 2: re-encode to AAC
    cmd_aac = [exe, "-y", "-i", video_path, "-vn", "-acodec", "aac", "-b:a", "128k", output_path]
    result2 = subprocess.run(cmd_aac, capture_output=True, text=True, timeout=120)
    if result2.returncode == 0 and out.exists() and out.stat().st_size > 0:
        logger.info("audio extraction done (re-encoded) | bytes=%d", out.stat().st_size)
        return

    raise FFmpegError(
        f"audio extraction failed for {video_path}: {(result2.stderr or '')[-400:]}",
        is_retryable=False,
    )


def transcode_to_mp3(input_path: str, output_path: str) -> None:
    """Transcode any audio file to MP3 128kbps.

    Used as a Groq codec-rejection fallback — Groq HTTP 400 can mean the
    original container (e.g. raw m4a from DASH) is not accepted; mp3 always is.
    Raises FFmpegError on failure.
    """
    exe = get_ffmpeg_exe()
    out = Path(output_path)
    cmd = [exe, "-y", "-i", input_path, "-acodec", "libmp3lame", "-b:a", "128k", output_path]

    logger.info("transcoding to mp3 | src=%s | dst=%s", input_path, output_path)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode == 0 and out.exists() and out.stat().st_size > 0:
        logger.info("transcode done | bytes=%d", out.stat().st_size)
        return

    raise FFmpegError(
        f"transcode to mp3 failed for {input_path}: {(result.stderr or '')[-400:]}",
        is_retryable=False,
    )
