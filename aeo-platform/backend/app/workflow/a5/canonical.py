"""Canonical GEO analysis pipeline for A5."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import math
import re
from typing import Any, Iterable, Literal

from pydantic import BaseModel, Field

from app.core.domain_normalization import (
    domain_matches as resolve_domain_match,
    normalize_domain as normalize_identity_domain,
)
from app.workflow.a5.metrics import analyze_sentiment
from app.workflow.a5.diagnosis import (
    build_action_recommendations,
    build_data_audit,
    build_report_route,
    build_risk_concern_analysis,
    build_scenario_diagnostics,
    build_source_intelligence,
    build_structured_report,
    extract_geo_report_diagnosis,
    repair_report_artifact,
    validate_report_artifact,
)
from app.workflow.brand_mentions import extract_brand_aliases
from app.workflow.nodes_a4 import PLATFORMS


CANONICAL_PLATFORM_ALIASES = {
    "hunyuan": "yuanbao",
    "yuanbao": "yuanbao",
    "doubao": "doubao",
    "deepseek": "deepseek",
    "kimi": "kimi",
}

CANONICAL_REPORT_KIND_ALIASES = {
    "baseline": "panorama",
    "persona": "scenario",
    "panorama": "panorama",
    "scenario": "scenario",
}

INTENT_ALIASES = {
    "what_is_it": "what_is_it",
    "是什么": "what_is_it",
    "了解": "what_is_it",
    "which_is_better": "which_is_better",
    "哪个好": "which_is_better",
    "对比": "which_is_better",
    "比较": "which_is_better",
    "how_to_choose": "how_to_choose",
    "怎么选": "how_to_choose",
    "如何选": "how_to_choose",
    "选购": "how_to_choose",
    "how_to_use": "how_to_use",
    "怎么用": "how_to_use",
    "risk_or_problem": "risk_or_problem",
    "风险问题": "risk_or_problem",
    "风险": "risk_or_problem",
    "price_or_cost": "price_or_cost",
    "价格成本": "price_or_cost",
    "价格": "price_or_cost",
    "成本": "price_or_cost",
    "alternative_or_replace": "alternative_or_replace",
    "替代替换": "alternative_or_replace",
    "替代": "alternative_or_replace",
    "case_or_example": "case_or_example",
    "案例示例": "case_or_example",
    "案例": "case_or_example",
    "vendor_recommendation": "vendor_recommendation",
    "厂商推荐": "vendor_recommendation",
    "推荐": "vendor_recommendation",
    "awareness": "what_is_it",
    "interest": "how_to_choose",
    "comparison": "which_is_better",
    "decision": "vendor_recommendation",
    "action": "how_to_use",
}

INTENT_DISPLAY = {
    "what_is_it": "产品了解",
    "which_is_better": "选项对比",
    "how_to_choose": "怎么选",
    "how_to_use": "如何使用",
    "risk_or_problem": "风险和顾虑",
    "price_or_cost": "价格与成本",
    "alternative_or_replace": "替代分析",
    "case_or_example": "案例示例",
    "vendor_recommendation": "直接问推荐",
    "other": "其他",
}

DECISION_STAGE_ALIASES = {
    "awareness": "awareness",
    "认知": "awareness",
    "understanding": "understanding",
    "理解": "understanding",
    "兴趣": "understanding",
    "evaluation": "evaluation",
    "评估": "evaluation",
    "决策": "evaluation",
    "purchase": "purchase",
    "购买": "purchase",
    "implementation": "implementation",
    "实施": "implementation",
    "operation": "operation",
    "运营": "operation",
    "interest": "understanding",
    "decision": "evaluation",
    "action": "implementation",
}

DECISION_STAGE_DISPLAY = {
    "awareness": "认知",
    "understanding": "理解",
    "evaluation": "评估",
    "purchase": "购买",
    "implementation": "实施",
    "operation": "运营",
    "other": "其他",
}

SOURCE_TYPE_ORDER = [
    "official",
    "authority_media",
    "vertical_media",
    "community",
    "video_or_content",
    "other",
]

SOURCE_TYPE_DISPLAY = {
    "official": "官网 / 官方文档 / 白皮书",
    "authority_media": "官媒 / 权威机构",
    "vertical_media": "行业媒体",
    "community": "社区 / 论坛 / 问答",
    "video_or_content": "视频 / 内容平台",
    "other": "其他",
}
UNKNOWN_URL_INTELLIGENCE_VALUES = {
    "缺乏特征，无法识别",
    "缺乏特征，无法识别。",
}

NEGATIVE_TOPIC_RULES = {
    "price": (
        "太贵",
        "偏贵",
        "价格高",
        "成本高",
        "预算高",
        "门槛高",
        "不划算",
        "溢价",
        "费用高",
        "price",
    ),
    "deployment": (
        "部署复杂",
        "实施复杂",
        "改造复杂",
        "维护复杂",
        "结构复杂",
        "周期长",
        "门槛高",
        "改造难",
        "部署难",
        "deployment",
    ),
    "service": (
        "服务差",
        "售后差",
        "响应慢",
        "排队",
        "不方便",
        "麻烦",
        "补能焦虑",
        "等待时间长",
        "服务区排队",
        "service",
    ),
    "ecosystem": (
        "生态封闭",
        "生态绑定",
        "兼容差",
        "适配差",
        "接入难",
        "绑定生态",
        "ecosystem",
    ),
    "case": (
        "案例少",
        "样本少",
        "验证不足",
        "缺少案例",
        "经验不足",
        "参考案例有限",
        "case",
    ),
    "usability": (
        "学习成本高",
        "操作复杂",
        "上手难",
        "不易上手",
        "不友好",
        "usability",
    ),
    "credibility": (
        "证据不足",
        "口径不一",
        "存在争议",
        "不确定",
        "真实性存疑",
        "credibility",
    ),
    "other": (),
}

NEGATIVE_TOPIC_DISPLAY = {
    "price": "价格与成本",
    "deployment": "维护与使用复杂度",
    "service": "服务与便利性",
    "ecosystem": "兼容与生态",
    "case": "案例与验证",
    "usability": "使用门槛",
    "credibility": "信息可信度",
    "other": "其他",
}

POSITIVE_REASON_RULES = {
    "technical_capability": ("技术", "能力", "架构", "性能", "一体化", "technical"),
    "industry_position": ("行业", "头部", "主流", "领先", "地位"),
    "case_proof": ("案例", "客户", "落地", "实践", "验证"),
    "cost_effectiveness": ("性价比", "划算", "成本友好", "价格合适"),
    "ease_of_use": ("易用", "上手", "操作简单", "便捷"),
    "service_capability": ("服务", "支持", "实施团队", "售后"),
    "ecosystem_capability": ("生态", "兼容", "连接", "集成"),
    "reputation": ("口碑", "知名", "认可", "评价"),
    "product_strength": ("产品力", "功能完整", "能力全面", "方案成熟"),
}

POSITIVE_REASON_DISPLAY = {
    "technical_capability": "技术能力",
    "industry_position": "行业地位",
    "case_proof": "案例背书",
    "cost_effectiveness": "性价比",
    "ease_of_use": "使用便利性",
    "service_capability": "服务支撑",
    "ecosystem_capability": "生态兼容",
    "reputation": "口碑声誉",
    "product_strength": "产品综合表现",
}

REPORT_LABEL_ALIASES = {
    "品牌直接问题": "直接问品牌的问题",
    "画像痛点场景": "具体使用场景问题",
    "品类选购对比": "选项对比问题",
    "行业趋势认知": "趋势判断问题",
    "品类需求咨询": "直接问怎么选的问题",
    "品类对比排名": "横向比较类问题",
    "场景化选购": "具体场景问题",
    "行业趋势探索": "趋势判断类问题",
}

LOGIC_ARCHETYPE_DISPLAY = {
    "principle_first": "原理先行型",
    "list_recommendation": "榜单罗列型",
    "comparison_review": "把几个选项放在一起比较",
    "risk_warning": "风险提醒型",
    "scenario_solution": "场景求解型",
    "ecosystem_oriented": "生态导向型",
}

RECOMMENDATION_PATTERN_DISPLAY = {
    "explain_then_example": "先解释，再举例",
    "compare_then_recommend": "先横向比较，再给建议",
    "scenario_then_solution": "先界定场景，再给方案",
    "list_then_brief_reason": "先列清单，再给短理由",
    "risk_then_fit": "先提示风险，再给适配建议",
    "ecosystem_aggregation": "先整合生态，再给推荐",
}

STATE_DISPLAY = {
    "no_brand": "不提任何品牌",
    "competitor_only": "只提竞品",
    "monitor_only": "只提品牌",
    "monitor_plus_others": "品牌和竞品一起出现",
}

STATE_IMPLICATION = {
    "no_brand": "该类问题更偏知识型，品牌进入门槛高。",
    "competitor_only": "品牌机会被竞品拿走。",
    "monitor_only": "品牌具备明确心智优势。",
    "monitor_plus_others": "品牌已入围，但竞争激烈。",
}

PLATFORM_DISPLAY = {
    "kimi": "Kimi",
    "doubao": "豆包",
    "deepseek": "DeepSeek",
    "yuanbao": "元宝",
}


def normalize_platform(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return CANONICAL_PLATFORM_ALIASES.get(normalized, normalized)


def normalize_report_kind(value: Any) -> Literal["panorama", "scenario"]:
    normalized = str(value or "").strip().lower()
    return CANONICAL_REPORT_KIND_ALIASES.get(normalized, "scenario")  # type: ignore[return-value]


def safe_ratio(numerator: int | float, denominator: int | float) -> float | None:
    if not denominator:
        return None
    try:
        result = float(numerator) / float(denominator)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return round(result, 4)


def _normalize_text_list(values: list[Any] | None) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
    return output


def _normalize_enum(value: Any, aliases: dict[str, str], default: str = "other") -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return default
    return aliases.get(normalized, default)


def _normalize_domain(url: str | None) -> str | None:
    return normalize_identity_domain(url)


def _expand_official_domains(
    primary_domain: str | None,
    *,
    brand_name: str | None = None,
    aliases: list[str] | None = None,
) -> list[str]:
    normalized = _normalize_domain(primary_domain)
    return [normalized] if normalized else []


def _domain_matches(domain: str | None, official_domains: list[str]) -> bool:
    return resolve_domain_match(domain, official_domains)


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords if keyword)


def _dedupe_dict_rows(
    rows: list[dict[str, Any]], key_fields: tuple[str, ...]
) -> list[dict[str, Any]]:
    seen: set[tuple[str, ...]] = set()
    output: list[dict[str, Any]] = []
    for row in rows:
        key = tuple(str(row.get(field) or "").strip().lower() for field in key_fields)
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def _format_ratio(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def _count_clause(count: int | float | None, text: str) -> str:
    if not isinstance(count, (int, float)) or count <= 0:
        return ""
    return f"{int(count)} 个{text}"


def _join_nonempty_clauses(
    clauses: list[str], prefix: str = "", separator: str = "，"
) -> str:
    parts = [item for item in clauses if item]
    if not parts:
        return ""
    return prefix + separator.join(parts)


def _format_delta_pp(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:+.1f}pp"


def _source_type_label(source_type: str) -> str:
    text = str(source_type or "").strip()
    return SOURCE_TYPE_DISPLAY.get(text, text or SOURCE_TYPE_DISPLAY["other"])


def _is_meaningful_site_category(value: str | None) -> bool:
    text = str(value or "").strip()
    return bool(text and text not in UNKNOWN_URL_INTELLIGENCE_VALUES)


def _ordered_source_types(source_types: Iterable[str]) -> list[str]:
    normalized = [
        str(item or "").strip() for item in source_types if str(item or "").strip()
    ]
    seen = set(normalized)
    known = set(SOURCE_TYPE_ORDER)
    ordered = [item for item in SOURCE_TYPE_ORDER if item in seen]
    ordered.extend(sorted(item for item in seen if item not in known))
    return ordered


def _negative_topic_label(topic: str) -> str:
    return NEGATIVE_TOPIC_DISPLAY.get(topic, NEGATIVE_TOPIC_DISPLAY["other"])


def _positive_reason_label(reason: str) -> str:
    return POSITIVE_REASON_DISPLAY.get(reason, reason)


def _report_label(value: str) -> str:
    text = str(value or "").strip()
    return REPORT_LABEL_ALIASES.get(text, text)


def _intent_label(intent: str | None) -> str:
    return INTENT_DISPLAY.get(intent or "other", intent or "其他")


def _stage_label(stage: str | None) -> str:
    return DECISION_STAGE_DISPLAY.get(stage or "other", stage or "其他")


def _state_label(state: str) -> str:
    return STATE_DISPLAY.get(state, state)


def _state_implication(state: str) -> str:
    return STATE_IMPLICATION.get(state, "需结合原始样本继续复核。")


def _platform_label(platform: str) -> str:
    return PLATFORM_DISPLAY.get(platform, platform)


def _escape_cell(value: Any) -> str:
    return str(value if value is not None else "N/A").replace("|", "\\|")


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_escape_cell(item) for item in row) + " |")
    return "\n".join(lines)


def _markdown_bullets(items: list[str]) -> str:
    if not items:
        return "- N/A"
    return "\n".join(f"- {item}" for item in items)


def _markdown_hint(text: str) -> str:
    return f"> {text}"


def _markdown_quote_block(text: str) -> str:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return "> N/A"
    return "\n".join(f"> {line}" for line in lines)


def _extract_sentences(text: str) -> list[str]:
    chunks = re.split(r"[。！？；;\n]", text)
    return [chunk.strip() for chunk in chunks if chunk and chunk.strip()]


def _clean_report_text(text: str, max_length: int = 60) -> str:
    cleaned = str(text or "")
    cleaned = re.sub(r"\[[^\]]+\]\(@ref\)", "", cleaned)
    cleaned = cleaned.replace("<br>", " ")
    cleaned = cleaned.replace("|", " ")
    cleaned = re.sub(r"[*_`#>-]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ：:;；-")
    if len(cleaned) > max_length:
        return cleaned[:max_length].rstrip() + "…"
    return cleaned


def _format_metric_emphasis(label: str, value: str) -> str:
    return f"{label} **{value}**"


def _brand_rank_sentence(brand_name: str, rank: int | None) -> str:
    if not rank:
        return "当前样本里还没有形成稳定的品牌排名。"
    if rank == 1:
        return f"在被提及的品牌里，{brand_name}目前排在第一位。"
    return f"在被提及的品牌里，{brand_name}目前排在第 {rank} 位。"


def _format_count_ratio(count: int, total: int) -> str:
    return f"{count}/{total}" if total > 0 else "0/0"


def _unique_preserve(items: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = str(item or "").strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(normalized)
    return output


def _sample_question_titles(
    rows: list[dict[str, Any]], limit: int = 3, *, max_length: int = 30
) -> list[str]:
    samples: list[str] = []
    for row in rows[:limit]:
        text = _clean_report_text(
            str(row.get("question_text") or ""), max_length=max_length
        )
        if not text:
            continue
        samples.append(f"「{text}」")
    return _unique_preserve(samples)


def _sample_question_quotes(
    rows: list[dict[str, Any]],
    limit: int = 2,
    *,
    max_length: int = 42,
) -> list[str]:
    quotes: list[str] = []
    seen: set[str] = set()
    for row in rows:
        text = _clean_report_text(
            str(row.get("question_text") or ""), max_length=max_length
        )
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        quotes.append(_markdown_quote_block(text))
        if len(quotes) >= limit:
            break
    return quotes


def _state_question_quotes(
    rows: list[dict[str, Any]],
    *,
    states: set[str],
    limit: int = 2,
    max_length: int = 42,
) -> list[str]:
    filtered = [row for row in rows if str(row.get("answer_state") or "") in states]
    return _sample_question_quotes(filtered, limit=limit, max_length=max_length)


def _sample_platform_labels(platforms: list[str]) -> str:
    labels = _unique_preserve([_platform_label(platform) for platform in platforms])
    return "、".join(labels) if labels else "N/A"


def _question_state_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counter = {
        "no_brand": 0,
        "competitor_only": 0,
        "monitor_only": 0,
        "monitor_plus_others": 0,
    }
    for row in rows:
        state = str(row.get("answer_state") or "")
        if state in counter:
            counter[state] += 1
    return counter


def _category_question_summary(
    question_rows: list[dict[str, Any]],
    *,
    field: str,
    value: str,
) -> dict[str, Any]:
    rows = [row for row in question_rows if str(row.get(field) or "") == value]
    counts = _question_state_counts(rows)
    return {
        "label": value,
        "question_count": len(rows),
        "entered_count": sum(1 for row in rows if bool(row.get("brand_present"))),
        "exclusive_count": counts["monitor_only"],
        "mixed_count": counts["monitor_plus_others"],
        "competitor_only_count": counts["competitor_only"],
        "no_brand_count": counts["no_brand"],
        "questions": rows,
        "samples": _sample_question_titles(rows),
    }


def _state_question_samples(
    rows: list[dict[str, Any]],
    *,
    states: set[str],
    limit: int = 2,
) -> list[str]:
    picked = [
        _clean_report_text(str(row.get("question_text") or ""), max_length=34)
        for row in rows
        if str(row.get("answer_state") or "") in states
    ]
    output: list[str] = []
    seen: set[str] = set()
    for item in picked:
        if not item or item in seen:
            continue
        seen.add(item)
        output.append(item)
        if len(output) >= limit:
            break
    return output


def _meaningful_band_summaries(
    question_rows: list[dict[str, Any]],
    *,
    field: str,
    labels: list[str],
    min_questions: int = 2,
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for label in labels:
        summary = _category_question_summary(question_rows, field=field, value=label)
        if summary["question_count"] < min_questions:
            continue
        summaries.append(summary)
    return summaries


def _strip_false_negative_topics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if str(row.get("topic") or "") != "other"]


def _format_delta_points_cn(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{abs(value) * 100:.1f} 个百分点"


def _top_scene_coverage_text(rows: list[dict[str, Any]], limit: int = 3) -> str:
    picked = [
        f"{_report_label(str(row['label']))}（{row['count']} 个问题）"
        for row in rows[:limit]
        if row.get("count")
    ]
    return "、".join(picked) or "暂无明显集中"


def _derive_negative_issue_label(question_text: str, conclusion_text: str) -> str:
    combined = f"{question_text} {conclusion_text}".lower()
    if any(
        token in combined
        for token in ("预算", "价格", "成本", "贵不贵", "值不值", "划算")
    ):
        return "价格和成本顾虑"
    if any(
        token in combined
        for token in ("服务", "响应", "排队", "等待", "支持", "不方便")
    ):
        return "服务与便利性顾虑"
    if any(token in combined for token in ("兼容", "接入", "适配", "生态", "集成")):
        return "兼容与适配顾虑"
    if any(
        token in combined for token in ("部署", "维护", "上手", "实施", "使用", "复杂")
    ):
        return "使用和实施顾虑"
    return _clean_report_text(question_text, max_length=22)


def _fallback_negative_issue_rows(bundle: InputBundle) -> list[dict[str, Any]]:
    monitor_brand_answers = sum(
        1
        for answer in bundle.answers
        if answer.status == "ok" and answer.mentioned_monitor_brand
    )
    counter: Counter[str] = Counter()
    examples: dict[str, dict[str, Any]] = {}
    for answer in bundle.answers:
        if answer.status != "ok" or not answer.negative_conclusions:
            continue
        conclusion_text = "；".join(
            str(item.get("text") or "").strip()
            for item in answer.negative_conclusions
            if str(item.get("text") or "").strip()
        )
        label = _derive_negative_issue_label(answer.question_text, conclusion_text)
        if not label:
            continue
        counter[label] += 1
        examples.setdefault(
            label,
            {
                "question_text": answer.question_text,
                "platform": answer.platform,
                "conclusion_text": conclusion_text,
            },
        )
    rows: list[dict[str, Any]] = []
    for label, count in counter.most_common(3):
        example = examples.get(label, {})
        rows.append(
            {
                "display": label,
                "rate": safe_ratio(count, monitor_brand_answers),
                "question_text": _clean_report_text(
                    str(example.get("question_text") or ""), max_length=80
                ),
                "platform": _platform_label(str(example.get("platform") or "")),
                "common_conclusion": _clean_report_text(
                    str(example.get("conclusion_text") or ""), max_length=72
                ),
            }
        )
    return rows


def _collect_other_domain_notes(bundle: InputBundle) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    example_by_domain: dict[str, dict[str, Any]] = {}
    for answer in bundle.answers:
        if answer.status != "ok":
            continue
        for citation in answer.citation_records:
            if not citation.brand_related or citation.source_type != "other":
                continue
            domain = str(citation.domain or "").strip().lower()
            if not domain:
                continue
            counter[domain] += 1
            example_by_domain.setdefault(
                domain,
                {
                    "platform": answer.platform,
                    "question_text": answer.question_text,
                    "title": citation.title,
                    "snippet": citation.snippet,
                },
            )
    notes: list[dict[str, Any]] = []
    for domain, count in counter.most_common():
        example = example_by_domain.get(domain, {})
        reason = "站点画像不足，暂保留为其他。"
        display_name = _resolve_site_display_name(
            domain=domain,
            sample_titles=(
                [str(example.get("title") or "")] if example.get("title") else []
            ),
        )
        notes.append(
            {
                "domain": domain,
                "display_name": display_name,
                "count": count,
                "platform": _platform_label(str(example.get("platform") or "")),
                "question_text": _clean_report_text(
                    str(example.get("question_text") or ""), max_length=38
                ),
                "reason": reason,
            }
        )
    return notes


def _resolve_site_display_name(
    *,
    domain: str | None,
    site_name: str | None = None,
    sample_titles: list[str] | None = None,
    taxonomy: Any = None,
) -> str:
    normalized_domain = str(domain or "").strip().lower()
    explicit_name = str(site_name or "").strip()
    if explicit_name and explicit_name.lower() != normalized_domain:
        return explicit_name
    if taxonomy and getattr(taxonomy, "display_name", None):
        return str(getattr(taxonomy, "display_name"))
    return normalized_domain or "N/A"


def _format_site_cell(row: dict[str, Any]) -> str:
    display_name = str(row.get("display_name") or row.get("domain") or "N/A")
    domain = str(row.get("domain") or "").strip()
    if domain and display_name != domain:
        return f"{display_name} ({domain})"
    return display_name


def _normalize_intent_value(raw_value: Any, question_text: str) -> str:
    normalized = str(raw_value or "").strip().lower()
    if normalized in INTENT_ALIASES:
        return INTENT_ALIASES[normalized]
    combined = f"{raw_value or ''} {question_text}".lower()
    heuristic_rules = [
        (("替代", "取代", "淘汰", "过渡方案"), "alternative_or_replace"),
        (("风险", "问题", "焦虑", "担心", "会不会", "能不能"), "risk_or_problem"),
        (("预算", "价格", "成本", "贵不贵"), "price_or_cost"),
        (("案例", "实测", "用户", "口碑"), "case_or_example"),
        (("推荐", "最合适", "买哪", "哪款", "选哪"), "vendor_recommendation"),
        (("怎么选", "如何选", "如何挑", "选择"), "how_to_choose"),
        (
            (
                "对比",
                "比较",
                "哪个好",
                "区别",
                "差异",
                "排名",
                "排行",
                "第一梯队",
                "共性",
            ),
            "which_is_better",
        ),
        (("怎么用", "使用", "步骤", "流程"), "how_to_use"),
        (("是什么", "了解", "原理", "特点"), "what_is_it"),
    ]
    for keywords, intent in heuristic_rules:
        if any(keyword in combined for keyword in keywords):
            return intent
    return "other"


def _normalize_decision_stage_value(raw_value: Any, question_text: str) -> str:
    normalized = str(raw_value or "").strip().lower()
    if normalized in DECISION_STAGE_ALIASES:
        return DECISION_STAGE_ALIASES[normalized]
    combined = f"{raw_value or ''} {question_text}".lower()
    if any(
        keyword in combined for keyword in ("怎么用", "实施", "流程", "配置", "部署")
    ):
        return "implementation"
    if any(
        keyword in combined
        for keyword in ("推荐", "买哪", "选哪", "预算", "值不值", "哪个好", "怎么选")
    ):
        return "evaluation"
    if any(
        keyword in combined
        for keyword in ("是什么", "趋势", "会不会", "为什么", "了解")
    ):
        return "awareness"
    return "understanding"


def _preferred_source_labels(source_preferences: dict[str, Any]) -> list[str]:
    preferred: list[str] = []
    for source_type in _ordered_source_types(source_preferences.keys()):
        strength = str(source_preferences.get(source_type) or "low")
        if strength in {"high", "medium"}:
            preferred.append(_source_type_label(source_type))
    return preferred


def _sort_counter_rows(counter: Counter[str], total: int) -> list[dict[str, Any]]:
    rows = []
    for label, count in sorted(counter.items(), key=lambda item: (-item[1], item[0])):
        rows.append({"label": label, "count": count, "rate": safe_ratio(count, total)})
    return rows


class ReportMeta(BaseModel):
    artifact_kind: Literal["geo_report"] = "geo_report"
    report_kind: Literal["panorama", "scenario"]
    analysis_mode: str
    brand_name: str
    industry: str | None = None
    scenario_theme: str | None = None
    baseline_report_id: str | None = None
    session_id: str
    entity_id: str | None = None
    generated_at: str
    platforms: list[str] = Field(default_factory=list)
    timezone: str = "Asia/Hong_Kong"


class BrandMaster(BaseModel):
    monitor_brand: str
    monitor_brand_aliases: list[str] = Field(default_factory=list)
    competitor_brands: list[str] = Field(default_factory=list)
    brand_alias_dict: dict[str, str] = Field(default_factory=dict)
    official_domains: list[str] = Field(default_factory=list)


class QuestionRecord(BaseModel):
    question_id: str
    question_text: str
    intent: str | None = None
    decision_stage: str | None = None
    persona: str | None = None
    scene: str | None = None
    pain_point: str | None = None
    tags: list[str] = Field(default_factory=list)
    priority: str = "medium"


class CitationFetchRecord(BaseModel):
    citation_id: str
    title: str | None = None
    url: str
    domain: str | None = None
    snippet: str | None = None
    site_name: str | None = None
    source_type: str = "other"
    site_category: str | None = None
    url_intelligence: dict[str, Any] = Field(default_factory=dict)
    information_updated_at: str | None = None
    information_updated_at_source: str | None = None
    ecosystem_tag: Literal[
        "none",
        "wechat",
        "douyin",
        "xiaohongshu",
        "bilibili",
        "toutiao",
        "tencent",
        "byte",
    ] = "none"
    is_platform_ecosystem: bool = False
    is_official: bool = False
    brand_related: bool = False
    official_conversion_flag: bool = False


class AnswerRecord(BaseModel):
    answer_id: str
    question_id: str
    question_text: str
    platform: str
    status: Literal["ok", "missing"]
    answer_text: str | None = None
    answer_time: str | None = None
    citation_records: list[CitationFetchRecord] = Field(default_factory=list)
    mentioned_brands: list[str] = Field(default_factory=list)
    mentioned_monitor_brand: bool = False
    competitor_brands: list[str] = Field(default_factory=list)
    primary_recommended_brand: str | None = None
    answer_state: Literal[
        "no_brand", "competitor_only", "monitor_only", "monitor_plus_others"
    ]
    sentiment: Literal["positive", "neutral", "negative"] = "neutral"
    positive_reasons: list[str] = Field(default_factory=list)
    negative_conclusions: list[dict[str, Any]] = Field(default_factory=list)
    negative_topics: list[str] = Field(default_factory=list)
    comparison_answer_flag: bool = False
    no_citation_strong_recommend_flag: bool = False
    logic_archetype: Literal[
        "principle_first",
        "list_recommendation",
        "comparison_review",
        "risk_warning",
        "scenario_solution",
        "ecosystem_oriented",
    ] = "principle_first"
    recommendation_pattern_code: Literal[
        "explain_then_example",
        "compare_then_recommend",
        "scenario_then_solution",
        "list_then_brief_reason",
        "risk_then_fit",
        "ecosystem_aggregation",
    ] = "explain_then_example"


class DomainTaxonomyRecord(BaseModel):
    domain: str
    source_type: str
    ecosystem_tag: Literal[
        "none",
        "wechat",
        "douyin",
        "xiaohongshu",
        "bilibili",
        "toutiao",
        "tencent",
        "byte",
    ] = "none"
    is_platform_ecosystem: bool = False
    display_name: str | None = None


class InputBundle(BaseModel):
    meta: ReportMeta
    brand_master: BrandMaster
    questions: list[QuestionRecord]
    answers: list[AnswerRecord]
    domain_taxonomy: list[DomainTaxonomyRecord]


class MetricBundle(BaseModel):
    total_questions: int
    total_answers: int
    successful_answers: int
    platform_count: int
    brand_visibility: float | None = None
    competitor_pressure: float | None = None
    no_brand_rate: float | None = None
    monitor_only_rate: float | None = None
    monitor_plus_others_rate: float | None = None
    brand_rank: int | None = None
    ranked_brand_count: int = 0
    brand_presence_count: int = 0
    higher_brands: list[str] = Field(default_factory=list)
    top_brand_ranking: list[dict[str, Any]] = Field(default_factory=list)
    brand_link_penetration: float | None = None
    official_share: float | None = None
    official_conversion_rate: float | None = None
    negative_rate: float | None = None
    sentiment_distribution: dict[str, float | None] = Field(default_factory=dict)
    top_positive_reasons: list[dict[str, Any]] = Field(default_factory=list)
    top_negative_topics: list[dict[str, Any]] = Field(default_factory=list)
    negative_source_distribution: dict[str, float | None] = Field(default_factory=dict)
    source_type_breakdown: dict[str, float | None] = Field(default_factory=dict)
    official_funnel: dict[str, int] = Field(default_factory=dict)
    coverage_by_scene: list[dict[str, Any]] = Field(default_factory=list)
    coverage_by_intent: list[dict[str, Any]] = Field(default_factory=list)
    coverage_by_stage: list[dict[str, Any]] = Field(default_factory=list)
    top_trigger_categories: list[dict[str, Any]] = Field(default_factory=list)
    top_dropout_categories: list[dict[str, Any]] = Field(default_factory=list)
    answer_state_matrix: dict[str, Any] = Field(default_factory=dict)
    platform_profiles: dict[str, Any] = Field(default_factory=dict)
    platform_judgments: dict[str, str | None] = Field(default_factory=dict)
    scenario_total: int = 0
    scenario_hit_count: int = 0
    high_risk_scenario_count: int = 0
    mention_rate: float | None = None
    content_citation_rate: float | None = None
    official_citation_rate: float | None = None
    visibility_summary: dict[str, Any] = Field(default_factory=dict)
    source_summary: dict[str, Any] = Field(default_factory=dict)
    question_diagnostics: dict[str, Any] = Field(default_factory=dict)
    sentiment_risk: dict[str, Any] = Field(default_factory=dict)
    platform_profile: dict[str, Any] = Field(default_factory=dict)


class ComparisonBundle(BaseModel):
    comparable: bool
    baseline_report_id: str | None = None
    reason: str | None = None
    visibility_delta: dict[str, Any] = Field(default_factory=dict)
    citation_delta: dict[str, Any] = Field(default_factory=dict)
    sentiment_delta: dict[str, Any] = Field(default_factory=dict)
    per_platform_delta: dict[str, Any] = Field(default_factory=dict)


def build_domain_taxonomy(official_domains: list[str]) -> list[DomainTaxonomyRecord]:
    return [
        DomainTaxonomyRecord(domain=domain, source_type="official", display_name=domain)
        for domain in official_domains
        if domain
    ]


def _infer_domain_taxonomy(
    domain: str, official_domains: list[str], platform: str
) -> DomainTaxonomyRecord:
    is_official = _domain_matches(domain, official_domains)
    return DomainTaxonomyRecord(
        domain=domain,
        source_type="official" if is_official else "other",
        display_name=domain,
    )


def _match_brand_from_text(text: str, candidate_name: str, aliases: list[str]) -> bool:
    lowered = text.lower()
    if candidate_name and candidate_name.lower() in lowered:
        return True
    return any(alias.lower() in lowered for alias in aliases if alias)


def _detect_mentioned_brands(
    answer_text: str, brand_master: BrandMaster
) -> tuple[list[str], bool, list[str]]:
    mentioned: list[str] = []
    monitor_mentioned = _match_brand_from_text(
        answer_text,
        brand_master.monitor_brand,
        brand_master.monitor_brand_aliases,
    )
    if monitor_mentioned:
        mentioned.append(brand_master.monitor_brand)
    competitors_present: list[str] = []
    for competitor in brand_master.competitor_brands:
        if competitor and competitor.lower() in answer_text.lower():
            competitors_present.append(competitor)
            mentioned.append(competitor)
    return (
        _normalize_text_list(mentioned),
        monitor_mentioned,
        _normalize_text_list(competitors_present),
    )


def _infer_primary_recommended_brand(
    text: str, mentioned_brands: list[str]
) -> str | None:
    if not any(cue in text for cue in ("推荐", "优先", "首选", "更适合", "建议选择")):
        return None
    lowered = text.lower()
    for brand in mentioned_brands:
        if brand and brand.lower() in lowered:
            return brand
    return mentioned_brands[0] if mentioned_brands else None


def _classify_answer_state(
    *,
    mentioned_brands: list[str],
    monitor_mentioned: bool,
) -> Literal["no_brand", "competitor_only", "monitor_only", "monitor_plus_others"]:
    if not mentioned_brands:
        return "no_brand"
    if not monitor_mentioned:
        return "competitor_only"
    if len(mentioned_brands) == 1:
        return "monitor_only"
    return "monitor_plus_others"


def _detect_positive_reasons(text: str, sentiment: str) -> list[str]:
    if sentiment != "positive":
        return []
    return [
        reason
        for reason, keywords in POSITIVE_REASON_RULES.items()
        if _contains_any(text, keywords)
    ][:3]


def _infer_negative_source_attribution(
    sentence: str, citations: list[CitationFetchRecord]
) -> tuple[str, list[str]]:
    citation_urls = []
    sentence_lower = sentence.lower()
    for citation in citations:
        haystack = f"{citation.title or ''} {citation.snippet or ''}".lower()
        if not haystack.strip():
            continue
        if any(
            keyword.lower() in haystack
            for topic in NEGATIVE_TOPIC_RULES.values()
            for keyword in topic
            if keyword and keyword.lower() in sentence_lower
        ):
            citation_urls.append(citation.url)
    if citation_urls and any(
        keyword in sentence_lower
        for keyword in ("认为", "可能", "通常", "往往", "更高")
    ):
        return "mixed", citation_urls
    if citation_urls:
        return "cited_source", citation_urls
    return "model_inference", []


def _detect_negative_conclusions(
    text: str, citations: list[CitationFetchRecord]
) -> tuple[list[dict[str, Any]], list[str]]:
    conclusions: list[dict[str, Any]] = []
    topics: list[str] = []
    seen_conclusions: set[str] = set()
    for sentence in _extract_sentences(text):
        cleaned_sentence = _clean_report_text(sentence, max_length=80)
        if len(cleaned_sentence) < 6:
            continue
        matched_topics = [
            topic
            for topic, keywords in NEGATIVE_TOPIC_RULES.items()
            if keywords and _contains_any(cleaned_sentence, keywords)
        ]
        if not matched_topics:
            continue
        key = cleaned_sentence.lower()
        if key in seen_conclusions:
            continue
        seen_conclusions.add(key)
        attribution, citation_urls = _infer_negative_source_attribution(
            cleaned_sentence, citations
        )
        conclusions.append(
            {
                "text": cleaned_sentence,
                "topics": _normalize_text_list(matched_topics),
                "source_attribution": attribution,
                "supporting_citation_urls": citation_urls,
            }
        )
        topics.extend(matched_topics)
    if not conclusions and any(
        word in text.lower()
        for word in ("太贵", "偏贵", "复杂", "风险", "争议", "不方便")
    ):
        fallback_text = _clean_report_text(text[:80], max_length=80)
        attribution, citation_urls = _infer_negative_source_attribution(
            fallback_text, citations
        )
        conclusions.append(
            {
                "text": fallback_text,
                "topics": ["other"],
                "source_attribution": attribution,
                "supporting_citation_urls": citation_urls,
            }
        )
        topics.append("other")
    return conclusions, _normalize_text_list(topics)


def _infer_logic_archetype(
    question: QuestionRecord, answer_text: str, citations: list[CitationFetchRecord]
) -> str:
    text = answer_text.lower()
    if any(
        token in text for token in ("对比", "相比", "优缺点", "更适合", "横向")
    ) or question.intent in {
        "which_is_better",
        "how_to_choose",
        "alternative_or_replace",
        "vendor_recommendation",
    }:
        return "comparison_review"
    if (
        any(token in text for token in ("风险", "注意", "门槛", "挑战", "限制"))
        or question.intent == "risk_or_problem"
    ):
        return "risk_warning"
    if any(token in text for token in ("场景", "方案", "适合", "落地", "部署")):
        return "scenario_solution"
    if any(citation.is_platform_ecosystem for citation in citations):
        return "ecosystem_oriented"
    if (
        len(re.findall(r"[\\d一二三四五六七八九十]+[\\.、]", answer_text)) >= 2
        or answer_text.count("；") >= 2
    ):
        return "list_recommendation"
    return "principle_first"


def _infer_recommendation_pattern(archetype: str) -> str:
    mapping = {
        "principle_first": "explain_then_example",
        "list_recommendation": "list_then_brief_reason",
        "comparison_review": "compare_then_recommend",
        "risk_warning": "risk_then_fit",
        "scenario_solution": "scenario_then_solution",
        "ecosystem_oriented": "ecosystem_aggregation",
    }
    return mapping.get(archetype, "explain_then_example")


ANSWER_CONTENT_FEATURES: dict[str, tuple[str, tuple[str, ...]]] = {
    "theory": (
        "原理/机制解释",
        ("原理", "机制", "吸收", "作用", "原因", "区别", "通常", "一般", "研究"),
    ),
    "evidence": (
        "证据背书",
        ("研究", "临床", "数据", "证据", "文献", "权威", "专家", "指南", "认证"),
    ),
    "product": (
        "产品/品牌介绍",
        ("产品", "品牌", "成分", "配方", "型号", "规格", "功效", "适合"),
    ),
    "risk_or_compliance": (
        "风险/合规提醒",
        (
            "注意",
            "风险",
            "副作用",
            "禁忌",
            "不建议",
            "遵医嘱",
            "医生",
            "药物",
            "冲突",
            "争议",
        ),
    ),
    "purchase_guidance": (
        "购买/选择建议",
        ("推荐", "选择", "购买", "渠道", "官方", "正规", "预算", "性价比", "优先"),
    ),
}


def _answer_feature_flags(
    answer_text: str, citations: list[CitationFetchRecord]
) -> set[str]:
    text = str(answer_text or "")
    flags: set[str] = set()
    for code, (_label, keywords) in ANSWER_CONTENT_FEATURES.items():
        if _contains_any(text, keywords):
            flags.add(code)
    if citations:
        flags.add("evidence")
    return flags


def _format_feature_mix(feature_mix: dict[str, float | None]) -> str:
    parts: list[str] = []
    for code, (label, _keywords) in ANSWER_CONTENT_FEATURES.items():
        value = feature_mix.get(code)
        if value is None or value <= 0:
            continue
        parts.append(f"{label} {_format_ratio(value)}")
    return "、".join(parts) or "暂未形成稳定行文特征"


def _is_comparison_question(question: QuestionRecord, answer_text: str) -> bool:
    if question.intent in {
        "which_is_better",
        "how_to_choose",
        "alternative_or_replace",
        "vendor_recommendation",
    }:
        return True
    return any(
        token in answer_text for token in ("对比", "比较", "替代", "哪个好", "推荐")
    )


def _preference_strength(share: float | None) -> str:
    if share is None:
        return "low"
    if share >= 0.45:
        return "high"
    if share >= 0.2:
        return "medium"
    return "low"


def _normalize_question_record(
    raw_question: dict[str, Any], fallback_index: int
) -> QuestionRecord:
    question_text = str(
        raw_question.get("question_text")
        or raw_question.get("core_question")
        or raw_question.get("question")
        or f"问题 {fallback_index}"
    ).strip()
    return QuestionRecord(
        question_id=str(raw_question.get("question_id") or f"q_{fallback_index:03d}"),
        question_text=question_text,
        intent=_normalize_intent_value(
            raw_question.get("intent") or raw_question.get("user_intent"),
            question_text,
        ),
        decision_stage=_normalize_decision_stage_value(
            raw_question.get("decision_stage"),
            question_text,
        ),
        persona=str(
            raw_question.get("persona_id") or raw_question.get("source_persona") or ""
        ).strip()
        or None,
        scene=str(
            raw_question.get("linked_scenario") or raw_question.get("category") or ""
        ).strip()
        or "其他",
        pain_point=str(raw_question.get("linked_pain_point") or "").strip() or None,
        tags=_normalize_text_list(
            list(raw_question.get("keywords") or [])
            + list(raw_question.get("seo_keywords") or [])
        ),
        priority=str(
            raw_question.get("scenario_priority")
            or raw_question.get("priority")
            or "medium"
        )
        .strip()
        .lower(),
    )


def build_input_bundle(
    *,
    session_id: str,
    entity_id: str | None,
    analysis_mode: str,
    brand_profile: dict[str, Any],
    competitors: list[dict[str, Any]],
    fetch_results: list[dict[str, Any]],
    simulated_questions: list[dict[str, Any]] | dict[str, Any] | None = None,
    baseline_report_id: str | None = None,
) -> InputBundle:
    report_kind = normalize_report_kind(analysis_mode)
    brand_name = str(brand_profile.get("brand_name") or "品牌").strip() or "品牌"
    aliases = _normalize_text_list(extract_brand_aliases(brand_profile) + [brand_name])
    official_domain = _normalize_domain(
        str(brand_profile.get("official_website") or "")
    )
    official_domains = _expand_official_domains(
        official_domain,
        brand_name=brand_name,
        aliases=aliases,
    )
    competitor_names = _normalize_text_list(
        [
            str(item.get("name") or "").strip()
            for item in competitors
            if isinstance(item, dict)
        ]
    )
    brand_master = BrandMaster(
        monitor_brand=brand_name,
        monitor_brand_aliases=aliases,
        competitor_brands=competitor_names,
        brand_alias_dict={alias.lower(): brand_name for alias in aliases},
        official_domains=official_domains,
    )

    raw_questions: list[dict[str, Any]]
    selected_personas: list[str] = []
    if isinstance(simulated_questions, dict):
        raw_questions = list(
            simulated_questions.get("simulated_questions")
            or simulated_questions.get("questions")
            or []
        )
        selected_personas = _normalize_text_list(
            list(
                simulated_questions.get("selectedPersonas")
                or simulated_questions.get("selected_personas")
                or []
            )
        )
    elif isinstance(simulated_questions, list):
        raw_questions = [item for item in simulated_questions if isinstance(item, dict)]
    else:
        raw_questions = []

    question_map: dict[str, QuestionRecord] = {}
    for index, question in enumerate(raw_questions, start=1):
        record = _normalize_question_record(question, index)
        question_map[record.question_id] = record

    if report_kind == "scenario" and not selected_personas:
        selected_personas = _normalize_text_list(
            [
                str(question.get("source_persona") or "").strip()
                for question in raw_questions
            ]
        )

    taxonomy_map = {
        item.domain: item for item in build_domain_taxonomy(official_domains)
    }
    answers: list[AnswerRecord] = []
    platforms_seen: set[str] = set()
    enforce_question_boundary = report_kind == "scenario" and bool(question_map)

    for question_index, fetch_row in enumerate(fetch_results, start=1):
        question_id = str(fetch_row.get("question_id") or f"q_{question_index:03d}")
        if enforce_question_boundary and question_id not in question_map:
            continue
        if question_id not in question_map:
            question_map[question_id] = _normalize_question_record(
                {
                    "question_id": question_id,
                    "question_text": fetch_row.get("question_text"),
                    "category": fetch_row.get("category"),
                    "linked_scenario": fetch_row.get("linked_scenario"),
                    "linked_pain_point": fetch_row.get("linked_pain_point"),
                    "user_intent": fetch_row.get("intent")
                    or fetch_row.get("user_intent"),
                    "decision_stage": fetch_row.get("decision_stage"),
                },
                question_index,
            )

        question = question_map[question_id]
        platform_results = (
            fetch_row.get("platform_results")
            if isinstance(fetch_row.get("platform_results"), list)
            else []
        )
        for platform_index, platform_result in enumerate(platform_results, start=1):
            if not isinstance(platform_result, dict):
                continue
            platform = normalize_platform(platform_result.get("platform"))
            if platform:
                platforms_seen.add(platform)
            success = bool(platform_result.get("success"))
            answer_payload = (
                platform_result.get("answer")
                if isinstance(platform_result.get("answer"), dict)
                else {}
            )
            answer_text = str(
                answer_payload.get("content")
                or platform_result.get("answer_text")
                or ""
            ).strip()
            citations_raw = (
                platform_result.get("citations")
                or answer_payload.get("search_references")
                or []
            )

            citation_records: list[CitationFetchRecord] = []
            seen_urls: set[str] = set()
            for citation_index, citation in enumerate(citations_raw, start=1):
                if not isinstance(citation, dict):
                    continue
                url = str(citation.get("url") or "").strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                metadata = (
                    citation.get("metadata")
                    if isinstance(citation.get("metadata"), dict)
                    else {}
                )
                domain = _normalize_domain(
                    citation.get("canonical_domain")
                    or metadata.get("canonical_domain")
                    or url
                )
                taxonomy = taxonomy_map.get(domain or "")
                if taxonomy is None and domain:
                    taxonomy = _infer_domain_taxonomy(
                        domain, official_domains, platform
                    )
                    taxonomy_map[domain] = taxonomy
                title = (
                    str(
                        citation.get("title") or citation.get("site_name") or ""
                    ).strip()
                    or None
                )
                snippet = (
                    str(
                        citation.get("snippet") or citation.get("summary") or ""
                    ).strip()
                    or None
                )
                brand_related = _domain_matches(domain, official_domains)
                if not brand_related:
                    brand_related = _match_brand_from_text(
                        f"{title or ''} {snippet or ''}", brand_name, aliases
                    )
                source_type = str(
                    citation.get("source_type") or metadata.get("source_type") or ""
                ).strip()
                url_intelligence = (
                    citation.get("url_intelligence")
                    if isinstance(citation.get("url_intelligence"), dict)
                    else (
                        metadata.get("url_intelligence")
                        if isinstance(metadata.get("url_intelligence"), dict)
                        else {}
                    )
                )
                site_category = str(
                    citation.get("site_category")
                    or metadata.get("site_category")
                    or (
                        url_intelligence.get("category")
                        if isinstance(url_intelligence, dict)
                        else ""
                    )
                    or ""
                ).strip()
                if (
                    _is_meaningful_site_category(site_category)
                    and source_type.lower() in {"", "other"}
                ):
                    source_type = site_category
                if not source_type:
                    source_type = (
                        site_category
                        if _is_meaningful_site_category(site_category)
                        else (taxonomy.source_type if taxonomy else "other")
                    )
                is_official = bool(citation.get("is_official")) or _domain_matches(
                    domain, official_domains
                )
                if is_official:
                    source_type = "official"
                site_name = str(
                    citation.get("site_display_name")
                    or metadata.get("site_display_name")
                    or citation.get("site_name")
                    or citation.get("source")
                    or ""
                ).strip() or (taxonomy.display_name if taxonomy else None)
                information_updated_at = str(
                    citation.get("information_updated_at")
                    or metadata.get("information_updated_at")
                    or ""
                ).strip()
                information_updated_at_source = str(
                    citation.get("information_updated_at_source")
                    or metadata.get("information_updated_at_source")
                    or ""
                ).strip()
                citation_records.append(
                    CitationFetchRecord(
                        citation_id=f"{question_id}:{platform}:{citation_index}",
                        title=title,
                        url=url,
                        domain=domain,
                        snippet=snippet,
                        site_name=site_name,
                        source_type=source_type,
                        site_category=(
                            site_category
                            if _is_meaningful_site_category(site_category)
                            else None
                        ),
                        url_intelligence=(
                            dict(url_intelligence)
                            if isinstance(url_intelligence, dict)
                            else {}
                        ),
                        information_updated_at=information_updated_at or None,
                        information_updated_at_source=(
                            information_updated_at_source or None
                        ),
                        ecosystem_tag=(taxonomy.ecosystem_tag if taxonomy else "none"),
                        is_platform_ecosystem=bool(
                            taxonomy and taxonomy.is_platform_ecosystem
                        ),
                        is_official=is_official,
                        brand_related=brand_related,
                        official_conversion_flag=is_official,
                    )
                )

            mentioned_brands, monitor_mentioned, competitor_brands = (
                _detect_mentioned_brands(answer_text, brand_master)
            )
            answer_state = _classify_answer_state(
                mentioned_brands=mentioned_brands,
                monitor_mentioned=monitor_mentioned,
            )
            sentiment = analyze_sentiment(answer_text) if answer_text else "neutral"
            positive_reasons = _detect_positive_reasons(answer_text, sentiment)
            negative_conclusions, negative_topics = _detect_negative_conclusions(
                answer_text, citation_records
            )
            logic_archetype = _infer_logic_archetype(
                question, answer_text, citation_records
            )
            recommendation_pattern_code = _infer_recommendation_pattern(logic_archetype)
            primary_recommended_brand = _infer_primary_recommended_brand(
                answer_text, mentioned_brands
            )

            answers.append(
                AnswerRecord(
                    answer_id=f"{question_id}:{platform}:{platform_index}",
                    question_id=question_id,
                    question_text=question.question_text,
                    platform=platform or "unknown",
                    status="ok" if success else "missing",
                    answer_text=answer_text or None,
                    answer_time=datetime.now(timezone.utc).isoformat(),
                    citation_records=citation_records,
                    mentioned_brands=mentioned_brands,
                    mentioned_monitor_brand=monitor_mentioned,
                    competitor_brands=competitor_brands,
                    primary_recommended_brand=primary_recommended_brand,
                    answer_state=answer_state,
                    sentiment=(
                        sentiment
                        if sentiment in {"positive", "neutral", "negative"}
                        else "neutral"
                    ),
                    positive_reasons=positive_reasons,
                    negative_conclusions=negative_conclusions,
                    negative_topics=negative_topics,
                    comparison_answer_flag=_is_comparison_question(
                        question, answer_text
                    ),
                    no_citation_strong_recommend_flag=bool(
                        primary_recommended_brand == brand_name
                        and not citation_records
                        and any(
                            token in answer_text
                            for token in ("推荐", "优先", "首选", "更适合")
                        )
                    ),
                    logic_archetype=logic_archetype,  # type: ignore[arg-type]
                    recommendation_pattern_code=recommendation_pattern_code,  # type: ignore[arg-type]
                )
            )

    meta = ReportMeta(
        report_kind=report_kind,
        analysis_mode=report_kind,
        brand_name=brand_name,
        industry=str(brand_profile.get("industry") or "").strip() or None,
        scenario_theme=(
            "、".join(selected_personas)
            if report_kind == "scenario" and selected_personas
            else str(brand_profile.get("scenario_theme") or "").strip() or None
        ),
        baseline_report_id=baseline_report_id,
        session_id=session_id,
        entity_id=entity_id,
        generated_at=datetime.now(timezone.utc).date().isoformat(),
        platforms=sorted(
            platforms_seen or {normalize_platform(platform) for platform in PLATFORMS}
        ),
    )

    return InputBundle(
        meta=meta,
        brand_master=brand_master,
        questions=[question_map[key] for key in sorted(question_map)],
        answers=answers,
        domain_taxonomy=[taxonomy_map[key] for key in sorted(taxonomy_map)],
    )


def _build_visibility_analyzer(bundle: InputBundle) -> dict[str, Any]:
    successful_answers = [answer for answer in bundle.answers if answer.status == "ok"]
    total_answers = len(successful_answers)
    answer_state_counter = Counter(answer.answer_state for answer in successful_answers)
    brand_answers = [
        answer for answer in successful_answers if answer.mentioned_monitor_brand
    ]

    brand_counter: Counter[str] = Counter()
    for answer in successful_answers:
        for brand in answer.mentioned_brands:
            brand_counter[brand] += 1

    ranked_brands = sorted(brand_counter.items(), key=lambda item: (-item[1], item[0]))
    brand_rank = None
    higher_brands: list[str] = []
    top_brand_ranking: list[dict[str, Any]] = []
    total_presence = sum(brand_counter.values())
    for index, (brand, count) in enumerate(ranked_brands, start=1):
        share = safe_ratio(count, total_presence)
        if index <= 10:
            top_brand_ranking.append(
                {
                    "rank": index,
                    "brand": brand,
                    "brand_presence_count": count,
                    "brand_share": share,
                }
            )
        if brand == bundle.brand_master.monitor_brand:
            brand_rank = index
            higher_brands = [item[0] for item in ranked_brands[: index - 1]][:5]

    summary = {
        "question_sample_count": len(bundle.questions),
        "answer_sample_count": total_answers,
        "platform_count": len(bundle.meta.platforms),
        "brand_visibility": safe_ratio(len(brand_answers), total_answers),
        "competitor_pressure": safe_ratio(
            answer_state_counter.get("competitor_only", 0), total_answers
        ),
        "no_brand_rate": safe_ratio(
            answer_state_counter.get("no_brand", 0), total_answers
        ),
        "monitor_only_rate": safe_ratio(
            answer_state_counter.get("monitor_only", 0), total_answers
        ),
        "monitor_plus_others_rate": safe_ratio(
            answer_state_counter.get("monitor_plus_others", 0), total_answers
        ),
        "brand_rank": brand_rank,
        "ranked_brand_count": len(ranked_brands),
        "brand_presence_count": brand_counter.get(bundle.brand_master.monitor_brand, 0),
        "higher_brands": higher_brands,
        "top_brand_ranking": top_brand_ranking,
    }
    structure_tree = [
        "全部答案",
        f"├─ 提及监测品牌        {_format_ratio(summary['brand_visibility'])}",
        f"├─ 提及品牌但未提我    {_format_ratio(summary['competitor_pressure'])}",
        f"└─ 完全无品牌          {_format_ratio(summary['no_brand_rate'])}",
    ]
    return {
        "summary": summary,
        "answer_states": [
            {
                "answer_id": answer.answer_id,
                "question_id": answer.question_id,
                "platform": answer.platform,
                "answer_state": answer.answer_state,
            }
            for answer in successful_answers
        ],
        "structure_tree": structure_tree,
    }


def _build_citation_analyzer(bundle: InputBundle) -> dict[str, Any]:
    total_citations = 0
    brand_related_links = 0
    official_links = 0
    source_counter: Counter[str] = Counter()
    domain_counter: Counter[str] = Counter()
    domain_source_counter: dict[str, Counter[str]] = defaultdict(Counter)
    domain_display_names: dict[str, Counter[str]] = defaultdict(Counter)
    domain_site_categories: dict[str, Counter[str]] = defaultdict(Counter)
    domain_titles: dict[str, list[str]] = defaultdict(list)
    monitor_brand_answers = [
        answer
        for answer in bundle.answers
        if answer.status == "ok" and answer.mentioned_monitor_brand
    ]
    brand_related_link_answer_count = 0
    official_link_answer_count = 0
    platform_citation_counter: dict[str, Counter[str]] = defaultdict(Counter)
    platform_brand_related_totals: Counter[str] = Counter()
    platform_ecosystem_counts: Counter[str] = Counter()
    answer_rows: list[dict[str, Any]] = []
    taxonomy_by_domain = {
        record.domain: record for record in bundle.domain_taxonomy if record.domain
    }

    for answer in bundle.answers:
        if answer.status != "ok":
            continue
        deduped = _dedupe_dict_rows(
            [item.model_dump() for item in answer.citation_records], ("url",)
        )
        citations = [CitationFetchRecord(**item) for item in deduped]
        brand_related_in_answer = 0
        official_in_answer = 0
        for citation in citations:
            total_citations += 1
            if citation.domain:
                domain_counter[citation.domain] += 1
                domain_source_counter[citation.domain][citation.source_type] += 1
                if citation.site_name:
                    domain_display_names[citation.domain][citation.site_name] += 1
                if citation.site_category:
                    domain_site_categories[citation.domain][citation.site_category] += 1
                if (
                    citation.title
                    and citation.title not in domain_titles[citation.domain]
                ):
                    domain_titles[citation.domain].append(citation.title)
            if citation.brand_related:
                brand_related_links += 1
                brand_related_in_answer += 1
                source_counter[citation.source_type] += 1
                platform_citation_counter[answer.platform][citation.source_type] += 1
                platform_brand_related_totals[answer.platform] += 1
                if citation.is_platform_ecosystem:
                    platform_ecosystem_counts[answer.platform] += 1
            if citation.is_official:
                official_links += 1
                official_in_answer += 1
        if answer.mentioned_monitor_brand and brand_related_in_answer > 0:
            brand_related_link_answer_count += 1
        if answer.mentioned_monitor_brand and official_in_answer > 0:
            official_link_answer_count += 1
        answer_rows.append(
            {
                "answer_id": answer.answer_id,
                "platform": answer.platform,
                "citation_count": len(citations),
                "brand_related_link_count": brand_related_in_answer,
                "official_link_count": official_in_answer,
                "official_conversion_flag": bool(official_in_answer),
                "brand_related_links": [
                    citation.model_dump()
                    for citation in citations
                    if citation.brand_related
                ],
            }
        )

    source_type_keys = _ordered_source_types(source_counter.keys())
    source_type_breakdown = {
        source_type: safe_ratio(source_counter.get(source_type, 0), brand_related_links)
        for source_type in source_type_keys
    }

    platform_profiles: dict[str, Any] = {}
    for platform in bundle.meta.platforms:
        total = platform_brand_related_totals.get(platform, 0)
        source_preferences = {
            source_type: _preference_strength(
                safe_ratio(
                    platform_citation_counter[platform].get(source_type, 0), total
                )
            )
            for source_type in source_type_keys
        }
        platform_profiles[platform] = {
            "source_preferences": source_preferences,
            "ecosystem_preference": _preference_strength(
                safe_ratio(platform_ecosystem_counts.get(platform, 0), total)
            ),
            "brand_related_link_count": total,
        }

    top_domains = []
    for domain, count in sorted(
        domain_counter.items(), key=lambda item: (-item[1], item[0])
    )[:10]:
        taxonomy = taxonomy_by_domain.get(domain)
        source_type = (
            domain_source_counter[domain].most_common(1)[0][0]
            if domain_source_counter.get(domain)
            else (
                taxonomy.source_type
                if taxonomy
                else (
                    "official"
                    if _domain_matches(domain, bundle.brand_master.official_domains)
                    else "other"
                )
            )
        )
        sample_titles = domain_titles.get(domain, [])[:3]
        display_name = (
            domain_display_names[domain].most_common(1)[0][0]
            if domain_display_names.get(domain)
            else ""
        )
        site_category = (
            domain_site_categories[domain].most_common(1)[0][0]
            if domain_site_categories.get(domain)
            else None
        )
        top_domains.append(
            {
                "domain": domain,
                "display_name": _resolve_site_display_name(
                    domain=domain,
                    site_name=display_name,
                    sample_titles=sample_titles,
                    taxonomy=taxonomy,
                ),
                "count": count,
                "share": safe_ratio(count, total_citations),
                "is_official": _domain_matches(
                    domain, bundle.brand_master.official_domains
                ),
                "source_type": source_type,
                "site_category": site_category,
                "sample_titles": sample_titles,
            }
        )

    summary = {
        "brand_link_penetration": safe_ratio(brand_related_links, total_citations),
        "official_share": safe_ratio(official_links, brand_related_links),
        "official_conversion_rate": safe_ratio(
            official_link_answer_count, len(monitor_brand_answers)
        ),
        "source_type_breakdown": source_type_breakdown,
        "official_funnel": {
            "monitor_brand_answer_count": len(monitor_brand_answers),
            "brand_related_link_answer_count": brand_related_link_answer_count,
            "official_link_answer_count": official_link_answer_count,
        },
        "top_domains": top_domains,
        "platform_profiles": platform_profiles,
        "total_citations": total_citations,
        "brand_related_links": brand_related_links,
        "official_links": official_links,
    }
    return {"summary": summary, "answers": answer_rows}


def _build_question_coverage_analyzer(bundle: InputBundle) -> dict[str, Any]:
    answers_by_question: dict[str, list[AnswerRecord]] = defaultdict(list)
    for answer in bundle.answers:
        if answer.status == "ok":
            answers_by_question[answer.question_id].append(answer)

    successful_answers = [answer for answer in bundle.answers if answer.status == "ok"]
    brand_question_ids = {
        answer.question_id
        for answer in successful_answers
        if answer.mentioned_monitor_brand
    }

    coverage_scene = Counter(question.scene or "其他" for question in bundle.questions)
    coverage_intent = Counter(
        _intent_label(question.intent) for question in bundle.questions
    )
    coverage_stage = Counter(
        _stage_label(question.decision_stage) for question in bundle.questions
    )

    trigger_rows: list[dict[str, Any]] = []
    dropout_rows: list[dict[str, Any]] = []
    for dimension, extractor in (
        ("scene", lambda q: q.scene or "其他"),
        ("intent", lambda q: _intent_label(q.intent)),
        ("decision_stage", lambda q: _stage_label(q.decision_stage)),
    ):
        grouped_questions: dict[str, list[QuestionRecord]] = defaultdict(list)
        for question in bundle.questions:
            grouped_questions[extractor(question)].append(question)
        for value, questions in grouped_questions.items():
            relevant_answers = [
                answer
                for question in questions
                for answer in answers_by_question.get(question.question_id, [])
            ]
            total = len(relevant_answers)
            trigger_rows.append(
                {
                    "dimension": dimension,
                    "value": value,
                    "rate": safe_ratio(
                        sum(
                            1
                            for answer in relevant_answers
                            if answer.mentioned_monitor_brand
                        ),
                        total,
                    ),
                }
            )
            dropout_rows.append(
                {
                    "dimension": dimension,
                    "value": value,
                    "rate": safe_ratio(
                        sum(
                            1
                            for answer in relevant_answers
                            if answer.answer_state in {"no_brand", "competitor_only"}
                        ),
                        total,
                    ),
                }
            )

    overall_state_counter = Counter(
        answer.answer_state for answer in successful_answers
    )
    answer_state_matrix = {
        "overall": {
            state: safe_ratio(
                overall_state_counter.get(state, 0), len(successful_answers)
            )
            for state in (
                "no_brand",
                "competitor_only",
                "monitor_only",
                "monitor_plus_others",
            )
        },
        "by_intent": {},
    }
    for intent in sorted(
        {_intent_label(question.intent) for question in bundle.questions}
    ):
        question_ids = {
            question.question_id
            for question in bundle.questions
            if _intent_label(question.intent) == intent
        }
        intent_answers = [
            answer
            for answer in successful_answers
            if answer.question_id in question_ids
        ]
        answer_state_matrix["by_intent"][intent] = {
            state: safe_ratio(
                sum(1 for answer in intent_answers if answer.answer_state == state),
                len(intent_answers),
            )
            for state in (
                "no_brand",
                "competitor_only",
                "monitor_only",
                "monitor_plus_others",
            )
        }

    question_rows: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []
    risk_rows: list[dict[str, Any]] = []
    for question in bundle.questions:
        related_answers = answers_by_question.get(question.question_id, [])
        state_counter = Counter(answer.answer_state for answer in related_answers)
        dominant_state = (
            sorted(state_counter.items(), key=lambda item: (-item[1], item[0]))[0][0]
            if state_counter
            else "no_brand"
        )
        state_platforms = {
            state: sorted(
                {
                    answer.platform
                    for answer in related_answers
                    if answer.answer_state == state
                }
            )
            for state in (
                "no_brand",
                "competitor_only",
                "monitor_only",
                "monitor_plus_others",
            )
        }
        competitors_present = _normalize_text_list(
            [brand for answer in related_answers for brand in answer.competitor_brands]
        )
        negative_topics = _normalize_text_list(
            [topic for answer in related_answers for topic in answer.negative_topics]
        )
        row = {
            "question_id": question.question_id,
            "question_text": question.question_text,
            "scene": question.scene or "其他",
            "intent": _intent_label(question.intent),
            "decision_stage": _stage_label(question.decision_stage),
            "brand_present": question.question_id in brand_question_ids,
            "present_platforms": sorted(
                {answer.platform for answer in related_answers}
            ),
            "state_platforms": state_platforms,
            "official_citation_present": any(
                any(citation.is_official for citation in answer.citation_records)
                for answer in related_answers
                if answer.mentioned_monitor_brand
            ),
            "competitors_present": competitors_present,
            "answer_state": dominant_state,
            "negative_topics": negative_topics,
            "risk_level": (
                "high"
                if dominant_state in {"competitor_only", "no_brand"} or negative_topics
                else "medium" if competitors_present else "low"
            ),
        }
        question_rows.append(row)
        if dominant_state in {"competitor_only", "no_brand"}:
            missing_rows.append(row)
        if row["risk_level"] == "high":
            risk_rows.append(row)

    summary = {
        "question_count": len(bundle.questions),
        "coverage_by_scene": [
            {"label": item["label"], "count": item["count"], "rate": item["rate"]}
            for item in _sort_counter_rows(coverage_scene, len(bundle.questions))
        ],
        "coverage_by_intent": [
            {"label": item["label"], "count": item["count"], "rate": item["rate"]}
            for item in _sort_counter_rows(coverage_intent, len(bundle.questions))
        ],
        "coverage_by_stage": [
            {"label": item["label"], "count": item["count"], "rate": item["rate"]}
            for item in _sort_counter_rows(coverage_stage, len(bundle.questions))
        ],
        "top_trigger_categories": sorted(
            trigger_rows, key=lambda item: (-(item["rate"] or -1), item["value"])
        )[:3],
        "top_dropout_categories": sorted(
            dropout_rows, key=lambda item: (-(item["rate"] or -1), item["value"])
        )[:3],
        "answer_state_matrix": answer_state_matrix,
        "scenario_total": len(bundle.questions),
        "scenario_hit_count": len(brand_question_ids),
        "high_risk_scenario_count": len(risk_rows),
    }
    return {
        "summary": summary,
        "question_rows": question_rows,
        "missing_rows": missing_rows,
        "risk_rows": risk_rows,
    }


def _build_sentiment_risk_analyzer(bundle: InputBundle) -> dict[str, Any]:
    monitor_answers = [
        answer
        for answer in bundle.answers
        if answer.status == "ok" and answer.mentioned_monitor_brand
    ]
    distribution_counter = Counter(answer.sentiment for answer in monitor_answers)
    positive_reason_counter: Counter[str] = Counter()
    positive_reason_questions: dict[str, Counter[str]] = defaultdict(Counter)
    positive_reason_examples: dict[str, list[str]] = defaultdict(list)
    negative_topic_counter: Counter[str] = Counter()
    negative_topic_examples: dict[str, list[str]] = defaultdict(list)
    platform_negative_counter: dict[str, Counter[str]] = defaultdict(Counter)
    negative_source_counter: Counter[str] = Counter()
    answer_items: list[dict[str, Any]] = []
    negative_answer_count = 0

    for answer in monitor_answers:
        unique_reasons = _normalize_text_list(answer.positive_reasons)
        for reason in unique_reasons:
            positive_reason_counter[reason] += 1
            positive_reason_questions[reason][answer.question_text] += 1
            if len(positive_reason_examples[reason]) < 2 and answer.answer_text:
                positive_reason_examples[reason].append(
                    _clean_report_text(answer.answer_text, max_length=72)
                )
        unique_negative_topics = _normalize_text_list(answer.negative_topics)
        if unique_negative_topics:
            negative_answer_count += 1
        for source_attribution in {
            str(conclusion.get("source_attribution") or "model_inference")
            for conclusion in answer.negative_conclusions
        }:
            negative_source_counter[source_attribution] += 1
        for topic in unique_negative_topics:
            negative_topic_counter[topic] += 1
            platform_negative_counter[answer.platform][topic] += 1
        for conclusion in answer.negative_conclusions:
            for topic in conclusion.get("topics", []):
                if len(negative_topic_examples[topic]) < 2:
                    negative_topic_examples[topic].append(
                        _clean_report_text(
                            str(conclusion.get("text") or ""), max_length=60
                        )
                    )
        answer_items.append(
            {
                "answer_id": answer.answer_id,
                "question_id": answer.question_id,
                "question_text": answer.question_text,
                "platform": answer.platform,
                "sentiment": answer.sentiment,
                "answer_excerpt": _clean_report_text(
                    str(answer.answer_text or ""), max_length=96
                ),
                "positive_reasons": unique_reasons,
                "negative_topics": unique_negative_topics,
                "negative_conclusions": answer.negative_conclusions,
            }
        )

    positive_total = distribution_counter.get("positive", 0)
    top_positive_reasons = []
    for reason, count in sorted(
        positive_reason_counter.items(), key=lambda item: (-item[1], item[0])
    )[:3]:
        major_question_type = (
            sorted(
                positive_reason_questions[reason].items(),
                key=lambda item: (-item[1], item[0]),
            )[0][0]
            if positive_reason_questions[reason]
            else "N/A"
        )
        top_positive_reasons.append(
            {
                "reason": reason,
                "display": _positive_reason_label(reason),
                "rate": safe_ratio(count, positive_total),
                "major_question_type": major_question_type,
                "common_conclusion": "；".join(
                    positive_reason_examples.get(reason, [])[:2]
                )
                or "N/A",
            }
        )

    top_negative_topics = []
    for topic, count in sorted(
        negative_topic_counter.items(), key=lambda item: (-item[1], item[0])
    )[:4]:
        top_negative_topics.append(
            {
                "topic": topic,
                "display": _negative_topic_label(topic),
                "rate": safe_ratio(count, len(monitor_answers)),
                "common_conclusion": "；".join(
                    negative_topic_examples.get(topic, [])[:2]
                )
                or "N/A",
                "count": count,
            }
        )

    per_platform_negative_topics = {
        platform: {
            topic: platform_negative_counter[platform].get(topic, 0)
            for topic in NEGATIVE_TOPIC_DISPLAY
        }
        for platform in bundle.meta.platforms
    }
    negative_source_distribution = {
        "model_inference": safe_ratio(
            negative_source_counter.get("model_inference", 0),
            sum(negative_source_counter.values()),
        ),
        "cited_source": safe_ratio(
            negative_source_counter.get("cited_source", 0),
            sum(negative_source_counter.values()),
        ),
        "mixed": safe_ratio(
            negative_source_counter.get("mixed", 0),
            sum(negative_source_counter.values()),
        ),
    }
    summary = {
        "positive": safe_ratio(
            distribution_counter.get("positive", 0), len(monitor_answers)
        ),
        "neutral": safe_ratio(
            distribution_counter.get("neutral", 0), len(monitor_answers)
        ),
        "negative": safe_ratio(
            distribution_counter.get("negative", 0), len(monitor_answers)
        ),
    }
    return {
        "summary": summary,
        "top_positive_reasons": top_positive_reasons,
        "top_negative_topics": top_negative_topics,
        "per_platform_negative_topics": per_platform_negative_topics,
        "negative_source_distribution": negative_source_distribution,
        "items": answer_items,
    }


def _build_platform_profile_analyzer(
    bundle: InputBundle, citation_summary: dict[str, Any]
) -> dict[str, Any]:
    platform_answers: dict[str, list[AnswerRecord]] = defaultdict(list)
    for answer in bundle.answers:
        platform_answers[answer.platform].append(answer)

    platform_profiles: dict[str, Any] = {}
    for platform in bundle.meta.platforms:
        answers = [
            answer
            for answer in platform_answers.get(platform, [])
            if answer.status == "ok"
        ]
        if not answers:
            platform_profiles[platform] = {
                "data_status": "missing",
                "dominant_logic_archetype": None,
                "dominant_logic_display": "N/A",
                "recommendation_pattern_code": None,
                "recommendation_pattern_display": "N/A",
                "brand_friendly_question_types": [],
                "brand_unfriendly_question_types": [],
                "comparison_answer_inclusion_rate": None,
                "no_citation_strong_recommend_rate": None,
                "source_preferences": {},
                "ecosystem_preference": "low",
                "answer_feature_mix": {},
            }
            continue

        logic_counter = Counter(answer.logic_archetype for answer in answers)
        pattern_counter = Counter(
            answer.recommendation_pattern_code for answer in answers
        )
        comparison_answers = [
            answer for answer in answers if answer.comparison_answer_flag
        ]
        comparison_with_brand = [
            answer for answer in comparison_answers if answer.mentioned_monitor_brand
        ]
        no_citation_strong = [
            answer for answer in answers if answer.no_citation_strong_recommend_flag
        ]
        feature_counter: Counter[str] = Counter()
        for answer in answers:
            for feature in _answer_feature_flags(
                answer.answer_text or "", answer.citation_records
            ):
                feature_counter[feature] += 1

        friendly_rows = []
        unfriendly_rows = []
        for scene in sorted(
            {question.scene or "其他" for question in bundle.questions}
        ):
            scene_answers = [
                answer
                for answer in answers
                if next(
                    (question.scene or "其他")
                    for question in bundle.questions
                    if question.question_id == answer.question_id
                )
                == scene
            ]
            total = len(scene_answers)
            if not total:
                continue
            friendly_rows.append(
                {
                    "scene": scene,
                    "rate": safe_ratio(
                        sum(
                            1
                            for answer in scene_answers
                            if answer.mentioned_monitor_brand
                        ),
                        total,
                    ),
                }
            )
            unfriendly_rows.append(
                {
                    "scene": scene,
                    "rate": safe_ratio(
                        sum(
                            1
                            for answer in scene_answers
                            if answer.answer_state in {"no_brand", "competitor_only"}
                        ),
                        total,
                    ),
                }
            )

        citation_profile = citation_summary.get("platform_profiles", {}).get(
            platform, {}
        )
        dominant_logic = sorted(
            logic_counter.items(), key=lambda item: (-item[1], item[0])
        )[0][0]
        dominant_pattern = sorted(
            pattern_counter.items(), key=lambda item: (-item[1], item[0])
        )[0][0]
        platform_profiles[platform] = {
            "data_status": "ok",
            "dominant_logic_archetype": dominant_logic,
            "dominant_logic_display": LOGIC_ARCHETYPE_DISPLAY.get(
                dominant_logic, dominant_logic
            ),
            "recommendation_pattern_code": dominant_pattern,
            "recommendation_pattern_display": RECOMMENDATION_PATTERN_DISPLAY.get(
                dominant_pattern, dominant_pattern
            ),
            "brand_friendly_question_types": [
                row["scene"]
                for row in sorted(
                    friendly_rows,
                    key=lambda item: (-(item["rate"] or -1), item["scene"]),
                )[:2]
            ],
            "brand_unfriendly_question_types": [
                row["scene"]
                for row in sorted(
                    unfriendly_rows,
                    key=lambda item: (-(item["rate"] or -1), item["scene"]),
                )[:2]
            ],
            "comparison_answer_inclusion_rate": safe_ratio(
                len(comparison_with_brand), len(comparison_answers)
            ),
            "no_citation_strong_recommend_rate": safe_ratio(
                len(no_citation_strong), len(answers)
            ),
            "source_preferences": citation_profile.get(
                "source_preferences",
                {},
            ),
            "ecosystem_preference": citation_profile.get("ecosystem_preference", "low"),
            "answer_feature_mix": {
                code: safe_ratio(feature_counter.get(code, 0), len(answers))
                for code in ANSWER_CONTENT_FEATURES
            },
        }

    def _pick_platform(metric_getter) -> str | None:
        rows = []
        for platform, profile in platform_profiles.items():
            if profile.get("data_status") != "ok":
                continue
            value = metric_getter(profile)
            if value is None:
                continue
            rows.append((platform, value))
        if not rows:
            return None
        return sorted(rows, key=lambda item: (-item[1], item[0]))[0][0]

    judgments = {
        "most_official_friendly": _pick_platform(
            lambda profile: (
                2
                if profile["source_preferences"].get("official") == "high"
                else (
                    1
                    if profile["source_preferences"].get("official") == "medium"
                    else 0
                )
            )
        ),
        "most_vertical_media_influenced": _pick_platform(
            lambda profile: (
                2
                if profile["source_preferences"].get("vertical_media") == "high"
                else (
                    1
                    if profile["source_preferences"].get("vertical_media") == "medium"
                    else 0
                )
            )
        ),
        "most_no_citation_strong_recommend": _pick_platform(
            lambda profile: profile.get("no_citation_strong_recommend_rate") or 0
        ),
        "best_comparison_answer_breakthrough": _pick_platform(
            lambda profile: profile.get("comparison_answer_inclusion_rate") or 0
        ),
    }
    return {"platform_profiles": platform_profiles, "platform_judgments": judgments}


def build_metric_bundle(
    bundle: InputBundle,
    *,
    base_metrics: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], MetricBundle]:
    visibility = _build_visibility_analyzer(bundle)
    citations = _build_citation_analyzer(bundle)
    question_coverage = _build_question_coverage_analyzer(bundle)
    sentiment_risk = _build_sentiment_risk_analyzer(bundle)
    platform_profile = _build_platform_profile_analyzer(bundle, citations["summary"])

    metric_bundle = MetricBundle(
        total_questions=len(bundle.questions),
        total_answers=len(bundle.answers),
        successful_answers=visibility["summary"]["answer_sample_count"],
        platform_count=visibility["summary"]["platform_count"],
        brand_visibility=visibility["summary"]["brand_visibility"],
        competitor_pressure=visibility["summary"]["competitor_pressure"],
        no_brand_rate=visibility["summary"]["no_brand_rate"],
        monitor_only_rate=visibility["summary"]["monitor_only_rate"],
        monitor_plus_others_rate=visibility["summary"]["monitor_plus_others_rate"],
        brand_rank=visibility["summary"]["brand_rank"],
        ranked_brand_count=visibility["summary"]["ranked_brand_count"],
        brand_presence_count=visibility["summary"]["brand_presence_count"],
        higher_brands=visibility["summary"]["higher_brands"],
        top_brand_ranking=visibility["summary"]["top_brand_ranking"],
        brand_link_penetration=citations["summary"]["brand_link_penetration"],
        official_share=citations["summary"]["official_share"],
        official_conversion_rate=citations["summary"]["official_conversion_rate"],
        negative_rate=sentiment_risk["summary"]["negative"],
        sentiment_distribution=sentiment_risk["summary"],
        top_positive_reasons=sentiment_risk["top_positive_reasons"],
        top_negative_topics=sentiment_risk["top_negative_topics"],
        negative_source_distribution=sentiment_risk["negative_source_distribution"],
        source_type_breakdown=citations["summary"]["source_type_breakdown"],
        official_funnel=citations["summary"]["official_funnel"],
        coverage_by_scene=question_coverage["summary"]["coverage_by_scene"],
        coverage_by_intent=question_coverage["summary"]["coverage_by_intent"],
        coverage_by_stage=question_coverage["summary"]["coverage_by_stage"],
        top_trigger_categories=question_coverage["summary"]["top_trigger_categories"],
        top_dropout_categories=question_coverage["summary"]["top_dropout_categories"],
        answer_state_matrix=question_coverage["summary"]["answer_state_matrix"],
        platform_profiles=platform_profile["platform_profiles"],
        platform_judgments=platform_profile["platform_judgments"],
        scenario_total=question_coverage["summary"]["scenario_total"],
        scenario_hit_count=question_coverage["summary"]["scenario_hit_count"],
        high_risk_scenario_count=question_coverage["summary"][
            "high_risk_scenario_count"
        ],
        mention_rate=visibility["summary"]["brand_visibility"],
        content_citation_rate=citations["summary"]["brand_link_penetration"],
        official_citation_rate=citations["summary"]["official_conversion_rate"],
        visibility_summary=visibility["summary"],
        source_summary=citations["summary"],
        question_diagnostics={
            "question_rows": question_coverage["question_rows"],
            "missing_rows": question_coverage["missing_rows"],
            "risk_rows": question_coverage["risk_rows"],
            "top_trigger_categories": question_coverage["summary"][
                "top_trigger_categories"
            ],
            "top_dropout_categories": question_coverage["summary"][
                "top_dropout_categories"
            ],
        },
        sentiment_risk={
            "items": sentiment_risk["items"],
            "top_positive_reasons": sentiment_risk["top_positive_reasons"],
            "top_negative_topics": sentiment_risk["top_negative_topics"],
            "per_platform_negative_topics": sentiment_risk[
                "per_platform_negative_topics"
            ],
            "negative_source_distribution": sentiment_risk[
                "negative_source_distribution"
            ],
        },
        platform_profile={
            "platform_profiles": platform_profile["platform_profiles"],
            "platform_judgments": platform_profile["platform_judgments"],
        },
    )
    analyzer_outputs = {
        "brand_entity_resolver": {
            "answers": [
                {
                    "answer_id": answer.answer_id,
                    "mentioned_brands": answer.mentioned_brands,
                    "mentioned_monitor_brand": answer.mentioned_monitor_brand,
                    "competitor_brands": answer.competitor_brands,
                    "primary_recommended_brand": answer.primary_recommended_brand,
                }
                for answer in bundle.answers
                if answer.status == "ok"
            ]
        },
        "answer_state_classifier": {
            "answers": [
                {"answer_id": answer.answer_id, "answer_state": answer.answer_state}
                for answer in bundle.answers
                if answer.status == "ok"
            ]
        },
        "citation_analyzer": citations,
        "question_coverage_mapper": question_coverage,
        "sentiment_reason_parser": sentiment_risk,
        "platform_logic_profiler": platform_profile,
        "legacy_metrics": base_metrics or {},
    }
    return analyzer_outputs, metric_bundle


def build_comparison_bundle(
    *,
    bundle: InputBundle,
    metric_bundle: MetricBundle,
    baseline_report: dict[str, Any] | None = None,
) -> ComparisonBundle:
    if bundle.meta.report_kind != "scenario":
        return ComparisonBundle(
            comparable=False, reason="panorama_report_has_no_baseline_delta"
        )
    baseline_payload = baseline_report or {}
    baseline_metric_bundle = baseline_payload.get("metric_bundle")
    if not isinstance(baseline_metric_bundle, dict):
        return ComparisonBundle(
            comparable=False,
            baseline_report_id=bundle.meta.baseline_report_id,
            reason="baseline_metric_bundle_missing",
        )

    visibility_delta = {
        "brand_visibility": (
            round(
                metric_bundle.brand_visibility
                - baseline_metric_bundle.get("brand_visibility"),
                4,
            )
            if isinstance(metric_bundle.brand_visibility, (int, float))
            and isinstance(baseline_metric_bundle.get("brand_visibility"), (int, float))
            else None
        ),
        "brand_rank": (
            baseline_metric_bundle.get("brand_rank") - metric_bundle.brand_rank
            if isinstance(metric_bundle.brand_rank, int)
            and isinstance(baseline_metric_bundle.get("brand_rank"), int)
            else None
        ),
        "competitor_pressure": (
            round(
                metric_bundle.competitor_pressure
                - baseline_metric_bundle.get("competitor_pressure"),
                4,
            )
            if isinstance(metric_bundle.competitor_pressure, (int, float))
            and isinstance(
                baseline_metric_bundle.get("competitor_pressure"), (int, float)
            )
            else None
        ),
        "no_brand_rate": (
            round(
                metric_bundle.no_brand_rate
                - baseline_metric_bundle.get("no_brand_rate"),
                4,
            )
            if isinstance(metric_bundle.no_brand_rate, (int, float))
            and isinstance(baseline_metric_bundle.get("no_brand_rate"), (int, float))
            else None
        ),
    }
    citation_delta = {
        "brand_link_penetration": (
            round(
                metric_bundle.brand_link_penetration
                - baseline_metric_bundle.get("brand_link_penetration"),
                4,
            )
            if isinstance(metric_bundle.brand_link_penetration, (int, float))
            and isinstance(
                baseline_metric_bundle.get("brand_link_penetration"), (int, float)
            )
            else None
        ),
        "official_share": (
            round(
                metric_bundle.official_share
                - baseline_metric_bundle.get("official_share"),
                4,
            )
            if isinstance(metric_bundle.official_share, (int, float))
            and isinstance(baseline_metric_bundle.get("official_share"), (int, float))
            else None
        ),
        "official_conversion_rate": (
            round(
                metric_bundle.official_conversion_rate
                - baseline_metric_bundle.get("official_conversion_rate"),
                4,
            )
            if isinstance(metric_bundle.official_conversion_rate, (int, float))
            and isinstance(
                baseline_metric_bundle.get("official_conversion_rate"), (int, float)
            )
            else None
        ),
    }
    sentiment_delta = {
        "negative_rate": (
            round(
                metric_bundle.negative_rate
                - baseline_metric_bundle.get("negative_rate"),
                4,
            )
            if isinstance(metric_bundle.negative_rate, (int, float))
            and isinstance(baseline_metric_bundle.get("negative_rate"), (int, float))
            else None
        )
    }
    baseline_platforms = (
        baseline_metric_bundle.get("platform_profiles", {})
        if isinstance(baseline_metric_bundle.get("platform_profiles"), dict)
        else {}
    )
    per_platform_delta = {}
    for platform, profile in metric_bundle.platform_profiles.items():
        baseline_profile = (
            baseline_platforms.get(platform, {})
            if isinstance(baseline_platforms.get(platform), dict)
            else {}
        )
        per_platform_delta[platform] = {
            "comparison_answer_inclusion_rate": (
                round(
                    (profile.get("comparison_answer_inclusion_rate") or 0)
                    - (baseline_profile.get("comparison_answer_inclusion_rate") or 0),
                    4,
                )
                if baseline_profile
                else None
            )
        }

    return ComparisonBundle(
        comparable=True,
        baseline_report_id=bundle.meta.baseline_report_id
        or str(
            baseline_payload.get("artifact_id")
            or baseline_payload.get("report_id")
            or ""
        ),
        visibility_delta=visibility_delta,
        citation_delta=citation_delta,
        sentiment_delta=sentiment_delta,
        per_platform_delta=per_platform_delta,
    )


def _build_header_markdown(bundle: InputBundle) -> tuple[dict[str, Any], str]:
    title = (
        f"{bundle.meta.brand_name}｜品牌全景分析报告"
        if bundle.meta.report_kind == "panorama"
        else f"{bundle.meta.brand_name}｜用户场景分析报告"
    )
    subtitle = (
        f"这份报告关注 {bundle.meta.brand_name} 在品牌进入、来源承接、问题覆盖和平台偏好上的当前表现。"
        if bundle.meta.report_kind == "panorama"
        else f"围绕{bundle.meta.scenario_theme or '当前场景'}，这份报告关注{bundle.meta.brand_name}在这个场景里的品牌进入、官网承接，以及相对全景基线的变化。"
    )
    lines = [f"# {title}", "", subtitle, ""]
    lines.append(f"**品牌**：{bundle.meta.brand_name}  ")
    if bundle.meta.report_kind == "panorama":
        lines.append(f"**行业**：{bundle.meta.industry or 'N/A'}  ")
    else:
        lines.append(f"**场景主题**：{bundle.meta.scenario_theme or 'N/A'}  ")
    lines.append(
        f"**监测平台**：{' / '.join(_platform_label(platform) for platform in bundle.meta.platforms)}  "
    )
    lines.append(f"**问题样本数**：{len(bundle.questions)}  ")
    lines.append(
        f"**答案样本数**：{len([answer for answer in bundle.answers if answer.status == 'ok'])}  "
    )
    lines.append(f"**监测时间**：{bundle.meta.generated_at}  ")
    if bundle.meta.report_kind == "scenario":
        lines.append(
            "**对比基线**："
            + (
                "已绑定当前会话最近一次品牌全景分析报告  "
                if bundle.meta.baseline_report_id
                else "N/A  "
            )
        )
    markdown = "\n".join(lines).strip()
    return (
        {
            "section_name": "header",
            "title": title,
            "subtitle": subtitle,
            "markdown": markdown,
            "data": bundle.meta.model_dump(),
        },
        markdown,
    )


def _build_summary_section(
    bundle: InputBundle, metrics: MetricBundle, comparison: ComparisonBundle
) -> dict[str, Any]:
    summary_rows = [
        [
            "品牌可见度",
            _format_ratio(metrics.brand_visibility),
            "所有答案中提及监测品牌的比例",
        ],
        [
            "品牌提及排名",
            f"#{metrics.brand_rank}" if metrics.brand_rank else "N/A",
            "在全部被提及品牌中排名",
        ],
        [
            "竞品挤压率",
            _format_ratio(metrics.competitor_pressure),
            "提及品牌但未提监测品牌的答案占比",
        ],
        [
            "品牌负向提及率",
            _format_ratio(metrics.negative_rate),
            "提及监测品牌的答案中出现负向信息的比例",
        ],
        [
            "官网引用转化率",
            _format_ratio(metrics.official_conversion_rate),
            "提及监测品牌的答案中，同时引用官网链接的答案占比",
        ],
    ]
    biggest_gap = "竞品把答案拿走"
    if (metrics.no_brand_rate or 0) > (metrics.competitor_pressure or 0):
        biggest_gap = "平台不给品牌"
    elif (metrics.official_conversion_rate or 0) < 0.15:
        biggest_gap = "官网没接住流量"
    strong_visibility = (metrics.brand_visibility or 0) >= 0.6
    leading_rank = metrics.brand_rank == 1 if metrics.brand_rank else False
    top_negative = _strip_false_negative_topics(metrics.top_negative_topics)[:2]
    fallback_negative_issues = (
        _fallback_negative_issue_rows(bundle) if not top_negative else []
    )
    topic_text = (
        "、".join(item["display"] for item in top_negative)
        if top_negative
        else "负面信息暂不集中"
    )
    if not metrics.brand_visibility or metrics.brand_visibility <= 0:
        one_line = f"{bundle.meta.brand_name}在当前样本中还没有稳定进入答案，眼下最要紧的是先让平台愿意提到品牌；最大缺口在于{biggest_gap}。"
    else:
        if strong_visibility and leading_rank:
            if (metrics.official_conversion_rate or 0) <= 0:
                one_line = f"{bundle.meta.brand_name}在当前样本里的整体表现不错：已经进入大多数答案，而且在被提及的品牌里排第一；接下来更值得补的是把这部分露出接回官网。"
            elif (metrics.official_conversion_rate or 0) < 0.5:
                one_line = f"{bundle.meta.brand_name}在当前样本里的整体表现不错：已经进入大多数答案，而且在被提及的品牌里排第一；官网已经开始承接流量，下一步更适合继续提升承接稳定性。"
            else:
                one_line = f"{bundle.meta.brand_name}在当前样本里的整体表现不错：已经进入大多数答案，而且在被提及的品牌里排第一；官网承接也已经形成基础，后续可以继续放大这部分优势。"
        else:
            if (metrics.official_conversion_rate or 0) <= 0:
                one_line = f"{bundle.meta.brand_name}已经能被提到，也具备一定进入能力；接下来更值得继续优化的是让这种露出更稳定，同时把流量接回官网。"
            else:
                one_line = f"{bundle.meta.brand_name}已经能被提到，也具备一定进入能力；官网已经开始承接流量，接下来更值得继续优化的是把这种露出变成更稳定的主推荐。"
    suggestions: list[str] = []
    if not metrics.brand_visibility or (metrics.no_brand_rate or 0) >= 0.5:
        suggestions.append(
            f"先解决平台不给品牌的问题：补品牌定义页、适用场景页和替代对比页，让平台先愿意把{bundle.meta.brand_name}带进答案。"
        )
    if (metrics.official_conversion_rate or 0) < 0.2:
        suggestions.append(
            "优先补价格、使用场景、核心差异和替代对比这几类官网内容，把品牌露出接回官网。"
        )
    if (metrics.competitor_pressure or 0) >= 0.3:
        suggestions.append(
            "优先治理比较型问题里的竞品压制，强化对比页、案例页和选型说明。"
        )
    if top_negative:
        suggestions.append(
            f"优先处理 {topic_text} 相关的负向认知，并同步清理外部高频来源。"
        )
    elif fallback_negative_issues:
        suggestions.append(
            f"优先把{('、'.join(row['display'] for row in fallback_negative_issues[:2]))}这些决策顾虑讲清楚，减少模型自己补出结论。"
        )
    if bundle.meta.report_kind == "scenario" and comparison.comparable:
        no_brand_delta = comparison.visibility_delta.get("no_brand_rate")
        if isinstance(no_brand_delta, (int, float)) and no_brand_delta > 0:
            suggestions.append(
                "优先补这个场景里最容易不提品牌的问题，先把相关顾虑和使用条件写成能被直接摘用的结论。"
            )
    if not suggestions:
        suggestions.append(
            "优先围绕当前场景补一页式结论页和 FAQ，再看品牌可见度和官网引用转化率会不会继续抬高。"
        )
    subtitle = (
        "这个场景下，品牌进入、官网承接，以及相对全景基线的变化，是最值得关注的三件事。"
        if bundle.meta.report_kind == "scenario"
        else "品牌进入、排位变化和官网承接，是当前最值得关注的三件事。"
    )
    official_bullet = (
        "品牌被提到以后，本轮还没有出现官网引用。"
        if (metrics.official_conversion_rate or 0) <= 0
        else (
            "品牌被提到以后，已经有一部分流量回到官网。"
            if (metrics.official_conversion_rate or 0) < 0.5
            else "品牌被提到以后，官网已经能承接较大一部分流量。"
        )
    )
    third_key_fact = (
        "主要引用来源仍然是外部垂媒，官网还没有开始承接流量。"
        if (metrics.official_conversion_rate or 0) <= 0
        else "主要引用来源仍然是外部垂媒，官网已经开始承接一部分流量。"
    )
    summary_opening = (
        f"{bundle.meta.brand_name}在当前样本里的整体表现不错，已经能稳定进入答案，并且在被提及的品牌里排在前面。"
        if strong_visibility and leading_rank
        else (
            f"{bundle.meta.brand_name}已经能进入一部分答案，说明品牌具备基础进入能力。"
            if metrics.brand_visibility and metrics.brand_visibility > 0
            else f"{bundle.meta.brand_name}在当前样本里还没有稳定进入答案。"
        )
    )
    second_key_fact = (
        f"在被提及的品牌里，{bundle.meta.brand_name}目前排在 **第 {metrics.brand_rank} 位**；这轮更值得继续优化的，是让更多比较类回答把品牌写成更明确的推荐。"
        if leading_rank
        else (
            f"在被提及的品牌里，{bundle.meta.brand_name}目前排在 **第 {metrics.brand_rank} 位**；后续可以继续看哪些问题更容易把品牌带进答案。"
            if metrics.brand_rank
            else "当前样本里还没有形成稳定的品牌排名，需要先让品牌更稳定地进入答案。"
        )
    )
    if strong_visibility:
        visibility_bullet = f"{bundle.meta.brand_name}已经能被平台带进大多数答案。"
        first_key_fact = (
            f"{bundle.meta.brand_name}已经进入大多数答案，其中 **{_format_ratio(metrics.monitor_only_rate)}** "
            f"的答案只提{bundle.meta.brand_name}，**{_format_ratio(metrics.monitor_plus_others_rate)}** 的答案会和竞品同台出现。"
        )
    elif (metrics.brand_visibility or 0) > 0:
        visibility_bullet = (
            f"{bundle.meta.brand_name}只进入了一部分答案，还不能算稳定进入。"
        )
        first_key_fact = (
            f"{bundle.meta.brand_name}已经有基础露出，但进入还不稳定；只提{bundle.meta.brand_name}的答案占 **{_format_ratio(metrics.monitor_only_rate)}**，"
            f"和竞品同台出现的答案占 **{_format_ratio(metrics.monitor_plus_others_rate)}**。"
        )
    else:
        visibility_bullet = f"{bundle.meta.brand_name}当前还没有稳定进入答案。"
        first_key_fact = f"{bundle.meta.brand_name}当前还没有稳定进入答案，第一优先级是先减少无品牌回答和只提竞品回答。"
    competitor_bullet = (
        f"这部分答案会优先给竞品，不写{bundle.meta.brand_name}。"
        if (metrics.competitor_pressure or 0) > 0
        else ""
    )
    baseline_fact_lines: list[str] = []
    if bundle.meta.report_kind == "scenario" and comparison.comparable:
        official_delta = comparison.citation_delta.get("official_conversion_rate")
        no_brand_delta = comparison.visibility_delta.get("no_brand_rate")
        if isinstance(official_delta, (int, float)) or isinstance(
            no_brand_delta, (int, float)
        ):
            baseline_fact = []
            if isinstance(official_delta, (int, float)):
                direction = "高了" if official_delta >= 0 else "低了"
                baseline_fact.append(
                    f"官网引用转化率比全景基线{direction} **{_format_delta_points_cn(official_delta)}**"
                )
            if isinstance(no_brand_delta, (int, float)):
                direction = "更高" if no_brand_delta >= 0 else "更低"
                baseline_fact.append(
                    f"不提任何品牌的答案占比也{direction} **{_format_delta_points_cn(no_brand_delta)}**"
                )
            if baseline_fact:
                baseline_fact_lines.extend(
                    [
                        "",
                        "### 和全景基线相比",
                        "",
                        "，".join(baseline_fact) + "。",
                    ]
                )
    markdown = "\n".join(
        [
            "## 执行摘要",
            "",
            summary_opening,
            "",
            "- "
            + _format_metric_emphasis(
                "品牌可见度", _format_ratio(metrics.brand_visibility)
            )
            + f"。{visibility_bullet}",
            "- "
            + _format_metric_emphasis(
                "品牌提及排名",
                f"#{metrics.brand_rank}" if metrics.brand_rank else "N/A",
            )
            + f"。{_brand_rank_sentence(bundle.meta.brand_name, metrics.brand_rank)}",
            "- "
            + _format_metric_emphasis(
                "竞品挤压率", _format_ratio(metrics.competitor_pressure)
            )
            + ("。" + competitor_bullet if competitor_bullet else "。"),
            "- "
            + _format_metric_emphasis(
                "品牌负向提及率", _format_ratio(metrics.negative_rate)
            )
            + "。负面信息比例不高，但几类顾虑已经开始重复出现。",
            "- "
            + _format_metric_emphasis(
                "官网引用转化率", _format_ratio(metrics.official_conversion_rate)
            )
            + f"。{official_bullet}",
            "",
            f"一句话判断：{one_line}",
            "",
            "### 最值得先看的三件事",
            "",
            f"1. {first_key_fact}",
            f"2. {second_key_fact}",
            f"3. {third_key_fact}",
            *baseline_fact_lines,
            "",
            "### 当前最值得先做的事",
            "\n".join(
                f"{index}. {suggestion}"
                for index, suggestion in enumerate(suggestions[:3], start=1)
            ),
        ]
    ).strip()
    return {
        "section_name": "summary",
        "title": "执行摘要",
        "subtitle": subtitle,
        "markdown": markdown,
        "data": {
            "metrics": summary_rows,
            "one_line_conclusion": one_line,
            "suggestions": suggestions[:3],
        },
    }


def _build_visibility_section(
    bundle: InputBundle,
    metrics: MetricBundle,
    comparison: ComparisonBundle,
    visibility_data: dict[str, Any],
) -> dict[str, Any]:
    core_rows = [
        ["问题样本数", metrics.total_questions],
        ["答案样本数", metrics.successful_answers],
        ["平台数", metrics.platform_count],
        ["品牌可见度", _format_ratio(metrics.brand_visibility)],
        ["品牌提及排名", f"#{metrics.brand_rank}" if metrics.brand_rank else "N/A"],
        ["竞品挤压率", _format_ratio(metrics.competitor_pressure)],
        ["无品牌率", _format_ratio(metrics.no_brand_rate)],
    ]
    ranking_rows = [
        [
            row["rank"],
            (
                f"**{row['brand']}**"
                if row["brand"] == bundle.brand_master.monitor_brand
                else row["brand"]
            ),
            _format_ratio(
                safe_ratio(row["brand_presence_count"], metrics.successful_answers)
            ),
        ]
        for row in metrics.top_brand_ranking
    ]
    strong_visibility = (metrics.brand_visibility or 0) >= 0.6
    leading_rank = metrics.brand_rank == 1 if metrics.brand_rank else False
    if not metrics.brand_visibility or metrics.brand_visibility <= 0:
        opening_line = f"{bundle.meta.brand_name}在当前样本里还没有稳定进入答案，现阶段更重要的是先让平台愿意把品牌写进去。"
        conclusion = f"{bundle.meta.brand_name}还处在先进入答案的阶段；优先级最高的是减少无品牌回答。"
    elif strong_visibility and leading_rank:
        opening_line = f"{bundle.meta.brand_name}在这个场景里的可见度已经不错：大多数答案会提到它，而且当前提及排名第一。"
        conclusion = f"{bundle.meta.brand_name}已经具备较强的进入能力；如果还要继续优化，更适合把重点放在减少无品牌回答，以及让更多比较类回答把品牌写成更明确的推荐。"
    else:
        opening_line = f"{bundle.meta.brand_name}已经能进入不少答案，也具备基础可见度；后续可以继续看哪些问题更容易把它写成明确推荐。"
        conclusion = f"{bundle.meta.brand_name}已经进入答案，但不同问题上的表现还不完全一致；后续可以继续观察哪些问题更容易出现竞品同台或无品牌回答。"
    subtitle = f"看{bundle.meta.brand_name}能不能进答案、在被提及时排得靠不靠前，以及哪些回答会带上竞品或不给品牌。"
    ranking_lines = [
        f"- 第 {row['rank']} 位：**{row['brand']}**，提及率 {_format_ratio(safe_ratio(row['brand_presence_count'], metrics.successful_answers))}"
        for row in metrics.top_brand_ranking[:5]
    ]
    competition_line = (
        f"当前暂时没有品牌排在{bundle.meta.brand_name}前面，说明它已经具备较强的进入能力；后续更值得继续看的，是哪些问题会把它写成明确推荐，哪些问题干脆不给品牌。"
        if not metrics.higher_brands
        else f"当前排位高于{bundle.meta.brand_name}的品牌有{'、'.join(metrics.higher_brands)}，需要继续复核这些品牌在哪类问题上更容易被优先提及。"
    )
    if (metrics.brand_visibility or 0) >= 0.6:
        visibility_sentence = f"大多数答案会提到{bundle.meta.brand_name}。"
    elif (metrics.brand_visibility or 0) > 0:
        visibility_sentence = (
            f"只有一部分答案会提到{bundle.meta.brand_name}，还不能算稳定进入。"
        )
    else:
        visibility_sentence = f"当前样本里还没有答案稳定提到{bundle.meta.brand_name}。"
    markdown = "\n".join(
        [
            "## 1. 可见度分析",
            "",
            opening_line,
            "",
            f"- {_format_metric_emphasis('品牌可见度', _format_ratio(metrics.brand_visibility))}。{visibility_sentence}",
            f"- {_format_metric_emphasis(f'只提{bundle.meta.brand_name}的答案', _format_ratio(metrics.monitor_only_rate))}。这部分回答会把{bundle.meta.brand_name}作为更明确的推荐对象。",
            f"- {_format_metric_emphasis(f'同时提到{bundle.meta.brand_name}和竞品的答案', _format_ratio(metrics.monitor_plus_others_rate))}。这类回答更像比较名单，{bundle.meta.brand_name}和竞品会一起出现。",
            f"- {_format_metric_emphasis('无品牌率', _format_ratio(metrics.no_brand_rate))}。这部分回答更偏知识性建议，没有带出任何品牌。",
            "",
            "在这类需要比较的决策问题里，和竞品同台并不一定是坏信号，因为平台本来就偏好给比较名单；更值得继续优化的，是减少无品牌回答，以及让更多比较类回答把品牌写成更明确的推荐。",
            "",
            competition_line,
            "",
            "提及率排在前面的品牌是：",
            *((ranking_lines[:3] or ["- 当前样本中尚未形成稳定的品牌排名。"])),
            "",
            f"结论：{conclusion}",
        ]
    ).strip()
    return {
        "section_name": "visibility",
        "title": "可见度分析",
        "subtitle": subtitle,
        "markdown": markdown,
        "data": {
            "core_rows": core_rows,
            "ranking_rows": ranking_rows,
            "higher_brands": metrics.higher_brands,
            "conclusion": conclusion,
        },
    }


def _build_citation_section(
    bundle: InputBundle, metrics: MetricBundle
) -> dict[str, Any]:
    source_rows = [
        [
            _source_type_label(source_type),
            _format_ratio(metrics.source_type_breakdown.get(source_type)),
        ]
        for source_type in _ordered_source_types(metrics.source_type_breakdown.keys())
    ]
    funnel = metrics.official_funnel
    top_domains = (
        metrics.source_summary.get("top_domains", [])
        if isinstance(metrics.source_summary, dict)
        else []
    )
    domain_rows = [
        [
            _format_site_cell(row),
            _source_type_label(
                str(
                    row.get("source_type")
                    or ("official" if row.get("is_official") else "other")
                )
            ),
            row.get("count") or 0,
        ]
        for row in top_domains[:8]
    ]
    top_sites = "、".join(
        str(row.get("display_name") or row.get("domain") or "")
        for row in top_domains[:3]
        if row.get("display_name") or row.get("domain")
    )
    source_parts = []
    for source_type in _ordered_source_types(metrics.source_type_breakdown.keys()):
        ratio = metrics.source_type_breakdown.get(source_type)
        if ratio is None:
            continue
        if ratio <= 0:
            continue
        source_parts.append(
            f"{_source_type_label(source_type)} **{_format_ratio(ratio)}**"
        )
    other_domain_notes = _collect_other_domain_notes(bundle)
    ranked_site_lines = [
        f"{index}. **{row.get('display_name') or row.get('domain') or 'N/A'}**，{row.get('count') or 0} 次，{_source_type_label(str(row.get('source_type') or 'other'))}"
        for index, row in enumerate(top_domains[:5], start=1)
    ]
    conclusion = (
        f"当前不只是官网被引用少，更关键的是{bundle.meta.brand_name}被提及时，官网没有稳定接住这次露出机会；外部高频来源主要集中在{top_sites or '行业媒体'}。"
        if (metrics.official_conversion_rate or 0) < 0.3
        else f"{bundle.meta.brand_name}已经具备一定官网承接能力，但仍需继续优化品牌相关内容在引用链中的覆盖度。"
    )
    other_lines = []
    if other_domain_notes:
        other_lines.append(
            f"本轮被归到 **其他** 的并不是一个大类来源，而是 **{len(other_domain_notes)} 个零散站点**。"
        )
        for row in other_domain_notes[:4]:
            other_lines.append(
                f"- **{row['display_name']}（{row['domain']}）**：出现 {row['count']} 次，主要出现在{row['platform'] or 'N/A'}的问题「{row['question_text'] or 'N/A'}」里；{row['reason']}"
            )
    subtitle = (
        "官网已经开始承接一部分流量，但主要引用来源仍然是外部垂媒。"
        if (metrics.official_conversion_rate or 0) > 0
        else "品牌能被提到，但官网还没有接住这部分流量。"
    )
    opening_line = (
        f"{bundle.meta.brand_name}能被提到，但几乎没有把这次露出接回官网。"
        if (metrics.official_conversion_rate or 0) < 0.1
        else f"{bundle.meta.brand_name}能被提到，也已经开始把一部分露出接回官网，但承接还不稳定。"
    )
    markdown = "\n".join(
        [
            "## 2. 链接可见度分析",
            "",
            opening_line,
            "",
            f"- 提到品牌的答案有 **{funnel.get('monitor_brand_answer_count', 0)} 条**。",
            f"- 其中 **{funnel.get('brand_related_link_answer_count', 0)} 条** 带了品牌相关链接。",
            f"- 其中 **{funnel.get('official_link_answer_count', 0)} 条** 直接引用官网，对应 **官网引用转化率 {_format_ratio(metrics.official_conversion_rate)}**。",
            "",
            f"如果只看品牌相关链接，来源主要是 {'、'.join(source_parts) if source_parts else 'N/A'}。也就是说，当前承接品牌露出的主要不是官网，而是外部垂媒和社区。",
            "",
            "平台最常引用的站点是：",
            "",
            *((ranked_site_lines or ["1. 当前样本里暂无可复核的高频引用站点。"])),
            "",
            "关于“其他”：",
            *((other_lines or ["本轮没有落入“其他”的品牌相关站点。"])),
            "",
            f"**结论**：{conclusion}",
        ]
    ).strip()
    return {
        "section_name": "citation_visibility",
        "title": "链接可见度分析",
        "subtitle": subtitle,
        "markdown": markdown,
        "data": {
            "source_rows": source_rows,
            "domain_rows": domain_rows,
            "official_funnel": funnel,
            "conclusion": conclusion,
        },
    }


def _build_question_section(
    bundle: InputBundle, metrics: MetricBundle, analyzer_outputs: dict[str, Any]
) -> dict[str, Any]:
    question_rows = analyzer_outputs["question_coverage_mapper"]["question_rows"]
    scene_labels = [str(row["label"]) for row in metrics.coverage_by_scene]
    entry_scene_summaries = sorted(
        _meaningful_band_summaries(question_rows, field="scene", labels=scene_labels),
        key=lambda item: (
            -(safe_ratio(item["entered_count"], item["question_count"]) or -1),
            -item["question_count"],
            item["label"],
        ),
    )
    dropout_scene_summaries = sorted(
        _meaningful_band_summaries(question_rows, field="scene", labels=scene_labels),
        key=lambda item: (
            -(
                safe_ratio(
                    item["competitor_only_count"] + item["no_brand_count"],
                    item["question_count"],
                )
                or -1
            ),
            -item["question_count"],
            item["label"],
        ),
    )
    risk_summary = _category_question_summary(
        question_rows, field="intent", value=_intent_label("risk_or_problem")
    )
    price_summary = _category_question_summary(
        question_rows, field="intent", value=_intent_label("price_or_cost")
    )
    scene_summary = _category_question_summary(
        question_rows, field="scene", value="画像痛点场景"
    )
    comparison_summary = _category_question_summary(
        question_rows, field="scene", value="品类选购对比"
    )
    scene_label = _report_label(scene_summary["label"])
    comparison_label = _report_label(comparison_summary["label"])
    coverage_text = _top_scene_coverage_text(metrics.coverage_by_scene)
    comparison_entered = comparison_summary["entered_count"]
    comparison_total = comparison_summary["question_count"]
    entry_lines = []
    for summary in entry_scene_summaries[:2]:
        entry_rate = safe_ratio(summary["entered_count"], summary["question_count"])
        if (
            not summary["question_count"]
            or not summary["entered_count"]
            or summary["label"] == comparison_summary["label"]
        ):
            continue
        exclusive_note = (
            f"其中有 {summary['exclusive_count']} 个问题最后只提了{bundle.meta.brand_name}。"
            if (summary["exclusive_count"] or 0) > 0
            else ""
        )
        sample_quotes = _sample_question_quotes(summary["questions"], limit=2)
        block = [
            f"- {_report_label(summary['label'])}共有 {summary['question_count']} 个问题，至少有一个平台把{bundle.meta.brand_name}写进答案的有 {summary['entered_count']} 个，进入率 **{_format_ratio(entry_rate)}**。{exclusive_note}".strip()
        ]
        block.extend(sample_quotes)
        entry_lines.append("\n".join(block))
    dropout_lines = []
    for summary in dropout_scene_summaries[:2]:
        missed_count = summary["competitor_only_count"] + summary["no_brand_count"]
        if not summary["question_count"] or not missed_count:
            continue
        gap_quotes = _state_question_quotes(
            summary["questions"],
            states={"competitor_only", "no_brand"},
        )
        dropout_clause = _join_nonempty_clauses(
            [
                _count_clause(summary["competitor_only_count"], "只提竞品"),
                _count_clause(summary["no_brand_count"], "完全不提品牌"),
            ],
            prefix="其中 ",
        )
        block = [
            (
                f"- {_report_label(summary['label'])}共有 {summary['question_count']} 个问题，{dropout_clause}。"
                if dropout_clause
                else f"- {_report_label(summary['label'])}共有 {summary['question_count']} 个问题，是本轮需要复查的掉出问题。"
            )
        ]
        block.extend(gap_quotes)
        dropout_lines.append("\n".join(block))
    if not risk_summary["question_count"]:
        risk_line = "这轮暂时没有形成明显的风险顾虑问题带。"
    elif not risk_summary["entered_count"]:
        risk_line = (
            f"这轮和风险、顾虑有关的问题有 {risk_summary['question_count']} 个，"
            f"本轮没有稳定把{bundle.meta.brand_name}写进答案；这些问题需要优先补充可引用的安全边界、适用条件和证据出处。"
        )
    elif (risk_summary["exclusive_count"] or 0) > 0:
        risk_line = (
            f"这轮和风险、顾虑有关的问题有 {risk_summary['question_count']} 个。"
            f"至少有一个平台把{bundle.meta.brand_name}写进答案的有 {risk_summary['entered_count']} 个，"
            f"其中最后只提{bundle.meta.brand_name}的有 **{risk_summary['exclusive_count']} 个**；"
            "也就是说，平台更愿意把它放进比较名单，而不是直接给出结论。"
        )
    else:
        risk_line = (
            f"这轮和风险、顾虑有关的问题有 {risk_summary['question_count']} 个。"
            f"至少有一个平台把{bundle.meta.brand_name}写进答案的有 {risk_summary['entered_count']} 个；"
            "这些问题里，品牌更多是被放进比较名单，而不是直接成为结论。"
        )
    price_drop_samples = _state_question_samples(
        price_summary["questions"], states={"competitor_only", "no_brand"}, limit=2
    )
    if not price_summary["question_count"]:
        price_line = "这轮暂时没有形成明显的价格和成本问题带。"
    elif not price_summary["entered_count"]:
        sample_clause = (
            f"例如「{'、'.join(price_drop_samples)}」。" if price_drop_samples else ""
        )
        price_line = (
            f"这轮和价格、成本有关的问题有 {price_summary['question_count']} 个，"
            f"本轮没有稳定把{bundle.meta.brand_name}写进答案；需要补清价格理由、购买渠道和替代方案对比。"
            f"{sample_clause}"
        )
    elif price_drop_samples:
        price_line = (
            f"这轮和价格、成本有关的问题有 {price_summary['question_count']} 个。"
            f"至少有一个平台把{bundle.meta.brand_name}写进答案的有 {price_summary['entered_count']} 个；"
            f"其中「{'、'.join(price_drop_samples)}」已经出现品牌掉出。"
        )
    else:
        price_line = (
            f"这轮和价格、成本有关的问题有 {price_summary['question_count']} 个。"
            f"至少有一个平台把{bundle.meta.brand_name}写进答案的有 {price_summary['entered_count']} 个。"
        )
    if not scene_summary["question_count"]:
        scene_line = "这轮暂时还没有形成稳定的具体使用场景问题带。"
    elif not scene_summary["entered_count"]:
        scene_line = (
            f"{scene_label}共有 {scene_summary['question_count']} 个，"
            f"本轮没有稳定把{bundle.meta.brand_name}写进答案；这是当前最容易掉出的使用场景，需要补具体人群、场景痛点和产品适配证据。"
        )
    elif (scene_summary["exclusive_count"] or 0) > 0:
        scene_line = (
            f"{scene_label}共有 {scene_summary['question_count']} 个。"
            f"至少有一个平台把{bundle.meta.brand_name}写进答案的有 {scene_summary['entered_count']} 个，"
            f"其中最后只提{bundle.meta.brand_name}的有 **{scene_summary['exclusive_count']} 个**；"
            "这也是当前最容易直接不给品牌的一类问题。"
        )
    else:
        scene_line = (
            f"{scene_label}共有 {scene_summary['question_count']} 个。"
            f"至少有一个平台把{bundle.meta.brand_name}写进答案的有 {scene_summary['entered_count']} 个；"
            "这也是当前最容易直接不给品牌的一类问题。"
        )
    comparison_line = ""
    if comparison_total and comparison_entered:
        comparison_line = (
            f"{comparison_label}相对更容易带出品牌：共 {comparison_total} 个问题，"
            f"其中 {comparison_entered} 个问题至少有一个平台提到{bundle.meta.brand_name}。"
        )
    elif comparison_total:
        comparison_line = f"{comparison_label}本轮没有稳定带出{bundle.meta.brand_name}，暂不把它作为优势问题类型。"
    gap_question_lines = []
    for row in sorted(
        [
            row
            for row in question_rows
            if row["answer_state"] in {"competitor_only", "no_brand"}
        ],
        key=lambda item: (
            0 if item["answer_state"] == "no_brand" else 1,
            item["question_text"],
        ),
    )[:4]:
        state = str(row["answer_state"])
        state_platforms = row.get("state_platforms") or {}
        platforms = (
            state_platforms.get(state) if isinstance(state_platforms, dict) else None
        ) or row.get("present_platforms", [])
        platform_clause = (
            "未提及任何品牌的平台"
            if state == "no_brand"
            else f"只提竞品、未提{bundle.meta.brand_name}的平台"
        )
        gap_question_lines.append(
            "\n".join(
                [
                    f"{len(gap_question_lines) + 1}. {platform_clause}：{_sample_platform_labels(platforms)}。",
                    _markdown_quote_block(
                        _clean_report_text(row["question_text"], max_length=80)
                    ),
                ]
            )
        )
    entry_hint = (
        f"直接问品牌和{comparison_label}"
        if comparison_total and comparison_entered
        else "直接问品牌"
    )
    conclusion = f"{bundle.meta.brand_name}不是完全进不去答案，而是在不同问题上的表现差得很大：{entry_hint}时更容易进去，{scene_label}和风险顾虑这类问题更容易不给品牌。"
    subtitle = f"{entry_hint}更容易进入；{scene_label}与风险顾虑更容易掉出。"
    markdown = "\n".join(
        [
            "## 3. 问题解析",
            "",
            f"{bundle.meta.brand_name}现在最需要分清的是：哪些问题会认真推荐它，哪些问题压根不给品牌。",
            "",
            f"当前最集中的问题是：{coverage_text}。",
            "",
            "### 3.1 更容易写进答案的问题",
            "",
            *(([f"- {comparison_line}"] if comparison_line else [])),
            *((entry_lines or ["- 当前样本里还没有形成稳定的进入优势。"])),
            "",
            f"### 3.2 最容易不提{bundle.meta.brand_name}的问题",
            "",
            *((dropout_lines or ["- 当前样本里还没有形成稳定的掉点。"])),
            "",
            "### 3.3 最该先补的内容",
            "",
            f"- {risk_line}",
            f"- {price_line}",
            f"- {scene_line}",
            "",
            "### 3.4 需要马上复盘的原问题",
            "",
            *((gap_question_lines or ["- 当前没有需要单独拉出来复盘的掉出问题。"])),
            "",
            f"结论：{conclusion}",
        ]
    ).strip()
    return {
        "section_name": "question_diagnostics",
        "title": "问题解析",
        "subtitle": subtitle,
        "markdown": markdown,
        "data": {
            "question_rows": question_rows,
            "trigger_summaries": entry_scene_summaries[:2],
            "dropout_summaries": dropout_scene_summaries[:2],
            "conclusion": conclusion,
        },
    }


def _build_sentiment_section(
    bundle: InputBundle, metrics: MetricBundle
) -> dict[str, Any]:
    distribution_rows = [
        ["正向", _format_ratio(metrics.sentiment_distribution.get("positive"))],
        ["中性", _format_ratio(metrics.sentiment_distribution.get("neutral"))],
        ["负向", _format_ratio(metrics.sentiment_distribution.get("negative"))],
    ]
    positive_rows = [
        [
            index,
            row["display"],
            _format_ratio(row["rate"]),
            row.get("common_conclusion") or row["major_question_type"],
        ]
        for index, row in enumerate(metrics.top_positive_reasons, start=1)
    ]
    display_negative_topics = _strip_false_negative_topics(metrics.top_negative_topics)
    fallback_negative_issues = (
        _fallback_negative_issue_rows(bundle) if not display_negative_topics else []
    )
    if not display_negative_topics:
        display_negative_topics = []
    negative_rows = [
        [index, row["display"], _format_ratio(row["rate"]), row["common_conclusion"]]
        for index, row in enumerate(display_negative_topics, start=1)
    ]
    per_platform_topics = metrics.sentiment_risk.get("per_platform_negative_topics", {})
    per_platform_rows = [
        [
            _platform_label(platform),
            per_platform_topics.get(platform, {}).get("price", 0),
            per_platform_topics.get(platform, {}).get("deployment", 0),
            per_platform_topics.get(platform, {}).get("ecosystem", 0),
            per_platform_topics.get(platform, {}).get("service", 0),
        ]
        for platform in bundle.meta.platforms
    ]
    negative_source_rows = [
        [
            "模型自身归纳",
            _format_ratio(metrics.negative_source_distribution.get("model_inference")),
        ],
        [
            "引用来源带出",
            _format_ratio(metrics.negative_source_distribution.get("cited_source")),
        ],
        ["混合", _format_ratio(metrics.negative_source_distribution.get("mixed"))],
    ]
    if not any(
        value for value in metrics.sentiment_distribution.values() if value is not None
    ):
        conclusion = "当前样本里品牌几乎没有被明确提及，因此还谈不上稳定的品牌情感画像；应先让品牌进入答案，再看正负反馈结构。"
    elif fallback_negative_issues:
        focus_text = "、".join(row["display"] for row in fallback_negative_issues[:2])
        conclusion = f"当前更需要澄清的，不是笼统差评，而是几类会卡住决策的问题：{focus_text}。这类顾虑大多来自模型自己的归纳，不是外部文章直接给出的结论。"
    else:
        conclusion = f"当前需要优先澄清的负面信息主要集中在 {'、'.join(row['display'] for row in display_negative_topics[:2]) or '少量零散问题'}，既需要补官网澄清内容，也要同步关注模型在回答中的默认归纳逻辑。"
    subtitle = (
        "当前更像决策顾虑，而不是大面积口碑差评。"
        if fallback_negative_issues
        else "负面信息比例不高，但已经有几类顾虑在反复出现。"
    )
    positive_lines = []
    for row in positive_rows[:3]:
        positive_lines.append(
            "\n".join(
                [
                    f"- {row[1]}，出现率 **{row[2]}**；典型说法：",
                    _markdown_quote_block(
                        _clean_report_text(str(row[3]), max_length=88)
                    ),
                ]
            )
        )
    negative_lines = []
    if fallback_negative_issues:
        for row in fallback_negative_issues[:3]:
            negative_lines.append(
                "\n".join(
                    [
                        f"- {row['display']}，影响答案占比 **{_format_ratio(row['rate'])}**；对应问题：",
                        _markdown_quote_block(row["question_text"]),
                        *(
                            [_markdown_quote_block(row["common_conclusion"])]
                            if row.get("common_conclusion")
                            else []
                        ),
                    ]
                )
            )
    else:
        for row in negative_rows[:3]:
            negative_lines.append(
                "\n".join(
                    [
                        f"- {row[1]}，影响答案占比 **{row[2]}**；典型负面/顾虑说法：",
                        _markdown_quote_block(
                            _clean_report_text(str(row[3]), max_length=72)
                        ),
                    ]
                )
            )
    platform_lines = []
    for row in per_platform_rows:
        (
            platform_label,
            price_count,
            deployment_count,
            ecosystem_count,
            service_count,
        ) = row
        total_negative = (
            int(price_count)
            + int(deployment_count)
            + int(ecosystem_count)
            + int(service_count)
        )
        if total_negative <= 0:
            continue
        focus_pairs = []
        if deployment_count:
            focus_pairs.append(
                f"{_negative_topic_label('deployment')} {deployment_count} 次"
            )
        if service_count:
            focus_pairs.append(f"{_negative_topic_label('service')} {service_count} 次")
        if price_count:
            focus_pairs.append(f"{_negative_topic_label('price')} {price_count} 次")
        if ecosystem_count:
            focus_pairs.append(
                f"{_negative_topic_label('ecosystem')} {ecosystem_count} 次"
            )
        platform_lines.append(
            f"- **{platform_label}**：本轮更容易放大 {'、'.join(focus_pairs)}。"
        )
    markdown = "\n".join(
        [
            "## 4. 情感与风险解析",
            "",
            f"{bundle.meta.brand_name}的负面信息比例不高，但已经有几类会卡住决策的顾虑在重复出现。",
            "",
            f"在提到{bundle.meta.brand_name}的答案里，整体以正向 **{_format_ratio(metrics.sentiment_distribution.get('positive'))}** 和中性 **{_format_ratio(metrics.sentiment_distribution.get('neutral'))}** 为主，明确负向的比例是 **{_format_ratio(metrics.sentiment_distribution.get('negative'))}**。",
            "",
            "### 4.1 当前最常被认可的信息",
            *((positive_lines or ["- 当前样本里还没有形成稳定的正向判断。"])),
            "",
            "### 4.2 最需要澄清的顾虑",
            *(
                (
                    negative_lines
                    or [
                        "- 当前样本里的负面信息还不够集中，暂时没有形成稳定的高频负面说法。"
                    ]
                )
            ),
            "",
            "### 4.3 哪些平台更容易放大这些顾虑",
            *((platform_lines or ["- 当前还没有足够样本判断平台差异。"])),
            "",
            f"本轮负面信息里，**模型自身归纳占 {_format_ratio(metrics.negative_source_distribution.get('model_inference'))}**，**外部引用直接带出占 {_format_ratio(metrics.negative_source_distribution.get('cited_source'))}**。这意味着当前更大的问题不是“外部文章在骂品牌”，而是模型在回答时主动归纳出了这些顾虑。",
            "",
            f"结论：{conclusion}",
        ]
    ).strip()
    return {
        "section_name": "sentiment_risk",
        "title": "情感与风险解析",
        "subtitle": subtitle,
        "markdown": markdown,
        "data": {
            "distribution_rows": distribution_rows,
            "positive_rows": positive_rows,
            "negative_rows": negative_rows,
            "per_platform_rows": per_platform_rows,
            "negative_source_rows": negative_source_rows,
            "conclusion": conclusion,
        },
    }


def _build_platform_section(
    bundle: InputBundle, metrics: MetricBundle
) -> dict[str, Any]:
    platform_profiles = metrics.platform_profiles
    logic_rows = []
    comparison_rows = []
    preference_rows = []
    effective_platform_notes = []
    empty_platforms = []
    for platform in bundle.meta.platforms:
        profile = platform_profiles.get(platform, {})
        platform_label = _platform_label(platform)
        source_preferences = profile.get("source_preferences", {})
        if profile.get("data_status") != "ok":
            logic_rows.append([platform_label, "样本不足", "N/A", "N/A", "N/A"])
            comparison_rows.append([platform_label, "N/A"])
            preference_rows.append(
                [
                    platform_label,
                    "暂无明显来源偏好",
                    {"high": "高", "medium": "中", "low": "低"}.get(
                        profile.get("ecosystem_preference"), "低"
                    ),
                    "N/A",
                ]
            )
            empty_platforms.append(platform_label)
            continue
        logic_rows.append(
            [
                platform_label,
                profile.get("dominant_logic_display") or "N/A",
                profile.get("recommendation_pattern_display") or "N/A",
                "、".join(profile.get("brand_friendly_question_types") or []) or "N/A",
                "、".join(profile.get("brand_unfriendly_question_types") or [])
                or "N/A",
            ]
        )
        comparison_rows.append(
            [
                platform_label,
                _format_ratio(profile.get("comparison_answer_inclusion_rate")),
            ]
        )
        preferred_sources = (
            "、".join(_preferred_source_labels(source_preferences))
            or "暂无明显来源偏好"
        )
        preference_rows.append(
            [
                platform_label,
                preferred_sources,
                {"high": "高", "medium": "中", "low": "低"}.get(
                    profile.get("ecosystem_preference"), "低"
                ),
                _format_ratio(profile.get("no_citation_strong_recommend_rate")),
            ]
        )
        comparison_rate = _format_ratio(profile.get("comparison_answer_inclusion_rate"))
        friendly_labels = [
            label
            for label in (
                _report_label(item)
                for item in (profile.get("brand_friendly_question_types") or [])
            )
            if label and label != "其他"
        ]
        unfriendly_labels = [
            label
            for label in (
                _report_label(item)
                for item in (profile.get("brand_unfriendly_question_types") or [])
            )
            if label and label != "其他"
        ]
        mention_sentence = (
            f"更容易在{'、'.join(friendly_labels)}这类问题里提到品牌"
            if friendly_labels
            else "目前还看不出哪类问题会明显更愿意提到品牌"
        )
        miss_sentence = (
            f"在{'、'.join(unfriendly_labels)}这类问题里更容易不提品牌"
            if unfriendly_labels
            else "也还看不出哪类问题会稳定把品牌排除在外"
        )
        source_sentence = (
            f"引用上更依赖 {preferred_sources}"
            if preferred_sources != "暂无明显来源偏好"
            else "本轮没有看到稳定的来源偏好"
        )
        feature_mix = _format_feature_mix(profile.get("answer_feature_mix", {}))
        platform_note = (
            f"{platform_label}的答案结构里，{feature_mix}。"
            f" 常见组织方式是“{profile.get('dominant_logic_display') or 'N/A'} / {profile.get('recommendation_pattern_display') or 'N/A'}”。"
            f" 比较类问题里，{bundle.meta.brand_name}进入答案的比例是 **{comparison_rate}**；{mention_sentence}，{miss_sentence}。"
            f" {source_sentence}。"
        )
        effective_platform_notes.append(f"### {platform_label}\n{platform_note}")
    judgments = metrics.platform_judgments
    subtitle = (
        f"本轮只有{_platform_label(next((p for p in bundle.meta.platforms if platform_profiles.get(p, {}).get('data_status') == 'ok'), ''))}有稳定样本，适合先做验证。"
        if any(
            platform_profiles.get(p, {}).get("data_status") == "ok"
            for p in bundle.meta.platforms
        )
        else "当前样本还不足，暂时看不出稳定的平台差异。"
    )
    lead_line = (
        f"这轮能稳定下判断的平台，主要是{'和'.join([_platform_label(p) for p in bundle.meta.platforms if platform_profiles.get(p, {}).get('data_status') == 'ok'][:2])}。"
        if sum(
            1
            for p in bundle.meta.platforms
            if platform_profiles.get(p, {}).get("data_status") == "ok"
        )
        >= 2
        else (
            f"这轮能稳定下判断的平台，主要是{_platform_label(next((p for p in bundle.meta.platforms if platform_profiles.get(p, {}).get('data_status') == 'ok'), ''))}。"
            if any(
                platform_profiles.get(p, {}).get("data_status") == "ok"
                for p in bundle.meta.platforms
            )
            else "这轮样本还不足，暂时看不出稳定的平台差异。"
        )
    )
    empty_platform_line = (
        f"### {'、'.join(empty_platforms)}\n本轮可用于平台偏好判断的样本不足，先不下平台性格结论。"
        if empty_platforms
        else None
    )
    validation_platform = judgments.get("best_comparison_answer_breakthrough")
    validation_platform_label = (
        _platform_label(validation_platform) if validation_platform else None
    )
    validation_reason = None
    if validation_platform:
        validation_profile = platform_profiles.get(validation_platform, {})
        validation_rate = _format_ratio(
            validation_profile.get("comparison_answer_inclusion_rate")
        )
        source_preferences = validation_profile.get("source_preferences", {})
        preferred_sources = (
            "、".join(_preferred_source_labels(source_preferences))
            or "暂无明显来源偏好"
        )
        if validation_rate not in {"N/A", "0.0%"}:
            validation_reason = (
                f"最适合先验证内容调整的平台是{validation_platform_label}。"
                f" 这个平台在比较类问题里已经更愿意让{bundle.meta.brand_name}进入答案（当前为 **{validation_rate}**），"
                f"而且它的引用更受{preferred_sources}影响；如果官网结论页和可引用内容补齐，"
                "也最容易先看到品牌可见度和官网引用转化率的变化。"
            )
        else:
            validation_reason = (
                f"最适合先验证内容调整的平台是{validation_platform_label}。"
                f" 这个平台已经有可复查的比较类样本，虽然当前还没形成明显优势，但最适合先观察内容调整后的品牌可见度和官网引用转化率。"
            )
    judgment_lines = [
        f"最愿意引用官网：{_platform_label(judgments.get('most_official_friendly')) if judgments.get('most_official_friendly') else 'N/A'}",
        f"最容易被垂媒影响：{_platform_label(judgments.get('most_vertical_media_influenced')) if judgments.get('most_vertical_media_influenced') else 'N/A'}",
        f"最适合先验证内容调整：{validation_platform_label or 'N/A'}",
    ]
    comparison_summary = "；".join(
        f"{row[0]} **{row[1]}**" for row in comparison_rows if row[1] != "N/A"
    )
    conclusion = (
        validation_reason.replace("最适合先验证内容调整的平台是", "").strip()
        if validation_reason
        else "当前样本还不足以形成稳定的平台结论。"
    )
    markdown = "\n".join(
        [
            "## 5. 平台偏好分析",
            "",
            lead_line,
            "",
            *((effective_platform_notes or ["当前样本不足，尚未形成稳定的平台判断。"])),
            *(([empty_platform_line] if empty_platform_line else [])),
            "",
            f"比较类问题里，{bundle.meta.brand_name}进入答案的比例分别是：{comparison_summary or '当前样本不足，无法比较。'}。",
            "",
            *([validation_reason] if validation_reason else []),
        ]
    ).strip()
    return {
        "section_name": "platform_preference",
        "title": "平台偏好分析",
        "subtitle": subtitle,
        "markdown": markdown,
        "data": {
            "logic_rows": logic_rows,
            "comparison_rows": comparison_rows,
            "preference_rows": preference_rows,
            "platform_notes": effective_platform_notes,
            "judgment_lines": judgment_lines,
            "conclusion": conclusion,
        },
    }


def _build_recommendation_section(
    bundle: InputBundle,
    metrics: MetricBundle,
    comparison: ComparisonBundle,
    analyzer_outputs: dict[str, Any],
) -> dict[str, Any]:
    recommendations: list[list[Any]] = []
    question_rows = analyzer_outputs["question_coverage_mapper"]["question_rows"]
    price_summary = _category_question_summary(
        question_rows, field="intent", value=_intent_label("price_or_cost")
    )
    scene_summary = _category_question_summary(
        question_rows, field="scene", value="画像痛点场景"
    )
    citation_summary = analyzer_outputs["citation_analyzer"]["summary"]
    top_domains = (
        citation_summary.get("top_domains", [])
        if isinstance(citation_summary, dict)
        else []
    )
    top_source_names = (
        "、".join(
            str(row.get("display_name") or row.get("domain") or "")
            for row in top_domains[:3]
            if row.get("display_name") or row.get("domain")
        )
        or "主要垂媒"
    )
    if not metrics.brand_visibility or (metrics.no_brand_rate or 0) >= 0.5:
        recommendations.append(
            [
                "P1",
                "先把品牌带进答案",
                f"当前无品牌率是 **{_format_ratio(metrics.no_brand_rate)}**，说明品牌还没有稳定进入答案。",
                "先把品牌定义、适用场景和替代对比三类基础内容写成可直接引用的官网结论句，不要只放产品参数。",
                "观察品牌可见度和无品牌率是否一起改善。",
            ]
        )
    elif price_summary["question_count"] or scene_summary["question_count"]:
        dropped_samples = _state_question_samples(
            price_summary["questions"] + scene_summary["questions"],
            states={"competitor_only", "no_brand"},
            limit=3,
        )
        sample_text = "、".join(dropped_samples) or "当前最容易没有把品牌写进答案的问题"
        recommendations.append(
            [
                "P1",
                "先补最接近决策的问题",
                f"这轮和价格、成本有关的问题有 **{price_summary['question_count']}** 个，{_report_label(scene_summary['label'])}有 **{scene_summary['question_count']}** 个。当前最常没有把品牌写进答案的问题是 {sample_text}。",
                "先把这些决策问题整理成官网结论页，再准备可被平台直接摘用的短答案。",
                "观察这几类问题里的品牌可见度，以及官网引用转化率是否继续抬高。",
            ]
        )
    if (metrics.official_conversion_rate or 0) < 0.2:
        recommendations.append(
            [
                "P1",
                "把品牌露出接回官网",
                f"现在有 **{metrics.official_funnel.get('monitor_brand_answer_count', 0)}** 条答案提到品牌，其中 **{metrics.official_funnel.get('official_link_answer_count', 0)}** 条答案引用官网，流量主要被 {top_source_names} 接走。",
                "先把价格对比、使用顾虑、核心差异和典型场景这几类页面改成结论页，而不是只放产品页。",
                "观察官网引用转化率和品牌相关链接数能不能先抬起来。",
            ]
        )
    if (metrics.competitor_pressure or 0) >= 0.3:
        recommendations.append(
            [
                "P1",
                "把比较题做成品牌主场",
                f"竞品挤压率已经到 **{_format_ratio(metrics.competitor_pressure)}**，说明比较问题里还有明显的替代风险。",
                f"先把核心竞品对比、关键差异和适合谁用写成一页式内容，让平台在横向比较时更容易先给出{bundle.meta.brand_name}的理由。",
                "观察竞品挤压率和比较类问题里的品牌可见度。",
            ]
        )
    display_negative_topics = _strip_false_negative_topics(metrics.top_negative_topics)
    if display_negative_topics:
        focus_topics = "、".join(row["display"] for row in display_negative_topics[:2])
        recommendations.append(
            [
                "P2",
                "先把反复出现的顾虑讲清楚",
                f"当前重复出现的顾虑集中在 {focus_topics}。",
                "先围绕这些问题补 FAQ 和短句结论，把真实限制、适用条件和边界说清楚，减少模型自己补出负面判断。",
                "观察品牌负面提及率，以及这些顾虑是否还在反复出现。",
            ]
        )
    if metrics.platform_judgments.get("best_comparison_answer_breakthrough"):
        target_platform = _platform_label(
            metrics.platform_judgments["best_comparison_answer_breakthrough"]
        )
        target_profile = metrics.platform_profiles.get(
            metrics.platform_judgments["best_comparison_answer_breakthrough"], {}
        )
        target_rate = _format_ratio(
            target_profile.get("comparison_answer_inclusion_rate")
        )
        if target_rate not in {"N/A", "0.0%"}:
            action_text = (
                f"{target_platform}在比较类问题里已经更愿意让{bundle.meta.brand_name}进入答案，当前比例是 **{target_rate}**。"
                "先把新内容投到这个平台最常见的比较问题里，再看调整有没有最快起效。"
            )
        else:
            action_text = (
                f"{target_platform}已经形成可复查的比较类样本，适合先拿来验证内容调整。"
                "先把新内容投到这个平台最常见的比较问题里，再看调整后品牌会不会更容易进入答案。"
            )
        recommendations.append(
            [
                "P2",
                "先在最容易起量的平台验证",
                action_text.split("先把", 1)[0].strip(),
                (
                    ("先把" + action_text.split("先把", 1)[1])
                    if "先把" in action_text
                    else action_text
                ),
                "观察该平台的比较类问题品牌可见度，再看官网引用转化率。",
            ]
        )
    if bundle.meta.report_kind == "scenario":
        comparison_line = None
        if comparison.comparable:
            no_brand_delta = comparison.visibility_delta.get("no_brand_rate")
            official_delta = comparison.citation_delta.get("official_conversion_rate")
            facts = []
            if isinstance(no_brand_delta, (int, float)):
                direction = "更高" if no_brand_delta >= 0 else "更低"
                facts.append(
                    f"这个场景里不提任何品牌的答案占比比全景基线{direction} **{_format_delta_points_cn(no_brand_delta)}**"
                )
            if isinstance(official_delta, (int, float)):
                direction = "更高" if official_delta >= 0 else "更低"
                facts.append(
                    f"官网引用转化率也比全景基线{direction} **{_format_delta_points_cn(official_delta)}**"
                )
            if facts:
                comparison_line = "，".join(facts)
        recommendations.append(
            [
                "P3",
                "把这个场景单独做成可引用内容",
                (
                    f"围绕{bundle.meta.scenario_theme or '当前场景'}，这批问题和全景基线相比，{comparison_line}。"
                    if comparison_line
                    else f"围绕{bundle.meta.scenario_theme or '当前场景'}，这批问题已经形成了稳定样本。"
                ),
                "把这个场景下反复出现的顾虑、比较点和使用条件整理成专题页、FAQ 和短结论。",
                "观察相对全景基线的无品牌率和官网引用转化率，还要看这几个场景问题里品牌会不会更容易被直接写进答案。",
            ]
        )
    subtitle = "优先做最容易改善品牌进入、官网承接和场景内容复用的动作。"
    action_blocks: list[str] = []
    for index, row in enumerate(recommendations[:4], start=1):
        _, title, fact_text, action_text, observe = row
        action_blocks.append(
            "\n".join(
                [
                    f"### 6.{index} {title}",
                    "",
                    f"- **事实**：{fact_text}",
                    f"- **动作**：{action_text}",
                    f"- **观察指标**：{observe}",
                ]
            )
        )
    markdown = "\n".join(
        [
            "## 6. 行动建议",
            "",
            *(
                action_blocks
                or [
                    "### 6.1 持续监测",
                    "",
                    "- **事实**：当前样本还不足以支持更细的动作拆分。",
                    "- **动作**：继续补样本，同时围绕当前主题整理一页式结论和 FAQ。",
                    "- **观察指标**：继续扩大样本并复核当前判断。",
                ]
            ),
        ]
    ).strip()
    return {
        "section_name": "recommendations",
        "title": "行动建议",
        "subtitle": subtitle,
        "markdown": markdown,
        "data": {"recommendations": recommendations[:4]},
    }


def _build_appendix_section(
    bundle: InputBundle, metrics: MetricBundle, analyzer_outputs: dict[str, Any]
) -> dict[str, Any]:
    question_rows = analyzer_outputs["question_coverage_mapper"]["question_rows"]
    citation_answers = analyzer_outputs["citation_analyzer"]["answers"]
    answer_lookup = {
        answer.answer_id: answer for answer in bundle.answers if answer.status == "ok"
    }
    high_risk_rows = [row for row in question_rows[:10] if row["risk_level"] == "high"][
        :4
    ]
    other_domain_notes = _collect_other_domain_notes(bundle)
    citation_sample_rows = [
        row
        for row in citation_answers
        if (row.get("brand_related_link_count") or 0) > 0
        or (row.get("official_link_count") or 0) > 0
    ][:4]
    markdown = "\n".join(
        [
            "## 7. 附录",
            "",
            "只保留最需要人工复核的样本，不把附录写成第二份正文。",
            "",
            "### 7.1 高风险问题样本",
            "",
            *(
                (
                    [
                        "\n".join(
                            [
                                f"{index}. 当前状态：{_state_label(row['answer_state'])}；平台：{_sample_platform_labels(row.get('present_platforms', []))}；负面信息：{('、'.join(_negative_topic_label(topic) for topic in row.get('negative_topics', []) if topic != 'other') or '暂不集中')}。",
                                _markdown_quote_block(
                                    _clean_report_text(
                                        row["question_text"], max_length=80
                                    )
                                ),
                            ]
                        )
                        for index, row in enumerate(high_risk_rows, start=1)
                    ]
                )
                or ["- 当前样本里暂无高风险问题。"]
            ),
            "",
            "### 7.2 暂时还没法准确定类的来源站点",
            "",
            *(
                (
                    [
                        f"- **{row['display_name']}（{row['domain']}）**：出现 {row['count']} 次；{row['reason']}"
                        for row in other_domain_notes
                    ]
                )
                or ["- 当前没有待继续归一的品牌相关来源站点。"]
            ),
            "",
            "### 7.3 品牌相关链接样本",
            "",
            *(
                (
                    [
                        "\n".join(
                            [
                                f"{index}. 平台：{_platform_label(str(row['platform']))}；品牌相关链接 {row['brand_related_link_count']} 个，其中官网链接 {row['official_link_count']} 个。",
                                _markdown_quote_block(
                                    _clean_report_text(
                                        (
                                            answer_lookup.get(
                                                row["answer_id"]
                                            ).question_text
                                            if answer_lookup.get(row["answer_id"])
                                            else "N/A"
                                        ),
                                        max_length=80,
                                    )
                                ),
                            ]
                        )
                        for index, row in enumerate(citation_sample_rows, start=1)
                    ]
                )
                or ["- 当前没有可复核的品牌相关链接样本。"]
            ),
        ]
    ).strip()
    return {
        "section_name": "appendix",
        "title": "附录",
        "subtitle": "保留必要样本，方便人工复核。",
        "markdown": markdown,
        "data": {
            "question_count": len(bundle.questions),
            "high_risk_scenario_count": metrics.high_risk_scenario_count,
        },
    }


def build_report_sections(
    *,
    bundle: InputBundle,
    metric_bundle: MetricBundle,
    comparison_bundle: ComparisonBundle,
    analyzer_outputs: dict[str, Any],
) -> list[dict[str, Any]]:
    visibility_data = _build_visibility_analyzer(bundle)
    header_section, _ = _build_header_markdown(bundle)
    return [
        header_section,
        _build_summary_section(bundle, metric_bundle, comparison_bundle),
        _build_visibility_section(
            bundle, metric_bundle, comparison_bundle, visibility_data
        ),
        _build_citation_section(bundle, metric_bundle),
        _build_question_section(bundle, metric_bundle, analyzer_outputs),
        _build_sentiment_section(bundle, metric_bundle),
        _build_platform_section(bundle, metric_bundle),
        _build_recommendation_section(
            bundle, metric_bundle, comparison_bundle, analyzer_outputs
        ),
        _build_appendix_section(bundle, metric_bundle, analyzer_outputs),
    ]


def build_full_markdown(*, sections: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        section["markdown"].strip() for section in sections if section.get("markdown")
    ).strip()


def build_home_v4_projection(
    *, bundle: InputBundle, metric_bundle: MetricBundle
) -> dict[str, Any]:
    def word_rows(rows: list[dict[str, Any]], sentiment: str) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for row in rows:
            text = str(
                row.get("display") or row.get("reason") or row.get("topic") or ""
            ).strip()
            if not text:
                continue
            output.append(
                {
                    "text": text,
                    "weight": (
                        row.get("rate")
                        if isinstance(row.get("rate"), (int, float))
                        else 0
                    ),
                    "sentiment": sentiment,
                    "count": int(row.get("count", 0) or 0),
                }
            )
        return output

    platform_rows: dict[str, dict[str, Any]] = {}
    platform_negative_topics: dict[str, Counter[str]] = defaultdict(Counter)
    for answer in bundle.answers:
        if answer.status != "ok":
            continue
        row = platform_rows.setdefault(
            answer.platform,
            {
                "platform": _platform_label(answer.platform),
                "status": "unknown",
                "answerCount": 0,
                "brandMentionCount": 0,
                "positiveCount": 0,
                "negativeCount": 0,
            },
        )
        row["answerCount"] += 1
        if answer.mentioned_monitor_brand:
            row["brandMentionCount"] += 1
            if answer.sentiment == "positive":
                row["positiveCount"] += 1
            elif answer.sentiment == "negative":
                row["negativeCount"] += 1
            for topic in answer.negative_topics:
                platform_negative_topics[answer.platform][topic] += 1

    for platform, row in platform_rows.items():
        if row["negativeCount"] > row["positiveCount"] and row["negativeCount"] > 0:
            row["status"] = "risk"
        elif row["brandMentionCount"] > 0:
            row["status"] = "good"
        elif row["answerCount"] > 0:
            row["status"] = "watch"
        if platform_negative_topics.get(platform):
            topic = platform_negative_topics[platform].most_common(1)[0][0]
            row["mainConcern"] = _negative_topic_label(topic)

    question_rows = [
        row
        for row in metric_bundle.question_diagnostics.get("question_rows", [])
        if isinstance(row, dict)
    ]
    risk_rows = [
        row
        for row in metric_bundle.question_diagnostics.get("risk_rows", [])
        if isinstance(row, dict)
    ]
    risks = [
        {
            "title": _clean_report_text(
                str(row.get("question_text") or row.get("scene") or ""), max_length=42
            ),
            "level": "high" if row.get("risk_level") == "high" else "medium",
            "platform": "、".join(
                _platform_label(str(platform))
                for platform in row.get("present_platforms", []) or []
                if platform
            ),
            "evidence": "、".join(
                _negative_topic_label(str(topic))
                for topic in row.get("negative_topics", []) or []
                if topic and str(topic) != "other"
            )
            or _state_label(str(row.get("answer_state") or "")),
        }
        for row in sorted(
            risk_rows,
            key=lambda item: (
                str(item.get("risk_level") or ""),
                str(item.get("question_text") or ""),
            ),
        )[:4]
        if row.get("question_text") or row.get("scene")
    ]

    advantage_candidates = [
        row
        for row in question_rows
        if row.get("brand_present")
        and str(row.get("risk_level") or "") in {"low", "medium"}
    ]
    advantage_candidates.sort(
        key=lambda row: (
            -len(row.get("present_platforms", []) or []),
            str(row.get("question_text") or ""),
        )
    )
    advantages = [
        {
            "title": _clean_report_text(
                str(row.get("question_text") or row.get("scene") or ""), max_length=42
            ),
            "platformCount": len(row.get("present_platforms", []) or []),
            "evidence": "、".join(
                _platform_label(str(platform))
                for platform in row.get("present_platforms", []) or []
                if platform
            ),
        }
        for row in advantage_candidates[:4]
        if row.get("question_text") or row.get("scene")
    ]

    answer_sample_count = (
        metric_bundle.successful_answers or metric_bundle.total_answers
    )
    mention_ranking = [
        {
            "rank": int(row.get("rank", 0) or 0),
            "brand": str(row.get("brand") or ""),
            "mentionRate": safe_ratio(
                int(row.get("brand_presence_count", 0) or 0), answer_sample_count
            ),
            "mentionCount": int(row.get("brand_presence_count", 0) or 0),
            "isCurrentBrand": str(row.get("brand") or "")
            == bundle.brand_master.monitor_brand,
        }
        for row in metric_bundle.top_brand_ranking[:10]
        if isinstance(row, dict) and row.get("brand")
    ]

    source_type_breakdown = metric_bundle.source_summary.get(
        "source_type_breakdown", {}
    )
    source_types = (
        [
            {
                "key": key,
                "label": _source_type_label(key),
                "share": value,
            }
            for key, value in source_type_breakdown.items()
            if isinstance(value, (int, float)) and value > 0
        ]
        if isinstance(source_type_breakdown, dict)
        else []
    )
    source_types.sort(key=lambda item: (-(item["share"] or 0), item["label"]))

    top_domains = [
        {
            "domain": str(row.get("domain") or ""),
            "displayName": str(
                row.get("display_name")
                or row.get("site_name")
                or row.get("domain")
                or ""
            ),
            "count": int(row.get("count", 0) or 0),
            "share": (
                row.get("share") if isinstance(row.get("share"), (int, float)) else None
            ),
            "isOfficial": bool(row.get("is_official", False)),
            "sourceType": str(row.get("source_type") or "other"),
            "sourceTypeLabel": _source_type_label(
                str(row.get("source_type") or "other")
            ),
            "siteCategory": str(row.get("site_category") or ""),
        }
        for row in metric_bundle.source_summary.get("top_domains", []) or []
        if isinstance(row, dict) and row.get("domain")
    ][:8]

    return {
        "wordCloud": {
            "positive": word_rows(metric_bundle.top_positive_reasons, "positive"),
            "negative": word_rows(metric_bundle.top_negative_topics, "negative"),
        },
        "platformDiagnosis": sorted(
            platform_rows.values(),
            key=lambda row: (
                row["status"] == "risk",
                row["brandMentionCount"],
                row["platform"],
            ),
            reverse=True,
        ),
        "risks": risks,
        "advantages": advantages,
        "mentionRanking": mention_ranking,
        "sourceStructure": {
            "officialConversionRate": metric_bundle.official_conversion_rate,
            "sourceTypes": source_types,
            "topDomains": top_domains,
        },
    }


def build_dashboard_projection(
    *,
    bundle: InputBundle,
    metric_bundle: MetricBundle,
    comparison_bundle: ComparisonBundle,
    sections: list[dict[str, Any]],
) -> dict[str, Any]:
    section_map = {section["section_name"]: section.get("data") for section in sections}
    return {
        "report_kind": bundle.meta.report_kind,
        "home_v4": build_home_v4_projection(bundle=bundle, metric_bundle=metric_bundle),
        "boards": {
            "visibility": section_map.get("visibility"),
            "citation_visibility": section_map.get("citation_visibility"),
            "question_diagnostics": section_map.get("question_diagnostics"),
            "sentiment_risk": section_map.get("sentiment_risk"),
            "platform_profile": section_map.get("platform_preference"),
            "scenario_delta": (
                comparison_bundle.model_dump()
                if bundle.meta.report_kind == "scenario"
                else None
            ),
            "recommendations": section_map.get("recommendations"),
        },
        "headline_metrics": {
            "brand_visibility": metric_bundle.brand_visibility,
            "brand_rank": metric_bundle.brand_rank,
            "competitor_pressure": metric_bundle.competitor_pressure,
            "negative_rate": metric_bundle.negative_rate,
            "official_conversion_rate": metric_bundle.official_conversion_rate,
        },
    }


def build_canonical_report_artifact(
    *,
    session_id: str,
    entity_id: str | None,
    analysis_mode: str,
    brand_profile: dict[str, Any],
    competitors: list[dict[str, Any]],
    fetch_results: list[dict[str, Any]],
    simulated_questions: list[dict[str, Any]] | dict[str, Any] | None,
    base_metrics: dict[str, Any] | None,
    baseline_report: dict[str, Any] | None = None,
    baseline_report_id: str | None = None,
) -> dict[str, Any]:
    resolved_baseline_report_id = (
        str(
            baseline_report_id
            or (baseline_report or {}).get("artifact_id")
            or (baseline_report or {}).get("report_id")
            or ""
        ).strip()
        or None
    )
    bundle = build_input_bundle(
        session_id=session_id,
        entity_id=entity_id,
        analysis_mode=analysis_mode,
        brand_profile=brand_profile,
        competitors=competitors,
        fetch_results=fetch_results,
        simulated_questions=simulated_questions,
        baseline_report_id=resolved_baseline_report_id,
    )
    analyzer_outputs, metric_bundle = build_metric_bundle(
        bundle, base_metrics=base_metrics
    )
    comparison_bundle = build_comparison_bundle(
        bundle=bundle, metric_bundle=metric_bundle, baseline_report=baseline_report
    )
    analyzer_outputs["comparison_engine"] = comparison_bundle.model_dump()

    metric_bundle_payload = metric_bundle.model_dump()
    input_bundle_payload = bundle.model_dump()
    data_audit = build_data_audit(metric_bundle_payload)
    report_route = build_report_route(data_audit, report_kind=bundle.meta.report_kind)
    scenario_diagnostics = build_scenario_diagnostics(
        input_bundle_payload, analyzer_outputs
    )
    source_intelligence = build_source_intelligence(
        metric_bundle_payload,
        competitors=competitors,
    )
    risk_concern_analysis = build_risk_concern_analysis(
        metric_bundle_payload,
        analyzer_outputs,
    )
    action_recommendations = build_action_recommendations(
        data_audit=data_audit,
        scenario_diagnostics=scenario_diagnostics,
        source_intelligence=source_intelligence,
        risk_concern_analysis=risk_concern_analysis,
        metric_bundle=metric_bundle_payload,
        brand_name=bundle.meta.brand_name,
    )

    structured_report = build_structured_report(
        brand_name=bundle.meta.brand_name,
        report_kind=bundle.meta.report_kind,
        metric_bundle=metric_bundle_payload,
        data_audit=data_audit,
        report_route=report_route,
        scenario_diagnostics=scenario_diagnostics,
        source_intelligence=source_intelligence,
        risk_concern_analysis=risk_concern_analysis,
        action_recommendations=action_recommendations,
    )
    sections = build_report_sections(
        bundle=bundle,
        metric_bundle=metric_bundle,
        comparison_bundle=comparison_bundle,
        analyzer_outputs=analyzer_outputs,
    )
    full_markdown = structured_report["report_markdown"]
    executive_summary = structured_report["executive_summary"]
    executive_summary_text = str(
        executive_summary.get("one_line_judgment")
        if isinstance(executive_summary, dict)
        else ""
    ).strip()
    operations_diagnosis = structured_report["operations_diagnosis"]
    diagnostic_conclusions = structured_report["diagnostic_conclusions"]
    report_sections = structured_report["report_sections"]
    title = f"{bundle.meta.brand_name}｜{report_route.get('title') or '品牌 AI 答案诊断报告'}"
    insight_candidates = [
        item.get("action") or item.get("fact")
        for item in diagnostic_conclusions
        if isinstance(item, dict)
    ]

    dashboard_projection = build_dashboard_projection(
        bundle=bundle,
        metric_bundle=metric_bundle,
        comparison_bundle=comparison_bundle,
        sections=sections,
    )
    artifact = {
        "artifact_kind": "geo_report",
        "report_kind": bundle.meta.report_kind,
        "report_mode": data_audit.get("report_mode"),
        "title": title,
        "headline": title,
        "subtitle": executive_summary_text,
        "brand_name": bundle.meta.brand_name,
        "meta": bundle.meta.model_dump(),
        "input_bundle": input_bundle_payload,
        "skill_outputs": analyzer_outputs,
        "metric_bundle": metric_bundle_payload,
        "comparison_bundle": comparison_bundle.model_dump(),
        "data_audit": data_audit,
        "report_route": report_route,
        "scenario_diagnostics": scenario_diagnostics,
        "source_intelligence": source_intelligence,
        "risk_concern_analysis": risk_concern_analysis,
        "action_recommendations": action_recommendations,
        "diagnostic_conclusions": diagnostic_conclusions,
        "insight_candidates": insight_candidates,
        "sections": sections,
        "report_sections": report_sections,
        "full_markdown": full_markdown,
        "report_markdown": full_markdown,
        "dashboard_projection": dashboard_projection,
        "executive_report": executive_summary,
        "executive_summary": executive_summary,
        "executive_summary_text": executive_summary_text,
        "operations_diagnosis": operations_diagnosis,
        "key_findings": diagnostic_conclusions,
        "metrics": {
            "brand_visibility": metric_bundle.brand_visibility,
            "brand_rank": metric_bundle.brand_rank,
            "competitor_pressure": metric_bundle.competitor_pressure,
            "negative_rate": metric_bundle.negative_rate,
            "official_conversion_rate": metric_bundle.official_conversion_rate,
            "total_questions": metric_bundle.total_questions,
            "total_answers": metric_bundle.successful_answers,
        },
        "metrics_raw": base_metrics or {},
    }
    artifact["diagnosis_modules"] = extract_geo_report_diagnosis(artifact)
    initial_validator_result = validate_report_artifact(artifact)
    if not initial_validator_result["pass"]:
        artifact = repair_report_artifact(artifact)
    validator_result = validate_report_artifact(artifact)
    artifact["validator_result"] = validator_result
    if not initial_validator_result["pass"]:
        artifact["validator_result"]["initial_issues"] = initial_validator_result[
            "issues"
        ]
    if not validator_result["pass"]:
        raise ValueError(
            f"A5 report validation failed: {validator_result['required_fixes']}"
        )
    return artifact
