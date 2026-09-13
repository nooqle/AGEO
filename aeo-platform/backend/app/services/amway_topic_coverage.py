"""Bounded diagnostics emitted by the real matching and calibration stages."""

from collections import Counter, defaultdict
from copy import deepcopy
from typing import Any

from app.ontology import AmwayEntityDefinition, AmwayEntityOntologyRegistry


TOPIC_ANALYSIS_VERSION = "2026-09-13-topic-coverage-v1"
MAX_EVIDENCE_SAMPLES = 3
MAX_EXCERPT_LENGTH = 360


def extraction_eligibility_reason(
    entity: AmwayEntityDefinition,
    registry: AmwayEntityOntologyRegistry,
    source_side: str = "answer",
) -> str | None:
    """The same gate is used for extraction candidates and coverage explanation."""
    if entity.review_status != "approved":
        return "review_excluded"
    if entity.semantic_definition and entity.semantic_definition.match_policy == "disabled":
        return "matching_disabled"
    entity_type = registry.get_entity_type(entity.entity_type)
    if entity_type is None or source_side not in entity_type.extractable_from:
        return "type_excluded"
    return None


class TopicCoverageRecorder:
    """Observe decisions; never independently score or infer semantic matches."""

    def __init__(self, registry: AmwayEntityOntologyRegistry) -> None:
        self.registry = registry
        self.topics = {
            entity.entity_id: entity for entity in registry.entities
            if entity.semantic_definition and entity.semantic_definition.graph_role == "topic"
        }
        self.events: dict[str, Counter[str]] = defaultdict(Counter)
        self.evidence: dict[str, list[dict[str, str]]] = defaultdict(list)
        self.decisions: dict[str, dict[str, Any]] = {}

    def record(self, entity_id: str, reason: str, signal: dict[str, Any]) -> None:
        if entity_id not in self.topics:
            return
        self.events[entity_id][reason] += 1
        samples = self.evidence[entity_id]
        answer_id = str(signal.get("answer_id") or "")
        if any(
            sample["answer_id"] == answer_id and sample["reason"] == reason for sample in samples
        ):
            return
        if len(samples) >= MAX_EVIDENCE_SAMPLES:
            # Included topics must have a supporting sample even if filtered
            # matches occurred first in the collection order.
            rejected = next((i for i, sample in enumerate(samples) if sample["reason"] != "accepted"), None)
            if reason != "accepted" or rejected is None:
                return
            samples.pop(rejected)
        samples.append({
            key: str(signal.get(key) or "")[:MAX_EXCERPT_LENGTH]
            for key in ("answer_id", "question_id", "platform", "question", "evidence_text")
        } | {"reason": reason})

    def decide(self, entity_id: str, reason: str, score: int | None = None) -> None:
        self.decisions[entity_id] = {"reason": reason}
        if score is not None:
            self.decisions[entity_id]["score"] = score

    def finish(self, nodes: list[dict], signals: list[dict]) -> dict[str, Any]:
        nodes_by_id = {node["entity_id"]: node for node in nodes}
        signal_counts = Counter(signal["entity_id"] for signal in signals)
        answer_refs: dict[str, set[str]] = defaultdict(set)
        for signal in signals:
            if signal.get("answer_id"):
                answer_refs[signal["entity_id"]].add(str(signal["answer_id"]))
        rows = [self._row(entity, nodes_by_id.get(entity_id), signal_counts[entity_id],
                          len(answer_refs[entity_id]))
                for entity_id, entity in sorted(self.topics.items())]
        anchor_ids = sorted(
            entity.entity_id
            for node in nodes if (entity := self.registry.get_entity(node["entity_id"]))
            if entity.semantic_definition and entity.semantic_definition.graph_role == "anchor"
        )
        included_count = sum(row["status"] == "included" for row in rows)
        return {
            "schema_version": 1, "scope": "run", "analysis_version": TOPIC_ANALYSIS_VERSION,
            "lexicon_hash": self.registry.effective_hash,
            "total_topic_count": len(rows), "included_topic_count": included_count,
            "anchor_node_count": len(anchor_ids), "anchor_entity_ids": anchor_ids,
            "other_node_count": len(nodes) - included_count - len(anchor_ids),
            "status_counts": dict(Counter(row["status"] for row in rows)), "topics": rows,
        }

    def _row(self, entity, node, signal_count: int, answer_count: int) -> dict[str, Any]:
        entity_id = entity.entity_id
        eligibility = extraction_eligibility_reason(entity, self.registry)
        decision = self.decisions.get(entity_id, {})
        reasons = self.events[entity_id]
        if node:
            reason = "included"
        elif decision:
            reason = decision["reason"]
        elif eligibility:
            reason = eligibility
        elif reasons:
            relation_reasons = set(reasons) & {"market_context_only", "risk_denied"}
            if len(relation_reasons) == 2:
                reason = "relation_excluded"
            elif relation_reasons:
                reason = next(iter(relation_reasons))
            else:
                reason = "mapping_excluded"
        else:
            reason = "no_signal"
        status = {
            "included": "included", "no_signal": "unmatched",
            "market_context_only": "relation_filtered", "risk_denied": "relation_filtered",
            "relation_excluded": "relation_filtered",
        }.get(reason, "excluded")
        if reason == "review_excluded" and entity.review_status == "pending_review":
            status = "pending_review"
        result = {
            "entity_id": entity_id, "canonical_name": entity.canonical_name,
            "status": status, "reason": reason, "review_status": entity.review_status,
            "answer_count": answer_count, "signal_count": signal_count,
            "reason_counts": dict(reasons), "evidence_samples": self.evidence[entity_id],
        }
        if node:
            result["score"] = node["gravity_score"]
            result["answer_count"] = node["answer_count"]
        elif "score" in decision:
            result["score"] = decision["score"]
        return result


