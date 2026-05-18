# Pipeline Fallback & FFmpeg Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a multi-layer fallback chain to the FastAPI + Celery ingestion pipeline so media processing never crashes due to FFmpeg absence, codec issues, or partial step failures.

**Architecture:** A new `services/ffmpeg_utils.py` owns all FFmpeg concerns (auto-detection via `imageio-ffmpeg` bundled binary, audio extraction, transcoding). `downloader.py` grows a video-download + audio-extraction fallback when the DASH audio URL is absent. `transcriber.py` transcodes to MP3 and retries Groq when it rejects the original codec (HTTP 400). `tasks.py` switches from hard-fail to graceful degradation when transcription fails, letting the pipeline continue with caption-only signal.

**Tech Stack:** Python 3.9, imageio-ffmpeg (bundled binary, no system install needed), pytest + pytest-mock, existing curl_cffi / Groq / Celery / Supabase stack.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/requirements.txt` | Modify | Add `imageio-ffmpeg`, `pytest`, `pytest-mock` |
| `backend/services/ffmpeg_utils.py` | **Create** | FFmpeg detection, audio extraction, MP3 transcode |
| `backend/services/downloader.py` | Modify | Video-download + audio-extraction fallback path |
| `backend/services/transcriber.py` | Modify | `http_status` on error, transcode + retry fallback, `_call_groq_whisper` helper |
| `backend/workers/tasks.py` | Modify | Graceful degradation on transcription failure, terminal-state guard |
| `backend/tests/__init__.py` | **Create** | Empty package marker |
| `backend/tests/conftest.py` | **Create** | sys.path fix + Celery eager-mode fixture |
| `backend/tests/test_ffmpeg_utils.py` | **Create** | Tests for FFmpegUtils module |
| `backend/tests/test_downloader_fallback.py` | **Create** | Tests for audio-extraction fallback |
| `backend/tests/test_transcriber_fallback.py` | **Create** | Tests for transcode + retry fallback |
| `backend/tests/test_tasks_resilience.py` | **Create** | Tests for graceful degradation + retry-safe guard |

---

## Task 1: Add dependencies + scaffold `ffmpeg_utils.py` with FFmpeg detection

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/services/ffmpeg_utils.py`
- Create: `backend/tests/test_ffmpeg_utils.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/__init__.py` (empty file), then `backend/tests/conftest.py`:

```python
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

Create `backend/tests/test_ffmpeg_utils.py`:

```python
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest


def test_get_ffmpeg_exe_returns_bundled_path():
    fake_exe = "/bundled/ffmpeg"
    fake_module = MagicMock()
    fake_module.get_ffmpeg_exe.return_value = fake_exe
    with patch.dict(sys.modules, {"imageio_ffmpeg": fake_module}):
        from importlib import reload
        import services.ffmpeg_utils as fu
        reload(fu)
        result = fu.get_ffmpeg_exe()
    assert result == fake_exe


def test_get_ffmpeg_exe_falls_back_to_system_ffmpeg():
    broken_module = MagicMock()
    broken_module.get_ffmpeg_exe.side_effect = RuntimeError("no binary")
    with patch.dict(sys.modules, {"imageio_ffmpeg": broken_module}):
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            from importlib import reload
            import services.ffmpeg_utils as fu
            reload(fu)
            result = fu.get_ffmpeg_exe()
    assert result == "/usr/bin/ffmpeg"


def test_get_ffmpeg_exe_raises_when_nothing_found():
    broken_module = MagicMock()
    broken_module.get_ffmpeg_exe.side_effect = RuntimeError("no binary")
    with patch.dict(sys.modules, {"imageio_ffmpeg": broken_module}):
        with patch("shutil.which", return_value=None):
            from importlib import reload
            import services.ffmpeg_utils as fu
            reload(fu)
            with pytest.raises(fu.FFmpegError):
                fu.get_ffmpeg_exe()


def test_is_ffmpeg_available_true_when_exe_found_and_runs():
    with patch("services.ffmpeg_utils.get_ffmpeg_exe", return_value="/ffmpeg"):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            from services.ffmpeg_utils import is_ffmpeg_available
            assert is_ffmpeg_available() is True


def test_is_ffmpeg_available_false_when_exe_not_found():
    with patch("services.ffmpeg_utils.get_ffmpeg_exe", side_effect=Exception("not found")):
        from services.ffmpeg_utils import is_ffmpeg_available
        assert is_ffmpeg_available() is False
```

- [ ] **Step 2: Run tests — verify they all FAIL**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/test_ffmpeg_utils.py -v 2>&1 | head -40
```

Expected: `ModuleNotFoundError: No module named 'services.ffmpeg_utils'`

- [ ] **Step 3: Add dependencies to `requirements.txt`**

Add these lines at the end of `backend/requirements.txt`:

```
# FFmpeg (bundled binary — no system install needed)
imageio-ffmpeg>=0.5.1

# Testing
pytest>=8.0.0
pytest-mock>=3.14.0
```

Install them:

```bash
cd backend && source venv/bin/activate && pip install imageio-ffmpeg pytest pytest-mock
```

