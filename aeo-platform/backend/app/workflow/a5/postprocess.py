"""A5 report post-processing helpers.

Keeps LLM output enrichment and degraded fallback generation outside the node
so the node focuses on orchestration and persistence.
"""

from __future__ import annotations

from typing import Any

from app.core.utils import extract_domain
from app.workflow.a5 import metrics as a5_metrics
from app.workflow.nodes_a4 import PLATFORMS


def _safe_ratio(value: Any, denominator: Any | None = None) -> float:
    try:
        numerator = float(value or 0)
    except (TypeError, ValueError):
        return 0.0

    if denominator is not None:
        try:
            denominator_value = float(denominator or 0)
        except (TypeError, ValueError):
            return 0.0
        if denominator_value <= 0:
            return 0.0
        numeric = numerator / denominator_value
    else:
        numeric = numerator

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


def _pick_brand_mention_domains(
    mention_sentiment_analysis: dict[str, Any]
) -> list[tuple[str, int]]:
    domain_counts: dict[str, int] = {}
    brand_payload = (
        mention_sentiment_analysis.get("brand", {})
        if isinstance(mention_sentiment_analysis, dict)
        else {}
    )
    brand_items = (
        brand_payload.get("items", []) if isinstance(brand_payload, dict) else []
    )
    for item in brand_items:
        if not isinstance(item, dict):
            continue
        for domain in item.get("citation_domains", []) or []:
            if not isinstance(domain, str) or not domain.strip():
                continue
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
    return sorted(domain_counts.items(), key=lambda pair: (-pair[1], pair[0]))


