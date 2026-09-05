"""Runtime registry for browser user-action handoff.

This module coordinates the temporary handoff from automated browser fetching
to the human user. It supports process-local coordination by default and
optionally mirrors pending requests into Redis so multi-worker deployments can
resolve and resume the same browser-action request.
"""

from __future__ import annotations

import asyncio
from hashlib import sha1
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import select

from app.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.session import Session
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
    target_url: str | None
    blocking_url: str | None
    blocking_fingerprint: str | None
    reason_code: str | None
    progress: float
    created_at: float
    event: asyncio.Event | None
    run_id: str | None = None
    task_id: str | None = None
    user_id: str | None = None
    child_attempt_id: str | None = None
    resolution: BrowserActionResolution | None = None
    state: str | None = None
    takeover: dict[str, Any] | None = None


# Keep pending browser handoff context alive long enough for realistic
# user re-entry/reconnect flows across page refreshes and short offline gaps.
_REQUEST_TTL_SECONDS = 86400
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


async def _load_session_user_id(session_id: str) -> str | None:
    try:
        session_uuid = UUID(str(session_id))
    except (TypeError, ValueError):
        return None

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Session.user_id).where(Session.id == session_uuid)
        )
        user_id = result.scalar_one_or_none()
        return str(user_id) if user_id is not None else None


async def _hydrate_takeover_for_request(
    request: BrowserActionRequest,
) -> dict[str, Any] | None:
    if request.takeover is not None or not request.request_id:
        return request.takeover

    user_id = await _load_session_user_id(request.session_id)
    if not user_id:
        return None

    from app.services.aio_session_manager import aio_session_manager

    takeover = await aio_session_manager.get_takeover_by_request_id(
        request_id=request.request_id,
        user_id=user_id,
    )
    if takeover is None:
        return None

    bundle = {
        "takeover_id": takeover.takeover_id,
        "mode": takeover.mode,
        "open_path": f"/api/v1/aio/takeovers/{takeover.takeover_id}/open",
        "canvas_config_path": f"/api/v1/aio/takeovers/{takeover.takeover_id}/canvas-config",
        "vnc_url_path": f"/api/v1/aio/takeovers/{takeover.takeover_id}/vnc-url",
        "heartbeat_path": f"/api/v1/aio/takeovers/{takeover.takeover_id}/heartbeat",
        "resolve_path": f"/api/v1/aio/takeovers/{takeover.takeover_id}/resolve",
        "cancel_path": f"/api/v1/aio/takeovers/{takeover.takeover_id}/cancel",
        "expires_at": takeover.expires_at.isoformat(),
        "action_type": request.action_type,
        "reason_code": request.reason_code,
        "target_url": request.target_url,
        "blocking_url": request.blocking_url,
        "blocking_fingerprint": request.blocking_fingerprint,
    }
    request.takeover = dict(bundle)
    await update_browser_action_request(
        request.request_id,
        state=request.state,
        takeover=bundle,
        target_url=request.target_url,
        blocking_url=request.blocking_url,
        blocking_fingerprint=request.blocking_fingerprint,
        reason_code=request.reason_code,
    )
    return bundle


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
                error_message=_resolve_unresolved_error_message(
                    request,
                    unresolved_status=TaskRunChildAttemptStatus.EXPIRED,
                    error_message="浏览器操作请求已过期",
                ),
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
        "target_url": request.target_url,
        "blocking_url": request.blocking_url,
        "blocking_fingerprint": request.blocking_fingerprint,
        "reason_code": request.reason_code,
        "progress": request.progress,
        "created_at": request.created_at,
        "run_id": request.run_id,
        "task_id": request.task_id,
        "user_id": request.user_id,
        "child_attempt_id": request.child_attempt_id,
        "resolution": request.resolution,
        "state": request.state,
        "takeover": request.takeover,
    }


