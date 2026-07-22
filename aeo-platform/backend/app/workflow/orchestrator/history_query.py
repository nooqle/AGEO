"""History / follow-up query predicates (P2 knife 2)."""

from __future__ import annotations

from typing import Any, Mapping

from app.workflow.orchestrator.run_context import _get_latest_user_message
from app.workflow.orchestrator.text_normalize import (
    _contains_non_negated_keyword,
    _extract_exact_datetime_scope_text,
)

def _contains_positive_continuation_marker(
    text: str, keywords: tuple[str, ...]
) -> bool:
    normalized = str(text or "")
    negative_markers = (
        "不要",
        "别",
        "不需要",
        "无需",
        "不是",
        "不用",
        "不必",
        "暂不",
        "先不",
        "先别",
        "禁止",
    )
    for keyword in keywords:
        start = normalized.find(keyword)
        while start >= 0:
            prefix_window = normalized[max(0, start - 16) : start]
            if not any(marker in prefix_window for marker in negative_markers):
                return True
            start = normalized.find(keyword, start + len(keyword))
    return False

def _is_precise_history_query(text: str) -> bool:
    normalized = str(text or "")
    if not _extract_exact_datetime_scope_text(normalized):
        return False
    if not any(
        keyword in normalized
        for keyword in (
            "只查",
            "只查询",
            "只看",
            "这一轮",
            "这轮",
            "这一批",
            "这个时间点",
        )
    ):
        return False
    return any(
        keyword in normalized
        for keyword in ("过往回答", "回答", "答案", "记录", "资料表", "数据表")
    )

def _is_history_answer_content_query(text: str | None) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return False

    history_markers = (
        "历史",
        "过往",
        "之前",
        "以前",
        "历次",
        "上一轮",
        "上轮",
        "上次",
        "最近一轮",
    )
    answer_markers = (
        "回答",
        "答案",
        "回答内容",
        "具体回答",
        "具体的回答",
        "回复内容",
        "内容",
        "原文",
    )
    compare_markers = ("对比", "比较", "变化", "趋势")
    stats_markers = (
        "成功率",
        "失败率",
        "失败数",
        "失败平台",
        "失败问题",
        "失败题目",
        "补采",
    )

    if not any(marker in normalized for marker in history_markers):
        return False
    if not any(marker in normalized for marker in answer_markers):
        return False
    if any(marker in normalized for marker in compare_markers):
        return False
    if any(marker in normalized for marker in stats_markers):
        return False
    return True

def _is_history_answer_continuation_query(text: str | None) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return False

    continuation_markers = (
        "完整内容",
        "完整回答",
        "完整回答内容",
        "完整答案",
        "完整回复",
        "具体内容",
        "原文",
        "全文",
    )
    compare_markers = ("对比", "比较", "变化", "趋势")
    stats_markers = (
        "成功率",
        "失败率",
        "失败数",
        "失败平台",
        "失败问题",
        "失败题目",
        "补采",
    )
    if not any(marker in normalized for marker in continuation_markers):
        return False
    if any(marker in normalized for marker in compare_markers):
        return False
    if any(marker in normalized for marker in stats_markers):
        return False
    return True

def _iter_recent_history_messages(
    state: Mapping[str, Any],
    *,
    role: str | None = None,
    limit: int = 8,
) -> list[str]:
    history = list(state.get("orchestrator_history") or [])
    items: list[str] = []
    for item in reversed(history):
        if role and item.get("role") != role:
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        items.append(content)
        if len(items) >= limit:
            break
    return items

def _has_recent_history_answer_followup_invite(state: Mapping[str, Any]) -> bool:
    assistant_messages = _iter_recent_history_messages(state, role="assistant", limit=6)
    invite_markers = (
        "完整回答内容",
        "完整回答",
        "具体回答",
        "完整内容",
    )
    return any(
        any(marker in message for marker in invite_markers)
        for message in assistant_messages
    )

def _get_recent_history_answer_basis_query(state: Mapping[str, Any]) -> str | None:
    latest_user_message = _get_latest_user_message(state).strip()
    user_messages = _iter_recent_history_messages(state, role="user", limit=6)
    skipped_latest = False
    for message in user_messages:
        if not skipped_latest and message == latest_user_message:
            skipped_latest = True
            continue
        if _is_history_answer_content_query(message):
            return message
    return None

def _build_history_answer_export_query(
    *,
    latest_user_message: str,
    basis_query: str,
) -> str:
    if _is_history_answer_content_query(latest_user_message):
        return latest_user_message.strip()

    normalized_basis = str(basis_query or "").strip()
    if not normalized_basis:
        return ""

    if _is_history_answer_continuation_query(latest_user_message):
        continuation_markers = (
            "完整内容",
            "完整回答",
            "完整回答内容",
            "完整答案",
            "完整回复",
            "具体内容",
            "原文",
            "全文",
        )
        if not any(marker in normalized_basis for marker in continuation_markers):
            return f"{normalized_basis} 完整内容"

    return normalized_basis

def _get_recent_history_answer_result_query(state: Mapping[str, Any]) -> str | None:
    for result_key in ("knowledge_export_result", "knowledge_lookup_result"):
        result = state.get(result_key) or {}
        query = str(result.get("query") or "").strip()
        source_types = list(result.get("source_types") or [])
        if query and "fetch_answer" in source_types:
            return query
    return None

