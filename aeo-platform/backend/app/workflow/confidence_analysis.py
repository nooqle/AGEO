"""Compatibility helpers for the legacy confidence analysis artifact.

The old executor has been retired, but historical report payload tests still
exercise the artifact builder contract. Keep this module deterministic and
side-effect free so it remains a stable compatibility surface.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from urllib.parse import urlparse


DEFAULT_AICE_THRESHOLD = 80.0


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_domain(url: str | None, fallback: str | None = None) -> str:
    parsed = urlparse(_normalize_text(url))
    host = parsed.netloc or parsed.path
    host = host.lower().removeprefix("www.").strip("/")
    return host or _normalize_text(fallback).lower()


def _brand_keywords(brand_profile: dict[str, Any] | None) -> list[str]:
    profile = brand_profile or {}
    keywords = [_normalize_text(profile.get("brand_name"))]
    keywords.extend(_normalize_text(item) for item in profile.get("brand_keywords") or [])
    return [item.lower() for item in keywords if item]


def _competitor_keywords(competitors: list[dict[str, Any]] | None) -> list[str]:
    keywords: list[str] = []
    for competitor in competitors or []:
        keywords.append(_normalize_text(competitor.get("name")))
        keywords.append(_normalize_text(competitor.get("display_name")))
    return [item.lower() for item in keywords if item]


def _classify_source(
    citation: dict[str, Any],
    *,
    brand_keywords: list[str],
    competitor_keywords: list[str],
) -> str:
    searchable = " ".join(
        [
            _normalize_text(citation.get("title")),
            _normalize_text(citation.get("url")),
            _normalize_text(citation.get("site_name")),
            _normalize_domain(citation.get("url"), citation.get("site_name")),
        ]
    ).lower()
    if citation.get("is_official") is True:
        return "brand"
    if any(keyword and keyword in searchable for keyword in brand_keywords):
        return "brand"
    if any(keyword and keyword in searchable for keyword in competitor_keywords):
        return "competitor"
    return "general_knowledge"


def _score_item(frequency: int, platform_count: int) -> float:
    if platform_count <= 0:
        return 0.0
    coverage = min(frequency / platform_count, 1.0)
    return round(55.0 + coverage * 35.0, 2)


def _quadrant(score: float, threshold: float, classification: str) -> tuple[str, str, str]:
    if score >= threshold and classification == "brand":
        return (
            "q1_trusted_asset",
            "可信资产",
            "该来源与品牌强相关，并且在当前样本中有稳定出现。",
        )
    if score < threshold and classification == "brand":
        return (
            "q2_false_prosperity",
            "虚假繁荣",
            "该来源与品牌相关，但稳定性还没有达到当前阈值。",
        )
    if classification == "competitor":
        return (
            "q3_competitor_pressure",
            "竞品压力",
            "该来源更容易把答案导向竞品或竞品叙事。",
        )
    return (
        "q4_general_knowledge",
        "通用知识",
        "该来源提供背景信息，但不是品牌或竞品的直接资产。",
    )


def _iter_citations(fetch_results: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    citations: list[tuple[str, dict[str, Any]]] = []
    for question in fetch_results or []:
        question_id = _normalize_text(question.get("question_id"))
        for platform_result in question.get("platform_results") or []:
            platform = _normalize_text(platform_result.get("platform"))
            for citation in platform_result.get("citations") or []:
                citation_payload = dict(citation or {})
                citation_payload["question_id"] = question_id
                citation_payload["platform"] = platform
                citations.append((platform, citation_payload))
    return citations


def build_confidence_analysis_report(
    fetch_results: list[dict[str, Any]],
    *,
    brand_profile: dict[str, Any] | None = None,
    competitors: list[dict[str, Any]] | None = None,
    aice_threshold: float = DEFAULT_AICE_THRESHOLD,
) -> dict[str, Any]:
    """Build a deterministic legacy confidence analysis artifact."""
    brand_terms = _brand_keywords(brand_profile)
    competitor_terms = _competitor_keywords(competitors)
    citations = _iter_citations(fetch_results)
    platform_count = len({platform for platform, _ in citations if platform}) or 1

    grouped: dict[str, dict[str, Any]] = {}
    for _, citation in citations:
        domain = _normalize_domain(citation.get("url"), citation.get("site_name"))
        if not domain:
            continue
        item = grouped.setdefault(
            domain,
            {
                "domain": domain,
                "title": _normalize_text(citation.get("title")),
                "url": _normalize_text(citation.get("url")),
                "site_name": _normalize_text(citation.get("site_name")),
                "frequency": 0,
                "question_ids": set(),
                "platforms": set(),
                "samples": [],
                "entity_classification": _classify_source(
                    citation,
                    brand_keywords=brand_terms,
                    competitor_keywords=competitor_terms,
                ),
            },
        )
        item["frequency"] += 1
        if citation.get("question_id"):
            item["question_ids"].add(citation["question_id"])
        if citation.get("platform"):
            item["platforms"].add(citation["platform"])
        item["samples"].append(
            {
                "title": _normalize_text(citation.get("title")),
                "url": _normalize_text(citation.get("url")),
                "platform": _normalize_text(citation.get("platform")),
            }
        )

    auto_items: list[dict[str, Any]] = []
    for item in grouped.values():
        score = _score_item(int(item["frequency"]), platform_count)
        quadrant, quadrant_label, quadrant_description = _quadrant(
            score,
            float(aice_threshold),
            str(item["entity_classification"]),
        )
        auto_items.append(
            {
                **item,
                "question_ids": sorted(item["question_ids"]),
                "platforms": sorted(item["platforms"]),
                "aice_score": score,
                "overall_score": score,
                "quadrant": quadrant,
                "quadrant_label": quadrant_label,
                "quadrant_description": quadrant_description,
            }
        )

    auto_items.sort(key=lambda row: (-int(row["frequency"]), str(row["domain"])))
    brand_items = [item for item in auto_items if item["entity_classification"] == "brand"]
    competitor_items = [
        item for item in auto_items if item["entity_classification"] == "competitor"
    ]
    general_items = [
        item for item in auto_items if item["entity_classification"] == "general_knowledge"
    ]

    return {
        "report_kind": "confidence_analysis",
        "artifact_kind": "confidence_analysis",
        "headline": "置信度报告",
        "config": {"low_confidence_threshold": float(aice_threshold)},
        "status": {"phase": "ready"},
        "summary": {
            "total_citations": len(auto_items),
            "brand_count": len(brand_items),
            "competitor_count": len(competitor_items),
            "general_knowledge_count": len(general_items),
        },
        "auto_items": auto_items,
        "manual_items": [],
        "brand_confidence_overview": brand_items,
        "competitor_confidence_overview": competitor_items,
        "brand_low_confidence_patterns": [
            item for item in brand_items if item["aice_score"] < float(aice_threshold)
        ],
        "competitor_low_confidence_patterns": competitor_items,
        "strategic_recommendations": [],
    }


def append_confidence_analysis_manual_items(
    report: dict[str, Any],
    *,
    raw_input: str,
) -> dict[str, Any]:
    """Append a manually supplied source to a legacy confidence artifact."""
    updated = deepcopy(report)
    manual_items = list(updated.get("manual_items") or [])
    domain = _normalize_domain(raw_input)
    manual_items.append(
        {
            "domain": domain,
            "url": _normalize_text(raw_input),
            "entity_classification": "manual_review",
            "status": "pending_review",
        }
    )
    updated["manual_items"] = manual_items
    updated["status"] = {"phase": "ready"}
    updated.setdefault("report_kind", "confidence_analysis")
    updated.setdefault("artifact_kind", "confidence_analysis")
    updated.setdefault(
        "config",
        {"low_confidence_threshold": DEFAULT_AICE_THRESHOLD},
    )
    return updated
