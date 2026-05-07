"""Decision-diagnosis helpers for A5 GEO reports.

This module keeps the new diagnosis architecture deterministic and fast.  It
does not call an LLM; it builds structured diagnosis modules that the report
assembler can consume.
"""

from __future__ import annotations

import copy
import json
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse


REPORT_MODE_NO_SIGNAL = "NO_SIGNAL"
REPORT_MODE_WEAK_SIGNAL = "WEAK_SIGNAL"
REPORT_MODE_BRAND_ENTRY = "BRAND_ENTRY"
REPORT_MODE_FULL_LANDSCAPE = "FULL_LANDSCAPE"

_A5_DIR = Path(__file__).resolve().parent
_REQUIRED_CONCLUSION_FIELDS = ("fact", "detail")

PLATFORM_LABELS = {
    "deepseek": "DeepSeek",
    "kimi": "Kimi",
    "doubao": "豆包",
    "yuanbao": "元宝",
    "chatgpt": "ChatGPT",
    "gpt": "ChatGPT",
}

SOURCE_PREFERENCE_LABELS = {
    "official": "官网/官方文档/白皮书",
    "authority_media": "官媒/权威机构",
    "vertical_media": "行业媒体",
    "community": "社区/论坛/问答",
    "video_or_content": "视频/内容平台",
    "other": "其他",
}

BRAND_STATUS_LABELS = {
    "target_only": "只提监测品牌",
    "target_with_competitors": "品牌与竞品同台",
    "competitor_only": "只提竞品",
    "no_brand": "不提品牌",
    "monitor_only": "只提监测品牌",
    "monitor_plus_others": "品牌与竞品同台",
}

REPORT_MODE_LABELS = {
    REPORT_MODE_NO_SIGNAL: "品牌未进入",
    REPORT_MODE_WEAK_SIGNAL: "弱信号观察",
    REPORT_MODE_BRAND_ENTRY: "品牌已进入",
    REPORT_MODE_FULL_LANDSCAPE: "完整全景诊断",
}

JOURNEY_STAGE_LABELS = {
    "awareness": "认知/趋势心智",
    "understanding": "理解/知识查询",
    "supplier_evaluation": "供应商/选项评估",
    "purchase_evaluation": "购买/选型决策",
    "value_validation": "价值验证",
    "fit_evaluation": "适配评估",
    "risk_validation": "风险验证",
    "trust_validation": "信任验证",
    "scenario_solution": "场景解决方案",
}

BUSINESS_VALUE_LABELS = {
    "high": "高",
    "medium": "中",
    "low": "低",
}

BLOCKED_NO_SIGNAL_SECTIONS = [
    "sentiment_risk",
    "official_conversion",
    "platform_preference",
    "brand_reputation",
]

JUDGMENT_TOPIC_ALIASES = {
    "sentiment": {"sentiment", "sentiment_risk", "情感", "负向率", "品牌负向提及率"},
    "official_conversion": {
        "official_conversion",
        "official_conversion_rate",
        "official_site",
        "official_funnel",
        "官网承接",
        "官网引用转化率",
    },
    "platform_preference": {
        "platform_preference",
        "strong_platform_preference",
        "platform",
        "平台偏好",
    },
    "brand_reputation": {
        "brand_reputation",
        "stable_reputation",
        "reputation",
        "品牌口碑",
        "稳定口碑",
    },
}

