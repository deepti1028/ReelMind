import json
import pytest
from services.downloader import DownloadError


# ---------------------------------------------------------------------------
# Helpers — build minimal HTML pages
# ---------------------------------------------------------------------------

def _html_with_json_blocks(*payloads):
    """Wrap each dict as a <script type="application/json"> block."""
    blocks = "".join(
        f'<script type="application/json">{json.dumps(p)}</script>'
        for p in payloads
    )
    return f"<html><head>{blocks}</head><body></body></html>"


def _private_user_block():
    """JSON block with user metadata marking account private — no video payload."""
    return {"user": {"pk": "123", "username": "secretuser", "is_private": True}}


def _public_user_block():
    return {"user": {"pk": "456", "username": "publicuser", "is_private": False}}


def _media_block():
    """Minimal valid media block that _extract_media_item can find.

    Must use one of the keys in _SHORTCODE_INFO_KEYS and contain 'video_versions'
    so _extract_media_item's pre-filter passes the block.
    """
    return {
        "xdt_api__v1__media__shortcode__web_info": {
            "items": [{"pk": "999", "video_versions": [{"url": "https://cdn.ig/v.mp4"}]}]
        }
    }


# ---------------------------------------------------------------------------
# Unit tests for _html_signals_private_content
# ---------------------------------------------------------------------------

def test_signals_private_when_is_private_true_in_json_block():
    from services.downloader import _html_signals_private_content
    html = _html_with_json_blocks(_private_user_block())
    assert _html_signals_private_content(html) is True


def test_signals_false_when_is_private_false_in_json_block():
    from services.downloader import _html_signals_private_content
    html = _html_with_json_blocks(_public_user_block())
    assert _html_signals_private_content(html) is False


def test_signals_false_when_no_json_blocks():
    from services.downloader import _html_signals_private_content
    assert _html_signals_private_content("<html><body>nothing here</body></html>") is False


def test_signals_false_when_json_blocks_have_no_is_private_key():
    from services.downloader import _html_signals_private_content
    html = _html_with_json_blocks({"config": {"csrf_token": "abc"}})
    assert _html_signals_private_content(html) is False


def test_signals_true_when_one_of_multiple_blocks_is_private():
    from services.downloader import _html_signals_private_content
    html = _html_with_json_blocks(
        {"config": {"csrf_token": "abc"}},
        _private_user_block(),
        {"unrelated": True},
    )
    assert _html_signals_private_content(html) is True


def test_signals_false_when_media_block_has_no_is_private():
    from services.downloader import _html_signals_private_content
    html = _html_with_json_blocks(_media_block())
    assert _html_signals_private_content(html) is False


# ---------------------------------------------------------------------------
# Integration tests for _extract_media_item error routing
# ---------------------------------------------------------------------------

def test_extract_raises_private_error_when_html_signals_private():
    """No media item + private marker → DownloadError(is_private_content=True)."""
    from services.downloader import _extract_media_item
    import logging
    log = logging.LoggerAdapter(logging.getLogger("test"), {})

    html = _html_with_json_blocks(_private_user_block())
    with pytest.raises(DownloadError) as exc_info:
        _extract_media_item(html, log)

    assert exc_info.value.is_private_content is True
    assert exc_info.value.is_retryable is False


def test_extract_raises_retryable_error_when_no_private_signal():
    """No media item + no private marker → DownloadError(is_retryable=True) (existing behaviour)."""
    from services.downloader import _extract_media_item
    import logging
    log = logging.LoggerAdapter(logging.getLogger("test"), {})

    html = _html_with_json_blocks({"config": {"csrf_token": "abc"}})
    with pytest.raises(DownloadError) as exc_info:
        _extract_media_item(html, log)

    assert exc_info.value.is_retryable is True
    assert exc_info.value.is_private_content is False


def test_extract_returns_item_when_media_present_even_with_private_block():
    """If a valid media item IS found, private marker in other blocks is irrelevant."""
    from services.downloader import _extract_media_item
    import logging
    log = logging.LoggerAdapter(logging.getLogger("test"), {})

    html = _html_with_json_blocks(_private_user_block(), _media_block())
    result = _extract_media_item(html, log)
    assert result["pk"] == "999"
