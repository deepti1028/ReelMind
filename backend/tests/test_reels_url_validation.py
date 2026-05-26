from api.v1.reels import _is_instagram_reel_url


def test_valid_reel_url_with_www():
    assert _is_instagram_reel_url("https://www.instagram.com/reel/ABC123") is None


def test_valid_reel_url_no_www():
    assert _is_instagram_reel_url("https://instagram.com/reel/ABC123") is None


def test_valid_reels_plural_url():
    assert _is_instagram_reel_url("https://www.instagram.com/reels/ABC123") is None


def test_valid_reel_url_with_trailing_slash():
    assert _is_instagram_reel_url("https://www.instagram.com/reel/ABC123/") is None


def test_non_instagram_tiktok():
    assert _is_instagram_reel_url("https://tiktok.com/video/123") == "not_instagram"


def test_non_instagram_youtube():
    assert _is_instagram_reel_url("https://youtube.com/shorts/xyz") == "not_instagram"


def test_instagram_story():
    assert _is_instagram_reel_url("https://www.instagram.com/stories/username/123/") == "not_a_reel"


def test_instagram_post():
    assert _is_instagram_reel_url("https://www.instagram.com/p/ABC123/") == "not_a_reel"


def test_instagram_tv():
    assert _is_instagram_reel_url("https://www.instagram.com/tv/ABC123/") == "not_a_reel"


def test_instagram_profile():
    assert _is_instagram_reel_url("https://www.instagram.com/someuser/") == "not_a_reel"
