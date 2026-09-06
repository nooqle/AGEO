"""Minimal synthetic regressions; no controlled tender text is included."""
import hashlib
import json

import pytest

from app.ontology import AmwayEntityDefinition, AmwayEntityOntologyRegistry, load_default_amway_entity_ontology
from app.services.amway_entity_extraction_service import AmwayEntityExtractionService
from app.services.amway_entity_calibration_service import AmwayEntityCalibrationService
from app.services.amway_topic_projection import project_topic_signals
from app.services.amway_lexicon_repair_service import prepare_repair


SOURCE = {"source_id": "synthetic", "locator": "fixture", "quote": "reviewed sample"}


def semantic(kind="material", role="object", **kwargs):
    return {"semantic_type": kind, "graph_role": role, "identity_scope": "global",
            "match_policy": "exact", "source_refs": [SOURCE], **kwargs}


def entry(entity_id, name, **kwargs):
    return AmwayEntityDefinition.model_validate({
        "entity_id": entity_id, "canonical_name": name, "entity_type": "Object",
        "graph_policy": {"main_orbit": "not_allowed", "risk_view": "not_allowed", "target_gap_view": "not_allowed"},
        "source_policy": {"source_kind": "fixture", "source_document_section": "synthetic"},
        "semantic_definition": semantic(), **kwargs,
    })


def registry(*entries):
    base = load_default_amway_entity_ontology()
    return AmwayEntityOntologyRegistry(base.definition.model_copy(update={"entities": base.entities + tuple(entries)}))


def extract(reg, text):
    return AmwayEntityExtractionService(reg).extract_from_fetch_results([
        {"question_id": "q1", "question": "安利", "platform_results": [{"platform": "Kimi", "answer_text": text}]}
    ])


@pytest.mark.parametrize("status", ["pending_review", "rejected", "merged"])
def test_review_status_gates_canonical_and_alias(status):
    reg = registry(entry("sample", "Example Material", aliases=["Sample Alias"], review_status=status))
    assert not any(s["entity_id"] == "sample" for s in extract(reg, "Example Material Sample Alias")["signals"])


def test_related_cue_does_not_identify_object():
    reg = registry(entry("tool", "Specific App", semantic_definition=semantic("tool"), related_terms=["mobile app"]))
    assert not any(s["entity_id"] == "tool" for s in extract(reg, "A mobile app helps.")["signals"])
    assert any(s["entity_id"] == "tool" for s in extract(reg, "Specific App helps.")["signals"])


def test_direct_selling_matches_after_explicit_approval():
    base = load_default_amway_entity_ontology()
    reg = AmwayEntityOntologyRegistry(base.definition.model_copy(update={"entities": tuple(
        e.model_copy(update={"review_status": "approved"}) if e.entity_id == "business_direct_selling" else e
        for e in base.entities
    )}))
    assert any(s["entity_id"] == "business_direct_selling" for s in extract(reg, "安利采用直销模式")["signals"])


@pytest.mark.parametrize("text, expected", [
    ("安利采用直销模式。", "neutral"),
    ("安利通过合法合规的直销模式提供产品咨询和服务。", "neutral"),
    ("安利直销模式中的发展下线和熟人压力值得警惕。", "negative"),
    ("安利直销模式中出现强推产品的行为。", "negative"),
    ("安利直销模式可能涉及非法传销风险，应核查。", "negative"),
])
def test_direct_selling_polarity_depends_on_actual_context(text, expected):
    base = load_default_amway_entity_ontology()
    reg = AmwayEntityOntologyRegistry(base.definition.model_copy(update={"entities": tuple(
        e.model_copy(update={"review_status": "approved"}) if e.entity_id == "business_direct_selling" else e
        for e in base.entities
    )}))
    signal = next(s for s in extract(reg, text)["signals"] if s["entity_id"] == "business_direct_selling")
    assert signal["context_polarity"] == expected


def test_contextual_identity_requires_nearby_qualifier():
    reg = registry(entry("tool", "Sample Assistant", aliases=["nutritionist"], semantic_definition=semantic(
        "tool", identity_scope="sample-vendor", match_policy="contextual", context_terms=["Sample Vendor"])))
    assert not any(s["entity_id"] == "tool" for s in extract(reg, "Sample Vendor " + "x" * 150 + " nutritionist")["signals"])
    assert any(s["entity_id"] == "tool" for s in extract(reg, "Sample Vendor nutritionist")["signals"])


def test_ambiguous_same_surface_does_not_choose_identity():
    reg = registry(entry("one", "Shared Label"), entry("two", "Shared Label"))
    assert not {"one", "two"}.intersection(s["entity_id"] for s in extract(reg, "Shared Label")["signals"])


