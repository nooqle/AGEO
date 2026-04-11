"""AIO runtime control-plane endpoints."""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from datetime import datetime
from typing import Any

import websockets
from fastapi import APIRouter, Depends, HTTPException, WebSocket, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from websockets.exceptions import ConnectionClosed

from app.api.deps import (
    get_current_internal_admin_user,
    get_current_user,
    get_user_from_token,
)
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.fetchers.browser.aio_client import AioBackendError, AioSandboxClient
from app.services.aio_session_manager import (
    ACTIVE_TAKEOVER_STATES,
    SpectaAioSession,
    SpectaAioTakeover,
    aio_session_manager,
)
from app.workflow.browser_action_runtime import (
    get_browser_action_request,
    resolve_browser_action_request,
)

router = APIRouter(prefix="/aio", tags=["aio"])
logger = logging.getLogger(__name__)

_PLATFORM_DEFAULT_TARGET_URLS = {
    "doubao": "https://www.doubao.com/chat/",
    "deepseek": "https://chat.deepseek.com/",
    "kimi": "https://kimi.com/",
    "hunyuan": "https://yuanbao.tencent.com/",
    "yuanbao": "https://yuanbao.tencent.com/",
}


class AcquireAioSessionRequest(BaseModel):
    """Request body for runtime acquisition."""

    workspace_id: str
    task_id: str
    purpose: str = "a4"
    platforms: list[str] = Field(default_factory=list)


class CreateTakeoverRequest(BaseModel):
    """Request body for issuing a takeover bundle."""

    platform: str
    mode: str = "vnc_fallback"
    reason: str = "manual_intervention"


class TakeoverHeartbeatRequest(BaseModel):
    """Heartbeat payload from the active frontend."""

    frontend_id: str
    mode: str = "vnc_fallback"


class TakeoverOpenRequest(BaseModel):
    """Open or reopen payload from the frontend."""

    frontend_id: str | None = None
    mode: str = "vnc_fallback"


class TakeoverResolveRequest(BaseModel):
    """Resolve payload from the active frontend."""

    frontend_id: str
    mode: str = "vnc_fallback"
    client_observation: str | None = None
    resume_gate_result: str | None = None


class TakeoverCancelRequest(BaseModel):
    """Cancel payload from the active frontend."""

    frontend_id: str | None = None
    reason: str = "user_cancelled"


def _serialize_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _serialize_session(session: SpectaAioSession) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "workspace_id": session.workspace_id,
        "sandbox_ref": session.sandbox_ref,
        "base_url": session.base_url,
        "aio_version": session.aio_version,
        "home_dir": session.home_dir,
        "data_root": session.data_root,
        "session_state": session.session_state.value,
        "ref_count": session.ref_count,
        "holders": sorted(session.holders),
        "current_takeover_id": session.current_takeover_id,
        "human_takeover_lock": session.human_takeover_lock,
        "last_seen_at": _serialize_datetime(session.last_seen_at),
        "last_healthcheck_at": _serialize_datetime(session.last_healthcheck_at),
        "expires_at": _serialize_datetime(session.expires_at),
        "browser": {
            "cdp_url": session.browser_info.cdp_url,
            "vnc_url": session.browser_info.vnc_url,
            "user_agent": session.browser_info.user_agent,
            "viewport": session.browser_info.viewport,
        },
    }


