"""Scenario-first contract builders for A5 report output."""

from typing import Any

from app.core.utils import extract_domain
from app.workflow.brand_mentions import content_mentions_brand
from app.workflow.nodes_a4 import PLATFORMS


def _safe_rate(numerator: int | float, denominator: int | float) -> float:
    """Return a normalized 0..1 rate."""
    if not denominator:
        return 0.0
    return round(max(0.0, min(1.0, numerator / denominator)), 4)


def _name_in_text(name: str, text: str) -> bool:
    """Case-insensitive substring match for brand detection."""
    if not name or not text:
        return False
    return name.lower() in text.lower()


def _infer_scenario_priority(result: dict[str, Any]) -> str:
    """Read scenario priority from question metadata, default to medium."""
    for key in ("scenario_priority", "priority", "question_priority"):
        value = str(result.get(key, "")).lower()
        if value in {"high", "medium", "low"}:
            return value
    return "medium"


def _build_source_overview(citation_analysis: dict[str, Any]) -> dict[str, Any]:
    """Convert legacy citation_analysis into V2 source_overview shape."""
    total_citations = int(citation_analysis.get("total_citations", 0) or 0)
    official_citations = int(citation_analysis.get("official_citations", 0) or 0)
    branded_citations = int(citation_analysis.get("branded_citations", 0) or 0)
    brand_domain = str(citation_analysis.get("brand_domain", "") or "")
    unique_domains = int(citation_analysis.get("unique_domains", 0) or 0)

    top_domains: list[dict[str, Any]] = []
    for item in citation_analysis.get("top_domains", []) or []:
        if not isinstance(item, dict):
            continue
        count = int(item.get("count", 0) or 0)
        raw_share = item.get("share", 0) or 0
        share = (
            raw_share / 100
            if isinstance(raw_share, (int, float)) and raw_share > 1
            else raw_share
        )
        top_domains.append(
            {
                "domain": item.get("domain", ""),
                "count": count,
                "share": round(max(0.0, min(1.0, float(share or 0))), 4),
                "is_official": bool(item.get("is_official", False)),
                "sample_titles": item.get("sample_titles", []) or [],
            }
        )

    raw_platform_stats = citation_analysis.get("platform_citation_stats", {}) or {}
    platform_citation_stats: dict[str, Any] = {}
    if isinstance(raw_platform_stats, dict):
        for platform, stats in raw_platform_stats.items():
            if not isinstance(stats, dict):
                continue
            platform_total = int(stats.get("total_citations", 0) or 0)
            platform_official = int(stats.get("official_count", 0) or 0)
            platform_branded = int(stats.get("branded_count", 0) or 0)
            platform_citation_stats[str(platform)] = {
                "total_citations": platform_total,
                "official_citations": platform_official,
                "branded_citations": platform_branded,
                "official_citation_rate": _safe_rate(platform_official, platform_total),
                "brand_content_citation_rate": _safe_rate(
                    platform_branded,
                    platform_total,
                ),
                "unique_domains": int(stats.get("unique_domains", 0) or 0),
                "top_domains": [
                    {
                        "domain": domain_item.get("domain", ""),
                        "count": int(domain_item.get("count", 0) or 0),
                    }
                    for domain_item in stats.get("top_domains", []) or []
                    if isinstance(domain_item, dict)
                ],
            }

    return {
        "official_citation_rate": _safe_rate(official_citations, total_citations),
        "official_citations": official_citations,
        "branded_citations": branded_citations,
        "brand_content_citation_rate": _safe_rate(
            branded_citations,
            total_citations,
        ),
        "total_citations": total_citations,
        "unique_domains": unique_domains,
        "brand_domain": brand_domain,
        "top_domains": top_domains,
        "official_top_titles": [
            title
            for item in top_domains
            if item.get("is_official")
            for title in item.get("sample_titles", [])[:3]
            if isinstance(title, str) and title.strip()
        ][:6],
        "platform_citation_stats": platform_citation_stats,
        "note": "内容引用率口径为品牌相关引用次数 / 总引用次数；官网引用率口径为官网引用次数 / 总引用次数。",
    }


