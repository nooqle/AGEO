"""A5 report post-processing helpers.

Keeps LLM output enrichment and degraded fallback generation outside the node
so the node focuses on orchestration and persistence.
"""

from __future__ import annotations

from typing import Any

from app.workflow.a5 import metrics as a5_metrics
from app.workflow.nodes_a4 import PLATFORMS


def _safe_ratio(value: Any) -> float:
    try:
        numeric = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, numeric))


def _format_rate(value: Any) -> str:
    return f"{_safe_ratio(value):.1%}"


def _summarize_competitor_sentiment(value: Any) -> str:
    try:
        numeric = float(value or 0)
    except (TypeError, ValueError):
        numeric = 0.0
    if numeric <= -0.2:
        return "负向"
    if numeric >= 0.2:
        return "正向"
    return "中性"


def _sort_top_domains(source_overview: dict[str, Any]) -> list[dict[str, Any]]:
    items = source_overview.get("top_domains", []) or []
    return sorted(
        [item for item in items if isinstance(item, dict) and item.get("domain")],
        key=lambda item: int(item.get("count", 0) or 0),
        reverse=True,
    )


def _pick_brand_mention_domains(mention_sentiment_analysis: dict[str, Any]) -> list[tuple[str, int]]:
    domain_counts: dict[str, int] = {}
    brand_payload = mention_sentiment_analysis.get("brand", {}) if isinstance(mention_sentiment_analysis, dict) else {}
    brand_items = brand_payload.get("items", []) if isinstance(brand_payload, dict) else []
    for item in brand_items:
        if not isinstance(item, dict):
            continue
        for domain in item.get("citation_domains", []) or []:
            if not isinstance(domain, str) or not domain.strip():
                continue
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
    return sorted(domain_counts.items(), key=lambda pair: (-pair[1], pair[0]))


def _pick_negative_items(mention_sentiment_analysis: dict[str, Any]) -> list[dict[str, Any]]:
    brand_payload = mention_sentiment_analysis.get("brand", {}) if isinstance(mention_sentiment_analysis, dict) else {}
    brand_items = brand_payload.get("items", []) if isinstance(brand_payload, dict) else []
    negative_items = [
        item for item in brand_items
        if isinstance(item, dict) and str(item.get("sentiment", "neutral")) == "negative"
    ]
    return negative_items[:5]


def _build_negative_labels(negative_items: list[dict[str, Any]]) -> list[str]:
    labels: list[str] = []
    for item in negative_items:
        evidence = " ".join(str(item.get("evidence", "")).split())
        scenario = str(item.get("scenario_label", "")).strip()
        if evidence:
            labels.append(evidence[:80] + ("…" if len(evidence) > 80 else ""))
        elif scenario:
            labels.append(scenario)
    deduped: list[str] = []
    seen: set[str] = set()
    for label in labels:
        key = label.lower()
        if not label or key in seen:
            continue
        seen.add(key)
        deduped.append(label)
    return deduped[:4]


def _build_competitor_threats(
    competitor_metrics: list[dict[str, Any]],
    brand_mention_rate: float,
) -> list[dict[str, Any]]:
    threats: list[dict[str, Any]] = []
    for item in competitor_metrics:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        mention_rate = _safe_ratio(item.get("mention_rate", 0))
        if mention_rate <= 0:
            continue
        ratio_gap = abs(mention_rate - brand_mention_rate)
        if mention_rate >= brand_mention_rate * 0.85 or ratio_gap <= 0.08:
            threats.append(item)
    return sorted(
        threats,
        key=lambda item: _safe_ratio(item.get("mention_rate", 0)),
        reverse=True,
    )[:4]