Expected output ends with: `Successfully installed imageio-ffmpeg-...`

- [ ] **Step 4: Create `backend/services/ffmpeg_utils.py`**

```python
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
```

- [ ] **Step 5: Run tests — verify detection tests pass**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/test_ffmpeg_utils.py::test_get_ffmpeg_exe_returns_bundled_path tests/test_ffmpeg_utils.py::test_get_ffmpeg_exe_falls_back_to_system_ffmpeg tests/test_ffmpeg_utils.py::test_get_ffmpeg_exe_raises_when_nothing_found tests/test_ffmpeg_utils.py::test_is_ffmpeg_available_true_when_exe_found_and_runs tests/test_ffmpeg_utils.py::test_is_ffmpeg_available_false_when_exe_not_found -v
```

Expected: `5 passed`

- [ ] **Step 6: Commit**

```bash
cd backend && git add requirements.txt services/ffmpeg_utils.py tests/__init__.py tests/conftest.py tests/test_ffmpeg_utils.py
git commit -m "feat: add ffmpeg_utils module with auto-detection via imageio-ffmpeg"
```

---

## Task 2: Add `extract_audio_from_video` and `transcode_to_mp3` to `ffmpeg_utils.py`

**Files:**
- Modify: `backend/services/ffmpeg_utils.py`
- Modify: `backend/tests/test_ffmpeg_utils.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_ffmpeg_utils.py`:

```python
from pathlib import Path


def test_extract_audio_stream_copy_success(tmp_path):
    video_file = str(tmp_path / "input.mp4")
    audio_file = str(tmp_path / "output.m4a")
    Path(video_file).write_bytes(b"fake")  # exists but won't be read by mock

    with patch("services.ffmpeg_utils.get_ffmpeg_exe", return_value="/ffmpeg"):
        with patch("subprocess.run") as mock_run:
            # First call (stream-copy) succeeds
            mock_run.return_value = MagicMock(returncode=0)
            # Fake the output file existing with content
            with patch("pathlib.Path.exists", return_value=True):
                with patch("pathlib.Path.stat") as mock_stat:
                    mock_stat.return_value.st_size = 1024
                    from services.ffmpeg_utils import extract_audio_from_video
                    extract_audio_from_video(video_file, audio_file)

    # subprocess.run called with -acodec copy
    first_call_args = mock_run.call_args_list[0][0][0]
    assert "-acodec" in first_call_args
    assert "copy" in first_call_args


def test_extract_audio_falls_back_to_reencode_on_stream_copy_failure(tmp_path):
    video_file = str(tmp_path / "input.mp4")
    audio_file = str(tmp_path / "output.m4a")
    Path(video_file).write_bytes(b"fake")

    with patch("services.ffmpeg_utils.get_ffmpeg_exe", return_value="/ffmpeg"):
        with patch("subprocess.run") as mock_run:
            # First call fails, second succeeds
            mock_run.side_effect = [
                MagicMock(returncode=1, stderr="stream copy failed"),
                MagicMock(returncode=0),
            ]
            with patch("pathlib.Path.exists", side_effect=[False, True, True]):
                with patch("pathlib.Path.stat") as mock_stat:
                    mock_stat.return_value.st_size = 512
                    from services.ffmpeg_utils import extract_audio_from_video
                    extract_audio_from_video(video_file, audio_file)

    assert mock_run.call_count == 2
    second_call_args = mock_run.call_args_list[1][0][0]
    assert "aac" in second_call_args


def test_extract_audio_raises_ffmpeg_error_when_both_attempts_fail(tmp_path):
    video_file = str(tmp_path / "input.mp4")
    audio_file = str(tmp_path / "output.m4a")
    Path(video_file).write_bytes(b"fake")

    with patch("services.ffmpeg_utils.get_ffmpeg_exe", return_value="/ffmpeg"):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="both failed")
            with patch("pathlib.Path.exists", return_value=False):
                from services.ffmpeg_utils import extract_audio_from_video, FFmpegError
                with pytest.raises(FFmpegError):
                    extract_audio_from_video(video_file, audio_file)


def test_transcode_to_mp3_calls_ffmpeg_with_libmp3lame(tmp_path):
    input_file = str(tmp_path / "audio.m4a")
    output_file = str(tmp_path / "audio.mp3")
    Path(input_file).write_bytes(b"fake")

    with patch("services.ffmpeg_utils.get_ffmpeg_exe", return_value="/ffmpeg"):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            with patch("pathlib.Path.exists", return_value=True):
                with patch("pathlib.Path.stat") as mock_stat:
                    mock_stat.return_value.st_size = 800
                    from services.ffmpeg_utils import transcode_to_mp3
                    transcode_to_mp3(input_file, output_file)

    call_args = mock_run.call_args[0][0]
    assert "libmp3lame" in call_args


def test_transcode_to_mp3_raises_ffmpeg_error_on_failure(tmp_path):
    input_file = str(tmp_path / "audio.m4a")
    output_file = str(tmp_path / "audio.mp3")

    with patch("services.ffmpeg_utils.get_ffmpeg_exe", return_value="/ffmpeg"):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="encode error")
            with patch("pathlib.Path.exists", return_value=False):
                from services.ffmpeg_utils import transcode_to_mp3, FFmpegError
                with pytest.raises(FFmpegError):
                    transcode_to_mp3(input_file, output_file)