def _session_was_recalled(state: Mapping[str, Any] | None) -> bool:
    return bool((state or {}).get("session_recalled"))

def _is_current_report_follow_up(state: Mapping[str, Any]) -> bool:
    latest_user_message = _get_latest_user_message(state)
    if not latest_user_message:
        return False
    if not (state.get("fetch_results") or state.get("report") or state.get("metrics")):
        return False

    current_markers = [
        "这份报告",
        "当前报告",
        "本次报告",
        "这个报告",
        "基于这份报告",
        "基于当前报告",
        "当前结果",
        "本次抓取",
        "这次抓取",
        "当前分析",
    ]
    current_fetch_reference_markers = [
        "上次抓取",
        "上轮抓取",
        "刚才抓取",
        "上一轮抓取",
        "平台答案",
        "抓取的平台答案",
        "抓取结果",
        "上次的报告",
        "上一轮的报告",
    ]
    strong_history_markers = [
        "历史",
        "最近两次",
        "之前",
        "月份",
        "导出",
        "下载",
        "清单",
        "表格",
        "过去",
        "过往",
    ]
    mentions_current_report = any(
        marker in latest_user_message for marker in current_markers
    )
    mentions_current_fetch = any(
        marker in latest_user_message for marker in current_fetch_reference_markers
    )
    return (mentions_current_report or mentions_current_fetch) and not any(
        marker in latest_user_message for marker in strong_history_markers
    )

def _resolve_bounded_history_answer_query(state: Mapping[str, Any]) -> str | None:
    latest_user_message = _get_latest_user_message(state).strip()
    if not latest_user_message:
        return None

    if _is_history_answer_content_query(latest_user_message):
        return latest_user_message

    if not _is_history_answer_continuation_query(latest_user_message):
        return None

    basis_query = _get_recent_history_answer_basis_query(state)
    if basis_query:
        return _build_history_answer_export_query(
            latest_user_message=latest_user_message,
            basis_query=basis_query,
        )

    result_query = _get_recent_history_answer_result_query(state)
    if result_query and _session_was_recalled(state):
        return _build_history_answer_export_query(
            latest_user_message=latest_user_message,
            basis_query=result_query,
        )

    if _has_recent_history_answer_followup_invite(state):
        result_query = _get_recent_history_answer_result_query(state)
        if result_query:
            return _build_history_answer_export_query(
                latest_user_message=latest_user_message,
                basis_query=result_query,
            )

    if _is_current_report_follow_up(state):
        return None

    return None

def _is_bounded_history_answer_query_state(state: Mapping[str, Any]) -> bool:
    return _resolve_bounded_history_answer_query(state) is not None

def _is_latest_run_history_stats_query(message: str | None) -> bool:
    text = str(message or "").strip()
    if not text:
        return False

    latest_window_markers = [
        "上一轮",
        "上轮",
        "最近一轮",
        "最近这轮",
        "上次",
        "上一批",
        "最新一轮",
    ]
    fetch_status_markers = [
        "采集",
        "抓取",
        "成功",
        "失败",
        "成功率",
        "失败率",
        "失败平台",
        "失败的问题",
        "失败题目",
        "没有采集到答案",
        "没成功",
        "补采",
    ]
    return any(marker in text for marker in latest_window_markers) and any(
        marker in text for marker in fetch_status_markers
    )

def _has_authoritative_history_refresh_result(state: Mapping[str, Any]) -> bool:
    aggregate_result = state.get("knowledge_aggregate_result") or {}
    return (
        isinstance(aggregate_result, dict) and aggregate_result.get("status") == "hit"
    )

def _has_terminal_knowledge_result(state: Mapping[str, Any]) -> bool:
    for key in (
        "knowledge_lookup_result",
        "knowledge_aggregate_result",
        "knowledge_compare_result",
        "knowledge_export_result",
    ):
        result = state.get(key) or {}
        if isinstance(result, dict) and result.get("status") == "miss":
            return True
    return False

def _is_explicit_question_generation_only_request(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False

    has_question_object = any(
        marker in normalized
        for marker in (
            "问题",
            "question",
            "questions",
            "问题集",
            "全景问题",
            "用户关心的问题",
        )
    )
    has_generation_action = any(
        marker in normalized
        for marker in (
            "生成",
            "重新生成",
            "重生成",
            "模拟",
            "设计",
            "整理",
            "列出",
            "产出",
        )
    )
    if not (has_question_object and has_generation_action):
        return False

    continuation_markers = (
        "抓取",
        "采集",
        "提问",
        "报告",
        "跑完整",
        "全流程",
        "全景分析",
        "继续分析",
        "做分析",
        "分析报告",
        "监测",
    )
    if _contains_positive_continuation_marker(normalized, continuation_markers):
        return False

    return True

def _is_question_generation_only_state(state: Mapping[str, Any]) -> bool:
    tool_args = state.get("tool_call_args") or {}
    user_decisions = state.get("user_decisions") or {}
    simulated_questions = state.get("simulated_questions") or {}
    generation_context = (
        simulated_questions.get("generation_context")
        if isinstance(simulated_questions, dict)
        else {}
    ) or {}
    return bool(
        tool_args.get("question_only")
        or state.get("question_generation_only")
        or (
            isinstance(user_decisions, dict)
            and user_decisions.get("question_generation_only")
        )
        or (
            isinstance(generation_context, dict)
            and generation_context.get("question_only")
        )
    )

