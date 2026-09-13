"""Project independent identity evidence into answer-deduplicated topic units."""
from collections import defaultdict
from typing import Any

from app.ontology import AmwayEntityOntologyRegistry
from app.services.amway_topic_coverage import TopicCoverageRecorder


def topic_support_summary(contributions: list[dict]) -> dict:
    direct = {str(item["answer_id"]) for item in contributions
              if item.get("answer_id") and item.get("contribution_kind") == "direct"}
    mapped = {str(item["answer_id"]) for item in contributions
              if item.get("answer_id") and item.get("contribution_kind") == "mapped"}
    mode = "mixed" if direct and mapped else "mapped" if mapped else "direct"
    return {
        "contribution_mode": mode,
        "contribution_label": {"mapped": "由对象归组", "direct": "直接提及", "mixed": "直接提及与对象归组"}[mode],
        "direct_answer_count": len(direct), "mapped_answer_count": len(mapped),
        "overlap_answer_count": len(direct & mapped),
        "supporting_answer_count": len(direct | mapped),
    }


def project_topic_signals(
    signals: list[dict], registry: AmwayEntityOntologyRegistry, *,
    excluded_relation_types: set[str] | frozenset[str] = frozenset(),
    coverage: TopicCoverageRecorder | None = None,
) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for signal in signals:
        entity = registry.get_entity(str(signal.get("entity_id") or ""))
        if entity is None or entity.review_status != "approved":
            continue
        semantic = entity.semantic_definition
        if semantic and semantic.match_policy == "disabled":
            continue
        targets = []
        if semantic is None or semantic.graph_role in {"topic", "anchor"}:
            targets.append((entity, None))
        if semantic:
            for mapping in semantic.topic_mappings:
                target = registry.require_entity(mapping.target_entity_id)
                if mapping.review_status == "approved" and target.review_status == "approved":
                    targets.append((target, mapping))
                elif coverage:
                    coverage.record(target.entity_id, "mapping_excluded", signal)
        for target, mapping in targets:
            if target.semantic_definition and target.semantic_definition.match_policy == "disabled":
                if coverage:
                    coverage.record(target.entity_id, "matching_disabled", signal)
                continue
            relation = str(signal.get("relation_type") or "")
            if relation in excluded_relation_types:
                if coverage:
                    coverage.record(target.entity_id, relation.lower(), signal)
                continue
            if coverage:
                coverage.record(target.entity_id, "accepted", signal)
            contribution = {
                "entity_id": entity.entity_id, "entity_name": entity.canonical_name,
                "semantic_type": semantic.semantic_type if semantic else None,
                "identity_scope": semantic.identity_scope if semantic else None,
                "contribution_kind": "mapped" if mapping else "direct",
                "mapping_sources": mapping.model_dump(mode="json")["source_refs"] if mapping else [],
                "object_relations": semantic.model_dump(mode="json")["relations"] if semantic else [],
                "source_refs": semantic.model_dump(mode="json")["source_refs"] if semantic else [],
                "signal_id": signal.get("signal_id"), "answer_id": signal.get("answer_id"),
                "platform": signal.get("platform"), "question_id": signal.get("question_id"),
                "matched_text": signal.get("matched_text"), "evidence_text": signal.get("evidence_text"),
            }
            projected = {
                **signal, "entity_id": target.entity_id, "entity_name": target.canonical_name,
                "entity_type": target.entity_type, "contribution": contribution,
            }
            groups[(str(signal.get("answer_id") or ""), target.entity_id)].append(projected)
    return [_merge_unit(key, values) for key, values in sorted(groups.items())]


def _merge_unit(key: tuple[str, str], values: list[dict]) -> dict[str, Any]:
    # Direct mention wins ties; otherwise stable identity order. Preserve every
    # contributor separately so deduplication never discards the audit trail.
    values.sort(key=lambda row: (
        row["contribution"]["contribution_kind"] != "direct",
        str(row["contribution"]["entity_id"]), str(row.get("signal_id")),
    ))
    selected = dict(values[0])
    selected.pop("contribution", None)
    selected["signal_id"] = f"topic_{key[0]}_{key[1]}"
    selected["topic_contributions"] = [row["contribution"] for row in values]
    selected["match_source"] = "direct" if any(
        row["contribution"]["contribution_kind"] == "direct" for row in values
    ) else "topic_mapping"
    # Conflicting object stances are explicitly neutral at the topic unit.
    polarities = {row.get("context_polarity") for row in values}
    if len(polarities) > 1:
        selected["context_polarity"] = "neutral"
        selected["topic_stance_conflict"] = True
    return selected