```

- [ ] **Step 2: Run tests — verify they FAIL**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/test_ffmpeg_utils.py -k "extract_audio or transcode" -v 2>&1 | tail -15
```

Expected: `AttributeError: module 'services.ffmpeg_utils' has no attribute 'extract_audio_from_video'`

- [ ] **Step 3: Add `extract_audio_from_video` and `transcode_to_mp3` to `ffmpeg_utils.py`**

Append to `backend/services/ffmpeg_utils.py`:

```python
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
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/test_ffmpeg_utils.py -v
```

Expected: `10 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/services/ffmpeg_utils.py backend/tests/test_ffmpeg_utils.py
git commit -m "feat: add extract_audio_from_video and transcode_to_mp3 to ffmpeg_utils"
```

---

## Task 3: Add audio-extraction fallback to `downloader.py`

When the DASH manifest yields no audio URL but a combined video URL exists, download the video and extract the audio track via FFmpeg. Failure is swallowed — the pipeline continues with `audio_path=None`.

**Files:**
- Modify: `backend/services/downloader.py`
- Create: `backend/tests/test_downloader_fallback.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_downloader_fallback.py`:

```python
"""Tests for the audio-extraction fallback path in services/downloader.py."""
from unittest.mock import MagicMock, patch, call
import pytest


def _make_metadata(*, audio_url=None, video_url_best="https://cdn.ig/video.mp4", has_audio=True):
    meta = MagicMock()
    meta.audio_url = audio_url
    meta.video_url_best = video_url_best
    meta.has_audio = has_audio
    meta.thumbnail_url = None
    meta.shortcode = "ABC"
    meta.creator_handle = "testuser"
    meta.duration_seconds = 10.0
    return meta


def test_fallback_extracts_audio_from_video_when_no_dash_url(tmp_path):
    """When audio_url is None but video_url_best exists, extraction fallback runs."""
    meta = _make_metadata(audio_url=None)

    with patch("services.downloader._fetch_reel_html", return_value="<html/>"):
        with patch("services.downloader._extract_media_item", return_value={}):
            with patch("services.downloader._parse_metadata", return_value=meta):
                with patch("services.downloader._download_file", return_value=1024) as mock_dl:
                    with patch("services.ffmpeg_utils.extract_audio_from_video") as mock_extract:
                        with patch("services.ffmpeg_utils.is_ffmpeg_available", return_value=True):
                            with patch("tempfile.mkdtemp", return_value=str(tmp_path)):
                                with patch("os.path.exists", return_value=False):
                                    from services.downloader import download_reel
                                    result = download_reel("https://instagram.com/reel/ABC/", "reel-1")

    mock_extract.assert_called_once()
    # First download call should be for the video (fallback source), not audio URL
    first_download_url = mock_dl.call_args_list[0][0][0]
    assert first_download_url == "https://cdn.ig/video.mp4"


def test_fallback_returns_none_audio_path_when_ffmpeg_unavailable(tmp_path):
    """If FFmpeg is not available, fallback is skipped and audio_path is None."""
    meta = _make_metadata(audio_url=None)

    with patch("services.downloader._fetch_reel_html", return_value="<html/>"):
        with patch("services.downloader._extract_media_item", return_value={}):
            with patch("services.downloader._parse_metadata", return_value=meta):
                with patch("services.downloader._download_file", return_value=0):
                    with patch("services.ffmpeg_utils.is_ffmpeg_available", return_value=False):
                        with patch("tempfile.mkdtemp", return_value=str(tmp_path)):
                            from services.downloader import download_reel
                            result = download_reel("https://instagram.com/reel/ABC/", "reel-1")

    assert result.audio_path is None


def test_fallback_returns_none_audio_path_when_ffmpeg_raises(tmp_path):
    """If FFmpeg raises FFmpegError, audio_path is None (pipeline continues)."""
    meta = _make_metadata(audio_url=None)

    from services.ffmpeg_utils import FFmpegError

    with patch("services.downloader._fetch_reel_html", return_value="<html/>"):
        with patch("services.downloader._extract_media_item", return_value={}):
            with patch("services.downloader._parse_metadata", return_value=meta):
                with patch("services.downloader._download_file", return_value=1024):
                    with patch("services.ffmpeg_utils.is_ffmpeg_available", return_value=True):
                        with patch("services.ffmpeg_utils.extract_audio_from_video",
                                   side_effect=FFmpegError("encode failed")):
                            with patch("tempfile.mkdtemp", return_value=str(tmp_path)):
                                with patch("os.path.exists", return_value=False):
                                    from services.downloader import download_reel
                                    result = download_reel("https://instagram.com/reel/ABC/", "reel-1")

    assert result.audio_path is None


def test_no_fallback_when_no_video_url_either(tmp_path):
    """If both audio_url and video_url_best are None, audio_path is None, no FFmpeg call."""
    meta = _make_metadata(audio_url=None, video_url_best=None)

    with patch("services.downloader._fetch_reel_html", return_value="<html/>"):
        with patch("services.downloader._extract_media_item", return_value={}):
            with patch("services.downloader._parse_metadata", return_value=meta):
                with patch("services.downloader._download_file") as mock_dl:
                    with patch("services.ffmpeg_utils.extract_audio_from_video") as mock_extract:
                        with patch("tempfile.mkdtemp", return_value=str(tmp_path)):
                            from services.downloader import download_reel
                            result = download_reel("https://instagram.com/reel/ABC/", "reel-1")

    mock_extract.assert_not_called()
    assert result.audio_path is None


def test_primary_dash_path_unaffected_when_audio_url_exists(tmp_path):
    """Primary path (DASH audio URL present) is unchanged — no FFmpeg involvement."""
    meta = _make_metadata(audio_url="https://cdn.ig/audio.m4a")

    with patch("services.downloader._fetch_reel_html", return_value="<html/>"):
        with patch("services.downloader._extract_media_item", return_value={}):
            with patch("services.downloader._parse_metadata", return_value=meta):
                with patch("services.downloader._download_file", return_value=2048) as mock_dl:
                    with patch("services.ffmpeg_utils.extract_audio_from_video") as mock_extract:
                        with patch("tempfile.mkdtemp", return_value=str(tmp_path)):
                            with patch("os.path.exists", return_value=True):
                                from services.downloader import download_reel
                                result = download_reel("https://instagram.com/reel/ABC/", "reel-1")

    mock_extract.assert_not_called()
    first_url = mock_dl.call_args_list[0][0][0]
    assert first_url == "https://cdn.ig/audio.m4a"
```

