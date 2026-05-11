"""A1 web-search evidence helpers."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse, urlunparse


A1_WEB_SEARCH_PROMPT = (
    "你是品牌档案核验助手。请从网络搜索{search_result}中提取可用于核验品牌档案、"
    "官网、核心产品、竞品与竞品官网的证据。回答时必须保留来源标题、链接、媒体、"
    "发布日期和 refer；不要编造搜索结果以外的链接。"
)


def build_a1_web_search_tool() -> dict[str, Any]:
    """Build the GLM Web Search in Chat tool for A1 brand discovery."""

    return {
        "type": "web_search",
        "web_search": {
            "enable": True,
            "search_engine": "search_pro",
            "search_result": True,
            "search_prompt": A1_WEB_SEARCH_PROMPT,
            "count": 10,
            "search_recency_filter": "noLimit",
            "content_size": "high",
        },
    }


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_website_url(value: Any) -> str:
    """Normalize an A1 website field into a clickable HTTPS URL."""

    text = _clean_text(value)
    if not text:
        return ""
    if text.lower() in {"unknown", "n/a", "null", "none"}:
        return ""
    if text in {"未公开", "未知", "不确定", "未确认", "无"}:
        return ""

    text = re.sub(r"^[<（(【\\[]+", "", text)
    text = re.sub(r"[>）)】\\]。；;，,\s]+$", "", text)
    if text.startswith("//"):
        text = f"https:{text}"
    elif not re.match(r"^https?://", text, flags=re.I):
        text = f"https://{text}"

    parsed = urlparse(text)
    host = parsed.netloc.strip().lower()
    if not host or "." not in host:
        return ""
    path = parsed.path or "/"
    return urlunparse((parsed.scheme.lower() or "https", host, path, "", "", ""))


def _site_origin(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.netloc:
        return url
    return urlunparse(
        (parsed.scheme or "https", parsed.netloc.lower(), "/", "", "", "")
    )


def _domain_key(url: str) -> str:
    parsed = urlparse(normalize_website_url(url))
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


THIRD_PARTY_EVIDENCE_DOMAINS = {
    "baike.baidu.com",
    "baike.sogou.com",
    "chinapp.com",
    "mip.chinapp.com",
    "ilife.cn",
    "qcc.com",
    "tianyancha.com",
    "wikipedia.org",
    "zh.wikipedia.org",
    "weibo.com",
    "douyin.com",
    "xiaohongshu.com",
}


def _is_third_party_evidence_domain(url: str) -> bool:
    domain = _domain_key(url)
    return any(
        domain == blocked or domain.endswith(f".{blocked}")
        for blocked in THIRD_PARTY_EVIDENCE_DOMAINS
    )


def _target_terms(item: dict[str, Any]) -> list[str]:
    fields = (
        "brand_name",
        "brand_name_en",
        "name",
        "name_en",
        "english_name",
    )
    terms: list[str] = []
    for field in fields:
        value = _clean_text(item.get(field))
        if value and value not in terms:
            terms.append(value)
    return terms


def _evidence_website_candidates(
    target: dict[str, Any],
    evidence_sources: list[dict[str, str]],
) -> list[str]:
    terms = [term.lower() for term in _target_terms(target)]
    candidates: list[tuple[int, str]] = []

    for source in evidence_sources:
        link = normalize_website_url(source.get("link"))
        if not link or _is_third_party_evidence_domain(link):
            continue

        haystack = " ".join(
            _clean_text(source.get(field))
            for field in ("title", "link", "media", "refer", "usage")
        ).lower()
        if not any(term and term in haystack for term in terms):
            continue

        score = 0
        title = _clean_text(source.get("title"))
        if any(marker in title for marker in ("官网", "官方网站", "首页", "关于")):
            score += 4
        if any(
            term and term in _domain_key(link)
            for term in terms
            if re.search(r"[a-z]", term)
        ):
            score += 3
        if _clean_text(source.get("usage")):
            score += 1
        candidates.append((score, _site_origin(link)))

    ordered: list[str] = []
    for _score, url in sorted(candidates, key=lambda item: (-item[0], len(item[1]))):
        if url not in ordered:
            ordered.append(url)
    return ordered


async def repair_a1_website_fields(
    brand_profile: dict[str, Any],
    competitors: list[dict[str, Any]],
    evidence_sources: list[dict[str, str]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Normalize A1 official websites from web-search evidence only.

    The model may output plausible but unsupported domains. A1 already calls
    GLM web_search, so the blocking path trusts only evidence-backed candidates
    and avoids per-competitor HTTP probing.
    """

    async def repair_one(item: dict[str, Any], field: str) -> dict[str, Any]:
        next_item = dict(item)
        evidence_candidates = _evidence_website_candidates(next_item, evidence_sources)
        next_item[field] = evidence_candidates[0] if evidence_candidates else ""
        return next_item

    repaired_profile = await repair_one(brand_profile, "official_website")
    repaired_competitors = [
        await repair_one(comp, "website")
        for comp in competitors
        if isinstance(comp, dict)
    ]
    return repaired_profile, repaired_competitors


def normalize_evidence_sources(value: Any, *, limit: int = 12) -> list[dict[str, str]]:
    """Normalize model-returned A1 evidence sources for artifact persistence."""

    if not isinstance(value, list):
        return []

    sources: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue

        title = _clean_text(
            item.get("title") or item.get("source_title") or item.get("name")
        )
        link = _clean_text(
            item.get("link") or item.get("url") or item.get("source_url")
        )
        if not title and not link:
            continue

        sources.append(
            {
                "title": title or link,
                "link": link,
                "media": _clean_text(item.get("media") or item.get("site_name")),
                "publish_date": _clean_text(
                    item.get("publish_date") or item.get("published_at")
                ),
                "refer": _clean_text(item.get("refer") or item.get("ref")),
                "usage": _clean_text(
                    item.get("usage")
                    or item.get("supports")
                    or item.get("evidence_for")
                ),
            }
        )
        if len(sources) >= limit:
            break

    return sources
