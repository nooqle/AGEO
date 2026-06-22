import os
import re

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret")

from app.services.amway_entity_calibration_service import (
    AmwayEntityCalibrationService,
)
from app.services.amway_entity_extraction_service import (
    AmwayEntityExtractionService,
)
from app.workflow.a5.association_circle import (
    build_brand_association_circle_report_artifact,
)
from app.workflow import nodes_a4 as nodes_a4_module
from app.workflow.nodes_a4 import _build_amway_entity_pipeline_update
from tests.fixtures.association_circle_amway import amway_association_fetch_results


def test_amway_entity_extraction_outputs_answer_bound_signals():
    extraction = AmwayEntityExtractionService().extract_from_fetch_results(
        amway_association_fetch_results()
    )

    signals = extraction["signals"]
    names = {signal["entity_name"] for signal in signals}

    assert extraction["service"] == "AmwayEntityExtractionService"
    assert extraction["valid_answer_count"] == 6
    assert "纽崔莱" in names
    assert any(signal["entity_type"] == "Solution" for signal in signals)
    assert all(signal["answer_id"] for signal in signals)
    assert all(signal["evidence_text"] for signal in signals)
    assert all(signal["source_policy"] for signal in signals)


def test_answer_extraction_does_not_use_related_terms_as_answer_evidence():
    fetch_results = [
        {
            "question_id": "q_nutrition_compare",
            "question_text": "安利纽崔莱、汤臣倍健、Swisse 这些品牌，在长期健康管理上有什么区别？",
            "opportunity_point": "健康管理",
            "probe_type": "竞品比较探针",
            "platform_results": [
                {
                    "platform": "豆包",
                    "success": True,
                    "answer": {
                        "content": (
                            "纽崔莱价格偏高，采用直销+线上，有专业营养指导，"
                            "长期投入较高。Swisse 更偏跨境和轻补充。"
                        )
                    },
                }
            ],
        }
    ]

    extraction = AmwayEntityExtractionService().extract_from_fetch_results(
        fetch_results
    )
    signals = extraction["signals"]

    assert not [signal for signal in signals if signal["entity_name"] == "传销/拉人头"]
    assert any(
        signal["entity_name"] == "直销" and signal["matched_text"] == "直销"
        for signal in signals
    )


def test_direct_pyramid_risk_word_still_enters_risk_evidence():
    fetch_results = [
        {
            "question_id": "q_direct_risk",
            "question_text": "安利是不是容易被误解成传销或拉人头？",
            "opportunity_point": "风险认知",
            "probe_type": "品牌锚定风险探针",
            "platform_results": [
                {
                    "platform": "Kimi",
                    "success": True,
                    "answer": {
                        "content": (
                            "安利常被拿来讨论传销或拉人头的误解，"
                            "需要解释直销牌照、合规边界和收入预期。"
                        )
                    },
                }
            ],
        }
    ]
    extraction_service = AmwayEntityExtractionService()
    extraction = extraction_service.extract_from_fetch_results(fetch_results)
    calibration = AmwayEntityCalibrationService(
        extraction_service=extraction_service
    ).calibrate(
        fetch_results=fetch_results,
        extraction_result=extraction,
        center_terms=["安利"],
    )

    nodes = calibration["association_circle_projection"]["nodes"]
    risk_node = next(node for node in nodes if node["term"] == "传销/拉人头")
    evidence_index = calibration["evidence_index"]
    excerpts = [
        evidence_index[evidence_id]["answer_excerpt"]
        for evidence_id in risk_node["evidence_samples"]
    ]

    assert risk_node["is_risk_term"] is True
    assert any("传销" in excerpt or "拉人" in excerpt for excerpt in excerpts)


def test_internal_business_terms_do_not_become_risk_nodes():
    fetch_results = [
        {
            "question_id": "q_internal_business_terms",
            "question_text": "安利事业机会、直销、ABO、KOC 这些角色和模式怎么理解？",
            "opportunity_point": "事业机会",
            "probe_type": "品牌锚定风险探针",
            "platform_results": [
                {
                    "platform": "Kimi",
                    "success": True,
                    "answer": {
                        "content": (
                            "安利事业机会会涉及直销、ABO 和 KOC，"
                            "外界有时会讨论风险和争议，但这些词本身是安利体系内的业务角色与参与方式。"
                        )
                    },
                }
            ],
        }
    ]
    extraction_service = AmwayEntityExtractionService()
    extraction = extraction_service.extract_from_fetch_results(fetch_results)

    business_signals = [
        signal
        for signal in extraction["signals"]
        if signal["entity_name"] in {"安利事业机会", "直销", "ABO", "KOC"}
    ]
    assert business_signals
    assert all(signal["relation_type"] != "RISKS_AS" for signal in business_signals)

    calibration = AmwayEntityCalibrationService(
        extraction_service=extraction_service
    ).calibrate(
        fetch_results=fetch_results,
        extraction_result=extraction,
        center_terms=["安利"],
    )
    nodes = calibration["association_circle_projection"]["nodes"]
    business_nodes = [
        node for node in nodes if node["term"] in {"安利事业机会", "直销", "ABO", "KOC"}
    ]
    assert business_nodes
    assert all(node["is_risk_term"] is False for node in business_nodes)
    assert not (
        {"安利事业机会", "直销", "ABO", "KOC"}
        & {node["term"] for node in calibration["risk_map"]["risk_nodes"]}
    )
    security_pillar = next(
        pillar
        for pillar in calibration["strategy_storyline"]["pillars"]
        if pillar["key"] == "have_security"
    )
    assert not (
        {"安利事业机会", "直销", "ABO", "KOC"} & set(security_pillar["risk_terms"])
    )


