"""P2 knife 1: pure helpers extracted from orchestrator_node."""

from __future__ import annotations

from app.workflow.orchestrator.message_builders import (
    _build_orchestrator_assistant_message,
    _inject_runtime_reminder_message,
)
from app.workflow.orchestrator.report_state import _is_completed_analysis_report_state
from app.workflow.orchestrator.run_context import (
    _get_latest_user_message,
    get_recipe_meta_from_state,
    parse_recipe_meta_from_mapping,
)
from app.workflow.orchestrator.text_normalize import (
    _compact_text,
    _contains_non_negated_keyword,
    _normalize_public_report_kind,
    _normalize_internal_analysis_mode,
)
from app.workflow.orchestrator.thought_stream import _normalize_thought_text_for_stream
from app.workflow.orchestrator_node import (
    _compact_text as node_compact,
    _is_completed_analysis_report_state as node_report_done,
)


def test_text_normalize_report_kind():
    assert _normalize_public_report_kind("baseline") == "panorama"
    assert _normalize_public_report_kind("persona") == "scenario"
    assert _normalize_internal_analysis_mode("panorama") == "baseline"


def test_compact_and_keyword():
    assert _compact_text("a" * 20, 10).endswith("…")
    assert _contains_non_negated_keyword("请跳过豆包", ["跳过"])
    assert not _contains_non_negated_keyword("不要跳过豆包", ["跳过"])


def test_report_completed_state():
    assert _is_completed_analysis_report_state(
        {
            "execution_status": "completed",
            "current_step": "A5",
            "report": {"ok": True},
        }
    )
    assert not _is_completed_analysis_report_state(
        {"execution_status": "running", "current_step": "A5", "report": {"ok": True}}
    )


def test_run_context_recipe_and_message():
    assert parse_recipe_meta_from_mapping(
        {"recipe_id": "r1", "recipe_name": "三平台"}
    ) == {"recipe_id": "r1", "recipe_name": "三平台"}
    assert get_recipe_meta_from_state(
        {"input_scope": {"recipe_id": "r2", "recipe_name": "全平台"}}
    )["recipe_name"] == "全平台"
    assert (
        _get_latest_user_message(
            {
                "orchestrator_history": [
                    {"role": "assistant", "content": "hi"},
                    {"role": "user", "content": "跳过豆包"},
                ]
            }
        )
        == "跳过豆包"
    )


def test_message_builders():
    msg = _build_orchestrator_assistant_message(
        reply_text="好的",
        tool_call_result=None,
        raw_thinking_text="think",
    )
    assert msg["role"] == "assistant"
    assert msg["content"] == "好的"
    injected = _inject_runtime_reminder_message(
        [{"role": "system", "content": "s"}],
        "reminder",
    )
    assert any(m.get("content") == "reminder" for m in injected)


def test_thought_stream_filters_english():
    text, flag = _normalize_thought_text_for_stream(
        "Calling the tool now for analysis",
        placeholder_sent=False,
    )
    assert text is None
    text2, _ = _normalize_thought_text_for_stream("开始分析品牌", placeholder_sent=False)
    assert text2 == "开始分析品牌"


def test_reexport_identity_from_orchestrator_node():
    assert node_compact is _compact_text or node_compact("x", 10) == _compact_text("x", 10)
    assert node_report_done(
        {"execution_status": "completed", "current_step": "A5", "report": {"a": 1}}
    )