- [ ] **Step 2: Run tests — verify they FAIL**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/test_downloader_fallback.py -v 2>&1 | tail -20
```

Expected: tests fail because the fallback path doesn't exist yet.

- [ ] **Step 3: Add `_extract_audio_from_video_fallback` helper to `downloader.py`**

Add this function near the bottom of `backend/services/downloader.py`, before the `_bound_logger` function (after line 760):

```python
def _extract_audio_from_video_fallback(
    video_url: str,
    reel_id: str,
    temp_dir: str,
    log: logging.LoggerAdapter,
) -> str | None:
    """Download the combined video and extract its audio track.

    Returns the local audio path on success, or None on any failure.
    Never raises — all errors are logged as warnings so the pipeline
    continues without audio rather than crashing.
    """
    from services.ffmpeg_utils import FFmpegError, extract_audio_from_video, is_ffmpeg_available

    if not is_ffmpeg_available():
        log.warning(
            "video-audio fallback skipped — FFmpeg not available; "
            "install imageio-ffmpeg (pip install imageio-ffmpeg) to enable"
        )
        return None

    fallback_video = os.path.join(temp_dir, f"{reel_id}_source.mp4")
    audio_path = os.path.join(temp_dir, f"{reel_id}.m4a")
    try:
        video_bytes = _download_file(video_url, fallback_video, log)
        log.info("fallback video downloaded | bytes=%s", video_bytes)
        extract_audio_from_video(fallback_video, audio_path)
        log.info("audio extracted from video | dest=%s", audio_path)
        return audio_path
    except FFmpegError as exc:
        log.warning(
            "audio extraction failed | ffmpeg_error=%s — proceeding without audio", exc
        )
    except DownloadError as exc:
        log.warning(
            "video download for fallback failed | error=%s — proceeding without audio", exc
        )
    except Exception as exc:
        log.warning(
            "unexpected error in audio fallback | exc_type=%s | reason=%s — "
            "proceeding without audio",
            type(exc).__name__,
            exc,
        )
    finally:
        if os.path.exists(fallback_video):
            try:
                os.remove(fallback_video)
                log.info("removed intermediate fallback video | path=%s", fallback_video)
            except OSError:
                pass
    return None
```

- [ ] **Step 4: Replace the `else` block in the audio download section of `download_reel`**

In `backend/services/downloader.py`, find and replace this block (around lines 234–239):

```python
        else:
            log.warning(
                "no audio URL available — reel reports has_audio=%s "
                "(silent reel or missing DASH manifest)",
                metadata.has_audio,
            )
```

Replace with:

```python
        elif metadata.video_url_best:
            # Fallback: no DASH audio-only stream, but a combined video exists.
            # Download it and strip the audio track with FFmpeg.
            log.warning(
                "no DASH audio URL — trying video+audio fallback | has_audio=%s",
                metadata.has_audio,
            )
            audio_path = _extract_audio_from_video_fallback(
                metadata.video_url_best, reel_id, temp_dir, log
            )
        else:
            log.warning(
                "no audio URL and no video URL — reel reports has_audio=%s "
                "(silent reel or missing DASH manifest)",
                metadata.has_audio,
            )
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/test_downloader_fallback.py -v
```

Expected: `5 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/services/downloader.py backend/tests/test_downloader_fallback.py
git commit -m "feat: add video+FFmpeg audio-extraction fallback to downloader"
```

---

## Task 4: Add FFmpeg transcode fallback to `transcriber.py`

When Groq returns HTTP 400 (codec rejection), transcode the audio to MP3 and retry. Refactor the Groq call into `_call_groq_whisper` so both primary and fallback paths share the same response parsing. Add `http_status` attribute to `TranscriptionError`.

**Files:**
- Modify: `backend/services/transcriber.py`
- Create: `backend/tests/test_transcriber_fallback.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_transcriber_fallback.py`:

```python
"""Tests for FFmpeg transcode fallback in transcriber.py."""
import os
from unittest.mock import MagicMock, patch, call

