"""Scenario-first contract builders for A5 report output."""

from typing import Any

from app.core.utils import extract_domain
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
    brand_domain = str(citation_analysis.get("brand_domain", "") or "")
    unique_domains = int(citation_analysis.get("unique_domains", 0) or 0)

    top_domains: list[dict[str, Any]] = []
    for item in citation_analysis.get("top_domains", []) or []:
        if not isinstance(item, dict):
            continue
        count = int(item.get("count", 0) or 0)
        raw_share = item.get("share", 0) or 0
        share = raw_share / 100 if isinstance(raw_share, (int, float)) and raw_share > 1 else raw_share
        top_domains.append({
            "domain": item.get("domain", ""),
            "count": count,
            "share": round(max(0.0, min(1.0, float(share or 0))), 4),
            "is_official": bool(item.get("is_official", False)),
            "sample_titles": item.get("sample_titles", []) or [],
        })

    raw_platform_stats = citation_analysis.get("platform_citation_stats", {}) or {}
    platform_citation_stats: dict[str, Any] = {}
    if isinstance(raw_platform_stats, dict):
        for platform, stats in raw_platform_stats.items():
            if not isinstance(stats, dict):
                continue
            platform_total = int(stats.get("total_citations", 0) or 0)
            platform_official = int(stats.get("official_count", 0) or 0)
            platform_citation_stats[str(platform)] = {
                "total_citations": platform_total,
                "official_citations": platform_official,
                "official_citation_rate": _safe_rate(platform_official, platform_total),
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
        "note": "官网引用率口径为官网引用次数 / 总引用次数。",
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
    brand_aliases = [name for name in [brand_name, brand_name_en] if name]
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
            pr for pr in platform_results
            if isinstance(pr, dict) and pr.get("success")
        ]

        present_platforms: list[str] = []
        official_source_domains: set[str] = set()
        competitors_present: set[str] = set()
        winner_counts: dict[str, int] = {}
        brand_present = False

        for pr in successful_results:
            platform = str(pr.get("platform", "") or "")
            answer = pr.get("answer", {})
            content = answer.get("content", "") if isinstance(answer, dict) else str(answer)
            has_brand_mention = (
                bool(answer.get("has_brand_mention", False))
                if isinstance(answer, dict)
                else False
            )
            if not has_brand_mention and any(_name_in_text(alias, content) for alias in brand_aliases):
                has_brand_mention = True

            if has_brand_mention:
                brand_present = True
                if platform:
                    present_platforms.append(platform)
                winner_counts[brand_label] = winner_counts.get(brand_label, 0) + 1

            for competitor_name in competitor_names:
                if _name_in_text(competitor_name, content):
                    competitors_present.add(competitor_name)
                    winner_counts[competitor_name] = winner_counts.get(competitor_name, 0) + 1

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

        unique_platforms = sorted({platform for platform in present_platforms if platform})
        official_citation_present = bool(official_source_domains)
        competitor_names_sorted = sorted(competitors_present)

        max_mentions = max(winner_counts.values(), default=0)
        winner_brands = sorted([
            name for name, count in winner_counts.items()
            if max_mentions > 0 and count == max_mentions
        ])

        if not brand_present and competitor_names_sorted:
            battle_status = "missing"
        elif brand_present and winner_brands == [brand_label] and not competitor_names_sorted:
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

        scenario_matrix.append({
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
                max(0.0, min(1.0, len(successful_results) / max(len(PLATFORMS), 1))),
                2,
            ),
        })

    return scenario_matrix


