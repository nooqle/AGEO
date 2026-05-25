from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-secret")

from app.services.brand_ontology_action_planner_service import (
    BrandOntologyActionPlannerService,
)
from app.workflow.orchestrator_context_packets import (
    build_ontology_action_plan_packet,
    render_ontology_action_plan_packet,
)


def _world(*summaries: dict) -> dict:
    return {
        "entity_id": "11111111-1111-1111-1111-111111111111",
        "brand": {
            "object_id": "11111111-1111-1111-1111-111111111111",
            "label": "Specta",
            "lifecycle": "active",
        },
        "object_summaries": [
            _summary("brand_entity", 1, {"active": 1}),
            *summaries,
        ],
        "relationship_counts": {},
        "available_actions": [],
        "warnings": [],
    }


def _summary(
    object_type: str,
    total: int,
    lifecycle_counts: dict[str, int] | None = None,
) -> dict:
    return {
        "object_type": object_type,
        "display_name": object_type,
        "total": total,
        "lifecycle_counts": lifecycle_counts or {},
        "sample_lifecycle_counts": lifecycle_counts or {},
        "samples": [],
    }


def _recommendation_by_key(plan: dict, action_key: str) -> dict:
    recommendations = {item["action_key"]: item for item in plan["recommended_actions"]}
    return recommendations[action_key]


def test_action_plan_recommends_context_and_question_generation_for_brand_only():
    plan = BrandOntologyActionPlannerService().build_plan(
        ontology_world=_world(),
        state={"user_id": "user-1"},
    )

    assert plan is not None
    assert plan["world_phase"] == "brand_ready"
    assert [item["action_key"] for item in plan["recommended_actions"]][:2] == [
        "generate_brand_context",
        "generate_question_set",
    ]
    assert (
        _recommendation_by_key(plan, "generate_question_set")["readiness"]
        == "ready_with_defaults"
    )
    assert any(gap["key"] == "brand_context_missing" for gap in plan["gaps"])
    assert any(gap["key"] == "question_set_missing" for gap in plan["gaps"])


def test_action_plan_blocks_question_confirmation_without_actor_id():
    plan = BrandOntologyActionPlannerService().build_plan(
        ontology_world=_world(
            _summary("competitor_entity", 1, {"confirmed": 1}),
            _summary("simulated_question", 2, {"generated": 2}),
        ),
        state={"secret": "do-not-expose"},
    )

    assert plan is not None
    confirm = _recommendation_by_key(plan, "confirm_question_set")
    assert confirm["readiness"] == "needs_input"
    assert confirm["missing_inputs"] == ["actor_id"]
    assert confirm["requires_confirmation"] is True

    rendered = render_ontology_action_plan_packet(
        build_ontology_action_plan_packet({"ontology_action_plan": plan})
    )
    assert "对象世界计算的行动判断" in rendered
    assert "确认问题组" in rendered
    assert "payload 不完整" in rendered
    assert "do-not-expose" not in rendered


def test_action_plan_recommends_report_after_answer_evidence():
    plan = BrandOntologyActionPlannerService().build_plan(
        ontology_world=_world(
            _summary("competitor_entity", 1, {"confirmed": 1}),
            _summary("simulated_question", 1, {"fetched": 1}),
            _summary("platform_answer", 1, {"captured": 1}),
            _summary("evidence_set", 1, {"attached_to_report": 1}),
        ),
        state={"user_id": "user-1"},
    )

    assert plan is not None
    assert plan["world_phase"] == "evidence_ready"
    report = _recommendation_by_key(plan, "generate_report")
    assert report["readiness"] == "ready_with_defaults"
    assert report["defaulted_inputs"] == [
        {"input_key": "report_kind", "source": "orchestrator_policy"}
    ]


def test_action_plan_blocks_answer_fetch_until_questions_are_confirmed():
    plan = BrandOntologyActionPlannerService().build_plan(
        ontology_world=_world(
            _summary("competitor_entity", 1, {"confirmed": 1}),
            _summary("simulated_question", 2, {"generated": 2}),
        ),
        state={"user_id": "user-1"},
    )

    assert plan is not None
    readiness = {item["action_key"]: item for item in plan["action_readiness"]}
    assert readiness["run_answer_fetch"]["readiness"] == "blocked"
    assert readiness["run_answer_fetch"]["missing_objects"] == [
        {
            "object_type": "simulated_question",
            "required_status": "confirmed",
        }
    ]


def test_action_plan_requires_human_confirmation_for_monitoring_plan():
    plan = BrandOntologyActionPlannerService().build_plan(
        ontology_world=_world(
            _summary("competitor_entity", 1, {"confirmed": 1}),
            _summary("simulated_question", 1, {"fetched": 1}),
            _summary("platform_answer", 1, {"captured": 1}),
            _summary("report_artifact", 1, {"published": 1}),
        ),
        state={"user_id": "user-1", "cadence": "weekly"},
    )

    assert plan is not None
    monitoring = _recommendation_by_key(plan, "create_monitoring_plan")
    assert monitoring["readiness"] == "needs_confirmation"
    assert monitoring["requires_confirmation"] is True
    assert [item["action_key"] for item in plan["needs_human_confirmation"]] == [
        "create_monitoring_plan"
    ]