def _build_platform_preference_lines(source_overview: dict[str, Any]) -> list[str]:
    platform_stats = source_overview.get("platform_citation_stats", {}) or {}
    lines: list[str] = []
    for platform in PLATFORMS:
        stats = platform_stats.get(platform, {}) if isinstance(platform_stats, dict) else {}
        top_domains = stats.get("top_domains", []) if isinstance(stats, dict) else []
        domains = [
            f"{item.get('domain')}（{int(item.get('count', 0) or 0)} 次）"
            for item in top_domains[:3]
            if isinstance(item, dict) and item.get("domain")
        ]
        if not domains:
            domains = ["暂无明显来源偏好"]
        lines.append(
            f"- {platform}：总引用 {int(stats.get('total_citations', 0) or 0)} 次，"
            f"官网引用率 {_format_rate(stats.get('official_citation_rate', 0))}；"
            f"高频来源 {('、'.join(domains))}。"
        )
    return lines


def _contains_reasoning_leak(markdown: str) -> bool:
    lowered = str(markdown or "").lower()
    leak_signals = [
        "让我们",
        "等一下",
        "检查一下",
        "我必须",
        "起草",
        "自我修正",
        "最终润色",
        "这里看起来",
        "不对",
        "让我们保持",
        "analysis notes",
        "draft v2",
        "step 1",
        "step 2",
    ]
    return any(signal in lowered for signal in leak_signals)


