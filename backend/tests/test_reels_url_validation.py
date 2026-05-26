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


from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from main import app
from api.deps import get_current_user_id


async def _mock_user_id():
    return "user-1"


def test_create_reel_422_for_non_instagram_url():
    app.dependency_overrides[get_current_user_id] = _mock_user_id
    client = TestClient(app)

    with patch("api.v1.reels.notify_invalid_url") as mock_task:
        mock_task.delay = MagicMock()
        response = client.post(
            "/api/v1/reels",
            json={"url": "https://tiktok.com/video/123", "auto_categorise": True},
        )

    app.dependency_overrides.clear()
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["reason"] == "not_instagram"
    assert "Instagram" in detail["message"]
    mock_task.delay.assert_called_once_with("user-1", "not_instagram")


def test_create_reel_422_for_instagram_story():
    app.dependency_overrides[get_current_user_id] = _mock_user_id
    client = TestClient(app)

    with patch("api.v1.reels.notify_invalid_url") as mock_task:
        mock_task.delay = MagicMock()
        response = client.post(
            "/api/v1/reels",
            json={
                "url": "https://www.instagram.com/stories/someuser/123/",
                "auto_categorise": True,
            },
        )

    app.dependency_overrides.clear()
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["reason"] == "not_a_reel"
    mock_task.delay.assert_called_once_with("user-1", "not_a_reel")
