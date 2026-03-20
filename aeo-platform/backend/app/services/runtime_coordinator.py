"""Runtime coordination boundary.

This module centralizes ephemeral coordination concerns that are separate from
the durable Task / TaskRun state machine. The current implementation supports a
local in-process coordinator and an opt-in Redis-backed coordinator for shared
session locks, blocked flags, and recall markers.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from app.config import get_settings
from app.services.local_runtime_registry import (
    LocalExecutionBinding,
    local_runtime_registry,
)
from app.services.task_event_bus import (
    TaskStatusChangedEvent,
    TaskStatusSubscriber,
    task_event_bus,
)

logger = logging.getLogger(__name__)

SESSION_LIVE_LOCK_TTL_SECONDS = 15
SESSION_BLOCK_TTL_SECONDS = 120
SESSION_RECALL_TTL_SECONDS = 600
RUNTIME_TASK_STATUS_CHANNEL = "runtime:task_status"
RUNTIME_CANCEL_CHANNEL = "runtime:cancel"


def _session_live_lock_key(session_id: str) -> str:
    return f"runtime:session:{session_id}:live"


def _session_live_meta_key(session_id: str) -> str:
    return f"runtime:session:{session_id}:live_meta"


def _session_blocked_key(session_id: str) -> str:
    return f"runtime:session:{session_id}:blocked"


def _session_recall_key(session_id: str) -> str:
    return f"runtime:session:{session_id}:recalled"


def _session_lock_token(run_id: UUID, lease_owner: str) -> str:
    return f"{run_id}:{lease_owner}"


@dataclass(slots=True)
class SessionExecutionPresence:
    """Minimal cross-process execution presence payload."""

    session_id: str
    task_id: str
    run_id: str
    lease_owner: str
    executor_kind: str
    executor_ref: str | None


class RuntimeCoordinator(Protocol):
    """Abstraction for ephemeral runtime coordination concerns."""

    async def start_background_tasks(self) -> None: ...

    async def stop_background_tasks(self) -> None: ...

    async def register_local_execution(
        self,
        *,
        session_id: str,
        task_id: UUID,
        run_id: UUID,
        lease_owner: str,
        execution_task: asyncio.Task,
    ) -> None: ...

    async def cancel_session_execution(
        self, session_id: str
    ) -> LocalExecutionBinding | None: ...

    async def cancel_task_execution(
        self,
        task_id: UUID,
        *,
        session_id: str | None = None,
    ) -> LocalExecutionBinding | None: ...

    async def allow_session_runtime_events(self, session_id: str) -> None: ...

    async def get_live_session_execution(
        self, session_id: str
    ) -> LocalExecutionBinding | None: ...

    async def has_live_session_execution(self, session_id: str) -> bool: ...

    async def is_session_runtime_blocked(self, session_id: str) -> bool: ...

    async def mark_session_recalled(self, session_id: str) -> None: ...

    async def consume_recalled_session(self, session_id: str) -> bool: ...

    async def publish_task_status(self, event: TaskStatusChangedEvent) -> None: ...

    def subscribe_task_status(self, subscriber: TaskStatusSubscriber) -> None: ...

    def unsubscribe_task_status(self, subscriber: TaskStatusSubscriber) -> None: ...


class LocalRuntimeCoordinator:
    """Single-process implementation backed by in-memory coordination helpers."""

    def __init__(self) -> None:
        self._recalled_sessions: set[str] = set()

    async def start_background_tasks(self) -> None:
        return None

    async def stop_background_tasks(self) -> None:
        return None

    async def register_local_execution(
        self,
        *,
        session_id: str,
        task_id: UUID,
        run_id: UUID,
        lease_owner: str,
        execution_task: asyncio.Task,
    ) -> None:
        await local_runtime_registry.register_execution(
            session_id=session_id,
            task_id=task_id,
            run_id=run_id,
            lease_owner=lease_owner,
            execution_task=execution_task,
        )

    async def cancel_session_execution(
        self, session_id: str
    ) -> LocalExecutionBinding | None:
        return await local_runtime_registry.cancel_session_execution(session_id)

    async def cancel_task_execution(
        self,
        task_id: UUID,
        *,
        session_id: str | None = None,
    ) -> LocalExecutionBinding | None:
        return await local_runtime_registry.cancel_task_execution(task_id)

    async def allow_session_runtime_events(self, session_id: str) -> None:
        await local_runtime_registry.allow_session_runtime_events(session_id)

    async def get_live_session_execution(
        self, session_id: str
    ) -> LocalExecutionBinding | None:
        return await local_runtime_registry.get_live_session_execution(session_id)

    async def has_live_session_execution(self, session_id: str) -> bool:
        return await self.get_live_session_execution(session_id) is not None

    async def is_session_runtime_blocked(self, session_id: str) -> bool:
        return local_runtime_registry.is_session_runtime_blocked(session_id)

    async def mark_session_recalled(self, session_id: str) -> None:
        self._recalled_sessions.add(session_id)

    async def consume_recalled_session(self, session_id: str) -> bool:
        if session_id not in self._recalled_sessions:
            return False
        self._recalled_sessions.discard(session_id)
        return True

    async def publish_task_status(self, event: TaskStatusChangedEvent) -> None:
        await task_event_bus.publish_task_status(event)

    def subscribe_task_status(self, subscriber: TaskStatusSubscriber) -> None:
        task_event_bus.subscribe_task_status(subscriber)

    def unsubscribe_task_status(self, subscriber: TaskStatusSubscriber) -> None:
        task_event_bus.unsubscribe_task_status(subscriber)


class RedisRuntimeCoordinator:
    """Redis-backed coordinator for shared ephemeral runtime state."""

    def __init__(
        self,
        *,
        redis_url: str,
        redis_client: Any | None = None,
    ) -> None:
        self._redis_url = redis_url
        self._redis = redis_client
        self._fallback = LocalRuntimeCoordinator()
        self._client_lock = asyncio.Lock()
        self._listener_task: asyncio.Task | None = None
        self._listener_stop = asyncio.Event()

    async def start_background_tasks(self) -> None:
        if self._listener_task is not None and not self._listener_task.done():
            return

        client = await self._get_redis()
        if client is None:
            logger.warning(
                "[RuntimeCoordinator] Redis listener not started because Redis is unavailable"
            )
            return

        self._listener_stop.clear()
        self._listener_task = asyncio.create_task(self._run_pubsub_listener())
        logger.info("[RuntimeCoordinator] Redis pubsub listener started")

    async def stop_background_tasks(self) -> None:
        self._listener_stop.set()
        if self._listener_task is None:
            return
        self._listener_task.cancel()
        try:
            await self._listener_task
        except asyncio.CancelledError:
            pass
        finally:
            self._listener_task = None

    async def register_local_execution(
        self,
        *,
        session_id: str,
        task_id: UUID,
        run_id: UUID,
        lease_owner: str,
        execution_task: asyncio.Task,
    ) -> None:
        client = await self._get_redis()
        if client is None:
            await self._fallback.register_local_execution(
                session_id=session_id,
                task_id=task_id,
                run_id=run_id,
                lease_owner=lease_owner,
                execution_task=execution_task,
            )
            return

        await self._acquire_session_live_lock(
            session_id=session_id,
            task_id=task_id,
            run_id=run_id,
            lease_owner=lease_owner,
        )
        try:
            await local_runtime_registry.register_execution(
                session_id=session_id,
                task_id=task_id,
                run_id=run_id,
                lease_owner=lease_owner,
                execution_task=execution_task,
                heartbeat_callback=self._refresh_session_live_lock,
                release_callback=self._release_session_live_lock,
            )
            await self._delete_key(_session_blocked_key(session_id))
        except Exception:
            await self._release_session_live_lock(
                session_id,
                task_id,
                run_id,
                lease_owner,
            )
            raise

    async def cancel_session_execution(
        self, session_id: str
    ) -> LocalExecutionBinding | None:
        await self._set_session_blocked(session_id)
        binding = await self._fallback.cancel_session_execution(session_id)
        await self._publish_cancel(
            {
                "session_id": session_id,
                "task_id": str(binding.task_id) if binding else None,
            }
        )
        return binding

    async def cancel_task_execution(
        self,
        task_id: UUID,
        *,
        session_id: str | None = None,
    ) -> LocalExecutionBinding | None:
        binding = await self._fallback.cancel_task_execution(task_id)
        target_session_id = session_id or (binding.session_id if binding else None)
        if target_session_id:
            await self._set_session_blocked(target_session_id)
        await self._publish_cancel(
            {
                "session_id": target_session_id,
                "task_id": str(task_id),
            }
        )
        return binding

    async def allow_session_runtime_events(self, session_id: str) -> None:
        await self._delete_key(_session_blocked_key(session_id))
        await self._fallback.allow_session_runtime_events(session_id)

    async def get_live_session_execution(
        self, session_id: str
    ) -> LocalExecutionBinding | None:
        return await self._fallback.get_live_session_execution(session_id)

    async def has_live_session_execution(self, session_id: str) -> bool:
        if await self._fallback.has_live_session_execution(session_id):
            return True
        client = await self._get_redis()
        if client is None:
            return False
        try:
            return bool(await client.get(_session_live_lock_key(session_id)))
        except Exception:
            logger.exception(
                "[RuntimeCoordinator] Failed to read session live lock " "(session=%s)",
                session_id,
            )
            return False

    async def is_session_runtime_blocked(self, session_id: str) -> bool:
        if await self._fallback.is_session_runtime_blocked(session_id):
            return True
        client = await self._get_redis()
        if client is None:
            return False
        try:
            return bool(await client.get(_session_blocked_key(session_id)))
        except Exception:
            logger.exception(
                "[RuntimeCoordinator] Failed to read blocked flag " "(session=%s)",
                session_id,
            )
            return False

    async def mark_session_recalled(self, session_id: str) -> None:
        client = await self._get_redis()
        if client is None:
            await self._fallback.mark_session_recalled(session_id)
            return
        try:
            await client.set(
                _session_recall_key(session_id),
                "1",
                ex=SESSION_RECALL_TTL_SECONDS,
            )
        except Exception:
            logger.exception(
                "[RuntimeCoordinator] Failed to mark session recalled " "(session=%s)",
                session_id,
            )
            await self._fallback.mark_session_recalled(session_id)

    async def consume_recalled_session(self, session_id: str) -> bool:
        client = await self._get_redis()
        if client is None:
            return await self._fallback.consume_recalled_session(session_id)
        try:
            return bool(await client.getdel(_session_recall_key(session_id)))
        except Exception:
            logger.exception(
                "[RuntimeCoordinator] Failed to consume recall marker " "(session=%s)",
                session_id,
            )
            return await self._fallback.consume_recalled_session(session_id)

    async def publish_task_status(self, event: TaskStatusChangedEvent) -> None:
        client = await self._get_redis()
        if client is None:
            await self._fallback.publish_task_status(event)
            return
        try:
            await client.publish(
                RUNTIME_TASK_STATUS_CHANNEL,
                json.dumps(
                    {
                        "session_id": event.session_id,
                        "status": event.status,
                        "task": event.task,
                    }
                ),
            )
        except Exception:
            logger.exception("[RuntimeCoordinator] Failed to publish task status event")
            await self._fallback.publish_task_status(event)

    def subscribe_task_status(self, subscriber: TaskStatusSubscriber) -> None:
        self._fallback.subscribe_task_status(subscriber)

    def unsubscribe_task_status(self, subscriber: TaskStatusSubscriber) -> None:
        self._fallback.unsubscribe_task_status(subscriber)

    async def _get_redis(self) -> Any | None:
        if self._redis is not None:
            return self._redis

    async def _publish_cancel(self, payload: dict[str, Any]) -> None:
        client = await self._get_redis()
        if client is None:
            return
        try:
            await client.publish(RUNTIME_CANCEL_CHANNEL, json.dumps(payload))
        except Exception:
            logger.exception("[RuntimeCoordinator] Failed to publish cancel signal")

    async def _run_pubsub_listener(self) -> None:
        client = await self._get_redis()
        if client is None:
            return

        pubsub = client.pubsub()
        try:
            await pubsub.subscribe(RUNTIME_TASK_STATUS_CHANNEL, RUNTIME_CANCEL_CHANNEL)
            while not self._listener_stop.is_set():
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if not message:
                    await asyncio.sleep(0.1)
                    continue
                await self._handle_pubsub_message(message)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("[RuntimeCoordinator] Redis pubsub listener crashed")
        finally:
            try:
                await pubsub.unsubscribe(
                    RUNTIME_TASK_STATUS_CHANNEL,
                    RUNTIME_CANCEL_CHANNEL,
                )
                await pubsub.close()
            except Exception:
                logger.exception("[RuntimeCoordinator] Failed to close Redis pubsub")

    async def _handle_pubsub_message(self, message: dict[str, Any]) -> None:
        channel = message.get("channel")
        data = message.get("data")
        if isinstance(channel, bytes):
            channel = channel.decode()
        if isinstance(data, bytes):
            data = data.decode()
        if not isinstance(channel, str) or not isinstance(data, str):
            return

        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            logger.warning(
                "[RuntimeCoordinator] Ignoring malformed pubsub payload on %s",
                channel,
            )
            return

        if channel == RUNTIME_TASK_STATUS_CHANNEL:
            await self._fallback.publish_task_status(
                TaskStatusChangedEvent(
                    session_id=payload.get("session_id"),
                    status=payload.get("status", "pending"),
                    task=payload.get("task") or {},
                )
            )
            return

        if channel == RUNTIME_CANCEL_CHANNEL:
            session_id = payload.get("session_id")
            task_id = payload.get("task_id")
            if session_id:
                await self._fallback.cancel_session_execution(session_id)
            elif task_id:
                try:
                    await self._fallback.cancel_task_execution(UUID(task_id))
                except ValueError:
                    logger.warning(
                        "[RuntimeCoordinator] Ignoring malformed cancel task_id %s",
                        task_id,
                    )

        async with self._client_lock:
            if self._redis is not None:
                return self._redis
            try:
                import redis.asyncio as redis_async

                self._redis = redis_async.from_url(
                    self._redis_url,
                    decode_responses=True,
                )
                await self._redis.ping()
            except Exception:
                logger.exception(
                    "[RuntimeCoordinator] Failed to initialize Redis client"
                )
                self._redis = None
            return self._redis

    async def _set_session_blocked(self, session_id: str) -> None:
        client = await self._get_redis()
        if client is None:
            return
        try:
            await client.set(
                _session_blocked_key(session_id),
                "1",
                ex=SESSION_BLOCK_TTL_SECONDS,
            )
        except Exception:
            logger.exception(
                "[RuntimeCoordinator] Failed to set blocked flag " "(session=%s)",
                session_id,
            )

    async def _delete_key(self, key: str) -> None:
        client = await self._get_redis()
        if client is None:
            return
        try:
            await client.delete(key)
        except Exception:
            logger.exception("[RuntimeCoordinator] Failed to delete key %s", key)

    async def _acquire_session_live_lock(
        self,
        *,
        session_id: str,
        task_id: UUID,
        run_id: UUID,
        lease_owner: str,
    ) -> None:
        client = await self._get_redis()
        if client is None:
            return

        token = _session_lock_token(run_id, lease_owner)
        lock_key = _session_live_lock_key(session_id)
        acquired = await client.set(
            lock_key,
            token,
            ex=SESSION_LIVE_LOCK_TTL_SECONDS,
            nx=True,
        )
        if not acquired:
            current = await client.get(lock_key)
            if current != token:
                raise RuntimeError("Session already has a live shared runtime executor")

        await client.set(
            _session_live_meta_key(session_id),
            json.dumps(
                {
                    "session_id": session_id,
                    "task_id": str(task_id),
                    "run_id": str(run_id),
                    "lease_owner": lease_owner,
                    "executor_kind": "local_workflow",
                    "executor_ref": f"session:{session_id}",
                }
            ),
            ex=SESSION_LIVE_LOCK_TTL_SECONDS,
        )

    async def _refresh_session_live_lock(
        self,
        session_id: str,
        task_id: UUID,
        run_id: UUID,
        lease_owner: str,
    ) -> None:
        client = await self._get_redis()
        if client is None:
            return

        token = _session_lock_token(run_id, lease_owner)
        lock_key = _session_live_lock_key(session_id)
        meta_key = _session_live_meta_key(session_id)
        meta = json.dumps(
            {
                "session_id": session_id,
                "task_id": str(task_id),
                "run_id": str(run_id),
                "lease_owner": lease_owner,
                "executor_kind": "local_workflow",
                "executor_ref": f"session:{session_id}",
            }
        )
        current = await client.get(lock_key)
        if current is None:
            acquired = await client.set(
                lock_key,
                token,
                ex=SESSION_LIVE_LOCK_TTL_SECONDS,
                nx=True,
            )
            if not acquired:
                raise RuntimeError("Session live lock was stolen by another executor")
            await client.set(meta_key, meta, ex=SESSION_LIVE_LOCK_TTL_SECONDS)
            return

        if current != token:
            raise RuntimeError("Session live lock owner changed unexpectedly")

        refreshed = await client.eval(
            """
            if redis.call('get', KEYS[1]) == ARGV[1] then
                redis.call('expire', KEYS[1], tonumber(ARGV[2]))
                redis.call('set', KEYS[2], ARGV[3], 'EX', tonumber(ARGV[2]))
                return 1
            end
            return 0
            """,
            2,
            lock_key,
            meta_key,
            token,
            str(SESSION_LIVE_LOCK_TTL_SECONDS),
            meta,
        )
        if refreshed != 1:
            raise RuntimeError("Session live lock owner changed unexpectedly")

    async def _release_session_live_lock(
        self,
        session_id: str,
        task_id: UUID,
        run_id: UUID,
        lease_owner: str,
    ) -> None:
        client = await self._get_redis()
        if client is None:
            return

        token = _session_lock_token(run_id, lease_owner)
        try:
            await client.eval(
                """
                if redis.call('get', KEYS[1]) == ARGV[1] then
                    redis.call('del', KEYS[1])
                    redis.call('del', KEYS[2])
                    return 1
                end
                return 0
                """,
                2,
                _session_live_lock_key(session_id),
                _session_live_meta_key(session_id),
                token,
            )
        except Exception:
            logger.exception(
                "[RuntimeCoordinator] Failed to release session live lock "
                "(session=%s, task=%s, run=%s)",
                session_id,
                task_id,
                run_id,
            )


def _build_runtime_coordinator() -> RuntimeCoordinator:
    settings = get_settings()
    if settings.REDIS_URL:
        logger.info("[RuntimeCoordinator] Using Redis-backed coordinator")
        return RedisRuntimeCoordinator(redis_url=settings.REDIS_URL)
    return LocalRuntimeCoordinator()


runtime_coordinator: RuntimeCoordinator = _build_runtime_coordinator()
