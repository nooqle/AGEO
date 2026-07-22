"""Knowledge planning/fallback pure helpers (P2 knife 7, cautious)."""

from __future__ import annotations

from typing import Any, Mapping

from app.workflow.orchestrator.history_query import (
    _has_terminal_knowledge_result,
    _is_current_report_follow_up,
    _is_precise_history_query,
    _session_was_recalled,
)
from app.workflow.orchestrator.knowledge_format import (
    _format_knowledge_comparison,
    _format_knowledge_group,
    _format_knowledge_lookup_match,
)
from app.workflow.orchestrator.run_context import _get_latest_user_message
from app.workflow.orchestrator.session_tool_surface import (
    _infer_authoritative_history_refresh_tool,
)
from app.workflow.orchestrator.text_normalize import (
    _contains_non_negated_keyword,
)

def _build_recent_knowledge_context(state: Mapping[str, Any]) -> str:
    """Expose the latest knowledge tool output back to the orchestrator.

    Only surface this when the orchestrator is resuming immediately after a tool
    run. On a brand-new user turn we avoid carrying stale evidence into the
    system prompt and instead rely on history + fresh planning.
    """
    history = state.get("orchestrator_history") or []
    if history and history[-1].get("role") == "user":
        return ""

    lookup_result = state.get("knowledge_lookup_result") or {}
    if lookup_result.get("status") == "hit":
        matches = lookup_result.get("matches") or []
        lines = [_format_knowledge_lookup_match(match) for match in matches[:3]]
        if lines:
            return "\n最近一次过往资料检索结果:\n" + "\n".join(lines)

    aggregate_result = state.get("knowledge_aggregate_result") or {}
    if aggregate_result.get("status") == "hit":
        groups = aggregate_result.get("groups") or []
        lines = [_format_knowledge_group(group) for group in groups[:4]]
        if lines:
            return (
                "\n最近一次过往资料整理结果"
                f"（group_by={aggregate_result.get('group_by', 'source_type')}）:\n"
                + "\n".join(lines)
            )

    export_result = state.get("knowledge_export_result") or {}
    if export_result.get("status") == "hit":
        return (
            "\n最近一次资料表结果:\n"
            f"- 标题={export_result.get('title', '过往资料表')}；"
            f"记录数={export_result.get('item_count', 0)}；"
            "相关结果已生成"
        )

    compare_result = state.get("knowledge_compare_result") or {}
    if compare_result.get("status") == "hit":
        comparisons = compare_result.get("comparisons") or []
        lines = [_format_knowledge_comparison(item) for item in comparisons[:4]]
        if lines:
            return (
                "\n最近一次过往资料对比结果"
                f"（{compare_result.get('previous_label', 'previous')} -> "
                f"{compare_result.get('latest_label', 'latest')}）:\n"
                + "\n".join(lines)
            )

    return ""

def _build_knowledge_planning_hint(state: Mapping[str, Any]) -> str:
    """Provide a lightweight planning hint without hard-forcing tool choice."""
    latest_user_message = _get_latest_user_message(state)
    if not latest_user_message:
        return ""
    if (
        _session_was_recalled(state)
        or _is_current_report_follow_up(state)
        or _has_terminal_knowledge_result(state)
    ):
        return ""

    manifest = state.get("knowledge_manifest") or {}
    available_sources = manifest.get("available_sources") or {}
    history_info = manifest.get("history") or {}
    has_materials = any(bool(value) for value in available_sources.values())
    if not has_materials:
        return ""

    if _infer_authoritative_history_refresh_tool(state) is not None:
        return (
            "\n当前用户明确在问上一轮/最近一轮抓取的失败统计或补采对象。"
            "这里不能直接复述历史对话中的旧数字，必须先刷新权威历史结果；"
            "优先考虑 knowledge_aggregate，必要时再结合 knowledge_lookup。"
        )

    text = latest_user_message.lower()
    compare_keywords = [
        "对比",
        "比较",
        "变化",
        "趋势",
        "最近两次",
        "上次",
        "这次",
    ]
    export_keywords = [
        "导出",
        "下载",
        "文件",
        "表格",
        "清单",
        "csv",
        "excel",
        "pdf",
        "md",
    ]
    aggregate_keywords = [
        "汇总",
        "统计",
        "盘点",
        "列表",
        "所有",
        "全部",
        "按平台",
        "按月份",
        "3月",
        "4月",
        "5月",
    ]
    lookup_keywords = [
        "品牌",
        "竞品",
        "答案",
        "引用",
        "官网",
        "来源",
        "历史",
        "差距",
        "为什么",
    ]

    if int(history_info.get("analysis_window_count") or 0) >= 2 and any(
        keyword in text for keyword in compare_keywords
    ):
        return (
            "\n当前用户请求明显属于“过往资料对比/变化解释”任务。"
            "优先考虑 knowledge_compare；若结果不足，再决定是否补抓。"
        )

    if any(keyword in text for keyword in export_keywords):
        return (
            "\n当前用户请求明显属于“过往资料导出/交付”任务。"
            "优先考虑 knowledge_export；必要时再用 knowledge_lookup 或 knowledge_aggregate 补证据。"
        )

    if any(keyword in text for keyword in aggregate_keywords):
        return (
            "\n当前用户请求明显属于“过往资料汇总/导出/盘点”任务。"
            "优先考虑 knowledge_aggregate；必要时再结合 knowledge_lookup 补证据。"
        )

    if any(keyword in text for keyword in lookup_keywords):
        return (
            "\n当前用户请求明显围绕“过往事实/回答/引用”展开。"
            "优先考虑 knowledge_lookup；如果命中不足，再决定是否调用 brand_analysis 或 answer_fetch。"
        )

    return ""

