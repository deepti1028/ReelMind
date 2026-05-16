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
