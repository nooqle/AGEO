from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.workflow import orchestrator_node as orchestrator_module


@pytest.mark.asyncio
async def test_ask_user_without_options_after_a1_gets_next_step_options(monkeypatch):
    events: list[tuple[str, dict]] = []

    async def emit_to_session(_session_id: str, event_type: str, payload: dict) -> None:
        events.append((event_type, payload))

    monkeypatch.setattr(
        orchestrator_module.session_event_publisher,
        "emit_to_session",
        emit_to_session,
    )

    command = await orchestrator_module._handle_tool_call(
        state={
            "session_id": "session-a1-empty-options",
            "next_action": "a1_brand",
            "brand_name": "安利",
            "brand_profile": {"brand_name": "安利"},
            "orchestrator_history": [{"role": "user", "content": "生成品牌档案"}],
        },
        session_id="session-a1-empty-options",
        tool_call=SimpleNamespace(
            name="ask_user",
            arguments={"message": "请选择下一步", "options": []},
            id="call_ask_user_after_a1",
        ),
        reply_text="请选择您想要的下一步。",
        new_history=[],
    )

    assert command.goto == "wait_for_user"
    assert command.update["awaiting_user"] is True
    option_ids = [
        option["id"] for option in command.update["pending_confirmation"]["options"]
    ]
    assert option_ids == ["panorama_fast", "panorama_full", "persona_first", "ask"]
    assert [event_type for event_type, _payload in events] == [
        "inline_confirmation",
        "confirmation_request",
    ]


@pytest.mark.asyncio
async def test_no_tool_call_after_a1_forces_next_step_confirmation(monkeypatch):
    events: list[tuple[str, dict]] = []

    async def emit_to_session(_session_id: str, event_type: str, payload: dict) -> None:
        events.append((event_type, payload))

    class FakeModel:
        def stream(self, **_kwargs):
            yield SimpleNamespace(
                content="品牌档案已生成，请选择您想要的下一步。",
                thinking_blocks=[],
                tool_calls=[],
                finish_reason=None,
                usage=None,
            )
            yield SimpleNamespace(
                content="",
                thinking_blocks=[],
                tool_calls=[],
                finish_reason="stop",
                usage=None,
            )

    monkeypatch.setattr(
        orchestrator_module.session_event_publisher,
        "emit_to_session",
        emit_to_session,
    )
    monkeypatch.setattr(
        orchestrator_module,
        "get_orchestrator_llm_model",
        lambda: FakeModel(),
    )
    monkeypatch.setattr(
        orchestrator_module, "build_agent_tools", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        orchestrator_module,
        "_hydrate_knowledge_manifest",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        orchestrator_module, "send_reply_event", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        orchestrator_module, "send_plan_event", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        orchestrator_module,
        "send_action_log_event",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.workflow.events.send_progress_event",
        AsyncMock(return_value=None),
    )

    command = await orchestrator_module.orchestrator_node(
        {
            "session_id": "session-a1-no-tool",
            "next_action": "a1_brand",
            "current_step": "A1",
            "current_skill": "brand_analysis",
            "brand_name": "安利",
            "brand_profile": {"brand_name": "安利"},
            "execution_status": "completed",
            "orchestrator_history": [{"role": "user", "content": "生成品牌档案"}],
            "user_decisions": {},
        }
    )

    assert command.goto == "wait_for_user"
    assert command.update["pending_confirmation"]["step_name"] == "选择品牌档案下一步"
    option_ids = [
        option["id"] for option in command.update["pending_confirmation"]["options"]
    ]
    assert option_ids == ["panorama_fast", "panorama_full", "persona_first", "ask"]
    assert [event_type for event_type, _payload in events] == [
        "inline_confirmation",
        "confirmation_request",
    ]