def test_calibration_drops_legacy_related_term_answer_signal():
    fetch_results = [
        {
            "question_id": "q_legacy_related_term",
            "question_text": "安利纽崔莱和 Swisse 在长期健康管理上有什么区别？",
            "opportunity_point": "健康管理",
            "probe_type": "竞品比较探针",
            "platform_results": [
                {
                    "platform": "豆包",
                    "success": True,
                    "answer": {
                        "content": ("纽崔莱价格偏高，采用直销+线上，有专业营养指导。")
                    },
                }
            ],
        }
    ]
    legacy_signal = {
        "signal_id": "sig_legacy_related_term",
        "answer_id": "answer_q_legacy_related_term_doubao",
        "question_id": "q_legacy_related_term",
        "question": fetch_results[0]["question_text"],
        "platform": "豆包",
        "entity_id": "risk_pyramid_scheme",
        "entity_name": "传销/拉人头",
        "entity_type": "RiskLabel",
        "matched_text": "直销",
        "match_source": "related_term",
        "relation_type": "RISKS_AS",
        "evidence_text": "纽崔莱价格偏高，采用直销+线上，有专业营养指导。",
        "answer_position": "middle",
        "term_origin": "answer",
        "source_side": "answer",
        "graph_policy": {
            "main_orbit": "not_allowed",
            "risk_view": "aggregate_only",
            "target_gap_view": "not_allowed",
        },
        "source_policy": {"source_kind": "lexicon"},
        "review_status": "approved",
        "question_context": {
            "opportunity_point": "健康管理",
            "probe_type": "竞品比较探针",
        },
        "question_mentions_center": True,
        "answer_mentions_center": False,
        "near_center_context": False,
        "center_connection_basis": "question_mentions_center",
        "context_polarity": "negative",
        "risk_context_cues": ["直销"],
        "comparison_context_cues": [],
        "center_context_excerpt": "纽崔莱价格偏高，采用直销+线上，有专业营养指导。",
    }

    calibration = AmwayEntityCalibrationService().calibrate(
        fetch_results=fetch_results,
        extraction_result={"signals": [legacy_signal]},
        center_terms=["安利"],
    )

    terms = {
        node["term"] for node in calibration["association_circle_projection"]["nodes"]
    }
    assert "传销/拉人头" not in terms


def test_amway_entity_calibration_generates_projection_and_report_input():
    fetch_results = amway_association_fetch_results()
    extraction_service = AmwayEntityExtractionService()
    extraction = extraction_service.extract_from_fetch_results(fetch_results)
    calibration = AmwayEntityCalibrationService(
        extraction_service=extraction_service
    ).calibrate(
        fetch_results=fetch_results,
        extraction_result=extraction,
        center_terms=["安利"],
    )

    projection = calibration["association_circle_projection"]
    report_input = calibration["report_input"]
    nodes = projection["nodes"]

    assert calibration["service"] == "AmwayEntityCalibrationService"
    assert report_input["association_map"]["nodes"] == nodes
    assert report_input["strategy_validation"]
    assert projection["evidence_samples"]
    assert projection["platform_source_summary"]["platforms"]
    assert all(node["entity_id"] for node in nodes)
    assert all(node["term_origin"] in {"answer", "strategy"} for node in nodes)
    assert any(node["term"] == "纽崔莱" for node in nodes)
    assert projection["tracking_projection"]["status"] == "baseline"
    assert projection["tracking_projection"]["status_label"] == "首期基线"
    assert report_input["tracking_projection"] == projection["tracking_projection"]
    assert projection["priority_summary"] == report_input["priority_summary"]
    assert "top_risks" in projection["priority_summary"]
    assert "top_opportunities" in projection["priority_summary"]
    assert calibration["sample_scope"]["tracking_status_label"] == "首期基线"
    assert all(node.get("maturity_tier") for node in nodes)
    assert all(node.get("maturity_label") for node in nodes)


def test_calibration_splits_opportunity_maturity_and_structured_actions():
    fetch_results = amway_association_fetch_results()
    extraction_service = AmwayEntityExtractionService()
    extraction = extraction_service.extract_from_fetch_results(fetch_results)
    calibration = AmwayEntityCalibrationService(
        extraction_service=extraction_service
    ).calibrate(
        fetch_results=fetch_results,
        extraction_result=extraction,
        center_terms=["安利"],
    )

    nodes = calibration["association_circle_projection"]["nodes"]
    non_risk_tiers = {
        node["maturity_tier"] for node in nodes if not node.get("is_risk_term")
    }
    actions = calibration["association_circle_projection"]["association_actions"]

    assert "stable_asset" in non_risk_tiers
    assert non_risk_tiers.intersection(
        {"near_opportunity", "far_opportunity", "watch_signal", "evidence_gap"}
    )
    assert actions
    for action in actions[:4]:
        assert action["goal_metric"]
        assert action["review_criteria"]
        assert action["execution_steps"]
        assert "target_platforms" in action
        assert "target_scene" in action
        assert action["next_question_suggestion"]
    strategy_actions = {
        row["strategy_term"]: row["action_recommendation"]
        for row in calibration["strategy_validation"]
        if row.get("action_recommendation")
    }
    assert len(set(strategy_actions.values())) > 1


def test_non_amway_market_context_does_not_enter_brand_graph():
    fetch_results = [
        {
            "question_id": "q_market_only",
            "question_text": "中年人体重管理可以看哪些营养品牌？",
            "opportunity_point": "体重管理",
            "probe_type": "场景探针",
            "platform_results": [
                {
                    "platform": "豆包",
                    "success": True,
                    "answer": {
                        "content": (
                            "体重管理可以比较康宝莱、Swisse和蛋白粉产品，"
                            "同时关注饮食、运动和代谢管理。"
                        )
                    },
                }
            ],
        }
    ]
    extraction_service = AmwayEntityExtractionService()
    extraction = extraction_service.extract_from_fetch_results(fetch_results)
    market_only = [
        signal
        for signal in extraction["signals"]
        if signal["entity_name"] in {"康宝莱", "Swisse", "体重管理"}
    ]

    assert market_only
    assert all(
        signal["relation_type"] == "MARKET_CONTEXT_ONLY" for signal in market_only
    )

    calibration = AmwayEntityCalibrationService(
        extraction_service=extraction_service
    ).calibrate(
        fetch_results=fetch_results,
        extraction_result=extraction,
        center_terms=["安利"],
    )
    node_terms = {
        node["term"] for node in calibration["association_circle_projection"]["nodes"]
    }

    assert "康宝莱" not in node_terms
    assert "Swisse" not in node_terms
    assert calibration["sample_scope"]["market_context_signal_count"] >= len(
        market_only
    )


