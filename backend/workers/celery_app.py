"""Celery application configuration.

Run a worker locally with:
    celery -A workers.celery_app worker --loglevel=info
"""

from celery import Celery

from config import get_config

config = get_config()

celery_app = Celery(
    "reelmind",
    broker=config.REDIS_URL,
    backend=config.REDIS_URL,
    include=["workers.tasks"],
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
