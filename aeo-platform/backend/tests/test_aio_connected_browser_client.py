from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.fetchers.browser.aio_connected_client import AioConnectedBrowserClient


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