def _serialize_takeover(takeover: SpectaAioTakeover) -> dict[str, Any]:
    return {
        "takeover_id": takeover.takeover_id,
        "session_id": takeover.session_id,
        "platform": takeover.platform,
        "action_type": takeover.action_type,
        "request_id": takeover.request_id,
        "mode": takeover.mode,
        "reason": takeover.reason,
        "takeover_state": takeover.state.value,
        "frontend_id": takeover.frontend_id,
        "requested_at": _serialize_datetime(takeover.requested_at),
        "issued_at": _serialize_datetime(takeover.issued_at),
        "expires_at": _serialize_datetime(takeover.expires_at),
        "last_heartbeat_at": _serialize_datetime(takeover.last_heartbeat_at),
        "resume_gate_result": takeover.resume_gate_result,
        "access_bundle": {
            "open_path": f"/api/v1/aio/takeovers/{takeover.takeover_id}/open",
            "canvas_config_path": f"/api/v1/aio/takeovers/{takeover.takeover_id}/canvas-config",
            "vnc_url_path": f"/api/v1/aio/takeovers/{takeover.takeover_id}/vnc-url",
            "heartbeat_path": f"/api/v1/aio/takeovers/{takeover.takeover_id}/heartbeat",
            "resolve_path": f"/api/v1/aio/takeovers/{takeover.takeover_id}/resolve",
            "cancel_path": f"/api/v1/aio/takeovers/{takeover.takeover_id}/cancel",
        },
    }


def _serialize_takeover_with_target(
    takeover: SpectaAioTakeover,
    *,
    target_url: str | None,
) -> dict[str, Any]:
    payload = _serialize_takeover(takeover)
    payload["target_url"] = target_url
    access_bundle = payload.get("access_bundle")
    if isinstance(access_bundle, dict):
        access_bundle["target_url"] = target_url
    return payload


def _normalize_cdp_websocket_url(cdp_url: str | None) -> str | None:
    """Normalize AIO browser info into a websocket URL suitable for proxying."""

    if not cdp_url:
        return None
    parsed = urlparse(cdp_url)
    if parsed.scheme in {"ws", "wss"}:
        return cdp_url
    if parsed.scheme == "http":
        return urlunparse(parsed._replace(scheme="ws"))
    if parsed.scheme == "https":
        return urlunparse(parsed._replace(scheme="wss"))
    return None


def _decorate_novnc_url(url: str) -> str:
    """Apply frontend-friendly noVNC defaults to reduce manual connect friction."""

    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("autoconnect", "1")
    query.setdefault("resize", "remote")
    query.setdefault("reconnect", "1")
    query.setdefault("reconnect_delay", "1000")
    return urlunparse(parsed._replace(query=urlencode(query)))


def _raise_from_aio_error(exc: AioBackendError) -> None:
    status_code = exc.status_code or status.HTTP_503_SERVICE_UNAVAILABLE
    raise HTTPException(status_code=status_code, detail=exc.to_dict())


async def _settle_takeover_request(
    takeover: SpectaAioTakeover,
    *,
    resolution: str,
) -> None:
    if not takeover.request_id:
        return
    settled = await resolve_browser_action_request(takeover.request_id, resolution)
    if settled is None:
        logger.warning(
            "aio.takeover.request_settle_missing takeover_id=%s request_id=%s resolution=%s",
            takeover.takeover_id,
            takeover.request_id,
            resolution,
        )


def _is_valid_takeover_target_url(url: str | None) -> bool:
    if not url or not url.strip():
        return False
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        return False
    lowered = url.strip().lower()
    return not lowered.startswith(
        ("chrome://", "chrome-untrusted://", "devtools://")
    )


async def _resolve_takeover_target_url(
    takeover: SpectaAioTakeover,
) -> str | None:
    if takeover.request_id:
        request = await get_browser_action_request(takeover.request_id)
        if request and _is_valid_takeover_target_url(request.target_url):
            return request.target_url
    fallback = _PLATFORM_DEFAULT_TARGET_URLS.get(takeover.platform)
    if _is_valid_takeover_target_url(fallback):
        return fallback
    return None


async def _require_takeover_target_url(takeover: SpectaAioTakeover) -> str:
    target_url = await _resolve_takeover_target_url(takeover)
    if not _is_valid_takeover_target_url(target_url):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="当前接管未找到有效目标页面，请重新申请新的 takeover。",
        )
    return target_url