def _build_scenario_matrix(
    fetch_results: list,
    brand_profile: dict[str, Any],
    competitors: list[dict[str, Any]],
    source_overview: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build scenario rows from A4 fetch results."""
    brand_name = str(brand_profile.get("brand_name", "") or "")
    brand_name_en = str(brand_profile.get("brand_name_en", "") or "")
    brand_label = brand_name or brand_name_en or "本品牌"
    brand_domain = str(source_overview.get("brand_domain", "") or "")
    competitor_names = [
        str(item.get("name", "") or "")
        for item in competitors
        if isinstance(item, dict) and item.get("name")
    ]

    scenario_matrix: list[dict[str, Any]] = []
    for idx, result in enumerate(fetch_results, start=1):
        scenario_id = str(result.get("question_id") or f"q_{idx:02d}")
        scenario_label = str(result.get("question_text") or f"场景 {idx}")
        scenario_priority = _infer_scenario_priority(result)
        platform_results = result.get("platform_results", []) or []
        successful_results = [
            pr for pr in platform_results if isinstance(pr, dict) and pr.get("success")
        ]

        present_platforms: list[str] = []
        official_source_domains: set[str] = set()
        competitors_present: set[str] = set()
        winner_counts: dict[str, int] = {}
        brand_present = False

        for pr in successful_results:
            platform = str(pr.get("platform", "") or "")
            answer = pr.get("answer", {})
            content = (
                answer.get("content", "") if isinstance(answer, dict) else str(answer)
            )
            has_brand_mention = (
                bool(answer.get("has_brand_mention", False))
                if isinstance(answer, dict)
                else False
            )
            if not has_brand_mention:
                has_brand_mention = content_mentions_brand(content, brand_profile)

            if has_brand_mention:
                brand_present = True
                if platform:
                    present_platforms.append(platform)
                winner_counts[brand_label] = winner_counts.get(brand_label, 0) + 1

            for competitor_name in competitor_names:
                if _name_in_text(competitor_name, content):
                    competitors_present.add(competitor_name)
                    winner_counts[competitor_name] = (
                        winner_counts.get(competitor_name, 0) + 1
                    )

            for citation in pr.get("citations", []) or []:
                if not isinstance(citation, dict):
                    continue
                citation_domain = extract_domain(citation.get("url", "") or "")
                if (
                    brand_domain
                    and citation_domain
                    and (
                        citation_domain == brand_domain
                        or citation_domain.endswith("." + brand_domain)
                    )
                ):
                    official_source_domains.add(citation_domain)

        unique_platforms = sorted(
            {platform for platform in present_platforms if platform}
        )
        official_citation_present = bool(official_source_domains)
        competitor_names_sorted = sorted(competitors_present)

        max_mentions = max(winner_counts.values(), default=0)
        winner_brands = sorted(
            [
                name
                for name, count in winner_counts.items()
                if max_mentions > 0 and count == max_mentions
            ]
        )

        if not brand_present and competitor_names_sorted:
            battle_status = "missing"
        elif (
            brand_present
            and winner_brands == [brand_label]
            and not competitor_names_sorted
        ):
            battle_status = "advantage"
        elif brand_present and brand_label in winner_brands:
            battle_status = "defend"
        else:
            battle_status = "contested"

        if battle_status == "missing":
            evidence = (
                f"{'、'.join(competitor_names_sorted[:3])}已出现在回答中，品牌尚未进入该场景。"
                if competitor_names_sorted
                else "品牌尚未进入该场景。"
            )
            action_hint = "补充该场景的官网内容与 FAQ，争取先进入回答。"
        elif brand_present and not official_citation_present:
            evidence = "品牌已被提及，但官网内容尚未进入引用链路。"
            action_hint = "补强官网页面的结构化信息与证据内容，提升官网被引用概率。"
        elif battle_status == "contested":
            evidence = (
                f"品牌已出现，但与 {'、'.join(competitor_names_sorted[:2])} 仍处于争夺状态。"
                if competitor_names_sorted
                else "品牌已出现，但主导优势仍不稳定。"
            )
            action_hint = "强化该场景的对比型与解释型内容，提升主胜稳定性。"
        elif battle_status == "defend":
            evidence = (
                f"品牌与 {'、'.join(competitor_names_sorted[:2])} 同场出现，但目前保持主胜。"
                if competitor_names_sorted
                else "品牌已进入该场景并保持稳定露出。"
            )
            action_hint = "继续维护该场景内容，并强化官网引用链路。"
        else:
            evidence = "品牌在该场景中稳定出现，暂未观察到明显竞品压力。"
            action_hint = "维持当前内容优势，持续巩固该场景表现。"

        scenario_matrix.append(
            {
                "scenario_id": scenario_id,
                "scenario_label": scenario_label,
                "scenario_priority": scenario_priority,
                "brand_present": brand_present,
                "present_platforms": unique_platforms,
                "official_citation_present": official_citation_present,
                "official_source_domains": sorted(official_source_domains),
                "competitors_present": competitor_names_sorted,
                "winner_brands": winner_brands,
                "battle_status": battle_status,
                "risk_level": "low",
                "evidence": evidence,
                "query_examples": [scenario_label],
                "action_hint": action_hint,
                "confidence": round(
                    max(
                        0.0, min(1.0, len(successful_results) / max(len(PLATFORMS), 1))
                    ),
                    2,
                ),
            }
        )

    return scenario_matrix


def _build_summary_metrics(
    metrics: dict[str, Any],
    scenario_matrix: list[dict[str, Any]],
    source_overview: dict[str, Any],
    mention_sentiment_analysis: dict[str, Any],
) -> dict[str, Any]:
    """Aggregate top-level summary metrics for Report V2."""
    scenario_total = len(scenario_matrix)
    scenario_hit_count = sum(1 for item in scenario_matrix if item.get("brand_present"))
    mention_rate = float(metrics.get("mention_rate", 0) or 0)
    official_citation_rate = float(
        source_overview.get("official_citation_rate", 0) or 0
    )
    content_citation_rate = float(
        source_overview.get("brand_content_citation_rate", 0) or 0
    )

    status_summary = (
        f"品牌提及率 {mention_rate:.1%}"
        f"，内容引用率 {content_citation_rate:.1%}"
        f"，已覆盖 {scenario_hit_count}/{scenario_total} 个场景。"
    )

    return {
        "brand_mention_rate": max(0.0, min(1.0, mention_rate)),
        "content_citation_rate": content_citation_rate,
        "official_citation_rate": max(0.0, min(1.0, official_citation_rate)),
        "accuracy_score": None,
        "accuracy_status": "pending",
        "scenario_total": scenario_total,
        "scenario_hit_count": scenario_hit_count,
        "high_risk_scenario_count": 0,
        "status_summary": status_summary,
    }


def _build_report_summary_metrics(
    summary_metrics: dict[str, Any]
) -> list[dict[str, Any]]:
    """Build metric cards for Report V2 summary section."""
    mention_rate = float(summary_metrics.get("brand_mention_rate", 0) or 0)
    content_citation_rate = float(summary_metrics.get("content_citation_rate", 0) or 0)
    scenario_hit_count = int(summary_metrics.get("scenario_hit_count", 0) or 0)
    scenario_total = int(summary_metrics.get("scenario_total", 0) or 0)

    return [
        {
            "id": "brand_mention_rate",
            "label": "品牌提及率",
            "value": mention_rate,
            "unit": "ratio",
            "description": "品牌在 AI 回答中被直接提到的频率。",
            "status": (
                "good"
                if mention_rate >= 0.5
                else "warning" if mention_rate >= 0.2 else "risk"
            ),
        },
        {
            "id": "content_citation_rate",
            "label": "内容引用率",
            "value": content_citation_rate,
            "unit": "ratio",
            "description": "品牌被提及的问题里，有多少已经进入了引用来源链。",
            "status": (
                "good"
                if content_citation_rate >= 0.3
                else "warning" if content_citation_rate >= 0.1 else "risk"
            ),
        },
        {
            "id": "scenario_coverage_count",
            "label": "场景覆盖数",
            "value": scenario_hit_count,
            "description": f"品牌已经进入回答的问题数，当前共识别 {scenario_total} 个场景。",
            "status": "good" if scenario_hit_count >= 3 else "warning",
        },
    ]


def _build_mentions_section(
    mention_sentiment_analysis: dict[str, Any],
) -> dict[str, Any]:
    brand_payload = (
        mention_sentiment_analysis.get("brand", {})
        if isinstance(mention_sentiment_analysis, dict)
        else {}
    )
    brand_items = (
        brand_payload.get("items", []) if isinstance(brand_payload, dict) else []
    )
    groups = (
        mention_sentiment_analysis.get("groups", [])
        if isinstance(mention_sentiment_analysis, dict)
        else []
    )
    summary = (
        brand_payload.get("summary", {}) if isinstance(brand_payload, dict) else {}
    )

    positive = int(summary.get("positive", 0) or 0)
    neutral = int(summary.get("neutral", 0) or 0)
    negative = int(summary.get("negative", 0) or 0)

    return {
        "title": "提及率分析",
        "description": "",
        "mention_count": len(
            {
                str(item.get("scenario_id") or item.get("scenario_label") or "")
                for item in brand_items
                if str(
                    item.get("scenario_id") or item.get("scenario_label") or ""
                ).strip()
            }
        ),
        "sentiment_summary": {
            "positive": positive,
            "neutral": neutral,
            "negative": negative,
        },
        "brand_mentions": brand_items,
        "competitor_mentions": [
            mention
            for payload in (mention_sentiment_analysis.get("competitors", []) or [])
            if isinstance(payload, dict)
            for mention in (payload.get("items", []) or [])
            if isinstance(mention, dict)
        ],
        "groups": groups,
    }


def _build_report_v2_sections(
    report_data: dict[str, Any],
    summary_metrics: dict[str, Any],
    scenario_matrix: list[dict[str, Any]],
    source_overview: dict[str, Any],
    citation_analysis: dict[str, Any],
    mention_sentiment_analysis: dict[str, Any],
) -> dict[str, Any]:
    """Build minimal Report V2 sections from facts and explicit agent output."""
    executive_summary_payload = report_data.get("executive_summary", "")
    if isinstance(executive_summary_payload, dict):
        executive_summary_text = str(
            executive_summary_payload.get("one_line_judgment") or ""
        ).strip()
    else:
        executive_summary_text = str(
            report_data.get("executive_summary_text") or executive_summary_payload or ""
        ).strip()
    report_summary = {
        "title": "品牌现状",
        "description": "",
        "subtitle": "",
        "summary": executive_summary_text,
        "status_summary": "",
        "metrics": _build_report_summary_metrics(summary_metrics),
        "executive_summary": executive_summary_payload,
        "executive_summary_text": executive_summary_text,
        "key_findings": report_data.get("key_findings", []),
    }

    scenario_coverage = {
        "title": "场景覆盖",
        "description": "",
        "summary": "",
        "items": scenario_matrix,
    }

    source_section = {
        "title": "信息源分析",
        "description": "",
        "summary": "",
        "official_citation_rate": source_overview.get("official_citation_rate", 0),
        "source_overview": source_overview,
        "citation_analysis": citation_analysis,
    }

    mentions_section = _build_mentions_section(mention_sentiment_analysis)

    return {
        "report_summary": report_summary,
        "scenario_coverage": scenario_coverage,
        "source_section": source_section,
        "mentions_section": mentions_section,
        "report_v2": {
            "summary": report_summary,
            "mentions": mentions_section,
            "scenarioCoverage": scenario_coverage,
            "sources": source_section,
        },
    }
