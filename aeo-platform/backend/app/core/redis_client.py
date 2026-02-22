"""Redis client for caching and task tracking."""

import importlib
import redis
from app.config import get_settings

_redis_client = None


def get_redis_client():
    """Get or create Redis client."""
    global _redis_client

    if _redis_client is None:
        settings = get_settings()
        redis_url = settings.REDIS_URL or "redis://localhost:6379/0"

        try:
            _redis_client = redis.from_url(
                redis_url,
                decode_responses=True,
            )
            # Test connection
            _redis_client.ping()
        except (redis.ConnectionError, redis.ResponseError):
            # Fallback to fakeredis for development
            fakeredis_module = importlib.import_module("fakeredis")
            _redis_client = fakeredis_module.FakeRedis(decode_responses=True)
            print("[Redis] Using fakeredis for development")

    return _redis_client
