from typing import Any


def _safe_ratio(value: Any) -> float:
    try:
        numeric = float(value or 0)
    except (TypeError, ValueError):
        numeric = 0.0
    return max(0.0, min(1.0, numeric))


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _summary_text(report_data: dict[str, Any]) -> str:
    summary = report_data.get("executive_summary")
    if isinstance(summary, dict):
        one_line = str(summary.get("one_line_judgment") or "").strip()
        if one_line:
            return one_line
    for key in ("executive_summary_text", "subtitle", "executive_summary"):
        value = report_data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def build_report_artifact_data(
    *,
    brand_name: str,
    is_baseline: bool,
    metrics: dict[str, Any],
    report_data: dict[str, Any],
    summary_metrics: dict[str, Any],
    fetch_results_summary: list[dict[str, Any]],
    competitor_metrics: list[dict[str, Any]],
    delta_vs_previous: dict[str, Any] | None,
    report_v2_sections: dict[str, Any],
    scenario_matrix: list[dict[str, Any]],
    source_overview: dict[str, Any],
    mention_sentiment_analysis: dict[str, Any],
) -> dict[str, Any]:
    brand_mention_rate = _safe_ratio(summary_metrics.get("brand_mention_rate", 0))
    content_citation_rate = _safe_ratio(summary_metrics.get("content_citation_rate", 0))
    official_citation_rate = _safe_ratio(
        summary_metrics.get("official_citation_rate", 0)
    )
    scenario_hit_count = _safe_int(summary_metrics.get("scenario_hit_count", 0))
    scenario_total = _safe_int(summary_metrics.get("scenario_total", 0))
    high_risk_scenario_count = _safe_int(
        summary_metrics.get("high_risk_scenario_count", 0)
    )
    total_questions = _safe_int(metrics.get("total_questions", 0))
    total_mentions = _safe_int(metrics.get("total_mentions", 0))
    report_headline = (
        f"{brand_name or '品牌'} 品牌全景分析报告"
        if is_baseline
        else f"{brand_name or '品牌'} 用户画像场景分析报告"
    )
    executive_summary_text = _summary_text(report_data)
    return {
        "headline": report_headline,
        "subtitle": (
            f"品牌提及率 {brand_mention_rate:.1%} | "
            f"内容引用率 {content_citation_rate:.1%} | "
            f"场景覆盖 {scenario_hit_count}/{scenario_total}"
        ),
        "metrics": {
            "brand_mention_rate": brand_mention_rate,
            "content_citation_rate": content_citation_rate,
            "official_citation_rate": official_citation_rate,
            "scenario_hit_count": scenario_hit_count,
            "high_risk_scenario_count": high_risk_scenario_count,
            "accuracy_score": summary_metrics.get("accuracy_score"),
            "accuracy_status": summary_metrics.get("accuracy_status"),
            "total_questions": total_questions,
            "total_mentions": total_mentions,
        },
        "content": executive_summary_text,
        "executive_summary": report_data.get("executive_summary", ""),
        "executive_summary_text": executive_summary_text,
        "report_markdown": report_data.get("report_markdown", ""),
        "key_findings": report_data.get("key_findings", []),
        "fetch_results_summary": fetch_results_summary,
        "competitors": competitor_metrics,
        "metrics_raw": metrics,
        "report_data": report_data,
        "delta_vs_previous": delta_vs_previous,
        "citation_analysis": metrics.get("citation_analysis", {}),
        "summary_metrics": summary_metrics,
        "scenario_matrix": scenario_matrix,
        "source_overview": source_overview,
        "mention_sentiment_analysis": mention_sentiment_analysis,
        "report_summary": report_v2_sections["report_summary"],
        "scenario_coverage": report_v2_sections["scenario_coverage"],
        "source_section": report_v2_sections["source_section"],
        "mentions_section": report_v2_sections["mentions_section"],
        "report_v2": report_v2_sections["report_v2"],
    }
