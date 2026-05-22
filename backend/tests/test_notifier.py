"""Tests for services.notifier — Step 22 FCM push wrapper."""
from unittest.mock import MagicMock, patch

import pytest


@patch("services.notifier._get_firebase_app")
@patch("services.notifier.messaging.send")
def test_send_success_returns_true(mock_send, mock_get_app):
    mock_get_app.return_value = MagicMock()  # Firebase app is initialised
    mock_send.return_value = "projects/foo/messages/123"

    from services.notifier import send_push_notification
    result = send_push_notification(
        fcm_token="device-token-abc",
        title="Reel saved!",
        body="Categorised as Fitness",
        data={"reel_id": "reel-1", "status": "ready"},
    )
    assert result is True
    assert mock_send.call_count == 1


@patch("services.notifier._get_firebase_app")
def test_no_fcm_token_returns_false(mock_get_app):
    from services.notifier import send_push_notification
    result = send_push_notification(
        fcm_token=None,
        title="Reel saved",
        body="Body",
    )
    assert result is False
    mock_get_app.assert_not_called()  # short-circuits before Firebase init


@patch("services.notifier._get_firebase_app")
def test_missing_credentials_returns_false(mock_get_app):
    mock_get_app.return_value = None  # FIREBASE_SERVICE_ACCOUNT_JSON not set
    from services.notifier import send_push_notification
    result = send_push_notification(
        fcm_token="device-token-abc",
        title="Reel saved",
        body="Body",
    )
    assert result is False


@patch("services.notifier._get_firebase_app")
@patch("services.notifier.messaging.send")
def test_send_exception_returns_false(mock_send, mock_get_app):
    mock_get_app.return_value = MagicMock()
    mock_send.side_effect = Exception("APNs unreachable")

    from services.notifier import send_push_notification
    result = send_push_notification(
        fcm_token="device-token-abc",
        title="Reel saved",
        body="Body",
    )
    assert result is False  # never re-raises


@patch("services.notifier._get_firebase_app")
@patch("services.notifier.messaging.send")
def test_category_id_sets_apns_config(mock_send, mock_get_app):
    mock_get_app.return_value = MagicMock()
    mock_send.return_value = "ok"

    from services.notifier import send_push_notification
    send_push_notification(
        fcm_token="device-token-abc",
        title="Help us categorise this reel",
        body="Body",
        category_id="CATEGORISE",
    )

    # The Message instance passed to messaging.send should have an apns config
    # with category="CATEGORISE" inside its APNSPayload.aps.
    call_arg = mock_send.call_args.args[0]
    assert call_arg.apns is not None
    assert call_arg.apns.payload.aps.category == "CATEGORISE"


@patch("services.notifier._get_firebase_app")
@patch("services.notifier.messaging.send")
def test_no_category_id_no_apns_config(mock_send, mock_get_app):
    mock_get_app.return_value = MagicMock()
    mock_send.return_value = "ok"

    from services.notifier import send_push_notification
    send_push_notification(
        fcm_token="device-token-abc",
        title="Reel saved!",
        body="Categorised as Fitness",
    )

    call_arg = mock_send.call_args.args[0]
    assert call_arg.apns is None


@patch("services.notifier._get_firebase_app")
@patch("services.notifier.messaging.send")
def test_data_payload_passed_through(mock_send, mock_get_app):
    mock_get_app.return_value = MagicMock()
    mock_send.return_value = "ok"

    from services.notifier import send_push_notification
    send_push_notification(
        fcm_token="device-token-abc",
        title="t",
        body="b",
        data={"reel_id": "r1", "suggestions": '["Fitness","Nutrition"]'},
    )

    call_arg = mock_send.call_args.args[0]
    assert call_arg.data == {"reel_id": "r1", "suggestions": '["Fitness","Nutrition"]'}