def test_non_named_question_metadata_cannot_force_brand_link():
    fetch_results = [
        {
            "question_id": "q_bad_metadata",
            "question_text": "中年人体重管理可以看哪些营养方案？",
            "mentions_amway": True,
            "opportunity_point": "体重管理",
            "probe_type": "场景探针",
            "platform_results": [
                {
                    "platform": "豆包",
                    "success": True,
                    "answer": {
                        "content": "可以从控糖、蛋白粉、运动计划和代谢管理入手。"
                    },
                }
            ],
        }
    ]
    extraction_service = AmwayEntityExtractionService()
    extraction = extraction_service.extract_from_fetch_results(fetch_results)
    signals = [
        signal
        for signal in extraction["signals"]
        if signal["entity_name"] in {"体重管理", "蛋白粉", "代谢管理"}
    ]

    assert signals
    assert all(signal["question_mentions_center"] is False for signal in signals)
    assert all(signal["relation_type"] == "MARKET_CONTEXT_ONLY" for signal in signals)

    calibration = AmwayEntityCalibrationService(
        extraction_service=extraction_service
    ).calibrate(
        fetch_results=fetch_results,
        extraction_result=extraction,
        center_terms=["安利"],
    )

    assert calibration["association_circle_projection"]["nodes"] == []


def test_non_named_question_only_links_entities_near_answer_center_context():
    fetch_results = [
        {
            "question_id": "q_answer_center_context",
            "question_text": "中年人体重管理可以看哪些营养方案？",
            "opportunity_point": "体重管理",
            "probe_type": "场景探针",
            "platform_results": [
                {
                    "platform": "Kimi",
                    "success": True,
                    "answer": {
                        "content": (
                            "如果考虑安利，可以从纽崔莱蛋白粉和体重管理方案入手。"
                            "另外市场上也有很多普通控糖建议。"
                        )
                    },
                }
            ],
        }
    ]
    extraction_service = AmwayEntityExtractionService()
    extraction = extraction_service.extract_from_fetch_results(fetch_results)
    linked = [
        signal
        for signal in extraction["signals"]
        if signal["entity_name"] in {"纽崔莱", "蛋白粉", "体重管理"}
    ]

    assert linked
    assert all(signal["question_mentions_center"] is False for signal in linked)
    assert any(
        signal["center_connection_basis"] == "answer_near_center" for signal in linked
    )
    assert any(signal["relation_type"] != "MARKET_CONTEXT_ONLY" for signal in linked)


def test_non_named_question_does_not_link_entities_far_from_answer_center():
    fetch_results = [
        {
            "question_id": "q_answer_center_far_context",
            "question_text": "中年人体重管理可以看哪些营养方案？",
            "opportunity_point": "体重管理",
            "probe_type": "场景探针",
            "platform_results": [
                {
                    "platform": "Kimi",
                    "success": True,
                    "answer": {
                        "content": (
                            "安利是一个跨品类品牌。"
                            + "这里先讨论普通生活建议。" * 40
                            + "体重管理可以从蛋白粉、控糖和运动计划入手。"
                        )
                    },
                }
            ],
        }
    ]
    extraction_service = AmwayEntityExtractionService()
    extraction = extraction_service.extract_from_fetch_results(fetch_results)
    entity_signals = [
        signal
        for signal in extraction["signals"]
        if signal["entity_name"] in {"体重管理", "蛋白粉"}
    ]

    assert entity_signals
    assert all(
        signal["center_connection_basis"] == "answer_mentions_center_far"
        for signal in entity_signals
    )
    assert all(
        signal["relation_type"] == "MARKET_CONTEXT_ONLY" for signal in entity_signals
    )

    calibration = AmwayEntityCalibrationService(
        extraction_service=extraction_service
    ).calibrate(
        fetch_results=fetch_results,
        extraction_result=extraction,
        center_terms=["安利"],
    )

    node_terms = {
        node["term"] for node in calibration["association_circle_projection"]["nodes"]
    }

    assert "体重管理" not in node_terms
    assert "蛋白粉" not in node_terms


def test_strategy_validation_excludes_market_context_questions_from_evidence_refs():
    fetch_results = [
        {
            "question_id": "q_market_relationship",
            "question_text": "我 55 岁左右，快退休了，想找一件有朋友、有价值感的事情，有什么建议？",
            "opportunity_point": "良好关系",
            "probe_type": "场景探针",
            "platform_results": [
                {
                    "platform": "豆包",
                    "success": True,
                    "answer": {
                        "content": "可以参加老友俱乐部、兴趣社群和志愿服务，获得朋友、陪伴和价值感。"
                    },
                }
            ],
        },
        {
            "question_id": "q_brand_relationship",
            "question_text": "朋友说安利适合退休前后参与，有社群、有朋友、有价值感，这靠谱吗？",
            "opportunity_point": "良好关系",
            "probe_type": "品牌锚定探针",
            "platform_results": [
                {
                    "platform": "Kimi",
                    "success": True,
                    "answer": {
                        "content": "安利可以通过美好生活社群提供朋友、陪伴和社群支持，但也要看投入和风险。"
                    },
                }
            ],
        },
    ]
    extraction_service = AmwayEntityExtractionService()
    extraction = extraction_service.extract_from_fetch_results(fetch_results)
    market_relationship_signals = [
        signal
        for signal in extraction["signals"]
        if signal["entity_name"] == "良好关系"
        and signal["question_id"] == "q_market_relationship"
    ]

    assert market_relationship_signals
    assert all(
        signal["relation_type"] == "MARKET_CONTEXT_ONLY"
        for signal in market_relationship_signals
    )

    calibration = AmwayEntityCalibrationService(
        extraction_service=extraction_service
    ).calibrate(
        fetch_results=fetch_results,
        extraction_result=extraction,
        center_terms=["安利"],
    )
    strategy_rows = calibration["strategy_validation"]
    relationship_row = next(
        row for row in strategy_rows if row["strategy_term"] == "良好关系"
    )
    relationship_node = next(
        node
        for node in calibration["association_circle_projection"]["nodes"]
        if node["term"] == "良好关系"
    )

    assert relationship_node["trigger_questions"] == ["q_brand_relationship"]
    assert relationship_row["question_refs"] == ["q_brand_relationship"]
    assert relationship_row["question_count"] == 1
    assert "q_market_relationship" in relationship_row["designed_question_refs"]
    assert "q_market_relationship" not in relationship_row["question_refs"]


