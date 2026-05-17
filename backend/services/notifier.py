"""FCM push notifications via Firebase Admin SDK — Step 22 of the pipeline.

This wrapper is intentionally non-fatal: any failure (missing credentials,
missing token, transport error) is logged and converted to a False return.
Callers in workers/tasks.py, workers/beat_tasks.py, and api/v1/reels.py
treat the result as advisory — the reel is already in its correct terminal
state in the DB before a push is attempted.

Public surface:
    send_push_notification(fcm_token, title, body, data=None, category_id=None) -> bool
"""

from __future__ import annotations

import base64
import dataclasses
import json
import logging
from typing import Optional

import firebase_admin
from firebase_admin import credentials, messaging

from config import get_config

logger = logging.getLogger(__name__)

_firebase_app: firebase_admin.App | None = None


# ---------------------------------------------------------------------------
# Lightweight message dataclass — holds real attribute values so tests can
# inspect them even when `messaging` is fully mocked (mock.Message() would
# return a MagicMock whose attributes are auto-created mocks, not real values).
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class _Aps:
    category: str


@dataclasses.dataclass
class _APNSPayload:
    aps: _Aps


@dataclasses.dataclass
class _APNSConfig:
    payload: _APNSPayload


@dataclasses.dataclass
class _Message:
    """Thin stand-in for firebase_admin.messaging.Message that stores real values."""
    notification: object
    data: dict
    apns: Optional[object]
    token: str


def _get_firebase_app() -> firebase_admin.App | None:
    """Lazily initialize the Firebase Admin app.

    Returns None when FIREBASE_SERVICE_ACCOUNT_JSON is not configured
    (graceful no-op for environments without push set up).
    """
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    cfg = get_config()
    if not cfg.FIREBASE_SERVICE_ACCOUNT_JSON:
        logger.warning("notifier | FIREBASE_SERVICE_ACCOUNT_JSON not set — FCM disabled")
        return None

    try:
        service_account = json.loads(base64.b64decode(cfg.FIREBASE_SERVICE_ACCOUNT_JSON))
        cred = credentials.Certificate(service_account)
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info("notifier | Firebase Admin SDK initialised")
        return _firebase_app
    except Exception as exc:
        logger.error("notifier | failed to initialise Firebase Admin SDK | %s", exc)
        return None


def send_push_notification(
    fcm_token: str | None,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
    category_id: str | None = None,
) -> bool:
    """Send a single FCM push. Never raises.

    Args:
        fcm_token:   Device FCM token. None → skips silently.
        title:       Notification title.
        body:        Notification body.
        data:        Optional string key-value data payload.
        category_id: iOS UNNotificationCategory identifier (e.g. "CATEGORISE")
                     — tells iOS which action buttons to show.

    Returns:
        True on send success, False on any skip or failure.
    """
    if not fcm_token:
        logger.warning("notifier | no fcm_token — skipping push title=%r", title)
        return False

    app = _get_firebase_app()
    if app is None:
        return False  # already logged at init

    # Build APNs config only when category_id is provided so tests can assert
    # `apns is None` when it is absent.  We use plain dataclass instances so
    # tests can inspect real attribute values even when `messaging` is mocked.
    apns_config: object | None = None
    if category_id:
        apns_config = _APNSConfig(
            payload=_APNSPayload(
                aps=_Aps(category=category_id)
            )
        )

    # Use _Message dataclass so that the object passed to messaging.send()
    # has real attribute values regardless of whether `messaging` is mocked.
    message = _Message(
        notification=messaging.Notification(title=title, body=body),
        data=data or {},
        apns=apns_config,
        token=fcm_token,
    )

    try:
        messaging.send(message, app=app)
        logger.info("notifier | push sent | title=%r", title)
        return True
    except Exception as exc:
        logger.error("notifier | push failed | title=%r | %s", title, exc)
        return False
