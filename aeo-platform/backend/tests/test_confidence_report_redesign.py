from __future__ import annotations

from app.workflow.confidence_analysis import (
    append_confidence_analysis_manual_items,
    build_confidence_analysis_report,
)


def _sample_fetch_results():
    return [
        {
            "question_id": "q_brand",
            "question_text": "BrandX AI architecture capabilities",
            "platform_results": [
                {
                    "platform": "gpt",
                    "citations": [
                        {
                            "title": "BrandX official AI architecture whitepaper 2026",
                            "url": "https://brandx.com/ai-whitepaper-2026",
                            "site_name": "BrandX",
                            "is_official": True,
                        },
                        {
                            "title": "CompetitorY product benchmark 2026",
                            "url": "https://competitory.com/product-benchmark-2026",
                            "site_name": "CompetitorY",
                            "is_official": False,
                        },
                    ],
                },
                {
                    "platform": "kimi",
                    "citations": [
                        {
                            "title": "BrandX official AI architecture whitepaper 2026",
                            "url": "https://brandx.com/ai-whitepaper-2026",
                            "site_name": "BrandX",
                            "is_official": True,
                        },
                        {
                            "title": "Industry AI report 2026 overview",
                            "url": "https://researchhub.org/ai-report-2026",
                            "site_name": "ResearchHub",
                            "is_official": False,
                        },
                    ],
                },
            ],
        }
    ]


def test_confidence_report_payload_contains_matrix_and_analysis_blocks():
    report = build_confidence_analysis_report(
        _sample_fetch_results(),
        brand_profile={"brand_name": "BrandX", "brand_keywords": ["BrandX", "Brand X"]},
        competitors=[{"name": "CompetitorY"}],
        aice_threshold=83.0,
    )

    assert report["report_kind"] == "confidence_analysis"
    assert report["artifact_kind"] == "confidence_analysis"
    assert report["headline"] == "置信度报告"
    assert report["config"]["low_confidence_threshold"] == 83.0
    assert report["summary"]["total_citations"] == 3
    assert report["summary"]["brand_count"] == 1
    assert report["summary"]["competitor_count"] == 1
    assert "brand_confidence_overview" in report
    assert "competitor_confidence_overview" in report
    assert "brand_low_confidence_patterns" in report
    assert "competitor_low_confidence_patterns" in report
    assert "strategic_recommendations" in report


def test_confidence_report_classifies_brand_competitor_and_general_knowledge():
    report = build_confidence_analysis_report(
        _sample_fetch_results(),
        brand_profile={"brand_name": "BrandX", "brand_keywords": ["BrandX"]},
        competitors=[{"name": "CompetitorY"}],
    )

    items = {item["domain"]: item for item in report["auto_items"]}

    assert items["brandx.com"]["entity_classification"] == "brand"
    assert items["competitory.com"]["entity_classification"] == "competitor"
    assert items["researchhub.org"]["entity_classification"] == "general_knowledge"

    assert items["brandx.com"]["frequency"] == 2
    assert items["brandx.com"]["aice_score"] == items["brandx.com"]["overall_score"]
    assert items["brandx.com"]["quadrant_label"]
    assert items["brandx.com"]["quadrant_description"]
    assert report["summary"]["general_knowledge_count"] == 1


def test_confidence_report_respects_custom_aice_threshold_for_quadrants():
    report = build_confidence_analysis_report(
        _sample_fetch_results(),
        brand_profile={"brand_name": "BrandX", "brand_keywords": ["BrandX"]},
        competitors=[{"name": "CompetitorY"}],
        aice_threshold=95.0,
    )

    brand_item = next(item for item in report["auto_items"] if item["domain"] == "brandx.com")

    assert report["config"]["low_confidence_threshold"] == 95.0
    assert brand_item["quadrant"] == "q2_false_prosperity"


def test_append_manual_items_reuses_existing_threshold():
    report = build_confidence_analysis_report(
        _sample_fetch_results(),
        brand_profile={"brand_name": "BrandX", "brand_keywords": ["BrandX"]},
        competitors=[{"name": "CompetitorY"}],
        aice_threshold=83.0,
    )

    updated = append_confidence_analysis_manual_items(
        report,
        raw_input="https://brandx.com/product-specs-2026",
    )

    assert updated["report_kind"] == "confidence_analysis"
    assert updated["config"]["low_confidence_threshold"] == 83.0
    assert len(updated["manual_items"]) == 1
    assert updated["status"]["phase"] == "ready"
