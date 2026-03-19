from __future__ import annotations

import re
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


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(text)
    return result


def _sanitize_entity_label(label: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"^[与和及、，,\s]+", "", str(label or "").strip())).strip()


def _split_sentences(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(r"(?<=[。！？!?；;])", text)
    return [part.strip() for part in parts if part and len(part.strip()) >= 8]


def _extract_fact_sentences(texts: list[str], anchors: list[str]) -> list[str]:
    normalized_anchors = [anchor.replace(" ", "").lower() for anchor in anchors if anchor and anchor.strip()]
    if not normalized_anchors:
        return []

    sentences: list[str] = []
    for text in texts:
        for sentence in _split_sentences(text):
            normalized_sentence = sentence.replace(" ", "").lower()
            if any(anchor in normalized_sentence for anchor in normalized_anchors):
                sentences.append(sentence)
    return _unique_strings(sentences)[:3]


def _extract_generic_product_mentions(texts: list[str]) -> list[str]:
    merged = " ".join(texts)
    patterns = [
        r"[\u4e00-\u9fa5]{2,6}\s*Model\s?[A-Z0-9]+",
        r"[\u4e00-\u9fa5]{2,6}\s*[A-Za-z]{1,4}\d{1,4}[A-Za-z0-9+\-]*",
        r"[\u4e00-\u9fa5]{2,6}\s*\d{3,4}[A-Za-z0-9+\-]*",
        r"\bModel\s?[A-Z0-9]+\b",
    ]
    matches: list[str] = []
    for pattern in patterns:
        matches.extend(re.findall(pattern, merged, flags=re.IGNORECASE))
    return _unique_strings([_sanitize_entity_label(match) for match in matches])[:8]


def _extract_product_mentions(texts: list[str], brands: list[str]) -> list[str]:
    merged = " ".join(texts)
    matches: list[str] = []
    for brand in brands:
        compact_brand = re.sub(r"\s+", "", brand)
        if not compact_brand:
            continue
        pattern = re.compile(
            rf"{re.escape(compact_brand)}(?:\s|-)*(?:Model\s?[A-Z0-9]+|[A-Za-z]{{1,4}}\d{{1,4}}[A-Za-z0-9-]*|[A-Z]{{1,3}}\d{{1,3}}|[\u4e00-\u9fa5]{{1,4}}(?:版|车型|系列))",
            re.IGNORECASE,
        )
        matches.extend(pattern.findall(merged))
    return _unique_strings([_sanitize_entity_label(match) for match in matches])[:6]


def _build_brand_labels(brand_name: str, texts: list[str], brand_aliases: list[str]) -> list[str]:
    generic_products = _extract_generic_product_mentions(texts)
    products = _unique_strings(
        _extract_product_mentions(texts, brand_aliases)
        + [item for item in generic_products if brand_name and brand_name in item]
    )
    if products:
        labels: list[str] = []
        for product in products:
            if brand_name and brand_name in product:
                labels.append(product)
            elif brand_name:
                labels.append(f"{brand_name}/{product}")
        return _unique_strings(labels)[:4]

    return [f"{brand_name}/未涉及具体型号"] if brand_name else []


def _build_competitor_labels(competitor_names: list[str], texts: list[str], brand_name: str) -> list[str]:
    products = _unique_strings(
        _extract_product_mentions(texts, competitor_names)
        + _extract_generic_product_mentions(texts)
    )
    products = [item for item in products if not (brand_name and brand_name in item)]
    explicit_products = [
        product for product in products
        if any(name and name in product for name in competitor_names)
    ]
    if explicit_products:
        return explicit_products[:6]

    question_products = [
        item for item in _extract_generic_product_mentions(texts[:1])
        if not (brand_name and brand_name in item)
    ]
    return _unique_strings(
        [f"{name}/未涉及具体型号" for name in competitor_names]
        + question_products
        + products
    )[:6]


def _dominant_sentiment(items: list[dict[str, Any]]) -> str:
    positive = sum(1 for item in items if str(item.get("sentiment", "")) == "positive")
    negative = sum(1 for item in items if str(item.get("sentiment", "")) == "negative")
    if positive > negative:
        return "positive"
    if negative > positive:
        return "negative"
    return "neutral"


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
    brand_name = str(brand_profile.get("brand_name", "") or "").strip()
    brand_domain = extract_domain(brand_profile.get("official_website", "") or "")
    competitor_names = [
        str(item.get("name", "") or "").strip()
        for item in competitors
        if isinstance(item, dict) and item.get("name")
    ]

    brand_items: list[dict[str, Any]] = []
    competitor_items: dict[str, list[dict[str, Any]]] = {name: [] for name in competitor_names}
    grouped: dict[str, dict[str, Any]] = {}

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
            group_key = scenario_id or scenario_label
            group = grouped.setdefault(
                group_key,
                {
                    "key": group_key,
                    "question": scenario_label,
                    "platforms": [],
                    "source_labels": [],
                    "brand_items": [],
                    "competitor_items": [],
                    "brand_texts": [scenario_label],
                    "competitor_texts": [scenario_label],
                },
            )

            brand_mentioned = False
            if isinstance(answer, dict) and answer.get("has_brand_mention"):
                brand_mentioned = True
            elif content_mentions_brand(content, brand_profile):
                brand_mentioned = True

            if brand_mentioned:
                brand_payload = {
                    "scenario_id": scenario_id,
                    "scenario_label": scenario_label,
                    "platform": platform,
                    "sentiment": sentiment,
                    "evidence": evidence,
                    "citation_domains": citation_domains,
                    "citation_titles": citation_titles,
                    "citation_urls": citation_urls,
                    "official_citation_present": official_cited,
                }
                brand_items.append(brand_payload)
                group["brand_items"].append(brand_payload)
                group["brand_texts"].append(content)
                if platform:
                    group["platforms"].append(platform)
                group["source_labels"].extend(citation_domains)

            for competitor_name in competitor_names:
                if not _name_in_text(competitor_name, content):
                    continue
                competitor_payload = {
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
                }
                competitor_items.setdefault(competitor_name, []).append(competitor_payload)
                group["competitor_items"].append(competitor_payload)
                group["competitor_texts"].append(content)
                if platform:
                    group["platforms"].append(platform)
                group["source_labels"].extend(citation_domains)

    groups: list[dict[str, Any]] = []
    for group in grouped.values():
        brand_group_items = group.get("brand_items", [])
        if not brand_group_items:
            continue
        competitor_group_items = group.get("competitor_items", [])
        brand_labels = _build_brand_labels(
            brand_name,
            group.get("brand_texts", []),
            brand_aliases,
        )
        competitor_group_names = _unique_strings(
            [str(item.get("competitor", "") or "").strip() for item in competitor_group_items]
        )
        competitor_labels = _build_competitor_labels(
            competitor_group_names,
            group.get("competitor_texts", []),
            brand_name,
        )
        brand_facts = _extract_fact_sentences(
            group.get("brand_texts", []),
            [brand_name] + brand_labels,
        )[:2]
        competitor_facts = _extract_fact_sentences(
            group.get("competitor_texts", []),
            competitor_group_names + competitor_labels,
        )[:2]

        groups.append({
            "key": group.get("key", ""),
            "question": group.get("question", ""),
            "platforms": _unique_strings(group.get("platforms", [])),
            "source_labels": _unique_strings(group.get("source_labels", []))[:8],
            "brand_count": len(brand_group_items),
            "competitor_count": len(competitor_group_items),
            "sentiment": _dominant_sentiment(brand_group_items),
            "brand_sentiment": _dominant_sentiment(brand_group_items),
            "competitor_sentiment": _dominant_sentiment(competitor_group_items),
            "brand_labels": brand_labels,
            "competitor_labels": competitor_labels,
            "brand_facts": brand_facts,
            "competitor_facts": competitor_facts,
        })

    groups.sort(key=lambda item: (-int(item.get("brand_count", 0)), str(item.get("question", ""))))

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
        "groups": groups,
    }
