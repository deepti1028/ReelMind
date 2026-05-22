"""Celery application configuration.

Run a worker locally with:
    celery -A workers.celery_app worker --loglevel=info
"""

import ssl

from celery import Celery

from config import get_config

config = get_config()

celery_app = Celery(
    "reelmind",
    broker=config.REDIS_URL,
    backend=config.REDIS_URL,
    include=["workers.tasks", "workers.beat_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,
    task_soft_time_limit=540,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)

# Upstash requires TLS (rediss://). Celery needs ssl_cert_reqs explicitly set.
if config.REDIS_URL and config.REDIS_URL.startswith("rediss://"):
    _ssl_opts = {"ssl_cert_reqs": ssl.CERT_NONE}
    celery_app.conf.update(
        broker_use_ssl=_ssl_opts,
        redis_backend_use_ssl=_ssl_opts,
    )

celery_app.conf.beat_schedule = {
    "expire-pending-categories": {
        "task": "workers.beat_tasks.expire_pending_categories",
        "schedule": 30 * 60,  # every 30 minutes
    },
}