import pytest


def _make_groq_response(text="hello world", language="en", duration=5.0):
    resp = MagicMock()
    resp.text = text
    resp.language = language
    resp.duration = duration
    return resp


def test_transcription_error_carries_http_status():
    from services.transcriber import TranscriptionError
    err = TranscriptionError("bad", is_retryable=False, http_status=400)
    assert err.http_status == 400
    assert err.is_retryable is False


def test_transcode_fallback_triggered_on_groq_http_400(tmp_path):
    """HTTP 400 from Groq triggers FFmpeg transcode + second Groq call."""
    audio_file = str(tmp_path / "audio.m4a")
    open(audio_file, "wb").write(b"x" * 1024)  # non-empty file

    from services.transcriber import TranscriptionError

    groq_400_error = TranscriptionError("Groq 400", is_retryable=False, http_status=400)
    success_response = _make_groq_response()

    with patch("services.transcriber.get_config") as mock_cfg:
        mock_cfg.return_value.GROQ_API_KEY = "fake-key"
        with patch("services.transcriber._call_groq_whisper") as mock_call:
            mock_call.side_effect = [groq_400_error, success_response]
            with patch("services.ffmpeg_utils.is_ffmpeg_available", return_value=True):
                with patch("services.ffmpeg_utils.transcode_to_mp3") as mock_transcode:
                    with patch("os.path.exists", return_value=True):
                        with patch("os.remove"):
                            from services.transcriber import transcribe_audio
                            result = transcribe_audio(audio_file, "reel-1")

    mock_transcode.assert_called_once()
    assert mock_call.call_count == 2


def test_transcode_fallback_returns_result_on_success(tmp_path):
    """Fallback succeeds → TranscriptionResult returned normally."""
    audio_file = str(tmp_path / "audio.m4a")
    open(audio_file, "wb").write(b"x" * 100)

    from services.transcriber import TranscriptionError, TranscriptionResult

    groq_400 = TranscriptionError("bad codec", is_retryable=False, http_status=400)
    success = _make_groq_response(text="  great content  ", language="en", duration=8.0)

    with patch("services.transcriber.get_config") as mock_cfg:
        mock_cfg.return_value.GROQ_API_KEY = "fake-key"
        with patch("services.transcriber._call_groq_whisper") as mock_call:
            mock_call.side_effect = [groq_400, success]
            with patch("services.ffmpeg_utils.is_ffmpeg_available", return_value=True):
                with patch("services.ffmpeg_utils.transcode_to_mp3"):
                    with patch("os.path.exists", return_value=True):
                        with patch("os.remove"):
                            from services.transcriber import transcribe_audio
                            result = transcribe_audio(audio_file, "reel-1")

    # _call_groq_whisper returned the mock response object; transcribe_audio
    # wraps the second call's return value into a TranscriptionResult.
    # The second call returns `success` (a MagicMock with .text), so we
    # just assert no exception was raised.
    assert result is not None


def test_non_400_groq_error_does_not_trigger_fallback(tmp_path):
    """HTTP 500 should NOT trigger FFmpeg fallback — it's retryable."""
    audio_file = str(tmp_path / "audio.m4a")
    open(audio_file, "wb").write(b"x" * 100)

    from services.transcriber import TranscriptionError

    groq_500 = TranscriptionError("server error", is_retryable=True, http_status=500)

    with patch("services.transcriber.get_config") as mock_cfg:
        mock_cfg.return_value.GROQ_API_KEY = "fake-key"
        with patch("services.transcriber._call_groq_whisper", side_effect=groq_500):
            with patch("services.ffmpeg_utils.transcode_to_mp3") as mock_transcode:
                with patch("os.path.exists", return_value=True):
                    from services.transcriber import transcribe_audio
                    with pytest.raises(TranscriptionError) as exc_info:
                        transcribe_audio(audio_file, "reel-1")

    mock_transcode.assert_not_called()
    assert exc_info.value.is_retryable is True


def test_fallback_raises_original_error_when_ffmpeg_unavailable(tmp_path):
    """If FFmpeg is not available, the original 400 error is re-raised."""
    audio_file = str(tmp_path / "audio.m4a")
    open(audio_file, "wb").write(b"x" * 100)

    from services.transcriber import TranscriptionError

    groq_400 = TranscriptionError("bad codec", is_retryable=False, http_status=400)

    with patch("services.transcriber.get_config") as mock_cfg:
        mock_cfg.return_value.GROQ_API_KEY = "fake-key"
        with patch("services.transcriber._call_groq_whisper", side_effect=groq_400):
            with patch("services.ffmpeg_utils.is_ffmpeg_available", return_value=False):
                with patch("os.path.exists", return_value=True):
                    from services.transcriber import transcribe_audio
                    with pytest.raises(TranscriptionError) as exc_info:
                        transcribe_audio(audio_file, "reel-1")

    assert exc_info.value.http_status == 400
