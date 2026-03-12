"""A5 report post-processing helpers.

Keeps LLM output enrichment and degraded fallback generation outside the node
so the node focuses on orchestration and persistence.
"""

from typing import Any

from app.workflow.a5 import metrics as a5_metrics
from app.workflow.nodes_a4 import PLATFORMS


def enrich_report_data(
    report_data: dict[str, Any],
    metrics: dict[str, Any],
    competitor_metrics: list[dict[str, Any]],
    fetch_results: list,
    brand_profile: dict,
) -> dict[str, Any]:
    """Fill UI-facing derived fields without overriding LLM-authored content."""
    platform_breakdown = metrics.get("platform_breakdown", {})

    platform_analysis = report_data.get("platform_analysis", [])
    for platform_analysis_item in platform_analysis:
        platform_key = str(platform_analysis_item.get("platform") or platform_analysis_item.get("name") or "")

        if "performance_summary" in platform_analysis_item and "summary" not in platform_analysis_item:
            platform_analysis_item["summary"] = platform_analysis_item["performance_summary"]
        if "mention_count" in platform_analysis_item and "mentions" not in platform_analysis_item:
            platform_analysis_item["mentions"] = platform_analysis_item["mention_count"]

        platform_breakdown_item = None
        for key, value in platform_breakdown.items():
            if key.lower() == platform_key.lower():
                platform_breakdown_item = value
                break

        if platform_breakdown_item:
            total = platform_breakdown_item.get("total", 0)
            mentions_value = platform_breakdown_item.get("mentions", 0)
            platform_analysis_item.setdefault("mentions", mentions_value)
            platform_analysis_item.setdefault("total_questions", total)
            platform_analysis_item.setdefault(
                "mention_rate",
                round(mentions_value / total, 4) if total > 0 else 0.0,
            )
            platform_analysis_item.setdefault(
                "sentiment",
                a5_metrics.compute_platform_sentiment(fetch_results, platform_key),
            )
            platform_analysis_item.setdefault(
                "status",
                "success" if platform_breakdown_item.get("success", 0) > 0 else "failed",
            )

    competitor_deep_analysis = report_data.get("competitor_deep_analysis")
    if isinstance(competitor_deep_analysis, dict):
        matrix = competitor_deep_analysis.get("comparison_matrix", [])
        competitor_lookup = {
            item["name"].lower(): item
            for item in competitor_metrics
            if item.get("name")
        }

        for row in matrix:
            if "competitor" in row and "name" not in row:
                row["name"] = row["competitor"]
            if "competitor_mention_rate" in row and "mention_rate" not in row:
                row["mention_rate"] = row["competitor_mention_rate"]

            name_lower = str(row.get("name") or row.get("competitor") or "").lower()
            competitor_metric = competitor_lookup.get(name_lower)
            if not competitor_metric:
                continue

            row.setdefault("mention_rate", competitor_metric.get("mention_rate", 0))
            raw_sentiment = competitor_metric.get("sentiment", 0)
            row.setdefault("sentiment", round(max(0, min(100, (raw_sentiment + 1) * 50)), 1))

            appeared_in = competitor_metric.get("appeared_in", [])
            unique_platforms = len(
                set(
                    item.get("platform", "")
                    for item in appeared_in
                    if item.get("platform")
                )
            )
            total_platforms = len(PLATFORMS)
            coverage = unique_platforms / total_platforms if total_platforms > 0 else 0
            row.setdefault("coverage", round(coverage, 4))

            from app.core.constants import BWVSConstants

            mention_score = min(100.0, row.get("mention_rate", 0) * BWVSConstants.MENTION_RATE_MULTIPLIER)
            sentiment_score = row.get("sentiment", BWVSConstants.DEFAULT_SENTIMENT_SCORE)
            coverage_score = row.get("coverage", 0) * 100
            bwvs = (
                a5_metrics.BWVS_WEIGHTS["mention"] * mention_score
                + a5_metrics.BWVS_WEIGHTS["sentiment"] * sentiment_score
                + a5_metrics.BWVS_WEIGHTS["coverage"] * coverage_score
                + a5_metrics.BWVS_WEIGHTS["citation"] * BWVSConstants.DEFAULT_CITATION_SCORE
            ) / 100
            row.setdefault("bwvs", round(min(100, bwvs), 1))

        has_self = any(row.get("is_self") for row in matrix)
        if not has_self and brand_profile.get("brand_name"):
            breakdown = metrics.get("bwvs_breakdown", {})
            matrix.insert(
                0,
                {
                    "name": brand_profile["brand_name"],
                    "is_self": True,
                    "bwvs": round(metrics.get("bwvs_index", 0), 1),
                    "mention_rate": round(metrics.get("mention_rate", 0), 4),
                    "sentiment": round(breakdown.get("sentiment_score", 50), 1),
                    "coverage": round(breakdown.get("coverage_score", 0) / 100, 4),
                },
            )

        competitor_deep_analysis["comparison_matrix"] = matrix

    return report_data


def generate_fallback_report(metrics: dict[str, Any], brand_profile: dict[str, Any]) -> dict[str, Any]:
    """Generate degraded but UI-compatible report data when the LLM fails."""
    brand_name = brand_profile.get("brand_name", "品牌")
    mention_rate = metrics.get("mention_rate", 0)

    if mention_rate >= 0.7:
        summary = (
            f"{brand_name} 的 AI 平台可见度分析已完成。"
            f"整体提及率为 {mention_rate:.1%}，品牌已进入较多回答场景，表现较强。"
        )
    elif mention_rate >= 0.4:
        summary = (
            f"{brand_name} 的 AI 平台可见度分析已完成。"
            f"整体提及率为 {mention_rate:.1%}，已有一定存在感，但仍有明显提升空间。"
        )
    else:
        summary = (
            f"{brand_name} 的 AI 平台可见度分析已完成。"
            f"整体提及率为 {mention_rate:.1%}，当前露出偏弱，建议优先优化内容策略。"
        )

    return {
        "executive_summary": summary,
        "key_findings": [
            f"品牌整体提及率: {mention_rate:.1%}",
            "建议优先补齐缺席场景并提升官网引用。",
        ],
        "industry_insights": None,
        "platform_analysis": [],
        "competitor_deep_analysis": None,
        "actionable_recommendations": [],
        "risk_alerts": [],
        "strengths": [f"品牌在 AI 平台中有基础曝光 (提及率 {mention_rate:.1%})"] if mention_rate > 0.1 else [],
        "weaknesses": [],
        "opportunities": ["建议增加品牌相关内容在权威平台的布局"],
        "threats": [],
        "recommendations": [],
        "action_plan": {},
        "_degraded": True,
    }
