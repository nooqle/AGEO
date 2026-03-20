"""Runtime registry for browser user-action handoff.

This module coordinates the temporary handoff from automated browser fetching
to the human user. It supports process-local coordination by default and
optionally mirrors pending requests into Redis so multi-worker deployments can
resolve and resume the same browser-action request.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID, uuid4

from app.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.task_run_child_attempt import TaskRunChildAttemptStatus
from app.services.task_run_child_attempt_service import TaskRunChildAttemptService


BrowserActionResolution = Literal["completed", "skip"]
logger = logging.getLogger(__name__)


@dataclass
class BrowserActionRequest:
    request_id: str
    session_id: str
    platform: str
    action_type: str
    message: str
    action_hint: str | None
    progress: float
    created_at: float
    event: asyncio.Event | None
    run_id: str | None = None
    child_attempt_id: str | None = None
    resolution: BrowserActionResolution | None = None


_REQUEST_TTL_SECONDS = 3600
_POLL_INTERVAL_SECONDS = 1.0
_REQUEST_KEY_PREFIX = "runtime:browser_action:request:"
_SESSION_KEY_PREFIX = "runtime:browser_action:session:"
_requests_by_id: dict[str, BrowserActionRequest] = {}
_requests_by_session: dict[str, set[str]] = {}
_redis_client: Any | None = None
_redis_lock = asyncio.Lock()


def _request_key(request_id: str) -> str:
    return f"{_REQUEST_KEY_PREFIX}{request_id}"


def _session_key(session_id: str) -> str:
    return f"{_SESSION_KEY_PREFIX}{session_id}"


async def _get_redis() -> Any | None:
    global _redis_client

    if _redis_client is not None:
        return _redis_client

    settings = get_settings()
    if not settings.REDIS_URL:
        return None

    async with _redis_lock:
        if _redis_client is not None:
            return _redis_client
        try:
            import redis.asyncio as redis_async

            _redis_client = redis_async.from_url(
                settings.REDIS_URL,
                decode_responses=True,
            )
            await _redis_client.ping()
        except Exception:
            _redis_client = None
        return _redis_client


def _purge_expired() -> None:
    now = time.monotonic()
    expired_ids = [
        request_id
        for request_id, request in _requests_by_id.items()
        if now - request.created_at > _REQUEST_TTL_SECONDS
    ]
    for request_id in expired_ids:
        request = _requests_by_id.get(request_id)
        clear_browser_action_request_local(request_id)
        if request is None or request.resolution is not None:
            continue
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            continue
        loop.create_task(
            _finalize_unresolved_child_attempt(
                request_id,
                final_status=TaskRunChildAttemptStatus.EXPIRED,
                error_message="浏览器操作请求已过期",
            )
        )


def _serialize_request(request: BrowserActionRequest) -> dict[str, Any]:
    return {
        "request_id": request.request_id,
        "session_id": request.session_id,
        "platform": request.platform,
        "action_type": request.action_type,
        "message": request.message,
        "action_hint": request.action_hint,
        "progress": request.progress,
        "created_at": request.created_at,
        "run_id": request.run_id,
        "child_attempt_id": request.child_attempt_id,
        "resolution": request.resolution,
    }


def _deserialize_request(payload: dict[str, Any]) -> BrowserActionRequest | None:
    request_id = payload.get("request_id")
    session_id = payload.get("session_id")
    platform = payload.get("platform")
    action_type = payload.get("action_type")
    message = payload.get("message")
    if not all(
        isinstance(value, str)
        for value in [request_id, session_id, platform, action_type, message]
    ):
        return None

    resolution = payload.get("resolution")
    if resolution not in {None, "completed", "skip"}:
        resolution = None

    return BrowserActionRequest(
        request_id=request_id,
        session_id=session_id,
        platform=platform,
        action_type=action_type,
        message=message,
        action_hint=payload.get("action_hint"),
        progress=float(payload.get("progress", 0.0) or 0.0),
        created_at=float(
            payload.get("created_at", time.monotonic()) or time.monotonic()
        ),
        event=None,
        run_id=payload.get("run_id"),
        child_attempt_id=payload.get("child_attempt_id"),
        resolution=resolution,
    )


def clear_browser_action_request_local(request_id: str) -> None:
    request = _requests_by_id.pop(request_id, None)
    if request is None:
        return
    session_requests = _requests_by_session.get(request.session_id)
    if session_requests is not None:
        session_requests.discard(request_id)
        if not session_requests:
            _requests_by_session.pop(request.session_id, None)


async def register_browser_action_request(
    session_id: str,
    platform: str,
    action_type: str,
    message: str,
    action_hint: str | None,
    progress: float,
    run_id: str | None = None,
) -> BrowserActionRequest:
    _purge_expired()

    request = BrowserActionRequest(
        request_id=f"browser_action_{uuid4().hex}",
        session_id=session_id,
        platform=platform,
        action_type=action_type,
        message=message,
        action_hint=action_hint,
        progress=progress,
        created_at=time.monotonic(),
        event=asyncio.Event(),
        run_id=run_id,
    )
    if run_id:
        request.child_attempt_id = await _create_child_attempt(request)
    _requests_by_id[request.request_id] = request
    _requests_by_session.setdefault(session_id, set()).add(request.request_id)

    client = await _get_redis()
    if client is not None:
        payload = json.dumps(_serialize_request(request))
        await client.set(
            _request_key(request.request_id), payload, ex=_REQUEST_TTL_SECONDS
        )
        await client.sadd(_session_key(session_id), request.request_id)
        await client.expire(_session_key(session_id), _REQUEST_TTL_SECONDS)

    return request


async def wait_for_browser_action_resolution(
    request_id: str,
    timeout: float = 300.0,
) -> BrowserActionResolution | None:
    request = _requests_by_id.get(request_id)
    client = await _get_redis()

    if client is None:
        if request is None or request.event is None:
            return None
        try:
            await asyncio.wait_for(request.event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
        return request.resolution

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if request is not None and request.event is not None and request.event.is_set():
            return request.resolution

        raw = await client.get(_request_key(request_id))
        if not raw:
            return request.resolution if request is not None else None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        resolution = payload.get("resolution")
        if resolution in {"completed", "skip"}:
            if request is not None:
                request.resolution = resolution
                if request.event is not None:
                    request.event.set()
            return resolution

        await asyncio.sleep(_POLL_INTERVAL_SECONDS)

    return None


async def resolve_browser_action_request(
    request_id: str,
    resolution: BrowserActionResolution,
) -> BrowserActionRequest | None:
    request = _requests_by_id.get(request_id)
    if request is not None:
        request.resolution = resolution
        if request.event is not None:
            request.event.set()

    client = await _get_redis()
    if client is not None:
        raw = await client.get(_request_key(request_id))
        if raw:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {}
            payload["resolution"] = resolution
            await client.set(
                _request_key(request_id), json.dumps(payload), ex=_REQUEST_TTL_SECONDS
            )
            if request is None:
                request = _deserialize_request(payload)

    await _resolve_child_attempt(request_id, resolution)
    return request


async def get_browser_action_request(request_id: str) -> BrowserActionRequest | None:
    _purge_expired()
    request = _requests_by_id.get(request_id)
    if request is not None:
        return request

    client = await _get_redis()
    if client is None:
        return None

    raw = await client.get(_request_key(request_id))
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return _deserialize_request(payload)


async def clear_browser_action_request(
    request_id: str,
    *,
    unresolved_status: TaskRunChildAttemptStatus = TaskRunChildAttemptStatus.EXPIRED,
    error_message: str | None = "等待用户操作超时或请求已失效",
) -> None:
    request = _requests_by_id.get(request_id)
    clear_browser_action_request_local(request_id)

    client = await _get_redis()
    if request is None and client is not None:
        request = await get_browser_action_request(request_id)

    if request is not None and request.resolution is None:
        await _finalize_unresolved_child_attempt(
            request_id,
            final_status=unresolved_status,
            error_message=error_message,
        )

    if client is None:
        return

    await client.delete(_request_key(request_id))
    if request is not None:
        await client.srem(_session_key(request.session_id), request_id)


async def clear_session_browser_action_requests(
    session_id: str,
    *,
    unresolved_status: TaskRunChildAttemptStatus = TaskRunChildAttemptStatus.CANCELLED,
    error_message: str | None = "任务已取消",
) -> None:
    request_ids = list(_requests_by_session.pop(session_id, set()))
    for request_id in request_ids:
        _requests_by_id.pop(request_id, None)
        await _finalize_unresolved_child_attempt(
            request_id,
            final_status=unresolved_status,
            error_message=error_message,
        )

    client = await _get_redis()
    if client is None:
        return

    session_ids = await client.smembers(_session_key(session_id))
    if session_ids:
        pipeline = client.pipeline()
        for request_id in session_ids:
            pipeline.delete(_request_key(request_id))
            pipeline.srem(_session_key(session_id), request_id)
        await pipeline.execute()
    for request_id in set(session_ids or []):
        await _finalize_unresolved_child_attempt(
            request_id,
            final_status=unresolved_status,
            error_message=error_message,
        )
    await client.delete(_session_key(session_id))


async def get_session_browser_action_requests(session_id: str) -> list[dict[str, Any]]:
    _purge_expired()
    results: list[dict[str, Any]] = []
    request_ids = _requests_by_session.get(session_id, set())
    for request_id in request_ids:
        request = _requests_by_id.get(request_id)
        if request is not None:
            results.append(
                {
                    "request_id": request.request_id,
                    "platform": request.platform,
                    "action_type": request.action_type,
                    "message": request.message,
                    "action_hint": request.action_hint,
                    "progress": request.progress,
                }
            )

    client = await _get_redis()
    if client is None:
        return results

    remote_ids = await client.smembers(_session_key(session_id))
    seen = {item["request_id"] for item in results}
    for request_id in remote_ids:
        if request_id in seen:
            continue
        request = await get_browser_action_request(request_id)
        if request is None:
            continue
        results.append(
            {
                "request_id": request.request_id,
                "platform": request.platform,
                "action_type": request.action_type,
                "message": request.message,
                "action_hint": request.action_hint,
                "progress": request.progress,
            }
        )

    return results


async def _create_child_attempt(request: BrowserActionRequest) -> str | None:
    if not request.run_id:
        return None

    try:
        run_id = UUID(request.run_id)
    except ValueError:
        logger.warning(
            "[BrowserActionRuntime] Ignoring invalid run_id %s for request %s",
            request.run_id,
            request.request_id,
        )
        return None

    try:
        async with AsyncSessionLocal() as db:
            service = TaskRunChildAttemptService(db)
            attempt = await service.create_browser_action_attempt(
                task_run_id=run_id,
                request_id=request.request_id,
                platform=request.platform,
                action_type=request.action_type,
                message=request.message,
                action_hint=request.action_hint,
                progress=request.progress,
            )
            return str(attempt.id)
    except Exception:
        logger.exception(
            "[BrowserActionRuntime] Failed to create child attempt for request %s",
            request.request_id,
        )
        return None


async def _resolve_child_attempt(
    request_id: str,
    resolution: BrowserActionResolution,
) -> None:
    try:
        async with AsyncSessionLocal() as db:
            service = TaskRunChildAttemptService(db)
            await service.resolve_by_request_id(request_id, resolution=resolution)
    except Exception:
        logger.exception(
            "[BrowserActionRuntime] Failed to resolve child attempt for request %s",
            request_id,
        )


async def _finalize_unresolved_child_attempt(
    request_id: str,
    *,
    final_status: TaskRunChildAttemptStatus,
    error_message: str | None,
) -> None:
    try:
        async with AsyncSessionLocal() as db:
            service = TaskRunChildAttemptService(db)
            await service.finalize_unresolved_by_request_id(
                request_id,
                final_status=final_status,
                error_message=error_message,
            )
    except Exception:
        logger.exception(
            "[BrowserActionRuntime] Failed to finalize child attempt for request %s",
            request_id,
        )
