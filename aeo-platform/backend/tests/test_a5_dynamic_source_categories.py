from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-secret")

from app.workflow.a5.diagnosis import build_source_intelligence
from app.workflow.a5.canonical import build_input_bundle, build_metric_bundle
from app.workflow.nodes_a5 import _calculate_metrics
from app.workflow.nodes_a4 import (
    _citation_information_updated_at,
    _collect_citation_intelligence_targets,
)


def test_a4_collects_url_level_targets_for_domain_skill():
    fetch_results = [
        {
            "platform_results": [
                {
                    "citations": [
                        {
                            "url": "https://m.bohe.cn/article/a.html",
                            "title": "文章 A",
                        },
                        {
                            "url": "https://m.bohe.cn/article/b.html",
                            "title": "文章 B",
                        },
                    ]
                }
            ]
        }
    ]

    targets = _collect_citation_intelligence_targets(fetch_results)

    assert [target.url for target in targets] == [
        "https://m.bohe.cn/article/a.html",
        "https://m.bohe.cn/article/b.html",
    ]
    assert [target.canonical_domain for target in targets] == ["bohe.cn", "bohe.cn"]


def test_a4_citation_information_updated_at_prefers_existing_value():
    value, source = _citation_information_updated_at(
        citation={"metadata": {"published_at": "2026-04-01"}},
        platform_result={"fetched_at": "2026-04-02T00:00:00+00:00"},
        fetch_result={},
        fallback="2026-04-03T00:00:00+00:00",
    )

    assert value == "2026-04-01"
    assert source == "metadata"


def test_a5_uses_url_intelligence_category_as_source_type():
    fetch_results = [
        {
            "question_id": "q1",
            "question_text": "纽崔莱蛋白粉怎么样？",
            "platform_results": [
                {
                    "platform": "doubao",
                    "success": True,
                    "answer": {"content": "纽崔莱蛋白粉经常被健康内容引用。"},
                    "citations": [
                        {
                            "title": "百度健康：蛋白粉",
                            "url": "https://health.baidu.com/example",
                            "canonical_domain": "health.baidu.com",
                            "site_display_name": "百度健康",
                            "site_category": "健康医疗/垂直内容",
                            "source_type": "other",
                            "snippet": "纽崔莱蛋白粉健康内容",
                            "url_intelligence": {
                                "domain": "health.baidu.com",
                                "site_name": "百度健康",
                                "category": "健康医疗/垂直内容",
                            },
                            "information_updated_at": "2026-04-30T01:00:00+00:00",
                            "information_updated_at_source": "a4_enrichment",
                        }
                    ],
                }
            ],
        }
    ]

    bundle = build_input_bundle(
        session_id="session-1",
        entity_id="entity-1",
        analysis_mode="panorama",
        brand_profile={
            "brand_name": "纽崔莱",
            "official_website": "https://www.amway.com.cn",
        },
        competitors=[],
        fetch_results=fetch_results,
    )
    _, metric_bundle = build_metric_bundle(bundle)

    citation = bundle.answers[0].citation_records[0]
    assert citation.source_type == "健康医疗/垂直内容"
    assert citation.site_category == "健康医疗/垂直内容"
    assert citation.url_intelligence["domain"] == "health.baidu.com"
    assert citation.information_updated_at == "2026-04-30T01:00:00+00:00"
    assert citation.information_updated_at_source == "a4_enrichment"

    assert (
        metric_bundle.source_summary["source_type_breakdown"]["健康医疗/垂直内容"]
        == 1.0
    )
    assert metric_bundle.source_summary["top_domains"][0]["site_category"] == (
        "健康医疗/垂直内容"
    )

    source = build_source_intelligence(metric_bundle.model_dump(), competitors=[])
    assert source["domains"][0]["source_type_label"] == "健康医疗/垂直内容"
    assert "规则库" not in source["domains"][0]["recommended_action"]


def test_legacy_metrics_preserve_a4_source_fields_for_domain_aggregation():
    metrics = _calculate_metrics(
        [
            {
                "question_id": "q1",
                "platform_results": [
                    {
                        "platform": "doubao",
                        "success": True,
                        "answer": {"content": "理想汽车经常被汽车媒体引用。"},
                        "citations": [
                            {
                                "title": "6座SUV--家庭/商务全场景推荐_懂车帝",
                                "url": "https://www.dongchedi.com/article/1",
                                "canonical_domain": "dongchedi.com",
                                "site_display_name": "懂车帝",
                                "site_category": "汽车垂直媒体",
                                "source_type": "other",
                                "url_intelligence": {
                                    "domain": "dongchedi.com",
                                    "site_name": "懂车帝",
                                    "category": "汽车垂直媒体",
                                },
                            }
                        ],
                    }
                ],
            }
        ],
        {"brand_name": "理想汽车", "official_website": "https://www.lixiang.com"},
    )

    domain = metrics["citation_analysis"]["top_domains"][0]
    assert domain["domain"] == "dongchedi.com"
    assert domain["display_name"] == "懂车帝"
    assert domain["source_type"] == "汽车垂直媒体"
    assert domain["site_category"] == "汽车垂直媒体"