async def _stabilize_takeover_browser_surface(
    *,
    session: SpectaAioSession,
    target_url: str,
) -> None:
    client = AioSandboxClient(
        base_url=session.base_url,
        auth_token=settings.AIO_AUTH_TOKEN,
        timeout_seconds=settings.AIO_REQUEST_TIMEOUT_SECONDS,
    )
    try:
        await client.stabilize_browser_surface(
            preferred_url=target_url,
            exclusive=True,
        )
    except AioBackendError as exc:
        _raise_from_aio_error(exc)


async def _get_takeover_and_session_for_user(
    *,
    takeover_id: str,
    user_id: str,
) -> tuple[SpectaAioTakeover, SpectaAioSession]:
    try:
        takeover = await aio_session_manager.get_takeover(takeover_id)
        session = await aio_session_manager.get_session(takeover.session_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if takeover.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前用户无权访问该 takeover",
        )
    return takeover, session


def _ensure_takeover_bundle_is_active(takeover: SpectaAioTakeover) -> None:
    if takeover.state in ACTIVE_TAKEOVER_STATES:
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            f"当前 takeover 已处于 {takeover.state.value} 终态，旧接管 bundle 已失效，"
            "如需继续请重新申请新的 takeover。"
        ),
    )


async def _authenticate_takeover_websocket(websocket: WebSocket):
    token = websocket.query_params.get("token")
    if not token and settings.DEBUG and settings.DEV_MODE_ENABLED:
        token = settings.DEV_TOKEN
    if not token:
        await websocket.close(code=1008, reason="Missing token")
        return None

    async with AsyncSessionLocal() as db:
        user = await get_user_from_token(token, db)

    if user is None:
        await websocket.close(code=1008, reason="Unauthorized")
        return None
    return user


@router.get("/runtime/info")
async def get_aio_runtime_info(
    _current_user=Depends(get_current_internal_admin_user),
):
    """Inspect upstream AIO runtime metadata."""

    try:
        return await aio_session_manager.inspect_runtime()
    except AioBackendError as exc:
        _raise_from_aio_error(exc)


@router.post("/sessions/acquire")
async def acquire_aio_session(
    body: AcquireAioSessionRequest,
    _current_user=Depends(get_current_internal_admin_user),
):
    """Acquire or reuse a workspace-scoped AIO session."""

    try:
        session = await aio_session_manager.acquire_session(
            workspace_id=body.workspace_id,
            task_id=body.task_id,
            purpose=body.purpose,
            platforms=body.platforms,
        )
    except AioBackendError as exc:
        _raise_from_aio_error(exc)

    return {"session": _serialize_session(session)}


@router.get("/sessions/{session_id}")
async def get_aio_session(
    session_id: str,
    _current_user=Depends(get_current_internal_admin_user),
):
    """Get the current in-memory session view."""

    try:
        session = await aio_session_manager.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return {"session": _serialize_session(session)}


