"""Tool availability gate (P2 knife 6, cautious)."""

from __future__ import annotations

from typing import Any, Mapping

from app.services.tool_capability_matrix import ToolAvailabilityConstraint
from app.workflow.orchestrator.history_query import _session_was_recalled
from app.workflow.orchestrator.misc_pure import _format_tool_args_for_suggestion
from app.workflow.orchestrator.session_tool_surface import (
    _KNOWLEDGE_TOOL_NAMES,
    _get_contextual_hidden_tool_names,
    _infer_current_session_followup_tool,
)

def validate_tool_available_in_current_state(
    tool_name: str | None,
    state: Mapping[str, Any] | None,
) -> ToolAvailabilityConstraint:
    """Validate whether a stable-surface tool call is allowed this turn."""

    normalized_name = str(tool_name or "").strip()
    if not normalized_name or not state:
        return ToolAvailabilityConstraint(tool_name=normalized_name, blocked=False)

    hidden_tool_names = _get_contextual_hidden_tool_names(state)
    if normalized_name not in hidden_tool_names:
        return ToolAvailabilityConstraint(tool_name=normalized_name, blocked=False)

    if normalized_name == "ask_user" and state.get("headless_mode"):
        a4_observation = state.get("a4_completion_observation") or {}
        if bool(a4_observation.get("artifact_write_validated", False)):
            report_type = (
                "panorama"
                if str(state.get("analysis_mode") or "").strip().lower() == "baseline"
                else "scenario"
            )
            return ToolAvailabilityConstraint(
                tool_name=normalized_name,
                blocked=True,
                reason=(
                    "当前任务是 headless 定时任务，不能等待用户确认；"
                    "ask_user 不能在本轮执行。"
                ),
                suggested_next_actions=(
                    f"改为调用 analysis_report_skill(report_type='{report_type}') 继续生成报告",
                    "如果缺少继续条件，直接返回可恢复错误并记录原因",
                ),
            )
        return ToolAvailabilityConstraint(
            tool_name=normalized_name,
            blocked=True,
            reason=(
                "当前任务是 headless 定时任务，不能等待用户确认；"
                "ask_user 不能在本轮执行。"
            ),
            suggested_next_actions=(
                "选择一个确定性的下一步工具继续执行",
                "如果没有确定性下一步，结束任务并写入可恢复错误",
            ),
        )

    preferred_followup_tool = _infer_current_session_followup_tool(state)
    if preferred_followup_tool is not None:
        preferred_name, preferred_args = preferred_followup_tool
        suggestion = (
            f"改为调用 {preferred_name}"
            f"{_format_tool_args_for_suggestion(preferred_args)}"
        )
        return ToolAvailabilityConstraint(
            tool_name=normalized_name,
            blocked=True,
            reason=(
                "当前用户问题属于本次结果追问，应优先使用本次结果上下文，"
                "不要切到过往资料工具或泛化后续分析工具。"
            ),
            suggested_next_actions=(
                suggestion,
                "也可以直接基于当前抓取结果向用户解释，不再调用工具",
            ),
        )

    if normalized_name in _KNOWLEDGE_TOOL_NAMES and _session_was_recalled(state):
        return ToolAvailabilityConstraint(
            tool_name=normalized_name,
            blocked=True,
            reason=(
                "当前会话已从历史资料唤起，相关过往资料已经作为上下文加载，"
                "本轮不要重复调用 knowledge_* 工具。"
            ),
            suggested_next_actions=(
                "直接基于已加载的历史上下文回答用户",
                "如需新增实时数据，改为调用 brand_analysis 或 answer_fetch",
            ),
        )

    return ToolAvailabilityConstraint(
        tool_name=normalized_name,
        blocked=True,
        reason="该工具当前不满足本轮上下文前置条件。",
        suggested_next_actions=(
            "改用当前回合提示中推荐的可用工具",
            "向用户说明缺少的前置条件并给出下一步选择",
        ),
    )

