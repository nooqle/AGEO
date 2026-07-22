"""Thought stream localization helpers (P2 knife 1b)."""

from __future__ import annotations

from app.workflow.orchestrator.text_normalize import _is_english_dominant_text

_VISIBLE_TOOL_NAME_LABELS: dict[str, str] = {
    "brand_analysis": "品牌分析",
    "persona_generation": "画像生成",
    "question_simulation": "问题模拟",
    "answer_fetch": "答案抓取",
    "amway_entity_extract": "实体抽取",
    "amway_circle_projection": "图谱构建",
    "amway_secondary_analysis": "数据分析",
    "amway_content_draft": "内容创作",
    "analysis_report_skill": "分析报告",
    "data_analytics": "分析报告",
    "confidence_analysis_skill": "引用置信度评估",
    "confidence_signal_skill": "引用置信度评估",
    "citation_confidence_analysis": "引用置信度评估",
    "site_confidence_assessment_skill": "官网 AI 友好度",
    "post_analysis_skill": "后续分析",
    "drill_down_analysis": "深入分析",
    "compare_snapshots": "快照对比",
    "knowledge_lookup": "过往资料检索",
    "knowledge_aggregate": "过往资料整理",
    "knowledge_compare": "过往资料对比",
    "knowledge_export": "过往资料表",
    "ask_user": "用户确认",
    "fast": "快速采集",
    "full": "完整采集",
}

def _localize_visible_terms(text: str) -> str:
    localized = str(text or "")
    for source, target in _VISIBLE_TOOL_NAME_LABELS.items():
        localized = localized.replace(source, target)
    return localized

def _normalize_thought_text_for_stream(
    text: str,
    *,
    placeholder_sent: bool,
) -> tuple[str | None, bool]:
    stripped = _localize_visible_terms(text).strip()
    if not stripped:
        return None, placeholder_sent
    if _is_english_dominant_text(stripped):
        return None, placeholder_sent
    return stripped, placeholder_sent

