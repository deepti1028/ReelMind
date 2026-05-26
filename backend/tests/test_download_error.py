from services.downloader import DownloadError


def test_download_error_is_private_content_defaults_false():
    err = DownloadError("some error")
    assert err.is_private_content is False


def test_download_error_is_private_content_can_be_set_true():
    err = DownloadError("private", is_private_content=True)
    assert err.is_private_content is True
    assert err.is_retryable is False


def test_download_error_all_flags():
    err = DownloadError("both", is_retryable=True, is_private_content=True)
    assert err.is_retryable is True
    assert err.is_private_content is True