def _infer_knowledge_fallback_tool(
    state: Mapping[str, Any],
) -> tuple[str, dict[str, Any]] | None:
    """Fallback only when LLM produced no tool call for a clear history task."""
    latest_user_message = _get_latest_user_message(state)
    if not latest_user_message:
        return None
    if _session_was_recalled(state) or _is_current_report_follow_up(state):
        return None
    if _has_terminal_knowledge_result(state):
        return None

    manifest = state.get("knowledge_manifest") or {}
    available_sources = manifest.get("available_sources") or {}
    history_info = manifest.get("history") or {}
    has_materials = any(bool(value) for value in available_sources.values())
    if not has_materials:
        return None

    text = latest_user_message.lower()
    current_uploaded_table_query = (
        any(keyword in latest_user_message for keyword in ("上传", "导入", "附件"))
        and any(
            keyword in latest_user_message
            for keyword in ("表格", "问题列表", "问题内容", "识别")
        )
        and (
            bool(state.get("table_intake_result"))
            or (
                isinstance(state.get("simulated_questions"), dict)
                and (state.get("simulated_questions") or {}).get("generation_mode")
                == "uploaded_list"
            )
        )
    )
    if current_uploaded_table_query:
        return None

    resolved_history_answer_query = _resolve_bounded_history_answer_query(state)
    if resolved_history_answer_query:
        return (
            "knowledge_export",
            {
                "query": resolved_history_answer_query,
                "limit": 200,
                "source_types": ["fetch_answer"],
            },
        )

    compare_keywords = ["对比", "比较", "变化", "趋势", "最近两次", "上次", "这次"]
    export_keywords = [
        "导出",
        "下载",
        "文件",
        "表格",
        "清单",
        "csv",
        "excel",
        "pdf",
        "md",
    ]
    aggregate_keywords = [
        "汇总",
        "统计",
        "盘点",
        "列表",
        "所有",
        "全部",
        "按平台",
        "按月份",
        "3月",
        "4月",
        "5月",
    ]
    lookup_keywords = [
        "品牌",
        "竞品",
        "答案",
        "引用",
        "官网",
        "来源",
        "历史",
        "差距",
        "为什么",
    ]

    if int(history_info.get("analysis_window_count") or 0) >= 2 and any(
        keyword in text for keyword in compare_keywords
    ):
        compare_by = "platform"
        if "竞品" in latest_user_message:
            compare_by = "competitor"
        elif "引用" in latest_user_message or "域名" in latest_user_message:
            compare_by = "domain"
        elif "问题" in latest_user_message:
            compare_by = "question"
        return ("knowledge_compare", {"compare_by": compare_by, "limit": 8})

    if _is_precise_history_query(latest_user_message):
        args: dict[str, Any] = {
            "query": latest_user_message,
            "limit": 200,
        }
        if any(
            keyword in latest_user_message for keyword in ("回答", "答案", "过往回答")
        ):
            args["source_types"] = ["fetch_answer"]
        return ("knowledge_export", args)

    if any(keyword in text for keyword in export_keywords):
        return (
            "knowledge_export",
            {
                "query": latest_user_message,
                "limit": 200,
            },
        )

    if _contains_non_negated_keyword(latest_user_message, aggregate_keywords):
        group_by = "source_type"
        if "平台" in latest_user_message:
            group_by = "platform"
        elif "竞品" in latest_user_message:
            group_by = "competitor"
        elif (
            "引用" in latest_user_message
            or "域名" in latest_user_message
            or "官网" in latest_user_message
            or "来源" in latest_user_message
        ):
            group_by = "domain"
        elif "问题" in latest_user_message:
            group_by = "question"
        elif any(
            month in latest_user_message
            for month in [
                "1月",
                "2月",
                "3月",
                "4月",
                "5月",
                "6月",
                "7月",
                "8月",
                "9月",
                "10月",
                "11月",
                "12月",
            ]
        ):
            group_by = "month"
        return (
            "knowledge_aggregate",
            {
                "query": latest_user_message,
                "group_by": group_by,
                "limit": 12,
            },
        )

    if any(keyword in text for keyword in lookup_keywords):
        source_types = None
        answer_detail_keywords = [
            "答案",
            "回答",
            "怎么回答",
            "提及",
            "负向",
            "负面",
            "正向",
            "正面",
            "中性",
            "情感",
            "证据",
        ]
        if any(keyword in latest_user_message for keyword in answer_detail_keywords):
            source_types = ["fetch_answer", "fetch_citation"]
        elif (
            "引用" in latest_user_message
            or "官网" in latest_user_message
            or "来源" in latest_user_message
        ):
            source_types = ["fetch_citation", "fetch_answer"]
        elif "竞品" in latest_user_message:
            source_types = ["competitor_profile", "fetch_answer"]
        elif any(
            keyword in latest_user_message
            for keyword in [
                "品牌档案",
                "品牌信息",
                "品牌定位",
                "品牌介绍",
                "核心产品",
                "目标受众",
            ]
        ):
            source_types = ["brand_profile", "competitor_profile"]
        elif "答案" in latest_user_message:
            source_types = ["fetch_answer"]
        args: dict[str, Any] = {
            "query": latest_user_message,
            "limit": 8,
        }
        if source_types:
            args["source_types"] = source_types
        return ("knowledge_lookup", args)

    return None

def _should_stream_thoughts(state: Mapping[str, Any]) -> bool:
    """Mute low-value reasoning streams for obvious history-export tasks."""

    fallback = _infer_knowledge_fallback_tool(state)
    if fallback and fallback[0] == "knowledge_export":
        return False
    return True