def _materialize_request(request: BrowserActionRequest) -> BrowserActionRequest:
    if request.event is None:
        request.event = asyncio.Event()
        if request.resolution is not None:
            request.event.set()
    _requests_by_id[request.request_id] = request
    _requests_by_session.setdefault(request.session_id, set()).add(request.request_id)
    return request


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
        target_url=payload.get("target_url"),
        blocking_url=payload.get("blocking_url"),
        blocking_fingerprint=payload.get("blocking_fingerprint"),
        reason_code=payload.get("reason_code"),
        progress=float(payload.get("progress", 0.0) or 0.0),
        created_at=float(
            payload.get("created_at", time.monotonic()) or time.monotonic()
        ),
        event=None,
        run_id=payload.get("run_id"),
        task_id=payload.get("task_id"),
        user_id=payload.get("user_id"),
        child_attempt_id=payload.get("child_attempt_id"),
        resolution=resolution,
        state=payload.get("state"),
        takeover=(
            payload.get("takeover")
            if isinstance(payload.get("takeover"), dict)
            else None
        ),
    )


def _request_matches_reuse(
    request: BrowserActionRequest,
    *,
    platform: str,
    action_type: str,
    run_id: str | None,
    task_id: str | None,
    user_id: str | None,
    blocking_fingerprint: str | None,
) -> bool:
    return (
        request.resolution is None
        and request.platform == platform
        and request.action_type == action_type
        and request.run_id == run_id
        and request.task_id == task_id
        and request.user_id == user_id
        and request.blocking_fingerprint == blocking_fingerprint
    )


def _normalize_blocking_fingerprint(
    *,
    platform: str,
    action_type: str,
    blocking_fingerprint: str | None,
    blocking_url: str | None,
    reason_code: str | None,
) -> str | None:
    if isinstance(blocking_fingerprint, str) and blocking_fingerprint.strip():
        return blocking_fingerprint.strip()
    if not any(
        isinstance(value, str) and value.strip()
        for value in (blocking_url, reason_code)
    ):
        return None
    seed = "|".join(
        [
            platform,
            action_type,
            str(reason_code or "").strip().lower(),
            str(blocking_url or "").strip().lower(),
        ]
    )
    return sha1(seed.encode("utf-8")).hexdigest()[:16]


def infer_browser_action_state(action_type: str) -> str:
    """Return the frontend-facing browser state for a pending user action."""

    if action_type == "modal":
        return "waiting_for_modal"
    return "waiting_for_login"


