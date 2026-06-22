import os
import re
from copy import deepcopy

os.environ.setdefault("JWT_SECRET", "test-secret")

from app.workflow.a5.association_circle import (
    REPORT_COPY_FORBIDDEN_PHRASES,
    REPORT_COPY_FORBIDDEN_PATTERNS,
    REPORT_KIND,
    build_brand_association_circle_report_artifact,
)
from app.services.amway_entity_calibration_service import (
    AmwayEntityCalibrationService,
)
from app.services.amway_entity_extraction_service import (
    AmwayEntityExtractionService,
)
from app.workflow.nodes_a5 import (
    _association_center_terms_from_state,
    _resolve_a5_analysis_mode,
)
from app.tools.question_generation import build_association_circle_question_matrix
from tests.fixtures.association_circle_amway import amway_association_fetch_results


def _calibrated_artifact(
    *,
    fetch_results: list[dict] | None = None,
    center_terms: list[str] | None = None,
    simulated_questions=None,
) -> dict:
    fetch_results = fetch_results or amway_association_fetch_results()
    extraction_service = AmwayEntityExtractionService()
    extraction = extraction_service.extract_from_fetch_results(fetch_results)
    calibration = AmwayEntityCalibrationService(
        extraction_service=extraction_service
    ).calibrate(
        fetch_results=fetch_results,
        extraction_result=extraction,
        center_terms=center_terms or ["安利"],
    )
    return build_brand_association_circle_report_artifact(
        session_id="session-1",
        entity_id="entity-1",
        brand_profile={"brand_name": "安利中国"},
        fetch_results=fetch_results,
        simulated_questions=simulated_questions,
        center_terms=center_terms,
        entity_calibration_result=calibration,
    )


def _calibration_payload(
    *,
    fetch_results: list[dict] | None = None,
    center_terms: list[str] | None = None,
) -> dict:
    fetch_results = fetch_results or amway_association_fetch_results()
    extraction_service = AmwayEntityExtractionService()
    extraction = extraction_service.extract_from_fetch_results(fetch_results)
    return AmwayEntityCalibrationService(
        extraction_service=extraction_service
    ).calibrate(
        fetch_results=fetch_results,
        extraction_result=extraction,
        center_terms=center_terms or ["安利"],
    )


