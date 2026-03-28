"""Confidence analysis artifact builders.

This module turns citation data into an independent ``confidence_analysis``
artifact. The current implementation does not fetch full page DOM yet, but it
already applies a structured AICE 9C scoring model with:

- per-dimension score / max score / confidence / reasoning
- conservative hard-deduction handling for C6 / C9a / C9b
- overall confidence derived from evidence sufficiency

Output guardrails for the confidence report:

- only describe facts that can be traced back to score dimensions, citation data,
  DOM/text evidence, or deterministic rules
- do not fabricate causes, actions, or labels that lack evidence
- do not emit filler summaries, slogan-like headings, or generic advice with no
  factual anchor
- if a source lacks enough evidence for a strong conclusion, say that directly
  instead of inventing confidence reasons
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
        "dimension_scores": dimensions,
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


async def _build_enriched_url_manual_items(
    urls: list[str],
    *,
    start_index: int = 1,
    item_origin: str = "manual_extra",
) -> list[dict[str, Any]]:
    base_items = [
        {
            "item_id": f"manual_url_{offset}",
            "item_origin": item_origin,
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
        for offset, url in enumerate(urls, start=start_index)
    ]
    return await _enrich_url_items(base_items)


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
        "auto_evaluated_count": len(auto_items),
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
        "average_score": average_score,
        "average_confidence_score": average_confidence_score,
        "updated_at": _now_iso(),
    }


def _round_score(value: float) -> float:
    return round(float(value or 0.0), 1)


def _average_score(items: list[dict[str, Any]]) -> float | None:
    if not items:
        return None
    return _round_score(
        sum(float(item.get("aice_score", item.get("overall_score", 0.0)) or 0.0) for item in items)
        / len(items)
    )


def _weighted_average_score(items: list[dict[str, Any]]) -> float | None:
    if not items:
        return None
    total_weight = sum(max(1, int(item.get("frequency", item.get("occurrences", 1)) or 1)) for item in items)
    if total_weight <= 0:
        return None
    weighted = sum(
        float(item.get("aice_score", item.get("overall_score", 0.0)) or 0.0)
        * max(1, int(item.get("frequency", item.get("occurrences", 1)) or 1))
        for item in items
    )
    return _round_score(weighted / total_weight)


def _representative_sources(items: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    ranked = sorted(
        items,
        key=lambda item: (
            -max(1, int(item.get("frequency", item.get("occurrences", 1)) or 1)),
            -float(item.get("aice_score", item.get("overall_score", 0.0)) or 0.0),
            str(item.get("label", "") or ""),
        ),
    )
    return [
        {
            "item_id": item.get("item_id"),
            "label": item.get("label", ""),
            "domain": item.get("domain", ""),
            "url": item.get("url", ""),
            "score": _round_score(item.get("aice_score", item.get("overall_score", 0.0)) or 0.0),
            "frequency": max(1, int(item.get("frequency", item.get("occurrences", 1)) or 1)),
        }
        for item in ranked[:limit]
    ]


def _lowest_dimensions(item: dict[str, Any], limit: int = 2) -> list[dict[str, Any]]:
    dimensions = [
        dimension
        for dimension in (item.get("dimension_scores", []) or [])
        if isinstance(dimension, dict) and dimension.get("key")
    ]
    ranked = sorted(
        dimensions,
        key=lambda dimension: (
            float(dimension.get("score", 0.0)) / max(float(dimension.get("max_score", 1.0) or 1.0), 1.0),
            str(dimension.get("key", "")),
        ),
    )
    return ranked[:limit]


def _suggestion_for_dimension(dimension_key: str, *, controllable: bool) -> str:
    if dimension_key == "c4":
        return "减少主观宣传表达，补充更具体的数据、来源和归因。"
    if dimension_key == "c3":
        return "增加可核查证据、测试口径、原始来源或外部证明链接。"
    if dimension_key == "c8":
        return "补充最新时间点、更新年份或删除已过时的数据表述。"
    if dimension_key == "c9a":
        return (
            "补全 H1 / H2 和正文结构，让核心事实更容易被模型分层理解。"
            if controllable
            else "用我方可控页面重新组织同主题内容，避免继续依赖结构混乱的第三方页面。"
        )
    if dimension_key == "c9b":
        return (
            "补充 Schema.org 结构化数据，明确正文、标题、发布日期和主体。"
            if controllable
            else "围绕同主题提供带结构化数据的我方内容，替代结构化不足的外部来源。"
        )
    if dimension_key == "c6":
        return (
            "提高页面可访问性和可抓取性，避免爬虫抓取失败或正文缺失。"
            if controllable
            else "不要依赖不可稳定访问的外部来源，改用我方可稳定访问的页面承载该主题。"
        )
    if dimension_key == "c1":
        return "强化来源主体与权威背书，优先让更可信主体承载该主题事实。"
    if dimension_key == "c5":
        return "压缩冗长表述，直接用更清晰的主题句和事实段落组织内容。"
    if dimension_key == "c7":
        return "让标题和正文更直接回答用户问题，减少泛化叙事。"
    return "围绕该维度补强事实表达与结构质量。"


def _build_low_confidence_patterns(
    items: list[dict[str, Any]],
    *,
    low_confidence_threshold: float,
    controllable: bool,
) -> list[dict[str, Any]]:
    low_items = [
        item
        for item in items
        if float(item.get("aice_score", item.get("overall_score", 0.0)) or 0.0) < low_confidence_threshold
    ]
    pattern_map: dict[str, dict[str, Any]] = {}

    for item in low_items:
        lowest = _lowest_dimensions(item, limit=2)
        if not lowest:
            continue
        primary = lowest[0]
        key = str(primary.get("key", "") or "unknown")
        entry = pattern_map.setdefault(
            key,
            {
                "pattern_key": key,
                "pattern_label": DIMENSION_PLAIN_LABELS.get(key, key),
                "items": [],
                "evidence_examples": [],
                "affected_dimensions": [],
            },
        )
        entry["items"].append(item)
        entry["affected_dimensions"] = list({
            *entry["affected_dimensions"],
            *[
                DIMENSION_PLAIN_LABELS.get(str(dimension.get("key", "")), str(dimension.get("label", "")))
                for dimension in lowest
                if isinstance(dimension, dict)
            ],
        })
        if len(entry["evidence_examples"]) < 3:
            reasoning = str(primary.get("reasoning", "") or "").strip()
            entry["evidence_examples"].append(
                {
                    "label": item.get("label", ""),
                    "domain": item.get("domain", ""),
                    "score": _round_score(item.get("aice_score", item.get("overall_score", 0.0)) or 0.0),
                    "evidence": reasoning,
                }
            )

    patterns: list[dict[str, Any]] = []
    for key, entry in pattern_map.items():
        grouped_items = entry["items"]
        patterns.append(
            {
                "pattern_key": key,
                "pattern_label": entry["pattern_label"],
                "sample_count": len(grouped_items),
                "average_confidence": _average_score(grouped_items),
                "weighted_average_confidence": _weighted_average_score(grouped_items),
                "affected_dimensions": entry["affected_dimensions"],
                "evidence_examples": entry["evidence_examples"],
                "suggestion": _suggestion_for_dimension(key, controllable=controllable),
            }
        )

    return sorted(
        patterns,
        key=lambda pattern: (
            -int(pattern.get("sample_count", 0) or 0),
            float(pattern.get("average_confidence", 0.0) or 0.0),
            str(pattern.get("pattern_key", "")),
        ),
    )


def _build_confidence_overview(
    items: list[dict[str, Any]],
    *,
    entity_label: str,
    low_confidence_threshold: float,
) -> dict[str, Any]:
    low_count = len(
        [
            item
            for item in items
            if float(item.get("aice_score", item.get("overall_score", 0.0)) or 0.0) < low_confidence_threshold
        ]
    )
    return {
        "entity_label": entity_label,
        "average_confidence": _average_score(items),
        "weighted_average_confidence": _weighted_average_score(items),
        "source_count": len(items),
        "low_confidence_source_count": low_count,
        "representative_sources": _representative_sources(items),
    }


def _build_overall_conclusion(
    brand_overview: dict[str, Any],
    competitor_overview: dict[str, Any],
) -> str:
    brand_avg = brand_overview.get("weighted_average_confidence")
    competitor_avg = competitor_overview.get("weighted_average_confidence")
    brand_count = brand_overview.get("source_count", 0)
    competitor_count = competitor_overview.get("source_count", 0)

    if brand_count == 0 and competitor_count == 0:
        return "当前引用来源里没有足够的我方或竞品样本，暂时无法形成稳定的置信度对比结论。"
    if brand_count == 0:
        return f"当前引用来源里没有稳定的我方样本，竞品相关来源加权平均置信度为 {format(competitor_avg or 0, '.1f')}。"
    if competitor_count == 0:
        return f"当前引用来源里暂无稳定的竞品样本，我方相关来源加权平均置信度为 {format(brand_avg or 0, '.1f')}。"

    delta = float(brand_avg or 0.0) - float(competitor_avg or 0.0)
    if delta >= 5:
        return (
            f"我方相关来源的加权平均置信度为 {brand_avg:.1f}，高于竞品的 {competitor_avg:.1f}，"
            "说明 AI 在引用我方内容时整体质量更稳。"
        )
    if delta <= -5:
        return (
            f"竞品相关来源的加权平均置信度为 {competitor_avg:.1f}，高于我方的 {brand_avg:.1f}，"
            "说明竞品在 AI 引用质量上更具优势。"
        )
    return (
        f"我方与竞品相关来源的加权平均置信度接近（我方 {brand_avg:.1f}，竞品 {competitor_avg:.1f}），"
        "差距主要取决于低置信样本的结构和事实质量。"
    )


def _build_strategic_recommendations(
    brand_patterns: list[dict[str, Any]],
    competitor_patterns: list[dict[str, Any]],
    brand_overview: dict[str, Any],
    competitor_overview: dict[str, Any],
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []

    if brand_patterns:
        primary = brand_patterns[0]
        recommendations.append(
            {
                "title": f"优先修补我方的“{primary.get('pattern_label', '低置信问题')}”",
                "reason": f"当前我方有 {primary.get('sample_count', 0)} 个低置信来源集中出现在该问题上。",
                "action": primary.get("suggestion", ""),
            }
        )

    if competitor_patterns:
        primary = competitor_patterns[0]
        recommendations.append(
            {
                "title": f"围绕竞品的“{primary.get('pattern_label', '低置信问题')}”做替代性内容覆盖",
                "reason": f"当前竞品有 {primary.get('sample_count', 0)} 个低置信来源集中出现在该问题上。",
                "action": primary.get("suggestion", ""),
            }
        )

    brand_avg = brand_overview.get("weighted_average_confidence")
    competitor_avg = competitor_overview.get("weighted_average_confidence")
    if brand_avg is not None and competitor_avg is not None and float(brand_avg) + 5 < float(competitor_avg):
        recommendations.append(
            {
                "title": "先补我方核心主题页的事实与结构质量",
                "reason": "当前我方加权平均置信度显著低于竞品，优先补强我方事实源更有效。",
                "action": "围绕被高频引用的主题，优先补可核查数据、时间信息和结构化组织。",
            }
        )

    return recommendations[:3]


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
            }
        )
    return enriched


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
    summary = summarize_signal_items(enriched_auto_items, enriched_manual_items)

    auto_brand_items = [
        item for item in enriched_auto_items if item.get("entity_classification") == "brand"
    ]
    auto_competitor_items = [
        item for item in enriched_auto_items if item.get("entity_classification") == "competitor"
    ]
    brand_overview = _build_confidence_overview(
        auto_brand_items,
        entity_label="我方引用来源",
        low_confidence_threshold=resolved_aice_threshold,
    )
    competitor_overview = _build_confidence_overview(
        auto_competitor_items,
        entity_label="竞品引用来源",
        low_confidence_threshold=resolved_aice_threshold,
    )
    brand_patterns = _build_low_confidence_patterns(
        auto_brand_items,
        low_confidence_threshold=resolved_aice_threshold,
        controllable=True,
    )
    competitor_patterns = _build_low_confidence_patterns(
        auto_competitor_items,
        low_confidence_threshold=resolved_aice_threshold,
        controllable=False,
    )
    overall_conclusion = _build_overall_conclusion(brand_overview, competitor_overview)
    strategic_recommendations = _build_strategic_recommendations(
        brand_patterns,
        competitor_patterns,
        brand_overview,
        competitor_overview,
    )

    return {
        "report_kind": "confidence_analysis",
        "artifact_kind": "confidence_analysis",
        "headline": "置信度报告",
        "subtitle": "",
        "description": "",
        "brand_name": str((brand_profile or {}).get("brand_name", "") or ""),
        "brand_keywords": semantic_brand_keywords,
        "competitor_names": semantic_competitors,
        "updated_at": summary["updated_at"],
        "metrics": {
            "评估来源数": summary["auto_evaluated_count"],
            "我方平均置信度": brand_overview.get("average_confidence") or 0,
            "竞品平均置信度": competitor_overview.get("average_confidence") or 0,
            "额外评估": summary["manual_count"],
        },
        "summary": summary,
        "config": {
            "low_confidence_threshold": resolved_aice_threshold,
            "low_confidence_threshold_mode": "manual" if aice_threshold is not None else "adaptive_p60",
        },
        "overall_conclusion": overall_conclusion,
        "brand_confidence_overview": brand_overview,
        "competitor_confidence_overview": competitor_overview,
        "brand_low_confidence_patterns": brand_patterns,
        "competitor_low_confidence_patterns": competitor_patterns,
        "strategic_recommendations": strategic_recommendations,
        "extra_evaluation": {
            "count": len(enriched_manual_items),
            "items": enriched_manual_items,
        },
        "auto_items": enriched_auto_items,
        "manual_items": enriched_manual_items,
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
    }


def build_confidence_analysis_report(
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


async def build_confidence_analysis_report_async(
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


async def build_manual_items_from_raw_input_async(
    raw_input: str,
    *,
    start_index: int = 1,
    item_origin: str = "manual_extra",
) -> list[dict[str, Any]]:
    input_kind, payload = parse_extra_input(raw_input)
    if input_kind == "error":
        raise ValueError(str(payload))
    if input_kind == "url_list":
        return await _build_enriched_url_manual_items(
            list(payload),
            start_index=start_index,
            item_origin=item_origin,
        )
    return [_build_text_manual_item(str(payload), start_index)]


async def build_manual_items_from_link_rows_async(
    link_rows: list[dict[str, Any]] | None,
    *,
    start_index: int = 1,
    item_origin: str = "imported_link_list",
) -> list[dict[str, Any]]:
    normalized_urls: list[str] = []
    for row in link_rows or []:
        if not isinstance(row, dict):
            continue
        normalized = _normalize_url(str(row.get("url") or ""))
        if normalized:
            normalized_urls.append(normalized)
    if not normalized_urls:
        return []
    return await _build_enriched_url_manual_items(
        normalized_urls,
        start_index=start_index,
        item_origin=item_origin,
    )


def append_confidence_analysis_manual_items(
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
            ((existing_report.get("config", {}) or {}).get("low_confidence_threshold") or DEFAULT_AICE_THRESHOLD)
        ),
    )
    updated["status"] = {
        "phase": "ready",
        "message": "额外评估已完成",
    }
    return updated


async def append_confidence_analysis_manual_items_async(
    existing_report: dict[str, Any],
    *,
    raw_input: str,
) -> dict[str, Any]:
    current_manual_items = list(existing_report.get("manual_items", []) or [])
    next_index = len(current_manual_items) + 1
    new_items = await build_manual_items_from_raw_input_async(
        raw_input,
        start_index=next_index,
    )

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
            ((existing_report.get("config", {}) or {}).get("low_confidence_threshold") or DEFAULT_AICE_THRESHOLD)
        ),
    )
    updated["status"] = {
        "phase": "ready",
        "message": "额外评估已完成",
    }
    return updated


async def generate_confidence_analysis_artifact(
    session_id: str,
    fetch_results: list[dict[str, Any]] | None,
    *,
    manual_items: list[dict[str, Any]] | None = None,
    brand_profile: dict[str, Any] | None = None,
    competitors: list[dict[str, Any]] | None = None,
) -> None:
    """Generate the independent confidence analysis artifact."""
    from app.workflow.events import save_and_send_artifact

    report_data = await build_confidence_analysis_report_async(
        fetch_results,
        manual_items=manual_items,
        brand_profile=brand_profile,
        competitors=competitors,
    )
    await save_and_send_artifact(
        session_id=session_id,
        output_type="report",
        title="置信度报告",
        data=report_data,
        artifact_key=f"{session_id}_report_confidence_analysis_main",
    )
