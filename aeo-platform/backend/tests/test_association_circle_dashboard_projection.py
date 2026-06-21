import os
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret")

from app.services.brand_ontology_world_service import (
    BrandOntologyWorldService,
    _merge_association_actions_into_recommendations,
)
from app.services.amway_entity_calibration_service import (
    AmwayEntityCalibrationService,
)
from app.services.amway_entity_extraction_service import (
    AmwayEntityExtractionService,
)
from app.workflow.a5.association_circle import (
    build_brand_association_circle_report_artifact,
)
from tests.fixtures.association_circle_amway import amway_association_fetch_results


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def all(self):
        if self.value is None:
            return []
        if isinstance(self.value, list):
            return self.value
        return [self.value]


class _FakeDb:
    def __init__(self, report=None, question_rows=None):
        self.report = report
        self.question_rows = question_rows or []
        self.execute_count = 0

    async def execute(self, _statement):
        self.execute_count += 1
        if self.execute_count == 1:
            return _ScalarResult(self.report)
        return _ScalarResult(self.question_rows)


def _calibrated_artifact(
    *,
    session_id: str,
    entity_id: str,
    fetch_results: list[dict] | None = None,
) -> dict:
    fetch_results = fetch_results or amway_association_fetch_results()
    extraction_service = AmwayEntityExtractionService()
    extraction = extraction_service.extract_from_fetch_results(fetch_results)
    calibration = AmwayEntityCalibrationService(
        extraction_service=extraction_service
    ).calibrate(
        fetch_results=fetch_results,
        extraction_result=extraction,
        center_terms=["安利"],
    )
    return build_brand_association_circle_report_artifact(
        session_id=session_id,
        entity_id=entity_id,
        brand_profile={"brand_name": "安利中国"},
        fetch_results=fetch_results,
        center_terms=["安利"],
        entity_calibration_result=calibration,
    )


@pytest.mark.asyncio
async def test_association_circle_projection_returns_empty_amway_variant_without_report():
    service = BrandOntologyWorldService(_FakeDb())

    projection = await service._association_circle_projection(  # noqa: SLF001
        entity_id=uuid4(),
        snapshot={"brand": {"label": "安利中国"}},
    )

    assert projection["dashboard_variant"] == "amway_association_circle"
    assert projection["status"] == "not_generated"
    assert projection["center_terms"][:3] == ["安利", "安利中国", "纽崔莱"]
    assert projection["nodes"] == []


@pytest.mark.asyncio
async def test_association_circle_projection_uses_latest_report_payload():
    entity_id = uuid4()
    artifact = _calibrated_artifact(
        session_id="session-1",
        entity_id=str(entity_id),
    )
    service = BrandOntologyWorldService(
        _FakeDb(
            SimpleNamespace(
                payload=artifact,
                report_id="report-1",
                artifact_id="artifact-1",
                updated_at=datetime.now(timezone.utc),
            )
        )
    )

    projection = await service._association_circle_projection(  # noqa: SLF001
        entity_id=entity_id,
        snapshot={"brand": {"label": "安利中国"}},
    )

    assert projection["status"] == "ready"
    assert projection["nodes"]
    assert projection["question_bank"]
    assert projection["platform_comparison"]
    assert projection["association_actions"]
    assert projection["report_narrative_sections"]
    assert projection["question_definition"]
    assert projection["platform_source_summary"]
    assert projection["evidence_findings"]
    assert projection["analysis_tool_trace"]
    assert projection["source_appendix"]
    assert projection["report_quality_checks"]["passed"] is True
    assert projection["generated_from"] == "entity_calibration"
    assert projection["strategy_validation"]
    assert projection["risk_map"]


