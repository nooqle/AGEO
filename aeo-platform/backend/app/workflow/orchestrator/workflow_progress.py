"""Workflow step progress helpers (P2 knife 2)."""

from __future__ import annotations

from typing import Any, Mapping

from app.workflow.orchestrator.history_query import (
    _is_question_generation_only_state,
)

WORKFLOW_STEPS = [
    ("A1", "品牌信息采集", "brand_profile"),
    ("A2", "用户画像生成", "marketing_personas"),
    ("A3", "问题模拟生成", "simulated_questions"),
    ("A4", "AI答案抓取", "fetch_results"),
    ("A5", "数据分析报告", "metrics"),
]

def _get_tool_name_from_node(node_name: str) -> str | None:
    """Reverse lookup: node name → tool name."""
    preferred = {
        "a5_analytics": "analysis_report_skill",
        "confidence_analysis_executor": "confidence_analysis_skill",
        "a7_confidence_signal": "confidence_analysis_skill",
        "site_confidence_assessment_executor": "site_confidence_assessment_skill",
        "post_analysis_executor": "post_analysis_skill",
    }
    if node_name in preferred:
        return preferred[node_name]
    node_to_tool = {v: k for k, v in TOOL_TO_NODE.items()}
    return node_to_tool.get(node_name)

def _is_completed_question_generation_only_state(state: Mapping[str, Any]) -> bool:
    return (
        _get_tool_name_from_node(state.get("next_action", "") or "")
        == "question_simulation"
        and _is_question_generation_only_state(state)
        and bool(state.get("simulated_questions") or state.get("questions"))
    )

def _build_workflow_steps(state: Mapping[str, Any]) -> list[dict[str, str]]:
    """Build workflow steps list with completion status from state."""
    if _is_question_generation_only_state(state):
        status = "completed" if state.get("simulated_questions") else "pending"
        return [{"id": "A3", "label": "问题模拟生成", "status": status}]

    user_decisions = state.get("user_decisions", {})
    analysis_mode = state.get("analysis_mode", "persona")
    steps = []
    for step_id, label, state_key in WORKFLOW_STEPS:
        # A5 completion check depends on analysis_mode:
        # baseline mode writes to baseline_metrics; persona/default to metrics.
        if step_id == "A5":
            if analysis_mode == "baseline":
                completed = bool(state.get("baseline_metrics"))
            else:
                completed = bool(state.get("metrics"))
        else:
            completed = bool(state.get(state_key))

        if completed:
            status = "completed"
        elif _is_step_skipped(step_id, state, user_decisions):
            status = "skipped"
        else:
            status = "pending"
        steps.append({"id": step_id, "label": label, "status": status})
    return steps

def _is_step_skipped(step_id: str, state: Mapping[str, Any], user_decisions: dict) -> bool:
    """Determine if a step was intentionally skipped."""
    analysis_mode = state.get("analysis_mode")
    if step_id == "A1":
        # A1 is skipped in baseline mode (re-run baseline skips brand analysis)
        if analysis_mode == "baseline":
            return True
    if step_id == "A2":
        # A2 is skipped in baseline mode
        if analysis_mode == "baseline":
            return True
        if user_decisions.get("a3_mode") == "brand":
            return True
        if state.get("simulated_questions") and not state.get("marketing_personas"):
            return True
    return False

def _matches_failed_step(tool_name: str, failed_step: str) -> bool:
    step_id_map = {
        "brand_analysis": "A1",
        "persona_generation": "A2",
        "question_simulation": "A3",
        "answer_fetch": "A4",
        "analysis_report_skill": "A5",
        "data_analytics": "A5",
        "confidence_analysis_skill": "A7",
    }
    expected_step = step_id_map.get(tool_name, "")
    return failed_step in {tool_name, expected_step}