def _review_regression_fetch_results() -> list[dict]:
    question = (
        "朋友说安利适合中年人做第二曲线，不只是卖货，也有健康、社群和事业机会，"
        "这个说法怎么判断？"
    )
    return [
        {
            "question_id": "q_review_relationship",
            "question_text": question,
            "opportunity_point": "良好关系",
            "probe_type": "品牌锚定风险探针",
            "platform_results": [
                {
                    "platform": "DeepSeek",
                    "success": True,
                    "answer": {
                        "content": (
                            "安利会把良好关系、社群陪伴和事业机会放在一起讲，"
                            "也会提到收入与保障。但直销基因的枷锁仍然存在，"
                            "少数赚钱、多数陪跑，现实中的风险并未消失。"
                            "2005年《直销管理条例》禁止多层计酬后，销售体系受到巨大影响。"
                        )
                    },
                },
                {
                    "platform": "Kimi",
                    "success": True,
                    "answer": {
                        "content": (
                            "安利可以被放进第二曲线讨论，良好关系和社群陪伴有吸引力，"
                            "也能触及收入保障。但要理性看待直销模式、熟人压力和变现难。"
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


def test_a5_route_prefers_association_circle_dashboard_context():
    mode = _resolve_a5_analysis_mode(
        {
            "analysis_mode": "persona",
            "dashboard_context": {"analysis_mode": "brand_association_circle"},
        },
        "persona",
    )

    assert mode == REPORT_KIND


def test_a5_center_terms_prefer_active_single_center():
    terms = _association_center_terms_from_state(
        {
            "input_scope": {
                "active_center_term": "纽崔莱",
                "center_terms": ["安利", "安利中国", "纽崔莱"],
            }
        }
    )

    assert terms == ["纽崔莱"]


def test_association_circle_report_keeps_explicit_single_center():
    artifact = _calibrated_artifact(
        center_terms=["纽崔莱"],
    )

    assert artifact["center_terms"] == ["纽崔莱"]
    assert artifact["dashboard_projection"]["association_circle_projection"][
        "center_terms"
    ] == ["纽崔莱"]


def test_a5_requires_entity_calibration_report_input():
    artifact = build_brand_association_circle_report_artifact(
        session_id="session-missing-calibration",
        entity_id="entity-1",
        brand_profile={"brand_name": "安利中国"},
        fetch_results=amway_association_fetch_results(),
        center_terms=["安利"],
    )

    projection = artifact["dashboard_projection"]["association_circle_projection"]

    assert artifact["status"] == "needs_entity_calibration"
    assert artifact["association_circle"]["nodes"] == []
    assert projection["status"] == "needs_entity_calibration"
    assert projection["generated_from"] == "missing_entity_calibration"
    assert artifact["report_quality_checks"]["passed"] is False


def test_association_circle_nodes_only_come_from_answers():
    artifact = _calibrated_artifact()

    nodes = artifact["association_circle"]["nodes"]
    terms = {node["term"] for node in nodes}

    assert artifact["report_kind"] == REPORT_KIND
    assert "纽崔莱" in terms
    assert all(node["source"] == "answer_parsed" for node in nodes)
    assert all(node["evidence_samples"] for node in nodes)
    assert all(node["term_origin"] in {"answer", "strategy"} for node in nodes)


def test_association_circle_scores_orbits_and_business_tags():
    artifact = _calibrated_artifact()

    nodes_by_term = {
        node["term"]: node for node in artifact["association_circle"]["nodes"]
    }
    risk_nodes = [
        node for node in artifact["association_circle"]["nodes"] if node["is_risk_term"]
    ]
    asset_node = nodes_by_term["纽崔莱"]

    assert risk_nodes
    assert all(node["business_tag"] in {"风险认知", "竞争关系"} for node in risk_nodes)
    assert all(
        node["business_tag"] == "风险认知"
        for node in risk_nodes
        if node.get("entity_type") != "Competitor"
    )
    assert all(node["orbit"] == "risk_shadow" for node in risk_nodes)
    assert asset_node["distance_score"] == (100 - asset_node["gravity_score"])
    assert nodes_by_term["人生再出发"]["orbit_reason"]
    assert {
        "frequency_score",
        "position_score",
        "relation_type_score",
        "scene_coverage_score",
        "model_consistency_score",
    }.issubset(asset_node)
    assert asset_node["gravity_score"] == round(
        asset_node["frequency_score"] * 0.30
        + asset_node["position_score"] * 0.20
        + asset_node["relation_type_score"] * 0.20
        + asset_node["scene_coverage_score"] * 0.15
        + asset_node["model_consistency_score"] * 0.15
    )


def test_association_circle_platform_comparison_is_evidence_backed():
    artifact = _calibrated_artifact()

    platform_comparison = artifact["platform_comparison"]
    platforms = {item["platform"] for item in platform_comparison}

    assert {"DeepSeek", "Kimi", "豆包", "元宝"}.issubset(platforms)
    for item in platform_comparison:
        assert item["answer_preference"]
        if item["preferred_nodes"]:
            assert item["dominant_orbit"] != "unknown"
        else:
            assert "暂未形成稳定代表节点" in item["answer_preference"]
        assert item["recommendation"]


def test_association_circle_report_outputs_action_recommendations():
    artifact = _calibrated_artifact()

    actions = artifact["association_actions"]

    assert actions
    assert any(action["action_type"] == "translate" for action in actions)
    assert any(action["evidence_refs"] for action in actions)
    assert all(action.get("goal_metric") for action in actions[:4])
    assert all(action.get("review_criteria") for action in actions[:4])
    assert all("target_platforms" in action for action in actions[:4])
    assert artifact["dashboard_projection"]["association_circle_projection"][
        "association_actions"
    ]
    assert any(
        section["section_name"] == "association_actions"
        for section in artifact["report_sections"]
    )


def test_association_circle_report_generation_enforces_human_copy_contract():
    artifact = _calibrated_artifact(center_terms=["安利"])

    sections = artifact["report_narrative_sections"]
    projection_sections = artifact["dashboard_projection"][
        "association_circle_projection"
    ]["report_narrative_sections"]
    narrative_text = "\n".join(
        [
            str(section.get("title") or "")
            + "\n"
            + "\n".join(str(item) for item in section.get("paragraphs") or [])
            for section in sections
        ]
    )
    narrative_markdown = artifact["report_markdown"].split("## 附录：平台样本", 1)[0]

    assert sections
    assert projection_sections == sections
    assert any(
        section["section_name"] == "narrative"
        for section in artifact["report_sections"]
    )
    assert "## 核心判断" in artifact["report_markdown"]
    assert "## 安利的 AI 档案里写了什么" in artifact["report_markdown"]
    assert "## 四个价值支柱，在 AI 叙事里是什么状态" in artifact["report_markdown"]
    assert "## 安利的 AI 盲区" in artifact["report_markdown"]
    assert "## 平台差异" in artifact["report_markdown"]
    assert "## 从数据到行动" in artifact["report_markdown"]
    assert "Executive Summary" not in artifact["report_markdown"]
    assert "## 战略词证据明细" not in artifact["report_markdown"]
    assert "## 综合战略判断" not in artifact["report_markdown"]
    assert "## 下一轮追踪建议" not in artifact["report_markdown"]
    assert "## 安利战略词逐项验证" not in artifact["report_markdown"]
    assert "## 风险与竞品关系" not in artifact["report_markdown"]
    assert "最致命发现" in artifact["report_markdown"]
    assert "要看见的事实" in artifact["report_markdown"]
    assert "四种差距" in artifact["report_markdown"]
    assert "不问就不说" in artifact["report_markdown"]
    assert "平台画像" in narrative_text
    assert "问题一：" in artifact["report_markdown"]
    assert "核心要点" not in artifact["report_markdown"]
    assert "战略词证据" not in narrative_markdown
    assert "战略意图" not in narrative_markdown
    assert "回答证据" not in narrative_markdown
    assert "图谱表现" not in narrative_markdown
    assert "品牌含义" not in narrative_markdown
    assert "### 主动健康" not in narrative_markdown
    assert "### 良好关系" not in narrative_markdown
    assert "### 财务保障" not in narrative_markdown
    assert "主动提及率" in artifact["report_markdown"]
    assert "四有战略" in narrative_text
    assert "有健康" in narrative_text
    assert "有陪伴" in narrative_text
    assert "有保障" in narrative_text
    assert "有价值" in narrative_text
    assert artifact["strategy_storyline"]["framework"] == "amway_four_have_storyline_v2"
    assert (
        artifact["dashboard_projection"]["association_circle_projection"][
            "strategy_storyline"
        ]["framework"]
        == "amway_four_have_storyline_v2"
    )
    assert all(section.get("takeaway") for section in sections)
    assert all(section.get("claims") for section in sections)
    assert all(section.get("so_what") for section in sections)
    assert all(section.get("reader_question") for section in sections)
    assert all(section.get("next_probe") for section in sections)
    assert "核心判断" in artifact["report_markdown"]
    assert "下一轮先恢复失败平台" not in artifact["report_markdown"]
    assert "下一轮固定同一题库" in artifact["report_markdown"]
    assert artifact["report_quality_checks"]["passed"] is True
    assert (
        artifact["dashboard_projection"]["association_circle_projection"][
            "report_quality_checks"
        ]["passed"]
        is True
    )
    assert artifact["copy_constraints"]["version"]
    assert artifact["copy_constraints"]["required_spine"]
    assert "required_section_fields" in artifact["copy_constraints"]
    assert (
        "required_section_fields"
        in artifact["dashboard_projection"]["association_circle_projection"][
            "copy_constraints"
        ]
    )
    for phrase in REPORT_COPY_FORBIDDEN_PHRASES:
        assert phrase not in narrative_text
    for pattern in REPORT_COPY_FORBIDDEN_PATTERNS:
        assert re.search(pattern, narrative_text) is None
    assert ("不" + "是") not in narrative_text
    assert ("而" + "是") not in narrative_text
    assert ("说" + "明") not in narrative_text


def test_report_backfills_storyline_for_legacy_calibrated_payloads():
    fetch_results = amway_association_fetch_results()
    calibration = deepcopy(_calibration_payload(fetch_results=fetch_results))
    calibration.pop("strategy_storyline", None)
    calibration["report_input"].pop("strategy_storyline", None)
    calibration["association_circle_projection"].pop("strategy_storyline", None)

    artifact = build_brand_association_circle_report_artifact(
        session_id="session-legacy-storyline",
        entity_id="entity-1",
        brand_profile={"brand_name": "安利中国"},
        fetch_results=fetch_results,
        simulated_questions=None,
        center_terms=["安利"],
        entity_calibration_result=calibration,
    )

    markdown = artifact["report_markdown"]
    assert artifact["strategy_storyline"]["framework"] == "amway_four_have_storyline_v2"
    assert "## 核心判断" in markdown
    assert "## 安利的 AI 档案里写了什么" in markdown
    assert "## 四个价值支柱，在 AI 叙事里是什么状态" in markdown
    assert "## 安利的 AI 盲区" in markdown
    assert "## 从数据到行动" in markdown
    assert "Executive Summary" not in markdown
    assert "战略词证据明细" not in markdown


def test_association_circle_report_includes_question_platform_and_evidence_spine():
    artifact = _calibrated_artifact(center_terms=["安利"])

    question_definition = artifact["question_definition"]
    platform_source_summary = artifact["platform_source_summary"]
    evidence_findings = artifact["evidence_findings"]
    source_appendix = artifact["source_appendix"]
    projection = artifact["dashboard_projection"]["association_circle_projection"]
    markdown = artifact["report_markdown"]

    assert question_definition["center_term"] == "安利"
    assert question_definition["question_count"] == 4
    assert question_definition["sample_questions"]
    assert {"35-50 初老期", "活力银发"}.issubset(
        set(question_definition["audience_segments"])
    )
    assert {"品牌锚定探针", "路径探针", "机会探针"}.issubset(
        set(question_definition["probe_types"])
    )

    assert platform_source_summary["valid_answer_count"] == 6
    assert platform_source_summary["total_answer_count"] == 6
    platform_names = {row["platform"] for row in platform_source_summary["platforms"]}
    assert {"DeepSeek", "Kimi", "豆包", "元宝", "ChatGPT"}.issubset(platform_names)
    assert all(
        "valid_answer_count" in row for row in platform_source_summary["platforms"]
    )

    assert evidence_findings
    assert all(finding["supporting_facts"] for finding in evidence_findings)
    assert all(finding["evidence_refs"] for finding in evidence_findings)
    assert any(finding["node_term"] == "纽崔莱" for finding in evidence_findings)

    assert projection["question_definition"] == question_definition
    assert projection["platform_source_summary"] == platform_source_summary
    assert projection["evidence_findings"] == evidence_findings[:80]
    assert source_appendix
    assert projection["source_appendix"] == source_appendix[:80]
    projection_evidence_ids = {
        item["evidence_id"] for item in projection["evidence_samples"]
    }
    for node in projection["nodes"]:
        assert set(node["evidence_samples"]).issubset(projection_evidence_ids)
    assert all(
        item["passed"] for item in artifact["report_quality_checks"]["required_checks"]
    )
    check_keys = {
        item["key"] for item in artifact["report_quality_checks"]["required_checks"]
    }
    assert "section_takeaway" in check_keys
    assert "section_contract" in check_keys
    assert "## 核心判断" in markdown
    assert projection["tracking_projection"]["status_label"] == "首期基线"
    assert artifact["tracking_projection"]["status"] == "baseline"
    verdict_pos = markdown.index("## 核心判断")
    archive_pos = markdown.index("## 安利的 AI 档案里写了什么")
    pillars_pos = markdown.index("## 四个价值支柱，在 AI 叙事里是什么状态")
    blind_pos = markdown.index("## 安利的 AI 盲区")
    platform_pos = markdown.index("## 平台差异")
    action_pos = markdown.index("## 从数据到行动")
    story_text = markdown[verdict_pos:action_pos]
    assert (
        verdict_pos < archive_pos < pillars_pos < blind_pos < platform_pos < action_pos
    )
    assert "战略词证据" not in story_text
    assert ("平台原文" in story_text) or ("AI 原文" in story_text)
    assert "## 战略词逐项明细" not in markdown
    assert "## 附录：平台样本" in markdown
    assert "DeepSeek" in markdown
    assert "Kimi" in markdown
    quote_lines = [
        line for line in story_text.splitlines() if line.startswith("- 平台原文样本：")
    ]
    assert len(quote_lines) == len(set(quote_lines))


def test_association_circle_report_uses_four_have_story_not_strategy_templates():
    artifact = _calibrated_artifact(center_terms=["安利"])

    strategy_validation = artifact["strategy_validation"]
    markdown = artifact["report_markdown"]
    narrative_markdown = markdown.split("## 附录：平台样本", 1)[0]

    assert strategy_validation
    assert len(strategy_validation) >= 4
    assert "## 四个价值支柱，在 AI 叙事里是什么状态" in narrative_markdown
    assert "叙事层级差距" in narrative_markdown
    assert "叙事被劫持" in narrative_markdown or "弱信号待确认" in narrative_markdown
    assert "差距类型为" in narrative_markdown
    assert "累计命中" in narrative_markdown or "占 " in narrative_markdown
    assert "战略词证据" not in narrative_markdown
    for row in strategy_validation:
        assert f"### {row['strategy_term']}" not in narrative_markdown
        assert row["action_recommendation"]
        assert row["platform_outcomes"]
        assert any(
            outcome["status"] in {"mentioned", "not_mentioned"}
            for outcome in row["platform_outcomes"]
        )
    assert ("平台原文" in narrative_markdown) or ("AI 原文" in narrative_markdown)
    assert "## 战略词逐项明细" not in markdown
    assert "证据编号" not in markdown
    assert "回答稳定度" not in markdown
    assert "距离值" not in narrative_markdown


def test_report_uses_negative_context_and_diverse_source_appendix():
    artifact = _calibrated_artifact(
        fetch_results=_review_regression_fetch_results(),
        center_terms=["安利"],
    )

    nodes = artifact["association_circle"]["nodes"]
    regulation_node = next(node for node in nodes if node["term"] == "监管信息")
    relationship_row = next(
        row
        for row in artifact["strategy_validation"]
        if row["strategy_term"] == "良好关系"
    )
    executive_summary = artifact["executive_summary"]
    appendix_platforms = {
        row["platform"] for row in artifact["source_appendix"][:8] if row["platform"]
    }
    appendix_nodes = {
        row["node_term"] for row in artifact["source_appendix"][:8] if row["node_term"]
    }
    assert regulation_node["is_risk_term"] is True
    assert regulation_node["business_tag"] == "风险认知"
    assert "监管信息" not in executive_summary["current_default_identity"]
    assert artifact["risk_summary"]["risk_count"] >= 1
    assert relationship_row["validation_label"] == "部分验证，伴随质疑"
    assert relationship_row["stance_summary"]["skeptical"] >= 3
    assert "## 四个价值支柱，在 AI 叙事里是什么状态" in artifact["report_markdown"]
    assert "熟人压力" in artifact["report_markdown"]
    assert len(appendix_platforms) >= 3
    assert len(appendix_nodes) >= 2


def test_report_keeps_brand_evidence_assets_out_of_risk_language():
    artifact = _calibrated_artifact(
        fetch_results=[
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
        ],
        center_terms=["安利"],
    )

    findings = {
        finding["node_term"]: finding
        for finding in artifact["evidence_findings"]
        if finding["node_term"] in {"科学研究", "美好生活共创空间"}
    }

    assert findings
    assert "科学研究" in findings
    assert "风险" not in findings["科学研究"]["claim"]
    if "美好生活共创空间" in findings:
        assert "风险" not in findings["美好生活共创空间"]["claim"]
    assert (
        "科学研究会把回答带向信任、合规或销售关系风险"
        not in artifact["report_markdown"]
    )


def test_association_circle_smoke_distinguishes_valid_failed_and_empty_answers():
    fetch_results = amway_association_fetch_results()
    fetch_results[0]["platform_results"].append(
        {
            "platform": "元宝",
            "success": False,
            "error": "login_required",
            "answer": {"content": ""},
        }
    )
    fetch_results[1]["platform_results"].append(
        {
            "platform": "DeepSeek",
            "success": True,
            "answer": {"content": ""},
        }
    )

    artifact = _calibrated_artifact(
        fetch_results=fetch_results,
        simulated_questions=build_association_circle_question_matrix(),
        center_terms=["安利", "安利中国", "纽崔莱"],
    )

    sample_scope = artifact["sample_scope"]
    nodes = artifact["association_circle"]["nodes"]
    question_bank = artifact["association_circle"]["question_bank"]

    assert sample_scope["total_answer_count"] == 8
    assert sample_scope["valid_answer_count"] == 6
    assert sample_scope["failed_answer_count"] == 1
    assert sample_scope["empty_answer_count"] == 1
    assert sample_scope["platform_count"] >= 2
    assert sample_scope["requested_platform_count"] >= sample_scope["platform_count"]
    assert nodes
    assert artifact["platform_comparison"]
    assert artifact["association_actions"]
    assert question_bank
    assert sample_scope["question_bank_count"] == len(question_bank)
    assert all(node["source"] == "answer_parsed" for node in nodes)
    assert all(node["evidence_samples"] for node in nodes)
    assert (
        artifact["dashboard_projection"]["association_circle_projection"]["nodes"]
        == nodes
    )
    assert (
        artifact["dashboard_projection"]["association_circle_projection"][
            "question_bank"
        ]
        == question_bank[:200]
    )
