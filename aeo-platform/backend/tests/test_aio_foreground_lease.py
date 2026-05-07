from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.services.aio_foreground_lease import (
    AioForegroundLeaseManager,
    AioForegroundLeaseTimeout,
)


@pytest.mark.asyncio
async def test_human_takeover_waits_for_current_gui_action(monkeypatch):
    monkeypatch.setattr(settings, "REDIS_URL", None)
    manager = AioForegroundLeaseManager()

    gui_lease = await manager.acquire(
        key="aio_foreground:test",
        mode="gui_automation",
        platform="deepseek",
        owner="task-1:deepseek:submit",
        ttl_seconds=5,
        timeout_seconds=0.1,
    )

    human_task = asyncio.create_task(
        manager.acquire(
            key="aio_foreground:test",
            mode="human_takeover",
            platform="kimi",
            owner="takeover-1",
            ttl_seconds=5,
            timeout_seconds=1.0,
        )
    )

    await asyncio.sleep(0.05)
    assert not human_task.done()

    await manager.release(gui_lease)
    human_lease = await human_task

    assert human_lease.mode == "human_takeover"
    assert human_lease.platform == "kimi"


@pytest.mark.asyncio
async def test_gui_action_times_out_while_human_takeover_holds_foreground(monkeypatch):
    monkeypatch.setattr(settings, "REDIS_URL", None)
    manager = AioForegroundLeaseManager()

    await manager.acquire(
        key="aio_foreground:test",
        mode="human_takeover",
        platform="yuanbao",
        owner="takeover-2",
        ttl_seconds=5,
        timeout_seconds=0.1,
    )

    with pytest.raises(AioForegroundLeaseTimeout):
        await manager.acquire(
            key="aio_foreground:test",
            mode="gui_automation",
            platform="deepseek",
            owner="task-1:deepseek:submit",
            ttl_seconds=5,
            timeout_seconds=0.01,
        )


@pytest.mark.asyncio
async def test_release_still_clears_local_fallback_when_redis_returns_no_match(
    monkeypatch,
):
    monkeypatch.setattr(settings, "REDIS_URL", "redis://example.invalid/0")
    manager = AioForegroundLeaseManager()

    async def _no_redis():
        return None

    manager._get_redis = _no_redis
    lease = await manager.acquire(
        key="aio_foreground:test-fallback-release",
        mode="gui_automation",
        platform="deepseek",
        owner="task-1:deepseek:submit",
        ttl_seconds=5,
        timeout_seconds=0.1,
    )

    class FakeRedis:
        async def eval(self, *args):
            return 0

    async def _fake_redis():
        return FakeRedis()

    manager._get_redis = _fake_redis

    await manager.release(lease)

    assert manager._active_local_lease("aio_foreground:test-fallback-release") is None


@pytest.mark.asyncio
async def test_redis_lease_timeout_does_not_fallback_to_local(monkeypatch):
    monkeypatch.setattr(settings, "REDIS_URL", "redis://example.invalid/0")
    manager = AioForegroundLeaseManager()
    existing = manager._serialize_lease(
        manager._new_lease(
            key="aio_foreground:test-redis-timeout",
            mode="human_takeover",
            platform="kimi",
            owner="takeover-1",
            reason="login",
            ttl_seconds=5,
        )
    )

    class FakeRedis:
        async def set(self, *args, **kwargs):
            return False

        async def get(self, *args, **kwargs):
            return existing

    async def _fake_redis():
        return FakeRedis()

    manager._get_redis = _fake_redis

    with pytest.raises(AioForegroundLeaseTimeout):
        await manager.acquire(
            key="aio_foreground:test-redis-timeout",
            mode="gui_automation",
            platform="deepseek",
            owner="task-1:deepseek:submit",
            ttl_seconds=5,
            timeout_seconds=0.01,
        )

    assert manager._active_local_lease("aio_foreground:test-redis-timeout") is None


