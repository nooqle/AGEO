from __future__ import annotations

import json

import pytest

from app.ontology import OntologyRegistry, OntologyRegistryError, load_default_ontology


def test_default_ontology_loads_core_ai_brand_intelligence_model():
    registry = load_default_ontology()

    assert registry.definition.domain == "AI brand intelligence"
    assert registry.require_object_type("brand_entity").display_name == "品牌"
    assert registry.require_object_type("official_website_asset").display_name == (
        "官网资产"
    )
    assert registry.require_object_type("platform_answer").display_name == "AI 平台回答"
    assert registry.require_object_type("source_domain").display_name == "来源域名"
    assert registry.require_object_type("evidence_cluster").display_name == "证据簇"
    assert registry.require_object_type("action_record").display_name == "动作记录"
    assert registry.require_link_type("question_answered_by").from_object == (
        "simulated_question"
    )
    assert registry.require_action_type("generate_report").target_objects == (
        "brand_entity",
        "evidence_set",
        "report_artifact",
        "metric_snapshot",
        "intelligence_finding",
    )
    official_plan_action = registry.require_action_type(
        "generate_official_website_evidence_plan"
    )
    assert official_plan_action.required_inputs == (
        "brand_entity_id",
        "official_domain",
        "improvement_scope",
    )
    assert official_plan_action.requires_confirmation is True
    assert registry.require_action_type("record_user_feedback").writes == (
        "user_decision",
        "intelligence_finding.lifecycle",
    )
    assert registry.require_action_type("update_monitoring_plan").required_inputs == (
        "brand_entity_id",
        "monitoring_plan_id",
        "change_type",
        "actor_id",
    )
    assert registry.require_action_type("generate_brand_context").writes == (
        "competitor_entity",
    )
    assert registry.require_action_type("generate_persona_map").writes == (
        "audience_persona",
        "usage_scenario",
    )
    assert registry.require_link_type("question_set_contains_question").from_object == (
        "question_set"
    )
    assert registry.require_object_view("brand_intelligence_home").object_type == (
        "brand_entity"
    )
    assert "official_website_asset" in registry.require_object_view(
        "brand_intelligence_home"
    ).sections
    assert "official_website_observation" in registry.require_object_view(
        "brand_intelligence_home"
    ).sections
    assert "generate_official_website_evidence_plan" in registry.require_object_view(
        "brand_intelligence_home"
    ).actions
    assert registry.require_function("observe_official_website_asset").outputs == (
        "official_website_asset",
        "official_website_observation",
    )
    assert "generate_official_website_evidence_plan" in registry.require_function(
        "observe_official_website_asset"
    ).used_by_actions
    assert registry.require_function("audit_official_website_content").outputs == (
        "official_website_asset",
        "official_website_content_audit",
    )
    assert registry.require_function("cluster_citation_evidence").outputs == (
        "source_domain_summary",
        "evidence_cluster",
    )


def test_default_ontology_declares_traceable_report_evidence_chain():
    registry = load_default_ontology()

    link_keys = {link.key for link in registry.link_types}
    assert {
        "question_answered_by",
        "platform_answer_cites_source",
        "evidence_set_contains_answer",
        "report_uses_evidence_set",
        "brand_has_intelligence_finding",
        "report_contains_intelligence_finding",
        "intelligence_finding_uses_evidence_set",
        "question_set_contains_question",
        "monitoring_plan_uses_question_set",
        "action_record_handles_monitoring_plan",
    }.issubset(link_keys)

    report_action = registry.require_action_type("generate_report")
    assert "report_uses_evidence_set" in report_action.creates_links
    assert "intelligence_finding" in report_action.writes
    assert "emit_report_artifact" in report_action.side_effects


def test_registry_validates_object_lifecycle_status():
    registry = load_default_ontology()

    assert registry.require_lifecycle_status("simulated_question", "fetched") == (
        "fetched"
    )

    with pytest.raises(OntologyRegistryError, match="stale"):
        registry.require_lifecycle_status("simulated_question", "stale")


def test_registry_rejects_unknown_link_reference(tmp_path):
    payload = {
        "version": "test",
        "domain": "test",
        "purpose": "test",
        "object_types": [
            {
                "key": "brand_entity",
                "display_name": "Brand",
                "description": "Brand",
            }
        ],
        "link_types": [
            {
                "key": "bad_link",
                "display_name": "Bad link",
                "description": "Bad link",
                "from_object": "brand_entity",
                "to_object": "missing_object",
                "cardinality": "one_to_many",
            }
        ],
        "action_types": [],
        "functions": [],
        "object_views": [],
    }
    path = tmp_path / "ontology.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(OntologyRegistryError, match="missing_object"):
        OntologyRegistry.from_path(path)