def _pick_negative_items(
    mention_sentiment_analysis: dict[str, Any]
) -> list[dict[str, Any]]:
    brand_payload = (
        mention_sentiment_analysis.get("brand", {})
        if isinstance(mention_sentiment_analysis, dict)
        else {}
    )
    brand_items = (
        brand_payload.get("items", []) if isinstance(brand_payload, dict) else []
    )
    negative_items = [
        item
        for item in brand_items
        if isinstance(item, dict)
        and str(item.get("sentiment", "neutral")) == "negative"
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
        stats = (
            platform_stats.get(platform, {}) if isinstance(platform_stats, dict) else {}
        )
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


def _domain_to_site_name(domain: str) -> str:
    normalized = str(domain or "").strip().lower()
    if not normalized:
        return "未知来源"
    mapping = {
        "mp.weixin.qq.com": "微信公众号",
        "baijiahao.baidu.com": "百家号",
        "baike.baidu.com": "百度百科",
        "finance.sina.com.cn": "新浪财经",
        "finance.ifeng.com": "凤凰财经",
        "xueqiu.com": "雪球",
        "36kr.com": "36氪",
        "zhihu.com": "知乎",
        "m.chinairn.com": "中研网",
        "bkso.baidu.com": "百度知识搜索",
        "iesdouyin.com": "抖音",
        "toutiao.com": "今日头条",
        "sohu.com": "搜狐",
        "qq.com": "腾讯",
        "163.com": "网易",
        "sohu.com.cn": "搜狐",
        "autohome.com.cn": "汽车之家",
        "chejiahao.autohome.com.cn": "汽车之家车家号",
        "dongchedi.com": "懂车帝",
        "pcauto.com.cn": "太平洋汽车",
        "amway.com.cn": "纽崔莱官网",
    }
    if normalized in mapping:
        return mapping[normalized]
    for key, value in mapping.items():
        if normalized.endswith(key):
            return value
    parts = normalized.split(".")
    if len(parts) >= 2:
        return parts[-2].upper()
    return normalized


def _entity_aliases(
    entity_name: str, extra_aliases: list[str] | None = None
) -> list[str]:
    values = [entity_name, *(extra_aliases or [])]
    aliases: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        aliases.append(text)
    return aliases


def _text_mentions_aliases(text: str, aliases: list[str]) -> bool:
    haystack = str(text or "").lower()
    return any(alias.lower() in haystack for alias in aliases if alias)


def _compute_entity_metric_snapshot(
    fetch_results: list[dict[str, Any]],
    *,
    entity_name: str,
    aliases: list[str],
    official_domain: str,
) -> dict[str, Any]:
    total_questions = len(fetch_results or [])
    mentioned_questions = 0
    successful_answers = 0
    mentioned_answers = 0
    negative_answers = 0
    total_citations = 0
    total_citations_in_mentions = 0
    official_citations = 0
    branded_citations = 0

    for result in fetch_results or []:
        question_has_mention = False
        for platform_result in result.get("platform_results", []) or []:
            if not isinstance(platform_result, dict) or not platform_result.get(
                "success"
            ):
                continue
            successful_answers += 1
            answer = platform_result.get("answer", {})
            content = (
                answer.get("content", "")
                if isinstance(answer, dict)
                else str(answer or "")
            )
            has_brand_mention = _text_mentions_aliases(content, aliases)

            for citation in platform_result.get("citations", []) or []:
                if not isinstance(citation, dict):
                    continue
                total_citations += 1
                if has_brand_mention:
                    total_citations_in_mentions += 1
                url = str(citation.get("url", "") or "")
                title = str(citation.get("title", "") or "")
                domain = extract_domain(url)
                if (
                    official_domain
                    and domain
                    and (
                        domain == official_domain
                        or domain.endswith("." + official_domain)
                    )
                ):
                    official_citations += 1
                    branded_citations += 1
                    continue
                citation_text = f"{title} {url}".lower()
                if any(alias.lower() in citation_text for alias in aliases if alias):
                    branded_citations += 1

            if not has_brand_mention:
                continue
            question_has_mention = True
            mentioned_answers += 1
            if a5_metrics.analyze_sentiment(content) == "negative":
                negative_answers += 1

        if question_has_mention:
            mentioned_questions += 1

    return {
        "entity_name": entity_name,
        "mentioned_questions": mentioned_questions,
        "total_questions": total_questions,
        "successful_answers": successful_answers,
        "mention_rate": _safe_ratio(mentioned_answers, successful_answers),
        "mentioned_answers": mentioned_answers,
        "negative_answers": negative_answers,
        "negative_sentiment_ratio": _safe_ratio(negative_answers, mentioned_answers),
        "official_citations": official_citations,
        "branded_citations": branded_citations,
        "total_citations": total_citations,
        "total_citations_in_mentions": total_citations_in_mentions,
        "official_citation_ratio": _safe_ratio(official_citations, total_citations),
        "brand_content_citation_ratio": _safe_ratio(branded_citations, total_citations),
    }


def _build_metric_diagnosis(
    metric_name: str,
    brand_value: float,
    competitor_a_value: float | None,
    competitor_b_value: float | None,
) -> str:
    comparable = [
        value
        for value in (competitor_a_value, competitor_b_value)
        if isinstance(value, (int, float))
    ]
    if metric_name == "负向情感占比":
        if not comparable:
            return "当前缺少稳定竞品对照，先以本品牌自身负向占比跟踪变化。"
        min_comp = min(comparable)
        if brand_value <= min_comp:
            return "本品牌负向情感占比低于主要竞品，当前舆情压力相对可控。"
        return "本品牌负向情感占比高于竞品，需要优先处理高风险质疑。"

    if not comparable:
        return "当前缺少稳定竞品对照，先以本品牌自身口径做持续回测。"
    max_comp = max(comparable)
    if brand_value >= max_comp:
        return "本品牌当前领先于主要竞品，建议继续巩固该维度优势。"
    return "本品牌低于主要竞品，当前是需要优先补齐的短板。"


def _pick_competitor_pair(competitors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = []
    for item in competitors or []:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        ranked.append(item)
    ranked.sort(key=lambda item: float(item.get("mention_rate", 0) or 0), reverse=True)
    return ranked[:2]


def _build_platform_preference_text(platform: str) -> str:
    normalized = str(platform or "").lower()
    if normalized == "deepseek":
        return "更偏向技术资料、深度长文和相对权威的中文来源。"
    if normalized == "kimi":
        return "更偏向长文解析、媒体报道和信息组织较完整的页面。"
    if normalized == "doubao":
        return "更偏向资讯流、泛生活内容和短内容聚合来源。"
    if normalized in {"hunyuan", "yuanbao"}:
        return "更偏向中文综合内容、社区讨论和微信生态来源。"
    return "偏向中文综合内容与高频可访问来源。"


def _collect_platform_availability(metrics: dict[str, Any]) -> dict[str, list[str]]:
    platform_breakdown = metrics.get("platform_breakdown", {}) or {}
    available: list[str] = []
    unavailable: list[str] = []

    for platform in PLATFORMS:
        stats = (
            platform_breakdown.get(platform, {})
            if isinstance(platform_breakdown, dict)
            else {}
        )
        success_count = int(stats.get("success", 0) or 0)
        label = _display_platform_name(platform)
        if success_count > 0:
            available.append(label)
        else:
            unavailable.append(label)

    return {"available": available, "unavailable": unavailable}


def _build_reliability_notice(metrics: dict[str, Any]) -> str:
    availability = _collect_platform_availability(metrics)
    available = availability.get("available", [])
    unavailable = availability.get("unavailable", [])
    if not unavailable:
        return ""

    available_text = "、".join(available) if available else "暂无"
    unavailable_text = "、".join(unavailable)
    return (
        f"数据边界：本轮仅获得 {available_text} 的有效平台数据；"
        f"{unavailable_text} 平台本轮暂未成功获取有效结果，以下结论不代表这些平台的真实品牌表现。"
    )


def _summary_overclaims_unavailable_platforms(
    summary: str, unavailable_platforms: list[str]
) -> bool:
    normalized = " ".join(str(summary or "").split())
    risk_markers = ("完全缺位", "提及率 0", "提及率0", "0%", "零提及", "没有提及")
    return any(
        platform in normalized and any(marker in normalized for marker in risk_markers)
        for platform in unavailable_platforms
    )


def _build_guarded_summary_text(
    *,
    executive_summary: str,
    default_summary: str,
    metrics: dict[str, Any],
) -> str:
    availability = _collect_platform_availability(metrics)
    unavailable = availability.get("unavailable", [])
    candidate = " ".join(str(executive_summary or "").split()).strip() or default_summary
    if unavailable and _summary_overclaims_unavailable_platforms(candidate, unavailable):
        candidate = default_summary
    return _clip_text(candidate, 220)


def _format_delta_label(current: float, baseline: float) -> str:
    delta = current - baseline
    if abs(delta) < 0.005:
        return "与品牌全景分析基本持平"
    direction = "提升" if delta > 0 else "回落"
    return f"较品牌全景分析{direction} {abs(delta):.1%}"


def _build_baseline_comparison_lines(
    *,
    analysis_mode: str,
    summary_metrics: dict[str, Any],
    baseline_metrics: dict[str, Any] | None,
    baseline_report: dict[str, Any] | None,
) -> list[str]:
    if analysis_mode != "persona":
        return []

    if not baseline_metrics:
        return [
            "### 与品牌全景分析对比",
            "- 当前缺少品牌全景分析基线，本次仅能做场景内诊断，暂时无法判断该画像场景相对品牌整体表现是提升还是回落。",
        ]

    baseline_summary = baseline_metrics.get("summary_metrics", {}) or {}
    current_mention = float(summary_metrics.get("brand_mention_rate", 0) or 0)
    baseline_mention = float(baseline_metrics.get("mention_rate", 0) or 0)
    current_content = float(summary_metrics.get("content_citation_rate", 0) or 0)
    baseline_content = float(baseline_summary.get("content_citation_rate", 0) or 0)
    current_hit = int(summary_metrics.get("scenario_hit_count", 0) or 0)
    current_total = int(summary_metrics.get("scenario_total", 0) or 0)
    baseline_hit = int(baseline_summary.get("scenario_hit_count", 0) or 0)
    baseline_total = int(baseline_summary.get("scenario_total", 0) or 0)

    lines = [
        "### 与品牌全景分析对比",
        f"- 提及率：当前场景 {current_mention:.1%}，品牌全景分析 {baseline_mention:.1%}，{_format_delta_label(current_mention, baseline_mention)}。",
        f"- 内容引用率：当前场景 {current_content:.1%}，品牌全景分析 {baseline_content:.1%}，{_format_delta_label(current_content, baseline_content)}。",
        f"- 场景进入情况：当前画像场景覆盖 {current_hit}/{current_total}，品牌全景分析覆盖 {baseline_hit}/{baseline_total}。",
    ]

    findings = (
        baseline_report.get("key_findings", [])[:2]
        if isinstance(baseline_report, dict)
        else []
    )
    finding_text = "；".join(
        str(item).strip() for item in findings if str(item).strip()
    )
    if finding_text:
        lines.append(f"- 全景分析的核心提醒：{finding_text}。")

    return lines


def _build_aeo_report_facts(
    *,
    fetch_results: list[dict[str, Any]],
    brand_profile: dict[str, Any],
    competitors: list[dict[str, Any]],
    summary_metrics: dict[str, Any],
    scenario_matrix: list[dict[str, Any]],
    source_overview: dict[str, Any],
    mention_sentiment_analysis: dict[str, Any],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    brand_name = (
        str(brand_profile.get("brand_name", "") or "本品牌").strip() or "本品牌"
    )
    brand_aliases = _entity_aliases(
        brand_name,
        [str(brand_profile.get("brand_name_en", "") or "").strip()],
    )
    brand_domain = str(source_overview.get("brand_domain", "") or "").strip()

    brand_snapshot = _compute_entity_metric_snapshot(
        fetch_results,
        entity_name=brand_name,
        aliases=brand_aliases,
        official_domain=brand_domain,
    )

    competitor_snapshots: list[dict[str, Any]] = []
    for competitor in _pick_competitor_pair(competitors):
        website = str(competitor.get("website", "") or "").strip()
        competitor_domain = extract_domain(website) if website else ""
        aliases = _entity_aliases(
            str(competitor.get("name", "") or "").strip(),
            [str(competitor.get("name_en", "") or "").strip()],
        )
        snapshot = _compute_entity_metric_snapshot(
            fetch_results,
            entity_name=str(competitor.get("name", "") or "").strip(),
            aliases=aliases,
            official_domain=competitor_domain,
        )
        competitor_snapshots.append(snapshot)

    while len(competitor_snapshots) < 2:
        competitor_snapshots.append(
            {
                "entity_name": f"竞品{len(competitor_snapshots) + 1}",
                "mention_rate": None,
                "official_citation_ratio": None,
                "brand_content_citation_ratio": None,
                "negative_sentiment_ratio": None,
            }
        )

    metric_rows = []
    metric_specs = [
        ("提及率", "在监测问题中，被至少一个平台提及的比例。", "mention_rate"),
        (
            "官网引用占比",
            "在全部引用链接中，指向该品牌官网的占比。",
            "official_citation_ratio",
        ),
        (
            "品牌内容引用占比",
            "在全部引用链接中，直接指向品牌相关内容的占比。",
            "brand_content_citation_ratio",
        ),
        (
            "负向情感占比",
            "在提及该品牌的回答里，带有明显负向倾向的占比。",
            "negative_sentiment_ratio",
        ),
    ]
    for metric_name, definition, key in metric_specs:
        brand_value = brand_snapshot.get(key)
        comp_a_value = competitor_snapshots[0].get(key)
        comp_b_value = competitor_snapshots[1].get(key)
        metric_rows.append(
            {
                "metric_name": metric_name,
                "definition": definition,
                "brand_value": (
                    _format_rate(brand_value)
                    if isinstance(brand_value, (int, float))
                    else "暂无足够数据"
                ),
                "competitor_a_name": competitor_snapshots[0].get(
                    "entity_name", "竞品A"
                ),
                "competitor_a_value": (
                    _format_rate(comp_a_value)
                    if isinstance(comp_a_value, (int, float))
                    else "暂无足够数据"
                ),
                "competitor_b_name": competitor_snapshots[1].get(
                    "entity_name", "竞品B"
                ),
                "competitor_b_value": (
                    _format_rate(comp_b_value)
                    if isinstance(comp_b_value, (int, float))
                    else "暂无足够数据"
                ),
                "diagnosis": _build_metric_diagnosis(
                    metric_name,
                    float(brand_value or 0),
                    (
                        float(comp_a_value)
                        if isinstance(comp_a_value, (int, float))
                        else None
                    ),
                    (
                        float(comp_b_value)
                        if isinstance(comp_b_value, (int, float))
                        else None
                    ),
                ),
            }
        )

    platform_breakdown = (
        metrics.get("platform_breakdown", {}) if isinstance(metrics, dict) else {}
    )
    platform_citation_stats = (
        source_overview.get("platform_citation_stats", {})
        if isinstance(source_overview, dict)
        else {}
    )
    brand_items = (
        mention_sentiment_analysis.get("brand", {}).get("items", [])
        if isinstance(mention_sentiment_analysis, dict)
        else []
    )
    platform_rows = []
    for platform in ["deepseek", "kimi", "doubao", "hunyuan"]:
        raw_stats = (
            platform_breakdown.get(platform, {})
            if isinstance(platform_breakdown, dict)
            else {}
        )
        citation_stats = (
            platform_citation_stats.get(platform, {})
            if isinstance(platform_citation_stats, dict)
            else {}
        )
        mention_count = int(raw_stats.get("mentions", 0) or 0)
        success_count = int(raw_stats.get("success", 0) or 0)
        total_count = int(raw_stats.get("total", 0) or 0)
        official_rate = _safe_ratio(
            citation_stats.get("official_citations", 0) or 0,
            citation_stats.get("total_citations", 0) or 0,
        )
        platform_mention_items = [
            item
            for item in brand_items
            if isinstance(item, dict)
            and str(item.get("platform", "")).lower() == platform
        ]
        top_domains = [
            _domain_to_site_name(str(item.get("domain", "") or ""))
            for item in (citation_stats.get("top_domains", []) or [])[:3]
            if isinstance(item, dict) and item.get("domain")
        ]
        if success_count <= 0:
            status = "本轮该平台暂未成功获取到有效数据，当前无法判断品牌在该平台的真实占位。"
            problem = "优先修复该平台的抓取稳定性，再判断品牌是否真实缺席或被竞品压制。"
        elif mention_count <= 0:
            status = f"本轮 {success_count}/{total_count or '--'} 次成功回答里尚未稳定提及本品牌。"
            problem = (
                "当前更像收录或语料缺口问题，应优先补齐该平台可抓取的高质量品牌内容。"
            )
        else:
            status = (
                f"本轮成功回答 {success_count}/{total_count or '--'} 次，提及本品牌 {mention_count} 次，"
                f"官网引用占比 {_format_rate(official_rate)}。"
            )
            if official_rate <= 0.02:
                problem = "已有提及，但官方信源弱，建议补结构化官网页与权威长文。"
            elif platform_mention_items:
                problem = "已形成一定占位，可继续补对比型与场景型内容，提升主胜稳定性。"
            else:
                problem = "已有信源进入，但品牌提及还不稳定，需补更直接的品牌表达。"
        if top_domains:
            problem = f"{problem} 当前高频来源主要是 {'、'.join(top_domains)}。"
        platform_rows.append(
            {
                "platform": _display_platform_name(platform),
                "preference": _build_platform_preference_text(platform),
                "status": status,
                "problem": problem,
            }
        )

    missing_examples = [
        item
        for item in scenario_matrix
        if isinstance(item, dict) and item.get("battle_status") == "missing"
    ][:3]
    contested_examples = [
        item
        for item in scenario_matrix
        if isinstance(item, dict)
        and item.get("battle_status") in {"contested", "defend"}
        and (item.get("competitors_present") or [])
    ][:3]

    source_rows = []
    top_domains = _sort_top_domains(source_overview)
    for item in top_domains[:15]:
        domain = str(item.get("domain", "") or "").strip()
        if not domain:
            continue
        source_rows.append(
            {
                "site_name": _domain_to_site_name(domain),
                "domain": domain,
                "count": int(item.get("count", 0) or 0),
                "share": _format_rate(item.get("share", 0)),
            }
        )
    remaining_count = sum(int(item.get("count", 0) or 0) for item in top_domains[15:])

    return {
        "brand_name": brand_name,
        "competitor_a_name": competitor_snapshots[0].get("entity_name", "竞品A"),
        "competitor_b_name": competitor_snapshots[1].get("entity_name", "竞品B"),
        "total_questions": int(
            summary_metrics.get("scenario_total", 0) or len(fetch_results)
        ),
        "metric_rows": metric_rows,
        "platform_rows": platform_rows,
        "missing_examples": missing_examples,
        "contested_examples": contested_examples,
        "source_rows": source_rows,
        "remaining_source_count": remaining_count,
    }


def _display_platform_name(platform: str) -> str:
    mapping = {
        "deepseek": "DeepSeek",
        "kimi": "Kimi",
        "hunyuan": "元宝",
        "yuanbao": "元宝",
        "doubao": "豆包",
    }
    return mapping.get(
        str(platform or "").lower(), str(platform or "").strip() or "未知平台"
    )


def _clip_text(text: Any, limit: int = 72) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return value[:limit] + "…"


def _build_platform_mention_table(metrics: dict[str, Any]) -> list[str]:
    rows = [
        "| 平台 | 提及次数 | 提及率 | 成功回答 |",
        "| --- | ---: | ---: | ---: |",
    ]
    platform_breakdown = metrics.get("platform_breakdown", {}) or {}
    for platform in PLATFORMS:
        stats = (
            platform_breakdown.get(platform, {})
            if isinstance(platform_breakdown, dict)
            else {}
        )
        total = int(stats.get("total", 0) or 0)
        mentions = int(stats.get("mentions", 0) or 0)
        success = int(stats.get("success", 0) or 0)
        mention_rate = _safe_ratio((mentions / total) if total > 0 else 0)
        rows.append(
            f"| {_display_platform_name(platform)} | {mentions} | {_format_rate(mention_rate)} | {success}/{total if total > 0 else '--'} |"
        )
    return rows


def _build_source_distribution_table(source_overview: dict[str, Any]) -> list[str]:
    rows = [
        "| 来源域名 | 引用次数 | 占比 |",
        "| --- | ---: | ---: |",
    ]
    top_domains = _sort_top_domains(source_overview)
    for item in top_domains[:6]:
        share = _safe_ratio(item.get("share", 0))
        rows.append(
            f"| {item.get('domain')} | {int(item.get('count', 0) or 0)} | {_format_rate(share)} |"
        )
    return rows


def _build_topic_evidence_table(scenario_matrix: list[dict[str, Any]]) -> list[str]:
    rows = [
        "| 主题 | 当前状态 | 出现平台 | 证据 |",
        "| --- | --- | --- | --- |",
    ]
    status_map = {
        "advantage": "主胜",
        "defend": "占位",
        "contested": "争夺",
        "missing": "缺席",
    }
    for item in scenario_matrix[:6]:
        label = _clip_text(item.get("scenario_label", ""), 24)
        status = status_map.get(str(item.get("battle_status", "")), "待判定")
        platforms = "、".join(item.get("present_platforms", []) or []) or "未进入"
        evidence = _clip_text(item.get("evidence", ""), 34)
        rows.append(f"| {label} | {status} | {platforms} | {evidence} |")
    return rows


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
    fetch_results: list[dict[str, Any]],
    competitors: list[dict[str, Any]],
    summary_metrics: dict[str, Any],
    scenario_matrix: list[dict[str, Any]],
    source_overview: dict[str, Any],
    mention_sentiment_analysis: dict[str, Any],
    competitor_metrics: list[dict[str, Any]],
    executive_summary: str,
    key_findings: list[str],
    analysis_mode: str = "persona",
    baseline_metrics: dict[str, Any] | None = None,
    baseline_report: dict[str, Any] | None = None,
) -> str:
    facts = _build_aeo_report_facts(
        fetch_results=fetch_results,
        brand_profile=brand_profile,
        competitors=competitors,
        summary_metrics=summary_metrics,
        scenario_matrix=scenario_matrix,
        source_overview=source_overview,
        mention_sentiment_analysis=mention_sentiment_analysis,
        metrics=metrics,
    )

    brand_name = str(facts.get("brand_name", "") or "本品牌").strip() or "本品牌"
    competitor_a_name = (
        str(facts.get("competitor_a_name", "") or "竞品A").strip() or "竞品A"
    )
    competitor_b_name = (
        str(facts.get("competitor_b_name", "") or "竞品B").strip() or "竞品B"
    )
    total_questions = int(facts.get("total_questions", 0) or 0)
    metric_rows = [row for row in facts.get("metric_rows", []) if isinstance(row, dict)]
    platform_rows = [
        row for row in facts.get("platform_rows", []) if isinstance(row, dict)
    ]
    missing_examples = [
        row for row in facts.get("missing_examples", []) if isinstance(row, dict)
    ]
    contested_examples = [
        row for row in facts.get("contested_examples", []) if isinstance(row, dict)
    ]
    source_rows = [row for row in facts.get("source_rows", []) if isinstance(row, dict)]
    remaining_source_count = int(facts.get("remaining_source_count", 0) or 0)

    brand_metric_lookup = {
        str(item.get("metric_name", "")): item
        for item in metric_rows
        if item.get("metric_name")
    }
    mention_rate = str(
        brand_metric_lookup.get("提及率", {}).get("brand_value", "暂无足够数据")
    )
    official_ratio = str(
        brand_metric_lookup.get("官网引用占比", {}).get("brand_value", "暂无足够数据")
    )
    brand_content_ratio = str(
        brand_metric_lookup.get("品牌内容引用占比", {}).get(
            "brand_value", "暂无足够数据"
        )
    )

    negative_items = _pick_negative_items(mention_sentiment_analysis)
    negative_labels = _build_negative_labels(negative_items)
    threat_competitors = _build_competitor_threats(
        competitor_metrics,
        _safe_ratio(
            summary_metrics.get("brand_mention_rate", metrics.get("mention_rate", 0))
        ),
    )

    default_summary = (
        f"本轮共监测 {total_questions or '若干'} 个核心问题。{brand_name} 当前提及率为 {mention_rate}，"
        f"官网引用占比 {official_ratio}，品牌内容引用占比 {brand_content_ratio}。"
        f"最大压力集中在品牌待补场景与竞品同框场景，说明品牌虽然已经被部分平台识别，"
        f"但尚未形成稳定、可复用的高置信信源与对比语料，业务上会直接影响高意图问题下的优先推荐。"
    )
    summary_text = _build_guarded_summary_text(
        executive_summary=executive_summary,
        default_summary=default_summary,
        metrics=metrics,
    )
    reliability_notice = _build_reliability_notice(metrics)

    lines: list[str] = [
        "## 一、核心执行摘要",
        summary_text,
        "",
    ]

    if reliability_notice:
        lines.extend(["### 数据可靠性说明", f"- {reliability_notice}", ""])

    if key_findings:
        lines.append("### 关键发现")
        for finding in key_findings[:3]:
            text = " ".join(str(finding or "").split()).strip()
            if text:
                lines.append(f"- {text}")
        lines.append("")

    lines.extend(
        [
            "## 二、核心数据对比看板",
            "| 指标名称 | 指标定义 | "
            f"{brand_name} 数据 | {competitor_a_name} 数据 | {competitor_b_name} 数据 | 诊断结论 |",
            "| --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for row in metric_rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("metric_name", "") or "--"),
                    str(row.get("definition", "") or "--"),
                    str(row.get("brand_value", "") or "--"),
                    str(row.get("competitor_a_value", "") or "--"),
                    str(row.get("competitor_b_value", "") or "--"),
                    str(row.get("diagnosis", "") or "--"),
                ]
            )
            + " |"
        )

    baseline_comparison_lines = _build_baseline_comparison_lines(
        analysis_mode=analysis_mode,
        summary_metrics=summary_metrics,
        baseline_metrics=baseline_metrics,
        baseline_report=baseline_report,
    )
    if baseline_comparison_lines:
        lines.extend(["", *baseline_comparison_lines])

    lines.extend(
        [
            "",
            "### 证据来源分布（Top 15）",
            "| 网站名 | 域名 | 引用次数 | 占比 |",
            "| --- | --- | ---: | ---: |",
        ]
    )
    for row in source_rows[:15]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("site_name", "") or "未知来源"),
                    str(row.get("domain", "") or "--"),
                    str(row.get("count", "") or "--"),
                    str(row.get("share", "") or "--"),
                ]
            )
            + " |"
        )
    if remaining_source_count > 0:
        lines.append("")
        lines.append(f"- 其余长尾来源合计 {remaining_source_count} 次引用。")

    lines.extend(
        [
            "",
            "## 三、跨大模型平台表现拆解",
            "| 平台名称 | 平台抓取偏好 | 本品牌在该平台现状 | 存在问题与突破口 |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in platform_rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("platform", "") or "--"),
                    str(row.get("preference", "") or "--"),
                    str(row.get("status", "") or "--"),
                    str(row.get("problem", "") or "--"),
                ]
            )
            + " |"
        )

    lines.extend(["", "## 四、主题场景诊断：机会与竞争图谱", "### 品牌待补场景"])
    if missing_examples:
        for index, item in enumerate(missing_examples[:3], start=1):
            examples = [
                str(text).strip()
                for text in (item.get("query_examples", []) or [])
                if isinstance(text, str) and text.strip()
            ]
            question = (
                examples[0]
                if examples
                else str(item.get("scenario_label", "") or "").strip()
                or f"待补场景 {index}"
            )
            evidence = str(item.get("evidence", "") or "").strip()
            action_hint = str(item.get("action_hint", "") or "").strip()
            lines.extend(
                [
                    f"#### 典型问题 {index}",
                    f"- 问题：{question}",
                    f"- 数据依据：{evidence or 'AI 已回答该类问题，但品牌未进入最终答案。'}",
                    (
                        "- 业务影响：在这类场景里，用户已经带着明确需求来提问，"
                        "品牌如果迟迟未进入答案，流量与心智会直接被竞品或替代方案截走。"
                    ),
                ]
            )
            if action_hint:
                lines.append(f"- 需要补齐的语料方向：{action_hint}")
    else:
        lines.append(
            "- 本轮未发现典型的待补场景，但仍建议扩大问题样本，继续排查长尾场景。"
        )

    lines.extend(["", "### 竞争胶着场景"])
    if contested_examples:
        for index, item in enumerate(contested_examples[:3], start=1):
            examples = [
                str(text).strip()
                for text in (item.get("query_examples", []) or [])
                if isinstance(text, str) and text.strip()
            ]
            question = (
                examples[0]
                if examples
                else str(item.get("scenario_label", "") or "").strip()
                or f"竞争场景 {index}"
            )
            competitors_present = [
                str(name).strip()
                for name in (item.get("competitors_present", []) or [])
                if isinstance(name, str) and name.strip()
            ]
            evidence = str(item.get("evidence", "") or "").strip()
            action_hint = str(item.get("action_hint", "") or "").strip()
            lines.extend(
                [
                    f"#### 典型问题 {index}",
                    f"- 问题：{question}",
                    f"- 同框竞品：{'、'.join(competitors_present) if competitors_present else '已观察到竞品同框，但当前样本未明确命名。'}",
                    f"- 数据依据：{evidence or '品牌进入了答案，但未形成稳定主胜。'}",
                    (
                        "- 诊断：这类问题通常已经进入横向比较阶段，大模型会优先采用证据更完整、"
                        "历史语料更丰富的一方。品牌若想改变排序，必须补齐对比型、场景型与权威背书型语料。"
                    ),
                ]
            )
            if action_hint:
                lines.append(f"- 当前更缺的内容类型：{action_hint}")
    else:
        lines.append(
            "- 本轮未观察到典型的竞品胶着场景，但仍建议保留对比类问题的持续监测。"
        )

    negative_label_text = (
        "；".join(negative_labels[:3]) if negative_labels else "当前没有明显负向标签"
    )
    threat_text = (
        "、".join(
            f"{item.get('name')}（提及率 {_format_rate(item.get('mention_rate', 0))}）"
            for item in threat_competitors[:3]
        )
        if threat_competitors
        else "当前未出现对本品牌形成稳定压制的头部竞品"
    )
    official_signal = f"{brand_name} 当前官网引用占比为 {official_ratio}，说明官方信源对 AI 答案的支撑仍有限。"

    lines.extend(
        [
            "",
            "## 五、AEO 常态化运营与优化策略",
            "### 1. 基建优化（夯实第一信源）",
            f"- {official_signal}",
            "- 优先改造官网中最容易进入 AI 抓取链的页面：FAQ、参数页、对比页、产品详情页、品牌说明页。",
            "- 页面结构上要强化可解析性：明确标题层级、参数表、问答块和品牌主体信息，降低 AI 解析成本。",
            "",
            "### 2. 语料防御与对冲（处理负向与胶着）",
            f"- 当前负向线索：{negative_label_text}。",
            f"- 当前高压竞品：{threat_text}。",
            "- 要把品牌自己的权威说法、医生或专家背书、场景化证据和对比论点，持续铺到更高权重的内容阵地里，用更稳定的 EEAT 信号去对冲竞品和负向语料。",
            "",
            "### 3. 填补盲区漏洞（拓展增量流量）",
            "- 针对待补场景，定向产出首发内容，让品牌先进入答案，再争取主胜排序。",
            "- 内容选题要直接对应问题表达，而不是泛泛做品牌宣传；重点补齐用户高意图问题和场景化推荐问题。",
            "",
            "### 4. 按月度 / 双周回测监测",
            "- 持续回测四个核心指标：提及率、官网引用占比、品牌内容引用占比、负向情感占比。",
            "- 同时追踪各平台表现、待补场景与竞争胶着场景的变化，验证新增语料是否真的进入了答案与引用链。",
        ]
    )

    return "\n".join(line for line in lines if line is not None).strip()