@pytest.mark.asyncio
async def test_takeover_bundle_timeout_expires_takeover_and_returns_none(monkeypatch):
    from app.workflow import browser_action_contract

    monkeypatch.setattr(browser_action_contract.settings, "AIO_ENABLED", True)
    monkeypatch.setattr(
        browser_action_contract.settings,
        "AIO_BASE_URL",
        "https://aio.example.test",
    )

    takeover = SimpleNamespace(
        takeover_id="takeover-timeout",
        mode="canvas_cdp",
        expires_at=SimpleNamespace(isoformat=lambda: "2026-05-07T00:00:00+00:00"),
    )
    aio_manager = SimpleNamespace(
        create_takeover_access=AsyncMock(return_value=takeover),
        get_session=AsyncMock(
            return_value=SimpleNamespace(
                base_url="https://aio.example.test",
                sandbox_ref="sandbox-1",
            )
        ),
        expire_takeover=AsyncMock(),
    )
    foreground_manager = SimpleNamespace(
        acquire=AsyncMock(
            side_effect=AioForegroundLeaseTimeout("foreground busy")
        )
    )
    monkeypatch.setattr(
        browser_action_contract,
        "aio_foreground_lease_manager",
        foreground_manager,
    )
    monkeypatch.setitem(
        browser_action_contract.__dict__,
        "_aio_takeover_by_request_id",
        {},
    )
    monkeypatch.setattr(
        "app.services.aio_session_manager.aio_session_manager",
        aio_manager,
    )

    handler = SimpleNamespace(
        URL="https://kimi.com/",
        run_id="run-1",
        client=SimpleNamespace(
            page=None,
            aio_session_id="aio-session-1",
            task_id="task-1",
        ),
    )

    bundle = await browser_action_contract.ensure_aio_takeover_bundle(
        handler=handler,
        user_id="user-1",
        platform="kimi",
        request_id="request-1",
        action_type="login",
        message="请登录",
        target_url="https://kimi.com/",
    )

    assert bundle is None
    aio_manager.expire_takeover.assert_awaited_once_with("takeover-timeout")
    assert "request-1" not in browser_action_contract._aio_takeover_by_request_id


@pytest.mark.asyncio
async def test_takeover_bundle_reservation_error_expires_takeover_and_returns_none(
    monkeypatch,
):
    from app.workflow import browser_action_contract

    monkeypatch.setattr(browser_action_contract.settings, "AIO_ENABLED", True)
    monkeypatch.setattr(
        browser_action_contract.settings,
        "AIO_BASE_URL",
        "https://aio.example.test",
    )

    takeover = SimpleNamespace(
        takeover_id="takeover-error",
        mode="canvas_cdp",
        expires_at=SimpleNamespace(isoformat=lambda: "2026-05-07T00:00:00+00:00"),
    )
    aio_manager = SimpleNamespace(
        create_takeover_access=AsyncMock(return_value=takeover),
        get_session=AsyncMock(
            return_value=SimpleNamespace(
                base_url="https://aio.example.test",
                sandbox_ref="sandbox-1",
            )
        ),
        expire_takeover=AsyncMock(),
    )
    foreground_manager = SimpleNamespace(
        acquire=AsyncMock(side_effect=RuntimeError("foreground failed"))
    )
    monkeypatch.setattr(
        browser_action_contract,
        "aio_foreground_lease_manager",
        foreground_manager,
    )
    monkeypatch.setitem(
        browser_action_contract.__dict__,
        "_aio_takeover_by_request_id",
        {},
    )
    monkeypatch.setattr(
        "app.services.aio_session_manager.aio_session_manager",
        aio_manager,
    )

    handler = SimpleNamespace(
        URL="https://kimi.com/",
        run_id="run-1",
        client=SimpleNamespace(
            page=None,
            aio_session_id="aio-session-1",
            task_id="task-1",
        ),
    )

    bundle = await browser_action_contract.ensure_aio_takeover_bundle(
        handler=handler,
        user_id="user-1",
        platform="kimi",
        request_id="request-1",
        action_type="login",
        message="请登录",
        target_url="https://kimi.com/",
    )

    assert bundle is None
    aio_manager.expire_takeover.assert_awaited_once_with("takeover-error")
    assert "request-1" not in browser_action_contract._aio_takeover_by_request_id