def test_action_plan_turns_weak_official_website_asset_into_confirmation_action():
    world = _world(
        _summary("competitor_entity", 1, {"confirmed": 1}),
        _summary("simulated_question", 1, {"fetched": 1}),
        _summary("platform_answer", 3, {"captured": 3}),
        _summary("report_artifact", 1, {"published": 1}),
        _summary("monitoring_plan", 1, {"active": 1}),
        _summary("official_website_asset", 1, {"not_cited": 1}),
    )
    world["official_website_observation"] = {
        "status": "not_cited",
        "domain": "li.auto",
        "citation_count": 0,
        "value_score": 0,
        "gaps": ["官网没有进入引用链"],
        "content_audit": {
            "status": "partially_readable",
            "value_score": 58,
            "gaps": ["缺少页面描述"],
        },
    }

    plan = BrandOntologyActionPlannerService().build_plan(
        ontology_world=world,
        state={"user_id": "user-1"},
    )

    assert plan is not None
    action = _recommendation_by_key(plan, "generate_official_website_evidence_plan")
    assert action["source"] == "official_website_asset"
    assert action["target_object_type"] == "official_website_asset"
    assert action["target_object_id"] == "li.auto"
    assert action["readiness"] == "needs_confirmation"
    assert action["requires_confirmation"] is True
    assert action["defaulted_inputs"] == [
        {
            "input_key": "improvement_scope",
            "source": "official_website_evidence_policy",
        }
    ]
    assert "official_domain" in plan["available_inputs"]
    assert any(gap["key"] == "official_website_citation_gap" for gap in plan["gaps"])
    assert any(gap["key"] == "official_website_content_gap" for gap in plan["gaps"])

    rendered = render_ontology_action_plan_packet(
        build_ontology_action_plan_packet({"ontology_action_plan": plan})
    )
    assert "生成官网证据页优化建议" in rendered
    assert "来源=官网资产观测" in rendered
    assert "需人确认" in rendered


def test_action_plan_models_monitoring_plan_lifecycle_changes_as_controlled_action():
    plan = BrandOntologyActionPlannerService().build_plan(
        ontology_world=_world(
            _summary("competitor_entity", 1, {"confirmed": 1}),
            _summary("simulated_question", 1, {"fetched": 1}),
            _summary("platform_answer", 1, {"captured": 1}),
            _summary("report_artifact", 1, {"published": 1}),
            _summary("monitoring_plan", 1, {"paused": 1}),
        ),
        state={"actor_id": "user-1"},
    )

    assert plan is not None
    readiness = {item["action_key"]: item for item in plan["action_readiness"]}
    update_plan = readiness["update_monitoring_plan"]
    assert update_plan["readiness"] == "needs_input"
    assert update_plan["missing_inputs"] == ["change_type"]
    recommended_update = _recommendation_by_key(plan, "update_monitoring_plan")
    assert recommended_update["readiness"] == "needs_input"
    assert recommended_update["missing_inputs"] == ["change_type"]

    plan_with_change = BrandOntologyActionPlannerService().build_plan(
        ontology_world=_world(
            _summary("competitor_entity", 1, {"confirmed": 1}),
            _summary("simulated_question", 1, {"fetched": 1}),
            _summary("platform_answer", 1, {"captured": 1}),
            _summary("report_artifact", 1, {"published": 1}),
            _summary("monitoring_plan", 1, {"paused": 1}),
        ),
        state={"actor_id": "user-1", "change_type": "activate"},
    )

    readiness_with_change = {
        item["action_key"]: item for item in plan_with_change["action_readiness"]
    }
    assert readiness_with_change["update_monitoring_plan"]["readiness"] == (
        "needs_confirmation"
    )


def test_action_plan_turns_incomplete_finding_correction_into_input_request():
    world = _world(
        _summary("competitor_entity", 1, {"confirmed": 1}),
        _summary("simulated_question", 1, {"fetched": 1}),
        _summary("platform_answer", 1, {"captured": 1}),
        _summary("evidence_set", 1, {"attached_to_report": 1}),
        _summary("report_artifact", 1, {"published": 1}),
        _summary("intelligence_finding", 1, {"observed": 1}),
    )
    world["finding_feedback_summary"] = {
        "total": 1,
        "correction_count": 1,
        "correction_without_text_count": 1,
        "latest": [
            {
                "finding_id": "finding-1",
                "feedback_type": "correct",
                "has_feedback_text": False,
            }
        ],
    }

    plan = BrandOntologyActionPlannerService().build_plan(
        ontology_world=world,
        state={"user_id": "user-1"},
    )

    assert plan is not None
    feedback = _recommendation_by_key(plan, "record_user_feedback")
    assert feedback["source"] == "finding_feedback"
    assert feedback["readiness"] == "needs_input"
    assert feedback["missing_inputs"] == ["feedback_text"]
    assert feedback["target_object_type"] == "intelligence_finding"
    assert feedback["target_object_id"] == "finding-1"
    assert feedback["feedback_type"] == "correct"

    rendered = render_ontology_action_plan_packet(
        build_ontology_action_plan_packet({"ontology_action_plan": plan})
    )
    assert "来源=情报判断反馈" in rendered
    assert "缺输入=feedback_text" in rendered


def test_action_plan_blocks_recommendations_when_governance_is_blocked():
    world = _world(
        _summary("competitor_entity", 1, {"confirmed": 1}),
        _summary("simulated_question", 1, {"fetched": 1}),
    )
    world["governance_report"] = {"status": "blocked", "checks": []}

    plan = BrandOntologyActionPlannerService().build_plan(
        ontology_world=world,
        state={"user_id": "user-1"},
    )

    assert plan is not None
    assert plan["governance_status"] == "blocked"
    assert plan["recommended_actions"] == []
    assert plan["gaps"][0]["key"] == "ontology_governance_blocked"
    assert "ontology_governance_status_must_be_respected" in plan["guardrails"]

    rendered = render_ontology_action_plan_packet(
        build_ontology_action_plan_packet({"ontology_action_plan": plan})
    )
    assert "当前治理状态：blocked" in rendered
    assert "对象世界治理降级或阻断时不得绕过治理状态执行" in rendered