NO_SIGNAL_NOT_JUDGED = [
    {
        "code": "sentiment",
        "label": "情感",
        "reason": "本轮没有品牌提及样本，无法判断品牌正负面情绪。",
    },
    {
        "code": "official_conversion",
        "label": "官网承接",
        "reason": "本轮没有品牌提及样本，无法计算官网引用转化率。",
    },
    {
        "code": "platform_preference",
        "label": "平台偏好",
        "reason": "品牌尚未进入答案，平台差异只能作为下一轮采样方向。",
    },
    {
        "code": "brand_reputation",
        "label": "品牌口碑",
        "reason": "当前样本不能代表品牌口碑，只能说明品牌尚未进入本轮 AI 答案。",
    },
]


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_rate(numerator: int | float, denominator: int | float) -> float | None:
    if not denominator:
        return None
    try:
        return round(float(numerator) / float(denominator), 4)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _format_rate(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "暂无足够数据支撑"
    return f"{float(value) * 100:.1f}%"


def _clip(text: Any, limit: int = 48) -> str:
    cleaned = " ".join(str(text or "").replace("|", " ").split()).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "..."


def _text_or_pending(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.upper() == "N/A" or text.lower() == "none":
        return "暂无足够数据支撑"
    return text


def _platform_label(platform: Any) -> str:
    code = str(platform or "").strip()
    return PLATFORM_LABELS.get(code.lower(), code or "未知平台")


def _join_detail_parts(parts: list[str]) -> str:
    cleaned = [part.strip(" ；。") for part in parts if str(part or "").strip()]
    if not cleaned:
        return "暂无足够样本展开。"
    return "；".join(cleaned) + "。"


def _estimated_count_from_rate(value: Any, total: int) -> int | None:
    if not isinstance(value, (int, float)) or total <= 0:
        return None
    return int(round(float(value) * total))


def _brand_answer_samples(
    metric_bundle: dict[str, Any], *, limit: int = 3
) -> list[dict[str, Any]]:
    sentiment_risk = (
        metric_bundle.get("sentiment_risk")
        if isinstance(metric_bundle.get("sentiment_risk"), dict)
        else {}
    )
    samples: list[dict[str, Any]] = []
    for item in sentiment_risk.get("items", []) or []:
        if not isinstance(item, dict):
            continue
        if not (item.get("question_text") or item.get("answer_excerpt")):
            continue
        samples.append(item)
        if len(samples) >= limit:
            break
    return samples


def _format_answer_sample_detail(sample: dict[str, Any]) -> str:
    question = _clip(sample.get("question_text"), 72)
    platform = _platform_label(sample.get("platform"))
    excerpt = _clip(sample.get("answer_excerpt"), 96)
    parts = []
    if question:
        parts.append(f"问题「{question}」")
    if platform:
        parts.append(f"提及品牌的答案来自于{platform}")
    if excerpt:
        parts.append(f"相关答案是「{excerpt}」")
    return "，".join(parts)


def _brand_answer_detail(
    metric_bundle: dict[str, Any],
    *,
    brand_presence_count: int,
    successful_answers: int,
) -> str:
    samples = _brand_answer_samples(metric_bundle)
    if samples:
        sample_text = "；".join(
            _format_answer_sample_detail(sample) for sample in samples
        )
        return f"品牌提及样本：{sample_text}。"
    if brand_presence_count > 0:
        return (
            f"结构化指标记录到 {brand_presence_count} 条品牌提及；"
            "当前样本字段未保留可展示的答案摘录。"
        )
    return f"本轮 {successful_answers} 条有效答案里没有监测品牌提及样本。"


def _brand_entry_detail(
    metric_bundle: dict[str, Any],
    *,
    brand_presence_count: int,
    successful_answers: int,
) -> str:
    competitor_count = _estimated_count_from_rate(
        metric_bundle.get("competitor_pressure"), successful_answers
    )
    no_brand_count = _estimated_count_from_rate(
        metric_bundle.get("no_brand_rate"), successful_answers
    )
    monitor_only_count = _estimated_count_from_rate(
        metric_bundle.get("monitor_only_rate"), successful_answers
    )
    co_presence_count = _estimated_count_from_rate(
        metric_bundle.get("monitor_plus_others_rate"), successful_answers
    )
    parts = [f"品牌提及答案 {brand_presence_count} 条"]
    if monitor_only_count is not None:
        parts.append(f"只提监测品牌约 {monitor_only_count} 条")
    if co_presence_count is not None:
        parts.append(f"品牌与竞品同台约 {co_presence_count} 条")
    if competitor_count is not None:
        parts.append(f"只提竞品约 {competitor_count} 条")
    if no_brand_count is not None:
        parts.append(f"不提品牌约 {no_brand_count} 条")
    return _join_detail_parts(parts)


def _scenario_conclusion_detail(item: dict[str, Any], *, brand_name: str) -> str:
    status = str(item.get("brand_status") or "")
    competitors = "、".join(
        str(value) for value in item.get("competitors_present", []) if value
    )
    parts = []
    if item.get("question_text"):
        parts.append(f"代表问题「{_clip(item.get('question_text'), 88)}」")
    if competitors:
        parts.append(f"答案中出现竞品：{competitors}")
    if status == "competitor_only":
        parts.append(f"{brand_name}未出现在该问题答案中")
    elif status == "no_brand":
        parts.append("该问题答案没有进入品牌推荐结构")
    elif status == "target_with_competitors":
        parts.append(f"{brand_name}与竞品同时出现")
    elif status == "target_only":
        parts.append(f"{brand_name}单独出现")
    if item.get("content_gap"):
        parts.append(f"可补充信息：{item.get('content_gap')}")
    return _join_detail_parts(parts)


def _source_conclusion_detail(
    top_source: dict[str, Any], source_domains: list[dict[str, Any]]
) -> str:
    label = str(top_source.get("source_type_label") or "来源").strip()
    parts = [
        (
            f"来源类型「{label}」出现 {top_source.get('ai_citation_frequency')} 次，"
            f"占比 {_format_rate(top_source.get('citation_share'))}"
        )
    ]
    matched_domains = [
        item
        for item in source_domains
        if str(item.get("source_type_label") or "") == label
    ][:2] or source_domains[:2]
    domain_parts = []
    for item in matched_domains:
        site = item.get("site_display") or item.get("domain") or "未知来源"
        titles = "；".join(
            f"「{title}」" for title in item.get("sample_titles", [])[:2] if title
        )
        title_text = f"，样本标题：{titles}" if titles else ""
        domain_parts.append(
            f"{site}出现 {item.get('ai_citation_frequency')} 次{title_text}"
        )
    if domain_parts:
        parts.append(f"代表来源：{'；'.join(domain_parts)}")
    return _join_detail_parts(parts)


def _risk_conclusion_detail(item: dict[str, Any]) -> str:
    evidence = "；".join(
        f"「{_clip(sample, 72)}」" for sample in item.get("evidence", [])[:2] if sample
    )
    platform_counts = item.get("platform_counts", {}) or {}
    platforms = "、".join(
        f"{_platform_label(platform)} {count} 次"
        for platform, count in platform_counts.items()
        if count
    )
    parts = [
        f"{item.get('label')}出现 {item.get('count')} 次，占比 {_format_rate(item.get('share'))}"
    ]
    if platforms:
        parts.append(f"平台分布：{platforms}")
    if evidence:
        parts.append(f"样本证据：{evidence}")
    return _join_detail_parts(parts)


def _action_conclusion_detail(action: dict[str, Any]) -> str:
    metrics = "、".join(
        str(value) for value in action.get("target_metric", []) if value
    )
    parts = []
    if action.get("decision_scenario"):
        parts.append(f"对应场景：{action.get('decision_scenario')}")
    if action.get("recommended_asset"):
        parts.append(f"推荐资产：{action.get('recommended_asset')}")
    if metrics:
        parts.append(f"观察指标：{metrics}")
    if action.get("validation_plan"):
        parts.append(f"复测方式：{action.get('validation_plan')}")
    return _join_detail_parts(parts)


def _legacy_conclusion_detail(item: dict[str, Any]) -> str:
    return _join_detail_parts(
        [
            str(item.get("interpretation") or ""),
            str(item.get("boundary") or ""),
            str(item.get("action") or ""),
        ]
    )


def _brand_status_label(status: Any) -> str:
    text = str(status or "").strip()
    return BRAND_STATUS_LABELS.get(text, text or "需复核")


def _report_mode_label(mode: Any) -> str:
    text = str(mode or "").strip()
    return REPORT_MODE_LABELS.get(text, text or "需复核")


def _journey_stage_label(stage: Any) -> str:
    text = str(stage or "").strip()
    return JOURNEY_STAGE_LABELS.get(text, text or "需复核")


def _business_value_label(value: Any) -> str:
    text = str(value or "").strip()
    return BUSINESS_VALUE_LABELS.get(text, text or "需复核")


def _is_generic_label(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text in {"", "其他", "other", "通用问题", "未知", "暂无足够数据支撑"}


def _unique_values(values: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _format_site_name(domain: Any, site_name: Any) -> str:
    domain_text = str(domain or "").strip()
    site_text = str(site_name or "").strip()
    if site_text and domain_text and site_text != domain_text:
        return f"{site_text}（{domain_text}）"
    return site_text or domain_text or "未知站点"


def _competitor_site_name(domain: str, competitors: list[dict[str, Any]]) -> str:
    domain_text = _normalize_domain(domain)
    if not domain_text:
        return ""
    for competitor in competitors:
        if not isinstance(competitor, dict):
            continue
        competitor_domain = _normalize_domain(
            competitor.get("website")
            or competitor.get("official_website")
            or competitor.get("url")
        )
        if not competitor_domain:
            continue
        if domain_text == competitor_domain or domain_text.endswith(
            f".{competitor_domain}"
        ):
            return str(competitor.get("name") or "").strip()
    return ""


def _normalize_domain(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    parsed = urlparse(text if "://" in text else f"https://{text}")
    host = (parsed.netloc or parsed.path).split("/")[0].lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _read_json_config(filename: str) -> dict[str, Any]:
    path = _A5_DIR / filename
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


@lru_cache(maxsize=1)
def load_scenario_taxonomy() -> dict[str, Any]:
    return _read_json_config("scenario_taxonomy.json")


def _contains_any_token(text: str, tokens: list[Any]) -> bool:
    return any(str(token or "") and str(token) in text for token in tokens)


def _canonical_judgment_topic(topic: Any) -> str:
    normalized = str(topic or "").strip().lower()
    for canonical, aliases in JUDGMENT_TOPIC_ALIASES.items():
        if normalized == canonical:
            return canonical
        if any(normalized == str(alias).strip().lower() for alias in aliases):
            return canonical
    return normalized


def build_data_audit(metric_bundle: dict[str, Any]) -> dict[str, Any]:
    """Build the report-mode audit from existing metric_bundle fields."""
    brand_presence_count = _as_int(metric_bundle.get("brand_presence_count"))
    successful_answers = _as_int(metric_bundle.get("successful_answers"))
    official_funnel = (
        metric_bundle.get("official_funnel")
        if isinstance(metric_bundle.get("official_funnel"), dict)
        else {}
    )
    monitor_brand_answer_count = _as_int(
        official_funnel.get("monitor_brand_answer_count")
    )
    platform_profiles = (
        metric_bundle.get("platform_profiles")
        if isinstance(metric_bundle.get("platform_profiles"), dict)
        else {}
    )
    ok_platform_count = sum(
        1
        for profile in platform_profiles.values()
        if isinstance(profile, dict) and profile.get("data_status") == "ok"
    )

    if brand_presence_count <= 0:
        report_mode = REPORT_MODE_NO_SIGNAL
        confidence = "low"
        allowed_sections = [
            "executive_summary",
            "no_signal_diagnosis",
            "action_recommendations",
            "appendix",
        ]
        blocked_sections = list(BLOCKED_NO_SIGNAL_SECTIONS)
        not_judged = list(NO_SIGNAL_NOT_JUDGED)
        reasons = [
            "brand_presence_count 为 0，品牌尚未进入本轮 AI 答案。",
            "官网承接、情感和平台偏好没有有效分母。",
        ]
    elif brand_presence_count < 5:
        report_mode = REPORT_MODE_WEAK_SIGNAL
        confidence = "low"
        allowed_sections = [
            "executive_summary",
            "visibility",
            "scenario_diagnostics",
            "source_intelligence",
            "risk_concerns",
            "action_recommendations",
            "appendix",
        ]
        blocked_sections = ["strong_platform_preference", "stable_reputation_claim"]
        not_judged = [
            {
                "code": "stable_reputation",
                "label": "稳定口碑",
                "reason": "品牌提及样本不足 5 条，只能作为弱信号观察。",
            }
        ]
        reasons = ["品牌已有少量提及，但样本不足以支撑强结论。"]
    elif brand_presence_count >= 10 and successful_answers >= 30:
        report_mode = REPORT_MODE_FULL_LANDSCAPE
        confidence = "high"
        allowed_sections = [
            "executive_summary",
            "visibility",
            "scenario_diagnostics",
            "source_intelligence",
            "risk_concerns",
            "platform_preference",
            "action_recommendations",
            "appendix",
        ]
        blocked_sections = []
        not_judged = []
        reasons = ["品牌提及和答案样本达到完整诊断阈值。"]
    else:
        report_mode = REPORT_MODE_BRAND_ENTRY
        confidence = "medium"
        allowed_sections = [
            "executive_summary",
            "visibility",
            "scenario_diagnostics",
            "source_intelligence",
            "risk_concerns",
            "action_recommendations",
            "appendix",
        ]
        blocked_sections = ["strong_platform_preference"]
        not_judged = []
        reasons = ["品牌已经进入部分答案，适合做品牌进入诊断。"]

    if monitor_brand_answer_count <= 0:
        metric_official = {
            "judgeable": False,
            "reason": "没有品牌提及答案，官网引用转化率没有有效分母。",
        }
    else:
        metric_official = {"judgeable": True, "reason": "存在品牌提及答案。"}

    metric_eligibility = {
        "brand_visibility": {
            "judgeable": successful_answers > 0,
            "reason": (
                "有有效答案样本。" if successful_answers > 0 else "没有有效答案样本。"
            ),
        },
        "brand_rank": {
            "judgeable": brand_presence_count > 0,
            "reason": (
                "品牌已被提及。" if brand_presence_count > 0 else "品牌未被提及。"
            ),
        },
        "official_conversion": metric_official,
        "risk_concerns": {
            "judgeable": brand_presence_count > 0,
            "reason": (
                "存在品牌提及答案。"
                if brand_presence_count > 0
                else "品牌未被提及，不能判断品牌顾虑。"
            ),
        },
        "platform_preference": {
            "judgeable": ok_platform_count >= 2 and successful_answers >= 10,
            "reason": (
                "至少两个平台有有效样本。"
                if ok_platform_count >= 2 and successful_answers >= 10
                else "平台样本不足，不做稳定平台偏好判断。"
            ),
        },
    }

    return {
        "report_mode": report_mode,
        "confidence": confidence,
        "allowed_sections": allowed_sections,
        "blocked_sections": blocked_sections,
        "not_judged": not_judged,
        "reasons": reasons,
        "metric_eligibility": metric_eligibility,
    }


def build_report_route(
    data_audit: dict[str, Any],
    *,
    report_kind: str,
) -> dict[str, Any]:
    mode = str(data_audit.get("report_mode") or REPORT_MODE_BRAND_ENTRY)
    mode_titles = {
        REPORT_MODE_NO_SIGNAL: "品牌 AI 答案未进入诊断报告",
        REPORT_MODE_WEAK_SIGNAL: "品牌 AI 答案弱信号观察报告",
        REPORT_MODE_BRAND_ENTRY: "品牌 AI 答案进入诊断报告",
        REPORT_MODE_FULL_LANDSCAPE: "品牌 GEO 全景诊断报告",
    }
    operations_sections = (
        [
            "本轮结论",
            "问题触发类型",
            "竞品偶发进入",
            "内容缺口假设",
            "下一轮验证计划",
            "暂不判断事项",
        ]
        if mode == REPORT_MODE_NO_SIGNAL
        else [
            "数据状态",
            "品牌进入能力",
            "场景地图",
            "来源证据权",
            "风险顾虑",
            "行动建议",
            "复测计划",
            "样本附录",
        ]
    )
    return {
        "report_mode": mode,
        "report_kind": report_kind,
        "title": mode_titles.get(mode, mode_titles[REPORT_MODE_BRAND_ENTRY]),
        "operations_sections": operations_sections,
        "blocked_sections": data_audit.get("blocked_sections", []),
        "allowed_sections": data_audit.get("allowed_sections", []),
    }


def _detect_management_scenario(text: str) -> tuple[str, str, str] | None:
    lowered = text.lower()
    if any(token in text for token in ("麦肯锡", "贝恩", "BCG", "波士顿咨询")):
        return "顶级咨询公司比较", "supplier_evaluation", "high"
    if any(token in text for token in ("数字化转型", "埃森哲", "技术落地", "系统实施")):
        return "数字化转型咨询选型", "supplier_evaluation", "high"
    if any(token in text for token in ("制造业", "降本增效", "运营优化", "ROI")):
        return "制造业降本增效", "value_validation", "high"
    if any(token in text for token in ("中型企业", "组织架构", "预算有限")):
        return "中型企业组织调整", "fit_evaluation", "medium"
    if any(token in text for token in ("并购尽调", "尽调")):
        return "并购尽调", "supplier_evaluation", "high"
    if "pmi" in lowered or "并购后" in text or "整合咨询" in text:
        return "PMI 并购整合", "risk_validation", "high"
    if "esg" in lowered or "可持续发展" in text:
        return "ESG 可持续发展", "awareness", "medium"
    if any(
        token in text for token in ("经济下行", "管理咨询行业", "愿意为哪类咨询买单")
    ):
        return "经济下行周期", "awareness", "medium"
    return None


def _detect_supplement_scenario(text: str) -> tuple[str, str, str] | None:
    lowered = text.lower()
    if "老人" in text or "老年" in text or "蛋白粉" in text:
        return "老人营养", "purchase_evaluation", "high"
    if "儿童" in text or "小孩子" in text or "维生素" in text:
        return "儿童营养", "risk_validation", "high"
    if any(token in text for token in ("天然维", "合成维", "成分", "植物提取")):
        return "成分对比", "value_validation", "medium"
    if "蓝帽子" in text or "海外代购" in text or "安全" in text:
        return "安全合规", "trust_validation", "high"
    if "熬夜" in text or "疲劳" in text or "护肝" in text or "b 族" in lowered:
        return "疲劳熬夜", "scenario_solution", "medium"
    if "直销" in text or "药店品牌" in text:
        return "直销信任", "trust_validation", "high"
    if "500" in text or "预算" in text or "送爸妈" in text:
        return "预算选择", "purchase_evaluation", "medium"
    return None


def _detect_configured_scenario(
    industry: str, text: str
) -> tuple[str, str, str] | None:
    taxonomy = load_scenario_taxonomy()
    industries = taxonomy.get("industries", []) if isinstance(taxonomy, dict) else []
    for industry_item in industries:
        if not isinstance(industry_item, dict):
            continue
        industry_keywords = industry_item.get("industry_keywords", []) or []
        industry_match = _contains_any_token(industry, industry_keywords)
        scenarios = industry_item.get("scenarios", []) or []
        for scenario in scenarios:
            if not isinstance(scenario, dict):
                continue
            keywords = scenario.get("keywords", []) or []
            if not _contains_any_token(text, keywords):
                continue
            if not industry_match and not _contains_any_token(text, industry_keywords):
                continue
            return (
                str(scenario.get("decision_scenario") or "通用问题"),
                str(scenario.get("journey_stage") or "understanding"),
                str(scenario.get("business_value") or "low"),
            )
    return None


def _fallback_scenario(text: str, intent: str, scene: str) -> tuple[str, str, str]:
    if "趋势" in intent or "趋势" in scene:
        return "趋势议题心智", "awareness", "medium"
    if "对比" in intent or "比较" in intent:
        return "选项对比", "supplier_evaluation", "medium"
    if "怎么选" in intent or "推荐" in intent:
        return "购买/选型决策", "purchase_evaluation", "medium"
    if "风险" in intent or "顾虑" in intent:
        return "风险验证", "risk_validation", "medium"
    return scene or "通用问题", "understanding", "low"


def _brand_status(answer_state: str) -> str:
    return {
        "no_brand": "no_brand",
        "competitor_only": "competitor_only",
        "monitor_only": "target_only",
        "monitor_plus_others": "target_with_competitors",
    }.get(answer_state, "unknown")


def _content_gap_for_scenario(scenario: str) -> tuple[str, str]:
    taxonomy = load_scenario_taxonomy()
    for industry_item in taxonomy.get("industries", []) or []:
        if not isinstance(industry_item, dict):
            continue
        for item in industry_item.get("scenarios", []) or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("decision_scenario") or "") == scenario:
                return (
                    str(
                        item.get("content_gap") or "缺少面向该决策场景的可引用结论页。"
                    ),
                    str(item.get("recommended_asset") or f"{scenario}场景的权威解释页"),
                )
    mapping = {
        "数字化转型咨询选型": (
            "缺少战略咨询与系统实施分工的权威解释。",
            "数字化转型中，战略咨询公司与系统实施商如何分工",
        ),
        "PMI 并购整合": (
            "缺少并购后整合工作内容和风险边界的可引用说明。",
            "并购后整合 PMI 包含哪些关键工作",
        ),
        "ESG 可持续发展": (
            "缺少 ESG 咨询实用性、边界和案例证据。",
            "ESG 咨询什么时候实用，什么时候只是报告工作",
        ),
        "制造业降本增效": (
            "缺少运营优化 ROI 衡量口径和案例证据。",
            "制造业运营优化项目如何衡量 ROI",
        ),
        "老人营养": (
            "缺少老年人适用人群、肠胃耐受和成分边界说明。",
            "老年人蛋白粉怎么选：适用人群、成分和注意事项",
        ),
        "儿童营养": (
            "缺少儿童长期使用、安全性和是否必要的解释。",
            "儿童维生素是否必要：适用条件和安全边界",
        ),
        "安全合规": (
            "缺少蓝帽子、渠道和合规证据的集中说明。",
            "保健品蓝帽子和海外代购安全性说明",
        ),
        "预算选择": (
            "缺少价格理由、购买优先级和预算分层建议。",
            "不同预算下给父母买营养品的选择建议",
        ),
    }
    return mapping.get(
        scenario,
        ("缺少面向该决策场景的可引用结论页。", f"{scenario}场景的权威解释页"),
    )


def build_scenario_diagnostics(
    input_bundle: dict[str, Any],
    analyzer_outputs: dict[str, Any],
) -> dict[str, Any]:
    questions = {
        str(item.get("question_id") or ""): item
        for item in input_bundle.get("questions", []) or []
        if isinstance(item, dict)
    }
    meta = (
        input_bundle.get("meta", {})
        if isinstance(input_bundle.get("meta"), dict)
        else {}
    )
    industry = str(meta.get("industry") or "")
    question_rows = (
        analyzer_outputs.get("question_coverage_mapper", {}).get("question_rows", [])
        if isinstance(analyzer_outputs.get("question_coverage_mapper"), dict)
        else []
    )

    rows: list[dict[str, Any]] = []
    scenario_counter: Counter[str] = Counter()
    for raw_row in question_rows:
        if not isinstance(raw_row, dict):
            continue
        question_id = str(raw_row.get("question_id") or "")
        question = questions.get(question_id, {})
        text = str(raw_row.get("question_text") or question.get("question_text") or "")
        intent = str(raw_row.get("intent") or question.get("intent") or "")
        scene = str(raw_row.get("scene") or question.get("scene") or "")

        detected = _detect_configured_scenario(industry, text)
        if "咨询" in industry or any(
            token in text
            for token in ("咨询", "麦肯锡", "贝恩", "BCG", "埃森哲", "并购", "ESG")
        ):
            detected = detected or _detect_management_scenario(text)
        if detected is None and (
            any(token in industry for token in ("保健", "营养", "健康"))
            or any(
                token in text
                for token in ("蛋白粉", "维生素", "蓝帽子", "保健品", "老人", "儿童")
            )
        ):
            detected = _detect_supplement_scenario(text)
        if detected is None:
            detected = _fallback_scenario(text, intent, scene)

        scenario, journey_stage, business_value = detected
        content_gap, recommended_asset = _content_gap_for_scenario(scenario)
        answer_state = str(raw_row.get("answer_state") or "no_brand")
        status = _brand_status(answer_state)
        scenario_counter[scenario] += 1
        rows.append(
            {
                "question_id": question_id,
                "question_text": text,
                "question_type": intent or scene or "other",
                "decision_scenario": scenario,
                "journey_stage": journey_stage,
                "business_value": business_value,
                "brand_status": status,
                "brand_present": bool(raw_row.get("brand_present")),
                "competitors_present": raw_row.get("competitors_present", []) or [],
                "diagnosis": _scenario_diagnosis_sentence(scenario, status),
                "content_gap": content_gap,
                "recommended_asset": recommended_asset,
            }
        )

    return {
        "items": rows,
        "summary": _summarize_scenario_rows(rows, scenario_counter),
    }


def _summarize_scenario_rows(
    rows: list[dict[str, Any]], scenario_counter: Counter[str]
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("decision_scenario") or "通用问题")].append(row)

    summaries: list[dict[str, Any]] = []
    for scenario, count in scenario_counter.most_common():
        scenario_rows = grouped.get(scenario, [])
        status_counter = Counter(
            str(row.get("brand_status") or "unknown") for row in scenario_rows
        )
        brand_entry_count = status_counter.get("target_only", 0) + status_counter.get(
            "target_with_competitors", 0
        )
        no_brand_count = status_counter.get("no_brand", 0)
        competitor_only_count = status_counter.get("competitor_only", 0)
        target_with_competitors_count = status_counter.get("target_with_competitors", 0)
        representative_questions = [
            _clip(row.get("question_text"), 72)
            for row in scenario_rows[:3]
            if row.get("question_text")
        ]
        missing_questions = [
            _clip(row.get("question_text"), 72)
            for row in scenario_rows
            if row.get("brand_status") in {"no_brand", "competitor_only"}
            and row.get("question_text")
        ][:3]
        competitor_names = _unique_values(
            competitor
            for row in scenario_rows
            for competitor in row.get("competitors_present", []) or []
            if competitor
        )
        summaries.append(
            {
                "decision_scenario": scenario,
                "question_count": count,
                "brand_entry_count": brand_entry_count,
                "brand_entry_rate": _safe_rate(brand_entry_count, count),
                "no_brand_count": no_brand_count,
                "no_brand_rate": _safe_rate(no_brand_count, count),
                "competitor_only_count": competitor_only_count,
                "competitor_only_rate": _safe_rate(competitor_only_count, count),
                "target_only_count": status_counter.get("target_only", 0),
                "target_with_competitors_count": target_with_competitors_count,
                "competitor_co_presence_rate": _safe_rate(
                    target_with_competitors_count, count
                ),
                "journey_stage": str(
                    (scenario_rows[0] if scenario_rows else {}).get("journey_stage")
                    or "understanding"
                ),
                "business_value": str(
                    (scenario_rows[0] if scenario_rows else {}).get("business_value")
                    or "low"
                ),
                "representative_questions": representative_questions,
                "missing_questions": missing_questions,
                "competitors_present": competitor_names[:5],
                "content_gap": str(
                    (scenario_rows[0] if scenario_rows else {}).get("content_gap") or ""
                ),
                "recommended_asset": str(
                    (scenario_rows[0] if scenario_rows else {}).get("recommended_asset")
                    or ""
                ),
            }
        )
    return summaries


def _scenario_diagnosis_sentence(scenario: str, status: str) -> str:
    if status == "target_with_competitors":
        return f"{scenario}中品牌已经入围，但仍与竞品同台比较。"
    if status == "target_only":
        return f"{scenario}中品牌已经获得相对明确的单独露出。"
    if status == "competitor_only":
        return f"{scenario}中竞品进入答案，监测品牌缺席，存在替代风险。"
    if status == "no_brand":
        return f"{scenario}更容易触发知识型回答，品牌尚未进入候选答案。"
    return f"{scenario}需要结合样本继续复核。"


_UNKNOWN_SOURCE_VALUES = {
    "",
    "unknown",
    "other",
    "n/a",
    "na",
    "缺乏特征，无法识别",
    "缺乏特征，无法识别。",
}


def _clean_a4_source_value(value: Any) -> str:
    text = str(value or "").strip()
    if text.lower() in _UNKNOWN_SOURCE_VALUES or text in _UNKNOWN_SOURCE_VALUES:
        return ""
    return text


def _source_identity_from_a4(item: dict[str, Any]) -> tuple[str, str]:
    site_category = _clean_a4_source_value(item.get("site_category"))
    source_type = _clean_a4_source_value(item.get("source_type"))
    if site_category:
        return source_type or site_category, site_category
    if bool(item.get("is_official")):
        return "official", "品牌官网"
    if source_type:
        return source_type, source_type
    return "unknown", "未知"


def _source_action_from_a4_label(label: str, *, is_official: bool) -> str:
    if label == "未知":
        return "当前没有足够站点特征完成分类，建议人工复核域名归属。"
    if is_official:
        return "优先优化官网可引用内容和结构化入口。"
    if label == "电商平台":
        return "补齐商品详情页、店铺问答和规格对比中的品牌卖点。"
    if label == "消费社区/导购平台":
        return "补充评测、清单和真实使用体验中的品牌事实与对比口径。"
    if label in {"内容社区/种草平台", "短视频/内容平台"}:
        return "维护适合内容平台传播的场景卖点、使用体验和风险澄清。"
    if label in {"微信公众号内容", "内容资讯平台"}:
        return "补充可被引用的科普解释、选购建议和权威结论。"
    if label == "问答社区":
        return "沉淀问答式解释，覆盖典型疑问、适用边界和对比证据。"
    if label == "百科/知识库":
        return "校准基础事实、品牌实体信息和权威定义。"
    if label == "学术/医学":
        return "将专业证据转写为适合 AI 引用的安全边界和结论摘要。"
    return f"围绕“{label}”来源维护站点画像与内容治理。"


def build_source_intelligence(
    metric_bundle: dict[str, Any],
    *,
    competitors: list[dict[str, Any]],
) -> dict[str, Any]:
    del competitors
    source_summary = (
        metric_bundle.get("source_summary")
        if isinstance(metric_bundle.get("source_summary"), dict)
        else {}
    )
    top_domains = source_summary.get("top_domains", []) or []
    total_citations = _as_int(source_summary.get("total_citations"))
    rows: list[dict[str, Any]] = []
    type_counter: Counter[str] = Counter()

    for item in top_domains:
        if not isinstance(item, dict):
            continue
        domain = _normalize_domain(item.get("domain"))
        if not domain:
            continue
        titles = [str(title or "") for title in item.get("sample_titles", []) or []]
        display_name = str(item.get("display_name") or "").strip()
        explicit_site_name = str(item.get("site_name") or "").strip()
        site_name = (
            (display_name if display_name and display_name.lower() != domain else "")
            or (
                explicit_site_name
                if explicit_site_name and explicit_site_name.lower() != domain
                else ""
            )
            or domain
        )
        is_official = bool(item.get("is_official"))
        source_type, display = _source_identity_from_a4(item)
        site_category = _clean_a4_source_value(item.get("site_category")) or None
        authority = 85 if is_official else 35
        control = 100 if is_official else 0
        action = _source_action_from_a4_label(display, is_official=is_official)
        count = _as_int(item.get("count"))
        type_counter[display] += count
        rows.append(
            {
                "domain": domain,
                "site_name": site_name,
                "site_display": _format_site_name(domain, site_name),
                "source_type": source_type,
                "source_type_label": display,
                "site_category": site_category,
                "authority_score": authority,
                "brand_control_score": control,
                "ai_citation_frequency": count,
                "citation_share": _safe_rate(count, total_citations),
                "risk_level": ("low" if control > 0 else "medium"),
                "recommended_action": action,
                "sample_titles": [_clip(title, 56) for title in titles[:3] if title],
            }
        )

    unknown_domains = [
        {
            "domain": item["domain"],
            "site_name": item.get("site_name"),
            "site_display": item.get("site_display"),
            "ai_citation_frequency": item["ai_citation_frequency"],
            "recommended_action": item["recommended_action"],
            "sample_titles": item.get("sample_titles", []),
        }
        for item in rows
        if item.get("source_type") == "unknown"
    ]
    return {
        "domains": rows,
        "summary": [
            {
                "source_type_label": label,
                "ai_citation_frequency": count,
                "citation_share": _safe_rate(count, total_citations),
                "diagnosis": _source_type_diagnosis(label),
            }
            for label, count in type_counter.most_common()
        ],
        "unknown_domains": unknown_domains,
    }


def _source_type_diagnosis(label: str) -> str:
    if label == "未知":
        return "当前没有足够站点特征完成分类，需要人工复核域名归属。"
    if label == "品牌官网":
        return "品牌可控来源，应优先做结构化内容和可引用结论优化。"
    if label == "电商平台":
        return "AI 答案正在引用交易与商品详情入口，会影响购买转化和规格认知。"
    if label == "消费社区/导购平台":
        return "AI 答案依赖消费决策社区，说明真实体验、榜单和导购内容会影响品牌解释权。"
    if label in {"内容社区/种草平台", "短视频/内容平台"}:
        return "AI 答案引用内容平台，说明场景体验和口碑内容会影响用户第一印象。"
    if label in {"微信公众号内容", "内容资讯平台"}:
        return "AI 答案引用内容资讯来源，说明科普文章和媒体解释会影响决策理解。"
    if label == "问答社区":
        return "AI 答案引用问答社区，说明用户疑问和对比讨论正在影响答案组织。"
    if label == "百科/知识库":
        return "AI 答案引用百科知识库，说明基础事实和实体定义会影响品牌认知。"
    if label == "学术/医学":
        return "AI 答案引用学术或医学来源，说明安全、功效和证据边界是关键解释依据。"
    return f"该类型来自引用来源识别结果，用于观察 AI 答案对“{label}”来源的依赖。"


CONCERN_LABELS = {
    "price_barrier": "价格门槛",
    "delivery_complexity": "交付复杂度",
    "evidence_sufficiency": "证据充分性",
    "fit_boundary": "适配边界",
    "competitive_substitution_risk": "竞争替代风险",
    "general_decision_concern": "决策顾虑",
}


def _map_negative_topic(topic: str) -> str:
    return {
        "price": "price_barrier",
        "deployment": "delivery_complexity",
        "usability": "delivery_complexity",
        "case": "evidence_sufficiency",
        "credibility": "evidence_sufficiency",
        "service": "fit_boundary",
        "ecosystem": "fit_boundary",
    }.get(topic, "general_decision_concern")


def _infer_concerns_from_text(text: str) -> list[str]:
    lowered = str(text or "").lower()
    concerns: list[str] = []
    if any(
        token in text for token in ("价格高", "成本高", "预算", "费用高", "高客单价")
    ):
        concerns.append("price_barrier")
    if any(
        token in text
        for token in ("周期长", "实施复杂", "交付复杂", "组织承接", "上手难")
    ):
        concerns.append("delivery_complexity")
    if any(
        token in text
        for token in (
            "案例少",
            "证据不足",
            "证据",
            "成分",
            "浓度",
            "实验",
            "方法论",
            "数据支撑",
            "可信度",
        )
    ):
        concerns.append("evidence_sufficiency")
    if any(
        token in text
        for token in (
            "中型企业",
            "中小企业",
            "适配",
            "不适合",
            "不如本土",
            "客群",
            "肤质",
            "敏感肌",
            "耐受",
            "屏障",
            "试用",
            "香精",
        )
    ):
        concerns.append("fit_boundary")
    if (
        any(
            token in text
            for token in (
                "竞品",
                "替代",
                "更适合",
                "不如",
                "相比",
                "优先提到",
                "大众知名度",
                "公开讨论",
            )
        )
        or "competitor" in lowered
    ):
        concerns.append("competitive_substitution_risk")
    return concerns


def build_risk_concern_analysis(
    metric_bundle: dict[str, Any],
    analyzer_outputs: dict[str, Any],
) -> dict[str, Any]:
    concerns: Counter[str] = Counter()
    evidence: dict[str, list[str]] = {}
    platform_counts: dict[str, Counter[str]] = defaultdict(Counter)
    sentiment_risk = (
        metric_bundle.get("sentiment_risk")
        if isinstance(metric_bundle.get("sentiment_risk"), dict)
        else {}
    )
    per_platform_negative_topics = (
        sentiment_risk.get("per_platform_negative_topics", {})
        if isinstance(sentiment_risk.get("per_platform_negative_topics"), dict)
        else {}
    )
    for platform, topic_counts in per_platform_negative_topics.items():
        if not isinstance(topic_counts, dict):
            continue
        for topic, count in topic_counts.items():
            category = _map_negative_topic(str(topic or ""))
            amount = _as_int(count)
            if amount > 0:
                platform_counts[category][str(platform)] += amount

    for row in sentiment_risk.get("top_negative_topics", []) or []:
        if not isinstance(row, dict):
            continue
        concern_text = " ".join(
            str(row.get(field) or "")
            for field in ("topic", "display", "common_conclusion")
        )
        category = _map_negative_topic(str(row.get("topic") or ""))
        categories = {category, *_infer_concerns_from_text(concern_text)}
        count = _as_int(row.get("count"), 1)
        for category in categories:
            concerns[category] += max(count, 1)
            if row.get("common_conclusion"):
                evidence.setdefault(category, []).append(
                    str(row.get("common_conclusion"))
                )

    question_rows = (
        analyzer_outputs.get("question_coverage_mapper", {}).get("question_rows", [])
        if isinstance(analyzer_outputs.get("question_coverage_mapper"), dict)
        else []
    )
    for row in question_rows:
        if not isinstance(row, dict):
            continue
        answer_state = str(row.get("answer_state") or "")
        competitors_present = row.get("competitors_present") or []
        question_text = str(row.get("question_text") or "")
        if answer_state == "competitor_only":
            concerns["competitive_substitution_risk"] += 1
            evidence.setdefault("competitive_substitution_risk", []).append(
                _clip(question_text, 80)
            )
            for platform in row.get("present_platforms", []) or []:
                platform_counts["competitive_substitution_risk"][str(platform)] += 1
        elif competitors_present and any(
            token in question_text
            for token in ("还是", "对比", "怎么选", "更适合", "替代")
        ):
            concerns["competitive_substitution_risk"] += 1
            evidence.setdefault("competitive_substitution_risk", []).append(
                _clip(question_text, 80)
            )
            for platform in row.get("present_platforms", []) or []:
                platform_counts["competitive_substitution_risk"][str(platform)] += 1

    total = sum(concerns.values())
    items = [
        {
            "concern_type": key,
            "label": CONCERN_LABELS.get(key, key),
            "count": count,
            "share": _safe_rate(count, total),
            "evidence": evidence.get(key, [])[:3],
            "platform_counts": dict(platform_counts.get(key, {})),
        }
        for key, count in concerns.most_common()
    ]
    negative_rate = metric_bundle.get("negative_rate")
    narrative = (
        "本轮 AI 回答中出现较多决策顾虑，这不一定代表品牌口碑负面，而是说明 AI 在推荐或比较品牌时会提醒用户评估预算、组织承接能力、证据充分性和适配边界。"
        if isinstance(negative_rate, (int, float)) and negative_rate > 0.5
        else "本轮风险信号应按决策顾虑理解，这不一定代表品牌口碑负面；应避免把价格、复杂度或适配边界直接等同于口碑负面。"
    )
    return {
        "summary": {
            "decision_concern_count": total,
            "raw_negative_rate": negative_rate,
            "narrative": narrative,
        },
        "items": items,
    }


def build_action_recommendations(
    *,
    data_audit: dict[str, Any],
    scenario_diagnostics: dict[str, Any],
    source_intelligence: dict[str, Any],
    risk_concern_analysis: dict[str, Any],
    metric_bundle: dict[str, Any],
    brand_name: str,
) -> list[dict[str, Any]]:
    mode = data_audit.get("report_mode")
    recommendations: list[dict[str, Any]] = []
    scenario_items = [
        item
        for item in scenario_diagnostics.get("items", []) or []
        if isinstance(item, dict)
    ]

    if mode == REPORT_MODE_NO_SIGNAL:
        missing_item = next(
            (
                item
                for item in scenario_items
                if item.get("brand_status") in {"no_brand", "competitor_only"}
            ),
            scenario_items[0] if scenario_items else {},
        )
        scenario = str(missing_item.get("decision_scenario") or "高价值决策场景")
        asset = str(missing_item.get("recommended_asset") or f"{scenario}权威解释页")
        recommendations.append(
            {
                "priority": "P0",
                "decision_scenario": scenario,
                "fact": f"{brand_name}尚未进入本轮 AI 答案。",
                "business_problem": "当前优先问题不是官网承接或口碑，而是品牌还没有进入候选答案。",
                "recommended_asset": asset,
                "target_metric": ["品牌可见度", "无品牌率", "竞品挤压率"],
                "validation_plan": "新增品牌比较、场景购买、风险验证三类问题，每类至少 10 条并在主要平台复测。",
                "observation_cycle": "下一轮固定问题集复测后判断是否进入完整报告。",
            }
        )
        return recommendations

    contested = next(
        (
            item
            for item in scenario_items
            if item.get("brand_status")
            in {"target_with_competitors", "competitor_only"}
        ),
        scenario_items[0] if scenario_items else {},
    )
    if contested:
        scenario = str(contested.get("decision_scenario") or "核心决策场景")
        recommendations.append(
            {
                "priority": "P0",
                "decision_scenario": scenario,
                "fact": contested.get("diagnosis")
                or "该场景已经出现品牌进入或竞品同台信号。",
                "business_problem": contested.get("content_gap")
                or "AI 缺少可直接引用的品牌差异化解释。",
                "recommended_asset": contested.get("recommended_asset")
                or f"{scenario}权威解释页",
                "target_metric": ["主推荐率", "官网引用转化率", "竞品同台率"],
                "validation_plan": f"固定 20 个{scenario}问题，在 DeepSeek、豆包、Kimi、元宝复测。",
                "observation_cycle": "2-4 周或下一轮内容上线后。",
            }
        )

    official_conversion = metric_bundle.get("official_conversion_rate")
    if not isinstance(official_conversion, (int, float)) or official_conversion < 0.2:
        source_summary = source_intelligence.get("summary", []) or []
        top_source = (
            source_summary[0]["source_type_label"] if source_summary else "外部来源"
        )
        recommendations.append(
            {
                "priority": "P1",
                "decision_scenario": "来源证据权",
                "fact": f"当前 AI 答案主要受{top_source}影响，官网证据权不足。",
                "business_problem": "品牌露出没有稳定回到品牌可控内容。",
                "recommended_asset": "官网结论页、官方白皮书 HTML 摘要和可引用 FAQ",
                "target_metric": ["官网引用转化率", "品牌相关链接数"],
                "validation_plan": "复测带引用的平台答案，观察官网和官方文档是否进入引用链。",
                "observation_cycle": "内容上线后 2-4 周。",
            }
        )

    concern_items = risk_concern_analysis.get("items", []) or []
    if concern_items:
        top_concern = concern_items[0]
        recommendations.append(
            {
                "priority": "P1",
                "decision_scenario": str(top_concern.get("label") or "风险顾虑"),
                "fact": f"本轮主要决策顾虑集中在{top_concern.get('label')}。",
                "business_problem": "AI 在推荐或比较时会主动提醒用户评估该门槛。",
                "recommended_asset": f"{top_concern.get('label')}FAQ 和边界说明",
                "target_metric": ["决策顾虑率", "品牌主推荐率"],
                "validation_plan": "围绕该顾虑生成固定复测问题，观察顾虑是否被更准确解释。",
                "observation_cycle": "下一轮复测。",
            }
        )

    return recommendations[:4]


def build_no_signal_report(
    *,
    brand_name: str,
    report_kind: str,
    metric_bundle: dict[str, Any],
    data_audit: dict[str, Any],
    report_route: dict[str, Any],
    scenario_diagnostics: dict[str, Any],
    action_recommendations: list[dict[str, Any]],
) -> dict[str, Any]:
    no_brand_rate = metric_bundle.get("no_brand_rate")
    competitor_pressure = metric_bundle.get("competitor_pressure")
    total_questions = _as_int(metric_bundle.get("total_questions"))
    successful_answers = _as_int(metric_bundle.get("successful_answers"))
    scenario_items = [
        item
        for item in scenario_diagnostics.get("items", []) or []
        if isinstance(item, dict)
    ]
    competitor_scenarios = [
        item for item in scenario_items if item.get("brand_status") == "competitor_only"
    ]
    knowledge_scenarios = [
        item for item in scenario_items if item.get("brand_status") == "no_brand"
    ]
    suggested_scenarios = scenario_items[:4]
    not_judged = data_audit.get("not_judged", [])
    top_action = action_recommendations[0] if action_recommendations else {}

    executive_report = {
        "section_title": "高管版摘要",
        "one_line_judgment": (
            f"{brand_name}尚未进入本轮 AI 答案；当前优先任务是让品牌先进入候选答案，而不是判断官网承接或品牌口碑。"
        ),
        "key_findings": [
            {
                "fact": f"本轮有效答案 {successful_answers} 条，品牌提及样本为 0。",
                "detail": _brand_answer_detail(
                    metric_bundle,
                    brand_presence_count=0,
                    successful_answers=successful_answers,
                ),
            },
            {
                "fact": f"无品牌回答占比为 {_format_rate(no_brand_rate)}。",
                "detail": _brand_entry_detail(
                    metric_bundle,
                    brand_presence_count=0,
                    successful_answers=successful_answers,
                ),
            },
        ],
        "top_actions": action_recommendations[:3],
        "not_judged": not_judged,
    }

    lines = [
        f"# {brand_name}｜{report_route.get('title') or '品牌 AI 答案未进入诊断报告'}",
        "",
        "## 高管版摘要",
        "",
        executive_report["one_line_judgment"],
        "",
        "### 关键发现",
    ]
    for finding in executive_report["key_findings"]:
        lines.extend(
            [
                f"- **事实**：{finding['fact']}",
                f"  **详解**：{finding['detail']}",
            ]
        )
    lines.extend(
        [
            "",
            "### 优先动作",
            f"- **{top_action.get('priority', 'P0')}｜{top_action.get('recommended_asset', '建设高价值场景权威解释页')}**",
            f"  **验证方式**：{top_action.get('validation_plan', '下一轮固定问题集复测。')}",
            "",
            "## 运营版诊断",
            "",
            "### 1. 本轮结论",
            f"- 品牌是否进入答案：{brand_name}尚未进入本轮 AI 答案。",
            f"- 无品牌回答占比：{_format_rate(no_brand_rate)}。",
            f"- 是否出现竞品：{'出现竞品偶发进入。' if competitor_scenarios else '本轮未观察到稳定竞品进入。'}",
            "- 当前不能判断：情感、官网承接、平台偏好、品牌口碑。",
            "",
            "### 2. 问题触发类型",
        ]
    )
    if knowledge_scenarios:
        for item in knowledge_scenarios[:4]:
            lines.append(
                f"- **{item.get('decision_scenario')}**：{item.get('diagnosis')} 建议复采样问题「{_clip(item.get('question_text'), 44)}」。"
            )
    else:
        lines.append(
            "- 当前问题集尚未形成清晰触发类型，需要补充品牌比较和场景购买问题。"
        )

    lines.extend(["", "### 3. 竞品偶发进入"])
    if competitor_scenarios:
        for item in competitor_scenarios[:4]:
            competitors = "、".join(item.get("competitors_present") or []) or "竞品"
            lines.append(
                f"- **{item.get('decision_scenario')}**：{competitors}进入答案，{brand_name}缺席；需要复核这是主动推荐还是顺带提及。"
            )
    else:
        lines.append(
            f"- 竞品挤压率为 {_format_rate(competitor_pressure)}，本轮未形成稳定竞品挤压判断。"
        )

    lines.extend(["", "### 4. 内容缺口假设"])
    if suggested_scenarios:
        for item in suggested_scenarios[:5]:
            lines.append(
                f"- **{item.get('decision_scenario')}**：{item.get('content_gap')} 推荐资产：{item.get('recommended_asset')}。"
            )
    else:
        lines.extend(
            [
                "- 安全合规缺口：需要补充安全、认证、边界说明。",
                "- 适用人群缺口：需要说明适合谁、不适合谁。",
                "- 价格理由缺口：需要解释价格差异和价值依据。",
                "- 对比解释缺口：需要解释与竞品或替代方案的差异。",
                "- 购买渠道缺口：需要说明官方渠道和可信购买路径。",
            ]
        )

    lines.extend(
        [
            "",
            "### 5. 下一轮验证计划",
            f"- 新增问题：品牌比较、场景购买、风险验证三类问题，优先覆盖 {('、'.join(item.get('decision_scenario', '') for item in suggested_scenarios[:3]) or '高价值决策场景')}。",
            "- 每类问题采样：每个核心场景至少 10 条问题，覆盖 DeepSeek、豆包、Kimi、元宝。",
            "- 观察指标：品牌可见度、无品牌率、竞品挤压率、品牌相关链接数。",
            "- 进入完整报告阈值：品牌提及样本达到 5 条以上进入弱信号观察，达到 10 条且有效答案超过 30 条进入完整诊断。",
            "",
            "### 6. 暂不判断事项",
        ]
    )
    for item in not_judged:
        if isinstance(item, dict):
            lines.append(f"- **{item.get('label')}**：{item.get('reason')}")

    operations_diagnosis = {
        "section_title": "运营版诊断",
        "mode": REPORT_MODE_NO_SIGNAL,
        "sections": report_route.get("operations_sections", []),
        "total_questions": total_questions,
        "successful_answers": successful_answers,
        "scenario_items": scenario_items,
    }
    return {
        "sections": [
            {
                "section_name": "executive_summary",
                "title": "高管版摘要",
                "markdown": "\n".join(lines[: lines.index("## 运营版诊断")]).strip(),
                "data": executive_report,
            },
            {
                "section_name": "operations_diagnosis",
                "title": "运营版诊断",
                "markdown": "\n".join(lines[lines.index("## 运营版诊断") :]).strip(),
                "data": operations_diagnosis,
            },
        ],
        "report_markdown": "\n".join(lines).strip(),
        "executive_report": executive_report,
        "operations_diagnosis": operations_diagnosis,
    }


def build_standard_report_wrappers(
    *,
    brand_name: str,
    sections: list[dict[str, Any]],
    data_audit: dict[str, Any],
    report_route: dict[str, Any],
    action_recommendations: list[dict[str, Any]],
) -> dict[str, Any]:
    summary_section = next(
        (section for section in sections if section.get("section_name") == "summary"),
        {},
    )
    summary_data = (
        summary_section.get("data", {}) if isinstance(summary_section, dict) else {}
    )
    one_line = str(summary_data.get("one_line_conclusion") or "").strip()
    if not one_line:
        one_line = f"{brand_name}已完成本轮 AI 答案品牌诊断。"
    executive_report = {
        "section_title": "高管版摘要",
        "one_line_judgment": one_line,
        "key_findings": [
            {
                "fact": finding,
                "detail": "该条来自摘要建议，需回到对应场景、来源和风险样本复核。",
            }
            for finding in summary_data.get("suggestions", [])[:3]
            if isinstance(finding, str)
        ],
        "top_actions": action_recommendations[:3],
        "not_judged": data_audit.get("not_judged", []),
    }
    operations_diagnosis = {
        "section_title": "运营版诊断",
        "mode": data_audit.get("report_mode"),
        "sections": report_route.get("operations_sections", []),
        "section_names": [
            section.get("section_name")
            for section in sections
            if isinstance(section, dict) and section.get("section_name")
        ],
    }
    return {
        "executive_report": executive_report,
        "operations_diagnosis": operations_diagnosis,
    }


def build_diagnosis_markdown_appendix(
    *,
    scenario_diagnostics: dict[str, Any],
    source_intelligence: dict[str, Any],
    risk_concern_analysis: dict[str, Any],
    action_recommendations: list[dict[str, Any]],
) -> str:
    scenario_items = [
        item
        for item in scenario_diagnostics.get("items", []) or []
        if isinstance(item, dict)
    ][:6]
    source_summary = [
        item
        for item in source_intelligence.get("summary", []) or []
        if isinstance(item, dict)
    ][:3]
    source_domains = [
        item
        for item in source_intelligence.get("domains", []) or []
        if isinstance(item, dict)
    ][:5]
    risk_items = [
        item
        for item in risk_concern_analysis.get("items", []) or []
        if isinstance(item, dict)
    ][:5]
    risk_summary = (
        risk_concern_analysis.get("summary", {})
        if isinstance(risk_concern_analysis.get("summary"), dict)
        else {}
    )

    lines = [
        "## 8. 运营版诊断增强",
        "",
        "### 8.1 场景地图",
    ]
    if scenario_items:
        for item in scenario_items:
            lines.append(
                f"- **{item.get('decision_scenario')}**：决策阶段 {_journey_stage_label(item.get('journey_stage'))}，业务价值 {_business_value_label(item.get('business_value'))}，品牌状态 {_brand_status_label(item.get('brand_status'))}。"
            )
    else:
        lines.append("- 当前问题样本不足以形成稳定场景地图。")

    lines.extend(["", "### 8.2 来源证据权"])
    if source_summary:
        lines.append("当前 AI 答案主要依赖以下来源类型：")
        for index, item in enumerate(source_summary, start=1):
            lines.append(
                f"{index}. **{item.get('source_type_label')}**：{item.get('diagnosis')}"
            )
    else:
        lines.append("当前没有形成稳定来源类型结构。")
    for item in source_domains:
        lines.append(
            f"- {item.get('domain')}：{item.get('source_type_label')}；推荐动作：{item.get('recommended_action')}"
        )

    lines.extend(["", "### 8.3 风险顾虑"])
    narrative = str(risk_summary.get("narrative") or "").strip()
    if narrative:
        lines.append(narrative)
    if risk_items:
        for item in risk_items:
            evidence = "；".join(
                str(value) for value in item.get("evidence", []) if value
            )
            lines.append(
                f"- **{item.get('label')}**：出现 {item.get('count')} 次。证据：{evidence or '本轮样本未提供可引用原句。'}"
            )
    else:
        lines.append("- 当前没有稳定重复的风险顾虑。")

    lines.extend(["", "### 8.4 行动建议"])
    if action_recommendations:
        for item in action_recommendations[:5]:
            metrics = "、".join(
                str(value) for value in item.get("target_metric", []) if value
            )
            lines.extend(
                [
                    f"- **{item.get('priority')}｜{item.get('recommended_asset')}**",
                    f"  - 场景：{item.get('decision_scenario')}",
                    f"  - 事实：{item.get('fact')}",
                    f"  - 影响指标：{metrics or '品牌可见度、官网引用转化率'}",
                    f"  - 验证方式：{item.get('validation_plan')}",
                ]
            )
    else:
        lines.append("- 当前没有足够信号生成行动建议。")

    return "\n".join(lines).strip()


def build_diagnostic_conclusions(
    *,
    brand_name: str,
    metric_bundle: dict[str, Any],
    data_audit: dict[str, Any],
    scenario_diagnostics: dict[str, Any],
    source_intelligence: dict[str, Any],
    risk_concern_analysis: dict[str, Any],
    action_recommendations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    mode = str(data_audit.get("report_mode") or REPORT_MODE_BRAND_ENTRY)
    successful_answers = _as_int(metric_bundle.get("successful_answers"))
    total_questions = _as_int(metric_bundle.get("total_questions"))
    brand_presence_count = _as_int(metric_bundle.get("brand_presence_count"))
    brand_visibility = metric_bundle.get("brand_visibility")
    no_brand_rate = metric_bundle.get("no_brand_rate")
    competitor_pressure = metric_bundle.get("competitor_pressure")
    official_conversion = metric_bundle.get("official_conversion_rate")
    scenario_items = [
        item
        for item in scenario_diagnostics.get("items", []) or []
        if isinstance(item, dict)
    ]
    top_scenario = scenario_items[0] if scenario_items else {}
    source_summary = [
        item
        for item in source_intelligence.get("summary", []) or []
        if isinstance(item, dict)
    ]
    source_domains = [
        item
        for item in source_intelligence.get("domains", []) or []
        if isinstance(item, dict)
    ]
    top_source = source_summary[0] if source_summary else {}
    risk_items = [
        item
        for item in risk_concern_analysis.get("items", []) or []
        if isinstance(item, dict)
    ]
    top_risk = risk_items[0] if risk_items else {}
    top_action = action_recommendations[0] if action_recommendations else {}

    if mode == REPORT_MODE_NO_SIGNAL:
        return [
            {
                "code": "brand_not_entered",
                "fact": f"本轮有效答案 {successful_answers} 条，{brand_name}品牌提及样本为 0。",
                "detail": _brand_answer_detail(
                    metric_bundle,
                    brand_presence_count=0,
                    successful_answers=successful_answers,
                ),
                "summary": "品牌尚未进入本轮 AI 答案，当前优先问题是进入候选答案。",
            },
            {
                "code": "question_trigger",
                "fact": f"无品牌回答占比为 {_format_rate(no_brand_rate)}。",
                "detail": _brand_entry_detail(
                    metric_bundle,
                    brand_presence_count=0,
                    successful_answers=successful_answers,
                ),
                "summary": "当前问题集更容易触发知识型回答，而不是品牌推荐型回答。",
            },
        ]

    mode_summary = {
        REPORT_MODE_WEAK_SIGNAL: "品牌已经出现弱进入信号，但样本不足以支撑稳定结论。",
        REPORT_MODE_BRAND_ENTRY: "品牌已经进入部分答案，可以诊断进入场景、来源和顾虑。",
        REPORT_MODE_FULL_LANDSCAPE: "样本量达到完整诊断阈值，可以形成较完整的品牌决策诊断。",
    }.get(mode, "品牌已经进入本轮 AI 答案，可以进行结构化诊断。")
    conclusions = [
        {
            "code": "data_status",
            "fact": f"本轮覆盖 {total_questions} 个问题、{successful_answers} 条有效答案，品牌提及 {brand_presence_count} 条。",
            "detail": _brand_answer_detail(
                metric_bundle,
                brand_presence_count=brand_presence_count,
                successful_answers=successful_answers,
            ),
            "summary": mode_summary,
        },
        {
            "code": "brand_entry",
            "fact": f"品牌可见度为 {_format_rate(brand_visibility)}，竞品挤压率为 {_format_rate(competitor_pressure)}。",
            "detail": _brand_entry_detail(
                metric_bundle,
                brand_presence_count=brand_presence_count,
                successful_answers=successful_answers,
            ),
            "summary": "品牌进入能力需要同时看可见度、竞品同台和无品牌回答结构。",
        },
    ]
    if top_scenario:
        conclusions.append(
            {
                "code": "scenario_map",
                "fact": f"代表性场景为{top_scenario.get('decision_scenario')}，品牌状态为{_brand_status_label(top_scenario.get('brand_status'))}。",
                "detail": _scenario_conclusion_detail(
                    top_scenario, brand_name=brand_name
                ),
                "summary": str(
                    top_scenario.get("diagnosis") or "该场景需要结合样本继续复核。"
                ),
            }
        )
    if top_source:
        conclusions.append(
            {
                "code": "source_evidence",
                "fact": f"当前主要来源类型为{top_source.get('source_type_label')}，引用频次 {top_source.get('ai_citation_frequency')}。",
                "detail": _source_conclusion_detail(top_source, source_domains),
                "summary": str(
                    top_source.get("diagnosis") or "来源结构影响 AI 对品牌的解释权。"
                ),
            }
        )
    if top_risk:
        conclusions.append(
            {
                "code": "risk_concern",
                "fact": f"主要决策顾虑集中在{top_risk.get('label')}，出现 {top_risk.get('count')} 次。",
                "detail": _risk_conclusion_detail(top_risk),
                "summary": str(
                    risk_concern_analysis.get("summary", {}).get("narrative")
                    or "风险信号应按决策顾虑理解。"
                ),
            }
        )
    if top_action:
        conclusions.append(
            {
                "code": "top_action",
                "fact": str(top_action.get("fact") or "已有可执行行动建议。"),
                "detail": _action_conclusion_detail(top_action),
                "summary": str(
                    top_action.get("business_problem")
                    or "该建议用于提升品牌进入和解释权。"
                ),
            }
        )
    if isinstance(official_conversion, (int, float)):
        official_funnel = (
            metric_bundle.get("official_funnel")
            if isinstance(metric_bundle.get("official_funnel"), dict)
            else {}
        )
        conclusions.append(
            {
                "code": "official_conversion",
                "fact": f"官网引用转化率为 {_format_rate(official_conversion)}。",
                "detail": _join_detail_parts(
                    [
                        f"提及品牌答案 {official_funnel.get('monitor_brand_answer_count', 0)} 条",
                        f"品牌相关链接答案 {official_funnel.get('brand_related_link_answer_count', 0)} 条",
                        f"官网链接答案 {official_funnel.get('official_link_answer_count', 0)} 条",
                    ]
                ),
                "summary": "官网和官方内容是否进入引用链会影响品牌可控解释权。",
            }
        )
    return conclusions


def _render_conclusion_lines(conclusions: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in conclusions:
        detail = str(item.get("detail") or "").strip() or _legacy_conclusion_detail(
            item
        )
        lines.extend(
            [
                f"- **事实**：{item.get('fact')}",
                f"  **详解**：{detail}",
            ]
        )
    return lines


def _render_action_lines(actions: list[dict[str, Any]]) -> list[str]:
    if not actions:
        return ["- 当前没有足够信号生成行动建议。"]
    lines: list[str] = []
    for action in actions[:5]:
        target_metric = "、".join(
            str(value) for value in action.get("target_metric", []) if value
        )
        lines.extend(
            [
                f"- **{action.get('priority')}｜{action.get('recommended_asset')}**",
                f"  - 场景：{action.get('decision_scenario')}",
                f"  - 事实：{action.get('fact')}",
                f"  - 影响指标：{target_metric or '品牌可见度、官网引用转化率'}",
                f"  - 验证方式：{action.get('validation_plan')}",
            ]
        )
    return lines


def _build_retest_plan(
    *,
    mode: str,
    scenario_items: list[dict[str, Any]],
) -> dict[str, Any]:
    scenario_names = [
        str(item.get("decision_scenario") or "")
        for item in scenario_items[:3]
        if item.get("decision_scenario")
    ]
    return {
        "question_types": ["品牌比较", "场景购买", "风险验证"],
        "sample_size": "每个核心场景至少 10 条问题",
        "platforms": ["DeepSeek", "豆包", "Kimi", "元宝"],
        "metrics": ["品牌可见度", "无品牌率", "竞品挤压率", "官网引用转化率"],
        "entry_threshold": (
            "品牌提及样本达到 5 条以上进入弱信号观察，达到 10 条且有效答案超过 30 条进入完整诊断。"
            if mode == REPORT_MODE_NO_SIGNAL
            else "内容上线后用固定问题集复测，观察目标指标是否连续改善。"
        ),
        "priority_scenarios": scenario_names,
    }


def _metric_display(
    value: Any,
    *,
    kind: str = "rate",
    unavailable: str = "暂无足够数据支撑",
) -> str:
    if kind == "rank":
        return f"#{value}" if value else unavailable
    if kind == "count":
        return str(_as_int(value))
    return _format_rate(value)


def _build_core_metrics(
    metric_bundle: dict[str, Any],
    data_audit: dict[str, Any],
) -> list[dict[str, Any]]:
    eligibility = (
        data_audit.get("metric_eligibility")
        if isinstance(data_audit.get("metric_eligibility"), dict)
        else {}
    )
    official_eligibility = (
        eligibility.get("official_conversion")
        if isinstance(eligibility.get("official_conversion"), dict)
        else {}
    )
    brand_rank = metric_bundle.get("brand_rank")
    sentiment = (
        metric_bundle.get("sentiment_distribution")
        if isinstance(metric_bundle.get("sentiment_distribution"), dict)
        else {}
    )
    official_value = (
        _metric_display(metric_bundle.get("official_conversion_rate"))
        if official_eligibility.get("judgeable", True)
        else str(
            official_eligibility.get("reason")
            or "没有品牌提及答案，官网引用转化率没有有效分母。"
        )
    )
    brand_rank_value = (
        _metric_display(brand_rank, kind="rank", unavailable="未进入品牌排名")
        if brand_rank
        else (
            "品牌未进入答案，暂未形成排名"
            if _as_int(metric_bundle.get("brand_presence_count")) <= 0
            else "暂无足够数据支撑"
        )
    )
    return [
        {
            "code": "brand_visibility",
            "label": "品牌可见度",
            "value": _metric_display(metric_bundle.get("brand_visibility")),
            "interpretation": "所有有效答案中提及监测品牌的比例。",
        },
        {
            "code": "brand_rank",
            "label": "品牌提及排名",
            "value": brand_rank_value,
            "interpretation": "在全部被提及品牌中的相对位置。",
        },
        {
            "code": "competitor_pressure",
            "label": "竞品挤压率",
            "value": _metric_display(metric_bundle.get("competitor_pressure")),
            "interpretation": "提及竞品但未提监测品牌的答案占比。",
        },
        {
            "code": "no_brand_rate",
            "label": "无品牌率",
            "value": _metric_display(metric_bundle.get("no_brand_rate")),
            "interpretation": "回答停留在知识型建议、未进入品牌推荐的比例。",
        },
        {
            "code": "monitor_only_rate",
            "label": "只提品牌率",
            "value": _metric_display(metric_bundle.get("monitor_only_rate")),
            "interpretation": "答案只提监测品牌、不与竞品同台的比例。",
        },
        {
            "code": "monitor_plus_others_rate",
            "label": "品牌竞品同台率",
            "value": _metric_display(metric_bundle.get("monitor_plus_others_rate")),
            "interpretation": "答案同时提到监测品牌和竞品的比例。",
        },
        {
            "code": "official_conversion_rate",
            "label": "官网引用转化率",
            "value": official_value,
            "interpretation": "品牌被提到后，答案是否同步引用官网或官方内容。",
        },
        {
            "code": "sentiment_positive",
            "label": "正向情绪占比",
            "value": _metric_display(sentiment.get("positive")),
            "interpretation": "提及品牌的答案中，明确正向评价的比例。",
        },
        {
            "code": "sentiment_neutral",
            "label": "中性情绪占比",
            "value": _metric_display(sentiment.get("neutral")),
            "interpretation": "提及品牌的答案中，以事实描述或中性比较为主的比例。",
        },
        {
            "code": "sentiment_negative",
            "label": "负向/风险顾虑信号占比",
            "value": _metric_display(sentiment.get("negative")),
            "interpretation": "提及品牌的答案中出现负向或决策顾虑信号的比例；不直接等同于口碑负面。",
        },
    ]


def _build_sentiment_probe(
    metric_bundle: dict[str, Any],
    risk_concern_analysis: dict[str, Any],
) -> dict[str, Any]:
    brand_presence_count = _as_int(metric_bundle.get("brand_presence_count"))
    distribution = (
        metric_bundle.get("sentiment_distribution")
        if isinstance(metric_bundle.get("sentiment_distribution"), dict)
        else {}
    )
    top_positive_reasons = [
        item
        for item in metric_bundle.get("top_positive_reasons", []) or []
        if isinstance(item, dict)
    ]
    top_negative_topics = [
        item
        for item in metric_bundle.get("top_negative_topics", []) or []
        if isinstance(item, dict)
    ]
    sentiment_risk = (
        metric_bundle.get("sentiment_risk")
        if isinstance(metric_bundle.get("sentiment_risk"), dict)
        else {}
    )
    negative_source_distribution = (
        metric_bundle.get("negative_source_distribution")
        if isinstance(metric_bundle.get("negative_source_distribution"), dict)
        else {}
    )
    negative_topics = []
    for item in top_negative_topics:
        topic = str(item.get("topic") or "")
        concern_type = _map_negative_topic(topic)
        negative_topics.append(
            {
                "topic": topic,
                "display": item.get("display") or CONCERN_LABELS.get(concern_type),
                "mapped_concern": CONCERN_LABELS.get(concern_type, concern_type),
                "rate": item.get("rate"),
                "count": item.get("count"),
                "common_conclusion": _text_or_pending(item.get("common_conclusion")),
            }
        )
    negative_samples: list[dict[str, Any]] = []
    for item in sentiment_risk.get("items", []) or []:
        if not isinstance(item, dict):
            continue
        topics = [
            str(topic) for topic in item.get("negative_topics", []) or [] if topic
        ]
        conclusions = [
            _clip(conclusion.get("text"), 96)
            for conclusion in item.get("negative_conclusions", []) or []
            if isinstance(conclusion, dict) and conclusion.get("text")
        ]
        if not conclusions and item.get("answer_excerpt"):
            conclusions = [_clip(item.get("answer_excerpt"), 96)]
        if (
            str(item.get("sentiment") or "") != "negative"
            and not topics
            and not conclusions
        ):
            continue
        mapped_topics = _unique_values(
            CONCERN_LABELS.get(_map_negative_topic(topic), topic) for topic in topics
        )
        if not mapped_topics and item.get("answer_excerpt"):
            mapped_topics = _unique_values(
                CONCERN_LABELS.get(concern, concern)
                for concern in _infer_concerns_from_text(
                    str(item.get("answer_excerpt"))
                )
            )
        negative_samples.append(
            {
                "platform": item.get("platform"),
                "platform_label": _platform_label(item.get("platform")),
                "question_text": _clip(item.get("question_text"), 88),
                "mapped_concerns": mapped_topics,
                "conclusions": conclusions[:2],
            }
        )
    judgeable = brand_presence_count > 0
    if not judgeable:
        narrative = "本轮没有品牌提及样本，不能判断正向、中性、负向情绪；应先进入品牌未进入诊断。"
    else:
        narrative = "情绪分布用于观察 AI 回答语气和决策顾虑，负向信号需要进一步映射为价格门槛、证据充分性、适配边界等风险顾虑，不能直接写成品牌口碑负面。"
    return {
        "judgeable": judgeable,
        "distribution": {
            "positive": distribution.get("positive"),
            "neutral": distribution.get("neutral"),
            "negative": distribution.get("negative"),
        },
        "top_positive_reasons": top_positive_reasons,
        "negative_topics": negative_topics,
        "negative_samples": negative_samples[:8],
        "negative_source_distribution": negative_source_distribution,
        "risk_concern_narrative": risk_concern_analysis.get("summary", {}).get(
            "narrative"
        ),
        "narrative": narrative,
    }


def _preferred_source_labels(source_preferences: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for key, label in SOURCE_PREFERENCE_LABELS.items():
        if key == "other":
            continue
        strength = str(source_preferences.get(key) or "low")
        if strength in {"high", "medium"}:
            labels.append(label)
    return labels


def _build_platform_diagnostics(
    metric_bundle: dict[str, Any],
    *,
    scenario_items: list[dict[str, Any]],
) -> dict[str, Any]:
    profiles = (
        metric_bundle.get("platform_profiles")
        if isinstance(metric_bundle.get("platform_profiles"), dict)
        else {}
    )
    judgments = (
        metric_bundle.get("platform_judgments")
        if isinstance(metric_bundle.get("platform_judgments"), dict)
        else {}
    )
    question_diagnostics = (
        metric_bundle.get("question_diagnostics")
        if isinstance(metric_bundle.get("question_diagnostics"), dict)
        else {}
    )
    question_rows = [
        row
        for row in question_diagnostics.get("question_rows", []) or []
        if isinstance(row, dict)
    ]
    scenario_by_question = {
        str(item.get("question_id") or ""): str(item.get("decision_scenario") or "")
        for item in scenario_items
        if item.get("question_id")
    }
    platform_state_counts: dict[str, Counter[str]] = defaultdict(Counter)
    platform_scenario_counts: dict[str, dict[str, Counter[str]]] = defaultdict(
        lambda: defaultdict(Counter)
    )
    for row in question_rows:
        state_platforms = (
            row.get("state_platforms")
            if isinstance(row.get("state_platforms"), dict)
            else {}
        )
        scenario = scenario_by_question.get(str(row.get("question_id") or "")) or str(
            row.get("scene") or ""
        )
        for state, platforms in state_platforms.items():
            for platform in platforms or []:
                platform_key = str(platform or "")
                if not platform_key:
                    continue
                platform_state_counts[platform_key]["total"] += 1
                platform_state_counts[platform_key][str(state)] += 1
                if not _is_generic_label(scenario):
                    platform_scenario_counts[platform_key][scenario]["total"] += 1
                    if state in {"monitor_only", "monitor_plus_others"}:
                        platform_scenario_counts[platform_key][scenario][
                            "brand_entry"
                        ] += 1
                    if state in {"no_brand", "competitor_only"}:
                        platform_scenario_counts[platform_key][scenario]["missing"] += 1

    platform_names = sorted(set(profiles) | set(platform_state_counts))
    items: list[dict[str, Any]] = []
    for platform in platform_names:
        profile = (
            profiles.get(platform, {})
            if isinstance(profiles.get(platform), dict)
            else {}
        )
        states = platform_state_counts.get(platform, Counter())
        total = states.get("total", 0)
        brand_entry_count = states.get("monitor_only", 0) + states.get(
            "monitor_plus_others", 0
        )
        source_labels = _preferred_source_labels(
            profile.get("source_preferences", {})
            if isinstance(profile.get("source_preferences"), dict)
            else {}
        )
        scenario_counts = platform_scenario_counts.get(platform, {})
        friendly = [
            scenario
            for scenario, counts in sorted(
                scenario_counts.items(),
                key=lambda pair: (
                    -(
                        _safe_rate(
                            pair[1].get("brand_entry", 0), pair[1].get("total", 0)
                        )
                        or 0
                    ),
                    -pair[1].get("total", 0),
                    pair[0],
                ),
            )
            if counts.get("brand_entry", 0) > 0 and not _is_generic_label(scenario)
        ][:3]
        unfriendly = [
            scenario
            for scenario, counts in sorted(
                scenario_counts.items(),
                key=lambda pair: (
                    -(
                        _safe_rate(pair[1].get("missing", 0), pair[1].get("total", 0))
                        or 0
                    ),
                    -pair[1].get("total", 0),
                    pair[0],
                ),
            )
            if counts.get("missing", 0) > 0 and not _is_generic_label(scenario)
        ][:3]
        items.append(
            {
                "platform": platform,
                "platform_label": _platform_label(platform),
                "data_status": profile.get("data_status")
                or ("ok" if total else "missing"),
                "answer_sample_count": total,
                "brand_entry_count": brand_entry_count,
                "brand_entry_rate": _safe_rate(brand_entry_count, total),
                "no_brand_count": states.get("no_brand", 0),
                "competitor_only_count": states.get("competitor_only", 0),
                "comparison_answer_inclusion_rate": profile.get(
                    "comparison_answer_inclusion_rate"
                ),
                "dominant_logic_display": _text_or_pending(
                    profile.get("dominant_logic_display")
                ),
                "recommendation_pattern_display": _text_or_pending(
                    profile.get("recommendation_pattern_display")
                ),
                "brand_friendly_question_types": friendly[:3],
                "brand_unfriendly_question_types": unfriendly[:3],
                "source_preference_labels": source_labels,
            }
        )

    validation_platform = judgments.get("best_comparison_answer_breakthrough")
    return {
        "items": sorted(
            items,
            key=lambda item: (
                item["data_status"] != "ok",
                -(item["brand_entry_rate"] or 0),
                item["platform_label"],
            ),
        ),
        "judgments": judgments,
        "best_validation_platform": (
            {
                "platform": validation_platform,
                "platform_label": _platform_label(validation_platform),
            }
            if validation_platform
            else None
        ),
    }


def _build_sample_appendix(
    *,
    metric_bundle: dict[str, Any],
    scenario_items: list[dict[str, Any]],
    source_domains: list[dict[str, Any]],
    risk_items: list[dict[str, Any]],
) -> dict[str, Any]:
    question_diagnostics = (
        metric_bundle.get("question_diagnostics")
        if isinstance(metric_bundle.get("question_diagnostics"), dict)
        else {}
    )
    high_risk_rows = [
        row
        for row in question_diagnostics.get("risk_rows", []) or []
        if isinstance(row, dict)
    ]
    missing_rows = [
        item
        for item in scenario_items
        if item.get("brand_status") in {"no_brand", "competitor_only"}
    ]
    if not missing_rows:
        missing_rows = [
            item
            for item in scenario_items
            if item.get("brand_status") == "target_with_competitors"
        ]
    return {
        "scenario_count": len(scenario_items),
        "source_count": len(source_domains),
        "risk_concern_count": len(risk_items),
        "high_risk_questions": [
            {
                "question_text": _clip(row.get("question_text"), 88),
                "platforms": [
                    _platform_label(platform)
                    for platform in row.get("present_platforms", []) or []
                ],
                "answer_state": _brand_status_label(row.get("answer_state")),
                "risk_topics": [
                    CONCERN_LABELS.get(_map_negative_topic(str(topic)), str(topic))
                    for topic in row.get("negative_topics", []) or []
                ],
            }
            for row in high_risk_rows[:6]
        ],
        "missing_or_contested_questions": [
            {
                "decision_scenario": item.get("decision_scenario"),
                "question_text": _clip(item.get("question_text"), 88),
                "brand_status": _brand_status_label(item.get("brand_status")),
                "competitors_present": item.get("competitors_present", []) or [],
            }
            for item in missing_rows[:6]
        ],
        "unknown_sources": [
            {
                "domain": item.get("domain"),
                "site_name": item.get("site_name"),
                "site_display": item.get("site_display"),
                "ai_citation_frequency": item.get("ai_citation_frequency"),
                "sample_titles": item.get("sample_titles", []) or [],
            }
            for item in source_domains
            if item.get("source_type") == "unknown"
        ][:12],
        "source_samples": [
            {
                "domain": item.get("domain"),
                "site_name": item.get("site_name"),
                "site_display": item.get("site_display"),
                "source_type_label": item.get("source_type_label"),
                "ai_citation_frequency": item.get("ai_citation_frequency"),
                "sample_titles": item.get("sample_titles", []) or [],
            }
            for item in source_domains[:8]
        ],
        "risk_samples": [
            {
                "label": item.get("label"),
                "evidence": item.get("evidence", []) or [],
                "platform_counts": item.get("platform_counts", {}) or {},
            }
            for item in risk_items[:5]
        ],
    }


def build_structured_report(
    *,
    brand_name: str,
    report_kind: str,
    metric_bundle: dict[str, Any],
    data_audit: dict[str, Any],
    report_route: dict[str, Any],
    scenario_diagnostics: dict[str, Any],
    source_intelligence: dict[str, Any],
    risk_concern_analysis: dict[str, Any],
    action_recommendations: list[dict[str, Any]],
) -> dict[str, Any]:
    mode = str(data_audit.get("report_mode") or REPORT_MODE_BRAND_ENTRY)
    conclusions = build_diagnostic_conclusions(
        brand_name=brand_name,
        metric_bundle=metric_bundle,
        data_audit=data_audit,
        scenario_diagnostics=scenario_diagnostics,
        source_intelligence=source_intelligence,
        risk_concern_analysis=risk_concern_analysis,
        action_recommendations=action_recommendations,
    )
    scenario_items = [
        item
        for item in scenario_diagnostics.get("items", []) or []
        if isinstance(item, dict)
    ]
    scenario_summary = [
        item
        for item in scenario_diagnostics.get("summary", []) or []
        if isinstance(item, dict)
    ]
    source_domains = [
        item
        for item in source_intelligence.get("domains", []) or []
        if isinstance(item, dict)
    ]
    risk_items = [
        item
        for item in risk_concern_analysis.get("items", []) or []
        if isinstance(item, dict)
    ]
    retest_plan = _build_retest_plan(mode=mode, scenario_items=scenario_items)
    platform_diagnostics = _build_platform_diagnostics(
        metric_bundle,
        scenario_items=scenario_items,
    )
    core_metrics = _build_core_metrics(metric_bundle, data_audit)
    sentiment_probe = _build_sentiment_probe(metric_bundle, risk_concern_analysis)
    sample_appendix = _build_sample_appendix(
        metric_bundle=metric_bundle,
        scenario_items=scenario_items,
        source_domains=source_domains,
        risk_items=risk_items,
    )
    executive_summary = {
        "section_title": "高管版摘要",
        "one_line_judgment": (
            conclusions[0].get("summary") or conclusions[0].get("fact")
            if conclusions
            else f"{brand_name}已完成本轮 AI 答案品牌诊断。"
        ),
        "core_metrics": core_metrics,
        "key_findings": conclusions[:3],
        "top_actions": action_recommendations[:3],
        "not_judged": data_audit.get("not_judged", []),
    }
    operations_diagnosis = {
        "section_title": "运营版诊断",
        "mode": mode,
        "sections": report_route.get("operations_sections", []),
        "core_metrics": core_metrics,
        "diagnostic_conclusions": conclusions,
        "data_status": {
            "total_questions": _as_int(metric_bundle.get("total_questions")),
            "successful_answers": _as_int(metric_bundle.get("successful_answers")),
            "brand_presence_count": _as_int(metric_bundle.get("brand_presence_count")),
            "confidence": data_audit.get("confidence"),
            "metric_eligibility": data_audit.get("metric_eligibility", {}),
        },
        "brand_entry": {
            "brand_visibility": metric_bundle.get("brand_visibility"),
            "no_brand_rate": metric_bundle.get("no_brand_rate"),
            "competitor_pressure": metric_bundle.get("competitor_pressure"),
            "brand_rank": metric_bundle.get("brand_rank"),
            "ranked_brand_count": metric_bundle.get("ranked_brand_count"),
            "monitor_only_rate": metric_bundle.get("monitor_only_rate"),
            "monitor_plus_others_rate": metric_bundle.get("monitor_plus_others_rate"),
            "official_conversion_rate": metric_bundle.get("official_conversion_rate"),
            "official_funnel": metric_bundle.get("official_funnel", {}),
        },
        "scenario_map": scenario_items,
        "scenario_summary": scenario_summary,
        "source_evidence": source_intelligence,
        "sentiment_probe": sentiment_probe,
        "risk_concerns": risk_concern_analysis,
        "platform_diagnostics": platform_diagnostics,
        "action_recommendations": action_recommendations,
        "retest_plan": retest_plan,
        "sample_appendix": sample_appendix,
    }

    title = report_route.get("title") or "品牌 AI 答案诊断报告"
    lines = [
        f"# {brand_name}｜{title}",
        "",
        "## 高管版摘要",
        "",
        str(executive_summary["one_line_judgment"]),
        "",
        "### 核心指标",
        *[
            f"- **{item.get('label')}**：{item.get('value')}。{item.get('interpretation')}"
            for item in core_metrics
        ],
        "",
        "### 关键发现",
        *_render_conclusion_lines(executive_summary["key_findings"]),
        "",
        "### 优先动作",
        *_render_action_lines(action_recommendations[:3]),
        "",
        "## 运营版诊断",
        "",
    ]
    if mode == REPORT_MODE_NO_SIGNAL:
        competitor_scenarios = [
            item
            for item in scenario_items
            if item.get("brand_status") == "competitor_only"
        ]
        knowledge_scenarios = [
            item for item in scenario_items if item.get("brand_status") == "no_brand"
        ]
        lines.extend(
            [
                "### 1. 本轮结论",
                f"- 品牌是否进入答案：{brand_name}尚未进入本轮 AI 答案。",
                f"- 无品牌回答占比：{_format_rate(metric_bundle.get('no_brand_rate'))}。",
                f"- 是否出现竞品：{'出现竞品偶发进入。' if competitor_scenarios else '本轮未观察到稳定竞品进入。'}",
                "- 当前不能判断：情感、官网承接、平台偏好、品牌口碑。",
                "",
                "### 2. 问题触发类型",
            ]
        )
        lines.extend(
            [
                f"- **{item.get('decision_scenario')}**：{item.get('diagnosis')} 建议复采样问题「{_clip(item.get('question_text'), 44)}」。"
                for item in knowledge_scenarios[:4]
            ]
            or ["- 当前问题集尚未形成清晰触发类型，需要补充品牌比较和场景购买问题。"]
        )
        lines.extend(["", "### 3. 竞品偶发进入"])
        lines.extend(
            [
                f"- **{item.get('decision_scenario')}**：{'、'.join(item.get('competitors_present') or []) or '竞品'}进入答案，{brand_name}缺席；需要复核这是主动推荐还是顺带提及。"
                for item in competitor_scenarios[:4]
            ]
            or [
                f"- 竞品挤压率为 {_format_rate(metric_bundle.get('competitor_pressure'))}，本轮未形成稳定竞品挤压判断。"
            ]
        )
        lines.extend(["", "### 4. 内容缺口假设"])
        lines.extend(
            [
                f"- **{item.get('decision_scenario')}**：{item.get('content_gap')} 推荐资产：{item.get('recommended_asset')}。"
                for item in scenario_items[:5]
            ]
            or [
                "- 当前样本不足，需要补充安全合规、适用人群、价格理由、对比解释和购买渠道内容。"
            ]
        )
        lines.extend(
            [
                "",
                "### 5. 下一轮验证计划",
                f"- 新增问题：{', '.join(retest_plan['question_types'])}。",
                f"- 每类问题采样：{retest_plan['sample_size']}，覆盖 {'、'.join(retest_plan['platforms'])}。",
                f"- 观察指标：{'、'.join(retest_plan['metrics'])}。",
                f"- 进入完整报告阈值：{retest_plan['entry_threshold']}",
                "",
                "### 6. 暂不判断事项",
            ]
        )
        for item in data_audit.get("not_judged", []) or []:
            if isinstance(item, dict):
                lines.append(f"- **{item.get('label')}**：{item.get('reason')}")
    else:
        brand_entry = operations_diagnosis["brand_entry"]
        official_funnel = (
            brand_entry.get("official_funnel")
            if isinstance(brand_entry.get("official_funnel"), dict)
            else {}
        )
        rank_text = (
            f"#{brand_entry.get('brand_rank')}"
            if brand_entry.get("brand_rank")
            else "暂无足够数据支撑"
        )
        official_conversion = brand_entry.get("official_conversion_rate")
        lines.extend(
            [
                "### 1. 数据状态",
                f"- 问题/答案：本轮覆盖 {operations_diagnosis['data_status']['total_questions']} 个问题、{operations_diagnosis['data_status']['successful_answers']} 条有效答案；品牌提及 {operations_diagnosis['data_status']['brand_presence_count']} 条；报告模式：{_report_mode_label(mode)}。",
                f"- 进入拆解：品牌可见度 {_format_rate(brand_entry.get('brand_visibility'))}；只提品牌 {_format_rate(brand_entry.get('monitor_only_rate'))}；品牌与竞品同台 {_format_rate(brand_entry.get('monitor_plus_others_rate'))}；无品牌率 {_format_rate(brand_entry.get('no_brand_rate'))}；竞品挤压率 {_format_rate(brand_entry.get('competitor_pressure'))}。",
                f"- 排名/官网：品牌提及排名 {rank_text}；提及品牌答案 {official_funnel.get('monitor_brand_answer_count', 0)} 条，品牌相关链接答案 {official_funnel.get('brand_related_link_answer_count', 0)} 条，官网链接答案 {official_funnel.get('official_link_answer_count', 0)} 条；官网引用转化率 {_format_rate(official_conversion)}。",
                "- 读数说明：如果某项指标显示 0.0%，表示本轮样本没有观测到该类信号，不等于长期没有；需要结合样本标题和原始答案复核原因。",
                "",
                "### 2. 品牌进入能力",
                *_render_conclusion_lines(
                    [
                        item
                        for item in conclusions
                        if item.get("code") in {"data_status", "brand_entry"}
                    ]
                ),
                "",
                "### 3. 场景地图",
            ]
        )
        if scenario_summary:
            for item in scenario_summary[:8]:
                reps = "；".join(
                    f"「{question}」"
                    for question in item.get("representative_questions", [])[:2]
                )
                missing = "；".join(
                    f"「{question}」"
                    for question in item.get("missing_questions", [])[:2]
                )
                competitors = "、".join(item.get("competitors_present", []) or [])
                lines.append(
                    f"- **{item.get('decision_scenario')}**：问题 {item.get('question_count')} 个，进入率 {_format_rate(item.get('brand_entry_rate'))}，无品牌率 {_format_rate(item.get('no_brand_rate'))}，竞品单独进入 {item.get('competitor_only_count')} 个；决策阶段 {_journey_stage_label(item.get('journey_stage'))}，业务价值 {_business_value_label(item.get('business_value'))}。"
                )
                if reps:
                    lines.append(f"  - 代表问题：{reps}")
                if missing:
                    lines.append(f"  - 需要复盘：{missing}")
                if competitors:
                    lines.append(f"  - 同台/替代竞品：{competitors}")
                if item.get("content_gap") or item.get("recommended_asset"):
                    lines.append(
                        f"  - 内容缺口：{item.get('content_gap')} 推荐资产：{item.get('recommended_asset')}。"
                    )
        else:
            lines.append("- 当前问题样本不足以形成稳定场景地图。")
        lines.extend(["", "### 4. 来源证据权"])
        source_type_summary = [
            item
            for item in source_intelligence.get("summary", []) or []
            if isinstance(item, dict)
        ]
        if source_type_summary:
            lines.append("- 来源类型结构：")
            for item in source_type_summary[:6]:
                lines.append(
                    f"  - {item.get('source_type_label')}：出现 {item.get('ai_citation_frequency')} 次，占比 {_format_rate(item.get('citation_share'))}；{item.get('diagnosis')}"
                )
        if source_domains:
            lines.append("- 高频来源网站：")
            for item in source_domains[:8]:
                samples = "；".join(
                    f"「{title}」" for title in item.get("sample_titles", [])[:2]
                )
                sample_text = f"；样本标题：{samples}" if samples else ""
                lines.append(
                    f"  - {item.get('site_display') or item.get('domain')}：{item.get('source_type_label')}，出现 {item.get('ai_citation_frequency')} 次，占比 {_format_rate(item.get('citation_share'))}；推荐动作：{item.get('recommended_action')}{sample_text}"
                )
        if not source_type_summary and not source_domains:
            lines.append("- 当前没有形成稳定来源类型结构。")
        lines.extend(["", "### 5. 情绪探查"])
        distribution = sentiment_probe.get("distribution", {})
        lines.append(
            f"- 情绪分布：正向 {_format_rate(distribution.get('positive'))}；中性 {_format_rate(distribution.get('neutral'))}；负向/风险顾虑信号 {_format_rate(distribution.get('negative'))}。"
        )
        lines.append(
            "- 运营判断：负向/风险信号只作为问题排查入口，需要回到具体问题、平台和答案结论定位，不直接写成品牌口碑负面。"
        )
        positive_reasons = [
            item
            for item in sentiment_probe.get("top_positive_reasons", []) or []
            if isinstance(item, dict)
        ]
        if positive_reasons:
            lines.append("- 当前最常被认可的信息：")
            for item in positive_reasons[:4]:
                lines.append(
                    f"  - **{item.get('display')}**：出现率 {_format_rate(item.get('rate'))}；代表结论：{_text_or_pending(item.get('common_conclusion'))}"
                )
        else:
            lines.append("- 当前样本里还没有形成稳定的正向判断。")
        negative_samples = [
            item
            for item in sentiment_probe.get("negative_samples", []) or []
            if isinstance(item, dict)
        ]
        raw_negative_topics = [
            item
            for item in sentiment_probe.get("negative_topics", []) or []
            if isinstance(item, dict)
        ]
        negative_topics = [
            item
            for item in raw_negative_topics
            if not (
                _is_generic_label(item.get("display"))
                and str(item.get("mapped_concern") or "") in {"决策顾虑", "其他"}
            )
        ]
        if negative_topics:
            lines.append("- 负向信号对应的决策顾虑：")
            for item in negative_topics[:4]:
                lines.append(
                    f"  - **{item.get('display')} -> {item.get('mapped_concern')}**：出现率 {_format_rate(item.get('rate'))}；代表结论：{item.get('common_conclusion')}"
                )
        elif negative_samples:
            lines.append("- 当前负向/顾虑更适合按样本逐条定位，暂不汇总为泛化主题。")
        else:
            lines.append("- 当前没有稳定重复的负向/顾虑主题。")
        if negative_samples:
            lines.append("- 负向/顾虑样本定位：")
            for item in negative_samples[:5]:
                concerns = "、".join(item.get("mapped_concerns", []) or [])
                sample_conclusions = "；".join(
                    f"「{text}」" for text in item.get("conclusions", [])[:2]
                )
                lines.append(
                    f"  - **{item.get('platform_label')}**｜{concerns or '决策顾虑'}｜问题：{item.get('question_text')}；答案结论：{sample_conclusions or '暂无摘录'}"
                )
        source_distribution = (
            sentiment_probe.get("negative_source_distribution")
            if isinstance(sentiment_probe.get("negative_source_distribution"), dict)
            else {}
        )
        cited_source_rate = source_distribution.get("cited_source")
        mixed_source_rate = source_distribution.get("mixed")
        source_parts = []
        if cited_source_rate or mixed_source_rate:
            model_inference_rate = source_distribution.get("model_inference")
            if model_inference_rate:
                source_parts.append(
                    f"模型自身归纳 {_format_rate(model_inference_rate)}"
                )
            if cited_source_rate:
                source_parts.append(f"引用来源带出 {_format_rate(cited_source_rate)}")
            if mixed_source_rate:
                source_parts.append(f"混合 {_format_rate(mixed_source_rate)}")
        if source_parts:
            lines.append(f"- 负向信号来源：{'；'.join(source_parts)}。")

        lines.extend(["", "### 6. 风险顾虑"])
        risk_narrative = str(
            risk_concern_analysis.get("summary", {}).get("narrative") or ""
        )
        if risk_narrative:
            lines.append(risk_narrative)
        if risk_items:
            for item in risk_items[:6]:
                evidence = "；".join(
                    f"「{sample}」" for sample in item.get("evidence", [])[:2]
                )
                platform_counts = item.get("platform_counts", {}) or {}
                platform_text = "、".join(
                    f"{_platform_label(platform)} {count} 次"
                    for platform, count in platform_counts.items()
                    if count
                )
                lines.append(
                    f"- **{item.get('label')}**：出现 {item.get('count')} 次，占比 {_format_rate(item.get('share'))}。"
                )
                if platform_text:
                    lines.append(f"  - 平台分布：{platform_text}")
                if evidence:
                    lines.append(f"  - 样本证据：{evidence}")
        else:
            lines.append("- 当前没有稳定重复的风险顾虑。")
        lines.extend(["", "### 7. 平台差异"])
        platform_items = [
            item
            for item in platform_diagnostics.get("items", []) or []
            if isinstance(item, dict)
        ]
        if platform_items:
            for item in platform_items:
                friendly = "、".join(
                    item.get("brand_friendly_question_types", []) or []
                )
                unfriendly = "、".join(
                    item.get("brand_unfriendly_question_types", []) or []
                )
                source_pref = "、".join(item.get("source_preference_labels", []) or [])
                lines.append(
                    f"- **{item.get('platform_label')}**：样本 {item.get('answer_sample_count')} 条，品牌进入率 {_format_rate(item.get('brand_entry_rate'))}，比较类进入率 {_format_rate(item.get('comparison_answer_inclusion_rate'))}。"
                )
                lines.append(
                    f"  - 回答逻辑：{item.get('dominant_logic_display')}；推荐模式：{item.get('recommendation_pattern_display')}。"
                )
                lines.append(
                    f"  - 友好场景：{friendly or '暂无足够数据支撑'}；易缺席场景：{unfriendly or '暂无足够数据支撑'}；引用偏好：{source_pref or '暂无明显来源偏好'}。"
                )
            best_platform = platform_diagnostics.get("best_validation_platform")
            if isinstance(best_platform, dict):
                lines.append(
                    f"- 最适合先验证内容调整的平台：{best_platform.get('platform_label')}。"
                )
        else:
            lines.append("- 当前样本还不足，暂时看不出稳定的平台差异。")
        lines.extend(
            ["", "### 8. 行动建议", *_render_action_lines(action_recommendations)]
        )
        lines.extend(
            [
                "",
                "### 9. 复测计划",
                f"- 复测问题：{', '.join(retest_plan['question_types'])}。",
                f"- 采样要求：{retest_plan['sample_size']}。",
                f"- 观察指标：{'、'.join(retest_plan['metrics'])}。",
                "",
                "### 10. 样本附录",
                f"- 场景样本数：{sample_appendix['scenario_count']}；来源域名数：{sample_appendix['source_count']}；风险顾虑类型数：{sample_appendix['risk_concern_count']}。",
            ]
        )
        high_risk_questions = sample_appendix.get("high_risk_questions", []) or []
        if high_risk_questions:
            lines.append("- 高风险/需复盘问题：")
            for item in high_risk_questions[:5]:
                platforms = "、".join(item.get("platforms", []) or [])
                risk_topics = "、".join(item.get("risk_topics", []) or [])
                lines.append(
                    f"  - 当前状态：{item.get('answer_state') or '需复核'}；平台：{platforms or '暂无足够数据支撑'}；风险主题：{risk_topics or '暂不集中'}。{item.get('question_text')}"
                )
        missing_samples = (
            sample_appendix.get("missing_or_contested_questions", []) or []
        )
        if missing_samples:
            lines.append("- 缺席/同台问题样本：")
            for item in missing_samples[:5]:
                competitors = "、".join(item.get("competitors_present", []) or [])
                lines.append(
                    f"  - **{item.get('decision_scenario')}**：{_brand_status_label(item.get('brand_status'))}；竞品：{competitors or '未集中'}；问题：{item.get('question_text')}"
                )
        unknown_sources = sample_appendix.get("unknown_sources", []) or []
        if unknown_sources:
            lines.append("- 未知来源：")
            for item in unknown_sources[:8]:
                lines.append(
                    f"  - {item.get('site_display') or item.get('domain')}：出现 {item.get('ai_citation_frequency')} 次；{item.get('recommended_action') or '来源识别未返回有效分类，保留为未知来源。'}"
                )
        source_samples = sample_appendix.get("source_samples", []) or []
        if source_samples:
            lines.append("- 来源样本：")
            for item in source_samples[:5]:
                samples = "；".join(
                    f"「{title}」" for title in item.get("sample_titles", [])[:2]
                )
                lines.append(
                    f"  - {item.get('site_display') or item.get('domain')}：{item.get('source_type_label')}，出现 {item.get('ai_citation_frequency')} 次；{samples or '暂无标题样本'}"
                )

    markdown = sanitize_report_markdown(
        "\n".join(lines).strip(),
        risk_concern_analysis=risk_concern_analysis,
    )
    report_sections = [
        {
            "section_name": "executive_summary",
            "title": "高管版摘要",
            "markdown": markdown.split("## 运营版诊断")[0].strip(),
            "data": executive_summary,
        },
        {
            "section_name": "operations_diagnosis",
            "title": "运营版诊断",
            "markdown": (
                ("## 运营版诊断" + markdown.split("## 运营版诊断", 1)[1]).strip()
                if "## 运营版诊断" in markdown
                else ""
            ),
            "data": operations_diagnosis,
        },
    ]
    return {
        "report_markdown": markdown,
        "report_sections": report_sections,
        "executive_summary": executive_summary,
        "executive_report": executive_summary,
        "operations_diagnosis": operations_diagnosis,
        "diagnostic_conclusions": conclusions,
    }


def sanitize_report_markdown(
    markdown: str,
    *,
    risk_concern_analysis: dict[str, Any],
) -> str:
    sanitized = str(markdown or "")
    sanitized = sanitized.replace("N/A", "暂无足够数据支撑")
    for code, label in REPORT_MODE_LABELS.items():
        sanitized = sanitized.replace(f"报告模式：{code}", f"报告模式：{label}")
        sanitized = sanitized.replace(f"报告模式: {code}", f"报告模式：{label}")
    for code, label in JOURNEY_STAGE_LABELS.items():
        sanitized = sanitized.replace(f"决策阶段 {code}", f"决策阶段 {label}")
    for code, label in BUSINESS_VALUE_LABELS.items():
        sanitized = sanitized.replace(f"业务价值 {code}", f"业务价值 {label}")
    for code, label in BRAND_STATUS_LABELS.items():
        sanitized = sanitized.replace(f"品牌状态 {code}", f"品牌状态 {label}")
        sanitized = sanitized.replace(f"：{code}；", f"：{label}；")
    narrative = (
        risk_concern_analysis.get("summary", {}).get("narrative")
        if isinstance(risk_concern_analysis.get("summary"), dict)
        else ""
    )
    if narrative:
        sanitized = sanitized.replace(
            "负面信息比例不高，但几类顾虑已经开始重复出现。", str(narrative)
        )
        sanitized = sanitized.replace(
            "负面信息比例不高，但已经有几类顾虑在反复出现。", str(narrative)
        )
        sanitized = re.sub(
            r"[^。\n]{0,40}负面信息比例不高，但已经有几类会卡住决策的顾虑在重复出现。",
            str(narrative),
            sanitized,
        )
    return sanitized


def validate_report_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    markdown = str(artifact.get("report_markdown") or "")
    data_audit = (
        artifact.get("data_audit")
        if isinstance(artifact.get("data_audit"), dict)
        else {}
    )
    report_mode = data_audit.get("report_mode") or artifact.get("report_mode")
    metrics = (
        artifact.get("metrics") if isinstance(artifact.get("metrics"), dict) else {}
    )
    negative_rate = metrics.get("negative_rate")

    def add_issue(issue_id: str, message: str, *, repairable: bool = False) -> None:
        issues.append(
            {
                "id": issue_id,
                "message": message,
                "repairable": repairable,
            }
        )

    executive_summary = artifact.get("executive_summary")
    if not isinstance(executive_summary, dict):
        add_issue(
            "EXECUTIVE_SUMMARY_NOT_STRUCTURED",
            "executive_summary 必须是结构化对象。",
        )
    else:
        for field in (
            "section_title",
            "one_line_judgment",
            "core_metrics",
            "key_findings",
            "top_actions",
            "not_judged",
        ):
            if field not in executive_summary:
                add_issue(
                    "EXECUTIVE_SUMMARY_FIELD_MISSING",
                    f"executive_summary 缺少 {field}。",
                )
        if not isinstance(executive_summary.get("one_line_judgment"), str):
            add_issue(
                "EXECUTIVE_SUMMARY_TEXT_MISSING",
                "executive_summary.one_line_judgment 必须是字符串。",
            )
    if not isinstance(artifact.get("executive_summary_text"), str):
        add_issue(
            "EXECUTIVE_SUMMARY_TEXT_COMPAT_MISSING",
            "executive_summary_text 兼容字段必须是字符串。",
        )
    if not isinstance(artifact.get("operations_diagnosis"), dict):
        add_issue(
            "OPERATIONS_DIAGNOSIS_MISSING",
            "operations_diagnosis 必须是结构化对象。",
        )
    else:
        operations = artifact["operations_diagnosis"]
        if not isinstance(operations.get("core_metrics"), list):
            add_issue(
                "OPERATIONS_CORE_METRICS_MISSING",
                "operations_diagnosis 必须包含 core_metrics。",
            )
        if report_mode != REPORT_MODE_NO_SIGNAL and not isinstance(
            operations.get("sentiment_probe"), dict
        ):
            add_issue(
                "OPERATIONS_SENTIMENT_PROBE_MISSING",
                "非 NO_SIGNAL 报告必须包含 sentiment_probe。",
            )
    report_sections = artifact.get("report_sections")
    if not isinstance(report_sections, list):
        add_issue("REPORT_SECTIONS_MISSING", "report_sections 必须存在。")
    else:
        section_names = {
            str(section.get("section_name") or "")
            for section in report_sections
            if isinstance(section, dict)
        }
        if not {"executive_summary", "operations_diagnosis"} <= section_names:
            add_issue(
                "REPORT_SECTIONS_INCOMPLETE",
                "report_sections 必须包含 executive_summary 和 operations_diagnosis。",
            )

    diagnostic_conclusions = artifact.get("diagnostic_conclusions")
    if not isinstance(diagnostic_conclusions, list) or not diagnostic_conclusions:
        add_issue(
            "DIAGNOSTIC_CONCLUSIONS_MISSING",
            "diagnostic_conclusions 必须是非空数组。",
        )
    else:
        for index, conclusion in enumerate(diagnostic_conclusions, start=1):
            if not isinstance(conclusion, dict):
                add_issue(
                    "DIAGNOSTIC_CONCLUSION_INVALID",
                    f"第 {index} 条核心结论必须是对象。",
                )
                continue
            for field in _REQUIRED_CONCLUSION_FIELDS:
                if not str(conclusion.get(field) or "").strip():
                    add_issue(
                        "DIAGNOSTIC_CONCLUSION_FIELD_MISSING",
                        f"第 {index} 条核心结论缺少 {field}。",
                    )

    if "N/A" in markdown:
        add_issue(
            "NO_RAW_NA_IN_MARKDOWN",
            "用户可见报告正文不能直接展示 N/A。",
            repairable=True,
        )
    if report_mode == REPORT_MODE_NO_SIGNAL:
        forbidden_terms = [
            "品牌负向提及率",
            "情感与风险解析",
            "平台偏好分析",
            "官网承接不足",
            "负面信息比例不高",
        ]
        for term in forbidden_terms:
            if term in markdown:
                add_issue(
                    "NO_SIGNAL_FORBIDDEN_SECTION",
                    f"NO_SIGNAL 报告不能包含：{term}",
                    repairable=True,
                )
    if report_mode == REPORT_MODE_WEAK_SIGNAL:
        for term in ("稳定口碑", "明确平台偏好", "长期趋势"):
            if term in markdown:
                add_issue(
                    "WEAK_SIGNAL_STRONG_CLAIM",
                    f"WEAK_SIGNAL 报告不能包含强判断：{term}",
                    repairable=True,
                )
    if (
        isinstance(negative_rate, (int, float))
        and negative_rate > 0.5
        and "负面信息比例不高" in markdown
    ):
        add_issue(
            "NEGATIVE_RATE_CONFLICT",
            "高顾虑/负向比例不能写成负面信息比例不高。",
            repairable=True,
        )
    for index, recommendation in enumerate(
        artifact.get("action_recommendations", []) or [], start=1
    ):
        if not isinstance(recommendation, dict):
            continue
        for field in (
            "decision_scenario",
            "fact",
            "recommended_asset",
            "target_metric",
            "validation_plan",
        ):
            if not recommendation.get(field):
                add_issue(
                    "ACTION_RECOMMENDATION_INCOMPLETE",
                    f"第 {index} 条建议缺少 {field}。",
                )
    return {
        "pass": not issues,
        "issues": issues,
        "required_fixes": [issue["message"] for issue in issues],
    }


def repair_report_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    """Apply deterministic copy repairs before the final validator pass."""
    repaired = copy.deepcopy(artifact)
    history = list(repaired.get("repair_history", []) or [])

    def repair_markdown(replacement_map: dict[str, str]) -> None:
        markdown = str(repaired.get("report_markdown") or "")
        full_markdown = str(repaired.get("full_markdown") or "")
        for source, target in replacement_map.items():
            if source in markdown:
                markdown = markdown.replace(source, target)
                history.append(
                    {"repair": "replace_markdown", "from": source, "to": target}
                )
            if source in full_markdown:
                full_markdown = full_markdown.replace(source, target)
        repaired["report_markdown"] = markdown
        repaired["full_markdown"] = full_markdown or markdown

    risk_summary = (
        repaired.get("risk_concern_analysis", {}).get("summary", {})
        if isinstance(repaired.get("risk_concern_analysis"), dict)
        else {}
    )
    risk_narrative = str(
        risk_summary.get("narrative")
        or "本轮 AI 回答中的风险信号应按决策顾虑理解，不应直接写成品牌口碑负面。"
    )
    repair_markdown(
        {
            "N/A": "暂无足够数据支撑",
            "报告模式：NO_SIGNAL": "报告模式：品牌未进入",
            "报告模式：WEAK_SIGNAL": "报告模式：弱信号观察",
            "报告模式：BRAND_ENTRY": "报告模式：品牌已进入",
            "报告模式：FULL_LANDSCAPE": "报告模式：完整全景诊断",
            "决策阶段 awareness": "决策阶段 认知/趋势心智",
            "决策阶段 understanding": "决策阶段 理解/知识查询",
            "决策阶段 supplier_evaluation": "决策阶段 供应商/选项评估",
            "决策阶段 purchase_evaluation": "决策阶段 购买/选型决策",
            "决策阶段 value_validation": "决策阶段 价值验证",
            "决策阶段 fit_evaluation": "决策阶段 适配评估",
            "决策阶段 risk_validation": "决策阶段 风险验证",
            "决策阶段 trust_validation": "决策阶段 信任验证",
            "决策阶段 scenario_solution": "决策阶段 场景解决方案",
            "业务价值 high": "业务价值 高",
            "业务价值 medium": "业务价值 中",
            "业务价值 low": "业务价值 低",
            "品牌负向提及率": "决策顾虑观察",
            "官网承接不足": "当前尚不能判断官网承接",
            "品牌负面比例不高": risk_narrative,
            "负面信息比例不高": risk_narrative,
            "情感与风险解析": "风险顾虑诊断",
            "平台偏好分析": "平台样本观察",
            "稳定口碑": "弱信号口碑观察",
            "明确平台偏好": "平台差异观察",
            "长期趋势": "本轮样本观察",
        }
    )

    for section in repaired.get("report_sections", []) or []:
        if isinstance(section, dict) and isinstance(section.get("markdown"), str):
            section_markdown = section["markdown"]
            section_markdown = section_markdown.replace("N/A", "暂无足够数据支撑")
            section_markdown = section_markdown.replace(
                "负面信息比例不高", risk_narrative
            )
            section_markdown = section_markdown.replace(
                "品牌负面比例不高", risk_narrative
            )
            section_markdown = section_markdown.replace("稳定口碑", "弱信号口碑观察")
            section_markdown = section_markdown.replace("明确平台偏好", "平台差异观察")
            section_markdown = section_markdown.replace("长期趋势", "本轮样本观察")
            section["markdown"] = section_markdown

    repaired["repair_history"] = history
    return repaired


def extract_geo_report_diagnosis(artifact: dict[str, Any]) -> dict[str, Any]:
    """Return structured diagnosis modules for downstream skills and history reads."""
    if not isinstance(artifact, dict):
        return {
            "report_mode": REPORT_MODE_BRAND_ENTRY,
            "data_audit": {},
            "blocked_sections": [],
            "metric_eligibility": {},
            "scenario_diagnostics": {},
            "source_intelligence": {},
            "risk_concern_analysis": {},
            "action_recommendations": [],
            "not_judged": [],
            "judgment_policy": {},
        }
    data_audit = (
        artifact.get("data_audit")
        if isinstance(artifact.get("data_audit"), dict)
        else {}
    )
    metric_bundle = (
        artifact.get("metric_bundle")
        if isinstance(artifact.get("metric_bundle"), dict)
        else (
            artifact.get("metrics") if isinstance(artifact.get("metrics"), dict) else {}
        )
    )
    blocked_sections = [
        _canonical_judgment_topic(item)
        for item in data_audit.get("blocked_sections", []) or []
    ]
    not_judged_items = (
        data_audit.get("not_judged", []) if isinstance(data_audit, dict) else []
    )
    not_judged_codes = [
        _canonical_judgment_topic(item.get("code") or item.get("label"))
        for item in not_judged_items
        if isinstance(item, dict)
    ]
    metric_eligibility = (
        data_audit.get("metric_eligibility", {}) if isinstance(data_audit, dict) else {}
    )
    judgment_policy = {
        topic: {
            "judgeable": topic not in set(blocked_sections + not_judged_codes),
            "reason": next(
                (
                    str(item.get("reason") or "")
                    for item in not_judged_items
                    if isinstance(item, dict)
                    and _canonical_judgment_topic(item.get("code") or item.get("label"))
                    == topic
                ),
                "",
            ),
        }
        for topic in sorted(
            set(JUDGMENT_TOPIC_ALIASES) | set(blocked_sections) | set(not_judged_codes)
        )
    }
    return {
        "report_mode": data_audit.get("report_mode")
        or artifact.get("report_mode")
        or REPORT_MODE_BRAND_ENTRY,
        "data_audit": data_audit,
        "report_route": (
            artifact.get("report_route")
            if isinstance(artifact.get("report_route"), dict)
            else {}
        ),
        "metric_bundle": metric_bundle,
        "blocked_sections": blocked_sections,
        "metric_eligibility": metric_eligibility,
        "scenario_diagnostics": (
            artifact.get("scenario_diagnostics")
            if isinstance(artifact.get("scenario_diagnostics"), dict)
            else {}
        ),
        "source_intelligence": (
            artifact.get("source_intelligence")
            if isinstance(artifact.get("source_intelligence"), dict)
            else {}
        ),
        "risk_concern_analysis": (
            artifact.get("risk_concern_analysis")
            if isinstance(artifact.get("risk_concern_analysis"), dict)
            else {}
        ),
        "action_recommendations": (
            artifact.get("action_recommendations")
            if isinstance(artifact.get("action_recommendations"), list)
            else []
        ),
        "not_judged": (not_judged_items),
        "judgment_policy": judgment_policy,
    }


def is_geo_report_topic_judged(
    artifact_or_diagnosis: dict[str, Any],
    topic: str,
) -> bool:
    """Return whether a downstream skill may make conclusions about a topic."""
    diagnosis = (
        artifact_or_diagnosis
        if isinstance(artifact_or_diagnosis.get("judgment_policy"), dict)
        else extract_geo_report_diagnosis(artifact_or_diagnosis)
    )
    canonical_topic = _canonical_judgment_topic(topic)
    policy = diagnosis.get("judgment_policy")
    if isinstance(policy, dict) and canonical_topic in policy:
        item = policy.get(canonical_topic)
        if isinstance(item, dict):
            return bool(item.get("judgeable"))
    blocked = {
        _canonical_judgment_topic(item)
        for item in diagnosis.get("blocked_sections", []) or []
    }
    not_judged = {
        _canonical_judgment_topic(item.get("code") or item.get("label"))
        for item in diagnosis.get("not_judged", []) or []
        if isinstance(item, dict)
    }
    return canonical_topic not in blocked and canonical_topic not in not_judged


def require_geo_report_topic_judged(
    artifact_or_diagnosis: dict[str, Any],
    topic: str,
) -> dict[str, Any]:
    """Return a deterministic allow/block decision for follow-up skills."""
    diagnosis = (
        artifact_or_diagnosis
        if isinstance(artifact_or_diagnosis.get("judgment_policy"), dict)
        else extract_geo_report_diagnosis(artifact_or_diagnosis)
    )
    canonical_topic = _canonical_judgment_topic(topic)
    policy = diagnosis.get("judgment_policy", {})
    policy_item = policy.get(canonical_topic) if isinstance(policy, dict) else None
    judgeable = is_geo_report_topic_judged(diagnosis, canonical_topic)
    reason = (
        str(policy_item.get("reason") or "") if isinstance(policy_item, dict) else ""
    )
    if judgeable:
        return {
            "allowed": True,
            "topic": canonical_topic,
            "report_mode": diagnosis.get("report_mode"),
            "reason": reason or "该主题未被本轮数据审计阻断。",
        }
    return {
        "allowed": False,
        "topic": canonical_topic,
        "report_mode": diagnosis.get("report_mode"),
        "reason": reason or "该主题被本轮数据审计标记为暂不判断。",
        "fallback_action": "只输出数据诊断、采样建议或复测计划，不生成该主题的业务结论。",
    }