def test_strategy_validation_selects_evidence_from_multiple_questions():
    fetch_results = [
        {
            "question_id": "q_relationship_1",
            "question_text": "安利能帮助退休后建立良好关系和社群陪伴吗？",
            "opportunity_point": "良好关系",
            "probe_type": "品牌锚定探针",
            "platform_results": [
                {
                    "platform": "Kimi",
                    "success": True,
                    "answer": {
                        "content": "安利可以通过美好生活社群、朋友陪伴和共同成长来支持良好关系。"
                    },
                }
            ],
        },
        {
            "question_id": "q_relationship_2",
            "question_text": "安利的美好生活社群能否带来良好关系？",
            "opportunity_point": "良好关系",
            "probe_type": "路径探针",
            "platform_results": [
                {
                    "platform": "豆包",
                    "success": True,
                    "answer": {
                        "content": "安利和美好生活社群可以连接兴趣、健康打卡与良好关系。"
                    },
                }
            ],
        },
        {
            "question_id": "q_relationship_3",
            "question_text": "安利适合用良好关系连接健康和事业机会吗？",
            "opportunity_point": "良好关系",
            "probe_type": "机会探针",
            "platform_results": [
                {
                    "platform": "元宝",
                    "success": True,
                    "answer": {
                        "content": "安利在健康产品、社群陪伴和事业机会之间形成良好关系路径。"
                    },
                }
            ],
        },
    ]
    extraction_service = AmwayEntityExtractionService()
    extraction = extraction_service.extract_from_fetch_results(fetch_results)
    calibration = AmwayEntityCalibrationService(
        extraction_service=extraction_service
    ).calibrate(
        fetch_results=fetch_results,
        extraction_result=extraction,
        center_terms=["安利"],
    )
    relationship_row = next(
        row
        for row in calibration["strategy_validation"]
        if row["strategy_term"] == "良好关系"
    )

    assert relationship_row["question_count"] >= 3
    assert set(relationship_row["question_refs"]) >= {
        "q_relationship_1",
        "q_relationship_2",
        "q_relationship_3",
    }
    assert len(relationship_row["evidence_refs"]) >= 3
    assert len(relationship_row["question_samples"]) >= 3


def test_competitor_in_amway_context_is_competition_relation():
    fetch_results = [
        {
            "question_id": "q_competitor",
            "question_text": "安利做体重管理时，用户会和哪些品牌比较？",
            "opportunity_point": "体重管理",
            "probe_type": "风险探针",
            "platform_results": [
                {
                    "platform": "Kimi",
                    "success": True,
                    "answer": {
                        "content": (
                            "安利在体重管理和营养补充场景里，常会被拿来和"
                            "康宝莱比较。康宝莱更容易被用户理解为减重方案。"
                        )
                    },
                }
            ],
        }
    ]
    extraction_service = AmwayEntityExtractionService()
    extraction = extraction_service.extract_from_fetch_results(fetch_results)

    assert any(
        signal["entity_name"] == "康宝莱" and signal["relation_type"] == "COMPETES_WITH"
        for signal in extraction["signals"]
    )

    calibration = AmwayEntityCalibrationService(
        extraction_service=extraction_service
    ).calibrate(
        fetch_results=fetch_results,
        extraction_result=extraction,
        center_terms=["安利"],
    )
    nodes = calibration["association_circle_projection"]["nodes"]
    competitor_node = next(node for node in nodes if node["term"] == "康宝莱")

    assert competitor_node["business_tag"] == "竞争关系"
    assert competitor_node["orbit_label"] == "竞争关系"
    assert competitor_node["is_risk_term"] is True
    assert "康宝莱" in calibration["risk_map"]["nodes"][0]["term"]
    assert (
        "康宝莱" in calibration["platform_summary"]["platforms"][0]["competition_nodes"]
    )


def test_single_answer_competitor_stays_far_signal():
    fetch_results = [
        {
            "question_id": "q_perfect_single",
            "question_text": "安利和纽崔莱做营养补充时，会被拿来和哪些品牌比较？",
            "opportunity_point": "营养补充",
            "probe_type": "竞品探针",
            "platform_results": [
                {
                    "platform": "Kimi",
                    "success": True,
                    "answer": {
                        "content": (
                            "安利和纽崔莱通常会先被联想到营养补充。"
                            "在很少数回答里，也可能有人顺带提到完美。"
                        )
                    },
                },
                {
                    "platform": "豆包",
                    "success": True,
                    "answer": {
                        "content": "安利和纽崔莱更常被放在植物营养和体重管理语境里讨论。"
                    },
                },
                {
                    "platform": "元宝",
                    "success": True,
                    "answer": {
                        "content": "安利的营养补充更容易通过纽崔莱、植物蛋白和科学营养被理解。"
                    },
                },
            ],
        }
    ]
    extraction_service = AmwayEntityExtractionService()
    extraction = extraction_service.extract_from_fetch_results(fetch_results)
    calibration = AmwayEntityCalibrationService(
        extraction_service=extraction_service
    ).calibrate(
        fetch_results=fetch_results,
        extraction_result=extraction,
        center_terms=["安利"],
    )
    nodes = calibration["association_circle_projection"]["nodes"]
    competitor_node = next(node for node in nodes if node["term"] == "完美")

    assert competitor_node["business_tag"] == "竞争关系"
    assert competitor_node["answer_count"] == 1
    assert competitor_node["platform_count"] == 1
    assert competitor_node["gravity_score"] <= 28
    assert competitor_node["distance_score"] >= 72


def test_regulation_context_is_risk_relation_not_stable_asset():
    fetch_results = [
        {
            "question_id": "q_regulation_risk",
            "question_text": "做安利事业机会时，直销牌照和监管风险怎么看？",
            "opportunity_point": "事业机会",
            "probe_type": "风险探针",
            "platform_results": [
                {
                    "platform": "Kimi",
                    "success": True,
                    "answer": {
                        "content": (
                            "安利事业机会的监管风险会被反复提及。"
                            "直销管理条例禁止多层计酬后，销售体系受到巨大影响，"
                            "用户仍要关注直销模式、发展下线和经营压力等风险。"
                        )
                    },
                }
            ],
        }
    ]
    extraction_service = AmwayEntityExtractionService()
    extraction = extraction_service.extract_from_fetch_results(fetch_results)
    calibration = AmwayEntityCalibrationService(
        extraction_service=extraction_service
    ).calibrate(
        fetch_results=fetch_results,
        extraction_result=extraction,
        center_terms=["安利"],
    )
    regulation_node = next(
        node
        for node in calibration["association_circle_projection"]["nodes"]
        if node["term"] == "监管信息"
    )

    assert regulation_node["is_risk_term"] is True
    assert regulation_node["business_tag"] == "风险认知"
    assert regulation_node["orbit"] == "risk_shadow"
    assert "监管信息" in {
        node["term"] for node in calibration["risk_map"]["risk_nodes"]
    }


