from app.ontology import load_default_amway_entity_ontology


def test_amway_entity_ontology_loads_and_indexes_core_entities():
    registry = load_default_amway_entity_ontology()

    assert registry.definition.ontology_id == "amway_entity_ontology"
    assert registry.definition.center_brand_policy.default_center_brand == "安利"

    weight_management = registry.find_entity_by_name_or_alias("控重")
    assert weight_management is not None
    assert weight_management.canonical_name == "体重管理"
    assert weight_management.entity_type == "Solution"

    nutrition_breakfast = registry.require_entity("solution_nutrition_breakfast")
    assert nutrition_breakfast.canonical_name == "营养早餐"
    assert nutrition_breakfast.graph_policy.main_orbit == "allowed_with_answer_evidence"


def test_amway_entity_ontology_keeps_risk_labels_out_of_main_orbit():
    registry = load_default_amway_entity_ontology()

    risk_entities = registry.entities_by_type("RiskLabel")
    assert risk_entities
    assert all(
        entity.graph_policy.main_orbit == "not_allowed" for entity in risk_entities
    )
    assert all(
        entity.graph_policy.risk_view == "aggregate_only" for entity in risk_entities
    )


def test_amway_entity_ontology_merges_cloud_shop_duplicate_source_rows():
    registry = load_default_amway_entity_ontology()

    cloud_shop_entities = [
        entity for entity in registry.entities if entity.canonical_name == "安利云购"
    ]
    assert len(cloud_shop_entities) == 1
    assert "社交电商" in cloud_shop_entities[0].aliases
    assert "移动销售" in cloud_shop_entities[0].aliases


def test_amway_entity_ontology_preserves_review_boundaries():
    registry = load_default_amway_entity_ontology()

    active_health = registry.find_entity_by_name_or_alias("主动健康")
    assert active_health is not None
    assert active_health.entity_type == "BrandStrategy"
    assert active_health.review_status == "pending_review"

    direct_selling = registry.require_entity("business_direct_selling")
    assert direct_selling.review_status == "pending_review"
    assert direct_selling.graph_policy.risk_view == "not_allowed"
