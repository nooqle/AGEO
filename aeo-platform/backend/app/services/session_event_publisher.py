"""Session-scoped event publishing boundary.

Workflow and orchestration code should emit through this adapter instead of
depending directly on the concrete WebSocket connection manager. Under Redis,
session-scoped events are fanned out through pubsub so execution and transport
do not need to live in the same worker.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Protocol

from fastapi import WebSocket

from app.config import get_settings
from app.core.websocket_server import manager

logger = logging.getLogger(__name__)

SESSION_EVENT_CHANNEL = "runtime:session_event"


class SessionEventPublisher(Protocol):
    """Transport-agnostic session event publisher."""

    async def start_background_tasks(self) -> None: ...

    async def stop_background_tasks(self) -> None: ...

    async def emit_to_session(
        self,
        session_id: str,
        event: str,
        data: dict,
        *,
        bypass_runtime_guard: bool = False,
    ) -> None: ...

    async def emit_to_websocket(
        self,
        websocket: WebSocket,
        event: str,
        data: dict,
    ) -> None: ...


class WebSocketSessionEventPublisher:
    """Default publisher backed by the current WebSocket connection manager."""

    async def start_background_tasks(self) -> None:
        return None

    async def stop_background_tasks(self) -> None:
        return None

    async def emit_to_session(
        self,
        session_id: str,
        event: str,
        data: dict,
        *,
        bypass_runtime_guard: bool = False,
    ) -> None:
        await manager.emit_to_session(
            session_id,
            event,
            data,
            bypass_runtime_guard=bypass_runtime_guard,
        )

    async def emit_to_websocket(
        self,
        websocket: WebSocket,
        event: str,
        data: dict,
    ) -> None:
        await manager.emit_to_websocket(websocket, event, data)


class RedisSessionEventPublisher:
    """Redis-backed session event publisher for cross-worker WebSocket fanout."""

    def __init__(self, *, redis_url: str, redis_client: Any | None = None) -> None:
        self._redis_url = redis_url
        self._redis = redis_client
        self._fallback = WebSocketSessionEventPublisher()
        self._client_lock = asyncio.Lock()
        self._listener_task: asyncio.Task | None = None
        self._listener_stop = asyncio.Event()

    async def start_background_tasks(self) -> None:
        if self._listener_task is not None and not self._listener_task.done():
            return

        client = await self._get_redis()
        if client is None:
            logger.warning(
                "[SessionEventPublisher] Redis listener not started because Redis is unavailable"
            )
            return

        self._listener_stop.clear()
        self._listener_task = asyncio.create_task(self._run_pubsub_listener())
        logger.info("[SessionEventPublisher] Redis pubsub listener started")

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

    async def emit_to_session(
        self,
        session_id: str,
        event: str,
        data: dict,
        *,
        bypass_runtime_guard: bool = False,
    ) -> None:
        client = await self._get_redis()
        if client is None:
            await self._fallback.emit_to_session(
                session_id,
                event,
                data,
                bypass_runtime_guard=bypass_runtime_guard,
            )
            return

        try:
            await client.publish(
                SESSION_EVENT_CHANNEL,
                json.dumps(
                    {
                        "session_id": session_id,
                        "event": event,
                        "data": data,
                        "bypass_runtime_guard": bypass_runtime_guard,
                    }
                ),
            )
        except Exception:
            logger.exception("[SessionEventPublisher] Failed to publish session event")
            await self._fallback.emit_to_session(
                session_id,
                event,
                data,
                bypass_runtime_guard=bypass_runtime_guard,
            )

    async def emit_to_websocket(
        self,
        websocket: WebSocket,
        event: str,
        data: dict,
    ) -> None:
        await self._fallback.emit_to_websocket(websocket, event, data)

    async def _get_redis(self) -> Any | None:
        if self._redis is not None:
            return self._redis

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
                    "[SessionEventPublisher] Failed to initialize Redis client"
                )
                self._redis = None
            return self._redis

    async def _run_pubsub_listener(self) -> None:
        client = await self._get_redis()
        if client is None:
            return

        pubsub = client.pubsub()
        try:
            await pubsub.subscribe(SESSION_EVENT_CHANNEL)
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
            logger.exception("[SessionEventPublisher] Redis pubsub listener crashed")
        finally:
            try:
                await pubsub.unsubscribe(SESSION_EVENT_CHANNEL)
                await pubsub.close()
            except Exception:
                logger.exception(
                    "[SessionEventPublisher] Failed to close Redis pubsub"
                )

    async def _handle_pubsub_message(self, message: dict[str, Any]) -> None:
        data = message.get("data")
        if isinstance(data, bytes):
            data = data.decode()
        if not isinstance(data, str):
            return

        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            logger.warning(
                "[SessionEventPublisher] Ignoring malformed session event payload"
            )
            return

        session_id = payload.get("session_id")
        event = payload.get("event")
        event_data = payload.get("data")
        if not isinstance(session_id, str) or not isinstance(event, str):
            return
        if not isinstance(event_data, dict):
            event_data = {}

        await manager.emit_to_session(
            session_id,
            event,
            event_data,
            bypass_runtime_guard=bool(payload.get("bypass_runtime_guard", False)),
        )


def _build_session_event_publisher() -> SessionEventPublisher:
    settings = get_settings()
    if settings.REDIS_URL:
        logger.info("[SessionEventPublisher] Using Redis-backed publisher")
        return RedisSessionEventPublisher(redis_url=settings.REDIS_URL)
    return WebSocketSessionEventPublisher()


session_event_publisher: SessionEventPublisher = _build_session_event_publisher()