def _resolve_unresolved_error_message(
    request: BrowserActionRequest | None,
    *,
    unresolved_status: TaskRunChildAttemptStatus,
    error_message: str | None,
) -> str | None:
    if request is None or not request.takeover:
        return error_message

    if unresolved_status == TaskRunChildAttemptStatus.CANCELLED and (
        error_message is None or error_message == "任务已取消"
    ):
        return "浏览器接管未完成，任务已取消"

    if unresolved_status == TaskRunChildAttemptStatus.EXPIRED and (
        error_message is None
        or error_message in {"等待用户操作超时或请求已失效", "浏览器操作请求已过期"}
    ):
        return "浏览器接管未完成或未提交完成"

    return error_message


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
    target_url: str | None,
    blocking_url: str | None = None,
    blocking_fingerprint: str | None = None,
    reason_code: str | None = None,
    progress: float = 0.0,
    run_id: str | None = None,
    task_id: str | None = None,
    user_id: str | None = None,
    state: str | None = None,
) -> BrowserActionRequest:
    _purge_expired()
    normalized_blocking_fingerprint = _normalize_blocking_fingerprint(
        platform=platform,
        action_type=action_type,
        blocking_fingerprint=blocking_fingerprint,
        blocking_url=blocking_url,
        reason_code=reason_code,
    )

    request = BrowserActionRequest(
        request_id=f"browser_action_{uuid4().hex}",
        session_id=session_id,
        platform=platform,
        action_type=action_type,
        message=message,
        action_hint=action_hint,
        target_url=target_url,
        blocking_url=blocking_url,
        blocking_fingerprint=normalized_blocking_fingerprint,
        reason_code=reason_code,
        progress=progress,
        created_at=time.monotonic(),
        event=asyncio.Event(),
        run_id=run_id,
        task_id=task_id,
        user_id=user_id,
        state=state or infer_browser_action_state(action_type),
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


async def _find_reusable_browser_action_request(
    *,
    session_id: str,
    platform: str,
    action_type: str,
    run_id: str | None,
    task_id: str | None,
    user_id: str | None,
    blocking_fingerprint: str | None,
    request_id: str | None = None,
) -> BrowserActionRequest | None:
    if request_id:
        exact = await get_browser_action_request(request_id)
        if exact is not None and exact.resolution is None:
            return exact

    candidate_ids = set(_requests_by_session.get(session_id, set()))
    client = await _get_redis()
    if client is not None:
        candidate_ids.update(await client.smembers(_session_key(session_id)))

    newest_match: BrowserActionRequest | None = None
    for candidate_id in candidate_ids:
        request = await get_browser_action_request(candidate_id)
        if request is None:
            continue
        if not _request_matches_reuse(
            request,
            platform=platform,
            action_type=action_type,
            run_id=run_id,
            task_id=task_id,
            user_id=user_id,
            blocking_fingerprint=blocking_fingerprint,
        ):
            continue
        if newest_match is None or request.created_at > newest_match.created_at:
            newest_match = request

    return newest_match


async def get_or_register_browser_action_request(
    *,
    session_id: str,
    platform: str,
    action_type: str,
    message: str,
    action_hint: str | None,
    target_url: str | None,
    progress: float,
    run_id: str | None = None,
    task_id: str | None = None,
    user_id: str | None = None,
    state: str | None = None,
    reason_code: str | None = None,
    blocking_url: str | None = None,
    blocking_fingerprint: str | None = None,
    request_id: str | None = None,
) -> tuple[BrowserActionRequest, bool]:
    _purge_expired()
    normalized_blocking_fingerprint = _normalize_blocking_fingerprint(
        platform=platform,
        action_type=action_type,
        blocking_fingerprint=blocking_fingerprint,
        blocking_url=blocking_url,
        reason_code=reason_code,
    )

    existing = await _find_reusable_browser_action_request(
        session_id=session_id,
        platform=platform,
        action_type=action_type,
        run_id=run_id,
        task_id=task_id,
        user_id=user_id,
        blocking_fingerprint=normalized_blocking_fingerprint,
        request_id=request_id,
    )
    if existing is not None:
        await update_browser_action_request(
            existing.request_id,
            state=state or infer_browser_action_state(action_type),
            target_url=target_url,
            message=message,
            action_hint=action_hint,
            progress=progress,
            reason_code=reason_code,
            blocking_url=blocking_url,
            blocking_fingerprint=normalized_blocking_fingerprint,
        )
        refreshed = await get_browser_action_request(existing.request_id)
        return (refreshed or existing, False)

    created = await register_browser_action_request(
        session_id=session_id,
        platform=platform,
        action_type=action_type,
        message=message,
        action_hint=action_hint,
        target_url=target_url,
        blocking_url=blocking_url,
        blocking_fingerprint=normalized_blocking_fingerprint,
        reason_code=reason_code,
        progress=progress,
        run_id=run_id,
        task_id=task_id,
        user_id=user_id,
        state=state,
    )
    return created, True


async def update_browser_action_request(
    request_id: str,
    *,
    state: str | None = None,
    takeover: dict[str, Any] | None = None,
    target_url: str | None = None,
    blocking_url: str | None = None,
    blocking_fingerprint: str | None = None,
    reason_code: str | None = None,
    message: str | None = None,
    action_hint: str | None = None,
    progress: float | None = None,
) -> BrowserActionRequest | None:
    """Persist request-side metadata needed for reconnect rehydration."""

    request = _requests_by_id.get(request_id)
    if request is not None:
        if state is not None:
            request.state = state
        if takeover is not None:
            request.takeover = dict(takeover)
        if target_url is not None:
            request.target_url = target_url
        if blocking_url is not None:
            request.blocking_url = blocking_url
        if blocking_fingerprint is not None:
            request.blocking_fingerprint = blocking_fingerprint
        if reason_code is not None:
            request.reason_code = reason_code
        if message is not None:
            request.message = message
        if action_hint is not None:
            request.action_hint = action_hint
        if progress is not None:
            request.progress = float(progress)

    client = await _get_redis()
    if client is not None:
        raw = await client.get(_request_key(request_id))
        if raw:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {}
            if state is not None:
                payload["state"] = state
            if takeover is not None:
                payload["takeover"] = dict(takeover)
            if target_url is not None:
                payload["target_url"] = target_url
            if blocking_url is not None:
                payload["blocking_url"] = blocking_url
            if blocking_fingerprint is not None:
                payload["blocking_fingerprint"] = blocking_fingerprint
            if reason_code is not None:
                payload["reason_code"] = reason_code
            if message is not None:
                payload["message"] = message
            if action_hint is not None:
                payload["action_hint"] = action_hint
            if progress is not None:
                payload["progress"] = float(progress)
            await client.set(
                _request_key(request_id), json.dumps(payload), ex=_REQUEST_TTL_SECONDS
            )
            if request is None:
                request = _deserialize_request(payload)
                if request is not None:
                    request = _materialize_request(request)

    return request


async def wait_for_browser_action_resolution(
    request_id: str,
    timeout: float = 480.0,
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
    request = _deserialize_request(payload)
    if request is None:
        return None
    return _materialize_request(request)


async def clear_browser_action_request(
    request_id: str,
    *,
    unresolved_status: TaskRunChildAttemptStatus = TaskRunChildAttemptStatus.EXPIRED,
    error_message: str | None = "等待用户操作超时或请求已失效",
) -> None:
    request = _requests_by_id.get(request_id)
    client = await _get_redis()
    if request is None and client is not None:
        request = await get_browser_action_request(request_id)

    if request is not None and request.resolution is None:
        # Base-handler timeouts and cancelled waiters also clear requests here;
        # release their live browser lease before discarding the only bundle.
        from app.workflow.browser_action_contract import (
            _expire_aio_takeover_for_request,
            _release_browser_action_handoff_slot,
        )

        await _expire_aio_takeover_for_request(
            request_id, takeover=request.takeover
        )
        await _release_browser_action_handoff_slot(request_id)
        await _finalize_unresolved_child_attempt(
            request_id,
            final_status=unresolved_status,
            error_message=_resolve_unresolved_error_message(
                request,
                unresolved_status=unresolved_status,
                error_message=error_message,
            ),
        )

    clear_browser_action_request_local(request_id)
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
        request = _requests_by_id.get(request_id)
        if request is not None and request.resolution is None:
            request.resolution = "skip"
            if request.event is not None:
                request.event.set()
        clear_browser_action_request_local(request_id)
        await _finalize_unresolved_child_attempt(
            request_id,
            final_status=unresolved_status,
            error_message=_resolve_unresolved_error_message(
                request,
                unresolved_status=unresolved_status,
                error_message=error_message,
            ),
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
        request = await get_browser_action_request(request_id)
        await _finalize_unresolved_child_attempt(
            request_id,
            final_status=unresolved_status,
            error_message=_resolve_unresolved_error_message(
                request,
                unresolved_status=unresolved_status,
                error_message=error_message,
            ),
        )
    await client.delete(_session_key(session_id))


async def get_session_browser_action_requests(session_id: str) -> list[dict[str, Any]]:
    _purge_expired()
    results: list[dict[str, Any]] = []
    request_ids = _requests_by_session.get(session_id, set())
    for request_id in request_ids:
        request = _requests_by_id.get(request_id)
        if request is not None:
            if request.resolution is not None:
                continue
            await _hydrate_takeover_for_request(request)
            results.append(
                {
                    "request_id": request.request_id,
                    "platform": request.platform,
                    "action_type": request.action_type,
                    "message": request.message,
                    "action_hint": request.action_hint,
                    "target_url": request.target_url,
                    "blocking_url": request.blocking_url,
                    "blocking_fingerprint": request.blocking_fingerprint,
                    "reason_code": request.reason_code,
                    "progress": request.progress,
                    "run_id": request.run_id,
                    "task_id": request.task_id,
                    "user_id": request.user_id,
                    "state": request.state
                    or infer_browser_action_state(request.action_type),
                    "takeover": dict(request.takeover) if request.takeover else None,
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
        if request.resolution is not None:
            continue
        await _hydrate_takeover_for_request(request)
        results.append(
            {
                "request_id": request.request_id,
                "platform": request.platform,
                "action_type": request.action_type,
                "message": request.message,
                "action_hint": request.action_hint,
                "target_url": request.target_url,
                "blocking_url": request.blocking_url,
                "blocking_fingerprint": request.blocking_fingerprint,
                "reason_code": request.reason_code,
                "progress": request.progress,
                "run_id": request.run_id,
                "task_id": request.task_id,
                "user_id": request.user_id,
                "state": request.state
                or infer_browser_action_state(request.action_type),
                "takeover": dict(request.takeover) if request.takeover else None,
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
