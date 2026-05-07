from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.fetchers.browser import aio_connected_client as aio_client_module
from app.core.fetchers.browser import playwright_client as playwright_client_module
from app.core.fetchers.browser.aio_connected_client import AioConnectedBrowserClient
from app.services.aio_foreground_lease import aio_foreground_lease_manager


@pytest.mark.asyncio
async def test_aio_connected_browser_client_starts_cdp_driver_without_install(
    monkeypatch,
):
    class FakePatchrightStarter:
        async def start(self):
            return "patchright-driver"

    async def _unexpected_install_check():
        raise AssertionError("AIO CDP attach must not install local Chromium")

    monkeypatch.setattr(
        aio_client_module,
        "async_playwright",
        lambda: FakePatchrightStarter(),
    )
    monkeypatch.setattr(
        playwright_client_module,
        "ensure_playwright_ready",
        _unexpected_install_check,
    )

    client = AioConnectedBrowserClient(
        session_name="aio-test",
        workspace_id="workspace_1",
        task_id="task_1",
        platform="deepseek",
    )

    await client._ensure_playwright()

    assert client.playwright == "patchright-driver"


@pytest.mark.asyncio
async def test_aio_connected_browser_client_sets_cn_locale_for_new_context():
    captured: dict[str, object] = {}

    async def _new_context(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(pages=[])

    client = AioConnectedBrowserClient(
        session_name="aio-test",
        workspace_id="workspace_1",
        task_id="task_1",
        platform="kimi",
    )
    client.browser = SimpleNamespace(
        contexts=[], new_context=AsyncMock(side_effect=_new_context)
    )
    client._load_storage_state = AsyncMock(return_value=None)

    await client._get_or_create_remote_context("https://kimi.com/")

    assert captured["locale"] == "zh-CN"
    assert captured["timezone_id"] == "Asia/Shanghai"
    assert captured["extra_http_headers"] == {
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
    }


@pytest.mark.asyncio
async def test_aio_connected_browser_client_normalizes_macos_ua_to_linux():
    captured: dict[str, object] = {}

    async def _new_context(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(pages=[])

    client = AioConnectedBrowserClient(
        session_name="aio-test",
        workspace_id="workspace_1",
        task_id="task_1",
        platform="deepseek",
    )
    client.browser = SimpleNamespace(
        contexts=[],
        new_context=AsyncMock(side_effect=_new_context),
        version="135.0.7049.78",
    )
    client.browser_info = {
        "user_agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/140.0.0.0 Safari/537.36"
        ),
        "viewport": {"width": 1362, "height": 1042},
    }
    client._load_storage_state = AsyncMock(return_value=None)

    await client._get_or_create_remote_context("https://chat.deepseek.com/")

    assert captured["viewport"] == {"width": 1362, "height": 1042}
    assert captured["user_agent"] == (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.7049.78 Safari/537.36"
    )


@pytest.mark.asyncio
async def test_deepseek_reuses_default_aio_context_without_host_match(monkeypatch):
    monkeypatch.setattr(
        "app.core.fetchers.browser.aio_connected_client.settings."
        "AIO_BROWSER_REUSE_DEFAULT_CONTEXT_PLATFORMS",
        "deepseek",
    )
    existing_context = SimpleNamespace(
        pages=[
            SimpleNamespace(url="about:blank", is_closed=lambda: False),
        ]
    )
    browser = SimpleNamespace(
        contexts=[existing_context],
        new_context=AsyncMock(),
    )
    client = AioConnectedBrowserClient(
        session_name="aio-test",
        workspace_id="workspace_1",
        task_id="task_1",
        platform="deepseek",
    )
    client.browser = browser

    context = await client._get_or_create_remote_context(
        "https://chat.deepseek.com/"
    )

    assert context is existing_context
    assert client._context_owned_by_client is False
    assert client.context_reuse_strategy == "platform_default_context_reuse"
    browser.new_context.assert_not_called()


@pytest.mark.asyncio
async def test_non_strict_platform_still_creates_isolated_context(monkeypatch):
    monkeypatch.setattr(
        "app.core.fetchers.browser.aio_connected_client.settings."
        "AIO_BROWSER_REUSE_DEFAULT_CONTEXT_PLATFORMS",
        "deepseek",
    )
    existing_context = SimpleNamespace(
        pages=[
            SimpleNamespace(url="about:blank", is_closed=lambda: False),
        ]
    )
    created_context = SimpleNamespace(pages=[])
    browser = SimpleNamespace(
        contexts=[existing_context],
        new_context=AsyncMock(return_value=created_context),
    )
    client = AioConnectedBrowserClient(
        session_name="aio-test",
        workspace_id="workspace_1",
        task_id="task_1",
        platform="kimi",
    )
    client.browser = browser
    client._load_storage_state = AsyncMock(return_value=None)

    context = await client._get_or_create_remote_context("https://kimi.com/")

    assert context is created_context
    assert client._context_owned_by_client is True
    assert client.context_reuse_strategy == "isolated_context_created"
    browser.new_context.assert_awaited_once()


@pytest.mark.asyncio
async def test_cdp_only_platform_page_reuse_does_not_request_foreground():
    page = SimpleNamespace(url="https://kimi.com/", is_closed=lambda: False)
    context = SimpleNamespace(pages=[page])
    client = AioConnectedBrowserClient(
        session_name="aio-test",
        workspace_id="workspace_1",
        task_id="task_1",
        platform="kimi",
    )
    client.context = context
    client.bring_to_front = AsyncMock(return_value={"success": True})

    await client._get_or_create_remote_page("https://kimi.com/")

    assert client.page is page
    client.bring_to_front.assert_not_awaited()


@pytest.mark.asyncio
async def test_deepseek_gui_page_reuse_requests_foreground(monkeypatch):
    monkeypatch.setattr(
        "app.core.fetchers.browser.aio_connected_client.settings."
        "DEEPSEEK_AIO_INTERACTION_MODE",
        "gui_actions",
    )
    monkeypatch.setattr(aio_client_module.settings, "REDIS_URL", None)
    page = SimpleNamespace(url="https://chat.deepseek.com/", is_closed=lambda: False)
    context = SimpleNamespace(pages=[page])
    client = AioConnectedBrowserClient(
        session_name="aio-test",
        workspace_id="workspace_1",
        task_id="task_1",
        platform="deepseek",
    )
    client.context = context
    client.bring_to_front = AsyncMock(return_value={"success": True})

    await client._get_or_create_remote_page("https://chat.deepseek.com/")

    assert client.page is page
    client.bring_to_front.assert_awaited_once()


@pytest.mark.asyncio
async def test_deepseek_gui_foreground_respects_human_takeover_lease(monkeypatch):
    monkeypatch.setattr(
        "app.core.fetchers.browser.aio_connected_client.settings."
        "DEEPSEEK_AIO_INTERACTION_MODE",
        "gui_actions",
    )
    monkeypatch.setattr(aio_client_module.settings, "REDIS_URL", None)
    monkeypatch.setattr(
        aio_client_module.settings,
        "AIO_FOREGROUND_GUI_LEASE_WAIT_SECONDS",
        0.01,
    )
    foreground_key = "aio_foreground:test-client-blocked"
    human_lease = await aio_foreground_lease_manager.acquire(
        key=foreground_key,
        mode="human_takeover",
        platform="kimi",
        owner="takeover-1",
        ttl_seconds=5,
        timeout_seconds=0.1,
    )
    client = AioConnectedBrowserClient(
        session_name="aio-test",
        workspace_id="workspace_1",
        task_id="task_1",
        platform="deepseek",
    )
    client.foreground_key = foreground_key
    client.bring_to_front = AsyncMock(return_value={"success": True})

    try:
        result = await client.bring_to_front_for_automation(reason="surface_reuse")
    finally:
        await aio_foreground_lease_manager.release(human_lease)

    assert result["lease_timeout"] is True
    client.bring_to_front.assert_not_awaited()
