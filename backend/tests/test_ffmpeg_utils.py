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
