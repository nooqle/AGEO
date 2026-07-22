"""Prompt context summary helpers (P2 knife 6, cautious)."""

from __future__ import annotations

from typing import Any, Mapping

from app.services.skill_registry_service import build_builtin_skill_tool_definitions
from app.workflow.orchestrator_context_packets import (
    build_entity_context_packet,
    build_session_status_packet,
    render_entity_context_packet,
    render_session_status_packet,
)
from app.workflow.orchestrator.session_tool_surface import (
    _CURRENT_SESSION_FOLLOWUP_HIDDEN_TOOL_NAMES,
    _get_contextual_hidden_tool_names,
    _infer_current_session_followup_tool,
    _stable_tool_surface_enabled,
)
from app.workflow.orchestrator.text_normalize import _compact_text

def _build_context_summary(state: Mapping[str, Any]) -> str:
    """Build a summary of what data exists in the current session.

    Includes tool availability hints (Review C4) to help LLM
    distinguish between 9 tools and avoid misrouting.
    """
    parts = []
    available_tools = []
    unavailable_tools = []
    manifest = state.get("knowledge_manifest") or {}
    hidden_tool_names = _get_contextual_hidden_tool_names(state)
    preferred_followup_tool = _infer_current_session_followup_tool(state)

    if state.get("brand_profile"):
        brand = state["brand_profile"]
        parts.append(f"- 已分析品牌: {brand.get('brand_name', '未知')}")
        parts.append(f"- 行业: {brand.get('industry', '未知')}")

    if state.get("competitors"):
        names = [c.get("name", "") for c in state["competitors"][:5]]
        parts.append(f"- 已识别竞品: {', '.join(names)}")

    if state.get("fetch_results"):
        parts.append(f"- 抓取结果: {len(state['fetch_results'])} 组问题")
        if "post_analysis_skill" not in hidden_tool_names:
            available_tools.append(
                "post_analysis_skill (可对已有结果做深挖、对比、解释或风险提取)"
            )
        if (
            preferred_followup_tool
            and preferred_followup_tool[0] == "drill_down_analysis"
        ):
            parts.append("- 当前问题命中本次结果深挖场景，优先使用 drill_down_analysis")
            if "post_analysis_skill" in hidden_tool_names:
                parts.append(
                    "- 当前回合已收敛到 drill_down_analysis，泛化后续分析入口已从工具面隐藏"
                )
    else:
        unavailable_tools.append("post_analysis_skill (尚无先前分析结果)")

    if state.get("metrics"):
        m = state["metrics"]
        parts.append(f"- 品牌提及率: {m.get('mention_rate', 'N/A')}")
        if m.get("mention_sentiment_analysis") or (state.get("report") or {}).get(
            "mention_sentiment_analysis"
        ):
            parts.append("- 当前报告已包含提及情感证据，可直接追问正向/负向提及细节")

    if state.get("baseline_metrics"):
        bm = state["baseline_metrics"]
        parts.append(f"- 品牌全景提及率: {bm.get('mention_rate', 'N/A')}")
        parts.append("- 品牌全景分析: 已完成")

    if state.get("entity_id"):
        parts.append(f"- 品牌实体ID: {state['entity_id']} (已有过往快照)")
        available_tools.append(
            "manage_monitoring_schedule (可查询、创建或调整周期监测计划)"
        )
    else:
        unavailable_tools.append("manage_monitoring_schedule (尚无品牌实体)")

    if manifest:
        available_sources = manifest.get("available_sources", {})
        history_info = manifest.get("history", {})
        available_labels = [
            label
            for key, label in [
                ("brand_profile", "品牌档案"),
                ("competitor_profile", "竞品档案"),
                ("fetch_answer", "过往回答"),
                ("fetch_citation", "过往引用"),
            ]
            if available_sources.get(key)
        ]
        if available_labels:
            if "knowledge_lookup" not in hidden_tool_names:
                available_tools.append("knowledge_lookup (可查询过往事实资料)")
            if "knowledge_aggregate" not in hidden_tool_names:
                available_tools.append("knowledge_aggregate (可汇总过往资料)")
            if "knowledge_export" not in hidden_tool_names:
                available_tools.append("knowledge_export (可导出过往资料表)")
            if "knowledge_compare" not in hidden_tool_names:
                if int(history_info.get("analysis_window_count") or 0) >= 2:
                    available_tools.append("knowledge_compare (可对比最近变化)")
                else:
                    unavailable_tools.append(
                        "knowledge_compare (过往轮次不足，暂不可对比)"
                    )
        else:
            if "knowledge_lookup" not in hidden_tool_names:
                unavailable_tools.append("knowledge_lookup (当前尚无过往资料可复用)")
            if "knowledge_aggregate" not in hidden_tool_names:
                unavailable_tools.append("knowledge_aggregate (当前尚无过往资料可汇总)")
            if "knowledge_export" not in hidden_tool_names:
                unavailable_tools.append("knowledge_export (当前尚无过往资料可导出)")
            if "knowledge_compare" not in hidden_tool_names:
                unavailable_tools.append("knowledge_compare (当前尚无过往资料可对比)")

    if hidden_tool_names & _CURRENT_SESSION_FOLLOWUP_HIDDEN_TOOL_NAMES:
        if _stable_tool_surface_enabled():
            parts.append(
                "- 当前问题属于本次结果追问，过往资料工具保留在工具清单中，"
                "但本轮会由工具门禁拦截"
            )
        else:
            parts.append("- 当前问题属于本次结果追问，过往资料工具已从可用工具面隐藏")

    if not parts:
        summary = "\n当前会话数据: 尚无分析数据。"
    else:
        summary = "\n当前会话数据:\n" + "\n".join(parts)

    # Tool availability hints (Review C4)
    if available_tools:
        summary += "\n\n可用的追问工具:\n" + "\n".join(
            f"  - {t}" for t in available_tools
        )
    if unavailable_tools:
        summary += "\n\n不可用的工具（缺少前置数据）:\n" + "\n".join(
            f"  - {t}" for t in unavailable_tools
        )

    return summary

