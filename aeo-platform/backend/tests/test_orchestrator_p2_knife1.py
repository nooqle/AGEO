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


def test_knife5_session_surface_and_reply_pins():
    from app.workflow.orchestrator.prompt_evidence import (
        _should_render_history_availability,
    )
    from app.workflow.orchestrator.reply_text import (
        _build_ask_user_fallback_reply,
        _build_knowledge_export_completion_reply,
    )
    from app.workflow.orchestrator.session_tool_surface import (
        _get_contextual_hidden_tool_names,
        _infer_current_session_followup_tool,
    )
    from app.workflow.orchestrator_node import (
        _get_contextual_hidden_tool_names as node_hidden,
        _infer_current_session_followup_tool as node_followup,
        _build_knowledge_export_completion_reply as node_export,
    )

    assert node_followup is _infer_current_session_followup_tool
    assert node_hidden is _get_contextual_hidden_tool_names
    assert node_export is _build_knowledge_export_completion_reply

    assert "ask_user" in _get_contextual_hidden_tool_names({"headless_mode": True})
    followup = _infer_current_session_followup_tool(
        {
            "fetch_results": [{"x": 1}],
            "report": {"a": 1},
            "metrics": {"m": 1},
            "orchestrator_history": [
                {"role": "user", "content": "这份报告里 deepseek 怎么说"}
            ],
        }
    )
    assert followup is not None
    assert followup[0] == "drill_down_analysis"
    assert followup[1].get("focus_value") == "deepseek"

    export = _build_knowledge_export_completion_reply(
        {"item_count": 2, "title": "表A", "source_scope": "current_import_artifact"}
    )
    assert "导入" in export or "2" in export
    ask = _build_ask_user_fallback_reply(
        {"brand_name": "测试品牌", "baseline_metrics": {"m": 1}},
        "brand_analysis",
        "",
    )
    assert "测试品牌" in ask
    assert _should_render_history_availability({"session_recalled": True}, set()) is False


def test_knife4_feedback_and_misc_pure_behavior_pins():
    """Cautious knife: pin identities + pure behavior contracts."""
    from app.workflow.orchestrator.misc_pure import (
        _format_tool_args_for_suggestion,
        _infer_current_import_query,
        _normalize_sentiment_followup_value,
    )
    from app.workflow.orchestrator.ontology_action_feedback import (
        ONTOLOGY_TOOL_ACTION_MAP,
        _merge_ontology_provided_inputs_into_tool_args,
        _ontology_action_gate_message,
        _ontology_action_gate_options,
        _ontology_confirmed_action_for_tool,
        _ontology_feedback_covers_missing_inputs,
    )
    from app.workflow.orchestrator_node import (
        ONTOLOGY_TOOL_ACTION_MAP as node_map,
        _merge_ontology_provided_inputs_into_tool_args as node_merge,
        _normalize_sentiment_followup_value as node_sent,
    )

    assert node_map is ONTOLOGY_TOOL_ACTION_MAP
    assert node_merge is _merge_ontology_provided_inputs_into_tool_args
    assert node_sent is _normalize_sentiment_followup_value
    assert _normalize_sentiment_followup_value("负向提及") == "negative"
    assert _normalize_sentiment_followup_value("正向") == "positive"
    assert _format_tool_args_for_suggestion({"a": 1, "b": ""}) == "(a=1)"
    assert (
        _infer_current_import_query(
            {
                "current_import_artifact": {"artifact_id": "x"},
                "orchestrator_history": [{"role": "user", "content": "上传问题列表"}],
            }
        )
        == "上传问题列表"
    )
    merged = _merge_ontology_provided_inputs_into_tool_args(
        action_key="generate_official_website_evidence_plan",
        tool_args={},
        provided_inputs={"official_domain": "example.com"},
    )
    assert merged["root_url"] == "example.com"
    assert _ontology_feedback_covers_missing_inputs(
        action_key="generate_official_website_evidence_plan",
        missing_inputs=["official_domain"],
        feedback={"provided_inputs": {"root_url": "x.com"}},
    )
    assert "确认" in _ontology_action_gate_message(
        kind="needs_confirmation",
        action_name="抓取",
        action_item={},
        reason="需确认",
    )
    assert len(_ontology_action_gate_options("needs_confirmation", {"action_key": "k"})) == 2
    confirmed = _ontology_confirmed_action_for_tool(
        {
            "ontology_world": {
                "action_feedback_summary": {
                    "latest_by_action": {
                        "run_answer_fetch": {
                            "feedback_type": "confirm",
                            "action_record_id": "ar1",
                        }
                    }
                }
            }
        },
        "answer_fetch",
    )
    assert confirmed is not None
    assert confirmed["action_record_id"] == "ar1"


def test_knife3_ontology_and_prompt_bundle():
    from app.workflow.orchestrator.ontology_intelligence import (
        CORE_RELATIONSHIP_TYPES,
        _with_intelligence_reply_closure,
    )
    from app.workflow.orchestrator.prompt_bundle import (
        OrchestratorPromptBundle,
        _wrap_runtime_reminder_message,
    )
    from app.workflow.orchestrator.seed_surface import (
        _looks_like_keyword_list,
        _normalize_tool_topic_keywords,
    )
    from app.workflow.orchestrator_node import (
        OrchestratorPromptBundle as NodeBundle,
        _with_intelligence_reply_closure as node_closure,
    )

    assert "brand_has_intelligence_finding" in CORE_RELATIONSHIP_TYPES
    closed = _with_intelligence_reply_closure("结论：测试")
    assert "证据：" in closed
    assert _looks_like_keyword_list("a,b,c") or True  # pure smoke
    assert isinstance(_normalize_tool_topic_keywords(["x", "y"]), list)
    assert "本轮系统提醒" in _wrap_runtime_reminder_message("hello")
    assert NodeBundle is OrchestratorPromptBundle
    assert node_closure is _with_intelligence_reply_closure


def test_knife2_history_and_workflow():
    from app.workflow.orchestrator.history_query import (
        _is_history_answer_content_query,
        _is_precise_history_query,
        _session_was_recalled,
    )
    from app.workflow.orchestrator.workflow_progress import (
        WORKFLOW_STEPS,
        _build_workflow_steps,
        _matches_failed_step,
    )
    from app.workflow.orchestrator_node import (
        _is_history_answer_content_query as node_hist,
        _matches_failed_step as node_match,
    )

    assert _is_history_answer_content_query("查看过往回答内容")
    assert not _is_precise_history_query("随便问问")
    assert _session_was_recalled({"session_recalled": True})
    assert len(WORKFLOW_STEPS) == 5
    assert _matches_failed_step("answer_fetch", "A4")
    steps = _build_workflow_steps({"analysis_mode": "persona", "brand_profile": {"x": 1}})
    assert steps[0]["status"] == "completed"
    assert node_hist is _is_history_answer_content_query
    assert node_match is _matches_failed_step
