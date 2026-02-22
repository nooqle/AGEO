"""Cache service with Redis support and in-memory fallback."""

import json
from typing import Optional, Any

from app.core.config import settings


class CacheService:
    """Cache service with Redis support and in-memory fallback."""

    def __init__(self):
        """Initialize cache service."""
        self.redis = None
        self._memory_cache: dict[str, Any] = {}

        # Try to connect to Redis if configured
        if settings.REDIS_URL:
            try:
                import redis.asyncio as redis

                self.redis = redis.from_url(settings.REDIS_URL)
                print("Redis connected successfully")
            except Exception as e:
                print(f"Redis connection failed, using in-memory cache: {e}")

    async def get(self, key: str) -> Optional[str]:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None
        """
        if self.redis:
            value = await self.redis.get(key)
            return value.decode() if value else None
        return self._memory_cache.get(key)

    async def set(self, key: str, value: str, ttl: int = 3600) -> None:
        """Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
        """
        if self.redis:
            await self.redis.setex(key, ttl, value)
        else:
            self._memory_cache[key] = value

    async def delete(self, key: str) -> None:
        """Delete value from cache.

        Args:
            key: Cache key
        """
        if self.redis:
            await self.redis.delete(key)
        else:
            self._memory_cache.pop(key, None)

    async def get_json(self, key: str) -> Optional[Any]:
        """Get JSON value from cache.

        Args:
            key: Cache key

        Returns:
            Parsed JSON value or None
        """
        value = await self.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return None
        return None

    async def set_json(self, key: str, value: Any, ttl: int = 3600) -> None:
        """Set JSON value in cache.

        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl: Time to live in seconds
        """
        await self.set(key, json.dumps(value), ttl)


# Global cache instance
cache = CacheService()