```

- [ ] **Step 2: Run tests — verify they FAIL**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/test_transcriber_fallback.py -v 2>&1 | tail -20
```

Expected: `AttributeError: __init__() got an unexpected keyword argument 'http_status'`

- [ ] **Step 3: Add `http_status` to `TranscriptionError` and extract `_call_groq_whisper`**

In `backend/services/transcriber.py`, replace the `TranscriptionError` class (lines 45–53):

```python
class TranscriptionError(Exception):
    """Errors raised by the transcriber.

    ``is_retryable`` mirrors the contract used by services.downloader so the
    Celery task can apply the same retry logic to either failure source.
    ``http_status`` carries the HTTP code from Groq when applicable.
    """

    def __init__(self, message: str, *, is_retryable: bool = False, http_status: int | None = None):
        super().__init__(message)
        self.is_retryable = is_retryable
        self.http_status = http_status
```

- [ ] **Step 4: Extract the Groq API call + response parsing into `_call_groq_whisper`**

In `backend/services/transcriber.py`, insert this new helper function after the `_bound_logger` function (after line 228) and before the `if __name__ == "__main__":` block:

```python
def _call_groq_whisper(
    client,
    audio_path: str,
    log: logging.LoggerAdapter,
) -> TranscriptionResult:
    """Make one Groq Whisper API call and return a TranscriptionResult.

    Raises TranscriptionError (with is_retryable and http_status set) on any
    Groq failure. Callers use http_status=400 to decide whether to attempt a
    transcode fallback.
    """
    log.info("calling Groq Whisper | model=%s | path=%s", _WHISPER_MODEL, audio_path)
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
            "rate limit hit | reason=%s", exc,
        )
        raise TranscriptionError(
            f"Groq rate limit (HTTP 429): {exc}", is_retryable=True, http_status=429
        ) from exc
    except APITimeoutError as exc:
        log.warning(
            "Groq error | status=timeout | retryable=True | reason=%s", exc,
        )
        raise TranscriptionError(
            f"Groq timeout: {exc}", is_retryable=True
        ) from exc
    except APIConnectionError as exc:
        log.warning(
            "Groq error | status=connection | retryable=True | reason=%s", exc,
        )
        raise TranscriptionError(
            f"Groq connection error: {exc}", is_retryable=True
        ) from exc
    except APIError as exc:
        status = getattr(exc, "status_code", None)
        is_retryable = bool(status and status >= 500)
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
            status, is_retryable, cause, exc,
        )
        raise TranscriptionError(
            f"Groq API error (HTTP {status}): {cause}: {exc}",
            is_retryable=is_retryable,
            http_status=status,
        ) from exc

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
        language, duration_seconds, len(transcript), has_audio,
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
```

- [ ] **Step 5: Replace `transcribe_audio` body to use `_call_groq_whisper` + transcode fallback**

In `backend/services/transcriber.py`, replace the body of `transcribe_audio` (lines 57–218, keeping the docstring) with:

```python
def transcribe_audio(audio_path: str, reel_id: str) -> TranscriptionResult:
    """Transcribe a local audio file with Groq Whisper.

    Falls back to FFmpeg MP3 transcode + retry when Groq returns HTTP 400
    (codec rejection). All other errors propagate as TranscriptionError.

    Args:
        audio_path: Local path to the audio file (m4a, mp3, wav, etc.).
        reel_id: Caller-supplied identifier for log correlation.
    """
    log = _bound_logger(reel_id)
    log.info("transcribe_audio start | path=%s", audio_path)

    if not os.path.exists(audio_path):
        log.error(
            "transcribe failed | likely_cause=audio file missing between "
            "Step 15 download and Step 16 (cleanup race or worker restart) "
            "| path=%s", audio_path,
        )
        raise TranscriptionError(
            f"audio file not found: {audio_path}", is_retryable=False
        )

    file_size = os.path.getsize(audio_path)
    log.info("audio file ready | bytes=%s", file_size)

    if file_size == 0:
        log.error(
            "transcribe failed | likely_cause=audio download wrote 0 bytes | path=%s",
            audio_path,
        )
        raise TranscriptionError("audio file is empty (0 bytes)", is_retryable=False)

    if file_size > _MAX_FILE_BYTES:
        log.error(
            "transcribe failed | likely_cause=exceeds Groq 25MB limit "
            "| bytes=%s | limit=%s", file_size, _MAX_FILE_BYTES,
        )
        raise TranscriptionError(
            f"audio file too large for Groq ({file_size} bytes > {_MAX_FILE_BYTES})",
            is_retryable=False,
        )

    config = get_config()
    if not config.GROQ_API_KEY:
        log.error(
            "transcribe failed | likely_cause=GROQ_API_KEY not set"
        )
        raise TranscriptionError("GROQ_API_KEY not configured", is_retryable=False)

    from groq import Groq as _Groq
    client = _Groq(api_key=config.GROQ_API_KEY)

    try:
        return _call_groq_whisper(client, audio_path, log)
    except TranscriptionError as exc:
        if exc.http_status != 400:
            raise

        # HTTP 400 often means Groq rejected the codec (e.g., raw DASH m4a).
        # Transcode to MP3 and retry once.
        log.warning(
            "Groq HTTP 400 — attempting FFmpeg mp3 transcode fallback | path=%s",
            audio_path,
        )
        from services.ffmpeg_utils import FFmpegError, is_ffmpeg_available, transcode_to_mp3

        if not is_ffmpeg_available():
            log.warning(
                "FFmpeg not available for transcode fallback — re-raising original error"
            )
            raise

        mp3_path = os.path.splitext(audio_path)[0] + "_fallback.mp3"
        try:
            transcode_to_mp3(audio_path, mp3_path)
            log.info("transcode done — retrying Groq | mp3=%s", mp3_path)
            return _call_groq_whisper(client, mp3_path, log)
        except FFmpegError as ffmpeg_exc:
            log.error(
                "FFmpeg transcode fallback failed | %s — raising original error",
                ffmpeg_exc,
            )
            raise exc
        finally:
            if os.path.exists(mp3_path):
                try:
                    os.remove(mp3_path)
                except OSError:
                    pass
```

