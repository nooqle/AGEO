"""Command/update helpers (P2 knife 7, cautious)."""

from __future__ import annotations

from typing import Any, Mapping

from langgraph.types import Command

from app.workflow.runtime_policy_executor import (
    clear_runtime_policy_fields,
    get_user_visible_runtime_label,
    summarize_alternative_actions,
)

def _build_error_recovery_message(
    error_info: dict[str, Any],
    alternative_options: list[dict[str, Any]] | None = None,
) -> str:
    failed_step = str(error_info.get("step", "未知"))
    error_msg = str(error_info.get("error", "未知错误")).strip()
    error_category = str(error_info.get("category", "")).strip()
    alternative_preview = summarize_alternative_actions(alternative_options or [])

    if failed_step == "A5":
        if error_category == "system_persistence":
            message = (
                "分析结果已经生成，但在保存最终报告产物时发生了系统错误。"
                "这不是抓取数据质量问题，通常不需要重新抓取。"
                "建议直接重新尝试生成报告。"
            )
            if alternative_preview:
                message += f" 当前优先方案：{alternative_preview}。"
            return message
        if error_category == "system":
            message = (
                "报告生成遇到了系统处理问题，当前失败并不等于抓取数据不可用。"
                "建议先重新尝试生成报告；如果仍失败，再检查当前结果结构。"
            )
            if alternative_preview:
                message += f" 当前优先方案：{alternative_preview}。"
            return message
        message = (
            "报告生成遇到了处理问题。"
            "当前失败不一定来自抓取数据本身，建议先重新尝试生成报告。"
        )
        if alternative_preview:
            message += f" 当前优先方案：{alternative_preview}。"
        return message

    failed_step_label = get_user_visible_runtime_label(failed_step)
    clipped_error = error_msg[:100] if error_msg else "未知错误"
    message = f"{failed_step_label}遇到问题：{clipped_error}。"
    if alternative_preview:
        message += f" 建议优先：{alternative_preview}。"
    message += "请选择后续操作。"
    return message

def _sanitize_runtime_policy_state(state: Mapping[str, Any]) -> AgentState:
    """Drop consumed runtime policy artifacts before asking the model again."""

    return {
        **state,
        **clear_runtime_policy_fields(),
    }

def _merge_command_update(command: Command, extra_update: dict[str, Any]) -> Command:
    return Command(
        goto=command.goto,
        update={
            **dict(command.update or {}),
            **extra_update,
        },
    )

