"""Confidence signal artifact builders.

This module turns A4 citation data into an independent A7 ``confidence_signal``
artifact. The current implementation does not fetch full page DOM yet, but it
already applies a structured AICE 9C scoring model with:

- per-dimension score / max score / confidence / reasoning
- conservative hard-deduction handling for C6 / C9a / C9b
- overall confidence derived from evidence sufficiency
- actionable recommendations for low-scoring dimensions
"""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime, timezone
import re
from typing import Any
from urllib.parse import urlparse

from app.services.page_feature_service import fetch_page_features


AICE_DIMENSIONS: list[dict[str, Any]] = [
    {"key": "c6", "label": "C6: Coverage (覆盖度)", "max_score": 25},
    {"key": "c9a", "label": "C9a: Semantic Tagging", "max_score": 10},
    {"key": "c9b", "label": "C9b: Schema Usage", "max_score": 10},
    {"key": "c8", "label": "C8: Timeliness (时效性)", "max_score": 15},
    {"key": "c1", "label": "C1: Credibility (信源可信度)", "max_score": 10},
    {"key": "c4", "label": "C4: Claim Balance (宣传平衡性)", "max_score": 10},
    {"key": "c2", "label": "C2: Consistency (内容一致性)", "max_score": 5},
    {"key": "c3", "label": "C3: Checkability (可核查性)", "max_score": 5},
    {"key": "c5", "label": "C5: Clarity (结构清晰度)", "max_score": 5},
    {"key": "c7", "label": "C7: Intent Match (意图匹配)", "max_score": 5},
]
DEFAULT_AICE_THRESHOLD = 75.0
DEFAULT_FREQUENCY_THRESHOLD = 1.0
ENTITY_LABELS = {
    "brand": "我方阵营",
    "competitor": "竞方阵营",
    "general_knowledge": "共业阵营",
}
DIMENSION_PLAIN_LABELS = {
    "c6": "可访问性",
    "c9a": "结构清晰度",
    "c9b": "结构化信息",
    "c8": "时效性",
    "c1": "来源可信度",
    "c4": "客观度",
    "c2": "一致性",
    "c3": "可核查性",
    "c5": "主题表达",
    "c7": "场景匹配度",
}
TECHNICAL_DIMENSION_KEYS = {"c6", "c9a", "c9b"}
QUADRANT_META: dict[str, dict[str, str]] = {
    "q1_anchor": {
        "label": "定海神针",
        "description": "高频且高置信，语料纯粹，AI 提取稳定。",
        "strategy": "提炼优秀基因，固化内容生产 SOP。",
    },
    "q2_false_prosperity": {
        "label": "虚假繁荣",
        "description": "高频但低置信，当前被引用却缺乏稳固质量支撑。",
        "strategy": "重点修缮区域，净化语料或用更高质量内容降维覆盖。",
    },
    "q3_noise": {
        "label": "沉寂噪音",
        "description": "低频且低置信，不被青睐且质量不足。",
        "strategy": "战略性放弃，不优先投入资源。",
    },
    "q4_sleeping_asset": {
        "label": "高潜伏藏",
        "description": "低频但高置信，质量优良但还未充分被唤醒。",
        "strategy": "保持定力，确保持续可用并等待提示词触发。",
    },
}
ANALYSIS_GROUP_META: dict[str, dict[str, str]] = {
    "brand_q1": {
        "title": "我方阵地：坚如磐石（善因固化）",
        "description": "第一象限中的我方语料，是品牌在 AI 语境中的稳定根基，应提炼模板与生产规范。",
        "reason_label": "高置信度归因分析",
        "action_label": "修我/行动指南",
    },
    "competitor_q1": {
        "title": "竞方阵地：坚如磐石（见贤思齐）",
        "description": "第一象限中的竞品语料，说明对方已经形成稳定投喂，应客观拆解并对标补齐。",
        "reason_label": "高置信度归因分析",
        "action_label": "修我/行动指南",
    },
    "brand_q2": {
        "title": "我方阵地：被引用但置信度不高（发露修缮）",
        "description": "第二象限中的我方语料虽然已被引用，但底层脆弱，是当前最优先的修缮对象。",
        "reason_label": "低置信度归因分析",
        "action_label": "修我/行动指南",
    },
    "competitor_q2": {
        "title": "竞方阵地：被引用但置信度不高（法施填补）",
        "description": "第二象限中的竞品语料通常意味着行业供给不足，可通过更高质量内容实现替代。",
        "reason_label": "低置信度归因分析",
        "action_label": "修我/行动指南",
    },
}

OFFICIAL_TLDS = (".gov", ".edu", ".org")
EVERGREEN_HINTS = (
    "guide",
    "docs",
    "documentation",
    "faq",
    "help",
    "about",
    "learn",
    "manual",
    "教程",
    "指南",
    "说明",
    "帮助",
    "文档",
)
ABSOLUTE_CLAIMS = (
    "唯一",
    "第一",
    "最好",
    "最强",
    "顶级",
    "领先",
    "权威",
    "最佳",
    "no.1",
    "best",
    "leading",
    "world-class",
    "guarantee",
    "100%",
)
CHECKABLE_CUES = (
    "报告",
    "研究",
    "white paper",
    "doi",
    "paper",
    "公告",
    "财报",
    "数据",
    "according to",
    "来源",
    "source",
)
SOURCE_CUES = (
    "官网",
    "official",
    "ministry",
    "university",
    "institute",
    "press release",
    "公告",
    "研究院",
    "协会",
)
INTENT_CUES = (
    "how",
    "what",
    "why",
    "guide",
    "教程",
    "怎么",
    "如何",
    "是什么",
    "区别",
    "对比",
)
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_url(url: str) -> str:
    normalized = (url or "").strip()
    if not normalized:
        return ""
    try:
        parsed = urlparse(normalized)
        if not parsed.scheme:
            normalized = f"https://{normalized}"
            parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""
        return parsed.geturl()
    except Exception:
        return ""


def _extract_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _now_year() -> int:
    return datetime.now(timezone.utc).year


def _clip_score(value: float, max_score: int) -> float:
    return round(max(0.0, min(float(max_score), value)), 1)


def _clamp_confidence(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 2)


def _classify_signal_level(score: float) -> str:
    if score >= 82:
        return "high"
    if score >= 68:
        return "neutral"
    return "caution"


def _collapse_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = (text or "").lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _keyword_hits(text: str, keywords: tuple[str, ...]) -> int:
    lowered = (text or "").lower()
    return sum(1 for keyword in keywords if keyword.lower() in lowered)


def _extract_years(text: str) -> list[int]:
    matches = re.findall(r"\b(19\d{2}|20\d{2})\b", text or "")
    years = [int(match) for match in matches]
    return [year for year in years if 1900 <= year <= _now_year() + 1]


def _normalize_tokens(text: str) -> set[str]:
    ascii_tokens = {
        token
        for token in re.findall(r"[a-z0-9]{2,}", (text or "").lower())
        if len(token) >= 2
    }
    cjk_tokens = {
        token
        for token in re.findall(r"[\u4e00-\u9fff]{2,6}", text or "")
        if len(token) >= 2
    }
    return ascii_tokens | cjk_tokens


def _looks_like_pure_url_line(line: str) -> bool:
    stripped = (line or "").strip()
    if not stripped or any(ch.isspace() for ch in stripped):
        return False
    return bool(
        re.match(
            r"^(https?://|www\.|[a-z0-9][a-z0-9.-]*\.[a-z]{2,})(/.*)?$",
            stripped,
            re.IGNORECASE,
        )
    )

def _guess_core_path(url: str) -> bool:
    parsed = urlparse(url or "")
    if not parsed.netloc:
        return False
    path = parsed.path.strip("/")
    if not path:
        return True
    segments = [segment for segment in path.split("/") if segment]
    if len(segments) > 3:
        return False
    if parsed.query:
        return False
    if re.search(r"\.(pdf|jpg|jpeg|png|zip|docx?)$", path, re.IGNORECASE):
        return False
    return True


def _domain_authority(domain: str, is_official: bool) -> tuple[float, float, str]:
    normalized = (domain or "").lower()
    if is_official:
        return 9.5, 0.9, "引用已标记为官方来源。"
    if normalized.endswith(".gov") or ".gov." in normalized:
        return 9.0, 0.88, "政府域名通常具备较高公信力。"
    if normalized.endswith(".edu") or ".edu." in normalized:
        return 8.6, 0.84, "教育机构域名通常具备较强权威性。"
    if normalized.endswith(".org") or ".org." in normalized:
        return 7.4, 0.7, "组织机构域名具备一定公信力，但仍需结合内容核验。"
    if normalized:
        return 6.0, 0.62, "存在明确域名，但未见官方或公共机构信号。"
    return 4.0, 0.42, "缺少来源主体信息，可信度判断证据不足。"


def _make_dimension(
    key: str,
    score: float,
    confidence: float,
    reasoning: str,
) -> dict[str, Any]:
    definition = next(item for item in AICE_DIMENSIONS if item["key"] == key)
    return {
        "key": key,
        "label": definition["label"],
        "max_score": definition["max_score"],
        "score": _clip_score(score, definition["max_score"]),
        "confidence": _clamp_confidence(confidence),
        "reasoning": reasoning,
    }