def build_report_markdown(
    *,
    brand_profile: dict[str, Any],
    metrics: dict[str, Any],
    summary_metrics: dict[str, Any],
    scenario_matrix: list[dict[str, Any]],
    source_overview: dict[str, Any],
    mention_sentiment_analysis: dict[str, Any],
    competitor_metrics: list[dict[str, Any]],
    executive_summary: str,
    key_findings: list[str],
) -> str:
    brand_name = str(brand_profile.get("brand_name", "") or "品牌").strip() or "品牌"
    brand_mention_rate = _safe_ratio(summary_metrics.get("brand_mention_rate", metrics.get("mention_rate", 0)))
    total_questions = int(metrics.get("total_questions", 0) or 0)
    mention_total = int(metrics.get("total_mentions", 0) or 0)
    scenario_total = int(summary_metrics.get("scenario_total", len(scenario_matrix)) or len(scenario_matrix))
    scenario_hit_count = int(summary_metrics.get("scenario_hit_count", 0) or 0)
    content_citation_rate = _safe_ratio(summary_metrics.get("content_citation_rate", 0))
    official_citation_rate = _safe_ratio(source_overview.get("official_citation_rate", 0))
    official_citations = int(source_overview.get("official_citations", 0) or 0)
    total_citations = int(source_overview.get("total_citations", 0) or 0)
    brand_domain = str(source_overview.get("brand_domain", "") or "").strip()

    brand_payload = mention_sentiment_analysis.get("brand", {}) if isinstance(mention_sentiment_analysis, dict) else {}
    sentiment_summary = brand_payload.get("summary", {}) if isinstance(brand_payload, dict) else {}
    positive_count = int(sentiment_summary.get("positive", 0) or 0)
    neutral_count = int(sentiment_summary.get("neutral", 0) or 0)
    negative_count = int(sentiment_summary.get("negative", 0) or 0)

    negative_items = _pick_negative_items(mention_sentiment_analysis)
    negative_labels = _build_negative_labels(negative_items)
    competitor_threats = _build_competitor_threats(competitor_metrics, brand_mention_rate)

    top_domains = _sort_top_domains(source_overview)
    mention_domains = _pick_brand_mention_domains(mention_sentiment_analysis)
    official_titles = [
        title for title in source_overview.get("official_top_titles", []) or []
        if isinstance(title, str) and title.strip()
    ][:3]

    covered_topics = [
        item for item in scenario_matrix
        if isinstance(item, dict) and item.get("brand_present")
    ]
    missing_topics = [
        item for item in scenario_matrix
        if isinstance(item, dict) and not item.get("brand_present")
    ]
    defend_topics = [
        item for item in covered_topics
        if str(item.get("battle_status", "")) in {"advantage", "defend"}
    ]
    marginalized_topics = [
        item for item in scenario_matrix
        if isinstance(item, dict) and str(item.get("battle_status", "")) in {"contested", "missing"}
    ]

    lines: list[str] = [
        "## 摘要信息",
        executive_summary.strip() or (
            f"{brand_name} 本轮共覆盖 {scenario_total} 个业务主题，"
            f"品牌被提及 {mention_total} 次，提及率 {_format_rate(brand_mention_rate)}。"
        ),
    ]

    if key_findings:
        lines.append("")
        for finding in key_findings[:4]:
            text = str(finding or "").strip()
            if text:
                lines.append(f"- {text}")

    lines.extend([
        "",
        "## 一、提及率指标",
        (
            f"- 本次共分析 {total_questions} 个问题/场景，{brand_name} 在其中被提及 {mention_total} 次，"
            f"品牌提及率为 {_format_rate(brand_mention_rate)}，覆盖 {scenario_hit_count}/{scenario_total} 个业务主题。"
        ),
        (
            f"- 情感分布：正向 {positive_count} 次，中性 {neutral_count} 次，负向 {negative_count} 次。"
            f"{' 当前未发现明确负向提及。' if negative_count == 0 else ''}"
        ),
    ])
    if negative_labels:
        lines.append(f"- 负向提及主要集中在：{'；'.join(negative_labels)}。")
    if competitor_threats:
        threat_parts = [
            f"{item.get('name')}（提及率 {_format_rate(item.get('mention_rate', 0))}，{_summarize_competitor_sentiment(item.get('sentiment'))}）"
            for item in competitor_threats
        ]
        lines.append(f"- 当前威胁竞品：{'、'.join(threat_parts)}。")
    else:
        lines.append("- 当前未观察到提及率与本品牌接近的强威胁竞品。")

    lines.extend([
        "",
        "## 二、答案引用信息分布",
        (
            f"- 本轮共识别 {total_citations} 次答案引用，整体内容引用率 {_format_rate(content_citation_rate)}；"
            f"官网引用 {official_citations} 次，官网引用率 {_format_rate(official_citation_rate)}。"
        ),
    ])
    if top_domains:
        top_domain_parts = [
            f"{item.get('domain')}（{int(item.get('count', 0) or 0)} 次）"
            for item in top_domains[:5]
        ]
        lines.append(f"- 总体来源分布：{'、'.join(top_domain_parts)}。")
    if mention_domains:
        mention_domain_parts = [f"{domain}（{count} 次）" for domain, count in mention_domains[:5]]
        lines.append(f"- 在提及 {brand_name} 的回答中，高频来源为：{'、'.join(mention_domain_parts)}。")
    else:
        lines.append(f"- 在提及 {brand_name} 的回答中，当前还没有稳定的高频引用来源。")
    if brand_domain:
        official_text = f"{brand_domain} 已进入引用链路" if official_citations > 0 else f"{brand_domain} 本轮没有进入引用链路"
        if official_titles:
            official_text += f"，当前出现的官网标题包括：{'；'.join(official_titles)}"
        lines.append(f"- 官网出现情况：{official_text}。")
    lines.extend(_build_platform_preference_lines(source_overview))

    lines.extend([
        "",
        "## 三、业务主题覆盖",
        f"- 本次共涉及 {scenario_total} 个业务主题，其中 {brand_name} 已进入 {scenario_hit_count} 个主题。",
    ])
    if defend_topics:
        preferred = [
            str(item.get("scenario_label", "")).strip()
            for item in defend_topics[:5]
            if str(item.get("scenario_label", "")).strip()
        ]
        if preferred:
            lines.append(f"- 品牌被优先推荐的主题：{'、'.join(preferred)}。")
    if marginalized_topics:
        marginalized = [
            str(item.get("scenario_label", "")).strip()
            for item in marginalized_topics[:5]
            if str(item.get("scenario_label", "")).strip()
        ]
        if marginalized:
            lines.append(f"- 品牌被边缘化或竞争激烈的主题：{'、'.join(marginalized)}。")
    if missing_topics:
        missing = [
            str(item.get("scenario_label", "")).strip()
            for item in missing_topics[:5]
            if str(item.get("scenario_label", "")).strip()
        ]
        if missing:
            lines.append(f"- 品牌缺席的主题：{'、'.join(missing)}。")

    lines.extend([
        "",
        "## 四、进一步建议",
    ])
    if missing_topics:
        top_missing = [
            str(item.get("scenario_label", "")).strip()
            for item in missing_topics[:3]
            if str(item.get("scenario_label", "")).strip()
        ]
        lines.append(f"- 主题补位：优先围绕 {'、'.join(top_missing)} 补齐官网内容、FAQ 与对比型页面，先进入回答。")
    if negative_items:
        lines.append("- 负向修复：针对负向提及中的具体质疑点补齐事实证据、参数解释与使用场景说明，避免 AI 回答继续放大负面标签。")
    lines.append("- 平台优化：针对四大平台各自高频引用来源，优先布局更容易被其采纳的内容域名与页面类型。")
    lines.append("- 深挖方向：继续追问负向提及来自哪些平台、哪些问题最容易丢失官网引用、哪些竞品在同题竞争中持续压制本品牌。")

    return "\n".join(line for line in lines if line is not None).strip()


