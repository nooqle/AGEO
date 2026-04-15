"""Persistent control plane for AIO-backed Specta sessions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import logging
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.fetchers.browser.aio_client import (
    AioAuthInfo,
    AioBackendError,
    AioBrowserInfo,
    AioSandboxClient,
    AioSandboxInfo,
)
from app.models.aio_runtime_session import (
    AioPlatformRuntimeState,
    AioRuntimeSession,
    AioRuntimeTakeover,
)
from app.services.aio_runtime_contracts import (
    AioPlatformRoots,
    AioSessionState,
    AioTakeoverState,
    derive_data_root,
    derive_platform_roots,
    normalize_takeover_mode,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SpectaAioSession:
    session_id: str
    workspace_id: str
    sandbox_ref: str
    base_url: str
    aio_version: str | None
    home_dir: str
    data_root: str
    browser_info: AioBrowserInfo
    session_state: AioSessionState
    holders: set[str] = field(default_factory=set)
    ref_count: int = 0
    current_takeover_id: str | None = None
    automation_lock: str | None = None
    human_takeover_lock: bool = False
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_healthcheck_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    expires_at: datetime | None = None


@dataclass(slots=True)
class SpectaAioTakeover:
    takeover_id: str
    session_id: str
    workspace_id: str
    user_id: str
    platform: str
    mode: str
    reason: str
    state: AioTakeoverState
    frontend_id: str | None
    requested_at: datetime
    issued_at: datetime
    expires_at: datetime
    last_heartbeat_at: datetime | None = None
    request_id: str | None = None
    task_id: str | None = None
    run_id: str | None = None
    action_type: str | None = None


ACTIVE_TAKEOVER_STATES = {
    AioTakeoverState.ISSUED,
    AioTakeoverState.ACTIVE,
}


def _serialize_browser_info(browser: AioBrowserInfo) -> dict[str, Any]:
    return {
        "cdp_url": browser.cdp_url,
        "vnc_url": browser.vnc_url,
        "user_agent": browser.user_agent,
        "viewport": browser.viewport,
        "detail": browser.detail,
    }


def _deserialize_browser_info(payload: dict[str, Any] | None) -> AioBrowserInfo:
    payload = payload or {}
    return AioBrowserInfo(
        cdp_url=payload.get("cdp_url"),
        vnc_url=payload.get("vnc_url"),
        user_agent=payload.get("user_agent"),
        viewport=payload.get("viewport"),
        detail=(
            payload.get("detail")
            if isinstance(payload.get("detail"), dict)
            else payload
        ),
    )


class AioSandboxSessionManager:
    def __init__(self) -> None:
        self._client: AioSandboxClient | None = None
        self._sessions_by_id: dict[str, SpectaAioSession] = {}
        self._session_by_workspace: dict[str, str] = {}
        self._takeovers_by_id: dict[str, SpectaAioTakeover] = {}
        self._lock = asyncio.Lock()

    def _ensure_client(self) -> AioSandboxClient:
        if not settings.AIO_BASE_URL:
            raise AioBackendError(
                error_code="runtime_unavailable",
                recover_hint="configure_aio_base_url",
                transport_used="rest",
                retryable=False,
                detail="AIO_BASE_URL is not configured",
            )
        if self._client is None:
            self._client = AioSandboxClient(
                base_url=settings.AIO_BASE_URL,
                auth_token=settings.AIO_AUTH_TOKEN,
                timeout_seconds=settings.AIO_REQUEST_TIMEOUT_SECONDS,
            )
        return self._client

    def _build_client_for_base_url(self, base_url: str) -> AioSandboxClient:
        return AioSandboxClient(
            base_url=base_url,
            auth_token=settings.AIO_AUTH_TOKEN,
            timeout_seconds=settings.AIO_REQUEST_TIMEOUT_SECONDS,
        )

    def get_runtime_client(self) -> AioSandboxClient:
        return self._ensure_client()

    @staticmethod
    def _make_holder(task_id: str, purpose: str) -> str:
        return f"{purpose}:{task_id}"

    @staticmethod
    def _normalize_platform_scope(platforms: list[str] | None) -> tuple[str, ...]:
        if not platforms:
            return ()
        normalized: list[str] = []
        for platform in platforms:
            value = str(platform or "").strip().lower()
            if value and value not in normalized:
                normalized.append(value)
        return tuple(sorted(normalized))

    @classmethod
    def _derive_session_workspace_scope(
        cls, workspace_id: str, platforms: list[str] | None
    ) -> str:
        platform_scope = cls._normalize_platform_scope(platforms)
        if not platform_scope:
            return workspace_id
        return f"{workspace_id}::aio-platform::{'+'.join(platform_scope)}"

    @staticmethod
    def _touch_session(session: SpectaAioSession) -> None:
        now = datetime.now(timezone.utc)
        session.last_seen_at = now
        session.last_healthcheck_at = now

    def _cache_session(self, session: SpectaAioSession) -> SpectaAioSession:
        self._sessions_by_id[session.session_id] = session
        self._session_by_workspace[session.workspace_id] = session.session_id
        return session

    def _cache_takeover(self, takeover: SpectaAioTakeover) -> SpectaAioTakeover:
        self._takeovers_by_id[takeover.takeover_id] = takeover
        return takeover

    @staticmethod
    def _hydrate_session(record: AioRuntimeSession) -> SpectaAioSession:
        return SpectaAioSession(
            session_id=record.session_id,
            workspace_id=record.workspace_id,
            sandbox_ref=record.sandbox_ref,
            base_url=record.base_url,
            aio_version=record.aio_version,
            home_dir=record.home_dir,
            data_root=record.data_root,
            browser_info=_deserialize_browser_info(record.browser_info_json),
            session_state=record.session_state,
            holders=set(record.holders_json or []),
            ref_count=record.ref_count,
            current_takeover_id=record.current_takeover_id,
            automation_lock=record.automation_lock,
            human_takeover_lock=record.human_takeover_lock,
            last_seen_at=record.last_seen_at,
            last_healthcheck_at=record.last_healthcheck_at,
            expires_at=record.expires_at,
        )

    @staticmethod
    def _hydrate_takeover(record: AioRuntimeTakeover) -> SpectaAioTakeover:
        return SpectaAioTakeover(
            takeover_id=record.takeover_id,
            session_id=record.session_id,
            workspace_id=record.workspace_id,
            user_id=record.user_id,
            platform=record.platform,
            mode=record.mode,
            reason=record.reason,
            state=record.takeover_state,
            frontend_id=record.frontend_id,
            requested_at=record.requested_at,
            issued_at=record.issued_at,
            expires_at=record.expires_at,
            last_heartbeat_at=record.last_heartbeat_at,
            request_id=record.request_id,
            task_id=record.task_id,
            run_id=record.run_id,
            action_type=record.action_type,
        )

    async def _load_session_record(
        self,
        *,
        session_id: str | None = None,
        workspace_id: str | None = None,
    ) -> AioRuntimeSession | None:
        async with AsyncSessionLocal() as db:
            stmt = select(AioRuntimeSession)
            if session_id is not None:
                stmt = stmt.where(AioRuntimeSession.session_id == session_id)
            if workspace_id is not None:
                stmt = stmt.where(AioRuntimeSession.workspace_id == workspace_id)
                stmt = stmt.where(
                    AioRuntimeSession.session_state.notin_(
                        [AioSessionState.FAILED, AioSessionState.DESTROYED]
                    )
                )
                stmt = stmt.order_by(AioRuntimeSession.updated_at.desc())
            result = await db.execute(stmt.limit(1))
            return result.scalar_one_or_none()

    async def _load_takeover_record(
        self, takeover_id: str
    ) -> AioRuntimeTakeover | None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AioRuntimeTakeover).where(
                    AioRuntimeTakeover.takeover_id == takeover_id
                )
            )
            return result.scalar_one_or_none()

    async def _load_takeover_record_by_request_id(
        self, *, request_id: str, user_id: str
    ) -> AioRuntimeTakeover | None:
        async with AsyncSessionLocal() as db:
            stmt = (
                select(AioRuntimeTakeover)
                .where(AioRuntimeTakeover.request_id == request_id)
                .where(AioRuntimeTakeover.user_id == user_id)
                .order_by(AioRuntimeTakeover.updated_at.desc())
            )
            result = await db.execute(stmt.limit(1))
            return result.scalar_one_or_none()

    async def _save_session_record(self, session: SpectaAioSession) -> SpectaAioSession:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AioRuntimeSession).where(
                    AioRuntimeSession.session_id == session.session_id
                )
            )
            record = result.scalar_one_or_none()
            if record is None:
                record = AioRuntimeSession(
                    session_id=session.session_id,
                    workspace_id=session.workspace_id,
                    sandbox_ref=session.sandbox_ref,
                    base_url=session.base_url,
                    aio_version=session.aio_version,
                    home_dir=session.home_dir,
                    data_root=session.data_root,
                )
                db.add(record)

            record.workspace_id = session.workspace_id
            record.sandbox_ref = session.sandbox_ref
            record.base_url = session.base_url
            record.aio_version = session.aio_version
            record.home_dir = session.home_dir
            record.data_root = session.data_root
            record.browser_info_json = _serialize_browser_info(session.browser_info)
            record.session_state = session.session_state
            record.holders_json = sorted(session.holders)
            record.ref_count = session.ref_count
            record.current_takeover_id = session.current_takeover_id
            record.automation_lock = session.automation_lock
            record.human_takeover_lock = session.human_takeover_lock
            record.last_seen_at = session.last_seen_at
            record.last_healthcheck_at = session.last_healthcheck_at
            record.expires_at = session.expires_at

            await db.commit()
            await db.refresh(record)
            return self._cache_session(self._hydrate_session(record))

    async def _save_takeover_record(
        self, takeover: SpectaAioTakeover
    ) -> SpectaAioTakeover:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AioRuntimeTakeover).where(
                    AioRuntimeTakeover.takeover_id == takeover.takeover_id
                )
            )
            record = result.scalar_one_or_none()
            if record is None:
                record = AioRuntimeTakeover(
                    takeover_id=takeover.takeover_id,
                    session_id=takeover.session_id,
                    workspace_id=takeover.workspace_id,
                    user_id=takeover.user_id,
                    platform=takeover.platform,
                    mode=takeover.mode,
                    reason=takeover.reason,
                    takeover_state=takeover.state,
                    requested_at=takeover.requested_at,
                    issued_at=takeover.issued_at,
                    expires_at=takeover.expires_at,
                )
                db.add(record)

            record.session_id = takeover.session_id
            record.workspace_id = takeover.workspace_id
            record.user_id = takeover.user_id
            record.platform = takeover.platform
            record.mode = takeover.mode
            record.reason = takeover.reason
            record.takeover_state = takeover.state
            record.frontend_id = takeover.frontend_id
            record.request_id = takeover.request_id
            record.task_id = takeover.task_id
            record.run_id = takeover.run_id
            record.action_type = takeover.action_type
            record.last_heartbeat_at = takeover.last_heartbeat_at
            record.expires_at = takeover.expires_at
            record.resolved_at = (
                datetime.now(timezone.utc)
                if takeover.state
                in {
                    AioTakeoverState.RESOLVED,
                    AioTakeoverState.CANCELLED,
                    AioTakeoverState.EXPIRED,
                    AioTakeoverState.RESUME_FAILED,
                }
                else None
            )
            record.resume_gate_result = None

            await db.commit()
            await db.refresh(record)
            hydrated = self._hydrate_takeover(record)
            return self._cache_takeover(hydrated)

    async def _upsert_platform_state(
        self,
        *,
        session_id: str,
        workspace_id: str,
        task_id: str,
        platform: str,
        roots: AioPlatformRoots,
    ) -> None:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AioPlatformRuntimeState).where(
                    AioPlatformRuntimeState.session_id == session_id,
                    AioPlatformRuntimeState.task_id == task_id,
                    AioPlatformRuntimeState.platform == platform,
                )
            )
            record = result.scalar_one_or_none()
            if record is None:
                record = AioPlatformRuntimeState(
                    session_id=session_id,
                    workspace_id=workspace_id,
                    task_id=task_id,
                    platform=platform,
                    profile_root=roots.profile_root,
                    run_root=roots.run_root,
                    cookies_path=roots.cookies_path,
                    state_path=roots.state_path,
                    session_meta_path=roots.session_meta_path,
                    checkpoint_root=roots.checkpoint_root,
                    snapshot_root=roots.snapshot_root,
                    download_root=roots.download_root,
                    extraction_path=roots.extraction_path,
                )
                db.add(record)
            else:
                record.workspace_id = workspace_id
                record.profile_root = roots.profile_root
                record.run_root = roots.run_root
                record.cookies_path = roots.cookies_path
                record.state_path = roots.state_path
                record.session_meta_path = roots.session_meta_path
                record.checkpoint_root = roots.checkpoint_root
                record.snapshot_root = roots.snapshot_root
                record.download_root = roots.download_root
                record.extraction_path = roots.extraction_path
            await db.commit()

    async def _mark_platform_state_timestamp(
        self,
        *,
        session_id: str,
        task_id: str,
        platform: str,
        loaded: bool = False,
        saved: bool = False,
    ) -> None:
        if not loaded and not saved:
            return

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AioPlatformRuntimeState).where(
                    AioPlatformRuntimeState.session_id == session_id,
                    AioPlatformRuntimeState.task_id == task_id,
                    AioPlatformRuntimeState.platform == platform,
                )
            )
            record = result.scalar_one_or_none()
            if record is None:
                return

            now = datetime.now(timezone.utc)
            if loaded:
                record.last_state_load_at = now
            if saved:
                record.last_state_save_at = now
            await db.commit()

    async def _get_or_create_workspace_session_locked(
        self,
        *,
        workspace_id: str,
        holder: str | None,
    ) -> SpectaAioSession:
        existing_id = self._session_by_workspace.get(workspace_id)
        existing = self._sessions_by_id.get(existing_id) if existing_id else None
        if existing is None:
            record = await self._load_session_record(workspace_id=workspace_id)
            if record is not None:
                existing = self._cache_session(self._hydrate_session(record))

        if existing is not None:
            existing = await self._reconcile_session_takeover_lock_locked(existing)

        if existing and existing.session_state not in {
            AioSessionState.DRAINING,
            AioSessionState.FAILED,
            AioSessionState.DESTROYED,
        }:
            if (
                holder
                and existing.human_takeover_lock
                and existing.current_takeover_id
                and holder not in existing.holders
            ):
                raise AioBackendError(
                    error_code="takeover_locked",
                    recover_hint="wait_for_takeover_release",
                    transport_used="rest",
                    retryable=True,
                    detail=(
                        "AIO workspace is currently frozen for human takeover; "
                        "wait until the active takeover is resolved before driving "
                        "another platform."
                    ),
                )
            if holder:
                existing.holders.add(holder)
                existing.ref_count = len(existing.holders)
                existing.automation_lock = holder
                existing.session_state = AioSessionState.LEASED
            self._touch_session(existing)
            return await self._save_session_record(existing)

        client = self._ensure_client()
        sandbox: AioSandboxInfo = await client.get_sandbox_info()
        browser: AioBrowserInfo = await client.get_browser_info()
        holders = {holder} if holder else set()
        session = SpectaAioSession(
            session_id=f"aio_session_{uuid4().hex}",
            workspace_id=workspace_id,
            sandbox_ref=client.base_url,
            base_url=client.base_url,
            aio_version=sandbox.version,
            home_dir=sandbox.home_dir,
            data_root=derive_data_root(sandbox.home_dir),
            browser_info=browser,
            session_state=AioSessionState.LEASED if holder else AioSessionState.READY,
            holders=holders,
            ref_count=len(holders),
            automation_lock=holder,
        )
        return await self._save_session_record(session)

    async def _reconcile_session_takeover_lock_locked(
        self, session: SpectaAioSession
    ) -> SpectaAioSession:
        """Release stale human-takeover locks before leasing the workspace again."""

        if not session.human_takeover_lock and not session.current_takeover_id:
            return session

        takeover: SpectaAioTakeover | None = None
        if session.current_takeover_id:
            takeover = self._takeovers_by_id.get(session.current_takeover_id)
            if takeover is None:
                record = await self._load_takeover_record(session.current_takeover_id)
                if record is not None:
                    takeover = self._cache_takeover(self._hydrate_takeover(record))

        if takeover is None:
            session.current_takeover_id = None
            session.human_takeover_lock = False
            if session.ref_count > 0:
                session.session_state = AioSessionState.LEASED
            elif session.session_state == AioSessionState.IDLE:
                session.session_state = AioSessionState.IDLE
            else:
                session.session_state = AioSessionState.READY
            return await self._save_session_record(session)

        takeover = await self._expire_takeover_if_needed(takeover)
        refreshed_session = self._sessions_by_id.get(session.session_id, session)
        if takeover.state in ACTIVE_TAKEOVER_STATES:
            return refreshed_session

        if (
            refreshed_session.current_takeover_id == takeover.takeover_id
            or refreshed_session.human_takeover_lock
        ):
            refreshed_session.current_takeover_id = None
            refreshed_session.human_takeover_lock = False
            if refreshed_session.ref_count > 0:
                refreshed_session.session_state = AioSessionState.LEASED
            elif refreshed_session.session_state == AioSessionState.IDLE:
                refreshed_session.session_state = AioSessionState.IDLE
            else:
                refreshed_session.session_state = AioSessionState.READY
            refreshed_session = await self._save_session_record(refreshed_session)

        return refreshed_session

    async def inspect_runtime(self) -> dict[str, Any]:
        client = self._ensure_client()
        sandbox = await client.get_sandbox_info()
        browser = await client.get_browser_info()
        auth: AioAuthInfo | None = None
        try:
            auth = await client.get_auth_info()
        except AioBackendError:
            auth = None
        return {
            "configured": True,
            "base_url": client.base_url,
            "sandbox": sandbox.detail,
            "browser": browser.detail,
            "auth": auth.detail if auth else None,
        }

    async def get_session(self, session_id: str) -> SpectaAioSession:
        session = self._sessions_by_id.get(session_id)
        if session is None:
            record = await self._load_session_record(session_id=session_id)
            if record is None:
                raise KeyError(f"AIO session not found: {session_id}")
            session = self._cache_session(self._hydrate_session(record))
        self._touch_session(session)
        return session

    async def ensure_workspace_session(self, *, workspace_id: str) -> SpectaAioSession:
        async with self._lock:
            return await self._get_or_create_workspace_session_locked(
                workspace_id=workspace_id,
                holder=None,
            )

    async def acquire_session(
        self,
        *,
        workspace_id: str,
        task_id: str,
        purpose: str,
        platforms: list[str] | None = None,
    ) -> SpectaAioSession:
        session_workspace_id = self._derive_session_workspace_scope(
            workspace_id,
            platforms,
        )
        holder = self._make_holder(task_id, purpose)
        async with self._lock:
            return await self._get_or_create_workspace_session_locked(
                workspace_id=session_workspace_id,
                holder=holder,
            )

    async def refresh_browser_info(self, session_id: str) -> AioBrowserInfo:
        async with self._lock:
            session = await self.get_session(session_id)
            browser = await self._build_client_for_base_url(
                session.base_url
            ).get_browser_info()
            session.browser_info = browser
            self._touch_session(session)
            session = await self._save_session_record(session)
            return session.browser_info

    async def ensure_platform_roots(
        self,
        *,
        session_id: str,
        task_id: str,
        platform: str,
        workspace_id: str | None = None,
        auth_scope_id: str | None = None,
        run_scope_id: str | None = None,
    ) -> AioPlatformRoots:
        session = await self.get_session(session_id)
        logical_workspace_id = workspace_id or session.workspace_id
        roots = derive_platform_roots(
            data_root=session.data_root,
            workspace_id=logical_workspace_id,
            task_id=task_id,
            platform=platform,
            auth_scope_id=auth_scope_id or logical_workspace_id,
            run_scope_id=run_scope_id or logical_workspace_id,
            environment=settings.AIO_AUTH_ENV_SCOPE,
        )
        client = self._build_client_for_base_url(session.base_url)
        await client.ensure_directories(
            roots.profile_root,
            roots.run_root,
            roots.checkpoint_root,
            roots.snapshot_root,
            roots.download_root,
        )
        await client.write_text_file(
            roots.session_meta_path,
            json.dumps(
                {
                    "session_id": session.session_id,
                    "workspace_id": logical_workspace_id,
                    "session_workspace_id": session.workspace_id,
                    "task_id": task_id,
                    "platform": platform,
                    "auth_context_key": roots.auth_context_key,
                    "run_context_key": roots.run_context_key,
                    "sandbox_ref": session.sandbox_ref,
                    "data_root": session.data_root,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        await self._upsert_platform_state(
            session_id=session.session_id,
            workspace_id=logical_workspace_id,
            task_id=task_id,
            platform=platform,
            roots=roots,
        )
        return roots

    async def mark_platform_state_loaded(
        self,
        *,
        session_id: str,
        task_id: str,
        platform: str,
    ) -> None:
        await self._mark_platform_state_timestamp(
            session_id=session_id,
            task_id=task_id,
            platform=platform,
            loaded=True,
        )

    async def mark_platform_state_saved(
        self,
        *,
        session_id: str,
        task_id: str,
        platform: str,
    ) -> None:
        await self._mark_platform_state_timestamp(
            session_id=session_id,
            task_id=task_id,
            platform=platform,
            saved=True,
        )

    async def get_browser_connection(self, session_id: str) -> dict[str, Any]:
        session = await self.get_session(session_id)
        browser = await self.refresh_browser_info(session_id)
        return {
            "session_id": session.session_id,
            "sandbox_ref": session.sandbox_ref,
            "base_url": session.base_url,
            "cdp_url": browser.cdp_url,
            "vnc_url": browser.vnc_url,
            "user_agent": browser.user_agent,
            "viewport": browser.viewport,
            "preferred_access_mode": normalize_takeover_mode(
                settings.AIO_DEFAULT_ACCESS_MODE
            ),
        }

    async def release_session(
        self, session_id: str, *, task_id: str, purpose: str
    ) -> SpectaAioSession:
        holder = self._make_holder(task_id, purpose)
        async with self._lock:
            session = await self.get_session(session_id)
            session.holders.discard(holder)
            session.ref_count = len(session.holders)
            session.automation_lock = (
                None if session.ref_count == 0 else session.automation_lock
            )
            if session.human_takeover_lock and session.current_takeover_id:
                session.session_state = AioSessionState.TAKEOVER_FROZEN
            else:
                session.session_state = (
                    AioSessionState.IDLE
                    if session.ref_count == 0
                    else AioSessionState.LEASED
                )
            session.expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=settings.AIO_IDLE_TTL_SECONDS
            )
            self._touch_session(session)
            return await self._save_session_record(session)

    async def create_takeover_access(
        self,
        *,
        session_id: str,
        user_id: str,
        platform: str,
        mode: str,
        reason: str,
        request_id: str | None = None,
        task_id: str | None = None,
        run_id: str | None = None,
        action_type: str | None = None,
    ) -> SpectaAioTakeover:
        async with self._lock:
            if request_id:
                existing_record = await self._load_takeover_record_by_request_id(
                    request_id=request_id,
                    user_id=user_id,
                )
                if existing_record is not None:
                    existing = self._cache_takeover(
                        self._hydrate_takeover(existing_record)
                    )
                    existing = await self._expire_takeover_if_needed(existing)
                    if existing.state in ACTIVE_TAKEOVER_STATES:
                        existing.mode = normalize_takeover_mode(mode)
                        existing.reason = reason
                        existing.request_id = request_id or existing.request_id
                        existing.task_id = (
                            str(task_id) if task_id is not None else existing.task_id
                        )
                        existing.run_id = (
                            str(run_id) if run_id is not None else existing.run_id
                        )
                        existing.action_type = action_type or existing.action_type
                        existing = await self._save_takeover_record(existing)

                        session = await self.get_session(existing.session_id)
                        if (
                            session.current_takeover_id != existing.takeover_id
                            or not session.human_takeover_lock
                            or session.session_state != AioSessionState.TAKEOVER_FROZEN
                        ):
                            session.current_takeover_id = existing.takeover_id
                            session.human_takeover_lock = True
                            session.session_state = AioSessionState.TAKEOVER_FROZEN
                            await self._save_session_record(session)
                        return existing
                    # Terminal takeovers must not be revived in-place.
                    # Reopen requires a newly issued bundle so old URLs become invalid.
            session = await self.get_session(session_id)
            session.browser_info = await self._build_client_for_base_url(
                session.base_url
            ).get_browser_info()
            now = datetime.now(timezone.utc)
            takeover = SpectaAioTakeover(
                takeover_id=f"takeover_{uuid4().hex}",
                session_id=session.session_id,
                workspace_id=session.workspace_id,
                user_id=user_id,
                platform=platform,
                mode=normalize_takeover_mode(mode),
                reason=reason,
                state=AioTakeoverState.ISSUED,
                frontend_id=None,
                requested_at=now,
                issued_at=now,
                expires_at=now
                + timedelta(seconds=settings.AIO_TAKEOVER_ISSUED_TTL_SECONDS),
                request_id=request_id,
                task_id=task_id,
                run_id=run_id,
                action_type=action_type,
            )
            session.current_takeover_id = takeover.takeover_id
            session.human_takeover_lock = True
            session.session_state = AioSessionState.TAKEOVER_FROZEN
            await self._save_session_record(session)
            return await self._save_takeover_record(takeover)

    async def _expire_takeover_if_needed(
        self, takeover: SpectaAioTakeover
    ) -> SpectaAioTakeover:
        now = datetime.now(timezone.utc)
        if takeover.state not in ACTIVE_TAKEOVER_STATES:
            return takeover
        if now < takeover.expires_at:
            return takeover
        takeover.state = AioTakeoverState.EXPIRED
        session = await self.get_session(takeover.session_id)
        session.current_takeover_id = None
        session.human_takeover_lock = False
        session.session_state = (
            AioSessionState.LEASED if session.ref_count > 0 else AioSessionState.READY
        )
        await self._save_session_record(session)
        return await self._save_takeover_record(takeover)

    async def expire_takeover(self, takeover_id: str) -> SpectaAioTakeover:
        async with self._lock:
            takeover = await self.get_takeover(takeover_id)
            if takeover.state not in ACTIVE_TAKEOVER_STATES:
                return takeover
            takeover.state = AioTakeoverState.EXPIRED
            session = await self.get_session(takeover.session_id)
            session.current_takeover_id = None
            session.human_takeover_lock = False
            session.session_state = (
                AioSessionState.LEASED
                if session.ref_count > 0
                else AioSessionState.READY
            )
            await self._save_session_record(session)
            return await self._save_takeover_record(takeover)

    async def get_takeover(self, takeover_id: str) -> SpectaAioTakeover:
        takeover = self._takeovers_by_id.get(takeover_id)
        if takeover is None:
            record = await self._load_takeover_record(takeover_id)
            if record is None:
                raise KeyError(f"AIO takeover not found: {takeover_id}")
            takeover = self._cache_takeover(self._hydrate_takeover(record))
        return await self._expire_takeover_if_needed(takeover)

    async def get_takeover_by_request_id(
        self, *, request_id: str, user_id: str
    ) -> SpectaAioTakeover | None:
        for takeover in self._takeovers_by_id.values():
            if takeover.request_id == request_id and takeover.user_id == user_id:
                return await self._expire_takeover_if_needed(takeover)

        record = await self._load_takeover_record_by_request_id(
            request_id=request_id,
            user_id=user_id,
        )
        if record is None:
            return None
        return await self._expire_takeover_if_needed(
            self._cache_takeover(self._hydrate_takeover(record))
        )

    async def heartbeat_takeover(
        self,
        *,
        takeover_id: str,
        user_id: str,
        frontend_id: str,
        mode: str,
    ) -> SpectaAioTakeover:
        async with self._lock:
            takeover = await self.get_takeover(takeover_id)
            if takeover.user_id != user_id:
                raise PermissionError("当前用户无权操作该 takeover")
            if takeover.state not in ACTIVE_TAKEOVER_STATES:
                return takeover
            if takeover.frontend_id and takeover.frontend_id != frontend_id:
                raise PermissionError("该 takeover 已被另一个前端占用")
            takeover.frontend_id = frontend_id
            takeover.mode = normalize_takeover_mode(mode)
            takeover.state = AioTakeoverState.ACTIVE
            now = datetime.now(timezone.utc)
            takeover.last_heartbeat_at = now
            takeover.expires_at = now + timedelta(
                seconds=settings.AIO_TAKEOVER_HEARTBEAT_TTL_SECONDS
            )
            session = await self.get_session(takeover.session_id)
            session.current_takeover_id = takeover.takeover_id
            session.human_takeover_lock = True
            session.session_state = AioSessionState.TAKEOVER_FROZEN
            await self._save_session_record(session)
            return await self._save_takeover_record(takeover)

    async def open_takeover(
        self,
        *,
        takeover_id: str,
        user_id: str,
        frontend_id: str | None,
        mode: str,
    ) -> SpectaAioTakeover:
        takeover = await self.get_takeover(takeover_id)
        if takeover.user_id != user_id:
            raise PermissionError("当前用户无权操作该 takeover")

        normalized_mode = normalize_takeover_mode(mode)
        if takeover.state in ACTIVE_TAKEOVER_STATES:
            async with self._lock:
                takeover = await self.get_takeover(takeover_id)
                if takeover.user_id != user_id:
                    raise PermissionError("当前用户无权操作该 takeover")
                if takeover.state not in ACTIVE_TAKEOVER_STATES:
                    return takeover
                takeover.mode = normalized_mode
                takeover.frontend_id = frontend_id or takeover.frontend_id
                takeover.state = AioTakeoverState.ISSUED
                takeover.last_heartbeat_at = None
                takeover.expires_at = datetime.now(timezone.utc) + timedelta(
                    seconds=settings.AIO_TAKEOVER_ISSUED_TTL_SECONDS
                )
                session = await self.get_session(takeover.session_id)
                session.current_takeover_id = takeover.takeover_id
                session.human_takeover_lock = True
                session.session_state = AioSessionState.TAKEOVER_FROZEN
                await self._save_session_record(session)
                return await self._save_takeover_record(takeover)

        return await self.create_takeover_access(
            session_id=takeover.session_id,
            user_id=user_id,
            platform=takeover.platform,
            mode=normalized_mode,
            reason=takeover.reason,
            request_id=takeover.request_id,
            task_id=takeover.task_id,
            run_id=takeover.run_id,
            action_type=takeover.action_type,
        )

    async def maybe_autoresolve_takeover(
        self,
        *,
        takeover_id: str,
        user_id: str,
        frontend_id: str,
    ) -> tuple[SpectaAioTakeover, bool]:
        takeover = await self.get_takeover(takeover_id)
        if takeover.user_id != user_id:
            raise PermissionError("当前用户无权操作该 takeover")
        if takeover.frontend_id and takeover.frontend_id != frontend_id:
            raise PermissionError("该 takeover 不属于当前前端实例")
        return takeover, False

    async def resolve_takeover(
        self,
        *,
        takeover_id: str,
        user_id: str,
        frontend_id: str,
    ) -> SpectaAioTakeover:
        takeover = await self.get_takeover(takeover_id)
        if takeover.user_id != user_id:
            raise PermissionError("当前用户无权操作该 takeover")
        if takeover.frontend_id and takeover.frontend_id != frontend_id:
            raise PermissionError("该 takeover 不属于当前前端实例")
        if takeover.state not in ACTIVE_TAKEOVER_STATES:
            return takeover

        async with self._lock:
            takeover = await self.get_takeover(takeover_id)
            if takeover.user_id != user_id:
                raise PermissionError("当前用户无权操作该 takeover")
            if takeover.frontend_id and takeover.frontend_id != frontend_id:
                raise PermissionError("该 takeover 不属于当前前端实例")
            if takeover.state not in ACTIVE_TAKEOVER_STATES:
                return takeover
            takeover.state = AioTakeoverState.RESOLVED
            session = await self.get_session(takeover.session_id)
            session.current_takeover_id = None
            session.human_takeover_lock = False
            session.session_state = (
                AioSessionState.LEASED
                if session.ref_count > 0
                else AioSessionState.READY
            )
            await self._save_session_record(session)
            return await self._save_takeover_record(takeover)

    async def cancel_takeover(
        self,
        *,
        takeover_id: str,
        user_id: str,
        frontend_id: str | None = None,
    ) -> SpectaAioTakeover:
        async with self._lock:
            takeover = await self.get_takeover(takeover_id)
            if takeover.user_id != user_id:
                raise PermissionError("当前用户无权操作该 takeover")
            if (
                takeover.frontend_id
                and frontend_id
                and takeover.frontend_id != frontend_id
            ):
                raise PermissionError("该 takeover 不属于当前前端实例")
            takeover.state = AioTakeoverState.CANCELLED
            session = await self.get_session(takeover.session_id)
            session.current_takeover_id = None
            session.human_takeover_lock = False
            session.session_state = (
                AioSessionState.LEASED
                if session.ref_count > 0
                else AioSessionState.READY
            )
            await self._save_session_record(session)
            return await self._save_takeover_record(takeover)


aio_session_manager = AioSandboxSessionManager()