def topic_fixture():
    topic = entry("topic_sample", "Herbal Theme", entity_type="ProductCategory",
                  graph_policy={"main_orbit": "allowed_with_answer_evidence", "risk_view": "not_allowed", "target_gap_view": "allowed"},
                  semantic_definition=semantic("topic", "topic"))
    mapping = {"target_entity_id": topic.entity_id, "review_status": "approved", "source_refs": [SOURCE]}
    return registry(topic, entry("material_a", "Material Alpha", semantic_definition=semantic(topic_mappings=[mapping])),
                    entry("material_b", "Material Beta", semantic_definition=semantic(topic_mappings=[mapping])))


def test_two_objects_and_direct_theme_count_once_with_complete_drilldown():
    reg = topic_fixture()
    result = extract(reg, "Herbal Theme Material Alpha Material Beta")
    projected = project_topic_signals(result["signals"], reg)
    topic = next(s for s in projected if s["entity_id"] == "topic_sample")
    assert len(topic["topic_contributions"]) == 3
    calibration = AmwayEntityCalibrationService(reg)
    accumulator = calibration._build_accumulators(projected)["topic_sample"]
    assert len(accumulator.answer_ids) == 1
    assert sum(accumulator.platforms.values()) == 1
    assert sum(accumulator.answer_positions.values()) == 1
    assert sum(accumulator.relation_types.values()) == 1
    assert len(accumulator.signals) == 1
    assert {s["entity_id"] for s in result["signals"]} >= {"material_a", "material_b"}


def test_snapshot_freezes_overlay_and_tampering_is_rejected():
    reg = topic_fixture()
    result = extract(reg, "Material Alpha")
    restored = AmwayEntityOntologyRegistry.from_snapshot(result["effective_lexicon_snapshot"])
    assert restored.effective_hash == reg.effective_hash == result["effective_lexicon_hash"]
    extraction = AmwayEntityExtractionService(restored)
    assert AmwayEntityCalibrationService(extraction_service=extraction).registry is restored
    result["effective_lexicon_hash"] = "tampered"
    with pytest.raises(ValueError, match="hash mismatch"):
        AmwayEntityCalibrationService(restored).calibrate(fetch_results=[], extraction_result=result)


def test_schema_rejects_unsourced_relations_and_unresolved_matching():
    with pytest.raises(ValueError):
        entry("bad", "Unknown", semantic_definition=semantic("unresolved"))
    with pytest.raises(ValueError):
        entry("bad", "Bad Relation", semantic_definition=semantic(relations=[{
            "target_entity_id": "other", "relation_type": "supports", "source_refs": []}]))


def test_effective_hash_is_entity_order_independent():
    reg = topic_fixture()
    reverse = AmwayEntityOntologyRegistry(reg.definition.model_copy(update={"entities": tuple(reversed(reg.entities))}))
    assert reg.effective_hash == reverse.effective_hash


