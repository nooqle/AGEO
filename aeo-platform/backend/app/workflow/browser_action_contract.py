"""Reusable browser-action contract for human takeover flows.

This module sits between executors (for example A4) and the concrete browser
runtime (Playwright / AIO). Executors should only declare that a platform now
requires human action; this module owns request reuse, takeover bundle
attachment, and frontend-facing event emission.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.core.config import settings
from app.workflow.browser_action_runtime import (
    clear_browser_action_request,
    get_browser_action_request,
    get_or_register_browser_action_request,
    update_browser_action_request,
    wait_for_browser_action_resolution,
)
from app.workflow.events import (
    send_browser_state_event,
    send_browser_user_action_event,
    send_reply_event,
)

logger = logging.getLogger(__name__)

_aio_takeover_by_request_id: dict[str, dict[str, Any]] = {}


def _build_aio_readiness_probe(handler: Any, action_type: str):
    """Build a process-local readiness probe for one live browser handoff."""

    probe = getattr(handler, "probe_takeover_ready", None)
    if not callable(probe):
        return None

    async def _run_probe() -> bool:
        return bool(await probe(action_type))

    return _run_probe


def _build_aio_resume_gate_probe(handler: Any, action_type: str):
    """Build the explicit manual-resume probe for one live browser handoff."""

    probe = getattr(handler, "probe_resume_gate_ready", None)
    if not callable(probe):
        return None

    client = getattr(handler, "client", None)
    persist_runtime_state = getattr(client, "persist_runtime_state", None)
    sync_to_existing_target_page = getattr(client, "sync_to_existing_target_page", None)
    target_url = getattr(handler, "URL", None)

    async def _run_probe() -> bool:
        if callable(sync_to_existing_target_page):
            try:
                await sync_to_existing_target_page(target_url)
            except Exception as exc:
                logger.warning(
                    "[BrowserActionContract] Failed to sync live AIO page "
                    "(platform=%s action=%s): %s",
                    getattr(handler, "PLATFORM", None),
                    action_type,
                    exc,
                )
        ready = bool(await probe(action_type))
        if ready and callable(persist_runtime_state):
            try:
                await persist_runtime_state()
            except Exception as exc:
                logger.warning(
                    "[BrowserActionContract] Failed to persist AIO runtime state "
                    "(platform=%s action=%s): %s",
                    getattr(handler, "PLATFORM", None),
                    action_type,
                    exc,
                )
        return ready

    return _run_probe


async def _resolve_user_id_from_handler(
    handler: Any, user_id: str | None
) -> str | None:
    """Recover user_id from handler session when executor did not pass it explicitly."""

    if user_id:
        return user_id

    session_id = getattr(handler, "session_id", None)
    if not session_id:
        return None

    try:
        from uuid import UUID as _UUID

        from sqlalchemy import select

        from app.core.database import AsyncSessionLocal
        from app.models.session import Session

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Session.user_id).where(Session.id == _UUID(str(session_id)))
            )
            session_user_id = result.scalar_one_or_none()
            if session_user_id is not None:
                return str(session_user_id)
    except Exception as exc:
        logger.warning(
            "[BrowserActionContract] Failed to recover user_id for takeover "
            "(session_id=%s): %s",
            session_id,
            exc,
        )
    return None


async def ensure_aio_takeover_bundle(
    *,
    handler: Any,
    user_id: str | None,
    platform: str,
    request_id: str | None,
    action_type: str,
    message: str,
    target_url: str | None = None,
) -> dict[str, Any] | None:
    """Issue one AIO takeover bundle per browser-action request."""

    if not settings.AIO_ENABLED or not settings.AIO_BASE_URL:
        logger.debug(
            "[BrowserActionContract] Skip AIO bundle: runtime disabled "
            "(platform=%s request_id=%s)",
            platform,
            request_id,
        )
        return None
    if not request_id:
        logger.warning(
            "[BrowserActionContract] Skip AIO bundle: missing request_id "
            "(platform=%s action=%s)",
            platform,
            action_type,
        )
        return None

    current_page_url = None
    client = getattr(handler, "client", None)
    page = getattr(client, "page", None)
    if page is not None:
        try:
            page_url = getattr(page, "url", None)
            if isinstance(page_url, str) and page_url.strip():
                current_page_url = page_url.strip()
        except Exception:
            current_page_url = None

    resolved_target_url = current_page_url or target_url
    if not resolved_target_url:
        existing_request = await get_browser_action_request(request_id)
        if existing_request is not None:
            resolved_target_url = existing_request.target_url
    if not resolved_target_url:
        resolved_target_url = getattr(handler, "URL", None)

    existing = _aio_takeover_by_request_id.get(request_id)
    if existing is not None:
        if resolved_target_url and existing.get("target_url") != resolved_target_url:
            existing = {**existing, "target_url": resolved_target_url}
            _aio_takeover_by_request_id[request_id] = existing
            await update_browser_action_request(
                request_id,
                takeover=existing,
                target_url=resolved_target_url,
            )
        return existing

    resolved_user_id = await _resolve_user_id_from_handler(handler, user_id)
    if not resolved_user_id:
        logger.warning(
            "[BrowserActionContract] Skip AIO bundle: missing user_id "
            "(platform=%s request_id=%s action=%s)",
            platform,
            request_id,
            action_type,
        )
        return None

    aio_session_id = getattr(client, "aio_session_id", None)
    if not aio_session_id:
        ensure_remote_runtime = getattr(client, "_ensure_remote_runtime", None)
        if callable(ensure_remote_runtime):
            try:
                await ensure_remote_runtime()
            except Exception as exc:
                logger.warning(
                    "[BrowserActionContract] Failed to prime AIO session "
                    "(platform=%s request_id=%s): %s",
                    platform,
                    request_id,
                    exc,
                )
        aio_session_id = getattr(client, "aio_session_id", None)
    if not aio_session_id:
        logger.warning(
            "[BrowserActionContract] Skip AIO bundle: missing aio_session_id "
            "(platform=%s request_id=%s client=%s)",
            platform,
            request_id,
            type(client).__name__ if client is not None else "None",
        )
        return None

    task_id = getattr(client, "task_id", None)
    run_id = getattr(handler, "run_id", None)
    readiness_probe = _build_aio_readiness_probe(handler, action_type)
    resume_probe = _build_aio_resume_gate_probe(handler, action_type)

    from app.services.aio_session_manager import aio_session_manager

    takeover = await aio_session_manager.create_takeover_access(
        session_id=aio_session_id,
        user_id=str(resolved_user_id),
        platform=platform,
        mode=settings.AIO_DEFAULT_ACCESS_MODE,
        reason=message or action_type,
        request_id=request_id,
        task_id=str(task_id) if task_id else None,
        run_id=str(run_id) if run_id else None,
        action_type=action_type,
        readiness_probe=readiness_probe,
        resume_probe=resume_probe,
    )

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
        "target_url": resolved_target_url,
    }
    _aio_takeover_by_request_id[request_id] = bundle
    logger.info(
        "[BrowserActionContract] AIO takeover bundle issued "
        "(platform=%s request_id=%s takeover_id=%s session_id=%s)",
        platform,
        request_id,
        takeover.takeover_id,
        aio_session_id,
    )
    return bundle


async def persist_browser_action_takeover(
    *,
    request_id: str | None,
    state: str,
    takeover: dict[str, Any] | None,
    target_url: str | None = None,
) -> None:
    """Persist reconnect-critical takeover metadata onto the request record."""

    if not request_id:
        return
    await update_browser_action_request(
        request_id,
        state=state,
        takeover=takeover,
        target_url=target_url,
    )


async def emit_browser_action_handoff(
    *,
    session_id: str,
    platform: str,
    state: str,
    action_type: str,
    message: str,
    action_hint: str,
    progress: float,
    reply_markdown: str,
    run_id: str | None = None,
    handler: Any | None = None,
    user_id: str | None = None,
    takeover: dict[str, Any] | None = None,
    target_url: str | None = None,
) -> str:
    """Emit one frontend-facing browser action handoff contract."""

    resolved_target_url = target_url or getattr(handler, "URL", None)
    request, created_new = await get_or_register_browser_action_request(
        session_id=session_id,
        platform=platform,
        action_type=action_type,
        message=message,
        action_hint=action_hint,
        target_url=resolved_target_url,
        progress=progress,
        run_id=run_id,
        state=state,
    )
    if takeover is None and handler is not None:
        takeover = await ensure_aio_takeover_bundle(
            handler=handler,
            user_id=user_id,
            platform=platform,
            request_id=request.request_id,
            action_type=action_type,
            message=message,
            target_url=resolved_target_url,
        )
    await persist_browser_action_takeover(
        request_id=request.request_id,
        state=state,
        takeover=takeover,
        target_url=resolved_target_url,
    )
    if created_new:
        await send_reply_event(
            session_id,
            reply_markdown,
            is_delta=True,
            is_new_round=True,
        )
        await send_reply_event(session_id, "", is_complete=True)
    await send_browser_state_event(
        session_id=session_id,
        platform=platform,
        state=state,
        message=message,
        progress=progress,
        requires_action=True,
        action_hint=action_hint,
        request_id=request.request_id,
        takeover=takeover,
    )
    await send_browser_user_action_event(
        session_id=session_id,
        platform=platform,
        state=state,
        action_type=action_type,
        message=message,
        progress=progress,
        action_hint=action_hint,
        request_id=request.request_id,
        takeover=takeover,
    )
    return request.request_id


async def wait_for_browser_action_outcome(
    request_id: str, timeout: int = 480
) -> str | None:
    """Wait for user resolution and then clean reconnect caches."""

    try:
        resolution = await wait_for_browser_action_resolution(
            request_id, timeout=timeout
        )
        if resolution is None:
            await _expire_aio_takeover_for_request(request_id)
        return resolution
    finally:
        _aio_takeover_by_request_id.pop(request_id, None)
        await clear_browser_action_request(request_id)


async def _expire_aio_takeover_for_request(request_id: str) -> None:
    request = await get_browser_action_request(request_id)
    takeover = request.takeover if request is not None else None
    if not takeover:
        takeover = _aio_takeover_by_request_id.get(request_id)
    takeover_id = takeover.get("takeover_id") if isinstance(takeover, dict) else None
    if not isinstance(takeover_id, str) or not takeover_id:
        return
    try:
        from app.services.aio_session_manager import aio_session_manager

        await aio_session_manager.expire_takeover(takeover_id)
    except Exception as exc:
        logger.warning(
            "[BrowserActionContract] Failed to expire timed-out AIO takeover "
            "(request_id=%s takeover_id=%s): %s",
            request_id,
            takeover_id,
            exc,
        )


async def wait_for_browser_action_resume(
    *,
    request_id: str,
    handler: Any,
    action_type: str,
    timeout: int = 480,
    ready_timeout: int = 120,
    poll_interval: float = 2.0,
    on_completed: Any | None = None,
    skip_readiness_probe: bool = False,
) -> tuple[bool, str | None]:
    """Wait for the user action and then validate executor-side readiness."""

    async def _persist_handler_runtime_state() -> None:
        client = getattr(handler, "client", None)
        sync_page = getattr(client, "sync_to_existing_target_page", None)
        if callable(sync_page):
            try:
                await sync_page(getattr(handler, "URL", None))
            except Exception as exc:
                logger.warning(
                    "[BrowserActionContract] Failed to sync page before "
                    "persisting browser runtime state (request_id=%s action=%s): %s",
                    request_id,
                    action_type,
                    exc,
                )
        persist = getattr(client, "persist_runtime_state", None)
        if not callable(persist):
            return
        try:
            await persist()
        except Exception as exc:
            logger.warning(
                "[BrowserActionContract] Failed to persist browser runtime state "
                "(request_id=%s action=%s): %s",
                request_id,
                action_type,
                exc,
            )

    resolution = await wait_for_browser_action_outcome(request_id, timeout=timeout)
    if resolution != "completed":
        return False, resolution

    client = getattr(handler, "client", None)
    if getattr(client, "aio_session_id", None):
        # AIO resolve already validated the manual resume gate before settling
        # the request as completed. Avoid running a second long readiness probe
        # here, otherwise the next platform appears minutes later even though
        # the user has already finished the current takeover.
        await _persist_handler_runtime_state()
        return True, resolution

    if callable(on_completed):
        completed = bool(await on_completed())
        if completed:
            await _persist_handler_runtime_state()
        return completed, resolution

    if skip_readiness_probe:
        await _persist_handler_runtime_state()
        return True, resolution

    probe = getattr(handler, "probe_resume_gate_ready", None)
    if not callable(probe):
        await _persist_handler_runtime_state()
        return True, resolution

    deadline = time.monotonic() + max(float(ready_timeout), 0.0)
    while True:
        if bool(await probe(action_type)):
            await _persist_handler_runtime_state()
            return True, resolution
        if time.monotonic() >= deadline:
            return False, resolution
        await asyncio.sleep(poll_interval)
