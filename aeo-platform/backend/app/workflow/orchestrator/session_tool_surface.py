"""Session follow-up / hidden tool surface (P2 knife 5, cautious)."""

from __future__ import annotations

from typing import Any, Mapping

from app.config import get_settings
from app.workflow.orchestrator.history_query import (
    _has_authoritative_history_refresh_result,
    _is_current_report_follow_up,
    _is_latest_run_history_stats_query,
    _session_was_recalled,
)
from app.workflow.orchestrator.misc_pure import _normalize_sentiment_followup_value
from app.workflow.orchestrator.run_context import _get_latest_user_message

_CURRENT_SESSION_FOLLOWUP_HIDDEN_TOOL_NAMES = frozenset(
    {
        "knowledge_lookup",
        "knowledge_aggregate",
        "knowledge_compare",
        "knowledge_export",
    }
)

_SPECIFIC_DRILL_DOWN_HIDDEN_TOOL_NAMES = frozenset(
    {
        "post_analysis_skill",
        "compare_snapshots",
    }
)

_KNOWLEDGE_TOOL_NAMES = frozenset(
    {
        "knowledge_lookup",
        "knowledge_aggregate",
        "knowledge_compare",
        "knowledge_export",
    }
)

def _infer_current_session_followup_tool(
    state: Mapping[str, Any],
) -> tuple[str, dict[str, Any]] | None:
    latest_user_message = _get_latest_user_message(state)
    if not latest_user_message:
        return None

    if not state.get("fetch_results"):
        return None

    lowered = latest_user_message.lower()
    history_keywords = [
        "历史",
        "上次",
        "最近两次",
        "变化",
        "趋势",
        "导出",
        "汇总",
        "按月",
        "3月",
        "4月",
        "5月",
    ]
    if not _is_current_report_follow_up(state) and any(
        keyword in latest_user_message for keyword in history_keywords
    ):
        return None

    sentiment_value = _normalize_sentiment_followup_value(latest_user_message)
    if sentiment_value is not None:
        return (
            "drill_down_analysis",
            {
                "focus_dimension": "sentiment",
                "focus_value": sentiment_value,
            },
        )

    platform_aliases = {
        "deepseek": ["deepseek", "深度求索"],
        "kimi": ["kimi"],
        "doubao": ["豆包"],
        "hunyuan": ["元宝", "hunyuan", "腾讯元宝"],
    }
    for platform_key, aliases in platform_aliases.items():
        if any(alias.lower() in lowered for alias in aliases):
            return (
                "drill_down_analysis",
                {
                    "focus_dimension": "platform",
                    "focus_value": platform_key,
                },
            )

    return None

def _infer_authoritative_history_refresh_tool(
    state: Mapping[str, Any],
) -> tuple[str, dict[str, Any]] | None:
    """Require a fresh history read for latest-run fetch stats before answering."""

    latest_user_message = _get_latest_user_message(state)
    if not latest_user_message:
        return None
    if _session_was_recalled(state) or _is_current_report_follow_up(state):
        return None

    if not _is_latest_run_history_stats_query(latest_user_message):
        return None

    manifest = state.get("knowledge_manifest") or {}
    available_sources = manifest.get("available_sources") or {}
    if not any(bool(value) for value in available_sources.values()):
        return None

    if _has_authoritative_history_refresh_result(state):
        return None

    lowered = latest_user_message.lower()
    group_by = "source_type"
    if any(
        marker in latest_user_message
        for marker in ("问题", "题目", "没有采集到答案", "没成功")
    ):
        group_by = "question"
    elif any(
        marker in lowered
        for marker in ("平台", "deepseek", "kimi", "doubao", "元宝", "hunyuan")
    ):
        group_by = "platform"

    limit = 50 if group_by == "question" else 20

    return (
        "knowledge_aggregate",
        {
            "query": latest_user_message,
            "group_by": group_by,
            "limit": limit,
            "source_types": ["fetch_answer"],
        },
    )

def _stable_tool_surface_enabled() -> bool:
    return bool(
        getattr(get_settings(), "ORCHESTRATOR_STABLE_TOOL_SURFACE_ENABLED", False)
    )

def _get_contextual_hidden_tool_names(state: Mapping[str, Any] | None) -> set[str]:
    if not state:
        return set()

    hidden: set[str] = set()
    if state.get("headless_mode"):
        hidden.add("ask_user")
    if _session_was_recalled(state):
        hidden.update(_KNOWLEDGE_TOOL_NAMES)
    preferred_followup_tool = _infer_current_session_followup_tool(state)
    if preferred_followup_tool is not None:
        hidden.update(_CURRENT_SESSION_FOLLOWUP_HIDDEN_TOOL_NAMES)
        if preferred_followup_tool[0] == "drill_down_analysis":
            hidden.update(_SPECIFIC_DRILL_DOWN_HIDDEN_TOOL_NAMES)
    return hidden

def _should_force_fetch_recovery_confirmation(state: Mapping[str, Any]) -> bool:
    if not _is_latest_run_history_stats_query(_get_latest_user_message(state)):
        return False
    if state.get("awaiting_user") or state.get("pending_confirmation"):
        return False
    if not (state.get("a4_canonical_result") or state.get("fetch_results")):
        return False

    aggregate_result = state.get("knowledge_aggregate_result") or {}
    if (
        not isinstance(aggregate_result, dict)
        or aggregate_result.get("status") != "hit"
    ):
        return False

    fetch_status = aggregate_result.get("fetch_status_summary") or {}
    if not isinstance(fetch_status, dict):
        return False

    failure_count = int(fetch_status.get("failure_count") or 0)
    question_targets = normalize_question_targets(
        fetch_status.get("failed_question_targets")
    )
    return failure_count > 0 and bool(question_targets)

