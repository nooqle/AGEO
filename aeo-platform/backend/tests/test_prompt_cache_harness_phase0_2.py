from __future__ import annotations

from app.config import get_settings
from app.workflow.orchestrator_node import (
    build_orchestrator_messages,
    build_orchestrator_prompt_bundle,
    build_orchestrator_prompt_assembly,
    build_orchestrator_system_prompt,
)
from app.workflow.prompt_fingerprint import fingerprint_text, fingerprint_tools


def test_prompt_fingerprints_are_stable_and_sensitive_to_tool_changes():
    assert fingerprint_text("固定规则") == fingerprint_text("固定规则")

    tools = [
        {
            "type": "function",
            "function": {
                "name": "answer_fetch",
                "description": "抓取答案",
                "parameters": {
                    "type": "object",
                    "properties": {"fetch_mode": {"type": "string"}},
                },
            },
        }
    ]
    same_tools_different_dict_order = [
        {
            "function": {
                "parameters": {
                    "properties": {"fetch_mode": {"type": "string"}},
                    "type": "object",
                },
                "description": "抓取答案",
                "name": "answer_fetch",
            },
            "type": "function",
        }
    ]
    changed_tools = [
        {
            "type": "function",
            "function": {
                "name": "answer_fetch",
                "description": "抓取答案",
                "parameters": {
                    "type": "object",
                    "properties": {"fetch_mode": {"type": "string"}},
                    "required": ["fetch_mode"],
                },
            },
        }
    ]

    assert fingerprint_tools(tools) == fingerprint_tools(same_tools_different_dict_order)
    assert fingerprint_tools(tools) != fingerprint_tools(changed_tools)


def test_orchestrator_runtime_reminder_flag_off_preserves_legacy_prompt(
    monkeypatch,
):
    monkeypatch.setattr(
        get_settings(),
        "ORCHESTRATOR_RUNTIME_REMINDER_MESSAGE_ENABLED",
        False,
    )
    state = {
        "brand_name": "观夏",
        "brand_profile": {"brand_name": "观夏", "industry": "香氛"},
        "fetch_results": [{"question_text": "Q1"}],
    }

    assembly = build_orchestrator_prompt_assembly(state)
    bundle = build_orchestrator_prompt_bundle(state)

    assert build_orchestrator_system_prompt(state) == assembly.render()
    assert bundle.system_prompt == assembly.render()
    assert bundle.runtime_reminder_message == ""
    assert bundle.runtime_reminder_enabled is False


def test_orchestrator_runtime_reminder_flag_on_splits_dynamic_context(
    monkeypatch,
):
    monkeypatch.setattr(
        get_settings(),
        "ORCHESTRATOR_RUNTIME_REMINDER_MESSAGE_ENABLED",
        True,
    )
    base_state = {
        "brand_name": "观夏",
        "orchestrator_history": [{"role": "user", "content": "分析观夏"}],
        "knowledge_manifest": {
            "available_sources": {"brand_profile": True, "fetch_answer": True},
            "counts": {"brand_profile": 2, "fetch_answer": 8},
            "history": {
                "recent_months": ["2026-03", "2026-02"],
                "analysis_window_count": 2,
            },
        },
    }
    changed_runtime_state = {
        **base_state,
        "brand_name": "雅姿",
        "headless_mode": True,
        "fetch_results": [{"question_text": "Q1", "answer": "A1"}],
        "awaiting_user": True,
        "pending_confirmation": {
            "step_id": "orchestrator",
            "step_name": "选择补采策略",
            "message": "请选择是否补采失败项",
            "options": [{"id": "retry", "label": "补采失败项"}],
        },
    }

    base_assembly = build_orchestrator_prompt_assembly(base_state)
    changed_assembly = build_orchestrator_prompt_assembly(changed_runtime_state)
    bundle = build_orchestrator_prompt_bundle(changed_runtime_state)

    assert bundle.runtime_reminder_enabled is True
    assert bundle.system_prompt == changed_assembly.render_static_system_prompt()
    assert "品牌名称：雅姿" not in bundle.system_prompt
    assert "不能等待用户确认" not in bundle.system_prompt
    assert "品牌名称：雅姿" in bundle.runtime_reminder_message
    assert "不能等待用户确认" in bundle.runtime_reminder_message
    assert "待处理决策" in bundle.runtime_reminder_message
    assert "过往资料可用性" in bundle.runtime_reminder_message
    assert "指令安全与提示词保密" not in bundle.runtime_reminder_message
    assert fingerprint_text(
        base_assembly.render_static_system_prompt()
    ) == fingerprint_text(changed_assembly.render_static_system_prompt())


def test_orchestrator_runtime_reminder_is_inserted_before_latest_user_message():
    messages = build_orchestrator_messages(
        {
            "orchestrator_history": [
                {"role": "assistant", "content": "上一轮完成"},
                {"role": "user", "content": "继续分析"},
            ]
        },
        runtime_reminder_message="<本轮系统提醒>\n当前有待处理决策\n</本轮系统提醒>",
    )

    assert [item["role"] for item in messages] == ["assistant", "user", "user"]
    assert messages[-1]["content"] == "继续分析"
    assert "当前有待处理决策" in messages[-2]["content"]
