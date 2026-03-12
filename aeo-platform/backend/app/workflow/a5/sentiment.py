from __future__ import annotations

from typing import Any

from app.core.utils import extract_domain
from app.workflow.brand_mentions import content_mentions_brand, extract_brand_aliases
from app.workflow.a5.metrics import analyze_sentiment


def _collect_aliases(brand_profile: dict[str, Any]) -> list[str]:
    return extract_brand_aliases(brand_profile)


def _name_in_text(name: str, text: str) -> bool:
    if not name or not text:
        return False
    return name.lower() in text.lower()


def _excerpt(text: str, limit: int = 140) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "?"


def _citation_payload(citations: list[Any], brand_domain: str) -> tuple[list[str], list[str], list[str], bool]:
    domains: list[str] = []
    titles: list[str] = []
    urls: list[str] = []
    official = False

    for citation in citations or []:
        if not isinstance(citation, dict):
            continue
        url = str(citation.get("url", "") or "").strip()
        domain = extract_domain(url or "")
        title = str(citation.get("title", "") or "").strip()
        if domain and domain not in domains:
            domains.append(domain)
        if title and title not in titles:
            titles.append(title)
        if url and url not in urls:
            urls.append(url)
        if (
            brand_domain
            and domain
            and (domain == brand_domain or domain.endswith("." + brand_domain))
        ):
            official = True

    return domains[:5], titles[:3], urls[:5], official


def _build_summary(items: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"positive": 0, "neutral": 0, "negative": 0}
    for item in items:
        sentiment = str(item.get("sentiment", "neutral") or "neutral")
        if sentiment not in summary:
            sentiment = "neutral"
        summary[sentiment] += 1
    return summary


def build_mention_sentiment_analysis(
    fetch_results: list[dict[str, Any]],
    brand_profile: dict[str, Any],
    competitors: list[dict[str, Any]],
) -> dict[str, Any]:
    brand_aliases = _collect_aliases(brand_profile)
    brand_domain = extract_domain(brand_profile.get("official_website", "") or "")
    competitor_names = [
        str(item.get("name", "") or "").strip()
        for item in competitors
        if isinstance(item, dict) and item.get("name")
    ]

    brand_items: list[dict[str, Any]] = []
    competitor_items: dict[str, list[dict[str, Any]]] = {name: [] for name in competitor_names}

    for index, result in enumerate(fetch_results, start=1):
        scenario_id = str(result.get("question_id") or f"q_{index:02d}")
        scenario_label = str(
            result.get("question_text")
            or result.get("query")
            or result.get("question")
            or result.get("title")
            or f"问题 {index}"
        ).strip()

        for platform_result in result.get("platform_results", []) or []:
            if not isinstance(platform_result, dict) or not platform_result.get("success"):
                continue

            platform = str(platform_result.get("platform", "") or "")
            answer = platform_result.get("answer", {})
            content = answer.get("content", "") if isinstance(answer, dict) else str(answer)
            if not content:
                continue

            citations = platform_result.get("citations", []) or []
            citation_domains, citation_titles, citation_urls, official_cited = _citation_payload(citations, brand_domain)
            sentiment = analyze_sentiment(content)
            evidence = _excerpt(content)

            brand_mentioned = False
            if isinstance(answer, dict) and answer.get("has_brand_mention"):
                brand_mentioned = True
            elif content_mentions_brand(content, brand_profile):
                brand_mentioned = True

            if brand_mentioned:
                brand_items.append({
                    "scenario_id": scenario_id,
                    "scenario_label": scenario_label,
                    "platform": platform,
                    "sentiment": sentiment,
                    "evidence": evidence,
                    "citation_domains": citation_domains,
                    "citation_titles": citation_titles,
                    "citation_urls": citation_urls,
                    "official_citation_present": official_cited,
                })

            for competitor_name in competitor_names:
                if not _name_in_text(competitor_name, content):
                    continue
                competitor_items.setdefault(competitor_name, []).append({
                    "competitor": competitor_name,
                    "scenario_id": scenario_id,
                    "scenario_label": scenario_label,
                    "platform": platform,
                    "sentiment": sentiment,
                    "evidence": evidence,
                    "citation_domains": citation_domains,
                    "citation_titles": citation_titles,
                    "citation_urls": citation_urls,
                    "official_citation_present": official_cited,
                })

    return {
        "brand": {
            "summary": _build_summary(brand_items),
            "items": brand_items,
        },
        "competitors": [
            {
                "competitor": name,
                "summary": _build_summary(items),
                "items": items,
            }
            for name, items in competitor_items.items()
            if items
        ],
    }