def test_positive_regulation_context_does_not_become_amway_risk():
    fetch_results = [
        {
            "question_id": "q_regulation_positive",
            "question_text": "安利纽崔莱、汤臣倍健、Swisse 这些品牌，在长期健康管理上有什么区别？",
            "opportunity_point": "健康管理",
            "probe_type": "品牌比较探针",
            "platform_results": [
                {
                    "platform": "豆包",
                    "success": True,
                    "answer": {
                        "content": (
                            "汤臣倍健有蓝帽子认证和国产合规优势，适合基础补充。"
                            "纽崔莱属于中高价路线，直销加线上渠道，有专业营养指导，长期投入高。"
                        )
                    },
                }
            ],
        }
    ]
    extraction_service = AmwayEntityExtractionService()
    extraction = extraction_service.extract_from_fetch_results(fetch_results)
    regulation_signals = [
        signal
        for signal in extraction["signals"]
        if signal["entity_name"] == "监管信息"
    ]
    assert regulation_signals
    assert all(signal["relation_type"] != "RISKS_AS" for signal in regulation_signals)

    calibration = AmwayEntityCalibrationService(
        extraction_service=extraction_service
    ).calibrate(
        fetch_results=fetch_results,
        extraction_result=extraction,
        center_terms=["安利"],
    )
    assert "监管信息" not in {
        node["term"] for node in calibration["risk_map"]["risk_nodes"]
    }


def test_risk_denial_context_does_not_enter_risk_map():
    fetch_results = [
        {
            "question_id": "q_risk_denial",
            "question_text": "安利是不是传销？",
            "opportunity_point": "风险认知",
            "probe_type": "品牌锚定风险探针",
            "platform_results": [
                {
                    "platform": "Kimi",
                    "success": True,
                    "answer": {
                        "content": (
                            "安利不是传销，也不等于拉人头。它持有直销经营许可，"
                            "需要按合法合规边界理解。"
                        )
                    },
                }
            ],
        }
    ]
    extraction_service = AmwayEntityExtractionService()
    extraction = extraction_service.extract_from_fetch_results(fetch_results)
    pyramid_signals = [
        signal
        for signal in extraction["signals"]
        if signal["entity_name"] == "传销/拉人头"
    ]
    assert pyramid_signals
    assert {signal["relation_type"] for signal in pyramid_signals} == {"RISK_DENIED"}
    assert all(signal["context_polarity"] == "positive" for signal in pyramid_signals)

    calibration = AmwayEntityCalibrationService(
        extraction_service=extraction_service
    ).calibrate(
        fetch_results=fetch_results,
        extraction_result=extraction,
        center_terms=["安利"],
    )
    assert "传销/拉人头" not in {
        node["term"] for node in calibration["risk_map"]["risk_nodes"]
    }


def test_risk_attribution_context_enters_risk_map():
    fetch_results = [
        {
            "question_id": "q_risk_attribution",
            "question_text": "安利事业机会有什么风险？",
            "opportunity_point": "事业机会",
            "probe_type": "品牌锚定风险探针",
            "platform_results": [
                {
                    "platform": "Kimi",
                    "success": True,
                    "answer": {
                        "content": (
                            "安利事业机会容易被质疑为传销或拉人头，"
                            "发展下线、熟人压力和收入不稳定是主要风险。"
                        )
                    },
                }
            ],
        }
    ]
    extraction_service = AmwayEntityExtractionService()
    extraction = extraction_service.extract_from_fetch_results(fetch_results)
    pyramid_signals = [
        signal
        for signal in extraction["signals"]
        if signal["entity_name"] == "传销/拉人头"
    ]
    assert pyramid_signals
    assert any(signal["relation_type"] == "RISKS_AS" for signal in pyramid_signals)

    calibration = AmwayEntityCalibrationService(
        extraction_service=extraction_service
    ).calibrate(
        fetch_results=fetch_results,
        extraction_result=extraction,
        center_terms=["安利"],
    )
    assert "传销/拉人头" in {
        node["term"] for node in calibration["risk_map"]["risk_nodes"]
    }


def test_strategy_status_uses_context_stance_not_mentions_only():
    fetch_results = [
        {
            "question_id": "q_business_risk",
            "question_text": "朋友说安利适合人生再出发，这个风险大吗？",
            "opportunity_point": "人生再出发",
            "probe_type": "品牌锚定风险探针",
            "platform_results": [
                {
                    "platform": "Kimi",
                    "success": True,
                    "answer": {
                        "content": "安利人生再出发常被提到，但也伴随直销、发展下线、少数赚钱多数陪跑等风险。"
                    },
                },
                {
                    "platform": "豆包",
                    "success": True,
                    "answer": {
                        "content": "安利可以作为人生再出发讨论，但需要警惕熟人压力、囤货和变现难。"
                    },
                },
                {
                    "platform": "元宝",
                    "success": True,
                    "answer": {
                        "content": "安利人生再出发有合法直销背景，但风险、争议和经营压力需要先说清楚。"
                    },
                },
            ],
        }
    ]
    extraction_service = AmwayEntityExtractionService()
    extraction = extraction_service.extract_from_fetch_results(fetch_results)
    calibration = AmwayEntityCalibrationService(
        extraction_service=extraction_service
    ).calibrate(
        fetch_results=fetch_results,
        extraction_result=extraction,
        center_terms=["安利"],
    )
    row = next(
        item
        for item in calibration["strategy_validation"]
        if item["strategy_term"] == "人生再出发"
    )

    assert row["answer_mention_count"] >= 3
    assert row["status"] != "validated"
    assert row["validation_label"] in {"部分验证，伴随质疑", "风险遮蔽"}
    assert row["decision_tier"] in {"evidence_building", "risk_first"}


