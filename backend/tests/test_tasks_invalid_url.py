from unittest.mock import MagicMock, patch


def _make_profiles_db(fcm_token="test-fcm-token"):
    db = MagicMock()
    (
        db.table.return_value
        .select.return_value
        .eq.return_value
        .maybe_single.return_value
        .execute.return_value
        .data
    ) = {"fcm_token": fcm_token}
    return db


def test_notify_invalid_url_not_instagram_sends_push():
    from workers.tasks import notify_invalid_url

    with patch("workers.tasks.get_supabase", return_value=_make_profiles_db()):
        with patch("workers.tasks.send_push_notification") as mock_push:
            notify_invalid_url("user-1", "not_instagram")

    mock_push.assert_called_once()
    kwargs = mock_push.call_args[1]
    assert kwargs["title"] == "Can't save this"
    assert "Instagram" in kwargs["body"]
    assert kwargs["data"]["reason"] == "not_instagram"


def test_notify_invalid_url_not_a_reel_sends_push():
    from workers.tasks import notify_invalid_url

    with patch("workers.tasks.get_supabase", return_value=_make_profiles_db()):
        with patch("workers.tasks.send_push_notification") as mock_push:
            notify_invalid_url("user-1", "not_a_reel")

    mock_push.assert_called_once()
    kwargs = mock_push.call_args[1]
    assert kwargs["title"] == "Can't save this"
    assert "Reel" in kwargs["body"]
    assert kwargs["data"]["reason"] == "not_a_reel"


def test_notify_invalid_url_no_fcm_token_does_not_raise():
    from workers.tasks import notify_invalid_url

    db = MagicMock()
    (
        db.table.return_value
        .select.return_value
        .eq.return_value
        .maybe_single.return_value
        .execute.return_value
        .data
    ) = None

    with patch("workers.tasks.get_supabase", return_value=db):
        with patch("workers.tasks.send_push_notification") as mock_push:
            notify_invalid_url("user-1", "not_instagram")

    mock_push.assert_called_once()
    assert mock_push.call_args[1]["fcm_token"] is None


def test_notify_invalid_url_db_failure_does_not_raise():
    from workers.tasks import notify_invalid_url

    db = MagicMock()
    (
        db.table.return_value
        .select.return_value
        .eq.return_value
        .maybe_single.return_value
        .execute
        .side_effect
    ) = Exception("DB down")

    with patch("workers.tasks.get_supabase", return_value=db):
        with patch("workers.tasks.send_push_notification") as mock_push:
            notify_invalid_url("user-1", "not_instagram")

    mock_push.assert_called_once()
