from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.core.fetchers.browser.deepseek_handler import DeepSeekHandler


def test_deepseek_gui_actions_requires_aio_session(monkeypatch):
    monkeypatch.setattr(settings, "DEEPSEEK_AIO_INTERACTION_MODE", "gui_actions")

    handler_without_aio = DeepSeekHandler(client=SimpleNamespace(page=None))
    handler_with_aio = DeepSeekHandler(
        client=SimpleNamespace(page=None, aio_session_id="aio-session-1")
    )

    assert handler_without_aio._should_use_aio_gui_actions() is False
    assert handler_without_aio._interaction_metadata()["interaction_mode"] == "cdp_dom"
    assert handler_with_aio._should_use_aio_gui_actions() is True
    assert handler_with_aio._interaction_metadata()["interaction_mode"] == "gui_actions"


@pytest.mark.asyncio
async def test_deepseek_submit_uses_aio_gui_actions(monkeypatch):
    monkeypatch.setattr(settings, "DEEPSEEK_AIO_INTERACTION_MODE", "gui_actions")
    actions: list[dict] = []

    async def _execute_action(*, action_payload):
        actions.append(action_payload)
        return {"status": "ok", "detail": {"success": True}}

    handler = DeepSeekHandler(
        client=SimpleNamespace(
            page=SimpleNamespace(evaluate=AsyncMock()),
            aio_session_id="aio-session-1",
        )
    )
    handler._aio_backend = SimpleNamespace(execute_action=_execute_action)
    handler._deepseek_input_rect_for_gui_actions = AsyncMock(
        return_value={"gui_x": 640, "gui_y": 880}
    )
    handler._submission_looks_started = AsyncMock(return_value=True)

    submitted = await handler._submit_question_via_aio_gui_actions(
        "test question",
        {"message_count": 0, "answer_count": 0},
    )

    assert submitted is True
    assert [action["action_type"] for action in actions] == [
        "MOVE_TO",
        "CLICK",
        "HOTKEY",
        "TYPING",
        "PRESS",
    ]
    assert actions[1] == {"action_type": "CLICK", "x": 640, "y": 880}
    assert actions[3]["text"] == "test question"
    assert actions[3]["use_clipboard"] is True
    assert actions[4] == {"action_type": "PRESS", "key": "Enter"}


@pytest.mark.asyncio
async def test_deepseek_search_toggle_uses_aio_gui_click(monkeypatch):
    monkeypatch.setattr(settings, "DEEPSEEK_AIO_INTERACTION_MODE", "gui_actions")
    actions: list[dict] = []

    async def _execute_action(*, action_payload):
        actions.append(action_payload)
        return {"status": "ok", "detail": {"success": True}}

    page = SimpleNamespace(
        evaluate=AsyncMock(
            return_value={
                "toolbarBtns": [
                    {
                        "txt": "DeepThink",
                        "pressed": "false",
                        "cls": "ds-toggle",
                        "rect": {"gui_x": 500, "gui_y": 900},
                    },
                    {
                        "txt": "联网搜索",
                        "pressed": "false",
                        "cls": "ds-toggle",
                        "rect": {"gui_x": 600, "gui_y": 900},
                    },
                ]
            }
        )
    )
    handler = DeepSeekHandler(
        client=SimpleNamespace(page=page, aio_session_id="aio-session-1")
    )
    handler._aio_backend = SimpleNamespace(execute_action=_execute_action)

    await handler._ensure_web_search_on_via_aio_gui_actions()

    assert actions == [
        {"action_type": "MOVE_TO", "x": 600, "y": 900},
        {"action_type": "CLICK", "x": 600, "y": 900},
    ]


@pytest.mark.asyncio
async def test_deepseek_runtime_retry_marker_is_terminal_page_failure():
    handler = DeepSeekHandler(
        client=SimpleNamespace(page=None, aio_session_id="aio-session-1")
    )
    handler._browser_agent_text_snapshot_provider = AsyncMock(
        return_value="DeepSeek 页面提示：当前浏览器运行环境异常，请检查网络后重试"
    )
    handler._capture_failure_evidence = AsyncMock(
        return_value={"evidence_id": "deepseek-runtime-risk"}
    )

    events, handled = await handler._handle_browser_agent_empty_answer(
        "",
        progress=0.92,
        fallback_url=handler.URL,
    )

    assert handled is True
    assert len(events) == 1
    event = events[0]
    assert event.error_type == "page_runtime_retry_or_risk_control"
    assert event.failure_reason == "page_runtime_retry_or_risk_control"
    assert event.failure_layer == "adapter"
    assert event.retryable is False
    assert event.evidence_ref == {"evidence_id": "deepseek-runtime-risk"}
    handler._capture_failure_evidence.assert_awaited_once()