def test_review_regression_negative_context_does_not_become_positive_validation():
    shared_question = (
        "朋友说安利适合中年人做第二曲线，不只是卖货，也有健康、社群和事业机会，"
        "这个说法怎么判断？"
    )
    fetch_results = [
        {
            "question_id": "q_review_relationship",
            "question_text": shared_question,
            "opportunity_point": "良好关系",
            "probe_type": "品牌锚定风险探针",
            "platform_results": [
                {
                    "platform": "DeepSeek",
                    "success": True,
                    "answer": {
                        "content": (
                            "安利确实会把良好关系、社群陪伴和事业机会放在一起讲，"
                            "也会提到收入与保障。但直销基因的枷锁仍然存在，"
                            "其商业模式的核心依然是直销。少数赚钱、多数陪跑，"
                            "现实中的风险并未消失。2005年《直销管理条例》禁止多层计酬后，"
                            "销售体系受到巨大影响。"
                        )
                    },
                },
                {
                    "platform": "Kimi",
                    "success": True,
                    "answer": {
                        "content": (
                            "安利可以被放进第二曲线讨论，良好关系和社群陪伴有吸引力，"
                            "也能触及收入保障。但要理性看待直销模式、熟人压力和变现难，"
                            "不能把它直接当作稳妥事业。"
                        )
                    },
                },
                {
                    "platform": "元宝",
                    "success": True,
                    "answer": {
                        "content": (
                            "安利的健康、社群、事业机会能支持良好关系叙事，"
                            "但发展下线、囤货压力和收入不稳定会削弱财务保障。"
                            "它更像需要先验证的机会。"
                        )
                    },
                },
                {
                    "platform": "豆包",
                    "success": True,
                    "answer": {
                        "content": (
                            "安利会被一些回答描述为有朋友、有价值感的社群机会，"
                            "也会提到良好关系和财务保障。不过高投入、熟人销售压力和争议，"
                            "让这个机会需要谨慎评估。"
                        )
                    },
                },
            ],
        }
    ]
    extraction_service = AmwayEntityExtractionService()
    extraction = extraction_service.extract_from_fetch_results(fetch_results)

    regulation_signals = [
        signal
        for signal in extraction["signals"]
        if signal["entity_name"] == "监管信息"
    ]
    assert regulation_signals
    assert any(signal["relation_type"] == "RISKS_AS" for signal in regulation_signals)
    assert all(
        signal["context_polarity"] == "negative" for signal in regulation_signals
    )

    calibration = AmwayEntityCalibrationService(
        extraction_service=extraction_service
    ).calibrate(
        fetch_results=fetch_results,
        extraction_result=extraction,
        center_terms=["安利"],
    )
    nodes = calibration["association_circle_projection"]["nodes"]
    regulation_node = next(node for node in nodes if node["term"] == "监管信息")
    relationship_row = next(
        row
        for row in calibration["strategy_validation"]
        if row["strategy_term"] == "良好关系"
    )
    financial_row = next(
        row
        for row in calibration["strategy_validation"]
        if row["strategy_term"] == "财务保障"
    )
    evidence_index = calibration["evidence_index"]
    relationship_platforms = {
        evidence_index[evidence_id]["platform"]
        for evidence_id in relationship_row["evidence_refs"]
        if evidence_id in evidence_index
    }
    strong_terms = {
        node["term"]
        for node in nodes
        if node["orbit"] in {"core_near", "strong"} and not node.get("is_risk_term")
    }

    assert regulation_node["is_risk_term"] is True
    assert regulation_node["business_tag"] == "风险认知"
    assert regulation_node["orbit"] == "risk_shadow"
    assert "监管信息" not in strong_terms
    assert relationship_row["status"] != "validated"
    assert relationship_row["validation_label"] == "部分验证，伴随质疑"
    assert financial_row["status"] != "validated"
    assert relationship_row["stance_summary"]["skeptical"] >= 3
    assert financial_row["stance_summary"]["skeptical"] >= 2
    assert len(relationship_platforms) >= 3
    assert calibration["risk_map"]["risk_count"] >= 1
    assert "监管信息" in {
        node["term"] for node in calibration["risk_map"]["risk_nodes"]
    }


def test_strategy_scores_keep_separation_under_caution_context():
    fetch_results = [
        {
            "question_id": "q_relationship_strategy",
            "question_text": "安利的良好关系能否支持中年人的社群和价值感？",
            "opportunity_point": "良好关系",
            "probe_type": "品牌锚定风险探针",
            "platform_results": [
                {
                    "platform": "DeepSeek",
                    "success": True,
                    "answer": {
                        "content": "安利良好关系和社群陪伴有真实吸引力，但也要理性看待熟人压力。"
                    },
                },
                {
                    "platform": "Kimi",
                    "success": True,
                    "answer": {
                        "content": "安利可以用良好关系连接朋友和陪伴，不过直销模式带来的风险需要说明。"
                    },
                },
                {
                    "platform": "元宝",
                    "success": True,
                    "answer": {
                        "content": "安利良好关系能支持社群叙事，也要避免把风险包装成稳妥事业。"
                    },
                },
                {
                    "platform": "豆包",
                    "success": True,
                    "answer": {
                        "content": "安利良好关系、社群陪伴和价值感会被提及，但需要补充边界。"
                    },
                },
            ],
        },
        {
            "question_id": "q_security_strategy",
            "question_text": "安利能否带来财务保障？",
            "opportunity_point": "财务保障",
            "probe_type": "品牌锚定风险探针",
            "platform_results": [
                {
                    "platform": "Kimi",
                    "success": True,
                    "answer": {
                        "content": "安利财务保障有机会想象，但变现难和收入不稳定是需要谨慎评估的风险。"
                    },
                },
                {
                    "platform": "豆包",
                    "success": True,
                    "answer": {
                        "content": "安利财务保障不能直接承诺，少数赚钱多数陪跑的质疑需要被看见。"
                    },
                },
            ],
        },
    ]
    extraction_service = AmwayEntityExtractionService()
    extraction = extraction_service.extract_from_fetch_results(fetch_results)
    calibration = AmwayEntityCalibrationService(
        extraction_service=extraction_service
    ).calibrate(
        fetch_results=fetch_results,
        extraction_result=extraction,
        center_terms=["安利"],
    )
    rows = {
        row["strategy_term"]: row
        for row in calibration["strategy_validation"]
        if row["strategy_term"] in {"良好关系", "财务保障"}
    }

    assert rows["良好关系"]["node_score"] != rows["财务保障"]["node_score"]
    assert {rows["良好关系"]["node_score"], rows["财务保障"]["node_score"]} != {44}
    assert (
        rows["良好关系"]["answer_mention_count"]
        > rows["财务保障"]["answer_mention_count"]
    )
    assert (
        rows["良好关系"]["action_recommendation"]
        != rows["财务保障"]["action_recommendation"]
    )
    assert "社群" in rows["良好关系"]["action_recommendation"]
    assert "收入" in rows["财务保障"]["action_recommendation"]