@pytest.mark.asyncio
async def test_association_circle_projection_upgrades_legacy_report_sections():
    entity_id = uuid4()
    artifact = _calibrated_artifact(
        session_id="session-legacy-report",
        entity_id=str(entity_id),
    )
    legacy_sections = [
        {"section_id": "executive_summary", "title": "Executive Summary｜先给结论"},
        {"section_id": "strategy_validation", "title": "安利战略词逐项验证"},
        {"section_id": "overall_strategy", "title": "综合战略判断"},
        {"section_id": "next_tracking", "title": "下一轮追踪建议"},
    ]
    legacy_payload = deepcopy(artifact)
    legacy_payload["report_narrative_sections"] = legacy_sections
    legacy_payload.pop("strategy_storyline", None)
    legacy_payload["dashboard_projection"][
        "association_circle_projection"
    ]["report_narrative_sections"] = legacy_sections
    legacy_payload["dashboard_projection"][
        "association_circle_projection"
    ].pop("strategy_storyline", None)
    legacy_payload["report_input"].pop("strategy_storyline", None)
    service = BrandOntologyWorldService(
        _FakeDb(
            SimpleNamespace(
                payload=legacy_payload,
                report_id="report-legacy",
                artifact_id="artifact-legacy",
                session_id=uuid4(),
                updated_at=datetime.now(timezone.utc),
            )
        )
    )

    projection = await service._association_circle_projection(  # noqa: SLF001
        entity_id=entity_id,
        snapshot={"brand": {"label": "安利中国"}},
    )

    titles = [section["title"] for section in projection["report_narrative_sections"]]
    assert "核心判断" in titles
    assert "安利的 AI 档案里写了什么" in titles
    assert "四个价值支柱，在 AI 叙事里是什么状态" in titles
    assert "安利的 AI 盲区：不问就不说" in titles
    assert "Executive Summary｜先给结论" not in titles
    assert "安利战略词逐项验证" not in titles
    assert "综合战略判断" not in titles
    assert "下一轮追踪建议" not in titles


@pytest.mark.asyncio
async def test_association_circle_projection_appends_risk_map_nodes_when_clipped():
    entity_id = uuid4()
    fetch_results = amway_association_fetch_results()
    fetch_results.append(
        {
            "question_id": "q_competition_projection",
            "question_text": "安利纽崔莱和汤臣倍健、Swisse相比，用户会怎样选择？",
            "audience_segment": "35-50 初老期",
            "opportunity_point": "体重管理",
            "probe_type": "竞争探针",
            "platform_results": [
                {
                    "platform": "豆包",
                    "success": True,
                    "answer": {
                        "content": (
                            "如果用户只看营养补充，汤臣倍健和Swisse会成为安利纽崔莱的替代选择；"
                            "安利需要用体重管理服务和长期健康方案解释差异。"
                        )
                    },
                }
            ],
        }
    )
    artifact = _calibrated_artifact(
        session_id="session-risk-merge",
        entity_id=str(entity_id),
        fetch_results=fetch_results,
    )
    circle_projection = artifact["dashboard_projection"][
        "association_circle_projection"
    ]
    risk_nodes = circle_projection["risk_map"]["nodes"]
    assert risk_nodes
    clipped_nodes = [
        node for node in circle_projection["nodes"] if not node.get("is_risk_term")
    ][:80]
    circle_projection["nodes"] = clipped_nodes
    artifact["association_circle"]["nodes"] = clipped_nodes
    service = BrandOntologyWorldService(
        _FakeDb(
            SimpleNamespace(
                payload=artifact,
                report_id="report-risk-merge",
                artifact_id="artifact-risk-merge",
                updated_at=datetime.now(timezone.utc),
            )
        )
    )

    projection = await service._association_circle_projection(  # noqa: SLF001
        entity_id=entity_id,
        snapshot={"brand": {"label": "安利中国"}},
    )

    assert any(node.get("is_risk_term") for node in projection["nodes"])
    assert any(
        node.get("business_tag") == "竞争关系" for node in projection["nodes"]
    )


@pytest.mark.asyncio
async def test_association_circle_projection_keeps_node_referenced_evidence():
    entity_id = uuid4()
    artifact = _calibrated_artifact(
        session_id="session-evidence",
        entity_id=str(entity_id),
    )
    target_node = artifact["association_circle"]["nodes"][-1]
    target_ref = "ev_late_node_panel"
    target_node["evidence_samples"] = [target_ref]
    for projection_node in artifact["dashboard_projection"][
        "association_circle_projection"
    ]["nodes"]:
        if projection_node.get("node_id") == target_node["node_id"]:
            projection_node["evidence_samples"] = [target_ref]
            break
    artifact["association_circle"]["evidence_samples"].append(
        {
            "evidence_id": target_ref,
            "node_id": target_node["node_id"],
            "node_term": target_node["term"],
            "platform": "kimi",
            "question_id": "q_late",
            "question": "这个词是否能和安利形成新的品牌联想？",
            "answer_excerpt": "回答里把这个词和安利的长期品牌机会放在一起讨论。",
        }
    )
    artifact["dashboard_projection"]["association_circle_projection"][
        "evidence_samples"
    ] = artifact["association_circle"]["evidence_samples"][:1]
    service = BrandOntologyWorldService(
        _FakeDb(
            SimpleNamespace(
                payload=artifact,
                report_id="report-evidence",
                artifact_id="artifact-evidence",
                updated_at=datetime.now(timezone.utc),
            )
        )
    )

    projection = await service._association_circle_projection(  # noqa: SLF001
        entity_id=entity_id,
        snapshot={"brand": {"label": "安利中国"}},
    )

    returned_refs = {
        item["evidence_id"] for item in projection["evidence_samples"]
    }
    assert target_ref in returned_refs