def ensure_report_markdown(
    report_data: dict[str, Any],
    *,
    brand_profile: dict[str, Any],
    metrics: dict[str, Any],
    summary_metrics: dict[str, Any],
    scenario_matrix: list[dict[str, Any]],
    source_overview: dict[str, Any],
    mention_sentiment_analysis: dict[str, Any],
    competitor_metrics: list[dict[str, Any]],
) -> dict[str, Any]:
    markdown = str(report_data.get("report_markdown", "") or "").strip()
    required_headers = [
        "## 摘要信息",
        "## 一、提及率指标",
        "## 二、答案引用信息分布",
        "## 三、业务主题覆盖",
        "## 四、进一步建议",
    ]
    if (
        len(markdown) < 120
        or any(header not in markdown for header in required_headers)
        or _contains_reasoning_leak(markdown)
    ):
        report_data["report_markdown"] = build_report_markdown(
            brand_profile=brand_profile,
            metrics=metrics,
            summary_metrics=summary_metrics,
            scenario_matrix=scenario_matrix,
            source_overview=source_overview,
            mention_sentiment_analysis=mention_sentiment_analysis,
            competitor_metrics=competitor_metrics,
            executive_summary=str(report_data.get("executive_summary", "") or "").strip(),
            key_findings=[
                str(item or "").strip()
                for item in report_data.get("key_findings", []) or []
                if str(item or "").strip()
            ],
        )
    return report_data


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


def generate_fallback_report(
    metrics: dict[str, Any],
    brand_profile: dict[str, Any],
    summary_metrics: dict[str, Any] | None = None,
    scenario_matrix: list[dict[str, Any]] | None = None,
    source_overview: dict[str, Any] | None = None,
    mention_sentiment_analysis: dict[str, Any] | None = None,
    competitor_metrics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate degraded but UI-compatible report data when the LLM fails."""
    brand_name = brand_profile.get("brand_name", "品牌")
    mention_rate = metrics.get("mention_rate", 0)

    if mention_rate >= 0.7:
        summary = (
            f"{brand_name} 的 AI 平台可见性分析已完成。"
            f"整体提及率为 {mention_rate:.1%}，品牌已进入较多回答场景，表现较强。"
        )
    elif mention_rate >= 0.4:
        summary = (
            f"{brand_name} 的 AI 平台可见性分析已完成。"
            f"整体提及率为 {mention_rate:.1%}，已有一定存在感，但仍有明显提升空间。"
        )
    else:
        summary = (
            f"{brand_name} 的 AI 平台可见性分析已完成。"
            f"整体提及率为 {mention_rate:.1%}，当前露出偏弱，建议优先优化内容策略。"
        )

    report = {
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
    return ensure_report_markdown(
        report,
        brand_profile=brand_profile,
        metrics=metrics,
        summary_metrics=summary_metrics or {},
        scenario_matrix=scenario_matrix or [],
        source_overview=source_overview or {},
        mention_sentiment_analysis=mention_sentiment_analysis or {},
        competitor_metrics=competitor_metrics or [],
    )