def repair_fixture():
    base = load_default_amway_entity_ontology()
    extra = [entry(f"old_{i}", f"Old Object {i}") for i in range(128 - len(base.entities))]
    reg = registry(*extra)
    manifest = [{"source_record_id": str(i), "original_name": f"Source {i}", "source_refs": [SOURCE]} for i in range(71)]
    record = entry("new_identity", "New Identity").model_dump(mode="json")
    package = {
        "repair_id": "synthetic", "expected_effective_hash": reg.effective_hash,
        "preserve_entity_ids": [e.entity_id for e in reg.entities], "records": [record],
        "source_manifest": manifest,
        "source_manifest_hash": hashlib.sha256(json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "article_crosswalk": [{"source_record_id": str(i), "entity_id": "new_identity", "decision": "reuse", "reason": "reviewed"} for i in range(71)],
    }
    return reg, package


def test_repair_preserves_ids_is_idempotent_and_rejects_stale_hash():
    reg, package = repair_fixture()
    effective, changed = prepare_repair(reg, package)
    assert len(changed) == 1
    assert {e.entity_id for e in reg.entities}.issubset(e.entity_id for e in effective.entities)
    assert prepare_repair(effective, package)[1] == []
    package["expected_effective_hash"] = "stale"
    with pytest.raises(ValueError, match="changed"):
        prepare_repair(reg, package)


def test_crosswalk_cannot_replace_one_manifest_id_with_another():
    reg, package = repair_fixture()
    package["article_crosswalk"][0]["source_record_id"] = "unexpected"
    with pytest.raises(ValueError, match="manifest"):
        prepare_repair(reg, package)


def test_manifest_hash_binds_raw_quotes_but_reference_comparison_normalizes_whitespace():
    reg, package = repair_fixture()
    package["source_manifest"][0]["source_refs"] = [{**SOURCE, "quote": SOURCE["quote"] + " "}]
    package["source_manifest_hash"] = hashlib.sha256(json.dumps(
        package["source_manifest"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    assert len(prepare_repair(reg, package)[1]) == 1


def test_mapped_only_topic_is_labeled_and_counts_answer_union():
    from app.services.amway_topic_projection import topic_support_summary
    reg = topic_fixture()
    units = project_topic_signals(extract(reg, "Material Alpha Material Beta")["signals"], reg)
    unit = next(row for row in units if row["entity_id"] == "topic_sample")
    summary = topic_support_summary(unit["topic_contributions"])
    assert summary == {"contribution_mode": "mapped", "contribution_label": "由对象归组",
                       "direct_answer_count": 0, "mapped_answer_count": 1,
                       "overlap_answer_count": 0, "supporting_answer_count": 1}
    direct = {**unit["topic_contributions"][0], "contribution_kind": "direct"}
    mixed = topic_support_summary([*unit["topic_contributions"], direct])
    assert mixed["contribution_mode"] == "mixed"
    assert mixed["overlap_answer_count"] == mixed["supporting_answer_count"] == 1


def test_mixed_versions_have_no_combined_topic_nodes():
    from types import SimpleNamespace
    from app.services.amway_circle_tracking_service import _aggregate_projection, _change_top5
    old = {"nodes": [{"node_id": "x", "answer_count": 3}]}
    new = {"nodes": [{"node_id": "x", "answer_count": 4}], "effective_lexicon_hash": "new", "extraction_version": "semantic-v2"}
    result = _aggregate_projection([
        SimpleNamespace(circle_run_id="old", association_circle_projection=old),
        SimpleNamespace(circle_run_id="new", association_circle_projection=new),
    ], None)
    assert result["status"] == "incompatible_versions"
    assert result["nodes"] == []
    assert _change_top5(old, new) == []


@pytest.mark.parametrize("short,long", [
    ("植物营养", "植物营养素"), ("淫羊藿", "淫羊藿苷"),
    ("中国营养学会", "中国营养学会科学技术奖"),
])
def test_long_object_span_suppresses_embedded_short_identity_but_not_separate_mention(short, long):
    # Isolate the two reviewed identities from bundled aliases.
    base = load_default_amway_entity_ontology()
    reg = AmwayEntityOntologyRegistry(base.definition.model_copy(update={"entities": (
        entry("short", short), entry("long", long),
    )}))
    only_long = extract(reg, long)["signals"]
    assert {row["entity_id"] for row in only_long} == {"long"}
    assert only_long[0]["match_span"] == {"start": 0, "end": len(long)}
    separate = extract(reg, f"{long}；另提到{short}。")["signals"]
    assert {row["entity_id"] for row in separate} == {"short", "long"}
    short_signal = next(row for row in separate if row["entity_id"] == "short")
    assert short_signal["match_span"]["start"] > len(long)


def test_nested_brand_in_product_name_is_not_a_direct_brand_mention():
    base = load_default_amway_entity_ontology()
    reg = AmwayEntityOntologyRegistry(base.definition.model_copy(update={"entities": (
        entry("brand", "样例品牌", entity_type="SubBrand", semantic_definition=semantic("brand", "anchor")),
        entry("product", "样例品牌营养片", semantic_definition=semantic("product")),
    )}))
    assert {row["entity_id"] for row in extract(reg, "样例品牌营养片")["signals"]} == {"product"}
    assert {row["entity_id"] for row in extract(reg, "样例品牌提供样例品牌营养片")["signals"]} == {"brand", "product"}


def test_long_object_maps_to_topic_without_fabricating_direct_topic_mention():
    base = load_default_amway_entity_ontology()
    mapping = {"target_entity_id": "topic", "review_status": "approved", "source_refs": [SOURCE]}
    reg = AmwayEntityOntologyRegistry(base.definition.model_copy(update={"entities": (
        entry("topic", "植物营养", entity_type="ProductCategory", semantic_definition=semantic("topic", "topic")),
        entry("compound", "植物营养素", semantic_definition=semantic("concept", topic_mappings=[mapping])),
    )}))
    signals = extract(reg, "植物营养素")["signals"]
    assert {row["entity_id"] for row in signals} == {"compound"}
    unit = project_topic_signals(signals, reg)[0]
    assert unit["entity_id"] == "topic"
    assert [item["contribution_kind"] for item in unit["topic_contributions"]] == ["mapped"]