@pytest.mark.asyncio
async def test_association_circle_projection_keeps_source_appendix_platform_diverse():
    entity_id = uuid4()
    artifact = _calibrated_artifact(
        session_id="session-source-appendix",
        entity_id=str(entity_id),
    )
    source_appendix = [
        {
            "evidence_id": "ev_deepseek_1",
            "question_id": "q_same",
            "question": "安利适合中年人发展事业机会吗？",
            "platform": "DeepSeek",
            "node_term": "监管信息",
            "answer_excerpt": "回答先提到安利，再讨论监管和直销限制。",
        },
        {
            "evidence_id": "ev_deepseek_2",
            "question_id": "q_same",
            "question": "安利适合中年人发展事业机会吗？",
            "platform": "DeepSeek",
            "node_term": "良好关系",
            "answer_excerpt": "回答讨论关系陪伴，也提示现实经营压力。",
        },
        {
            "evidence_id": "ev_kimi_1",
            "question_id": "q_same",
            "question": "安利适合中年人发展事业机会吗？",
            "platform": "Kimi",
            "node_term": "良好关系",
            "answer_excerpt": "回答把社群关系和风险一起说明。",
        },
        {
            "evidence_id": "ev_kimi_2",
            "question_id": "q_kimi_unique",
            "question": "安利的社群关系能不能被 AI 稳定带出？",
            "platform": "Kimi",
            "node_term": "社群陪伴",
            "answer_excerpt": "回答讨论社群陪伴和品牌长期心智之间的关系。",
        },
        {
            "evidence_id": "ev_yuanbao_1",
            "question_id": "q_same",
            "question": "安利适合中年人发展事业机会吗？",
            "platform": "元宝",
            "node_term": "财务保障",
            "answer_excerpt": "回答提到收入机会，也提醒多数人收益不稳定。",
        },
        {
            "evidence_id": "ev_yuanbao_2",
            "question_id": "q_yuanbao_unique",
            "question": "安利的健康方案会不会被带回品牌？",
            "platform": "元宝",
            "node_term": "体重管理",
            "answer_excerpt": "回答讨论健康方案和品牌资产的连接。",
        },
        {
            "evidence_id": "ev_doubao_1",
            "question_id": "q_same",
            "question": "安利适合中年人发展事业机会吗？",
            "platform": "豆包",
            "node_term": "竞品参照",
            "answer_excerpt": "回答将安利和其他营养品牌放在同一选择场景。",
        },
        {
            "evidence_id": "ev_doubao_2",
            "question_id": "q_doubao_unique",
            "question": "安利和营养品牌相比时有哪些风险？",
            "platform": "豆包",
            "node_term": "竞争关系",
            "answer_excerpt": "回答把竞品参照放在用户选择场景里说明。",
        },
    ]
    artifact["source_appendix"] = source_appendix
    artifact["dashboard_projection"]["association_circle_projection"][
        "source_appendix"
    ] = source_appendix
    for node in artifact["dashboard_projection"]["association_circle_projection"][
        "nodes"
    ][:4]:
        node["evidence_samples"] = ["ev_deepseek_1"]
    service = BrandOntologyWorldService(
        _FakeDb(
            SimpleNamespace(
                payload=artifact,
                report_id="report-source-appendix",
                artifact_id="artifact-source-appendix",
                updated_at=datetime.now(timezone.utc),
            )
        )
    )

    projection = await service._association_circle_projection(  # noqa: SLF001
        entity_id=entity_id,
        snapshot={"brand": {"label": "安利中国"}},
    )

    platforms = {
        item["platform"] for item in projection["source_appendix"][:4]
    }
    questions = {
        item["question_id"] for item in projection["source_appendix"][:4]
    }
    assert platforms == {"DeepSeek", "Kimi", "元宝", "豆包"}
    assert len(questions) == 4


