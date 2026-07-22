"""Deterministic reply builders (P2 knife 5, cautious)."""

from __future__ import annotations

from typing import Any, Mapping

from app.workflow.orchestrator.text_normalize import _normalize_public_knowledge_text

def _build_knowledge_export_completion_reply(result: dict[str, Any]) -> str:
    """Build a deterministic close-out reply for successful knowledge exports."""

    item_count = int(result.get("item_count") or 0)
    period = str(result.get("analysis_period") or "").strip()
    description = _normalize_public_knowledge_text(result.get("description") or "")
    summary_metrics = result.get("summary_metrics") or {}
    platform_count = summary_metrics.get("覆盖平台数")
    source_type_count = summary_metrics.get("来源类型")

    detail_parts: list[str] = []
    if period:
        detail_parts.append(f"范围覆盖 {period}")
    if platform_count:
        detail_parts.append(f"{platform_count} 个平台")
    if source_type_count:
        detail_parts.append(f"{source_type_count} 类材料")
    detail_text = "，".join(detail_parts)

    current_import_scope = (
        str(result.get("source_scope") or "").strip() == "current_import_artifact"
    )
    title = str(result.get("title") or "").strip() or (
        "当前导入问题表" if current_import_scope else "过往资料表"
    )
    if current_import_scope:
        reply = f"已定位当前导入问题表，共整理 {item_count} 条记录。"
    else:
        reply = f"已完成导出，当前数据表共整理 {item_count} 条记录。"
    if detail_text:
        reply += f" 本次{detail_text}。"
    if description:
        reply += f" {description}"
    if result.get("truncated"):
        reply += (
            f" 当前结果较多，仅展示前 {int(result.get('export_limit') or item_count)} 条记录，"
            "如需完整导出请缩小筛选范围后重试。"
        )
    if current_import_scope:
        reply += f" 当前结果标题为《{title}》，且只来自本次上传表格，不包含历史资料。"
    reply += " 您可以直接在右侧继续导出为 md 或 pdf。"
    return reply

def _build_ask_user_fallback_reply(
    state: Mapping[str, Any],
    tool_name: str | None,
    message: str,
) -> str:
    """Build a deterministic user-facing reply when LLM omits natural language."""
    if tool_name == "brand_analysis":
        has_baseline = bool(state.get("baseline_metrics"))
        brand_name = (
            (state.get("brand_profile", {}) or {}).get("brand_name")
            or state.get("brand_name")
            or "该品牌"
        )
        if has_baseline:
            return (
                f"{brand_name}的品牌分析已完成，我已经整理出品牌画像和竞品格局。"
                "接下来您可以先做一次引用内容置信度评估，"
                "也可以继续生成用户画像做场景细化分析、重新运行品牌全景分析，"
                "或者直接基于已有结果提问。"
            )
        return (
            f"{brand_name}的品牌分析已完成，但当前还没有品牌全景分析结果。"
            "建议先运行品牌全景分析，建立各 AI 平台对该品牌的整体认知参考，"
            "后续再做画像和场景分析会更有对照价值。"
        )

    if tool_name == "persona_generation":
        return (
            "用户画像已生成并展示在右侧画布中。"
            "请先在画布里勾选您想重点分析的画像，然后回复我继续；"
            "如果不想限定画像，也可以直接告诉我走品牌全景分析。"
        )

    if tool_name == "question_simulation":
        return (
            "问题模拟已完成，相关问题已经展示在右侧画布中。"
            "您现在可以告诉我选择快速采集、完整采集，或要求我重新生成问题。"
        )

    if tool_name == "table_intake_skill":
        result = state.get("table_intake_result") or {}
        summary = result.get("summary") or "表格理解完成。"
        return f"{summary} 请确认是否按我识别的用途继续。"

    if tool_name == "answer_fetch":
        return (
            "答案抓取已完成。"
            "我会基于当前抓取结果立即继续生成分析报告，"
            "报告出来后您再决定是否继续做引用内容置信度评估或进入后续分析。"
        )

    if tool_name in {"data_analytics", "analysis_report_skill"}:
        return (
            "分析报告已生成。"
            "您现在可以选择继续做一次引用内容置信度评估，"
            "或者基于当前报告进入下一步画像分析、深入分析或直接提问。"
        )

    if tool_name == "confidence_analysis_skill":
        return (
            "引用内容置信度评估已完成。"
            "您现在可以继续基于这份评估追问具体来源问题，"
            "或者回到主报告继续后续分析。"
        )

    return message or "请继续告诉我您的选择。"

