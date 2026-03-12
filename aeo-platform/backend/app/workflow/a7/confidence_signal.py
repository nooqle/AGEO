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
            reasoning = f"检测到最近年份 {latest}，时效性较好。"
            confidence = 0.74
        elif gap <= 3:
            score = 11.5
            reasoning = f"检测到年份 {latest}，仍具一定时效性，但需注意是否已有更新。"
            confidence = 0.72
        else:
            score = 7.5
            reasoning = f"检测到年份 {latest}，内容可能已老化。"
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
            reasoning = f"文本包含最近年份 {latest}，时效性较好。"
            confidence = 0.82
        elif gap <= 3:
            score = 11.0
            reasoning = f"文本包含年份 {latest}，仍有一定时效性。"
            confidence = 0.8
        else:
            score = 7.0
            reasoning = f"文本包含年份 {latest}，信息可能过期。"
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
    return {
        "total_citations": len(auto_items),
        "evaluated_count": evaluated_count,
        "failed_count": failed_count,
        "high_confidence_count": level_counter.get("high", 0),
        "neutral_count": level_counter.get("neutral", 0),
        "caution_count": level_counter.get("caution", 0),
        "manual_count": len(manual_items),
        "average_score": average_score,
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
    schema_risk = len(
        [
            item
            for item in all_items
            if any(
                score.get("key") == "c9b" and float(score.get("score", 0.0)) <= 5.5
                for score in item.get("dimension_scores", [])
            )
        ]
    )
    balance_risk = len(
        [
            item
            for item in all_items
            if any(
                score.get("key") == "c4" and float(score.get("score", 0.0)) <= 6.0
                for score in item.get("dimension_scores", [])
            )
        ]
    )
    return [
        {
            "title": "引用来源整体结构已建立",
            "description": f"当前共识别 {len(auto_items)} 个自动引用来源，另有 {len(manual_items or [])} 个手动追加评估项。",
        },
        {
            "title": "官方来源覆盖",
            "description": f"官方或官网来源共 {official_count} 个，可优先作为高可信样本观察。",
        },
        {
            "title": "结构化风险分布",
            "description": f"共有 {schema_risk} 个来源在 C9b 上缺少明确结构化证据，后续应优先补充 Schema 或来源元信息。",
        },
        {
            "title": "宣传与审慎提醒",
            "description": f"共有 {caution_count} 个来源整体信号偏弱，其中 {balance_risk} 个来源在宣传平衡性上存在明显风险。",
        },
    ]


def _compose_report_payload(
    auto_items: list[dict[str, Any]],
    manual_items: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = summarize_signal_items(auto_items, manual_items)
    return {
        "report_kind": "confidence_signal",
        "artifact_kind": "confidence_signal",
        "headline": "置信度信号",
        "subtitle": "围绕 A4 抓取答案中的引用来源，按 AICE 9C 维度生成一个可持续追加的可信信号工作面板。",
        "description": "每条来源均输出 AICE 维度得分、置信度和可执行修改建议；当前网页结构维度在未抓取 DOM 时按保守逻辑处理。",
        "updated_at": summary["updated_at"],
        "metrics": {
            "引用来源数": summary["total_citations"],
            "高置信": summary["high_confidence_count"],
            "需审慎": summary["caution_count"],
            "平均分": summary["average_score"],
        },
        "summary": summary,
        "auto_items": auto_items,
        "manual_items": manual_items,
        "aggregate_findings": build_aggregate_findings(auto_items, manual_items),
        "composer": {
            "enabled": True,
            "allowed_input_types": ["url", "text"],
            "placeholder": "粘贴链接或文本，生成额外评估",
            "helper_text": "支持单个链接、多个链接或一段文本；当前不支持把链接和文本混合提交。",
        },
        "status": {
            "phase": "ready",
            "message": "AICE 置信度信号已就绪",
        },
    }


def build_confidence_signal_report(
    fetch_results: list[dict[str, Any]] | None,
    *,
    manual_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    auto_items = extract_citations(fetch_results)
    manual_items = manual_items or []
    return _compose_report_payload(auto_items, manual_items)


async def build_confidence_signal_report_async(
    fetch_results: list[dict[str, Any]] | None,
    *,
    manual_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    auto_items = extract_citations(fetch_results)
    auto_items = await _enrich_url_items(auto_items)
    return _compose_report_payload(auto_items, manual_items or [])


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
    summary = summarize_signal_items(auto_items, merged_manual)

    updated = dict(existing_report)
    updated["manual_items"] = merged_manual
    updated["summary"] = summary
    updated["updated_at"] = summary["updated_at"]
    updated["metrics"] = {
        "引用来源数": summary["total_citations"],
        "高置信": summary["high_confidence_count"],
        "需审慎": summary["caution_count"],
        "平均分": summary["average_score"],
    }
    updated["aggregate_findings"] = build_aggregate_findings(auto_items, merged_manual)
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
    updated = _compose_report_payload(auto_items, merged_manual)
    updated["status"] = {
        "phase": "ready",
        "message": "额外评估已完成",
    }
    return updated


async def generate_confidence_signal_artifact(
    session_id: str,
    fetch_results: list[dict[str, Any]] | None,
) -> None:
    """Generate the independent A7 confidence signal artifact from A4 data."""
    from app.workflow.events import save_and_send_artifact

    report_data = await build_confidence_signal_report_async(fetch_results)
    await save_and_send_artifact(
        session_id=session_id,
        output_type="report",
        title="置信度信号",
        data=report_data,
        artifact_key=f"{session_id}_report_confidence_signal_main",
    )