def _build_risk_map(scenario_matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build one primary risk item per scenario."""
    risk_items: list[dict[str, Any]] = []

    for scenario in scenario_matrix:
        scenario_id = str(scenario.get("scenario_id", ""))
        scenario_label = str(scenario.get("scenario_label", ""))
        scenario_priority = str(scenario.get("scenario_priority", "medium"))
        brand_present = bool(scenario.get("brand_present", False))
        official_citation_present = bool(scenario.get("official_citation_present", False))
        battle_status = str(scenario.get("battle_status", "missing"))
        competitors_present = scenario.get("competitors_present", []) or []

        risk_type = ""
        severity = "low"
        reason = ""

        if not brand_present and competitors_present:
            risk_type = "missing_presence"
            severity = "high" if scenario_priority == "high" else "medium"
            reason = "品牌在该场景中缺席，竞品已稳定占位。"
        elif brand_present and battle_status == "contested":
            risk_type = "competitor_substitution"
            severity = "high" if scenario_priority == "high" else "medium"
            reason = "品牌虽然已出现，但主导权不稳定，竞品存在替代风险。"
        elif brand_present and not official_citation_present:
            risk_type = "no_official_citation"
            severity = "medium" if scenario_priority == "high" else "low"
            reason = "品牌已被提及，但官网未被引用，官方信息链路偏弱。"
        elif brand_present and battle_status == "defend":
            risk_type = "weak_presence"
            severity = "low"
            reason = "品牌已出现，但仍存在持续防守压力。"

        if not risk_type:
            continue

        risk_items.append({
            "risk_id": f"risk_{scenario_id}_{risk_type}",
            "risk_type": risk_type,
            "scenario_id": scenario_id,
            "scenario_label": scenario_label,
            "severity": severity,
            "reason": reason,
            "evidence": scenario.get("evidence", ""),
            "mitigation_hint": scenario.get("action_hint", ""),
        })
        scenario["risk_level"] = severity

    return risk_items


def _build_competitor_battles(
    scenario_matrix: list[dict[str, Any]],
    competitors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate scenario-level battle data per competitor."""
    known_competitors = [
        str(item.get("name", "") or "")
        for item in competitors
        if isinstance(item, dict) and item.get("name")
    ]
    observed_competitors = {
        name
        for scenario in scenario_matrix
        for name in scenario.get("competitors_present", []) or []
        if name
    }
    all_competitors = sorted(set(known_competitors) | observed_competitors)

    competitor_battles: list[dict[str, Any]] = []
    for competitor_name in all_competitors:
        shared_scenarios = 0
        competitor_only_scenarios = 0
        brand_only_scenarios = 0
        conflict_scenarios: list[tuple[str, str]] = []

        for scenario in scenario_matrix:
            brand_present = bool(scenario.get("brand_present", False))
            competitors_present = scenario.get("competitors_present", []) or []
            is_present = competitor_name in competitors_present

            if brand_present and is_present:
                shared_scenarios += 1
                conflict_scenarios.append((
                    str(scenario.get("scenario_priority", "medium")),
                    str(scenario.get("scenario_label", "")),
                ))
            elif is_present and not brand_present:
                competitor_only_scenarios += 1
                conflict_scenarios.append((
                    str(scenario.get("scenario_priority", "medium")),
                    str(scenario.get("scenario_label", "")),
                ))
            elif brand_present and not is_present:
                brand_only_scenarios += 1

        if competitor_only_scenarios >= shared_scenarios and competitor_only_scenarios > 0:
            pressure_level = "high"
        elif shared_scenarios > 0 or competitor_only_scenarios > 0:
            pressure_level = "medium"
        else:
            pressure_level = "low"

        priority_order = {"high": 0, "medium": 1, "low": 2}
        top_conflict_scenarios = [
            label for _, label in sorted(
                conflict_scenarios,
                key=lambda item: (priority_order.get(item[0], 9), item[1]),
            )[:3]
        ]

        competitor_battles.append({
            "competitor": competitor_name,
            "shared_scenarios": shared_scenarios,
            "competitor_only_scenarios": competitor_only_scenarios,
            "brand_only_scenarios": brand_only_scenarios,
            "pressure_level": pressure_level,
            "top_conflict_scenarios": top_conflict_scenarios,
        })

    return competitor_battles


def _build_action_queue(
    scenario_matrix: list[dict[str, Any]],
    risk_map: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Create scenario-bound action queue from risks."""
    severity_to_priority = {"high": 1, "medium": 2, "low": 3}
    risk_sort_order = {"high": 0, "medium": 1, "low": 2}
    scenario_lookup = {
        str(scenario.get("scenario_id", "")): scenario
        for scenario in scenario_matrix
    }

    sorted_risks = sorted(
        risk_map,
        key=lambda item: (
            risk_sort_order.get(str(item.get("severity", "low")), 9),
            str(item.get("scenario_label", "")),
        ),
    )

    action_queue: list[dict[str, Any]] = []
    for risk in sorted_risks:
        scenario_id = str(risk.get("scenario_id", ""))
        scenario = scenario_lookup.get(scenario_id, {})
        severity = str(risk.get("severity", "low"))
        risk_type = str(risk.get("risk_type", ""))

        if risk_type == "missing_presence":
            target = "提升该场景的提及概率，先进入 AI 回答。"
            expected_impact = "提高该场景进入回答的概率。"
        elif risk_type == "competitor_substitution":
            target = "提升该场景的主胜稳定性，降低竞品替代风险。"
            expected_impact = "提高品牌在争夺场景中的主导概率。"
        elif risk_type == "no_official_citation":
            target = "提升该场景的官网引用概率。"
            expected_impact = "让官方信息更容易被 AI 引用。"
        else:
            target = "稳定该场景的品牌存在感。"
            expected_impact = "降低该场景后续波动风险。"

        action_queue.append({
            "priority": severity_to_priority.get(severity, 3),
            "scenario_id": scenario_id,
            "scenario_label": risk.get("scenario_label", ""),
            "action": scenario.get("action_hint", "") or risk.get("mitigation_hint", ""),
            "target": target,
            "related_competitors": scenario.get("competitors_present", []) or [],
            "owner_hint": "内容团队",
            "expected_impact": expected_impact,
            "difficulty": "medium",
        })

    return action_queue


def _build_summary_metrics(
    metrics: dict[str, Any],
    scenario_matrix: list[dict[str, Any]],
    risk_map: list[dict[str, Any]],
    source_overview: dict[str, Any],
) -> dict[str, Any]:
    """Aggregate top-level summary metrics for Report V2."""
    scenario_total = len(scenario_matrix)
    scenario_hit_count = sum(1 for item in scenario_matrix if item.get("brand_present"))
    missing_high_value_scenario_count = sum(
        1
        for item in scenario_matrix
        if item.get("scenario_priority") == "high" and not item.get("brand_present")
    )
    high_risk_scenario_count = len({
        str(item.get("scenario_id", ""))
        for item in risk_map
        if item.get("severity") == "high"
    })
    platform_coverage_count = len({
        platform
        for item in scenario_matrix
        for platform in item.get("present_platforms", []) or []
        if platform
    })
    platform_total_count = len(PLATFORMS)
    mention_rate = float(metrics.get("mention_rate", 0) or 0)
    official_citation_rate = float(source_overview.get("official_citation_rate", 0) or 0)
    scenario_effective_rate = (
        scenario_hit_count / scenario_total if scenario_total > 0 else 0.0
    )

    status_summary = (
        f"当前品牌已覆盖 {scenario_hit_count}/{scenario_total} 个场景"
        f"，覆盖 {platform_coverage_count}/{platform_total_count} 个平台"
        f"，官网引用率 {official_citation_rate:.1%}"
        f"，仍有 {missing_high_value_scenario_count} 个高价值场景缺席"
        f"，高风险问题 {high_risk_scenario_count} 个。"
    )

    return {
        "brand_mention_rate": max(0.0, min(1.0, mention_rate)),
        "official_citation_rate": max(0.0, min(1.0, official_citation_rate)),
        "platform_coverage_count": platform_coverage_count,
        "platform_total_count": platform_total_count,
        "scenario_total": scenario_total,
        "scenario_hit_count": scenario_hit_count,
        "missing_high_value_scenario_count": missing_high_value_scenario_count,
        "high_risk_scenario_count": high_risk_scenario_count,
        "scenario_effective_rate": max(0.0, min(1.0, scenario_effective_rate)),
        "status_summary": status_summary,
    }



def _build_report_summary_metrics(summary_metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """Build metric cards for Report V2 summary section."""
    mention_rate = float(summary_metrics.get("brand_mention_rate", 0) or 0)
    official_citation_rate = float(summary_metrics.get("official_citation_rate", 0) or 0)
    missing_count = int(summary_metrics.get("missing_high_value_scenario_count", 0) or 0)
    high_risk_count = int(summary_metrics.get("high_risk_scenario_count", 0) or 0)
    platform_coverage_count = int(summary_metrics.get("platform_coverage_count", 0) or 0)
    scenario_hit_count = int(summary_metrics.get("scenario_hit_count", 0) or 0)
    scenario_total = int(summary_metrics.get("scenario_total", 0) or 0)

    return [
        {
            "id": "brand_mention_rate",
            "label": "品牌提及率",
            "value": mention_rate,
            "unit": "ratio",
            "description": "品牌在 AI 回答中被直接提到的频率。",
            "status": "good" if mention_rate >= 0.5 else "warning" if mention_rate >= 0.2 else "risk",
        },
        {
            "id": "official_citation_rate",
            "label": "官网引用率",
            "value": official_citation_rate,
            "unit": "ratio",
            "description": "官网是否真正进入 AI 的引用链路。",
            "status": "good" if official_citation_rate >= 0.3 else "warning" if official_citation_rate >= 0.1 else "risk",
        },
        {
            "id": "platform_coverage_count",
            "label": "覆盖平台数",
            "value": platform_coverage_count,
            "description": "品牌已经进入回答的平台数量。",
            "status": "good" if platform_coverage_count >= 3 else "warning",
        },
        {
            "id": "scenario_hit_count",
            "label": "有效场景数",
            "value": scenario_hit_count,
            "description": f"当前共识别 {scenario_total} 个场景。",
            "status": "good" if scenario_hit_count >= 3 else "warning",
        },
        {
            "id": "missing_high_value_scenario_count",
            "label": "缺席高价值场景",
            "value": missing_count,
            "description": "高价值但品牌仍未进入回答的场景数。",
            "status": "good" if missing_count == 0 else "warning" if missing_count <= 2 else "risk",
        },
        {
            "id": "high_risk_scenario_count",
            "label": "高风险场景",
            "value": high_risk_count,
            "description": "当前需要优先处理的高风险问题数。",
            "status": "good" if high_risk_count == 0 else "warning" if high_risk_count <= 2 else "risk",
        },
    ]



def _coerce_insight_item(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, dict):
        title = str(raw.get("title", "") or raw.get("label", "") or raw.get("scenario_label", "") or "").strip()
        if not title:
            return None
        return {
            "title": title,
            "scenario": str(raw.get("scenario", "") or raw.get("scenario_label", "") or title),
            "evidence": str(raw.get("evidence", "") or raw.get("description", "") or raw.get("reason", "") or "").strip(),
            "platforms": raw.get("platforms", []) or raw.get("present_platforms", []) or [],
            "improvement_hint": str(raw.get("improvement_hint", "") or raw.get("mitigation_hint", "") or "").strip(),
        }
    text = str(raw or "").strip()
    if not text:
        return None
    return {
        "title": text,
        "scenario": text,
        "evidence": text,
        "platforms": [],
        "improvement_hint": "",
    }


def _build_insight_section(
    report_data: dict[str, Any],
    mention_sentiment_analysis: dict[str, Any],
) -> dict[str, Any]:
    explicit_strengths = [
        item for item in (
            _coerce_insight_item(raw) for raw in report_data.get("strengths", []) or []
        ) if item
    ]
    explicit_weaknesses = [
        item for item in (
            _coerce_insight_item(raw) for raw in report_data.get("weaknesses", []) or []
        ) if item
    ]

    brand_payload = mention_sentiment_analysis.get("brand", {}) if isinstance(mention_sentiment_analysis, dict) else {}
    brand_items = brand_payload.get("items", []) if isinstance(brand_payload, dict) else []

    positive_mentions = [item for item in brand_items if item.get("sentiment") == "positive"]
    non_positive_mentions = [item for item in brand_items if item.get("sentiment") in {"neutral", "negative"}]

    sentiment_label = {"positive": "正向", "neutral": "中性", "negative": "负向"}

    sentiment_strengths = []
    for item in positive_mentions[:3]:
        domains = item.get("citation_domains", []) or []
        domain_text = f"，主要引用：{'、'.join(domains[:3])}" if domains else ""
        sentiment_strengths.append({
            "title": f"{item.get('scenario_label', '该场景')}中品牌被{sentiment_label['positive']}提及",
            "scenario": item.get("scenario_label", ""),
            "evidence": f"在 {item.get('platform', 'AI 平台')} 的回答中，品牌被明确正向提及{domain_text}。",
            "platforms": [item.get("platform", "")] if item.get("platform") else [],
            "improvement_hint": "",
            "sentiment": item.get("sentiment"),
            "citation_domains": domains,
            "citation_titles": item.get("citation_titles", []) or [],
            "official_citation_present": item.get("official_citation_present", False),
        })

    sentiment_weaknesses = []
    for item in non_positive_mentions[:4]:
        label = sentiment_label.get(str(item.get("sentiment", "neutral")), "中性")
        domains = item.get("citation_domains", []) or []
        domain_text = f"，主要引用：{'、'.join(domains[:3])}" if domains else ""
        sentiment_weaknesses.append({
            "title": f"{item.get('scenario_label', '该场景')}中品牌呈{label}提及",
            "scenario": item.get("scenario_label", ""),
            "evidence": f"在 {item.get('platform', 'AI 平台')} 的回答中，品牌呈{label}提及{domain_text}。",
            "platforms": [item.get("platform", "")] if item.get("platform") else [],
            "improvement_hint": "优先补强该场景的官网证据、FAQ 和对比型内容。",
            "sentiment": item.get("sentiment"),
            "citation_domains": domains,
            "citation_titles": item.get("citation_titles", []) or [],
            "official_citation_present": item.get("official_citation_present", False),
        })

    strengths = explicit_strengths + [item for item in sentiment_strengths if item["title"] not in {s["title"] for s in explicit_strengths}]
    weaknesses = explicit_weaknesses + [item for item in sentiment_weaknesses if item["title"] not in {w["title"] for w in explicit_weaknesses}]

    summary_bits = []
    summary = brand_payload.get("summary", {}) if isinstance(brand_payload, dict) else {}
    if isinstance(summary, dict):
        if summary.get("positive"):
            summary_bits.append(f"品牌共有 {summary.get('positive', 0)} 条正向提及")
        if summary.get("neutral"):
            summary_bits.append(f"{summary.get('neutral', 0)} 条中性提及待补强")
        if summary.get("negative"):
            summary_bits.append(f"{summary.get('negative', 0)} 条负向提及需优先处理")

    return {
        "title": "洞察",
        "description": "先看品牌当前做得好的地方，以及还需要补强的地方。",
        "summary": "，".join(summary_bits) if summary_bits else "先看品牌当前做得好的地方，以及还需要补强的地方。",
        "strengths": strengths,
        "weaknesses": weaknesses,
    }


def _build_competitor_summary_cards(
    competitor_battles: list[dict[str, Any]],
    mention_sentiment_analysis: dict[str, Any],
) -> list[dict[str, Any]]:
    competitor_payloads = mention_sentiment_analysis.get("competitors", []) if isinstance(mention_sentiment_analysis, dict) else []
    sentiment_map = {}
    for item in competitor_payloads:
        if not isinstance(item, dict):
            continue
        name = str(item.get("competitor", "") or "").strip()
        if not name:
            continue
        sentiment_map[name] = item

    summary_cards = []
    for battle in competitor_battles:
        competitor = str(battle.get("competitor", "") or "").strip()
        sentiment_payload = sentiment_map.get(competitor, {})
        mention_examples = []
        for example in (sentiment_payload.get("items", []) or [])[:3]:
            if not isinstance(example, dict):
                continue
            mention_examples.append({
                "scenario_label": example.get("scenario_label", ""),
                "platform": example.get("platform", ""),
                "sentiment": example.get("sentiment", "neutral"),
                "citation_domains": example.get("citation_domains", []) or [],
            })

        summary_cards.append({
            **battle,
            "sentiment_summary": sentiment_payload.get("summary", {}),
            "mention_examples": mention_examples,
        })

    return summary_cards

def _build_report_v2_sections(
    report_data: dict[str, Any],
    summary_metrics: dict[str, Any],
    scenario_matrix: list[dict[str, Any]],
    competitor_battles: list[dict[str, Any]],
    risk_map: list[dict[str, Any]],
    action_queue: list[dict[str, Any]],
    source_overview: dict[str, Any],
    citation_analysis: dict[str, Any],
    mention_sentiment_analysis: dict[str, Any],
) -> dict[str, Any]:
    """Build structured Report V2 sections for the canvas artifact."""
    report_summary = {
        "title": "品牌现状",
        "description": "先看品牌当前的露出、官网引用和场景覆盖情况。",
        "subtitle": (
            f"品牌提及率 {summary_metrics.get('brand_mention_rate', 0):.1%} | "
            f"官网引用率 {summary_metrics.get('official_citation_rate', 0):.1%} | "
            f"有效场景 {summary_metrics.get('scenario_hit_count', 0)}/{summary_metrics.get('scenario_total', 0)}"
        ),
        "summary": report_data.get("executive_summary", ""),
        "status_summary": summary_metrics.get("status_summary", ""),
        "metrics": _build_report_summary_metrics(summary_metrics),
        "executive_summary": report_data.get("executive_summary", ""),
        "key_findings": report_data.get("key_findings", []),
    }

    scenario_coverage = {
        "title": "有效场景",
        "description": "品牌在哪些场景中已进入回答，哪些场景仍缺席。",
        "summary": (
            f"共识别 {len(scenario_matrix)} 个场景，其中 {summary_metrics.get('scenario_hit_count', 0)} 个场景已出现品牌。"
            if scenario_matrix
            else "当前暂无场景数据。"
        ),
        "items": scenario_matrix,
    }

    competitor_battle = {
        "title": "竞品争夺",
        "description": "聚焦场景层面的竞品争夺，而不是抽象平均分。",
        "summary": (
            f"已识别 {len(competitor_battles)} 个主要竞品争夺对象。"
            if competitor_battles
            else "当前暂无显著竞品争夺。"
        ),
        "overview": report_data.get("competitor_deep_analysis", {}).get("overview", ""),
        "items": competitor_battles,
    }

    risk_section = {
        "title": "缺口与风险",
        "description": "优先处理高价值场景缺席、竞品替代和官网未引用风险。",
        "summary": (
            f"当前共有 {summary_metrics.get('high_risk_scenario_count', 0)} 个高风险场景。"
            if risk_map
            else "当前未识别出显著风险。"
        ),
        "items": [
            {
                "risk_id": item.get("risk_id", ""),
                "risk_type": item.get("risk_type", ""),
                "scenario_label": item.get("scenario_label", ""),
                "severity": item.get("severity", "low"),
                "reason": item.get("reason", ""),
                "impact_summary": item.get("reason", ""),
                "evidence": item.get("evidence", ""),
                "recommended_action_ref": item.get("mitigation_hint", ""),
            }
            for item in risk_map
        ],
    }

    source_section = {
        "title": "信息源分析",
        "description": "AI 平台正在引用哪些来源来形成回答。",
        "summary": source_overview.get("note", ""),
        "official_citation_rate": source_overview.get("official_citation_rate", 0),
        "source_overview": source_overview,
        "citation_analysis": citation_analysis,
    }

    insight_section = _build_insight_section(report_data, mention_sentiment_analysis)

    action_section = {
        "title": "下一步优化",
        "description": "优先处理这些动作，才能改善接下来的战况。",
        "summary": (
            f"已整理 {len(action_queue)} 条优先动作，建议先处理高优先级场景。"
            if action_queue
            else "当前暂无建议动作。"
        ),
        "items": [
            {
                "priority": item.get("priority", 3),
                "scenario_id": item.get("scenario_id", ""),
                "scenario_label": item.get("scenario_label", ""),
                "action": item.get("action", ""),
                "title": item.get("action", ""),
                "target": item.get("target", ""),
                "related_competitors": item.get("related_competitors", []),
                "owner_hint": item.get("owner_hint", ""),
                "expected_impact": item.get("expected_impact", ""),
                "difficulty": item.get("difficulty", ""),
            }
            for item in action_queue
        ],
    }

    return {
        "report_summary": report_summary,
        "scenario_coverage": scenario_coverage,
        "competitor_battle": competitor_battle,
        "risk_section": risk_section,
        "source_section": source_section,
        "insight_section": insight_section,
        "action_queue_section": action_section,
        "report_v2": {
            "summary": report_summary,
            "scenarioCoverage": scenario_coverage,
            "competitorBattle": competitor_battle,
            "risks": risk_section,
            "sources": source_section,
            "insights": insight_section,
            "actionQueue": action_section,
        },
    }

