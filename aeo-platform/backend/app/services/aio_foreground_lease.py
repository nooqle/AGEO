"""Foreground lease coordination for AIO browser GUI actions.

The AIO runtime exposes one visible browser surface. CDP operations are scoped
to a Playwright page, but GUI actions and human takeover operate on that single
visible surface. This module coordinates only those foreground-sensitive
operations.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from hashlib import sha256
import json
import logging
import time
from typing import Any, AsyncIterator, Literal
from uuid import uuid4

from app.core.config import settings

logger = logging.getLogger(__name__)

AioForegroundLeaseMode = Literal["gui_automation", "human_takeover"]


class AioForegroundLeaseTimeout(RuntimeError):
    """Raised when a foreground lease cannot be acquired within the wait budget."""


@dataclass(slots=True)
class AioForegroundLease:
    key: str
    lease_id: str
    token: str
    mode: AioForegroundLeaseMode
    platform: str
    owner: str
    reason: str | None
    expires_at: float


def build_aio_foreground_key(
    base_url: str | None,
    sandbox_ref: str | None = None,
) -> str:
    """Build a stable, non-secret key for one visible AIO browser surface."""

    raw = (sandbox_ref or base_url or "default").strip() or "default"
    digest = sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"aio_foreground:{digest}"


class AioForegroundLeaseManager:
    def __init__(self) -> None:
        self._condition = asyncio.Condition()
        self._local_leases: dict[str, AioForegroundLease] = {}
        self._redis_client: Any | None = None
        self._redis_lock = asyncio.Lock()

    async def acquire(
        self,
        *,
        key: str,
        mode: AioForegroundLeaseMode,
        platform: str,
        owner: str,
        reason: str | None = None,
        ttl_seconds: float | None = None,
        timeout_seconds: float | None = None,
    ) -> AioForegroundLease:
        """Acquire a foreground lease.

        Human takeover and GUI automation share the same key. A same-owner
        acquire refreshes the existing lease so heartbeat/open calls are
        idempotent.
        """

        if not settings.AIO_FOREGROUND_LEASE_ENABLED:
            return self._new_lease(
                key=key,
                mode=mode,
                platform=platform,
                owner=owner,
                reason=reason,
                ttl_seconds=ttl_seconds or 1,
            )

        resolved_ttl = float(
            ttl_seconds
            if ttl_seconds is not None
            else (
                settings.AIO_FOREGROUND_HUMAN_LEASE_TTL_SECONDS
                if mode == "human_takeover"
                else settings.AIO_FOREGROUND_GUI_LEASE_TTL_SECONDS
            )
        )
        resolved_timeout = float(
            timeout_seconds
            if timeout_seconds is not None
            else (
                settings.AIO_FOREGROUND_HUMAN_LEASE_WAIT_SECONDS
                if mode == "human_takeover"
                else settings.AIO_FOREGROUND_GUI_LEASE_WAIT_SECONDS
            )
        )

        redis_client = await self._get_redis()
        if redis_client is not None:
            try:
                return await self._acquire_redis(
                    redis_client,
                    key=key,
                    mode=mode,
                    platform=platform,
                    owner=owner,
                    reason=reason,
                    ttl_seconds=resolved_ttl,
                    timeout_seconds=resolved_timeout,
                )
            except AioForegroundLeaseTimeout:
                raise
            except Exception:
                logger.exception(
                    "[AIOForeground] Redis lease failed; falling back to local "
                    "(key=%s mode=%s platform=%s owner=%s)",
                    key,
                    mode,
                    platform,
                    owner,
                )

        return await self._acquire_local(
            key=key,
            mode=mode,
            platform=platform,
            owner=owner,
            reason=reason,
            ttl_seconds=resolved_ttl,
            timeout_seconds=resolved_timeout,
        )

    @asynccontextmanager
    async def hold(
        self,
        *,
        key: str,
        mode: AioForegroundLeaseMode,
        platform: str,
        owner: str,
        reason: str | None = None,
        ttl_seconds: float | None = None,
        timeout_seconds: float | None = None,
    ) -> AsyncIterator[AioForegroundLease]:
        lease = await self.acquire(
            key=key,
            mode=mode,
            platform=platform,
            owner=owner,
            reason=reason,
            ttl_seconds=ttl_seconds,
            timeout_seconds=timeout_seconds,
        )
        try:
            yield lease
        finally:
            await self.release(lease)

    async def release(self, lease: AioForegroundLease) -> None:
        if not settings.AIO_FOREGROUND_LEASE_ENABLED:
            return
        redis_client = await self._get_redis()
        if redis_client is not None:
            try:
                await self._release_redis(redis_client, lease)
            except Exception:
                logger.exception(
                    "[AIOForeground] Redis release failed; falling back to local "
                    "(key=%s lease_id=%s)",
                    lease.key,
                    lease.lease_id,
                )
        await self._release_local(lease)

    async def release_owner(self, *, key: str, owner: str) -> None:
        if not settings.AIO_FOREGROUND_LEASE_ENABLED:
            return
        redis_client = await self._get_redis()
        if redis_client is not None:
            try:
                await self._release_owner_redis(redis_client, key=key, owner=owner)
            except Exception:
                logger.exception(
                    "[AIOForeground] Redis owner release failed; falling back to local "
                    "(key=%s owner=%s)",
                    key,
                    owner,
                )
        async with self._condition:
            current = self._active_local_lease(key)
            if current is not None and current.owner == owner:
                self._local_leases.pop(key, None)
                self._condition.notify_all()
                logger.info(
                    "[AIOForeground] foreground_lease_released key=%s mode=%s "
                    "platform=%s owner=%s reason=owner_release",
                    key,
                    current.mode,
                    current.platform,
                    owner,
                )

    async def _acquire_local(
        self,
        *,
        key: str,
        mode: AioForegroundLeaseMode,
        platform: str,
        owner: str,
        reason: str | None,
        ttl_seconds: float,
        timeout_seconds: float,
    ) -> AioForegroundLease:
        deadline = time.monotonic() + timeout_seconds
        async with self._condition:
            while True:
                current = self._active_local_lease(key)
                if current is None or current.owner == owner:
                    lease = self._new_lease(
                        key=key,
                        mode=mode,
                        platform=platform,
                        owner=owner,
                        reason=reason,
                        ttl_seconds=ttl_seconds,
                    )
                    self._local_leases[key] = lease
                    logger.info(
                        "[AIOForeground] foreground_lease_acquired key=%s mode=%s "
                        "platform=%s owner=%s reason=%s",
                        key,
                        mode,
                        platform,
                        owner,
                        reason or "",
                    )
                    return lease

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    logger.warning(
                        "[AIOForeground] foreground_lease_timeout key=%s mode=%s "
                        "platform=%s owner=%s blocked_by_mode=%s "
                        "blocked_by_platform=%s blocked_by_owner=%s",
                        key,
                        mode,
                        platform,
                        owner,
                        current.mode,
                        current.platform,
                        current.owner,
                    )
                    raise AioForegroundLeaseTimeout(
                        f"AIO foreground lease timeout: {key} blocked by "
                        f"{current.mode}:{current.platform}:{current.owner}"
                    )

                logger.info(
                    "[AIOForeground] foreground_lease_waiting key=%s requested=%s "
                    "platform=%s blocked_by=%s blocked_platform=%s",
                    key,
                    mode,
                    platform,
                    current.mode,
                    current.platform,
                )
                try:
                    await asyncio.wait_for(
                        self._condition.wait(),
                        timeout=min(0.2, remaining),
                    )
                except asyncio.TimeoutError:
                    pass

    async def _release_local(self, lease: AioForegroundLease) -> None:
        async with self._condition:
            current = self._active_local_lease(lease.key)
            if current is not None and current.token == lease.token:
                self._local_leases.pop(lease.key, None)
                self._condition.notify_all()
                logger.info(
                    "[AIOForeground] foreground_lease_released key=%s mode=%s "
                    "platform=%s owner=%s lease_id=%s",
                    lease.key,
                    lease.mode,
                    lease.platform,
                    lease.owner,
                    lease.lease_id,
                )

    def _active_local_lease(self, key: str) -> AioForegroundLease | None:
        current = self._local_leases.get(key)
        if current is None:
            return None
        if current.expires_at <= time.monotonic():
            self._local_leases.pop(key, None)
            return None
        return current

    async def _get_redis(self) -> Any | None:
        if self._redis_client is not None:
            return self._redis_client
        if not settings.REDIS_URL:
            return None
        async with self._redis_lock:
            if self._redis_client is not None:
                return self._redis_client
            try:
                import redis.asyncio as redis_async

                self._redis_client = redis_async.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True,
                )
                await self._redis_client.ping()
            except Exception:
                logger.exception("[AIOForeground] Failed to initialize Redis client")
                self._redis_client = None
            return self._redis_client

    async def _acquire_redis(
        self,
        client: Any,
        *,
        key: str,
        mode: AioForegroundLeaseMode,
        platform: str,
        owner: str,
        reason: str | None,
        ttl_seconds: float,
        timeout_seconds: float,
    ) -> AioForegroundLease:
        redis_key = self._redis_key(key)
        deadline = time.monotonic() + timeout_seconds
        while True:
            lease = self._new_lease(
                key=key,
                mode=mode,
                platform=platform,
                owner=owner,
                reason=reason,
                ttl_seconds=ttl_seconds,
            )
            payload = self._serialize_lease(lease)
            acquired = await client.set(
                redis_key,
                payload,
                ex=max(1, int(ttl_seconds)),
                nx=True,
            )
            if acquired:
                logger.info(
                    "[AIOForeground] foreground_lease_acquired key=%s mode=%s "
                    "platform=%s owner=%s reason=%s backend=redis",
                    key,
                    mode,
                    platform,
                    owner,
                    reason or "",
                )
                return lease

            current = self._deserialize_lease(await client.get(redis_key))
            if current is not None and current.owner == owner:
                await client.set(redis_key, payload, ex=max(1, int(ttl_seconds)))
                logger.info(
                    "[AIOForeground] foreground_lease_refreshed key=%s mode=%s "
                    "platform=%s owner=%s backend=redis",
                    key,
                    mode,
                    platform,
                    owner,
                )
                return lease

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AioForegroundLeaseTimeout(
                    f"AIO foreground lease timeout: {key}"
                )
            await asyncio.sleep(min(0.2, remaining))

    async def _release_redis(
        self,
        client: Any,
        lease: AioForegroundLease,
    ) -> None:
        released = await client.eval(
            """
            local payload = redis.call('get', KEYS[1])
            if not payload then
                return 0
            end
            local decoded = cjson.decode(payload)
            if decoded['token'] == ARGV[1] then
                redis.call('del', KEYS[1])
                return 1
            end
            return 0
            """,
            1,
            self._redis_key(lease.key),
            lease.token,
        )
        if not released:
            return
        logger.info(
            "[AIOForeground] foreground_lease_released key=%s mode=%s "
            "platform=%s owner=%s lease_id=%s backend=redis",
            lease.key,
            lease.mode,
            lease.platform,
            lease.owner,
            lease.lease_id,
        )

    async def _release_owner_redis(
        self,
        client: Any,
        *,
        key: str,
        owner: str,
    ) -> None:
        released = await client.eval(
            """
            local payload = redis.call('get', KEYS[1])
            if not payload then
                return 0
            end
            local decoded = cjson.decode(payload)
            if decoded['owner'] == ARGV[1] then
                redis.call('del', KEYS[1])
                return 1
            end
            return 0
            """,
            1,
            self._redis_key(key),
            owner,
        )
        if not released:
            return
        logger.info(
            "[AIOForeground] foreground_lease_released key=%s owner=%s "
            "reason=owner_release backend=redis",
            key,
            owner,
        )

    @staticmethod
    def _redis_key(key: str) -> str:
        return f"runtime:{key}:lease"

    @staticmethod
    def _new_lease(
        *,
        key: str,
        mode: AioForegroundLeaseMode,
        platform: str,
        owner: str,
        reason: str | None,
        ttl_seconds: float,
    ) -> AioForegroundLease:
        return AioForegroundLease(
            key=key,
            lease_id=f"aio_fg_{uuid4().hex}",
            token=uuid4().hex,
            mode=mode,
            platform=platform,
            owner=owner,
            reason=reason,
            expires_at=time.monotonic() + ttl_seconds,
        )

    @staticmethod
    def _serialize_lease(lease: AioForegroundLease) -> str:
        return json.dumps(
            {
                "key": lease.key,
                "lease_id": lease.lease_id,
                "token": lease.token,
                "mode": lease.mode,
                "platform": lease.platform,
                "owner": lease.owner,
                "reason": lease.reason,
                "expires_at": lease.expires_at,
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _deserialize_lease(payload: Any) -> AioForegroundLease | None:
        if not payload:
            return None
        try:
            data = json.loads(payload)
            return AioForegroundLease(
                key=str(data["key"]),
                lease_id=str(data["lease_id"]),
                token=str(data["token"]),
                mode=data["mode"],
                platform=str(data["platform"]),
                owner=str(data["owner"]),
                reason=(
                    str(data["reason"]) if data.get("reason") is not None else None
                ),
                expires_at=float(data["expires_at"]),
            )
        except Exception:
            return None


aio_foreground_lease_manager = AioForegroundLeaseManager()