@pytest.mark.asyncio
async def test_association_circle_projection_recovers_questions_from_legacy_evidence():
    entity_id = uuid4()
    artifact = _calibrated_artifact(
        session_id="session-legacy",
        entity_id=str(entity_id),
    )
    legacy_artifact = deepcopy(artifact)
    legacy_artifact.pop("question_bank", None)
    legacy_artifact["association_circle"].pop("question_bank", None)
    legacy_artifact["dashboard_projection"]["association_circle_projection"].pop(
        "question_bank",
        None,
    )
    service = BrandOntologyWorldService(
        _FakeDb(
            SimpleNamespace(
                payload=legacy_artifact,
                report_id="report-legacy",
                artifact_id="artifact-legacy",
                updated_at=datetime.now(timezone.utc),
            )
        )
    )

    projection = await service._association_circle_projection(  # noqa: SLF001
        entity_id=entity_id,
        snapshot={"brand": {"label": "安利中国"}},
    )

    assert projection["question_bank"]
    assert projection["question_bank"][0]["source"] == "evidence_sample"


@pytest.mark.asyncio
async def test_association_circle_projection_prefers_durable_question_bank_for_legacy_report():
    entity_id = uuid4()
    session_id = uuid4()
    artifact = _calibrated_artifact(
        session_id=str(session_id),
        entity_id=str(entity_id),
    )
    legacy_artifact = deepcopy(artifact)
    legacy_artifact.pop("question_bank", None)
    legacy_artifact["association_circle"].pop("question_bank", None)
    legacy_artifact["dashboard_projection"]["association_circle_projection"].pop(
        "question_bank",
        None,
    )
    rows = [
        SimpleNamespace(
            question_id=f"q_{index:03d}",
            question_text=f"历史问题 {index}",
            category="上传问题",
            user_intent="",
            decision_stage="",
            source_payload={
                "audience_segment": "35-50 初老期",
                "life_scene": "长期健康管理",
                "opportunity_point": "健康习惯",
                "probe_type": "路径探针",
                "question_set_version": "uploaded_amway_gravity_circle_v1",
            },
            session_id=session_id,
            updated_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
        for index in range(1, 33)
    ]
    service = BrandOntologyWorldService(
        _FakeDb(
            SimpleNamespace(
                payload=legacy_artifact,
                report_id="report-durable",
                artifact_id="artifact-durable",
                updated_at=datetime.now(timezone.utc),
            ),
            question_rows=rows,
        )
    )

    projection = await service._association_circle_projection(  # noqa: SLF001
        entity_id=entity_id,
        snapshot={"brand": {"label": "安利中国"}},
    )

    assert len(projection["question_bank"]) == 32
    assert projection["question_bank"][0]["source"] == "brand_intelligence_question"
    assert projection["question_bank"][0]["audience_segment"]
    assert projection["question_bank"][0]["metadata_status"] == "inferred_needs_review"


@pytest.mark.asyncio
async def test_association_circle_projection_ignores_non_amway_without_report():
    service = BrandOntologyWorldService(_FakeDb())

    projection = await service._association_circle_projection(  # noqa: SLF001
        entity_id=uuid4(),
        snapshot={"brand": {"label": "普通品牌"}},
    )

    assert projection is None


def test_association_actions_merge_into_existing_recommendations():
    projection = _merge_association_actions_into_recommendations(
        {"sample_status": {"status": "ready"}, "recommendations": []},
        [
            {
                "id": "association_translate_node_1",
                "action_label": "需要转译",
                "title": "转译旧认知",
                "node_term": "直销模式",
                "priority": "high",
                "reason": "旧认知贴近中心品牌",
                "expected_impact": "降低旧认知锁定。",
                "execution_steps": ["改写表达"],
                "evidence_refs": ["ev_0001"],
            }
        ],
    )

    recommendation = projection["recommendations"][0]
    assert recommendation["target_metric"] == "brand_association_circle"
    assert recommendation["content_format"] == "圈层行动"
    assert recommendation["evidence_refs"] == ["ev_0001"]
