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
