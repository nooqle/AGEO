"""Runtime registry for browser user-action handoff.

This module coordinates the temporary handoff from automated browser fetching
to the human user. It stores pending browser-action requests in-memory and
lets the WebSocket layer resolve them when the user clicks a completion action.

NOTE: This is process-local state and requires single-process deployment,
which matches the current WebSocket/session-layer assumptions in this repo.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Literal
from uuid import uuid4


BrowserActionResolution = Literal["completed", "skip"]


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
    event: asyncio.Event
    resolution: BrowserActionResolution | None = None


_REQUEST_TTL_SECONDS = 3600
_requests_by_id: dict[str, BrowserActionRequest] = {}
_requests_by_session: dict[str, set[str]] = {}


def _purge_expired() -> None:
    now = time.monotonic()
    expired_ids = [
        request_id
        for request_id, request in _requests_by_id.items()
        if now - request.created_at > _REQUEST_TTL_SECONDS
    ]
    for request_id in expired_ids:
        clear_browser_action_request(request_id)


def register_browser_action_request(
    session_id: str,
    platform: str,
    action_type: str,
    message: str,
    action_hint: str | None,
    progress: float,
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
    )
    _requests_by_id[request.request_id] = request
    _requests_by_session.setdefault(session_id, set()).add(request.request_id)
    return request


async def wait_for_browser_action_resolution(
    request_id: str,
    timeout: float = 300.0,
) -> BrowserActionResolution | None:
    request = _requests_by_id.get(request_id)
    if request is None:
        return None

    try:
        await asyncio.wait_for(request.event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        return None
    return request.resolution


def resolve_browser_action_request(
    request_id: str,
    resolution: BrowserActionResolution,
) -> BrowserActionRequest | None:
    request = _requests_by_id.get(request_id)
    if request is None:
        return None
    request.resolution = resolution
    request.event.set()
    return request


def get_browser_action_request(request_id: str) -> BrowserActionRequest | None:
    _purge_expired()
    return _requests_by_id.get(request_id)


def clear_browser_action_request(request_id: str) -> None:
    request = _requests_by_id.pop(request_id, None)
    if request is None:
        return
    session_requests = _requests_by_session.get(request.session_id)
    if session_requests is not None:
        session_requests.discard(request_id)
        if not session_requests:
            _requests_by_session.pop(request.session_id, None)


def clear_session_browser_action_requests(session_id: str) -> None:
    request_ids = list(_requests_by_session.pop(session_id, set()))
    for request_id in request_ids:
        _requests_by_id.pop(request_id, None)


def get_session_browser_action_requests(session_id: str) -> list[dict[str, Any]]:
    _purge_expired()
    request_ids = _requests_by_session.get(session_id, set())
    return [
        {
            "request_id": request.request_id,
            "platform": request.platform,
            "action_type": request.action_type,
            "message": request.message,
            "action_hint": request.action_hint,
            "progress": request.progress,
        }
        for request_id in request_ids
        if (request := _requests_by_id.get(request_id)) is not None
    ]