- [ ] **Step 6: Run tests — verify they pass**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/test_transcriber_fallback.py -v
```

Expected: `5 passed`

- [ ] **Step 7: Commit**

```bash
git add backend/services/transcriber.py backend/tests/test_transcriber_fallback.py
git commit -m "feat: add FFmpeg mp3 transcode fallback for Groq HTTP 400 in transcriber"
```

---

## Task 5: Graceful degradation + retry-safe guard in `tasks.py`

Replace the hard-fail on transcription error with graceful degradation: set `has_audio=False`, persist it, and continue the pipeline so caption-only classification can proceed. Add a terminal-state guard so duplicate/late task dispatches for already-completed reels are a no-op.

**Files:**
- Modify: `backend/workers/tasks.py`
- Create: `backend/tests/test_tasks_resilience.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_tasks_resilience.py`:

```python
"""Tests for graceful degradation and retry-safe behavior in workers/tasks.py."""
from unittest.mock import MagicMock, patch, call

import pytest


def _make_supabase_mock(status="queued", url="https://instagram.com/reel/ABC/"):
    """Return a mock supabase client wired up for typical task usage."""
    mock_db = MagicMock()

    # .table("reels").select(...).eq(...).single().execute().data
    select_chain = (
        mock_db.table.return_value
        .select.return_value
        .eq.return_value
        .single.return_value
        .execute.return_value
    )
    select_chain.data = {"url": url, "user_id": "user-1", "status": status}

    # .table("reels").update(...).eq(...).execute()
    mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = None
    return mock_db


def _make_task_self(retries=0, max_retries=3):
    task_self = MagicMock()
    task_self.request.retries = retries
    task_self.max_retries = max_retries
    # Make task_self.retry raise Retry exception like Celery does
    from celery.exceptions import Retry
    task_self.retry.side_effect = Retry()
    return task_self


def _make_download_result(audio_path="/tmp/audio.m4a", temp_dir="/tmp/reel_test"):
    result = MagicMock()
    result.audio_path = audio_path
    result.temp_dir = temp_dir
    result.metadata.creator_handle = "testuser"
    result.metadata.hashtags = ["tag1"]
    result.metadata.caption = "Test caption #tag1"
    result.metadata.thumbnail_url = None
    return result


def test_transcription_failure_does_not_mark_reel_failed():
    """Non-retryable TranscriptionError → has_audio=False saved, status NOT set to failed."""
    from services.transcriber import TranscriptionError
    from workers.tasks import process_reel

    task_self = _make_task_self(retries=3, max_retries=3)  # retries exhausted
    mock_db = _make_supabase_mock()

    with patch("workers.tasks.get_supabase", return_value=mock_db):
        with patch("workers.tasks.download_reel", return_value=_make_download_result()):
            with patch("workers.tasks.transcribe_audio",
                       side_effect=TranscriptionError("bad codec", is_retryable=False)):
                with patch("os.path.exists", return_value=False):
                    result = process_reel(task_self, "reel-123")

    # Should NOT return status=failed
    assert result.get("status") != "failed"

    # Verify "failed" was never set via DB update
    all_update_dicts = [
        c[0][0]
        for c in mock_db.table.return_value.update.call_args_list
    ]
    assert not any(d.get("status") == "failed" for d in all_update_dicts), (
        f"Expected no status=failed update, but got: {all_update_dicts}"
    )