def _score_url_coverage(meta: dict[str, Any]) -> dict[str, Any]:
    url = str(meta.get("url", "") or "")
    if not url:
        return _make_dimension("c6", 0, 0.95, "链接不可用，C6 技术可访问性直接记 0 分。")
    if meta.get("crawl_readable") is False and meta.get("http_status") is not None:
        return _make_dimension(
            "c6",
            0,
            0.96,
            f"页面抓取失败（HTTP {meta.get('http_status')}），C6 技术可访问性直接记 0 分。",
        )

    score = 14.0
    reasons = ["链接可访问，具备基础技术可读性。"]
    if url.startswith("https://"):
        score += 3
        reasons.append("使用 HTTPS。")
    if _guess_core_path(url):
        score += 4
        reasons.append("URL 位于较核心路径。")
    occurrences = int(meta.get("occurrences", 0) or 0)
    if occurrences >= 3:
        score += 4
        reasons.append("在多条回答中重复出现，说明覆盖权重较高。")
    elif occurrences == 2:
        score += 2
        reasons.append("已被多次引用。")
    if bool(meta.get("is_official")):
        score += 4
        reasons.append("来源带有官方属性。")
    score = min(score, 25.0)
    confidence = 0.86 if occurrences > 0 else 0.72
    return _make_dimension("c6", score, confidence, "".join(reasons))


def _score_url_semantic(meta: dict[str, Any]) -> dict[str, Any]:
    if meta.get("crawl_readable"):
        has_h1 = bool(meta.get("has_h1"))
        has_structure = bool(meta.get("has_main")) or bool(meta.get("has_article"))
        if not has_h1 or not has_structure:
            missing = []
            if not has_h1:
                missing.append("H1")
            if not has_structure:
                missing.append("main/article")
            return _make_dimension(
                "c9a",
                5.0,
                0.9,
                f"已抓到页面 HTML，但缺少 {' 和 '.join(missing)}，按 C9a 硬性扣分逻辑扣 5 分。",
            )

        score = 8.5
        if int(meta.get("h1_count", 0) or 0) == 1:
            score += 0.8
        return _make_dimension(
            "c9a",
            min(score, 10.0),
            0.92,
            "已确认页面存在 H1，且具备 main/article 等关键结构标签，语义结构较完整。",
        )

    has_title = bool(meta.get("title"))
    has_site = bool(meta.get("site_name"))
    if has_title and has_site and _guess_core_path(str(meta.get("url", "") or "")):
        score = 6.0
        reasoning = "当前只有 citation 元数据，未直接抓取 DOM；暂未确认 H1/main/article，先按结构证据部分存在保守给 6 分。"
    else:
        score = 5.0
        reasoning = "未抓取页面 DOM，未发现 H1 或关键结构标签证据，按 C9a 硬性扣分逻辑先扣 5 分。"
    return _make_dimension("c9a", score, 0.34, reasoning)


def _score_url_schema(meta: dict[str, Any]) -> dict[str, Any]:
    schema_types = meta.get("schema_types", []) or []
    if meta.get("crawl_readable"):
        if schema_types:
            return _make_dimension(
                "c9b",
                min(8.5 + min(len(schema_types), 2) * 0.6, 10.0),
                0.94,
                f"已发现 Schema.org 结构化数据：{', '.join(schema_types[:3])}。",
            )
        return _make_dimension(
            "c9b",
            5.0,
            0.94,
            "已抓取页面 HTML，但未发现 Schema.org 标记，按 C9b 硬性扣分逻辑扣 5 分。",
        )

    domain = str(meta.get("domain", "") or "")
    is_official = bool(meta.get("is_official"))
    if is_official or domain.endswith(OFFICIAL_TLDS):
        score = 6.0
        reasoning = "未直接抓到 Schema.org 标记，但官方/机构站点较可能存在结构化数据，先保守给 6 分。"
    else:
        score = 5.0
        reasoning = "当前未发现 Schema.org 证据，按 C9b 硬性扣分逻辑先扣 5 分。"
    return _make_dimension("c9b", score, 0.28, reasoning)


def _score_url_timeliness(meta: dict[str, Any]) -> dict[str, Any]:
    evidence_text = " ".join(
        [
            str(meta.get("title", "") or ""),
            str(meta.get("url", "") or ""),
            str(meta.get("site_name", "") or ""),
            str(meta.get("published_at", "") or ""),
        ]
    )
    years = _extract_years(evidence_text)
    current_year = _now_year()
    if years:
        latest = max(years)
        gap = current_year - latest
        if gap <= 1:
            score = 14.0
            reasoning = f"页面中出现 {latest} 年信息，更新较新。"
            confidence = 0.74
        elif gap <= 3:
            score = 11.5
            reasoning = f"页面中出现 {latest} 年信息，仍有一定时效性，但需确认是否已有更新。"
            confidence = 0.72
        else:
            score = 7.5
            reasoning = f"页面主要停留在 {latest} 年信息，内容可能已经老化。"
            confidence = 0.76
    elif _contains_any(evidence_text, EVERGREEN_HINTS):
        score = 12.0
        reasoning = "未见明确发布日期，但内容更像文档/FAQ/说明类常青信息。"
        confidence = 0.56
    else:
        score = 9.0
        reasoning = "未发现清晰日期证据，按中性偏保守处理。"
        confidence = 0.46
    return _make_dimension("c8", score, confidence, reasoning)


def _score_url_credibility(meta: dict[str, Any]) -> dict[str, Any]:
    score, confidence, reason = _domain_authority(
        str(meta.get("domain", "") or ""),
        bool(meta.get("is_official")),
    )
    site_name = str(meta.get("site_name", "") or "")
    if site_name:
        reason += " 存在明确站点名称。"
        score += 0.5
    return _make_dimension("c1", min(score, 10.0), confidence, reason)


def _score_url_claim_balance(meta: dict[str, Any]) -> dict[str, Any]:
    title = " ".join(
        [str(meta.get("title", "") or ""), str(meta.get("site_name", "") or "")]
    )
    hype_hits = _keyword_hits(title, ABSOLUTE_CLAIMS)
    if hype_hits == 0:
        score = 8.8
        reasoning = "标题和来源信息未见明显绝对化或夸大表述。"
    elif hype_hits == 1:
        score = 6.4
        reasoning = "存在单个偏营销化表述，需注意宣传倾向。"
    else:
        score = 4.2
        reasoning = "出现多处绝对化/宣传化词汇，宣传平衡性较弱。"
    return _make_dimension("c4", score, 0.58, reasoning)


def _score_url_consistency(meta: dict[str, Any]) -> dict[str, Any]:
    if bool(meta.get("is_official")):
        return _make_dimension("c2", 4.6, 0.64, "官方来源与主流事实偏差风险较低。")
    if _contains_any(str(meta.get("title", "") or ""), ABSOLUTE_CLAIMS):
        return _make_dimension("c2", 3.0, 0.42, "标题带有较强主观表达，一致性需二次核查。")
    return _make_dimension("c2", 3.8, 0.48, "暂无明显冲突信号，但缺少外部交叉验证。")


def _score_url_checkability(meta: dict[str, Any]) -> dict[str, Any]:
    title = str(meta.get("title", "") or "")
    score = 2.6
    reasons = []
    if bool(meta.get("is_official")):
        score += 1.4
        reasons.append("官方来源可直接回查。")
    if _contains_any(title, CHECKABLE_CUES):
        score += 0.8
        reasons.append("标题带有报告/数据/公告等可核查线索。")
    if _extract_years(" ".join([title, str(meta.get("url", "") or "")])):
        score += 0.4
        reasons.append("存在年份线索。")
    if not reasons:
        reasons.append("当前只有 citation 元数据，可核查线索有限。")
    return _make_dimension("c3", min(score, 5.0), 0.58, "".join(reasons))


def _score_url_clarity(meta: dict[str, Any]) -> dict[str, Any]:
    title = _collapse_text(str(meta.get("title", "") or ""))
    length = len(title)
    if 8 <= length <= 80:
        score = 4.4
        reasoning = "标题长度适中，可快速理解页面主题。"
    elif title:
        score = 3.6
        reasoning = "标题可读，但长度或信息密度一般。"
    else:
        score = 2.6
        reasoning = "缺少清晰标题，结构清晰度偏弱。"
    return _make_dimension("c5", score, 0.72, reasoning)


def _score_url_intent_match(meta: dict[str, Any]) -> dict[str, Any]:
    title_tokens = _normalize_tokens(
        " ".join([str(meta.get("title", "") or ""), str(meta.get("domain", "") or "")])
    )
    question_tokens: set[str] = set()
    for question in meta.get("question_samples", []) or []:
        question_tokens |= _normalize_tokens(str(question))

    overlap = len(title_tokens & question_tokens)
    if overlap >= 3:
        score = 4.8
        reasoning = "标题和被引用问题之间存在较高主题重合，意图匹配度较强。"
    elif overlap >= 1:
        score = 4.1
        reasoning = "标题与问题存在一定主题重合。"
    elif _contains_any(str(meta.get("title", "") or ""), INTENT_CUES):
        score = 3.8
        reasoning = "标题呈现解释型/问答型表达，具备一定大众查询意图适配性。"
    else:
        score = 3.2
        reasoning = "缺少直接的意图匹配证据，按中性偏保守处理。"
    return _make_dimension("c7", score, 0.56, reasoning)


