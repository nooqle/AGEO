from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.core.fetchers.browser import aio_backend as aio_backend_module
from app.core.fetchers.browser.aio_backend import AioSandboxBackend
from app.core.fetchers.browser.aio_client import AioBrowserActionResult


@pytest.mark.asyncio
async def test_aio_backend_normalizes_playwright_enter_key(monkeypatch):
    captured: dict = {}

    async def _execute_browser_action(payload):
        captured.update(payload)
        return AioBrowserActionResult(
            status="success",
            action_performed="PRESS",
            detail={"status": "success"},
        )

    runtime_client = type(
        "RuntimeClient",
        (),
        {"execute_browser_action": AsyncMock(side_effect=_execute_browser_action)},
    )()
    monkeypatch.setattr(
        aio_backend_module.aio_session_manager,
        "get_runtime_client",
        lambda: runtime_client,
    )

    original = {"action_type": "PRESS", "key": "Enter"}
    result = await AioSandboxBackend().execute_action(action_payload=original)

    assert captured == {"action_type": "PRESS", "key": "enter"}
    assert original == {"action_type": "PRESS", "key": "Enter"}
    assert result["status"] == "success"


def test_aio_backend_leaves_non_keyboard_action_payload_unchanged():
    payload = {"action_type": "CLICK", "x": 10, "y": 20}

    normalized = AioSandboxBackend._normalize_browser_action_payload(payload)

    assert normalized == payload
    assert normalized is not payload
