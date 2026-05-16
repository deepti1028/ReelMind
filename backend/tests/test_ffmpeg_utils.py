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
            with patch("pathlib.Path.exists", return_value=True):
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