def _text_structure_stats(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    paragraphs = [block.strip() for block in re.split(r"\n\s*\n", cleaned) if block.strip()]
    heading_like_lines = [
        line
        for line in lines
        if len(line) <= 24 and not re.search(r"[。.!?]$", line)
    ]
    return {
        "length": len(cleaned),
        "line_count": len(lines),
        "paragraph_count": len(paragraphs),
        "heading_count": len(heading_like_lines),
        "has_links": "http://" in cleaned or "https://" in cleaned,
        "has_numbers": bool(re.search(r"\d", cleaned)),
        "years": _extract_years(cleaned),
    }


def _score_text_coverage(text: str, stats: dict[str, Any]) -> dict[str, Any]:
    length = int(stats["length"])
    paragraphs = int(stats["paragraph_count"])
    if length < 80:
        score = 9.0
        reasoning = "文本已直接可访问，但内容过短，覆盖度不足。"
    else:
        score = 16.0
        reasoning = "文本可直接评估，具备基础可访问性。"
        if length >= 280:
            score += 5
            reasoning += " 内容长度较充分。"
        if paragraphs >= 3:
            score += 4
            reasoning += " 分段较完整。"
    return _make_dimension("c6", min(score, 25.0), 0.92, reasoning)


def _score_text_semantic(stats: dict[str, Any]) -> dict[str, Any]:
    paragraphs = int(stats["paragraph_count"])
    headings = int(stats["heading_count"])
    if headings >= 2 or paragraphs >= 4:
        score = 8.0
        reasoning = "文本具备较清晰的分段/小标题结构。"
    elif paragraphs >= 2:
        score = 6.5
        reasoning = "文本存在基本分段，但结构层次仍可加强。"
    else:
        score = 5.0
        reasoning = "纯文本缺少明显结构标签或段落层次，按 C9a 保守扣 5 分。"
    return _make_dimension("c9a", score, 0.82, reasoning)


def _score_text_schema(text: str, stats: dict[str, Any]) -> dict[str, Any]:
    score = 5.0
    reasoning = "纯文本输入不带网页 Schema，当前转按来源元信息完整度保守记 5 分。"
    if stats["has_links"] and _contains_any(text, SOURCE_CUES):
        score = 6.5
        reasoning = "文本虽然不是网页，但包含来源主体和外链，可视为结构化元信息较完整。"
    return _make_dimension("c9b", score, 0.36, reasoning)


def _score_text_timeliness(text: str, stats: dict[str, Any]) -> dict[str, Any]:
    years = list(stats["years"])
    current_year = _now_year()
    if years:
        latest = max(years)
        gap = current_year - latest
        if gap <= 1:
            score = 14.0
            reasoning = f"文本中出现 {latest} 年信息，更新较新。"
            confidence = 0.82
        elif gap <= 3:
            score = 11.0
            reasoning = f"文本中出现 {latest} 年信息，仍有一定时效性。"
            confidence = 0.8
        else:
            score = 7.0
            reasoning = f"文本主要停留在 {latest} 年信息，可能已经过期。"
            confidence = 0.83
    elif _contains_any(text, EVERGREEN_HINTS):
        score = 12.0
        reasoning = "未见明确日期，但文本更像常青说明或教程。"
        confidence = 0.58
    else:
        score = 9.0
        reasoning = "缺少日期线索，时效性判断证据不足。"
        confidence = 0.48
    return _make_dimension("c8", score, confidence, reasoning)


def _score_text_credibility(text: str, stats: dict[str, Any]) -> dict[str, Any]:
    score = 4.8
    reasoning = "纯文本默认缺少来源主体，可信度按中低位起评。"
    if _contains_any(text, SOURCE_CUES):
        score = 7.0
        reasoning = "文本明确提到机构/官方来源，可信度提升。"
    if stats["has_links"]:
        score += 1.0
        reasoning += " 同时附带外部链接。"
    return _make_dimension("c1", min(score, 10.0), 0.55, reasoning)


def _score_text_claim_balance(text: str) -> dict[str, Any]:
    hype_hits = _keyword_hits(text, ABSOLUTE_CLAIMS)
    if hype_hits == 0:
        score = 8.6
        reasoning = "文本表达较中性，未见明显绝对化宣传。"
    elif hype_hits == 1:
        score = 6.2
        reasoning = "存在少量绝对化表述，建议收敛宣传性。"
    else:
        score = 3.8
        reasoning = "出现多处夸大或排他性表述，宣传平衡性较弱。"
    return _make_dimension("c4", score, 0.84, reasoning)


def _score_text_consistency(text: str) -> dict[str, Any]:
    if _contains_any(text, SOURCE_CUES) and not _contains_any(text, ABSOLUTE_CLAIMS):
        return _make_dimension("c2", 4.2, 0.62, "文本存在归因或来源提示，且主观性较低。")
    if _contains_any(text, ABSOLUTE_CLAIMS):
        return _make_dimension("c2", 2.8, 0.58, "绝对化表达较多，与主流事实的一致性需要谨慎核查。")
    return _make_dimension("c2", 3.6, 0.52, "未见明显冲突点，但缺少外部交叉验证。")


def _score_text_checkability(text: str, stats: dict[str, Any]) -> dict[str, Any]:
    score = 2.0
    reasons = []
    if stats["has_links"]:
        score += 1.5
        reasons.append("包含外部链接。")
    if stats["has_numbers"]:
        score += 0.8
        reasons.append("包含数字信息。")
    if _contains_any(text, CHECKABLE_CUES):
        score += 0.7
        reasons.append("提及报告/数据/来源等核查线索。")
    if not reasons:
        reasons.append("当前缺少明确外部核查抓手。")
    return _make_dimension("c3", min(score, 5.0), 0.78, "".join(reasons))


def _score_text_clarity(text: str, stats: dict[str, Any]) -> dict[str, Any]:
    paragraphs = int(stats["paragraph_count"])
    length = int(stats["length"])
    if paragraphs >= 3 and length >= 200:
        score = 4.6
        reasoning = "文本结构完整，逻辑与段落划分较清晰。"
    elif paragraphs >= 2:
        score = 3.9
        reasoning = "文本基本清晰，但层次还可以更明确。"
    else:
        score = 3.0
        reasoning = "文本更像单段描述，清晰度一般。"
    return _make_dimension("c5", score, 0.9, reasoning)


def _score_text_intent_match(text: str) -> dict[str, Any]:
    if _contains_any(text, INTENT_CUES):
        return _make_dimension("c7", 4.3, 0.72, "文本呈现问答/解释型表达，较贴近大众查询意图。")
    if len(text) >= 120:
        return _make_dimension("c7", 3.7, 0.64, "文本具备一定解释性，但大众搜索意图不够明确。")
    return _make_dimension("c7", 3.0, 0.58, "文本偏短，意图匹配证据有限。")


def _summarize_top_signals(dimensions: list[dict[str, Any]]) -> list[str]:
    ranked = sorted(
        dimensions,
        key=lambda item: (
            float(item.get("score", 0.0)) / max(float(item.get("max_score", 1.0)), 1.0),
            float(item.get("confidence", 0.0)),
        ),
        reverse=True,
    )
    signals = []
    for item in ranked:
        ratio = float(item.get("score", 0.0)) / max(float(item.get("max_score", 1.0)), 1.0)
        if ratio < 0.74:
            continue
        label = str(item.get("label", "") or "").split(":", 1)[0]
        reasoning = str(item.get("reasoning", "") or "")
        summary = reasoning.split("。", 1)[0].strip() or "信号较强"
        signals.append(f"{label} 较强: {summary}")
        if len(signals) >= 3:
            break
    if not signals:
        return ["整体证据仍偏有限", "建议优先查看低分维度并补强来源证据"]
    return signals


def _build_recommendations(
    *,
    input_type: str,
    dimensions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []

    def add(title: str, action: str, reason: str) -> None:
        recommendations.append(
            {
                "title": title,
                "action": action,
                "reason": reason,
            }
        )

    by_key = {str(item["key"]): item for item in dimensions}

    if float(by_key["c9a"]["score"]) <= 6:
        if input_type == "url":
            add(
                "补充语义结构标签",
                "为页面补齐唯一 H1，并明确使用 main/article/section 等语义标签组织正文。",
                "C9a 偏低会让页面结构更难被模型稳定理解。",
            )
        else:
            add(
                "增加文本层次",
                "把内容拆成小标题 + 段落 + 列表，避免整段堆叠。",
                "C9a 偏低说明结构层次不够清晰。",
            )

    if float(by_key["c9b"]["score"]) <= 6:
        if input_type == "url":
            add(
                "补充 Schema.org 标记",
                "在页面 head 中增加 JSON-LD，例如 Organization / Article / FAQPage 等结构化数据。",
                "C9b 偏低会削弱模型和搜索系统对页面实体与主题的识别效率。",
            )
        else:
            add(
                "补充来源元信息",
                "在文本中明确作者、机构、发布时间和原始来源链接。",
                "纯文本没有网页 Schema，需要用显式元信息弥补结构化缺口。",
            )

    if float(by_key["c8"]["score"]) <= 9:
        add(
            "补强时效信息",
            "补充明确发布日期、版本号或最近更新时间；若数据过旧，优先替换为最近 1-2 年的数据。",
            "C8 偏低会直接影响模型是否采信当前表述。",
        )

    if float(by_key["c4"]["score"]) <= 6.5:
        add(
            "收敛宣传表述",
            "删除“唯一 / 最强 / 第一 / 100%”等绝对化词汇，改成可归因、可验证的中性描述。",
            "C4 偏低说明内容宣传性过强，会降低 AI 采信稳定性。",
        )

    if float(by_key["c3"]["score"]) <= 3.2:
        add(
            "增加可核查证据",
            "补充官方公告、研究报告、财报、标准文档或 DOI 链接，并保留关键数字来源。",
            "C3 偏低意味着外部验证抓手不足。",
        )

    if float(by_key["c1"]["score"]) <= 6:
        add(
            "强化来源主体",
            "优先使用官网、政府、教育机构或正式发布渠道作为主链接，并在正文中显式标注来源名称。",
            "C1 偏低会直接拉低整体可信度。",
        )

    return recommendations[:3] or [
        {
            "title": "继续完善结构化证据",
            "action": "保留当前中性表达，同时补充来源、日期和结构化信息。",
            "reason": "整体分数已具备基础采信能力，但仍可通过更强证据链提升稳定性。",
        }
    ]


def _weighted_confidence(dimensions: list[dict[str, Any]]) -> float:
    total_weight = sum(float(item["max_score"]) for item in dimensions) or 1.0
    weighted = sum(
        float(item["confidence"]) * float(item["max_score"])
        for item in dimensions
    )
    return _clamp_confidence(weighted / total_weight)


def _assemble_scored_item(
    *,
    base_item: dict[str, Any],
    dimensions: list[dict[str, Any]],
    created_at: str | None = None,
) -> dict[str, Any]:
    overall_score = round(sum(float(item["score"]) for item in dimensions), 1)
    overall_confidence = _weighted_confidence(dimensions)
    return {
        **base_item,
        "signal_level": _classify_signal_level(overall_score),
        "overall_score": overall_score,
        "overall_confidence": overall_confidence,
        "top_signals": _summarize_top_signals(dimensions),
        "dimension_scores": dimensions,
        "recommendations": _build_recommendations(
            input_type=str(base_item.get("input_type", "url")),
            dimensions=dimensions,
        ),
        "status": "ready",
        "error_message": "",
        "created_at": created_at or _now_iso(),
    }


def _normalize_keyword(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip().lower()


def _build_keyword_list(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalize_keyword(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(value.strip())
    return deduped


def _item_search_text(item: dict[str, Any]) -> str:
    return " ".join(
        str(part).strip()
        for part in [
            item.get("label", ""),
            item.get("title", ""),
            item.get("url", ""),
            item.get("domain", ""),
            item.get("site_name", ""),
            item.get("raw_text", ""),
            *(item.get("question_samples", []) or []),
        ]
        if str(part).strip()
    ).lower()


def _item_entity_text(item: dict[str, Any]) -> str:
    return " ".join(
        str(part).strip()
        for part in [
            item.get("label", ""),
            item.get("title", ""),
            item.get("url", ""),
            item.get("domain", ""),
            item.get("site_name", ""),
            item.get("raw_text", ""),
        ]
        if str(part).strip()
    ).lower()


def _count_keyword_hits(text: str, keywords: list[str]) -> int:
    lowered = (text or "").lower()
    return sum(1 for keyword in keywords if _normalize_keyword(keyword) in lowered)


def _compute_frequency_threshold(items: list[dict[str, Any]]) -> float:
    frequencies = sorted(
        max(1, int(item.get("occurrences", item.get("frequency", 1)) or 1))
        for item in items
    )
    if not frequencies:
        return DEFAULT_FREQUENCY_THRESHOLD
    if max(frequencies) <= 1:
        return 2.0
    middle = len(frequencies) // 2
    median = (
        float(frequencies[middle])
        if len(frequencies) % 2 == 1
        else round((frequencies[middle - 1] + frequencies[middle]) / 2, 1)
    )
    return max(2.0, median)


def _compute_percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])

    ordered = sorted(float(value) for value in values)
    clamped = max(0.0, min(1.0, percentile))
    position = (len(ordered) - 1) * clamped
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    if lower_index == upper_index:
        return ordered[lower_index]
    weight = position - lower_index
    return ordered[lower_index] * (1 - weight) + ordered[upper_index] * weight


def _compute_aice_threshold(items: list[dict[str, Any]]) -> float:
    scores = [
        float(item.get("overall_score", item.get("aice_score", 0.0)) or 0.0)
        for item in items
    ]
    if not scores:
        return DEFAULT_AICE_THRESHOLD
    percentile_60 = _compute_percentile(scores, 0.6)
    return round(max(68.0, min(80.0, percentile_60)), 1)


def _build_threshold_diagnostics(
    items: list[dict[str, Any]],
    *,
    aice_threshold: float,
) -> dict[str, Any]:
    scores = [
        float(item.get("overall_score", item.get("aice_score", 0.0)) or 0.0)
        for item in items
    ]
    if not scores:
        return {
            "current_threshold": round(float(aice_threshold), 1),
            "fit": "balanced",
            "note": "当前样本不足，先沿用默认高分阈值。",
        }

    average_score = round(sum(scores) / len(scores), 1)
    median_score = round(_compute_percentile(scores, 0.5), 1)
    percentile_75 = round(_compute_percentile(scores, 0.75), 1)
    suggested_threshold = _compute_aice_threshold(items)
    high_score_share = round(
        len([score for score in scores if score >= float(aice_threshold)]) / len(scores),
        2,
    )

    if high_score_share < 0.18:
        fit = "strict"
        note = (
            f"当前平均分 {average_score}，中位数 {median_score}。"
            f"把高分线放在 {round(float(aice_threshold), 1)} 分会偏严，高分样本占比只有 {round(high_score_share * 100)}%，"
            f"更适合把展示参考线放在 {suggested_threshold} 分附近。"
        )
    elif high_score_share > 0.48:
        fit = "loose"
        note = (
            f"当前平均分 {average_score}，中位数 {median_score}。"
            f"{round(float(aice_threshold), 1)} 分作为高分线偏松，高分样本占比已到 {round(high_score_share * 100)}%，"
            f"可考虑上调到 {max(suggested_threshold, percentile_75)} 分附近。"
        )
    else:
        fit = "balanced"
        note = (
            f"当前平均分 {average_score}，中位数 {median_score}。"
            f"{round(float(aice_threshold), 1)} 分作为高分线基本可用，高分样本占比约 {round(high_score_share * 100)}%。"
        )

    return {
        "current_threshold": round(float(aice_threshold), 1),
        "average_score": average_score,
        "median_score": median_score,
        "percentile_75_score": percentile_75,
        "suggested_threshold": suggested_threshold,
        "high_score_share": high_score_share,
        "fit": fit,
        "note": note,
    }


def _classify_entity(
    item: dict[str, Any],
    *,
    brand_keywords: list[str],
    competitor_names: list[str],
) -> str:
    if bool(item.get("is_official")):
        return "brand"

    text = _item_entity_text(item)
    brand_hits = _count_keyword_hits(text, brand_keywords)
    competitor_hits = _count_keyword_hits(text, competitor_names)

    if competitor_hits > brand_hits and competitor_hits > 0:
        return "competitor"
    if brand_hits > 0:
        return "brand"
    return "general_knowledge"


def _determine_quadrant(
    *,
    frequency: int,
    aice_score: float,
    aice_threshold: float,
    frequency_threshold: float,
) -> str:
    is_high_frequency = float(frequency) >= float(frequency_threshold)
    is_high_score = float(aice_score) >= float(aice_threshold)
    if is_high_frequency and is_high_score:
        return "q1_anchor"
    if is_high_frequency and not is_high_score:
        return "q2_false_prosperity"
    if not is_high_frequency and is_high_score:
        return "q4_sleeping_asset"
    return "q3_noise"


def _dimension_short_label(dimension: dict[str, Any]) -> str:
    return str(dimension.get("label", "") or dimension.get("key", "")).split(":", 1)[0]


def _dimension_ratio(dimension: dict[str, Any]) -> float:
    max_score = max(float(dimension.get("max_score", 1.0) or 1.0), 1.0)
    return float(dimension.get("score", 0.0) or 0.0) / max_score


def _dimension_key(dimension: dict[str, Any]) -> str:
    return str(dimension.get("key", "") or "").strip().lower()


def _dimension_plain_label(dimension: dict[str, Any]) -> str:
    return DIMENSION_PLAIN_LABELS.get(_dimension_key(dimension), _dimension_short_label(dimension))


def _extract_item_years(item: dict[str, Any]) -> list[int]:
    evidence_text = " ".join(
        [
            str(item.get("title", "") or ""),
            str(item.get("url", "") or ""),
            str(item.get("site_name", "") or ""),
            str(item.get("published_at", "") or ""),
            str(item.get("raw_text", "") or ""),
        ]
    )
    return _extract_years(evidence_text)


def _supports_technical_analysis(item: dict[str, Any], *, entity: str, quadrant: str) -> bool:
    if str(item.get("input_type", "url")) == "text":
        return False
    if entity == "brand":
        return bool(item.get("is_official"))
    if entity == "competitor" and quadrant == "q2_false_prosperity":
        return False
    return quadrant in {"q1_anchor", "q4_sleeping_asset"}


def _select_topic_focus(item: dict[str, Any]) -> str:
    candidates: list[str] = []
    candidates.extend(str(question).strip() for question in item.get("question_samples", []) or [])
    candidates.extend(
        [
            str(item.get("title", "") or "").strip(),
            str(item.get("label", "") or "").strip(),
        ]
    )
    for candidate in candidates:
        if not candidate:
            continue
        parts = re.split(r"[|｜\-—:：，,。！？?、/()（）]", candidate)
        for part in parts:
            cleaned = _collapse_text(part)
            if 4 <= len(cleaned) <= 24 and not cleaned.lower().endswith((".com", ".cn", ".net")):
                return cleaned
    fallback = _collapse_text(str(item.get("title", "") or item.get("label", "") or "该主题"))
    return fallback[:24] if fallback else "该主题"


def _list_dimension_names(dimensions: list[dict[str, Any]]) -> str:
    names = [_dimension_plain_label(dimension) for dimension in dimensions]
    if not names:
        return "内容质量"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]}和{names[1]}"
    return f"{'、'.join(names[:-1])}和{names[-1]}"


def _describe_dimension(item: dict[str, Any], dimension: dict[str, Any]) -> str:
    key = _dimension_key(dimension)
    years = _extract_item_years(item)
    latest_year = max(years) if years else None
    reasoning = str(dimension.get("reasoning", "") or "").strip()
    ratio = _dimension_ratio(dimension)
    positive = ratio >= 0.82
    domain = str(item.get("domain", "") or "")
    title = str(item.get("title", "") or item.get("label", "") or "")
    has_question_match = bool(item.get("question_samples"))
    if key == "c8":
        if latest_year is not None:
            if positive:
                return f"页面中出现 {latest_year} 年信息，更新较新。"
            if _now_year() - latest_year <= 3:
                return f"目前能看到的时间线停留在 {latest_year} 年，需确认是否已有更新版本。"
            return f"目前主要停留在 {latest_year} 年信息，时效性偏弱。"
        if positive:
            return "虽然没有明确日期，但内容更像常青说明型资料。"
        return "没有看到明确发布日期或年份线索，时效判断偏弱。"
    if key == "c4":
        if positive:
            return "标题和来源表述较克制，宣传痕迹较轻。"
        return "标题里带有较强营销或绝对化表述，客观度偏弱。"
    if key == "c3":
        if positive:
            return "页面能看到报告、数据或原始来源线索，外部回查相对容易。"
        return "缺少数据出处、原始链接或公告依据，可核查性不足。"
    if key == "c1":
        if positive and domain:
            return f"来源主体明确，{domain} 的站点身份比较清楚。"
        if positive:
            return "来源主体明确，站点公信力较强。"
        return "来源主体公信力一般，缺少更强的官方或机构背书。"
    if key == "c5":
        if positive:
            return "标题可以直接说明主题，AI 抽取重点的成本较低。"
        return "标题主题不够集中，AI 不容易一次抓到核心结论。"
    if key == "c7":
        if positive and has_question_match:
            return "标题和被引用问题贴合度较高，容易被模型命中。"
        if positive:
            return "内容主题与大众查询场景匹配度较高。"
        return "内容与用户提问场景的贴合度一般，命中稳定性有限。"
    if key == "c2":
        if positive:
            return "目前没有看到明显自相矛盾的信号。"
        return "内容主观性偏强，还需要更多外部证据交叉验证。"
    if key == "c6":
        http_status = item.get("http_status")
        if item.get("crawl_readable") is False and http_status is not None:
            return f"页面抓取失败（HTTP {http_status}），AI 难以稳定读取。"
        if positive:
            return "页面可以正常抓取，链接访问稳定。"
        return "页面访问或抓取稳定性一般，影响模型稳定读取。"
    if key == "c9a":
        if positive:
            return "页面标题层级和正文结构完整，重点位置清楚。"
        if item.get("crawl_readable"):
            return "页面结构线索不完整，重点信息容易散在正文里。"
        return "暂时拿不到足够的页面结构证据，重点定位能力偏弱。"
    if key == "c9b":
        schema_types = item.get("schema_types", []) or []
        if positive and schema_types:
            return f"页面提供了结构化信息（{', '.join(schema_types[:2])}），主题和实体更容易被识别。"
        if positive:
            return "页面具备较明确的结构化元信息。"
        return "没有看到足够的结构化信息或明确元数据。"
    clean_reasoning = reasoning.split("。", 1)[0].strip() or "当前是关键观察维度。"
    clean_reasoning = re.sub(r"\bC\d+[ab]?\b[:：]?\s*", "", clean_reasoning, flags=re.IGNORECASE)
    return clean_reasoning


def _pick_reason_dimensions(
    item: dict[str, Any],
    *,
    entity: str,
    quadrant: str,
) -> list[dict[str, Any]]:
    dimensions = list(item.get("dimension_scores", []) or [])
    if not dimensions:
        return []

    supports_technical = _supports_technical_analysis(item, entity=entity, quadrant=quadrant)
    working_dimensions = (
        dimensions
        if supports_technical
        else [dimension for dimension in dimensions if _dimension_key(dimension) not in TECHNICAL_DIMENSION_KEYS]
    )
    if not working_dimensions:
        working_dimensions = dimensions

    if quadrant in {"q1_anchor", "q4_sleeping_asset"}:
        ranked = sorted(
            working_dimensions,
            key=lambda dimension: (_dimension_ratio(dimension), float(dimension.get("confidence", 0.0))),
            reverse=True,
        )
        strong = [dimension for dimension in ranked if _dimension_ratio(dimension) >= 0.88]
        return strong[:4] if strong else ranked[:4]

    ranked = sorted(
        working_dimensions,
        key=lambda dimension: (_dimension_ratio(dimension), float(dimension.get("confidence", 0.0))),
    )
    weak = [dimension for dimension in ranked if _dimension_ratio(dimension) <= 0.72]
    return weak[:4] if weak else ranked[:4]


def _build_primary_reasons(item: dict[str, Any], *, entity: str, quadrant: str) -> list[str]:
    selected = _pick_reason_dimensions(item, entity=entity, quadrant=quadrant)
    if not selected:
        return ["当前尚未返回可解释的维度证据。"]
    return [f"{_dimension_plain_label(dimension)}：{_describe_dimension(item, dimension)}" for dimension in selected]


def _build_repair_action(item: dict[str, Any], *, entity: str, quadrant: str) -> str:
    selected = _pick_reason_dimensions(item, entity=entity, quadrant=quadrant)
    topic_focus = _select_topic_focus(item)
    weakness_names = _list_dimension_names(selected[:3])
    official_brand_source = entity == "brand" and bool(item.get("is_official"))

    if entity == "brand" and quadrant == "q1_anchor":
        return f"把这条围绕“{topic_focus}”的页面沉淀成模板，后续同主题内容优先复用它在{weakness_names}上的写法。"
    if entity == "competitor" and quadrant == "q1_anchor":
        return f"对标这条竞品内容在{weakness_names}上的做法，在我方围绕“{topic_focus}”补一版同主题标准页。"
    if entity == "brand" and quadrant == "q2_false_prosperity":
        if not official_brand_source:
            return (
                f"这条被引内容不在我方官网控制范围内，不要把动作放在页面技术细节上。优先在官网围绕“{topic_focus}”补一版可控内容："
                "去掉主观结论，补充最近时间点、官方数据来源和适用边界，再用清晰标题把核心结论写直。"
            )
        technical_gaps = [
            dimension
            for dimension in selected
            if _dimension_key(dimension) in TECHNICAL_DIMENSION_KEYS
        ]
        if technical_gaps:
            return (
                f"这条官网内容优先同时修内容和结构：围绕“{topic_focus}”补充最新数据、原始来源与适用边界，"
                "同时整理页面标题层级、正文结构和结构化信息，避免 AI 抽取时丢关键信息。"
            )
        return (
            f"围绕“{topic_focus}”先做内容修缮：补最近时间点、可核查出处和更克制的表述，"
            "把这条已经被引用的页面转成可持续承接引用的位置。"
        )
    if entity == "competitor" and quadrant == "q2_false_prosperity":
        return (
            f"竞品这条内容虽然被引用，但在{weakness_names}上仍然偏弱。建议围绕“{topic_focus}”做专项覆盖："
            "先给出清晰结论，再补官方数据、测试条件、发布时间和适用场景，用更可核查的事实替代这类低置信内容。"
        )
    if quadrant == "q3_noise":
        return "暂不投入专项资源，将资源优先集中到第二象限修缮与第一象限固化。"
    if entity == "general_knowledge":
        return f"保持观察，并判断“{topic_focus}”是否值得进入行业共识型解释内容。"
    return f"围绕“{topic_focus}”保持更新和场景承接，等待更合适的问题触发。"


def _determine_analysis_group(entity: str, quadrant: str) -> str:
    if entity == "brand" and quadrant == "q1_anchor":
        return "brand_q1"
    if entity == "competitor" and quadrant == "q1_anchor":
        return "competitor_q1"
    if entity == "brand" and quadrant == "q2_false_prosperity":
        return "brand_q2"
    if entity == "competitor" and quadrant == "q2_false_prosperity":
        return "competitor_q2"
    return "general"


def _sort_analysis_items(items: list[dict[str, Any]], quadrant: str) -> list[dict[str, Any]]:
    reverse_score = quadrant in {"q1_anchor", "q4_sleeping_asset"}
    return sorted(
        items,
        key=lambda item: (
            -int(item.get("frequency", 1) or 1),
            (-1 if reverse_score else 1) * float(item.get("aice_score", 0.0) or 0.0),
            str(item.get("label", "") or ""),
        ),
    )


def _score_url_item(base_item: dict[str, Any]) -> dict[str, Any]:
    dimensions = [
        _score_url_coverage(base_item),
        _score_url_semantic(base_item),
        _score_url_schema(base_item),
        _score_url_timeliness(base_item),
        _score_url_credibility(base_item),
        _score_url_claim_balance(base_item),
        _score_url_consistency(base_item),
        _score_url_checkability(base_item),
        _score_url_clarity(base_item),
        _score_url_intent_match(base_item),
    ]
    return _assemble_scored_item(base_item=base_item, dimensions=dimensions)


def _score_text_item(base_item: dict[str, Any], raw_text: str) -> dict[str, Any]:
    stats = _text_structure_stats(raw_text)
    dimensions = [
        _score_text_coverage(raw_text, stats),
        _score_text_semantic(stats),
        _score_text_schema(raw_text, stats),
        _score_text_timeliness(raw_text, stats),
        _score_text_credibility(raw_text, stats),
        _score_text_claim_balance(raw_text),
        _score_text_consistency(raw_text),
        _score_text_checkability(raw_text, stats),
        _score_text_clarity(raw_text, stats),
        _score_text_intent_match(raw_text),
    ]
    return _assemble_scored_item(base_item=base_item, dimensions=dimensions)


async def _enrich_scored_url_item(base_item: dict[str, Any]) -> dict[str, Any]:
    page_features = await fetch_page_features(str(base_item.get("url", "") or ""))
    enriched = {
        **base_item,
        **page_features,
    }
    if page_features.get("fetched_title") and (
        not str(base_item.get("title", "") or "").strip()
        or str(base_item.get("label", "") or "").strip()
        == str(base_item.get("url", "") or "").strip()
    ):
        enriched["title"] = page_features["fetched_title"]
        enriched["label"] = page_features["fetched_title"]
    if page_features.get("final_url"):
        enriched["url"] = page_features["final_url"]
        enriched["domain"] = _extract_domain(str(page_features["final_url"]))
    return _score_url_item(enriched)


async def _enrich_url_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        return []

    semaphore = asyncio.Semaphore(4)

    async def _runner(item: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            return await _enrich_scored_url_item(item)

    return await asyncio.gather(*[_runner(item) for item in items])


def _build_url_manual_item(url: str, index: int) -> dict[str, Any]:
    domain = _extract_domain(url)
    base_item = {
        "item_id": f"manual_url_{index}",
        "item_origin": "manual_extra",
        "input_type": "url",
        "label": domain or url,
        "url": url,
        "domain": domain,
        "site_name": domain,
        "is_official": domain.endswith(OFFICIAL_TLDS),
        "occurrences": 1,
        "platforms": [],
        "question_samples": [],
        "title": domain or url,
    }
    return _score_url_item(base_item)


def _build_text_manual_item(text: str, index: int) -> dict[str, Any]:
    preview = _collapse_text(text)
    base_item = {
        "item_id": f"manual_text_{index}",
        "item_origin": "manual_extra",
        "input_type": "text",
        "label": (preview[:42] + "...") if len(preview) > 45 else (preview or f"手动文本 {index}"),
        "raw_text": text,
    }
    return _score_text_item(base_item, text)


def extract_citations(fetch_results: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    if not fetch_results:
        return []

    for result in fetch_results:
        platform_results = result.get("platform_results", []) or []
        for platform_result in platform_results:
            citations = platform_result.get("citations", []) or []
            platform = platform_result.get("platform", "")
            question_id = result.get("question_id", "")
            question_text = result.get("question_text", "")
            for citation in citations:
                raw_url = citation.get("url", "")
                normalized_url = _normalize_url(raw_url)
                if not normalized_url:
                    continue

                existing = unique.get(normalized_url)
                if existing is None:
                    existing = {
                        "url": normalized_url,
                        "title": citation.get("title") or citation.get("site_name") or normalized_url,
                        "site_name": citation.get("site_name") or "",
                        "domain": _extract_domain(normalized_url),
                        "is_official": bool(citation.get("is_official")),
                        "occurrences": 0,
                        "platforms": set(),
                        "question_ids": set(),
                        "question_samples": [],
                    }
                    unique[normalized_url] = existing

                existing["is_official"] = existing["is_official"] or bool(
                    citation.get("is_official")
                )
                existing["occurrences"] += 1
                if platform:
                    existing["platforms"].add(platform)
                if question_id:
                    existing["question_ids"].add(question_id)
                if question_text and len(existing["question_samples"]) < 3:
                    existing["question_samples"].append(question_text)

    items: list[dict[str, Any]] = []
    for idx, item in enumerate(unique.values(), start=1):
        base_item = {
            "item_id": f"cite_{idx:03d}",
            "item_origin": "auto_citation",
            "input_type": "url",
            "label": item.get("title", ""),
            "url": item.get("url", ""),
            "domain": item.get("domain", ""),
            "site_name": item.get("site_name", ""),
            "is_official": bool(item.get("is_official")),
            "occurrences": int(item.get("occurrences", 0)),
            "platforms": sorted(item.get("platforms", set())),
            "question_samples": list(item.get("question_samples", [])),
            "title": item.get("title", ""),
        }
        items.append(_score_url_item(base_item))

    items.sort(
        key=lambda entry: (
            {"caution": 0, "neutral": 1, "high": 2}.get(str(entry.get("signal_level")), 3),
            -float(entry.get("overall_score", 0.0)),
            entry.get("label", ""),
        )
    )
    return items


def summarize_signal_items(
    auto_items: list[dict[str, Any]] | None,
    manual_items: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    auto_items = auto_items or []
    manual_items = manual_items or []
    all_items = auto_items + manual_items
    level_counter = Counter(item.get("signal_level", "neutral") for item in all_items)
    evaluated_count = len([item for item in all_items if item.get("status") == "ready"])
    failed_count = len([item for item in all_items if item.get("status") == "error"])
    average_score = (
        round(
            sum(float(item.get("overall_score", 0.0)) for item in all_items) / len(all_items),
            1,
        )
        if all_items
        else 0.0
    )
    average_confidence_score = (
        round(
            sum(float(item.get("overall_confidence", 0.0)) for item in all_items)
            / len(all_items),
            2,
        )
        if all_items
        else 0.0
    )
    return {
        "total_citations": len(auto_items),
        "evaluated_count": evaluated_count,
        "failed_count": failed_count,
        "high_confidence_count": level_counter.get("high", 0),
        "neutral_count": level_counter.get("neutral", 0),
        "caution_count": level_counter.get("caution", 0),
        "manual_count": len(manual_items),
        "brand_count": len(
            [item for item in all_items if item.get("entity_classification") == "brand"]
        ),
        "competitor_count": len(
            [item for item in all_items if item.get("entity_classification") == "competitor"]
        ),
        "general_knowledge_count": len(
            [
                item
                for item in all_items
                if item.get("entity_classification") == "general_knowledge"
            ]
        ),
        "second_quadrant_count": len(
            [item for item in all_items if item.get("quadrant") == "q2_false_prosperity"]
        ),
        "average_score": average_score,
        "average_confidence_score": average_confidence_score,
        "vulnerable_source_count": len(
            [item for item in all_items if item.get("quadrant") == "q2_false_prosperity"]
        ),
        "updated_at": _now_iso(),
    }


def build_aggregate_findings(
    auto_items: list[dict[str, Any]],
    manual_items: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    all_items = auto_items + (manual_items or [])
    if not all_items:
        return [
            {
                "title": "尚无可评估来源",
                "description": "当前回答未识别到可用引用链接。你仍可在下方追加链接或文本生成额外评估。",
            }
        ]

    official_count = len([item for item in auto_items if item.get("is_official")])
    caution_count = len([item for item in all_items if item.get("signal_level") == "caution"])
    q2_count = len([item for item in all_items if item.get("quadrant") == "q2_false_prosperity"])
    competitor_q1 = len([item for item in all_items if item.get("analysis_group") == "competitor_q1"])
    brand_q1 = len([item for item in all_items if item.get("analysis_group") == "brand_q1"])
    return [
        {
            "title": "引用生态已形成可诊断结构",
            "description": f"当前共识别 {len(auto_items)} 个自动引用来源，另有 {len(manual_items or [])} 个手动追加评估项，已可进入阵营与象限分析。",
        },
        {
            "title": "高频低置信区域值得优先处理",
            "description": f"当前共有 {q2_count} 个来源落在第二象限，说明部分语料虽被引用，却缺少稳定质量支撑。",
        },
        {
            "title": "高质量锚点仍可继续提炼",
            "description": f"我方第一象限来源共 {brand_q1} 个，官方或官网来源共 {official_count} 个，可优先抽取为后续内容模板。",
        },
        {
            "title": "竞方高质量样本需要持续对标",
            "description": f"竞方第一象限来源共 {competitor_q1} 个；另有 {caution_count} 个来源整体仍需审慎看待。",
        },
    ]


def _collect_brand_keywords(brand_profile: dict[str, Any] | None) -> list[str]:
    if not brand_profile:
        return []

    keywords: list[str] = []
    for key in ("brand_name", "brand_name_en"):
        value = str(brand_profile.get(key, "") or "").strip()
        if value:
            keywords.append(value)
    for key in ("brand_keywords", "core_products"):
        raw = brand_profile.get(key) or []
        if isinstance(raw, list):
            keywords.extend(str(item).strip() for item in raw if str(item).strip())

    deduped: list[str] = []
    seen: set[str] = set()
    for keyword in keywords:
        lowered = keyword.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(keyword)
    return deduped


def _collect_competitor_names(competitors: list[dict[str, Any]] | None) -> list[str]:
    if not competitors:
        return []

    names: list[str] = []
    for competitor in competitors:
        if not isinstance(competitor, dict):
            continue
        for key in ("name", "name_en"):
            value = str(competitor.get(key, "") or "").strip()
            if value:
                names.append(value)

    deduped: list[str] = []
    seen: set[str] = set()
    for name in names:
        lowered = name.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(name)
    return deduped


def _enrich_semantic_items(
    items: list[dict[str, Any]],
    *,
    brand_keywords: list[str],
    competitor_names: list[str],
    aice_threshold: float,
    frequency_threshold: float,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for item in items:
        frequency = max(1, int(item.get("occurrences", item.get("frequency", 1)) or 1))
        aice_score = round(float(item.get("overall_score", item.get("aice_score", 0.0)) or 0.0), 1)
        entity = _classify_entity(
            item,
            brand_keywords=brand_keywords,
            competitor_names=competitor_names,
        )
        quadrant = _determine_quadrant(
            frequency=frequency,
            aice_score=aice_score,
            aice_threshold=aice_threshold,
            frequency_threshold=frequency_threshold,
        )
        quadrant_meta = QUADRANT_META[quadrant]
        enriched.append(
            {
                **item,
                "entity_classification": entity,
                "entity_label": ENTITY_LABELS[entity],
                "frequency": frequency,
                "aice_score": aice_score,
                "quadrant": quadrant,
                "quadrant_label": quadrant_meta["label"],
                "quadrant_description": quadrant_meta["description"],
                "primary_reasons": _build_primary_reasons(item, entity=entity, quadrant=quadrant),
                "repair_action": _build_repair_action(item, entity=entity, quadrant=quadrant),
                "analysis_group": _determine_analysis_group(entity, quadrant),
            }
        )
    return enriched


def _build_ecosystem_diagnosis(items: list[dict[str, Any]]) -> str:
    if not items:
        return "当前未检测到可进入语境生态分析的引用来源。"

    entity_counter = Counter(str(item.get("entity_classification", "general_knowledge")) for item in items)
    quadrant_counter = Counter(str(item.get("quadrant", "q3_noise")) for item in items)
    brand_q1 = len([item for item in items if item.get("analysis_group") == "brand_q1"])
    competitor_q1 = len([item for item in items if item.get("analysis_group") == "competitor_q1"])
    brand_q2 = len([item for item in items if item.get("analysis_group") == "brand_q2"])
    competitor_q2 = len([item for item in items if item.get("analysis_group") == "competitor_q2"])

    parts: list[str] = []

    dominant_entity = entity_counter.most_common(1)[0][0]
    if dominant_entity == "brand":
        parts.append("当前引用生态以我方阵营为主")
    elif dominant_entity == "competitor":
        parts.append("当前引用生态由竞方阵营占据更强位置")
    else:
        parts.append("当前引用生态仍以共业语料充当基础认知框架")

    if competitor_q1 > brand_q1:
        parts.append("竞方在高频高置信区更强")
    elif brand_q1 > competitor_q1:
        parts.append("我方在高频高置信区已有稳定锚点")

    if brand_q2 > 0:
        parts.append(f"我方仍有 {brand_q2} 个高频低置信来源待优先修缮")
    if competitor_q2 > 0:
        parts.append(f"竞方有 {competitor_q2} 个高频低置信来源可作为降维覆盖机会")

    if quadrant_counter.get("q4_sleeping_asset", 0) > 0:
        parts.append("仍存在高潜伏高质量语料可进一步唤醒")

    return "，".join(parts) + "。"


def _build_quadrant_overview(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    overview: list[dict[str, Any]] = []
    for quadrant in ("q1_anchor", "q2_false_prosperity", "q3_noise", "q4_sleeping_asset"):
        quadrant_items = [item for item in items if item.get("quadrant") == quadrant]
        breakdown = Counter(str(item.get("entity_classification", "general_knowledge")) for item in quadrant_items)
        meta = QUADRANT_META[quadrant]
        overview.append(
            {
                "quadrant": quadrant,
                "quadrant_label": meta["label"],
                "description": meta["description"],
                "strategy": meta["strategy"],
                "count": len(quadrant_items),
                "entity_breakdown": {
                    "brand": breakdown.get("brand", 0),
                    "competitor": breakdown.get("competitor", 0),
                    "general_knowledge": breakdown.get("general_knowledge", 0),
                },
            }
        )
    return overview


def _build_analysis_blocks(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for key, meta in ANALYSIS_GROUP_META.items():
        block_items = [item for item in items if item.get("analysis_group") == key]
        if not block_items:
            continue
        quadrant = "q1_anchor" if key.endswith("q1") else "q2_false_prosperity"
        sorted_items = _sort_analysis_items(block_items, quadrant)[:5]
        blocks.append(
            {
                "key": key,
                "title": meta["title"],
                "description": meta["description"],
                "reason_label": meta["reason_label"],
                "action_label": meta["action_label"],
                "item_count": len(block_items),
                "items": sorted_items,
            }
        )
    return blocks


def _build_general_knowledge_insight(items: list[dict[str, Any]]) -> dict[str, Any]:
    general_items = [item for item in items if item.get("entity_classification") == "general_knowledge"]
    if not general_items:
        return {
            "summary": "当前这批引用来源中，共业阵营占比有限，AI 主要仍在品牌与竞品语料之间取材。",
            "top_frequency_items": [],
            "top_score_items": [],
            "representative_items": [],
        }

    top_frequency_items = sorted(
        general_items,
        key=lambda item: (-int(item.get("frequency", 1) or 1), str(item.get("label", "") or "")),
    )[:5]
    top_score_items = sorted(
        general_items,
        key=lambda item: (-float(item.get("aice_score", 0.0) or 0.0), str(item.get("label", "") or "")),
    )[:5]
    representative_items: list[dict[str, Any]] = []
    seen_item_ids: set[str] = set()
    for candidate in top_frequency_items + top_score_items:
        item_id = str(candidate.get("item_id", "") or "")
        if not item_id or item_id in seen_item_ids:
            continue
        seen_item_ids.add(item_id)
        representative_items.append(candidate)
    return {
        "summary": "共业阵营代表行业的默认解释框架，说明 AI 当前仍依赖研究、科普与第三方材料来组织基础认知。",
        "top_frequency_items": top_frequency_items,
        "top_score_items": top_score_items,
        "representative_items": representative_items[:8],
    }


def _build_repair_actions(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    brand_q2 = [item for item in items if item.get("analysis_group") == "brand_q2"]
    q1_items = [item for item in items if item.get("analysis_group") in {"brand_q1", "competitor_q1"}]
    competitor_q2 = [item for item in items if item.get("analysis_group") == "competitor_q2"]
    q3_items = [item for item in items if item.get("quadrant") == "q3_noise"]

    return [
        {
            "priority": "P0",
            "title": "立即修缮",
            "summary": "优先修复我方高频低置信语料，避免当前已有引用基础继续建立在脆弱页面上。",
            "count": len(brand_q2),
            "related_item_ids": [str(item.get("item_id", "")) for item in brand_q2[:8]],
        },
        {
            "priority": "P1",
            "title": "对标固化",
            "summary": "把第一象限的我方优势内容与竞品优秀样本抽象成模板，沉淀后续内容生产标准。",
            "count": len(q1_items),
            "related_item_ids": [str(item.get("item_id", "")) for item in q1_items[:8]],
        },
        {
            "priority": "P2",
            "title": "降维覆盖",
            "summary": "针对竞方高频低置信来源，产出更高质量、更可核查的替代内容，争夺后续引用位。",
            "count": len(competitor_q2),
            "related_item_ids": [str(item.get("item_id", "")) for item in competitor_q2[:8]],
        },
        {
            "priority": "P3",
            "title": "战略性忽略",
            "summary": "对低频低置信的沉寂噪音不投入专项资源，将精力集中到能真正影响 AI 占位的象限。",
            "count": len(q3_items),
            "related_item_ids": [str(item.get("item_id", "")) for item in q3_items[:8]],
        },
    ]


def _compose_report_payload(
    auto_items: list[dict[str, Any]],
    manual_items: list[dict[str, Any]],
    *,
    brand_profile: dict[str, Any] | None = None,
    competitors: list[dict[str, Any]] | None = None,
    aice_threshold: float | None = None,
) -> dict[str, Any]:
    brand_keywords = _collect_brand_keywords(brand_profile)
    competitor_names = _collect_competitor_names(competitors)
    semantic_brand_keywords = _build_keyword_list(brand_keywords)
    semantic_competitors = _build_keyword_list(competitor_names)
    all_source_items = auto_items + manual_items
    resolved_aice_threshold = round(
        float(aice_threshold)
        if aice_threshold is not None
        else _compute_aice_threshold(all_source_items),
        1,
    )
    frequency_threshold = _compute_frequency_threshold(all_source_items)
    enriched_auto_items = _enrich_semantic_items(
        auto_items,
        brand_keywords=semantic_brand_keywords,
        competitor_names=semantic_competitors,
        aice_threshold=resolved_aice_threshold,
        frequency_threshold=frequency_threshold,
    )
    enriched_manual_items = _enrich_semantic_items(
        manual_items,
        brand_keywords=semantic_brand_keywords,
        competitor_names=semantic_competitors,
        aice_threshold=resolved_aice_threshold,
        frequency_threshold=frequency_threshold,
    )
    all_items = enriched_auto_items + enriched_manual_items
    summary = summarize_signal_items(enriched_auto_items, enriched_manual_items)
    diagnosis = _build_ecosystem_diagnosis(all_items)
    threshold_diagnostics = _build_threshold_diagnostics(
        all_items,
        aice_threshold=resolved_aice_threshold,
    )
    return {
        "report_kind": "confidence_signal",
        "artifact_kind": "confidence_signal",
        "headline": "置信度报告",
        "subtitle": "评估 AI 回答引用语料的阵营分布、生态位置与修我方向。",
        "description": "底层继续基于 AICE 9C 维度评分，但交付层升级为阵营分类、语境生态矩阵与修我行动报告。",
        "brand_name": str((brand_profile or {}).get("brand_name", "") or ""),
        "brand_keywords": semantic_brand_keywords,
        "competitor_names": semantic_competitors,
        "updated_at": summary["updated_at"],
        "metrics": {
            "引用来源数": summary["total_citations"],
            "我方阵营": summary["brand_count"],
            "竞方阵营": summary["competitor_count"],
            "共业阵营": summary["general_knowledge_count"],
            "高频低置信来源": summary["vulnerable_source_count"],
            "平均置信分": summary["average_confidence_score"],
        },
        "summary": summary,
        "matrix_config": {
            "aice_threshold": resolved_aice_threshold,
            "frequency_threshold": frequency_threshold,
            "aice_threshold_mode": "manual" if aice_threshold is not None else "adaptive_p60",
            "frequency_threshold_mode": "repeat_aware_median",
            "threshold_diagnostics": threshold_diagnostics,
        },
        "ecosystem_matrix": {
            "title": "语境生态坐标系",
            "x_axis_label": "AICE 置信度",
            "y_axis_label": "引用频次",
            "total_points": len(all_items),
            "diagnosis": diagnosis,
        },
        "quadrant_overview": _build_quadrant_overview(all_items),
        "analysis_blocks": _build_analysis_blocks(all_items),
        "general_knowledge_insight": _build_general_knowledge_insight(all_items),
        "repair_actions": [],
        "auto_items": enriched_auto_items,
        "manual_items": enriched_manual_items,
        "aggregate_findings": [],
        "composer": {
            "enabled": True,
            "allowed_input_types": ["url", "text"],
            "placeholder": "粘贴链接或文本，生成额外评估",
            "helper_text": "支持单个链接、多个链接或一段文本；当前不支持把链接和文本混合提交。",
        },
        "status": {
            "phase": "ready",
            "message": "AICE 置信度报告已就绪",
        },
        "diagnosis": diagnosis,
    }


def build_confidence_signal_report(
    fetch_results: list[dict[str, Any]] | None,
    *,
    manual_items: list[dict[str, Any]] | None = None,
    brand_profile: dict[str, Any] | None = None,
    competitors: list[dict[str, Any]] | None = None,
    aice_threshold: float | None = None,
) -> dict[str, Any]:
    auto_items = extract_citations(fetch_results)
    manual_items = manual_items or []
    return _compose_report_payload(
        auto_items,
        manual_items,
        brand_profile=brand_profile,
        competitors=competitors,
        aice_threshold=aice_threshold,
    )


async def build_confidence_signal_report_async(
    fetch_results: list[dict[str, Any]] | None,
    *,
    manual_items: list[dict[str, Any]] | None = None,
    brand_profile: dict[str, Any] | None = None,
    competitors: list[dict[str, Any]] | None = None,
    aice_threshold: float | None = None,
) -> dict[str, Any]:
    auto_items = extract_citations(fetch_results)
    auto_items = await _enrich_url_items(auto_items)
    return _compose_report_payload(
        auto_items,
        manual_items or [],
        brand_profile=brand_profile,
        competitors=competitors,
        aice_threshold=aice_threshold,
    )


def parse_extra_input(raw_input: str) -> tuple[str, Any]:
    cleaned = (raw_input or "").strip()
    if not cleaned:
        return "error", "请输入链接或文本后再开始评估。"

    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    normalized_urls = [
        _normalize_url(line) if _looks_like_pure_url_line(line) else ""
        for line in lines
    ]
    valid_urls = [url for url in normalized_urls if url]
    pure_url_line_count = sum(1 for url in normalized_urls if url)

    if lines and len(valid_urls) == len(lines):
        return "url_list", valid_urls

    if pure_url_line_count > 0 and pure_url_line_count != len(lines):
        return "error", "当前额外评估暂不支持把链接和大段文本混合提交，请拆开后重试。"

    return "text", cleaned


def append_manual_items(
    existing_report: dict[str, Any],
    *,
    raw_input: str,
) -> dict[str, Any]:
    input_kind, payload = parse_extra_input(raw_input)
    if input_kind == "error":
        raise ValueError(str(payload))

    current_manual_items = list(existing_report.get("manual_items", []) or [])
    next_index = len(current_manual_items) + 1
    new_items: list[dict[str, Any]] = []

    if input_kind == "url_list":
        for offset, url in enumerate(payload, start=next_index):
            new_items.append(_build_url_manual_item(url, offset))
    else:
        new_items.append(_build_text_manual_item(str(payload), next_index))

    merged_manual = current_manual_items + new_items
    auto_items = list(existing_report.get("auto_items", []) or [])
    updated = _compose_report_payload(
        auto_items,
        merged_manual,
        brand_profile={
            "brand_name": existing_report.get("brand_name", ""),
            "brand_keywords": existing_report.get("brand_keywords", []) or [],
        },
        competitors=[
            {"name": name}
            for name in list(existing_report.get("competitor_names", []) or [])
        ],
        aice_threshold=float(
            ((existing_report.get("matrix_config", {}) or {}).get("aice_threshold") or DEFAULT_AICE_THRESHOLD)
        ),
    )
    updated["status"] = {
        "phase": "ready",
        "message": "额外评估已完成",
    }
    return updated


async def append_manual_items_async(
    existing_report: dict[str, Any],
    *,
    raw_input: str,
) -> dict[str, Any]:
    input_kind, payload = parse_extra_input(raw_input)
    if input_kind == "error":
        raise ValueError(str(payload))

    current_manual_items = list(existing_report.get("manual_items", []) or [])
    next_index = len(current_manual_items) + 1
    new_items: list[dict[str, Any]] = []

    if input_kind == "url_list":
        base_items = [
            {
                "item_id": f"manual_url_{offset}",
                "item_origin": "manual_extra",
                "input_type": "url",
                "label": _extract_domain(url) or url,
                "url": url,
                "domain": _extract_domain(url),
                "site_name": _extract_domain(url),
                "is_official": _extract_domain(url).endswith(OFFICIAL_TLDS),
                "occurrences": 1,
                "platforms": [],
                "question_samples": [],
                "title": _extract_domain(url) or url,
            }
            for offset, url in enumerate(payload, start=next_index)
        ]
        new_items = await _enrich_url_items(base_items)
    else:
        new_items.append(_build_text_manual_item(str(payload), next_index))

    merged_manual = current_manual_items + new_items
    auto_items = list(existing_report.get("auto_items", []) or [])
    updated = _compose_report_payload(
        auto_items,
        merged_manual,
        brand_profile={
            "brand_name": existing_report.get("brand_name", ""),
            "brand_keywords": existing_report.get("brand_keywords", []) or [],
        },
        competitors=[
            {"name": name}
            for name in list(existing_report.get("competitor_names", []) or [])
        ],
        aice_threshold=float(
            ((existing_report.get("matrix_config", {}) or {}).get("aice_threshold") or DEFAULT_AICE_THRESHOLD)
        ),
    )
    updated["status"] = {
        "phase": "ready",
        "message": "额外评估已完成",
    }
    return updated


async def generate_confidence_signal_artifact(
    session_id: str,
    fetch_results: list[dict[str, Any]] | None,
    *,
    brand_profile: dict[str, Any] | None = None,
    competitors: list[dict[str, Any]] | None = None,
) -> None:
    """Generate the independent A7 confidence signal artifact from A4 data."""
    from app.workflow.events import save_and_send_artifact

    report_data = await build_confidence_signal_report_async(
        fetch_results,
        brand_profile=brand_profile,
        competitors=competitors,
    )
    await save_and_send_artifact(
        session_id=session_id,
        output_type="report",
        title="置信度报告",
        data=report_data,
        artifact_key=f"{session_id}_report_confidence_signal_main",
    )