def aggregate_topic_coverage(
    bodies: list[tuple[str, dict[str, Any]]], nodes: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Explain actual period nodes using recorded run outcomes, without rescoring.

    A missing/unknown historical ledger makes the whole period coverage unknown.
    Run IDs namespace answer references and deduplicate repeated source rows.
    """
    unique = dict(bodies)
    coverages = [(run_id, body.get("topic_coverage")) for run_id, body in unique.items()]
    if not coverages or any(not run_id or not isinstance(value, dict) or value.get("schema_version") != 1
                            for run_id, value in coverages):
        return None
    hashes = {value.get("lexicon_hash") for _, value in coverages}
    versions = {value.get("analysis_version") for _, value in coverages}
    if len(hashes) != 1 or not next(iter(hashes)) or versions != {TOPIC_ANALYSIS_VERSION}:
        return None
    base = deepcopy(coverages[0][1])
    grouped: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    expected_ids = {row["entity_id"] for row in base["topics"]}
    for run_id, coverage in coverages:
        rows = coverage.get("topics", [])
        if len(rows) != len(expected_ids) or {row["entity_id"] for row in rows} != expected_ids:
            return None
        for row in rows:
            grouped[row["entity_id"]].append((run_id, row))
    nodes_by_id = {
        str(node.get("lexicon_entity_id") or node.get("entity_id") or node.get("node_id")): node
        for node in nodes
    }
    topics = [_period_topic_row(grouped[key], nodes_by_id.get(key)) for key in sorted(grouped)]
    anchors = {entity_id for _, value in coverages for entity_id in value.get("anchor_entity_ids", [])}
    anchors &= set(nodes_by_id)
    included = sum(row["status"] == "included" for row in topics)
    return {
        **base, "scope": "period", "run_ids": list(unique), "topics": topics,
        "total_topic_count": len(topics), "included_topic_count": included,
        "anchor_node_count": len(anchors), "anchor_entity_ids": sorted(anchors),
        "other_node_count": len(nodes) - included - len(anchors),
        "status_counts": dict(Counter(row["status"] for row in topics)),
    }


def _period_topic_row(sources: list[tuple[str, dict]], node: dict | None) -> dict:
    result = deepcopy(sources[0][1])
    meaningful = [row for _, row in sources if row["reason"] != "no_signal"]
    reasons = {row["reason"] for row in meaningful}
    if node:
        result.update(status="included", reason="included", score=node.get("gravity_score"),
                      answer_count=int(node.get("answer_count") or node.get("mention_answer_count") or 0))
    else:
        result.pop("score", None)
        if len(reasons) == 1:
            result.update(status=meaningful[0]["status"], reason=meaningful[0]["reason"])
        elif reasons and reasons <= {"market_context_only", "risk_denied", "relation_excluded"}:
            result.update(status="relation_filtered", reason="relation_excluded")
        elif reasons:
            result.update(status="excluded", reason="multiple_run_outcomes")
        if "included" in reasons:
            result.update(status="excluded", reason="period_filtered")
        result["answer_count"] = sum(int(row.get("answer_count") or 0) for _, row in sources)
    result["signal_count"] = sum(int(row.get("signal_count") or 0) for _, row in sources)
    counts: Counter[str] = Counter()
    evidence = []
    for run_id, row in sources:
        counts.update(row.get("reason_counts", {}))
        for sample in row.get("evidence_samples", []):
            evidence.append({**sample, "run_id": run_id,
                             "answer_id": f"{run_id}:{sample.get('answer_id') or ''}"})
    evidence.sort(key=lambda sample: sample.get("reason") != "accepted")
    result["evidence_samples"] = evidence[:MAX_EVIDENCE_SAMPLES]
    result["reason_counts"] = dict(counts)
    result["run_outcomes"] = [{"run_id": run_id, "status": row["status"], "reason": row["reason"]}
                              for run_id, row in sources]
    return result