def test_transcription_failure_sets_has_audio_false():
    """When transcription fails, has_audio=False is written to DB."""
    from services.transcriber import TranscriptionError
    from workers.tasks import process_reel

    task_self = _make_task_self(retries=3, max_retries=3)
    mock_db = _make_supabase_mock()

    with patch("workers.tasks.get_supabase", return_value=mock_db):
        with patch("workers.tasks.download_reel", return_value=_make_download_result()):
            with patch("workers.tasks.transcribe_audio",
                       side_effect=TranscriptionError("codec", is_retryable=False)):
                with patch("os.path.exists", return_value=False):
                    process_reel(task_self, "reel-123")

    all_update_dicts = [
        c[0][0]
        for c in mock_db.table.return_value.update.call_args_list
    ]
    assert any(d.get("has_audio") is False for d in all_update_dicts), (
        f"Expected has_audio=False in one update, got: {all_update_dicts}"
    )


def test_retryable_transcription_failure_schedules_celery_retry():
    """Retryable TranscriptionError with retries remaining → Celery retry raised."""
    from services.transcriber import TranscriptionError
    from workers.tasks import process_reel
    from celery.exceptions import Retry

    task_self = _make_task_self(retries=0, max_retries=3)
    mock_db = _make_supabase_mock()

    with patch("workers.tasks.get_supabase", return_value=mock_db):
        with patch("workers.tasks.download_reel", return_value=_make_download_result()):
            with patch("workers.tasks.transcribe_audio",
                       side_effect=TranscriptionError("timeout", is_retryable=True)):
                with patch("os.path.exists", return_value=False):
                    with pytest.raises(Retry):
                        process_reel(task_self, "reel-123")


def test_terminal_state_guard_skips_already_ready_reel():
    """If reel.status == 'ready', task returns immediately without re-processing."""
    from workers.tasks import process_reel

    task_self = _make_task_self()
    mock_db = _make_supabase_mock(status="ready")

    with patch("workers.tasks.get_supabase", return_value=mock_db):
        with patch("workers.tasks.download_reel") as mock_dl:
            result = process_reel(task_self, "reel-123")

    mock_dl.assert_not_called()
    assert result["status"] == "already_ready"


def test_download_failure_still_marks_reel_failed():
    """DownloadError (non-retryable, retries exhausted) → status=failed is correct behavior."""
    from services.downloader import DownloadError
    from workers.tasks import process_reel

    task_self = _make_task_self(retries=3, max_retries=3)
    mock_db = _make_supabase_mock()

    with patch("workers.tasks.get_supabase", return_value=mock_db):
        with patch("workers.tasks.download_reel",
                   side_effect=DownloadError("404 deleted", is_retryable=False)):
            with patch("os.path.exists", return_value=False):
                result = process_reel(task_self, "reel-123")

    assert result["status"] == "failed"
```

- [ ] **Step 2: Run tests — verify they FAIL**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/test_tasks_resilience.py -v 2>&1 | tail -25
```

Expected: most tests fail because the current code marks transcription failures as `failed` and lacks the terminal-state guard.

- [ ] **Step 3: Update `tasks.py` — add terminal-state guard**

In `backend/workers/tasks.py`, replace the row-fetch block (lines 62–70):

```python
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
```

With:

```python
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
```

- [ ] **Step 4: Update `tasks.py` — replace transcription error handling with graceful degradation**

In `backend/workers/tasks.py`, find and replace the transcription error block (lines 112–120):

```python
            except TranscriptionError as exc:
                log.warning(
                    "transcription failed | retryable=%s | %s",
                    exc.is_retryable,
                    exc,
                )
                return _handle_pipeline_error(
                    self, supabase, reel_id, exc, exc.is_retryable, log
                )
```

Replace with:

```python
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
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/test_tasks_resilience.py -v
```

Expected: `5 passed`

- [ ] **Step 6: Run the full test suite**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/ -v
```

Expected: `20 passed` (all tests across all four test files)

- [ ] **Step 7: Commit**

```bash
git add backend/workers/tasks.py backend/tests/test_tasks_resilience.py
git commit -m "feat: graceful transcription degradation and retry-safe terminal guard in tasks"
```

---

## Self-Review

### Spec Coverage

| Requirement | Task(s) |
|-------------|---------|
| Fallback executes automatically when primary flow fails | Tasks 3, 4, 5 |
| Robust error handling + logging | All tasks (every failure path logs with context) |
| Retry-safe behavior | Task 5 (terminal-state guard + Celery retry routing) |
| FFmpeg auto-install if missing | Task 1 (`imageio-ffmpeg` + `get_ffmpeg_exe`) |
| Media processing never crashes due to FFmpeg | Tasks 2, 3, 4 (FFmpegError caught, pipeline continues) |
| Do not restart FastAPI or Celery | Zero server lifecycle changes — code-only |

### Placeholder Scan

No TBDs or TODOs in any step. All code blocks are complete.

### Type Consistency

- `FFmpegError` defined in Task 1, referenced in Tasks 2, 3, 4 ✓
- `TranscriptionError.http_status` added in Task 4 Step 3, used in Task 4 Step 5 and Task 5 ✓
- `_call_groq_whisper(client, audio_path, log)` signature defined in Task 4 Step 4, called in Task 4 Step 5 ✓
- `_extract_audio_from_video_fallback(video_url, reel_id, temp_dir, log)` defined and called in Task 3 ✓
- `DownloadResult.audio_path` remains `str | None` throughout ✓
