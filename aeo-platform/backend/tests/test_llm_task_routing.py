from __future__ import annotations

from types import SimpleNamespace

from app.core.llm import ToolCallBlock
from app.core.llm.deepseek import DeepSeekConfig, DeepSeekModel
from app.core.llm import task_routing
from app.workflow.orchestrator_node import _build_orchestrator_assistant_message


def test_orchestrator_routes_to_deepseek_pro_thinking(monkeypatch):
    calls = []
    monkeypatch.setattr(
        task_routing,
        "get_settings",
        lambda: SimpleNamespace(
            ORCHESTRATOR_LLM_PROVIDER="deepseek",
            ORCHESTRATOR_MODEL_NAME="deepseek-v4-pro",
            ORCHESTRATOR_THINKING_ENABLED=True,
        ),
    )
    monkeypatch.setattr(
        task_routing,
        "get_llm_model",
        lambda **kwargs: calls.append(kwargs) or object(),
    )

    task_routing.get_orchestrator_llm_model()

    assert calls == [
        {
            "provider": "deepseek",
            "model_name": "deepseek-v4-pro",
            "thinking_enabled": True,
        }
    ]


def test_long_text_routes_to_deepseek_pro_thinking(monkeypatch):
    calls = []
    monkeypatch.setattr(
        task_routing,
        "get_settings",
        lambda: SimpleNamespace(
            LONG_TEXT_LLM_PROVIDER="deepseek",
            LONG_TEXT_MODEL_NAME="deepseek-v4-pro",
            LONG_TEXT_THINKING_ENABLED=True,
        ),
    )
    monkeypatch.setattr(
        task_routing,
        "get_llm_model",
        lambda **kwargs: calls.append(kwargs) or object(),
    )

    task_routing.get_long_text_llm_model()

    assert calls == [
        {
            "provider": "deepseek",
            "model_name": "deepseek-v4-pro",
            "thinking_enabled": True,
        }
    ]


def test_a1_routes_to_glm5(monkeypatch):
    calls = []
    monkeypatch.setattr(
        task_routing,
        "get_settings",
        lambda: SimpleNamespace(
            A1_LLM_PROVIDER="glm5",
            A1_MODEL_NAME="glm-5",
            A1_THINKING_ENABLED=True,
        ),
    )
    monkeypatch.setattr(
        task_routing,
        "get_llm_model",
        lambda **kwargs: calls.append(kwargs) or object(),
    )

    task_routing.get_a1_llm_model()

    assert calls == [
        {
            "provider": "glm5",
            "model_name": "glm-5",
            "thinking_enabled": True,
        }
    ]


def test_fast_structured_disables_thinking_even_for_deepseek(monkeypatch):
    calls = []
    monkeypatch.setattr(
        task_routing,
        "get_settings",
        lambda: SimpleNamespace(
            FAST_STRUCTURED_LLM_PROVIDER="deepseek",
            FAST_STRUCTURED_MODEL_NAME="deepseek-v4-pro",
            FAST_STRUCTURED_THINKING_ENABLED=False,
        ),
    )
    monkeypatch.setattr(
        task_routing,
        "get_llm_model",
        lambda **kwargs: calls.append(kwargs) or object(),
    )

    task_routing.get_fast_structured_llm_model()

    assert calls == [
        {
            "provider": "deepseek",
            "model_name": "deepseek-v4-pro",
            "thinking_enabled": False,
        }
    ]


def test_deepseek_messages_preserve_reasoning_content():
    model = DeepSeekModel(DeepSeekConfig(api_key="test-key", thinking_enabled=True))

    messages = [
        {
            "role": "assistant",
            "content": "",
            "reasoning_content": "需要调用工具。",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "answer_fetch", "arguments": "{}"},
                }
            ],
        }
    ]

    assert model._build_messages(messages)[0]["reasoning_content"] == "需要调用工具。"


def test_deepseek_thinking_converts_legacy_tool_call_without_reasoning():
    model = DeepSeekModel(DeepSeekConfig(api_key="test-key", thinking_enabled=True))

    messages = [
        {
            "role": "assistant",
            "content": "我先调用工具。",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "answer_fetch", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "工具完成。",
        },
        {"role": "user", "content": "继续"},
    ]

    built = model._build_messages(messages)

    assert built[0]["role"] == "assistant"
    assert "tool_calls" not in built[0]
    assert built[1]["role"] == "assistant"
    assert built[2]["role"] == "user"


def test_deepseek_repairs_orphan_tool_message():
    model = DeepSeekModel(DeepSeekConfig(api_key="test-key", thinking_enabled=True))

    built = model._build_messages(
        [
            {
                "role": "tool",
                "tool_call_id": "call_orphan",
                "content": "等待用户选择采集模式...",
            },
            {"role": "user", "content": "继续"},
        ]
    )

    assert built[0]["role"] == "assistant"
    assert "tool_call_id" not in built[0]
    assert built[1]["role"] == "user"


def test_deepseek_repairs_mismatched_tool_call_id_with_reasoning():
    model = DeepSeekModel(DeepSeekConfig(api_key="test-key", thinking_enabled=True))

    built = model._build_messages(
        [
            {
                "role": "assistant",
                "content": "",
                "reasoning_content": "需要调用工具。",
                "tool_calls": [
                    {
                        "id": "call_expected",
                        "type": "function",
                        "function": {"name": "answer_fetch", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "defense_fetch_1",
                "content": "等待用户选择采集模式...",
            },
        ]
    )

    assert built[0]["tool_calls"][0]["id"] == "call_expected"
    assert built[1]["role"] == "tool"
    assert built[1]["tool_call_id"] == "call_expected"


def test_deepseek_non_thinking_keeps_valid_tool_calls_without_reasoning():
    model = DeepSeekModel(DeepSeekConfig(api_key="test-key", thinking_enabled=False))

    built = model._build_messages(
        [
            {
                "role": "assistant",
                "content": "调用工具。",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "answer_fetch", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "完成。"},
        ]
    )

    assert built[0]["tool_calls"][0]["id"] == "call_1"
    assert built[1]["role"] == "tool"


def test_deepseek_thinking_drops_sampling_temperature():
    model = DeepSeekModel(DeepSeekConfig(api_key="test-key", thinking_enabled=True))
    request_kwargs = model.config.to_completion_kwargs()
    request_kwargs["temperature"] = 0.3

    model._drop_sampling_kwargs_for_thinking(request_kwargs)

    assert request_kwargs["extra_body"]["thinking"]["type"] == "enabled"
    assert "temperature" not in request_kwargs


def test_orchestrator_assistant_message_preserves_reasoning_for_tool_call():
    message = _build_orchestrator_assistant_message(
        reply_text="我会继续执行。",
        raw_thinking_text="需要调用 answer_fetch。",
        tool_call_result=ToolCallBlock(
            id="call_1",
            name="answer_fetch",
            arguments={"fetch_mode": "fast"},
        ),
    )

    assert message["reasoning_content"] == "需要调用 answer_fetch。"
    assert message["tool_calls"][0]["function"]["name"] == "answer_fetch"


def test_orchestrator_assistant_message_omits_reasoning_without_tool_call():
    message = _build_orchestrator_assistant_message(
        reply_text="这是直接回复。",
        raw_thinking_text="不需要工具。",
        tool_call_result=None,
    )

    assert "reasoning_content" not in message
    assert "tool_calls" not in message