def test_brand_assets_are_not_promoted_to_risk_by_shared_answer_context():
    fetch_results = [
        {
            "question_id": "q_asset_context",
            "question_text": "安利的科学研究和美好生活共创空间能否提升信任？",
            "opportunity_point": "科技产品力",
            "probe_type": "品牌锚定风险探针",
            "platform_results": [
                {
                    "platform": "Kimi",
                    "success": True,
                    "answer": {
                        "content": (
                            "安利可以用科学研究、科研背书和美好生活共创空间增强信任，"
                            "同时仍要解释直销模式、熟人压力和合规风险。"
                        )
                    },
                }
            ],
        }
    ]
    extraction_service = AmwayEntityExtractionService()
    extraction = extraction_service.extract_from_fetch_results(fetch_results)
    risky_signals = [
        signal
        for signal in extraction["signals"]
        if signal["entity_name"] in {"科学研究", "美好生活共创空间"}
        and signal["relation_type"] == "RISKS_AS"
    ]
    assert not risky_signals

    calibration = AmwayEntityCalibrationService(
        extraction_service=extraction_service
    ).calibrate(
        fetch_results=fetch_results,
        extraction_result=extraction,
        center_terms=["安利"],
    )
    nodes = {
        node["term"]: node
        for node in calibration["association_circle_projection"]["nodes"]
        if node["term"] in {"科学研究", "美好生活共创空间"}
    }

    assert nodes["科学研究"]["is_risk_term"] is False
    assert nodes["美好生活共创空间"]["is_risk_term"] is False
    assert "科学研究" not in {
        node["term"] for node in calibration["risk_map"]["risk_nodes"]
    }
    assert "美好生活共创空间" not in {
        node["term"] for node in calibration["risk_map"]["risk_nodes"]
    }
    findings = {
        finding["node_term"]: finding
        for finding in calibration["report_input"]["evidence_findings"]
        if finding["node_term"] in {"科学研究", "美好生活共创空间"}
    }
    assert findings["科学研究"]["claim"].find("风险") == -1
    assert findings["美好生活共创空间"]["claim"].find("风险") == -1


def test_brand_asset_risk_view_policy_blocks_risk_relation_override():
    extraction = {
        "signals": [
            {
                "answer_id": "answer_q_asset_kimi",
                "question_id": "q_asset_policy",
                "question": "安利如何用科学研究和美好生活共创空间提升信任？",
                "platform": "Kimi",
                "entity_id": "evidence_scientific_research",
                "entity_name": "科学研究",
                "entity_type": "EvidenceAsset",
                "matched_text": "科学研究",
                "relation_type": "RISKS_AS",
                "context_polarity": "negative",
                "evidence_text": "科学研究能提升信任，但同段回答也提醒直销模式和合规风险。",
                "center_context_excerpt": "安利可以用科学研究提升信任，但要解释合规风险。",
                "answer_position": "middle",
                "question_context": {"opportunity_point": "科技产品力"},
            },
            {
                "answer_id": "answer_q_asset_kimi",
                "question_id": "q_asset_policy",
                "question": "安利如何用科学研究和美好生活共创空间提升信任？",
                "platform": "Kimi",
                "entity_id": "touchpoint_better_life_cocreation_space",
                "entity_name": "美好生活共创空间",
                "entity_type": "Touchpoint",
                "matched_text": "美好生活共创空间",
                "relation_type": "RISKS_AS",
                "context_polarity": "negative",
                "evidence_text": "美好生活共创空间是社群触点，但同段回答也提醒熟人压力。",
                "center_context_excerpt": "安利可以用美好生活共创空间增强社群信任。",
                "answer_position": "middle",
                "question_context": {"opportunity_point": "良好关系"},
            },
        ]
    }
    fetch_results = [
        {
            "question_id": "q_asset_policy",
            "question_text": "安利如何用科学研究和美好生活共创空间提升信任？",
            "opportunity_point": "科技产品力",
            "platform_results": [
                {
                    "platform": "Kimi",
                    "success": True,
                    "answer": {
                        "content": "安利可以用科学研究和美好生活共创空间提升信任，但要解释合规风险。"
                    },
                }
            ],
        }
    ]

    calibration = AmwayEntityCalibrationService().calibrate(
        fetch_results=fetch_results,
        extraction_result=extraction,
        center_terms=["安利"],
    )
    nodes = {
        node["term"]: node
        for node in calibration["association_circle_projection"]["nodes"]
        if node["term"] in {"科学研究", "美好生活共创空间"}
    }

    assert nodes["科学研究"]["is_risk_term"] is False
    assert nodes["美好生活共创空间"]["is_risk_term"] is False
    assert "科学研究" not in {node["term"] for node in calibration["risk_map"]["nodes"]}
    assert "美好生活共创空间" not in {
        node["term"] for node in calibration["risk_map"]["nodes"]
    }


def test_failed_platform_is_requested_but_not_valid_platform():
    fetch_results = [
        {
            "question_id": "q_platform_scope",
            "question_text": "安利适合年轻人做主动健康管理吗？",
            "opportunity_point": "主动健康",
            "probe_type": "品牌锚定探针",
            "platform_results": [
                {
                    "platform": "Kimi",
                    "success": True,
                    "answer": {
                        "content": "安利可以通过纽崔莱、营养早餐和体重管理进入主动健康场景。"
                    },
                },
                {
                    "platform": "元宝",
                    "success": True,
                    "answer": {
                        "content": "安利的纽崔莱、营养补充和社群打卡适合做健康习惯管理。"
                    },
                },
                {
                    "platform": "豆包",
                    "success": True,
                    "answer": {
                        "content": "安利和纽崔莱常被用于营养早餐、运动营养和主动健康建议。"
                    },
                },
                {
                    "platform": "DeepSeek",
                    "success": False,
                    "error": "login_required",
                    "answer": {"content": ""},
                },
            ],
        }
    ]
    extraction_service = AmwayEntityExtractionService()
    extraction = extraction_service.extract_from_fetch_results(fetch_results)
    calibration = AmwayEntityCalibrationService(
        extraction_service=extraction_service
    ).calibrate(
        fetch_results=fetch_results,
        extraction_result=extraction,
        center_terms=["安利"],
    )

    sample_scope = calibration["sample_scope"]
    platform_summary = calibration["platform_summary"]
    platform_rows = {row["platform"]: row for row in platform_summary["platforms"]}

    assert sample_scope["total_answer_count"] == 4
    assert sample_scope["valid_answer_count"] == 3
    assert sample_scope["failed_answer_count"] == 1
    assert sample_scope["platform_count"] == 3
    assert sample_scope["requested_platform_count"] == 4
    assert set(sample_scope["platform_names"]) == {"Kimi", "元宝", "豆包"}
    assert set(sample_scope["requested_platform_names"]) == {
        "DeepSeek",
        "Kimi",
        "元宝",
        "豆包",
    }
    assert platform_summary["platform_count"] == 3
    assert platform_summary["requested_platform_count"] == 4
    assert platform_rows["DeepSeek"]["status"] == "failed"
    assert platform_rows["DeepSeek"]["valid_answer_count"] == 0
    assert platform_rows["DeepSeek"]["failed_answer_count"] == 1