@router.post("/sessions/{session_id}/takeovers")
async def create_takeover(
    session_id: str,
    body: CreateTakeoverRequest,
    current_user=Depends(get_current_user),
):
    """Issue a takeover bundle for the current user."""

    try:
        takeover = await aio_session_manager.create_takeover_access(
            session_id=session_id,
            user_id=str(current_user.id),
            platform=body.platform,
            mode=body.mode,
            reason=body.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    target_url = await _resolve_takeover_target_url(takeover)
    return {
        "takeover": _serialize_takeover_with_target(
            takeover, target_url=target_url
        )
    }


@router.get("/takeovers/{takeover_id}")
async def get_takeover(
    takeover_id: str,
    current_user=Depends(get_current_user),
):
    """Read the authoritative takeover state for the current user."""

    try:
        takeover = await aio_session_manager.get_takeover(takeover_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if takeover.user_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前用户无权访问该 takeover",
        )
    target_url = await _resolve_takeover_target_url(takeover)
    return {
        "takeover": _serialize_takeover_with_target(
            takeover, target_url=target_url
        )
    }


@router.post("/takeovers/{takeover_id}/open")
async def open_takeover(
    takeover_id: str,
    body: TakeoverOpenRequest,
    current_user=Depends(get_current_user),
):
    """Open or reopen a takeover and reset its user-facing operation window."""

    try:
        takeover = await aio_session_manager.open_takeover(
            takeover_id=takeover_id,
            user_id=str(current_user.id),
            frontend_id=body.frontend_id,
            mode=body.mode,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    target_url = await _resolve_takeover_target_url(takeover)
    if not _is_valid_takeover_target_url(target_url):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="当前接管未找到有效目标页面，请重新申请新的 takeover。",
        )
    return {
        "takeover": _serialize_takeover_with_target(
            takeover, target_url=target_url
        )
    }


@router.get("/takeovers/{takeover_id}/canvas-config")
async def get_takeover_canvas_config(
    takeover_id: str,
    current_user=Depends(get_current_user),
):
    """Return frontend-facing canvas takeover config."""

    try:
        takeover = await aio_session_manager.get_takeover(takeover_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if takeover.user_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前用户无权访问该 takeover",
        )
    _ensure_takeover_bundle_is_active(takeover)
    target_url = await _require_takeover_target_url(takeover)
    session = await aio_session_manager.get_session(takeover.session_id)
    await _stabilize_takeover_browser_surface(session=session, target_url=target_url)
    await aio_session_manager.refresh_browser_info(takeover.session_id)
    return {
        "mode": "canvas_cdp",
        "takeover_id": takeover.takeover_id,
        "cdp_endpoint": f"/api/v1/aio/takeovers/{takeover.takeover_id}/cdp-relay",
        "expires_at": _serialize_datetime(takeover.expires_at),
        "heartbeat_interval_ms": settings.AIO_TAKEOVER_HEARTBEAT_INTERVAL_MS,
        "target_url": target_url,
    }


@router.get("/takeovers/{takeover_id}/vnc-url")
async def get_takeover_vnc_url(
    takeover_id: str,
    current_user=Depends(get_current_user),
):
    """Return the Specta-owned VNC entry path for fallback takeover."""

    takeover, session = await _get_takeover_and_session_for_user(
        takeover_id=takeover_id,
        user_id=str(current_user.id),
    )
    _ensure_takeover_bundle_is_active(takeover)
    target_url = await _require_takeover_target_url(takeover)
    await _stabilize_takeover_browser_surface(session=session, target_url=target_url)
    browser = await aio_session_manager.refresh_browser_info(session.session_id)
    vnc_url = browser.vnc_url
    signed_vnc_url = vnc_url
    if vnc_url:
        client = AioSandboxClient(
            base_url=session.base_url,
            auth_token=settings.AIO_AUTH_TOKEN,
            timeout_seconds=settings.AIO_REQUEST_TIMEOUT_SECONDS,
        )
        try:
            ticket = await client.create_ticket()
        except AioBackendError as exc:
            _raise_from_aio_error(exc)

        parsed = urlparse(vnc_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query["ticket"] = ticket.ticket
        signed_vnc_url = _decorate_novnc_url(
            urlunparse(parsed._replace(query=urlencode(query)))
        )
    elif signed_vnc_url:
        signed_vnc_url = _decorate_novnc_url(signed_vnc_url)

    return {
        "mode": "vnc_fallback",
        "takeover_id": takeover.takeover_id,
        "url": signed_vnc_url,
        "expires_at": _serialize_datetime(takeover.expires_at),
        "upstream_vnc_available": bool(browser.vnc_url),
    }


@router.get("/takeovers/{takeover_id}/vnc-redirect")
async def redirect_takeover_vnc(
    takeover_id: str,
    current_user=Depends(get_current_user),
):
    """Broker a short-lived VNC ticket and redirect to the upstream VNC page.

    Note: this is a development bridge. Production relay hardening is handled by
    the dedicated access-relay implementation.
    """

    takeover, session = await _get_takeover_and_session_for_user(
        takeover_id=takeover_id,
        user_id=str(current_user.id),
    )
    _ensure_takeover_bundle_is_active(takeover)

    target_url = await _require_takeover_target_url(takeover)
    await _stabilize_takeover_browser_surface(session=session, target_url=target_url)
    browser = await aio_session_manager.refresh_browser_info(session.session_id)

    if not browser.vnc_url:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="当前 AIO runtime 未提供 VNC 能力",
        )

    client = AioSandboxClient(
        base_url=session.base_url,
        auth_token=settings.AIO_AUTH_TOKEN,
        timeout_seconds=settings.AIO_REQUEST_TIMEOUT_SECONDS,
    )
    try:
        ticket = await client.create_ticket()
    except AioBackendError as exc:
        _raise_from_aio_error(exc)

    target_base = browser.vnc_url or f"{session.base_url}/vnc/index.html"
    parsed = urlparse(target_base)
    base_query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    base_query["ticket"] = ticket.ticket
    base_query["path"] = f"websockify?ticket={ticket.ticket}"
    target_url = _decorate_novnc_url(
        urlunparse(parsed._replace(query=urlencode(base_query)))
    )
    return RedirectResponse(url=target_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.websocket("/takeovers/{takeover_id}/cdp-relay")
async def relay_takeover_cdp(websocket: WebSocket, takeover_id: str):
    """Proxy the AIO CDP websocket through Specta-owned auth/session checks."""

    user = await _authenticate_takeover_websocket(websocket)
    if user is None:
        return

    try:
        takeover, session = await _get_takeover_and_session_for_user(
            takeover_id=takeover_id,
            user_id=str(user.id),
        )
        _ensure_takeover_bundle_is_active(takeover)
    except HTTPException as exc:
        await websocket.close(code=1008, reason=str(exc.detail))
        return

    browser = await aio_session_manager.refresh_browser_info(session.session_id)
    cdp_url = _normalize_cdp_websocket_url(browser.cdp_url)
    if not cdp_url:
        logger.warning(
            "aio.cdp_relay.unavailable takeover_id=%s session_id=%s raw_cdp_url=%r",
            takeover_id,
            session.session_id,
            browser.cdp_url,
        )
        await websocket.close(code=1011, reason="CDP unavailable")
        return

    logger.info(
        "aio.cdp_relay.connect takeover_id=%s session_id=%s user_id=%s frontend_id=%s upstream=%s raw_cdp_url=%r",
        takeover_id,
        session.session_id,
        user.id,
        takeover.frontend_id,
        cdp_url,
        browser.cdp_url,
    )
    await websocket.accept()

    async def safe_close_downstream(*, code: int = 1000, reason: str = "") -> None:
        try:
            await websocket.close(code=code, reason=reason)
        except RuntimeError:
            pass
        except Exception:
            logger.debug(
                "aio.cdp_relay.downstream_close_ignored takeover_id=%s",
                takeover_id,
                exc_info=True,
            )

    async def safe_close_upstream() -> None:
        try:
            await upstream.close()
        except Exception:
            logger.debug(
                "aio.cdp_relay.upstream_close_ignored takeover_id=%s",
                takeover_id,
                exc_info=True,
            )

    try:
        upstream = await websockets.connect(
            cdp_url,
            open_timeout=settings.AIO_REQUEST_TIMEOUT_SECONDS,
            ping_interval=20,
            ping_timeout=20,
            max_size=None,
        )
    except Exception as exc:
        logger.exception(
            "aio.cdp_relay.connect_failed takeover_id=%s session_id=%s upstream=%s error=%s",
            takeover_id,
            session.session_id,
            cdp_url,
            exc,
        )
        await safe_close_downstream(code=1011, reason="Failed to connect upstream CDP")
        return

    async def downstream_to_upstream() -> None:
        try:
            while True:
                message = await websocket.receive()
                message_type = message.get("type")
                if message_type == "websocket.disconnect":
                    break
                if message.get("text") is not None:
                    await upstream.send(message["text"])
                    continue
                if message.get("bytes") is not None:
                    await upstream.send(message["bytes"])
        finally:
            await safe_close_upstream()

    async def upstream_to_downstream() -> None:
        try:
            async for payload in upstream:
                if isinstance(payload, bytes):
                    await websocket.send_bytes(payload)
                else:
                    await websocket.send_text(payload)
        except ConnectionClosed:
            return

    relay_tasks = {
        asyncio.create_task(downstream_to_upstream()),
        asyncio.create_task(upstream_to_downstream()),
    }

    done, pending = await asyncio.wait(relay_tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)

    await safe_close_upstream()
    await safe_close_downstream()

    for task in done:
        exc = task.exception()
        if exc and not isinstance(exc, ConnectionClosed):
            logger.exception(
                "aio.cdp_relay.relay_failed takeover_id=%s session_id=%s upstream=%s error=%s",
                takeover_id,
                session.session_id,
                cdp_url,
                exc,
            )
            raise exc


@router.post("/takeovers/{takeover_id}/heartbeat")
async def heartbeat_takeover(
    takeover_id: str,
    body: TakeoverHeartbeatRequest,
    current_user=Depends(get_current_user),
):
    """Refresh takeover ownership from the active frontend."""

    try:
        takeover = await aio_session_manager.heartbeat_takeover(
            takeover_id=takeover_id,
            user_id=str(current_user.id),
            frontend_id=body.frontend_id,
            mode=body.mode,
        )
    except KeyError as exc:
        logger.warning(
            "aio.takeover.heartbeat_missing takeover_id=%s user_id=%s frontend_id=%s mode=%s",
            takeover_id,
            current_user.id,
            body.frontend_id,
            body.mode,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PermissionError as exc:
        logger.warning(
            "aio.takeover.heartbeat_forbidden takeover_id=%s user_id=%s frontend_id=%s mode=%s reason=%s",
            takeover_id,
            current_user.id,
            body.frontend_id,
            body.mode,
            exc,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    auto_resolved = False
    try:
        takeover, auto_resolved = await aio_session_manager.maybe_autoresolve_takeover(
            takeover_id=takeover_id,
            user_id=str(current_user.id),
            frontend_id=body.frontend_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if auto_resolved:
        await _settle_takeover_request(takeover, resolution="completed")
        logger.info(
            "aio.takeover.auto_resolved takeover_id=%s request_id=%s user_id=%s frontend_id=%s",
            takeover_id,
            takeover.request_id,
            current_user.id,
            body.frontend_id,
        )
    target_url = await _resolve_takeover_target_url(takeover)
    return {
        "takeover": _serialize_takeover_with_target(
            takeover, target_url=target_url
        )
    }


@router.post("/takeovers/{takeover_id}/resolve")
async def resolve_takeover(
    takeover_id: str,
    body: TakeoverResolveRequest,
    current_user=Depends(get_current_user),
):
    """Resolve a takeover and release the frozen runtime back to automation."""

    try:
        takeover = await aio_session_manager.resolve_takeover(
            takeover_id=takeover_id,
            user_id=str(current_user.id),
            frontend_id=body.frontend_id,
            resume_gate_result=body.resume_gate_result,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if takeover.state.value == "resolved":
        await _settle_takeover_request(takeover, resolution="completed")
    target_url = await _resolve_takeover_target_url(takeover)
    return {
        "takeover": _serialize_takeover_with_target(
            takeover, target_url=target_url
        )
    }


@router.post("/takeovers/{takeover_id}/cancel")
async def cancel_takeover(
    takeover_id: str,
    body: TakeoverCancelRequest,
    current_user=Depends(get_current_user),
):
    """Cancel a takeover and unfreeze the runtime."""

    try:
        takeover = await aio_session_manager.cancel_takeover(
            takeover_id=takeover_id,
            user_id=str(current_user.id),
            frontend_id=body.frontend_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    await _settle_takeover_request(takeover, resolution="skip")
    target_url = await _resolve_takeover_target_url(takeover)
    return {
        "takeover": _serialize_takeover_with_target(
            takeover, target_url=target_url
        )
    }
