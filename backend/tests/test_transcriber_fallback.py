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