def test_a5_consumes_calibrated_report_input_without_reextracting_nodes():
    fetch_results = amway_association_fetch_results()
    extraction_service = AmwayEntityExtractionService()
    extraction = extraction_service.extract_from_fetch_results(fetch_results)
    calibration = AmwayEntityCalibrationService(
        extraction_service=extraction_service
    ).calibrate(
        fetch_results=fetch_results,
        extraction_result=extraction,
        center_terms=["安利"],
    )

    artifact = build_brand_association_circle_report_artifact(
        session_id="session-calibrated",
        entity_id="entity-1",
        brand_profile={"brand_name": "安利中国"},
        fetch_results=fetch_results,
        center_terms=["安利"],
        entity_calibration_result=calibration,
    )

    projection = artifact["dashboard_projection"]["association_circle_projection"]
    narrative_text = "\n".join(
        "\n".join(str(item) for item in section.get("paragraphs") or [])
        for section in artifact["report_narrative_sections"]
    )

    assert (
        artifact["association_circle"]["nodes"]
        == calibration["association_circle_projection"]["nodes"]
    )
    assert projection["generated_from"] == "entity_calibration"
    assert artifact["report_input"] == calibration["report_input"]
    assert "核心判断" in artifact["report_markdown"]
    assert "四个价值支柱，在 AI 叙事里是什么状态" in artifact["report_markdown"]
    assert artifact["strategy_storyline"] == calibration["strategy_storyline"]
    assert projection["strategy_storyline"] == calibration["strategy_storyline"]
    assert "附录：平台样本" in artifact["report_markdown"]
    forbidden_pattern = "不" + "是" + r"[^。；\n]{0,80}" + "而" + "是"
    assert re.search(forbidden_pattern, narrative_text) is None


@pytest.mark.asyncio
async def test_a4_entity_pipeline_skips_non_association_context():
    update = await _build_amway_entity_pipeline_update(
        {"analysis_mode": "panorama"},
        session_id="headless-association-test",
        fetch_results=amway_association_fetch_results(),
    )

    assert update == {}


@pytest.mark.asyncio
async def test_a4_entity_pipeline_outputs_a5_ready_report_input():
    update = await _build_amway_entity_pipeline_update(
        {
            "analysis_mode": "brand_association_circle",
            "input_scope": {"active_center_term": "安利"},
        },
        session_id="headless-association-test",
        fetch_results=amway_association_fetch_results(),
    )

    assert update["entity_extraction_result"]["signals"]
    assert update["entity_calibration_result"]["report_input"]
    assert (
        update["brand_association_report_input"]
        == update["entity_calibration_result"]["report_input"]
    )
    assert update["association_circle_projection"]["generated_from"] == (
        "entity_calibration"
    )


@pytest.mark.asyncio
async def test_a4_entity_pipeline_persists_extraction_and_calibration_events(
    monkeypatch,
):
    persisted: list[dict] = []

    async def fake_persist_stage_result(state, **kwargs):
        persisted.append({"state": state, **kwargs})

    monkeypatch.setattr(
        nodes_a4_module,
        "_persist_a4_stage_result",
        fake_persist_stage_result,
    )

    await nodes_a4_module._build_amway_entity_pipeline_update(
        {
            "analysis_mode": "brand_association_circle",
            "input_scope": {"active_center_term": "安利"},
        },
        session_id="headless-association-test",
        fetch_results=amway_association_fetch_results(),
        task_id="task-for-stage-cache",
    )

    extraction_events = [
        item for item in persisted if item["stage"] == "EntityExtraction"
    ]
    calibration_events = [
        item for item in persisted if item["stage"] == "EntityCalibration"
    ]
    assert extraction_events
    assert calibration_events
    assert calibration_events[-1]["data"]["generated_from"] == "entity_calibration"
    assert calibration_events[-1]["task_id"] == "task-for-stage-cache"


@pytest.mark.asyncio
async def test_a4_entity_pipeline_keeps_realtime_extraction_observability():
    fetch_results = amway_association_fetch_results()
    realtime = AmwayEntityExtractionService().extract_from_fetch_results(
        fetch_results[:1]
    )
    realtime["realtime_extraction_enabled"] = True
    realtime["realtime_answer_ids"] = [
        record["answer_id"] for record in realtime["answer_signals"]
    ]

    update = await _build_amway_entity_pipeline_update(
        {
            "analysis_mode": "brand_association_circle",
            "input_scope": {"active_center_term": "安利"},
        },
        session_id="headless-association-test",
        fetch_results=fetch_results,
        realtime_extraction_result=realtime,
    )

    extraction = update["entity_extraction_result"]
    assert extraction["realtime_extraction_enabled"] is True
    assert extraction["realtime_signal_count"] == realtime["signal_count"]
    assert extraction["realtime_answer_signal_count"] == realtime["answer_signal_count"]


@pytest.mark.asyncio
async def test_a4_entity_pipeline_does_not_replay_batch_extraction_when_realtime_exists(
    monkeypatch,
):
    persisted: list[dict] = []

    async def fake_persist_stage_result(state, **kwargs):
        persisted.append({"state": state, **kwargs})

    monkeypatch.setattr(
        nodes_a4_module,
        "_persist_a4_stage_result",
        fake_persist_stage_result,
    )

    fetch_results = amway_association_fetch_results()
    realtime = AmwayEntityExtractionService().extract_from_fetch_results(
        fetch_results[:1]
    )
    realtime["realtime_extraction_enabled"] = True
    realtime["realtime_answer_ids"] = [
        record["answer_id"] for record in realtime["answer_signals"]
    ]

    await _build_amway_entity_pipeline_update(
        {
            "analysis_mode": "brand_association_circle",
            "input_scope": {"active_center_term": "安利"},
        },
        session_id="headless-association-test",
        fetch_results=fetch_results,
        realtime_extraction_result=realtime,
        task_id="task-realtime-no-replay",
    )

    extraction_events = [
        item for item in persisted if item["stage"] == "EntityExtraction"
    ]
    calibration_events = [
        item for item in persisted if item["stage"] == "EntityCalibration"
    ]

    assert extraction_events == []
    assert calibration_events
    assert calibration_events[-1]["data"]["generated_from"] == "entity_calibration"
    assert calibration_events[-1]["data"]["signal_count"] >= realtime["signal_count"]
