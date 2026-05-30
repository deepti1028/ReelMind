"""Celery application configuration.

Run a worker locally with:
    celery -A workers.celery_app worker --loglevel=info
"""

import ssl

from celery import Celery
from kombu.transport import redis as _kombu_redis

from config import get_config

# brpop_timeout has no Celery config knob — patch the Transport class directly.
# Channel.__init__ reads self.connection.brpop_timeout (the Transport instance),
# which falls back to this class attribute since Transport.__init__ never sets
# an instance attribute when polling_interval is None (the default) .
_kombu_redis.Transport.brpop_timeout = 60

config = get_config()

celery_app = Celery(
    "reelmind",
    broker=config.REDIS_URL,
    include=["workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=False,
    task_ignore_result=True,
    task_time_limit=600,
    task_soft_time_limit=540,
    worker_prefetch_multiplier=1,
    task_acks_late=False,
    worker_heartbeat=0,
    worker_send_task_events=False,
    task_send_sent_event=False,
    broker_transport_options={
        "socket_timeout": 300,
        "socket_connect_timeout": 10,
        "ack_emulation": False,  # task_acks_late=False means nothing is ever unacked; skip the ZSET scan
    },
    broker_pool_limit=1,
)

# Upstash requires TLS (rediss://). Celery needs ssl_cert_reqs explicitly set.
if config.REDIS_URL and config.REDIS_URL.startswith("rediss://"):
    _ssl_opts = {"ssl_cert_reqs": ssl.CERT_NONE}
    celery_app.conf.update(
        broker_use_ssl=_ssl_opts,
    )

