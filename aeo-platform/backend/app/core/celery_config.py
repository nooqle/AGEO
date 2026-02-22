"""Celery configuration for async task processing.

This module configures Celery for handling long-running tasks like A4 answer fetching.
"""

import importlib
from app.config import get_settings
from app.core.constants import WorkflowConstants, CacheConstants

celery_module = importlib.import_module("celery")
Celery = celery_module.Celery
settings = get_settings()

# Try to use real Redis, fallback to fakeredis
try:
    import redis

    r = redis.from_url(settings.REDIS_URL or "redis://localhost:6379/0")
    r.ping()
    broker_url = settings.REDIS_URL or "redis://localhost:6379/0"
    print("[Celery] Using Redis broker")
except Exception:
    # Use fakeredis for development
    # Create a shared fake redis instance
    fakeredis_module = importlib.import_module("fakeredis")
    _fake_redis = fakeredis_module.FakeRedis(decode_responses=True)
    # Use memory broker for fakeredis
    broker_url = "memory://"
    print("[Celery] Using memory broker (fakeredis)")

# Create Celery app
celery_app = Celery(
    "specta_ai",
    broker=broker_url,
    backend=broker_url if broker_url != "memory://" else None,
    include=[
        "app.tasks.fetch_tasks",
    ],
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=WorkflowConstants.LLM_TIMEOUT,
    task_max_retries=WorkflowConstants.MAX_RETRIES,
    task_default_retry_delay=WorkflowConstants.RETRY_DELAY,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    # Result backend settings
    result_backend=broker_url if broker_url != "memory://" else "cache+memory://",
    cache_backend=broker_url if broker_url != "memory://" else "memory",
    result_expires=CacheConstants.TASK_TTL,
)


def get_celery_app():
    """Get Celery app instance."""
    return celery_app