def ensure_report_markdown(
    report_data: dict[str, Any],
    *,
    brand_profile: dict[str, Any],
    metrics: dict[str, Any],
    fetch_results: list[dict[str, Any]],
    competitors: list[dict[str, Any]],
    summary_metrics: dict[str, Any],
    scenario_matrix: list[dict[str, Any]],
    source_overview: dict[str, Any],
    mention_sentiment_analysis: dict[str, Any],
    competitor_metrics: list[dict[str, Any]],
    analysis_mode: str = "persona",
    baseline_metrics: dict[str, Any] | None = None,
    baseline_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report_data["aeo_report_facts"] = _build_aeo_report_facts(
        fetch_results=fetch_results,
        brand_profile=brand_profile,
        competitors=competitors,
        summary_metrics=summary_metrics,
        scenario_matrix=scenario_matrix,
        source_overview=source_overview,
        mention_sentiment_analysis=mention_sentiment_analysis,
        metrics=metrics,
    )
    markdown = str(report_data.get("report_markdown", "") or "").strip()
    required_headers = [
        "## 一、核心执行摘要",
        "## 二、核心数据对比看板",
        "## 三、跨大模型平台表现拆解",
        "## 四、主题场景诊断：机会与竞争图谱",
        "## 五、AEO 常态化运营与优化策略",
    ]
    default_summary = (
        f"本轮品牌提及率 {float(summary_metrics.get('brand_mention_rate', 0) or 0):.1%}，"
        f"内容引用率 {float(summary_metrics.get('content_citation_rate', 0) or 0):.1%}，"
        f"场景覆盖 {int(summary_metrics.get('scenario_hit_count', 0) or 0)}/"
        f"{int(summary_metrics.get('scenario_total', 0) or 0)}。"
    )
    report_data["executive_summary"] = _build_guarded_summary_text(
        executive_summary=str(report_data.get("executive_summary", "") or ""),
        default_summary=default_summary,
        metrics=metrics,
    )
    if (
        len(markdown) < 120
        or any(header not in markdown for header in required_headers)
        or _contains_reasoning_leak(markdown)
    ):
        report_data["report_markdown"] = build_report_markdown(
            brand_profile=brand_profile,
            metrics=metrics,
            fetch_results=fetch_results,
            competitors=competitors,
            summary_metrics=summary_metrics,
            scenario_matrix=scenario_matrix,
            source_overview=source_overview,
            mention_sentiment_analysis=mention_sentiment_analysis,
            competitor_metrics=competitor_metrics,
            executive_summary=str(
                report_data.get("executive_summary", "") or ""
            ).strip(),
            key_findings=[
                str(item or "").strip()
                for item in report_data.get("key_findings", []) or []
                if str(item or "").strip()
            ],
            analysis_mode=analysis_mode,
            baseline_metrics=baseline_metrics,
            baseline_report=baseline_report,
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
        platform_key = str(
            platform_analysis_item.get("platform")
            or platform_analysis_item.get("name")
            or ""
        )

        if (
            "performance_summary" in platform_analysis_item
            and "summary" not in platform_analysis_item
        ):
            platform_analysis_item["summary"] = platform_analysis_item[
                "performance_summary"
            ]
        if (
            "mention_count" in platform_analysis_item
            and "mentions" not in platform_analysis_item
        ):
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
                (
                    "success"
                    if platform_breakdown_item.get("success", 0) > 0
                    else "failed"
                ),
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
            row.setdefault(
                "sentiment", round(max(0, min(100, (raw_sentiment + 1) * 50)), 1)
            )

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

            mention_score = min(
                100.0,
                row.get("mention_rate", 0) * BWVSConstants.MENTION_RATE_MULTIPLIER,
            )
            sentiment_score = row.get(
                "sentiment", BWVSConstants.DEFAULT_SENTIMENT_SCORE
            )
            coverage_score = row.get("coverage", 0) * 100
            bwvs = (
                a5_metrics.BWVS_WEIGHTS["mention"] * mention_score
                + a5_metrics.BWVS_WEIGHTS["sentiment"] * sentiment_score
                + a5_metrics.BWVS_WEIGHTS["coverage"] * coverage_score
                + a5_metrics.BWVS_WEIGHTS["citation"]
                * BWVSConstants.DEFAULT_CITATION_SCORE
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
    fetch_results: list[dict[str, Any]] | None = None,
    competitors: list[dict[str, Any]] | None = None,
    summary_metrics: dict[str, Any] | None = None,
    scenario_matrix: list[dict[str, Any]] | None = None,
    source_overview: dict[str, Any] | None = None,
    mention_sentiment_analysis: dict[str, Any] | None = None,
    competitor_metrics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate degraded but UI-compatible report data when the LLM fails."""
    brand_name = brand_profile.get("brand_name", "品牌")
    mention_rate = _safe_ratio(metrics.get("mention_rate", 0))

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
        "strengths": (
            [f"品牌在 AI 平台中有基础曝光 (提及率 {mention_rate:.1%})"]
            if mention_rate > 0.1
            else []
        ),
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
        fetch_results=fetch_results or [],
        competitors=competitors or [],
        summary_metrics=summary_metrics or {},
        scenario_matrix=scenario_matrix or [],
        source_overview=source_overview or {},
        mention_sentiment_analysis=mention_sentiment_analysis or {},
        competitor_metrics=competitor_metrics or [],
    )