def _build_public_skill_index(state: Mapping[str, Any]) -> str:
    hidden_tool_names = _get_contextual_hidden_tool_names(state)
    stable_tool_surface = _stable_tool_surface_enabled()
    preferred_followup_tool = _infer_current_session_followup_tool(state)
    lines: list[str] = []
    note_lines: list[str] = []
    if hidden_tool_names & _CURRENT_SESSION_FOLLOWUP_HIDDEN_TOOL_NAMES:
        if stable_tool_surface:
            note_lines.append(
                "- 当前问题属于本次结果追问，过往资料工具仍在工具清单中，"
                "但本轮不应调用，误调用会被工具门禁拦截。"
            )
        else:
            note_lines.append(
                "- 当前问题属于本次结果追问，过往资料工具已从本轮公共技能面隐藏。"
            )
    if preferred_followup_tool and preferred_followup_tool[0] == "drill_down_analysis":
        note_lines.append(
            "- 当前回合已收敛到 drill_down_analysis，不再暴露泛化的后续分析入口。"
        )
    if note_lines:
        if stable_tool_surface:
            note_lines.append("- 以下标注当前回合推荐使用的公共技能。")
        else:
            note_lines.append("- 以下仅列出当前回合真实可调用的公共技能。")
    for definition in build_builtin_skill_tool_definitions():
        name = str(definition.get("name") or "")
        if name in hidden_tool_names and not stable_tool_surface:
            continue
        description = _compact_text(definition.get("description"), 56)
        if name in hidden_tool_names and stable_tool_surface:
            availability = "本轮受工具门禁限制"
        else:
            availability = "当前可用"
        if name == "post_analysis_skill" and not state.get("fetch_results"):
            availability = "需已有抓取结果或报告"
        elif name == "analysis_report_skill" and not state.get("fetch_results"):
            availability = "需先完成答案抓取"
        elif name == "confidence_analysis_skill" and not state.get("fetch_results"):
            availability = "需先有可评估的抓取结果"
        lines.append(f"- {name}: {description}；{availability}")
        if len(lines) >= 6:
            break
    return "\n".join([*note_lines, *lines])

def _build_contextual_tool_surface_note(state: Mapping[str, Any]) -> str | None:
    hidden_tool_names = _get_contextual_hidden_tool_names(state)
    stable_tool_surface = _stable_tool_surface_enabled()
    preferred_followup_tool = _infer_current_session_followup_tool(state)
    lines: list[str] = []

    if state.get("headless_mode"):
        if stable_tool_surface:
            lines.append(
                "- 当前任务是 headless 定时任务，不能等待用户确认；"
                "ask_user 如被误调用会被工具门禁拦截。"
            )
        else:
            lines.append(
                "- 当前任务是 headless 定时任务，不能等待用户确认；不要调用 ask_user。"
            )

    if hidden_tool_names & _CURRENT_SESSION_FOLLOWUP_HIDDEN_TOOL_NAMES:
        if stable_tool_surface:
            lines.append(
                "- 当前问题属于本次结果追问，过往资料工具仍在工具清单中，"
                "但本轮不要调用；误调用会被工具门禁拦截。"
            )
        else:
            lines.append(
                "- 当前问题属于本次结果追问，过往资料工具已从当前回合工具面隐藏。"
            )

    if preferred_followup_tool and preferred_followup_tool[0] == "drill_down_analysis":
        focus_args = preferred_followup_tool[1] or {}
        focus_dimension = str(focus_args.get("focus_dimension") or "").strip()
        focus_value = str(focus_args.get("focus_value") or "").strip()
        if focus_dimension == "platform" and focus_value:
            lines.append(
                f"- 当前回合应直接使用 drill_down_analysis，聚焦平台维度：{focus_value}。"
            )
        elif focus_dimension == "sentiment" and focus_value:
            lines.append(
                f"- 当前回合应直接使用 drill_down_analysis，聚焦情感维度：{focus_value}。"
            )
        else:
            lines.append("- 当前回合应直接使用 drill_down_analysis 处理本次结果追问。")
        lines.append("- 不要再先走 post_analysis_skill 或 knowledge_*。")

    if not lines:
        return None
    return "\n".join(lines)

def _build_orchestrator_data_status(state: Mapping[str, Any]) -> str:
    return render_session_status_packet(build_session_status_packet(state))

def _build_orchestrator_entity_context(state: Mapping[str, Any]) -> str:
    return render_entity_context_packet(build_entity_context_packet(state))

