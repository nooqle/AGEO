"""Calibration layer between A4 answer ingestion and A5 report writing.

This service consumes entity extraction signals and produces the stable
association-circle projection plus report input. A5 should read this calibrated
structure instead of re-extracting terms from raw answers.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.ontology import AmwayEntityDefinition, AmwayEntityOntologyRegistry
from app.ontology import load_default_amway_entity_ontology
from app.services.amway_entity_extraction_service import (
    AmwayEntityExtractionService,
)


CALIBRATION_SCHEMA_VERSION = "2026-07-14"
RISK_ORBIT = "risk_shadow"
STRATEGY_ENTITY_TYPES = {"BrandStrategy", "FourValue", "FlowerDimension"}
EXCLUDED_RELATION_TYPES = {"MARKET_CONTEXT_ONLY", "RISK_DENIED"}
RISK_RELATION_TYPES = {"RISKS_AS", "COMPETES_WITH"}
RISK_CONTEXT_ENTITY_IDS = {"evidence_regulation"}
SUPPORTIVE_CONTEXT_CUES = (
    "确实",
    "真实",
    "有一定道理",
    "合理",
    "适合",
    "可以",
    "支持",
    "有帮助",
    "优势",
    "匹配",
)
SKEPTICAL_CONTEXT_CUES = (
    "风险",
    "挑战",
    "质疑",
    "争议",
    "警惕",
    "谨慎",
    "高价",
    "价格高",
    "变现难",
    "少数赚钱",
    "多数陪跑",
    "直销基因",
    "枷锁",
    "传销",
    "拉人",
    "发展下线",
    "囤货",
    "熟人压力",
    "压力",
    "直销管理条例",
    "禁止多层计酬",
    "多层计酬",
    "巨大影响",
    "现实中的风险",
    "理想图景",
    "合规风险",
    "监管风险",
    "不可靠",
    "不适合",
    "理性看待",
)
REGULATORY_RISK_CUES = (
    "监管",
    "牌照",
    "许可",
    "备案",
    "批文",
    "合规",
    "直销",
    "条例",
)

FOUR_HAVE_STORYLINE_RULES: tuple[dict[str, Any], ...] = (
    {
        "key": "have_health",
        "label": "有健康",
        "annual_handle": "科技抗衰",
        "core_question": "AI 是否已经把安利带回长期健康管理？",
        "terms": (
            "有健康",
            "纽崔莱",
            "营养",
            "健康",
            "抗衰",
            "长寿时代",
            "心智抗衰",
            "细胞抗衰",
            "体重管理",
            "代谢管理",
            "营养早餐",
            "脑力抗衰",
            "行动力抗衰",
            "心血管健康",
            "科学研究",
            "认证与标准",
        ),
        "strategic_reading": "健康资产已经进入 AI 回答，但主叙事仍偏产品和品类，需要升级成可被复述的方案层。",
    },
    {
        "key": "have_companionship",
        "label": "有陪伴",
        "annual_handle": "安利社群外显",
        "core_question": "AI 是否把安利解释成关系陪伴和社群支持？",
        "terms": (
            "有陪伴",
            "良好关系",
            "社群陪伴",
            "关系抗衰",
            "美好生活社群",
            "美好生活共创空间",
            "长期陪伴网络",
            "亲子社群",
            "社群打卡",
        ),
        "risk_terms": ("卖货", "熟人", "压力", "拉人", "社群边界"),
        "strategic_reading": "陪伴叙事已经出现入口，但容易被卖货群、熟人销售压力和社群边界问题牵制。",
    },
    {
        "key": "have_security",
        "label": "有保障",
        "annual_handle": "透明事业边界",
        "core_question": "AI 是否认为安利能提供可信的保障感？",
        "terms": (
            "有保障",
            "财务保障",
            "事业机会",
            "人生托举",
            "直销",
            "合规",
            "监管",
            "认证",
        ),
        "risk_terms": (
            "传销",
            "拉人头",
            "发展下线",
            "熟人压力",
            "合规风险",
            "监管风险",
            "囤货",
            "收入不稳定",
        ),
        "strategic_reading": "保障感先受到信任、合规和收入边界影响，必须先把参与机制讲清楚。",
    },
    {
        "key": "have_value",
        "label": "有价值",
        "annual_handle": "人生再出发",
        "core_question": "AI 是否把安利解释成人生阶段里的价值感来源？",
        "terms": (
            "有价值",
            "人生再出发",
            "个人成长",
            "社会价值",
            "被需要",
            "价值感",
            "安利人",
        ),
        "risk_terms": ("收入", "变现", "少数赚钱", "多数陪跑", "发展下线"),
        "strategic_reading": "价值感需要先穿过保障和信任问题，随后才可能形成稳定的人生阶段叙事。",
    },
)


@dataclass(slots=True)
class _EntityAccumulator:
    entity_id: str
    entity_name: str
    entity_type: str
    term_origin: str
    graph_policy: dict[str, Any]
    source_policy: dict[str, Any]
    review_status: str
    matched_texts: Counter[str] = field(default_factory=Counter)
    answer_ids: set[str] = field(default_factory=set)
    question_ids: set[str] = field(default_factory=set)
    platforms: Counter[str] = field(default_factory=Counter)
    answer_positions: Counter[str] = field(default_factory=Counter)
    relation_types: Counter[str] = field(default_factory=Counter)
    audience_segments: Counter[str] = field(default_factory=Counter)
    opportunity_points: Counter[str] = field(default_factory=Counter)
    probe_types: Counter[str] = field(default_factory=Counter)
    signals: list[dict[str, Any]] = field(default_factory=list)


class AmwayEntityCalibrationService:
    """Aggregate answer-level signals into graph and report-ready structures."""

    def __init__(
        self,
        registry: AmwayEntityOntologyRegistry | None = None,
        extraction_service: AmwayEntityExtractionService | None = None,
    ) -> None:
        self.registry = registry or load_default_amway_entity_ontology()
        self.extraction_service = extraction_service or AmwayEntityExtractionService(
            self.registry
        )

    def calibrate(
        self,
        *,
        fetch_results: list[dict[str, Any]],
        extraction_result: dict[str, Any],
        center_terms: list[str] | None = None,
    ) -> dict[str, Any]:
        question_bank = _build_question_bank(fetch_results)
        question_signals = self._extract_question_signals(question_bank)
        signals = _dedupe_answer_signals(extraction_result.get("signals"))
        accumulators = self._build_accumulators(signals)
        sample_scope = self._build_sample_scope(
            fetch_results=fetch_results,
            extraction_result=extraction_result,
            question_bank=question_bank,
            signals=signals,
        )
        requested_platforms = _all_platform_names(fetch_results, signals)
        valid_platforms = _valid_platform_names(fetch_results, signals)
        platforms = valid_platforms or requested_platforms
        nodes, evidence_samples = self._build_nodes_and_evidence(
            accumulators=accumulators,
            total_valid_answers=int(sample_scope.get("valid_answer_count") or 0),
            total_platforms=max(len(platforms), 1),
            total_questions=max(len(question_bank), 1),
        )
        sample_scope["normalized_node_count"] = len(nodes)
        tracking_projection = _build_tracking_projection(
            nodes=nodes,
            platform_names=platforms,
        )
        sample_scope["tracking_status"] = tracking_projection["status"]
        sample_scope["tracking_status_label"] = tracking_projection["status_label"]
        sample_scope["tracking_round_label"] = tracking_projection["round_label"]
        platform_summary = _build_platform_summary(
            platforms=requested_platforms,
            valid_platforms=valid_platforms,
            signals=signals,
            fetch_results=fetch_results,
            nodes=nodes,
        )
        strategy_validation = self._build_strategy_validation(
            question_signals=question_signals,
            accumulators=accumulators,
            nodes=nodes,
            evidence_samples=evidence_samples,
            platforms=platforms,
        )
        risk_map = _build_risk_map(nodes=nodes, evidence_samples=evidence_samples)
        priority_summary = _build_priority_summary(
            nodes=nodes,
            risk_map=risk_map,
        )
        association_map = {
            "center_terms": _normalize_center_terms(center_terms, self.registry),
            "nodes": nodes,
            "evidence_samples": evidence_samples,
            "generated_from": "entity_calibration",
        }
        evidence_findings = _build_evidence_findings(
            nodes=nodes,
            evidence_samples=evidence_samples,
        )
        source_appendix = _build_source_appendix(
            question_bank=question_bank,
            evidence_samples=evidence_samples,
        )
        association_actions = _build_association_actions(nodes)
        strategy_storyline = _build_four_have_strategy_storyline(
            center_terms=association_map["center_terms"],
            sample_scope=sample_scope,
            nodes=nodes,
            strategy_validation=strategy_validation,
            risk_map=risk_map,
            platform_summary=platform_summary,
            source_appendix=source_appendix,
        )
        report_input = {
            "contract_version": CALIBRATION_SCHEMA_VERSION,
            "count_semantics": "distinct_answer_refs",
            "question_scope": _build_question_scope(question_bank),
            "platform_scope": platform_summary,
            "association_map": association_map,
            "strategy_validation": strategy_validation,
            "strategy_storyline": strategy_storyline,
            "risk_summary": risk_map,
            "priority_summary": priority_summary,
            "evidence_findings": evidence_findings,
            "source_appendix": source_appendix,
            "association_actions": association_actions,
            "tracking_projection": tracking_projection,
        }
        projection = {
            "center_terms": association_map["center_terms"],
            "nodes": nodes,
            "evidence_samples": evidence_samples,
            "question_bank": question_bank[:200],
            "platform_comparison": platform_summary.get("platforms", []),
            "association_actions": association_actions,
            "question_definition": report_input["question_scope"],
            "platform_source_summary": platform_summary,
            "evidence_findings": evidence_findings,
            "source_appendix": source_appendix,
            "strategy_validation": strategy_validation,
            "strategy_storyline": strategy_storyline,
            "risk_map": risk_map,
            "priority_summary": priority_summary,
            "sample_scope": sample_scope,
            "tracking_projection": tracking_projection,
            "generated_from": "entity_calibration",
        }

        return {
            "service": "AmwayEntityCalibrationService",
            "schema_version": CALIBRATION_SCHEMA_VERSION,
            "ontology_id": self.registry.definition.ontology_id,
            "ontology_version": self.registry.definition.version,
            "sample_scope": sample_scope,
            "association_map": association_map,
            "risk_map": risk_map,
            "priority_summary": priority_summary,
            "platform_summary": platform_summary,
            "strategy_validation": strategy_validation,
            "strategy_storyline": strategy_storyline,
            "evidence_index": {item["evidence_id"]: item for item in evidence_samples},
            "report_input": report_input,
            "association_circle_projection": projection,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _extract_question_signals(
        self,
        question_bank: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        for question in question_bank:
            text = " ".join(
                _clean_text(question.get(key))
                for key in (
                    "text",
                    "question",
                    "question_text",
                    "opportunity_point",
                    "life_scene",
                    "probe_type",
                    "mother_theme",
                )
                if _clean_text(question.get(key))
            )
            for signal in self.extraction_service.extract_question_entities(text):
                signals.append(
                    {
                        **signal,
                        "question_id": question.get("id"),
                        "question": question.get("text") or question.get("question"),
                    }
                )
        return signals

    def _build_accumulators(
        self,
        signals: list[dict[str, Any]],
    ) -> dict[str, _EntityAccumulator]:
        accumulators: dict[str, _EntityAccumulator] = {}
        for signal in signals:
            if _clean_text(signal.get("relation_type")) in EXCLUDED_RELATION_TYPES:
                continue
            entity_id = _clean_text(signal.get("entity_id"))
            entity = self.registry.get_entity(entity_id)
            if entity is None:
                continue
            acc = accumulators.setdefault(
                entity_id,
                _EntityAccumulator(
                    entity_id=entity_id,
                    entity_name=entity.canonical_name,
                    entity_type=entity.entity_type,
                    term_origin=_term_origin(entity),
                    graph_policy=entity.graph_policy.model_dump(),
                    source_policy=entity.source_policy.model_dump(),
                    review_status=entity.review_status,
                ),
            )
            acc.signals.append(signal)
            acc.matched_texts[_clean_text(signal.get("matched_text"))] += 1
            acc.answer_ids.add(_clean_text(signal.get("answer_id")))
            acc.question_ids.add(_clean_text(signal.get("question_id")))
            acc.platforms[_clean_text(signal.get("platform"))] += 1
            acc.answer_positions[_clean_text(signal.get("answer_position"))] += 1
            acc.relation_types[_clean_text(signal.get("relation_type"))] += 1
            context = (
                signal.get("question_context")
                if isinstance(signal.get("question_context"), dict)
                else {}
            )
            acc.audience_segments[_clean_text(context.get("audience_segment"))] += 1
            acc.opportunity_points[_clean_text(context.get("opportunity_point"))] += 1
            acc.probe_types[_clean_text(context.get("probe_type"))] += 1
        return accumulators

    def _build_nodes_and_evidence(
        self,
        *,
        accumulators: dict[str, _EntityAccumulator],
        total_valid_answers: int,
        total_platforms: int,
        total_questions: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        nodes: list[dict[str, Any]] = []
        evidence_samples: list[dict[str, Any]] = []
        evidence_index = 1
        for acc in accumulators.values():
            entity = self.registry.require_entity(acc.entity_id)
            if entity.entity_type in {"CenterBrand", "MarketContext"}:
                continue
            acc = self._risk_scoped_accumulator(entity, acc)
            score_components = _score_accumulator(
                acc,
                total_valid_answers=total_valid_answers,
                total_platforms=total_platforms,
                total_questions=total_questions,
            )
            raw_score = int(score_components["gravity_score"])
            stance_summary = _signal_stance_summary(acc.signals)
            is_risk = _is_risk_entity(entity, acc) or _is_contextual_risk_entity(
                entity,
                acc,
            )
            score = _context_adjusted_score(
                raw_score=raw_score,
                entity=entity,
                acc=acc,
                is_risk=is_risk,
                stance_summary=stance_summary,
            )
            score = _sample_confidence_adjusted_score(
                score=score,
                entity=entity,
                acc=acc,
                is_risk=is_risk,
            )
            score_components = {
                **score_components,
                "raw_gravity_score": raw_score,
                "gravity_score": score,
                "sentiment_gate_score": score,
                "supportive_evidence_count": stance_summary["supportive"],
                "skeptical_evidence_count": stance_summary["skeptical"],
                "risk_evidence_count": stance_summary["risk"],
                "competitive_evidence_count": stance_summary["competitive"],
            }
            if not is_risk and entity.graph_policy.main_orbit == "not_allowed":
                continue
            if score < 12 and not is_risk and acc.term_origin != "strategy":
                continue
            orbit, orbit_label = _orbit_for(score)
            if is_risk:
                orbit = RISK_ORBIT
                orbit_label = _risk_orbit_label(entity)
            node_id = f"node_{_safe_node_id(acc.entity_id)}"
            display_term = _node_display_term(entity=entity, is_risk=is_risk)
            node_evidence_ids: list[str] = []
            maturity_tier, maturity_label = _maturity_for(
                score=score,
                is_risk=is_risk,
                orbit=orbit,
            )
            for signal in _select_diverse_signals(acc.signals, limit=8):
                evidence_id = f"ev_{evidence_index:04d}"
                evidence_index += 1
                evidence_payload = _evidence_payload(
                    evidence_id=evidence_id,
                    node_id=node_id,
                    node_term=display_term,
                    signal=signal,
                )
                evidence_samples.append(evidence_payload)
                node_evidence_ids.append(evidence_id)
            node = {
                "node_id": node_id,
                "entity_id": acc.entity_id,
                "entity_type": acc.entity_type,
                "term": display_term,
                "normalized_expressions": [
                    item for item, _count in acc.matched_texts.most_common(8) if item
                ],
                "term_origin": acc.term_origin,
                "origin_label": "战略词" if acc.term_origin == "strategy" else "回答词",
                "source_policy": acc.source_policy,
                "graph_policy": acc.graph_policy,
                "review_status": acc.review_status,
                "orbit": orbit,
                "orbit_label": orbit_label,
                "business_tag": _business_tag(acc, score, is_risk),
                "maturity_tier": maturity_tier,
                "maturity_label": maturity_label,
                "association_score": score,
                "gravity_score": score,
                "closeness_score": score,
                "distance_score": 100 - score,
                **score_components,
                "semantic_direction": _semantic_direction(acc),
                "theme": _theme_for_entity(entity),
                "planet_group": _theme_for_entity(entity),
                "is_risk_term": is_risk,
                "is_target_term": acc.term_origin == "strategy",
                "answer_count": len([item for item in acc.answer_ids if item]),
                "answer_refs": sorted(item for item in acc.answer_ids if item),
                "answer_count_is_exact": True,
                "count_semantics": "distinct_answer_refs",
                "platform_count": len([item for item in acc.platforms if item]),
                "platform_distribution": dict(acc.platforms),
                "stance_summary": stance_summary,
                "primary_audience_segments": _top_counter_values(acc.audience_segments),
                "primary_opportunity_points": _top_counter_values(
                    acc.opportunity_points
                ),
                "relation_type_distribution": dict(acc.relation_types),
                "trigger_questions": sorted(item for item in acc.question_ids if item)[
                    :8
                ],
                "evidence_samples": node_evidence_ids,
                "evidence_count": len(acc.signals),
                "evidence_strength": _evidence_strength(acc),
                "source": "answer_parsed",
                "orbit_reason": _orbit_reason(
                    acc,
                    score,
                    is_risk,
                    display_term=display_term,
                ),
                "priority_rank": _node_priority_rank(
                    score=score,
                    is_risk=is_risk,
                    evidence_count=len(acc.signals),
                    platform_count=len([item for item in acc.platforms if item]),
                ),
            }
            nodes.append(node)
        nodes.sort(key=_node_sort_key)
        return nodes, evidence_samples

    def _risk_scoped_accumulator(
        self,
        entity: AmwayEntityDefinition,
        acc: _EntityAccumulator,
    ) -> _EntityAccumulator:
        if entity.entity_id != "evidence_regulation" or not _has_risk_relation(acc):
            return acc
        risk_signals = [
            signal
            for signal in acc.signals
            if _signal_stance(signal) in {"skeptical", "risk", "competitive"}
        ]
        return self._build_accumulators(risk_signals).get(acc.entity_id, acc)

    def _build_strategy_validation(
        self,
        *,
        question_signals: list[dict[str, Any]],
        accumulators: dict[str, _EntityAccumulator],
        nodes: list[dict[str, Any]],
        evidence_samples: list[dict[str, Any]],
        platforms: list[str],
    ) -> list[dict[str, Any]]:
        evidence_by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for evidence in evidence_samples:
            evidence_by_node[_clean_text(evidence.get("node_id"))].append(evidence)
        nodes_by_entity = {_clean_text(node.get("entity_id")): node for node in nodes}
        question_counts: Counter[str] = Counter()
        question_refs: dict[str, set[str]] = defaultdict(set)
        question_samples: dict[str, dict[str, str]] = defaultdict(dict)
        for signal in question_signals:
            if signal.get("entity_type") not in STRATEGY_ENTITY_TYPES:
                continue
            entity_id = _clean_text(signal.get("entity_id"))
            question_id = _clean_text(signal.get("question_id"))
            question_counts[entity_id] += 1
            question_refs[entity_id].add(question_id)
            question_text = _clean_text(signal.get("question"))
            if question_id and question_text:
                question_samples[entity_id][question_id] = question_text

        strategy_entity_ids = {
            entity.entity_id
            for entity in self.registry.entities
            if entity.entity_type == "BrandStrategy"
        }
        strategy_entity_ids.update(question_counts)
        strategy_entity_ids.update(
            entity_id
            for entity_id, acc in accumulators.items()
            if acc.term_origin == "strategy"
        )

        rows: list[dict[str, Any]] = []
        for entity_id in sorted(strategy_entity_ids):
            entity = self.registry.get_entity(entity_id)
            if entity is None:
                continue
            acc = accumulators.get(entity_id)
            node = nodes_by_entity.get(entity_id)
            answer_mentions = len(acc.answer_ids) if acc else 0
            platform_distribution = dict(acc.platforms) if acc else {}
            node_id = _clean_text(node.get("node_id")) if node else ""
            samples = evidence_by_node.get(node_id, []) if node_id else []
            selected_samples = _select_diverse_evidence_samples(samples, limit=6)
            evidence_question_samples: dict[str, str] = {}
            for sample in selected_samples:
                question_id = _clean_text(sample.get("question_id"))
                question_text = _clean_text(sample.get("question"))
                if question_id and question_text:
                    evidence_question_samples[question_id] = question_text
            evidence_question_refs = sorted(evidence_question_samples)
            display_question_refs = evidence_question_refs or sorted(
                item for item in question_refs.get(entity_id, set()) if item
            )
            display_question_samples = (
                evidence_question_samples
                if evidence_question_samples
                else question_samples.get(entity_id, {})
            )
            stance_summary = _stance_summary(samples)
            status = _strategy_status(
                answer_mentions=answer_mentions,
                platform_count=len(platform_distribution),
                question_count=len(display_question_refs),
                stance_summary=stance_summary,
            )
            validation_label = _strategy_validation_label(status, stance_summary)
            node_score = (
                int(node.get("gravity_score") or node.get("closeness_score") or 0)
                if node
                else 0
            )
            evidence_band = _strategy_evidence_band(
                status=status,
                answer_mentions=answer_mentions,
                platform_count=len(platform_distribution),
                node_score=node_score,
                stance_summary=stance_summary,
            )
            rows.append(
                {
                    "strategy_id": entity.entity_id,
                    "strategy_term": entity.canonical_name,
                    "entity_type": entity.entity_type,
                    "status": status,
                    "question_count": len(display_question_refs),
                    "question_refs": display_question_refs,
                    "designed_question_count": question_counts[entity_id],
                    "designed_question_refs": sorted(
                        item for item in question_refs.get(entity_id, set()) if item
                    ),
                    "question_samples": [
                        {"question_id": question_id, "question": question_text}
                        for question_id, question_text in sorted(
                            display_question_samples.items()
                        )[:6]
                    ],
                    "answer_mention_count": answer_mentions,
                    "answer_refs": sorted(acc.answer_ids) if acc else [],
                    "answer_count_is_exact": True,
                    "count_semantics": "distinct_answer_refs",
                    "platform_count": len(platform_distribution),
                    "platform_distribution": platform_distribution,
                    "stance_summary": stance_summary,
                    "validation_label": validation_label,
                    "node_score": node_score,
                    "evidence_band": evidence_band,
                    "decision_tier": _strategy_decision_tier(
                        status=status,
                        answer_mentions=answer_mentions,
                        platform_count=len(platform_distribution),
                        stance_summary=stance_summary,
                    ),
                    "related_node_ids": [node_id] if node_id else [],
                    "evidence_refs": [
                        _clean_text(sample.get("evidence_id"))
                        for sample in selected_samples
                    ],
                    "platform_outcomes": _platform_outcomes(
                        samples,
                        platforms=platforms,
                    ),
                    "interpretation": _strategy_interpretation(
                        term=entity.canonical_name,
                        status=status,
                        answer_mentions=answer_mentions,
                        platform_count=len(platform_distribution),
                        stance_summary=stance_summary,
                    ),
                    "action_recommendation": _strategy_action_recommendation(
                        term=entity.canonical_name,
                        evidence_band=evidence_band,
                        status=status,
                        answer_mentions=answer_mentions,
                        platform_count=len(platform_distribution),
                        stance_summary=stance_summary,
                    ),
                    "source_policy": entity.source_policy.model_dump(),
                    "review_status": entity.review_status,
                }
            )
        rows.sort(
            key=lambda row: (
                {"validated": 0, "risk": 1, "partial": 2, "missing": 3}.get(
                    str(row.get("status")),
                    9,
                ),
                -int(row.get("answer_mention_count") or 0),
                str(row.get("strategy_term") or ""),
            )
        )
        return rows

    def _build_sample_scope(
        self,
        *,
        fetch_results: list[dict[str, Any]],
        extraction_result: dict[str, Any],
        question_bank: list[dict[str, Any]],
        signals: list[dict[str, Any]],
    ) -> dict[str, Any]:
        status_counts = _fetch_result_status_counts(fetch_results)
        requested_platforms = _all_platform_names(fetch_results, signals)
        valid_platforms = _valid_platform_names(fetch_results, signals)
        return {
            "question_count": len(fetch_results or []),
            "question_bank_count": len(question_bank),
            "platform_count": len(valid_platforms),
            "platform_names": valid_platforms,
            "valid_platform_count": len(valid_platforms),
            "valid_platform_names": valid_platforms,
            "requested_platform_count": len(requested_platforms),
            "requested_platform_names": requested_platforms,
            "total_answer_count": status_counts["total_answer_count"],
            "valid_answer_count": status_counts["valid_answer_count"],
            "failed_answer_count": status_counts["failed_answer_count"],
            "empty_answer_count": status_counts["empty_answer_count"],
            "signal_count": len(signals),
            "center_linked_signal_count": len(
                [
                    signal
                    for signal in signals
                    if _clean_text(signal.get("relation_type"))
                    not in EXCLUDED_RELATION_TYPES
                ]
            ),
            "market_context_signal_count": len(
                [
                    signal
                    for signal in signals
                    if _clean_text(signal.get("relation_type"))
                    in EXCLUDED_RELATION_TYPES
                ]
            ),
            "answer_signal_count": extraction_result.get("answer_signal_count", 0),
            "normalized_node_count": 0,
            "scoring_model_version": "amway_entity_gravity_v2",
            "question_set_version": _question_set_version(question_bank),
        }


def _dedupe_answer_signals(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        if _is_legacy_related_term_answer_signal(item):
            continue
        answer_id = _clean_text(item.get("answer_id"))
        entity_id = _clean_text(item.get("entity_id"))
        if not answer_id or not entity_id:
            continue
        key = (answer_id, entity_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _is_legacy_related_term_answer_signal(item: dict[str, Any]) -> bool:
    return (
        _clean_text(item.get("source_side") or "answer") == "answer"
        and _clean_text(item.get("entity_type")) == "RiskLabel"
        and _clean_text(item.get("match_source")) == "related_term"
    )


def _score_accumulator(
    acc: _EntityAccumulator,
    *,
    total_valid_answers: int,
    total_platforms: int,
    total_questions: int,
) -> dict[str, int]:
    answer_count = len([item for item in acc.answer_ids if item])
    platform_count = len([item for item in acc.platforms if item])
    question_count = len([item for item in acc.question_ids if item])
    frequency_score = round(min(answer_count / max(total_valid_answers, 1), 1) * 100)
    position_score = _position_score(acc.answer_positions)
    relation_type_score = _relation_score(acc.relation_types)
    scene_coverage_score = round(min(question_count / max(total_questions, 1), 1) * 100)
    model_consistency_score = round(
        min(platform_count / max(total_platforms, 1), 1) * 100
    )
    gravity_score = round(
        frequency_score * 0.30
        + position_score * 0.20
        + relation_type_score * 0.20
        + scene_coverage_score * 0.15
        + model_consistency_score * 0.15
    )
    return {
        "frequency_score": frequency_score,
        "position_score": position_score,
        "relation_type_score": relation_type_score,
        "scene_coverage_score": scene_coverage_score,
        "model_consistency_score": model_consistency_score,
        "gravity_score": gravity_score,
    }


def _sample_confidence_adjusted_score(
    *,
    score: int,
    entity: AmwayEntityDefinition,
    acc: _EntityAccumulator,
    is_risk: bool,
) -> int:
    answer_count = len([item for item in acc.answer_ids if item])
    platform_count = len([item for item in acc.platforms if item])
    if answer_count <= 0:
        return min(score, 18)
    if platform_count <= 1 and answer_count <= 1:
        if entity.entity_type == "Competitor":
            return min(score, 28)
        if is_risk:
            return min(score, 32)
        return min(score, 34)
    if platform_count <= 1 and answer_count <= 3:
        if entity.entity_type == "Competitor":
            return min(score, 34)
        return min(score, 40)
    if platform_count <= 1 and answer_count <= 5:
        return min(score, 46)
    if platform_count == 2 and answer_count <= 2:
        return min(score, 45)
    return score


def _signal_stance_summary(signals: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter(_signal_stance(signal) for signal in signals)
    return {
        "supportive": counter.get("supportive", 0),
        "neutral": counter.get("neutral", 0),
        "skeptical": counter.get("skeptical", 0),
        "risk": counter.get("risk", 0),
        "competitive": counter.get("competitive", 0),
    }


def _signal_stance(signal: dict[str, Any]) -> str:
    relation_type = _clean_text(signal.get("relation_type"))
    context_polarity = _clean_text(signal.get("context_polarity"))
    text_parts = [
        _clean_text(signal.get("evidence_text")),
        _clean_text(signal.get("center_context_excerpt")),
        _clean_text(signal.get("question")),
    ]
    for key in ("risk_context_cues", "comparison_context_cues"):
        cues = signal.get(key)
        if isinstance(cues, list):
            text_parts.extend(_clean_text(item) for item in cues if _clean_text(item))
    text = " ".join(item for item in text_parts if item)
    if relation_type == "COMPETES_WITH":
        return "competitive"
    if relation_type == "RISKS_AS":
        return "risk"
    if relation_type == "RISK_DENIED":
        return "supportive"
    if context_polarity == "negative":
        return "skeptical"
    if any(cue in text for cue in SKEPTICAL_CONTEXT_CUES):
        return "skeptical"
    if any(cue in text for cue in SUPPORTIVE_CONTEXT_CUES):
        return "supportive"
    return "neutral"


def _context_adjusted_score(
    *,
    raw_score: int,
    entity: AmwayEntityDefinition,
    acc: _EntityAccumulator,
    is_risk: bool,
    stance_summary: dict[str, int],
) -> int:
    if is_risk:
        return raw_score
    if entity.entity_type not in STRATEGY_ENTITY_TYPES:
        return raw_score
    supportive = int(stance_summary.get("supportive") or 0)
    skeptical = int(stance_summary.get("skeptical") or 0)
    risk_like = int(stance_summary.get("risk") or 0) + int(
        stance_summary.get("competitive") or 0
    )
    caution_like = skeptical + risk_like
    if caution_like >= max(supportive, 1) and caution_like >= 2:
        penalty = min(
            26,
            10 + caution_like * 2 + max(caution_like - supportive, 0) * 2,
        )
        return min(raw_score, max(28, raw_score - penalty))
    if caution_like >= 1 and caution_like >= max(round(supportive * 0.5), 1):
        penalty = min(18, 6 + caution_like * 2)
        return min(raw_score, max(36, raw_score - penalty))
    if _has_accumulator_negative_context(acc):
        if caution_like >= max(supportive, 1):
            return min(raw_score, max(32, raw_score - 16))
        if caution_like:
            return min(raw_score, max(40, raw_score - 10))
    return raw_score


def _position_score(counter: Counter[str]) -> int:
    weights = {"start": 100, "middle": 72, "tail": 44, "unknown": 34}
    total = sum(counter.values())
    if not total:
        return 34
    score = sum(
        weights.get(position, 34) * count for position, count in counter.items()
    )
    return round(score / total)


def _select_diverse_signals(
    signals: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    selected_ids: set[int] = set()

    def add(signal: dict[str, Any]) -> None:
        if len(selected) >= limit:
            return
        key = id(signal)
        if key in selected_ids:
            return
        selected.append(signal)
        selected_ids.add(key)

    seen_platforms: set[str] = set()
    for signal in signals:
        platform = _clean_text(signal.get("platform"))
        if not platform or platform in seen_platforms:
            continue
        add(signal)
        seen_platforms.add(platform)
        if len(selected) >= limit:
            return selected

    seen_questions: set[str] = {
        _clean_text(signal.get("question_id")) for signal in selected
    }
    for signal in signals:
        question_id = _clean_text(signal.get("question_id"))
        if not question_id or question_id in seen_questions:
            continue
        add(signal)
        seen_questions.add(question_id)
        if len(selected) >= limit:
            return selected

    for signal in signals:
        add(signal)
        if len(selected) >= limit:
            return selected
    return selected


def _select_diverse_evidence_samples(
    samples: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()

    def add(sample: dict[str, Any]) -> None:
        evidence_id = _clean_text(sample.get("evidence_id"))
        if len(selected) >= limit or not evidence_id or evidence_id in selected_ids:
            return
        selected.append(sample)
        selected_ids.add(evidence_id)

    seen_platforms: set[str] = set()
    seen_questions: set[str] = set()
    seen_nodes: set[str] = set()
    platforms = []
    for sample in samples:
        platform = _clean_text(sample.get("platform"))
        if platform and platform not in platforms:
            platforms.append(platform)

    for platform in platforms:
        platform_samples = [
            sample
            for sample in samples
            if _clean_text(sample.get("platform")) == platform
        ]
        sample = next(
            (
                candidate
                for candidate in platform_samples
                if _clean_text(candidate.get("question_id"))
                and _clean_text(candidate.get("question_id")) not in seen_questions
                and _sample_node_key(candidate) not in seen_nodes
            ),
            platform_samples[0] if platform_samples else None,
        )
        if sample is None or platform in seen_platforms:
            continue
        add(sample)
        seen_platforms.add(platform)
        question_id = _clean_text(sample.get("question_id"))
        node_key = _sample_node_key(sample)
        if question_id:
            seen_questions.add(question_id)
        if node_key:
            seen_nodes.add(node_key)
        if len(selected) >= limit:
            return selected

    for sample in samples:
        node_key = _sample_node_key(sample)
        if not node_key or node_key in seen_nodes:
            continue
        question_id = _clean_text(sample.get("question_id"))
        if question_id and question_id in seen_questions:
            continue
        add(sample)
        seen_nodes.add(node_key)
        if question_id:
            seen_questions.add(question_id)
        if len(selected) >= limit:
            return selected

    for sample in samples:
        question_id = _clean_text(sample.get("question_id"))
        if not question_id or question_id in seen_questions:
            continue
        add(sample)
        seen_questions.add(question_id)
        node_key = _sample_node_key(sample)
        if node_key:
            seen_nodes.add(node_key)
        if len(selected) >= limit:
            return selected

    for sample in samples:
        node_key = _sample_node_key(sample)
        if not node_key or node_key in seen_nodes:
            continue
        add(sample)
        seen_nodes.add(node_key)
        if len(selected) >= limit:
            return selected

    for sample in samples:
        add(sample)
        if len(selected) >= limit:
            return selected
    return selected


def _sample_node_key(sample: dict[str, Any]) -> str:
    return _clean_text(sample.get("node_id")) or _clean_text(sample.get("node_term"))


def _relation_score(counter: Counter[str]) -> int:
    weights = {
        "LINKED_TO_CENTER_BRAND": 92,
        "MAPS_TO_STRATEGY": 78,
        "SUPPORTED_BY_PRODUCT": 74,
        "SUPPORTED_BY_SUBBRAND": 74,
        "MENTIONED_IN_ANSWER": 62,
        "RISKS_AS": 76,
        "RISK_DENIED": 0,
        "COMPETES_WITH": 70,
        "MARKET_CONTEXT_ONLY": 0,
    }
    total = sum(counter.values())
    if not total:
        return 50
    score = sum(
        weights.get(relation, 58) * count for relation, count in counter.items()
    )
    return round(score / total)


def _orbit_for(score: int) -> tuple[str, str]:
    if score >= 80:
        return "core_near", "已绑定资产"
    if score >= 60:
        return "strong", "已绑定资产"
    if score >= 50:
        return "near_opportunity", "近端机会"
    if score >= 35:
        return "far_opportunity", "远端机会"
    if score >= 20:
        return "weak", "待观察"
    return "blank", "远端待验证"


def _maturity_for(
    *,
    score: int,
    is_risk: bool,
    orbit: str,
) -> tuple[str, str]:
    if is_risk or orbit == RISK_ORBIT:
        return "risk", "风险关系"
    if score >= 60:
        return "stable_asset", "稳定资产"
    if score >= 50:
        return "near_opportunity", "近端机会"
    if score >= 35:
        return "far_opportunity", "远端机会"
    if score >= 20:
        return "watch_signal", "待观察"
    return "evidence_gap", "证据缺口"


def _risk_orbit_label(entity: AmwayEntityDefinition) -> str:
    if entity.entity_type == "Competitor":
        return "竞争关系"
    return "风险关系"


def _node_display_term(*, entity: AmwayEntityDefinition, is_risk: bool) -> str:
    if is_risk and entity.entity_id == "evidence_regulation":
        return "监管合规质疑"
    return entity.canonical_name


def _business_tag(acc: _EntityAccumulator, score: int, is_risk: bool) -> str:
    if is_risk:
        if acc.entity_type == "Competitor":
            return "竞争关系"
        return "风险认知"
    if score >= 60:
        return "已绑定资产"
    if acc.term_origin == "strategy":
        if score >= 50:
            return "战略近端机会"
        if score >= 35:
            return "战略远端机会"
        return "战略待验证"
    if score >= 50:
        return "近端机会"
    if score >= 35:
        return "远端机会"
    return "弱信号"


def _semantic_direction(acc: _EntityAccumulator) -> str:
    if acc.entity_type == "Competitor":
        return "竞争关系"
    if _has_risk_relation(acc):
        return "风险关系"
    if acc.entity_type == "RiskLabel":
        return "风险澄清"
    if acc.term_origin == "strategy":
        return "战略验证"
    if acc.entity_type in {"Solution", "HealthyLifestyle"}:
        return "解决方案"
    if acc.entity_type in {"SubBrand", "ProductCategory", "ProductFeature"}:
        return "产品资产"
    if acc.entity_type in {"Community", "BusinessModel", "Touchpoint"}:
        return "关系路径"
    return "回答联想"


def _theme_for_entity(entity: AmwayEntityDefinition) -> str:
    mapping = {
        "SubBrand": "品牌资产",
        "ProductCategory": "产品资产",
        "ProductFeature": "产品证据",
        "Solution": "解决方案",
        "HealthyLifestyle": "健康生活方式",
        "BrandStrategy": "品牌战略",
        "FourValue": "品牌战略",
        "FlowerDimension": "美好生活之花",
        "Community": "社群陪伴",
        "BusinessModel": "事业模式",
        "Touchpoint": "体验触点",
        "DigitalTool": "数字工具",
        "RiskLabel": "风险认知",
        "Competitor": "竞争关系",
    }
    return mapping.get(entity.entity_type, entity.entity_type)


def _evidence_payload(
    *,
    evidence_id: str,
    node_id: str,
    node_term: str,
    signal: dict[str, Any],
) -> dict[str, Any]:
    context = (
        signal.get("question_context")
        if isinstance(signal.get("question_context"), dict)
        else {}
    )
    return {
        "evidence_id": evidence_id,
        "node_id": node_id,
        "node_term": node_term,
        "entity_id": signal.get("entity_id"),
        "entity_type": signal.get("entity_type"),
        "answer_id": signal.get("answer_id"),
        "platform": signal.get("platform"),
        "question_id": signal.get("question_id"),
        "question": signal.get("question"),
        "matched_text": signal.get("matched_text"),
        "match_source": signal.get("match_source"),
        "answer_excerpt": signal.get("evidence_text"),
        "answer_position": signal.get("answer_position"),
        "relation_type": signal.get("relation_type"),
        "context_polarity": signal.get("context_polarity"),
        "comparison_context": bool(signal.get("comparison_context")),
        "risk_context_cues": signal.get("risk_context_cues") or [],
        "comparison_context_cues": signal.get("comparison_context_cues") or [],
        "evidence_strength": "stable",
        "question_mentions_center": bool(signal.get("question_mentions_center")),
        "answer_mentions_center": bool(signal.get("answer_mentions_center")),
        "near_center_context": bool(signal.get("near_center_context")),
        "center_connection_basis": signal.get("center_connection_basis"),
        "center_context_excerpt": signal.get("center_context_excerpt"),
        "audience_segment": context.get("audience_segment"),
        "core_anxiety": context.get("core_anxiety"),
        "life_scene": context.get("life_scene"),
        "opportunity_point": context.get("opportunity_point"),
        "probe_type": context.get("probe_type"),
        "mother_theme": context.get("mother_theme"),
        "question_type": context.get("question_type"),
        "mentions_amway": context.get("mentions_amway"),
        "life_stage": context.get("life_stage"),
        "four_have": context.get("four_have"),
        "touchpoint": context.get("touchpoint"),
        "monitoring_purpose": context.get("monitoring_purpose"),
    }


def _evidence_strength(acc: _EntityAccumulator) -> str:
    if len(acc.platforms) >= 3 and len(acc.answer_ids) >= 5:
        return "stable"
    if len(acc.platforms) >= 2:
        return "limited_stable"
    return "single_platform"


def _orbit_reason(
    acc: _EntityAccumulator,
    score: int,
    is_risk: bool,
    *,
    display_term: str,
) -> str:
    answer_count = len([item for item in acc.answer_ids if item])
    platform_count = len([item for item in acc.platforms if item])
    if is_risk:
        if acc.entity_type == "Competitor":
            scenes = _join_terms(_top_counter_values(acc.opportunity_points, 2))
            scene_text = f"，主要出现在{scenes}场景" if scenes else ""
            return (
                f"{display_term}被 {answer_count} 条回答提到，覆盖 "
                f"{platform_count} 个平台{scene_text}。它代表竞争或替代选择，"
                "需要和具体问题语境一起查看。"
            )
        return (
            f"{display_term}被 {answer_count} 条回答提到，覆盖 "
            f"{platform_count} 个平台，应进入风险关系单独查看。"
        )
    if score >= 60:
        return (
            f"{display_term}已经被 {answer_count} 条回答稳定带回品牌，"
            f"覆盖 {platform_count} 个平台。"
        )
    if score >= 50:
        return (
            f"{display_term}已有 {answer_count} 条回答证据，覆盖 "
            f"{platform_count} 个平台，属于近端机会，下一步要补直接证据。"
        )
    if score >= 35:
        return (
            f"{display_term}已有 {answer_count} 条回答证据，但平台和问题覆盖还弱，"
            "属于远端机会，需要先补场景和样本。"
        )
    return (
        f"{display_term}已有 {answer_count} 条回答证据，"
        "当前仍适合继续观察和补充样本。"
    )


def _node_priority_rank(
    *,
    score: int,
    is_risk: bool,
    evidence_count: int,
    platform_count: int,
) -> int:
    if is_risk:
        return 10 - min(evidence_count + platform_count, 8)
    if score >= 60:
        return 20 - min(platform_count, 4)
    if score >= 50:
        return 30 - min(evidence_count, 10)
    if score >= 35:
        return 40 - min(evidence_count, 8)
    return 50


def _build_tracking_projection(
    *,
    nodes: list[dict[str, Any]],
    platform_names: list[str],
) -> dict[str, Any]:
    maturity_counter: Counter[str] = Counter()
    orbit_counter: Counter[str] = Counter()
    for node in nodes:
        maturity_counter[
            _clean_text(node.get("maturity_tier")) or _clean_text(node.get("orbit"))
        ] += 1
        orbit_counter[_clean_text(node.get("orbit"))] += 1
    focus_nodes = sorted(
        nodes,
        key=lambda item: (
            int(item.get("priority_rank") or 99),
            -int(item.get("gravity_score") or 0),
            str(item.get("term") or ""),
        ),
    )[:8]
    return {
        "status": "baseline",
        "status_label": "首期基线",
        "round_label": "第 1 轮",
        "baseline_round": 1,
        "has_previous_round": False,
        "platform_names": [item for item in platform_names if item],
        "node_count": len(nodes),
        "maturity_counts": dict(maturity_counter),
        "orbit_counts": dict(orbit_counter),
        "baseline_focus": [
            {
                "node_id": node.get("node_id"),
                "term": node.get("term"),
                "maturity_tier": node.get("maturity_tier"),
                "maturity_label": node.get("maturity_label"),
                "orbit": node.get("orbit"),
                "gravity_score": node.get("gravity_score"),
                "evidence_count": node.get("evidence_count"),
                "platform_count": node.get("platform_count"),
            }
            for node in focus_nodes
        ],
        "next_compare_dimensions": [
            "节点位置",
            "平台覆盖",
            "证据数量",
            "风险关系",
            "战略词验证状态",
        ],
    }


def _join_terms(terms: list[str], fallback: str = "") -> str:
    values = [item for item in terms if item]
    return "、".join(values) if values else fallback


def _node_sort_key(node: dict[str, Any]) -> tuple[int, int, str]:
    order = {
        "core_near": 0,
        "strong": 1,
        "near_opportunity": 2,
        "contestable": 2,
        "far_opportunity": 3,
        "weak": 4,
        "blank": 5,
        RISK_ORBIT: 5,
    }
    return (
        int(node.get("priority_rank") or order.get(str(node.get("orbit")), 9)),
        -int(node.get("gravity_score") or 0),
        str(node.get("term") or ""),
    )


def _build_platform_summary(
    *,
    platforms: list[str],
    valid_platforms: list[str],
    signals: list[dict[str, Any]],
    fetch_results: list[dict[str, Any]],
    nodes: list[dict[str, Any]],
) -> dict[str, Any]:
    status_by_platform = _fetch_status_by_platform(fetch_results)
    valid_platform_set = set(valid_platforms)
    node_by_entity = {_clean_text(node.get("entity_id")): node for node in nodes}
    signals_by_platform: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for signal in signals:
        if _clean_text(signal.get("relation_type")) in EXCLUDED_RELATION_TYPES:
            continue
        signals_by_platform[_clean_text(signal.get("platform"))].append(signal)

    rows: list[dict[str, Any]] = []
    for platform in platforms:
        platform_signals = signals_by_platform.get(platform, [])
        entity_counter = Counter(
            _clean_text(signal.get("entity_id")) for signal in platform_signals
        )
        preferred_nodes = []
        competition_nodes = []
        for entity_id, _count in entity_counter.most_common():
            node = node_by_entity.get(entity_id)
            if not node:
                continue
            if node.get("business_tag") == "竞争关系":
                if len(competition_nodes) < 5:
                    competition_nodes.append(node.get("term"))
            elif not node.get("is_risk_term") and len(preferred_nodes) < 5:
                preferred_nodes.append(node.get("term"))
        risk_nodes = [
            node_by_entity.get(entity_id)
            for entity_id, _count in entity_counter.most_common()
            if node_by_entity.get(entity_id, {}).get("is_risk_term")
        ]
        status = status_by_platform.get(platform, {})
        valid_count = int(status.get("valid_answer_count") or 0)
        failed_count = int(status.get("failed_answer_count") or 0)
        empty_count = int(status.get("empty_answer_count") or 0)
        if valid_count > 0 or platform in valid_platform_set:
            status_label = "valid"
        elif failed_count > 0:
            status_label = "failed"
        elif empty_count > 0:
            status_label = "empty"
        else:
            status_label = "not_requested"
        rows.append(
            {
                "platform": platform,
                "total_answer_count": status.get("total_answer_count", 0),
                "valid_answer_count": valid_count,
                "failed_answer_count": failed_count,
                "empty_answer_count": empty_count,
                "is_valid_platform": status_label == "valid",
                "status": status_label,
                "preferred_nodes": [item for item in preferred_nodes if item],
                "competition_nodes": [item for item in competition_nodes if item],
                "risk_nodes": [
                    item.get("term")
                    for item in risk_nodes
                    if item and item.get("business_tag") != "竞争关系"
                ],
                "dominant_orbit": _dominant_orbit(platform, nodes),
                "answer_preference": _platform_preference_sentence(
                    platform=platform,
                    preferred_nodes=[item for item in preferred_nodes if item],
                    competition_nodes=[item for item in competition_nodes if item],
                    risk_count=len([item for item in risk_nodes if item]),
                ),
                "risk_bias": (
                    "风险提及较明显" if any(risk_nodes) else "风险提及不突出"
                ),
                "opportunity_bias": _opportunity_bias(preferred_nodes),
                "recommendation": "保留同题复测，观察代表节点是否稳定。",
            }
        )
    rows.sort(
        key=lambda item: (
            0 if item.get("is_valid_platform") else 1,
            -int(item.get("valid_answer_count") or 0),
            str(item.get("platform") or ""),
        )
    )
    return {
        "platform_count": len(valid_platforms),
        "platform_names": valid_platforms,
        "valid_platform_count": len(valid_platforms),
        "valid_platform_names": valid_platforms,
        "requested_platform_count": len(platforms),
        "requested_platform_names": platforms,
        "total_answer_count": sum(row["total_answer_count"] for row in rows),
        "valid_answer_count": sum(row["valid_answer_count"] for row in rows),
        "failed_answer_count": sum(row["failed_answer_count"] for row in rows),
        "empty_answer_count": sum(row["empty_answer_count"] for row in rows),
        "platforms": rows,
    }


def _platform_preference_sentence(
    *,
    platform: str,
    preferred_nodes: list[str],
    competition_nodes: list[str],
    risk_count: int,
) -> str:
    if preferred_nodes:
        return f"{platform}更常把回答组织到{ '、'.join(preferred_nodes[:3]) }。"
    if competition_nodes:
        return f"{platform}更容易带出{ '、'.join(competition_nodes[:3]) }等竞争参照。"
    if risk_count:
        return f"{platform}更容易暴露风险和信任问题。"
    return f"{platform}暂未形成稳定代表节点。"


def _opportunity_bias(preferred_nodes: list[Any]) -> str:
    terms = [str(item) for item in preferred_nodes if item]
    return "、".join(terms[:3]) if terms else "待观察"


def _dominant_orbit(platform: str, nodes: list[dict[str, Any]]) -> str:
    counter: Counter[str] = Counter()
    for node in nodes:
        distribution = node.get("platform_distribution")
        if not isinstance(distribution, dict):
            continue
        count = int(distribution.get(platform) or 0)
        if count:
            counter[_clean_text(node.get("orbit"))] += count
    return counter.most_common(1)[0][0] if counter else "unknown"


def _build_risk_map(
    *,
    nodes: list[dict[str, Any]],
    evidence_samples: list[dict[str, Any]],
) -> dict[str, Any]:
    risk_nodes = [node for node in nodes if node.get("is_risk_term")]
    evidence_by_id = {
        _clean_text(item.get("evidence_id")): item for item in evidence_samples
    }
    competition_nodes = [
        node for node in risk_nodes if node.get("business_tag") == "竞争关系"
    ]
    risk_only_nodes = [
        node for node in risk_nodes if node.get("business_tag") != "竞争关系"
    ]
    competition_scenes = _risk_scene_rows(
        nodes=competition_nodes,
        evidence_by_id=evidence_by_id,
    )
    risk_scenes = _risk_scene_rows(
        nodes=risk_only_nodes,
        evidence_by_id=evidence_by_id,
    )
    return {
        "risk_count": len(risk_nodes),
        "competition_count": len(competition_nodes),
        "nodes": risk_nodes,
        "competition_nodes": competition_nodes,
        "risk_nodes": risk_only_nodes,
        "competition_scenes": competition_scenes,
        "risk_scenes": risk_scenes,
        "evidence_samples": [
            evidence_by_id[evidence_id]
            for node in risk_nodes
            for evidence_id in node.get("evidence_samples") or []
            if evidence_id in evidence_by_id
        ],
        "reading": "风险认知和竞争关系作为单独关系查看，独立于正向机会轨道。",
    }


def _build_priority_summary(
    *,
    nodes: list[dict[str, Any]],
    risk_map: dict[str, Any],
) -> dict[str, Any]:
    risk_nodes = [
        node for node in risk_map.get("risk_nodes") or [] if isinstance(node, dict)
    ]
    competition_nodes = [
        node
        for node in risk_map.get("competition_nodes") or []
        if isinstance(node, dict)
    ]
    opportunity_nodes = [
        node
        for node in nodes
        if not node.get("is_risk_term")
        and str(node.get("maturity_tier") or "")
        in {
            "near_opportunity",
            "far_opportunity",
            "watch_signal",
            "evidence_gap",
        }
    ]
    stable_nodes = [
        node
        for node in nodes
        if not node.get("is_risk_term")
        and str(node.get("maturity_tier") or "") == "stable_asset"
    ]
    top_risks = [
        _priority_node_card(node, rank=index + 1, focus_type="risk")
        for index, node in enumerate(
            sorted(risk_nodes, key=_priority_node_sort_key)[:3]
        )
    ]
    top_competitors = [
        _priority_competitor_card(node, risk_map, rank=index + 1)
        for index, node in enumerate(
            sorted(competition_nodes, key=_priority_node_sort_key)[:3]
        )
    ]
    top_opportunities = [
        _priority_node_card(node, rank=index + 1, focus_type="opportunity")
        for index, node in enumerate(
            sorted(opportunity_nodes, key=_priority_node_sort_key)[:3]
        )
    ]
    top_assets = [
        _priority_node_card(node, rank=index + 1, focus_type="asset")
        for index, node in enumerate(
            sorted(stable_nodes, key=_priority_node_sort_key)[:3]
        )
    ]
    return {
        "top_risks": top_risks,
        "top_competitors": top_competitors,
        "top_opportunities": top_opportunities,
        "top_assets": top_assets,
        "next_focus": [
            *top_risks[:2],
            *top_competitors[:1],
            *top_opportunities[:2],
        ][:5],
        "reading": (
            "先看 Top 风险和竞品替代，再看近端机会；其余节点作为复测背景，"
            "不要求品牌团队逐个处理。"
        ),
    }


def _priority_node_sort_key(node: dict[str, Any]) -> tuple[int, int, int, int, str]:
    return (
        int(node.get("priority_rank") or 99),
        -int(node.get("evidence_count") or 0),
        -int(node.get("platform_count") or 0),
        -int(node.get("gravity_score") or node.get("closeness_score") or 0),
        str(node.get("term") or ""),
    )


def _priority_node_card(
    node: dict[str, Any],
    *,
    rank: int,
    focus_type: str,
) -> dict[str, Any]:
    evidence_count = int(node.get("answer_count") or node.get("evidence_count") or 0)
    platform_count = int(node.get("platform_count") or 0)
    answer_count_is_exact = node.get("answer_count_is_exact") is True or (
        node.get("answer_count_is_exact") is not False
        and (
            node.get("count_semantics") == "distinct_answer_refs"
            or isinstance(node.get("answer_refs"), list)
        )
    )
    count_semantics = (
        "distinct_answer_refs"
        if answer_count_is_exact
        else (
            "known_answer_refs_lower_bound"
            if node.get("count_semantics") == "known_answer_refs_lower_bound"
            else "legacy_summed_mentions"
        )
    )
    count_phrase = (
        f"{evidence_count} 条回答"
        if count_semantics == "distinct_answer_refs"
        else (
            f"至少 {evidence_count} 条可确认回答"
            if count_semantics == "known_answer_refs_lower_bound"
            else f"{evidence_count} 次节点提及"
        )
    )
    scenes = _join_terms(
        [
            str(item)
            for item in node.get("primary_opportunity_points") or []
            if str(item or "").strip()
        ][:2],
        "本轮核心问题",
    )
    if focus_type == "risk":
        action = "先补澄清证据和替代表达"
    elif focus_type == "opportunity":
        action = "补品牌锚定题和场景证据"
    elif focus_type == "asset":
        action = "沉淀为稳定内容资产"
    else:
        action = "回看原文语境"
    return {
        "rank": rank,
        "node_id": node.get("node_id"),
        "term": node.get("term"),
        "focus_type": focus_type,
        "business_tag": node.get("business_tag"),
        "maturity_tier": node.get("maturity_tier"),
        "score": node.get("gravity_score") or node.get("closeness_score"),
        "evidence_count": evidence_count,
        "answer_count_is_exact": answer_count_is_exact,
        "count_semantics": count_semantics,
        "platform_count": platform_count,
        "scene_hint": scenes,
        "reason": (
            f"{count_phrase}、{platform_count} 个平台提及，" f"主要出现在{scenes}。"
        ),
        "recommended_action": action,
        "evidence_refs": list(node.get("evidence_samples") or [])[:4],
    }


def _priority_competitor_card(
    node: dict[str, Any],
    risk_map: dict[str, Any],
    *,
    rank: int,
) -> dict[str, Any]:
    base = _priority_node_card(node, rank=rank, focus_type="competitor")
    scenes = [
        item
        for item in risk_map.get("competition_scenes") or []
        if isinstance(item, dict)
        and _clean_text(item.get("node_id")) == _clean_text(node.get("node_id"))
    ]
    scene = scenes[0] if scenes else {}
    base.update(
        {
            "focus_type": "competitor",
            "scene_hint": _join_terms(
                [str(item) for item in scene.get("scenes") or [] if str(item).strip()],
                base.get("scene_hint") or "竞品替代场景",
            ),
            "platform_distribution": scene.get("platform_distribution")
            or node.get("platform_distribution")
            or {},
            "question_refs": scene.get("question_refs")
            or node.get("trigger_questions")
            or [],
            "sample_excerpt": scene.get("sample_excerpt") or "",
            "recommended_action": "拆清替代场景并补差异化证据",
        }
    )
    return base


def _risk_scene_rows(
    *,
    nodes: list[dict[str, Any]],
    evidence_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for node in nodes:
        evidence_ids = [
            _clean_text(item)
            for item in node.get("evidence_samples") or []
            if _clean_text(item)
        ]
        samples = [
            evidence_by_id[item] for item in evidence_ids[:6] if item in evidence_by_id
        ]
        scene_counter: Counter[str] = Counter()
        platform_counter: Counter[str] = Counter()
        question_ids: set[str] = set()
        for sample in samples:
            scene = (
                _clean_text(sample.get("opportunity_point"))
                or _clean_text(sample.get("life_scene"))
                or "未标注场景"
            )
            scene_counter[scene] += 1
            platform_counter[_clean_text(sample.get("platform"))] += 1
            question_ids.add(_clean_text(sample.get("question_id")))
        rows.append(
            {
                "node_id": node.get("node_id"),
                "node_term": node.get("term"),
                "business_tag": node.get("business_tag"),
                "scenes": _top_counter_values(scene_counter, 4),
                "platform_distribution": {
                    platform: count
                    for platform, count in platform_counter.items()
                    if platform
                },
                "question_refs": sorted(item for item in question_ids if item)[:8],
                "evidence_refs": evidence_ids[:8],
                "sample_excerpt": samples[0].get("answer_excerpt") if samples else "",
            }
        )
    return rows


def _build_evidence_findings(
    *,
    nodes: list[dict[str, Any]],
    evidence_samples: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    evidence_by_id = {
        _clean_text(item.get("evidence_id")): item for item in evidence_samples
    }
    findings: list[dict[str, Any]] = []
    for node in nodes[:80]:
        refs = [
            evidence_id
            for evidence_id in node.get("evidence_samples") or []
            if _clean_text(evidence_id) in evidence_by_id
        ]
        samples = [evidence_by_id[ref] for ref in refs[:2]]
        first_sample = samples[0] if samples else {}
        findings.append(
            {
                "node_id": node.get("node_id"),
                "node_term": node.get("term"),
                "entity_id": node.get("entity_id"),
                "entity_type": node.get("entity_type"),
                "claim": _finding_claim(node),
                "orbit": node.get("orbit"),
                "orbit_label": node.get("orbit_label"),
                "business_tag": node.get("business_tag"),
                "supporting_facts": [
                    (
                        f"{node.get('answer_count', 0)} 条回答提到，"
                        f"覆盖 {node.get('platform_count', 0)} 个平台。"
                    ),
                    f"命中词：{'、'.join(node.get('normalized_expressions') or [])}。",
                ],
                "evidence_refs": refs,
                "sample_platform": first_sample.get("platform"),
                "sample_question": first_sample.get("question"),
                "sample_excerpt": first_sample.get("answer_excerpt"),
                "implication": node.get("orbit_reason"),
            }
        )
    return findings


def _finding_claim(node: dict[str, Any]) -> str:
    term = _clean_text(node.get("term"))
    scenes = _join_terms(
        [item for item in node.get("primary_opportunity_points") or [] if item],
        "相关问题",
    )
    if node.get("business_tag") == "竞争关系":
        return f"{term}是本轮回答里的竞争参照，主要需要回到{scenes}场景判断。"
    if _finding_node_is_risk(node):
        return f"{term}会把品牌解释带向风险或信任问题，主要出现在{scenes}场景。"
    if node.get("term_origin") == "strategy":
        return f"{term}属于战略验证词，本轮已有回答证据。"
    if node.get("orbit") in {"core_near", "strong"}:
        return f"{term}已经是回答端较稳定的品牌联想。"
    if node.get("maturity_tier") in {"near_opportunity", "far_opportunity"}:
        return f"{term}是本轮回答里可以继续拉近的机会线索，主要出现在{scenes}场景。"
    return f"{term}是回答中出现的机会线索。"


def _finding_node_is_risk(node: dict[str, Any]) -> bool:
    graph_policy = (
        node.get("graph_policy") if isinstance(node.get("graph_policy"), dict) else {}
    )
    return (
        bool(node.get("is_risk_term"))
        and node.get("business_tag") == "风险认知"
        and node.get("maturity_tier") == "risk"
        and graph_policy.get("risk_view") != "not_allowed"
    )


def _build_source_appendix(
    *,
    question_bank: list[dict[str, Any]],
    evidence_samples: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    question_by_id = {_clean_text(item.get("id")): item for item in question_bank}
    rows: list[dict[str, Any]] = []
    for evidence in _select_diverse_evidence_samples(
        evidence_samples, limit=len(evidence_samples)
    ):
        question_id = _clean_text(evidence.get("question_id"))
        question = question_by_id.get(question_id, {})
        rows.append(
            {
                "evidence_id": evidence.get("evidence_id"),
                "answer_id": evidence.get("answer_id"),
                "entity_id": evidence.get("entity_id"),
                "entity_type": evidence.get("entity_type"),
                "question_id": question_id,
                "question": evidence.get("question"),
                "platform": evidence.get("platform"),
                "node_term": evidence.get("node_term"),
                "answer_excerpt": evidence.get("answer_excerpt"),
                "relation_type": evidence.get("relation_type"),
                "center_connection_basis": evidence.get("center_connection_basis"),
                "question_mentions_center": evidence.get("question_mentions_center"),
                "answer_mentions_center": evidence.get("answer_mentions_center"),
                "near_center_context": evidence.get("near_center_context"),
                "center_context_excerpt": evidence.get("center_context_excerpt"),
                "audience_segment": question.get("audience_segment")
                or evidence.get("audience_segment"),
                "life_scene": question.get("life_scene") or evidence.get("life_scene"),
                "opportunity_point": question.get("opportunity_point")
                or evidence.get("opportunity_point"),
                "probe_type": question.get("probe_type") or evidence.get("probe_type"),
            }
        )
    return rows


def _build_four_have_strategy_storyline(
    *,
    center_terms: list[str],
    sample_scope: dict[str, Any],
    nodes: list[dict[str, Any]],
    strategy_validation: list[dict[str, Any]],
    risk_map: dict[str, Any],
    platform_summary: dict[str, Any],
    source_appendix: list[dict[str, Any]],
) -> dict[str, Any]:
    pillars = [
        _build_four_have_pillar(
            rule=rule,
            nodes=nodes,
            strategy_validation=strategy_validation,
            risk_map=risk_map,
            source_appendix=source_appendix,
        )
        for rule in FOUR_HAVE_STORYLINE_RULES
    ]
    health = _find_pillar(pillars, "have_health")
    companionship = _find_pillar(pillars, "have_companionship")
    security = _find_pillar(pillars, "have_security")
    value = _find_pillar(pillars, "have_value")
    verdict = {
        "center_term": center_terms[0] if center_terms else "安利",
        "headline": (
            "四有当前状态："
            f"有健康{health.get('status_label') or '待观察'}；"
            f"有陪伴{companionship.get('status_label') or '待观察'}；"
            f"有保障{security.get('status_label') or '待观察'}；"
            f"有价值{value.get('status_label') or '待观察'}。"
        ),
        "health_status": health.get("status_label"),
        "companionship_status": companionship.get("status_label"),
        "security_status": security.get("status_label"),
        "value_status": value.get("status_label"),
        "sample_sentence": (
            f"本轮围绕 {int(sample_scope.get('question_count') or 0)} 个问题，"
            f"读取 {int(sample_scope.get('valid_answer_count') or 0)} 条有效回答，"
            f"覆盖 {int(sample_scope.get('platform_count') or 0)} 个有效平台。"
        ),
    }
    weekly_actions = [
        {
            "action_id": "health_solution_upgrade",
            "pillar": "有健康",
            "annual_handle": "科技抗衰",
            "title": "把健康资产从产品层升级到方案层",
            "action": "围绕纽崔莱、体重管理、抗衰和科学证据，补一组可以直接进入 AI 回答的方案素材。",
            "validation": "下一轮看健康节点是否从品类罗列转向长期健康管理方案。",
        },
        {
            "action_id": "community_public_proof",
            "pillar": "有陪伴",
            "annual_handle": "安利社群外显",
            "title": "让社群陪伴脱离卖货群旧认知",
            "action": "补公开可验证的社群陪伴场景、参与边界和真实陪伴案例。",
            "validation": "下一轮看良好关系、社群陪伴是否减少风险伴随语境。",
        },
        {
            "action_id": "trust_boundary_repair",
            "pillar": "有保障 + 有价值",
            "annual_handle": "透明事业边界 / 人生再出发",
            "title": "先修复保障感，再讨论价值感",
            "action": "优先澄清直销、收入、合规和参与成本，再把人生再出发写成价值感叙事。",
            "validation": "下一轮看传销/拉人头、熟人压力等风险词是否下降，有价值类节点是否获得更多正向证据。",
        },
    ]
    return {
        "framework": "amway_four_have_storyline_v2",
        "center_terms": center_terms,
        "verdict": verdict,
        "pillars": pillars,
        "weekly_actions": weekly_actions,
        "platform_scope": {
            "requested_platform_names": platform_summary.get("requested_platform_names")
            or platform_summary.get("platform_names")
            or [],
            "valid_platform_names": platform_summary.get("platform_names") or [],
        },
        "risk_absorption": {
            "security_risk_terms": security.get("risk_terms", []),
            "companionship_risk_terms": companionship.get("risk_terms", []),
            "competition_terms": health.get("competition_terms", []),
            "reading": "风险和竞品被放回四有叙事：竞品主要作为有健康升级参照，传销/拉人头等风险解释有保障受遮蔽的原因。",
        },
    }


def _distinct_answer_mention_count(
    rows: list[dict[str, Any]],
    *,
    reference_key: str,
) -> int:
    return _answer_count_measure(rows, reference_key=reference_key)[0]


def _answer_count_measure(
    rows: list[dict[str, Any]],
    *,
    reference_key: str,
) -> tuple[int, str, bool]:
    modes: list[str] = []
    answer_refs: set[str] = set()
    declared_counts: list[int] = []
    for row in rows:
        raw_refs = row.get(reference_key)
        refs = {
            _clean_text(reference)
            for reference in raw_refs or []
            if _clean_text(reference)
        }
        answer_refs.update(refs)
        declared_count = int(
            row.get("answer_mention_count")
            or row.get("mention_answer_count")
            or row.get("answer_count")
            or 0
        )
        semantics = _clean_text(row.get("count_semantics"))
        is_exact = row.get("answer_count_is_exact")
        if semantics == "known_answer_refs_lower_bound":
            mode = "lower_bound"
        elif semantics == "legacy_summed_mentions" or is_exact is False:
            mode = "legacy"
        elif isinstance(raw_refs, list) and (
            semantics == "distinct_answer_refs"
            or is_exact is True
            or (not semantics and is_exact is None)
        ):
            mode = "exact"
        else:
            mode = "legacy"
        modes.append(mode)
        if mode == "exact":
            declared_counts.append(len(refs))
        elif mode == "lower_bound":
            declared_counts.append(max(declared_count, len(refs)))
        else:
            declared_counts.append(declared_count)

    if modes and all(mode == "exact" for mode in modes):
        return len(answer_refs), "distinct_answer_refs", True
    if modes and all(mode in {"exact", "lower_bound"} for mode in modes):
        lower_bound = max([len(answer_refs), *declared_counts], default=0)
        return lower_bound, "known_answer_refs_lower_bound", False
    return sum(declared_counts), "legacy_summed_mentions", False


def _build_four_have_pillar(
    *,
    rule: dict[str, Any],
    nodes: list[dict[str, Any]],
    strategy_validation: list[dict[str, Any]],
    risk_map: dict[str, Any],
    source_appendix: list[dict[str, Any]],
) -> dict[str, Any]:
    terms = tuple(
        _clean_text(item) for item in rule.get("terms", ()) if _clean_text(item)
    )
    risk_terms = tuple(
        _clean_text(item) for item in rule.get("risk_terms", ()) if _clean_text(item)
    )
    matched_strategy_rows = [
        row
        for row in strategy_validation
        if _term_matches_any(row.get("strategy_term"), terms)
    ]
    matched_nodes = [
        node for node in nodes if _term_matches_any(node.get("term"), terms)
    ]
    positive_nodes = [
        node
        for node in matched_nodes
        if not node.get("is_risk_term")
        and _clean_text(node.get("business_tag")) != "竞争关系"
    ]
    competition_nodes = [
        node
        for node in (risk_map.get("competition_nodes") or [])
        if isinstance(node, dict)
        and (
            rule.get("key") == "have_health"
            or _term_matches_any(node.get("term"), terms)
        )
    ]
    matched_risk_nodes = [
        node
        for node in (risk_map.get("risk_nodes") or [])
        if isinstance(node, dict)
        and (
            _term_matches_any(node.get("term"), risk_terms)
            or _term_matches_any(node.get("term"), terms)
        )
    ]
    evidence_refs = _unique_texts(
        [
            ref
            for row in matched_strategy_rows
            for ref in row.get("evidence_refs", [])[:3]
        ]
        + [
            ref
            for node in positive_nodes[:5]
            for ref in node.get("evidence_samples", [])[:2]
        ]
    )[:10]
    sample_questions = _unique_questions(matched_strategy_rows, limit=5)
    platform_distribution = _merge_platform_distributions(
        [*positive_nodes, *competition_nodes, *matched_risk_nodes]
    )
    status, status_label = _four_have_status(
        rule_key=_clean_text(rule.get("key")),
        strategy_rows=matched_strategy_rows,
        positive_nodes=positive_nodes,
        risk_nodes=matched_risk_nodes,
        competition_nodes=competition_nodes,
    )
    source_samples = _source_samples_for_terms(
        source_appendix=source_appendix,
        terms=[
            node.get("term")
            for node in [*positive_nodes, *matched_risk_nodes, *competition_nodes]
        ],
        limit=4,
    )
    answer_measure_rows = [*matched_strategy_rows, *positive_nodes]
    answer_count, count_semantics, answer_count_is_exact = _answer_count_measure(
        answer_measure_rows,
        reference_key="answer_refs",
    )
    return {
        "key": rule.get("key"),
        "label": rule.get("label"),
        "annual_handle": rule.get("annual_handle"),
        "core_question": rule.get("core_question"),
        "strategic_reading": rule.get("strategic_reading"),
        "status": status,
        "status_label": status_label,
        "node_terms": [_clean_text(node.get("term")) for node in positive_nodes[:8]],
        "risk_terms": [
            _clean_text(node.get("term")) for node in matched_risk_nodes[:8]
        ],
        "competition_terms": [
            _clean_text(node.get("term")) for node in competition_nodes[:6]
        ],
        "strategy_terms": [
            _clean_text(row.get("strategy_term")) for row in matched_strategy_rows[:8]
        ],
        "sample_questions": sample_questions,
        "answer_mention_count": answer_count,
        "answer_count_is_exact": answer_count_is_exact,
        "count_semantics": count_semantics,
        "platform_count": len(platform_distribution),
        "platform_distribution": platform_distribution,
        "evidence_refs": evidence_refs,
        "source_samples": source_samples,
    }


def _four_have_status(
    *,
    rule_key: str,
    strategy_rows: list[dict[str, Any]],
    positive_nodes: list[dict[str, Any]],
    risk_nodes: list[dict[str, Any]],
    competition_nodes: list[dict[str, Any]],
) -> tuple[str, str]:
    answer_mentions = _distinct_answer_mention_count(
        [*strategy_rows, *positive_nodes],
        reference_key="answer_refs",
    )
    risk_count = sum(int(node.get("answer_count") or 0) for node in risk_nodes)
    if rule_key == "have_health":
        if answer_mentions >= 8 or positive_nodes:
            return "caught_product_layer", "已接住，仍偏产品层"
        return "under_evidenced", "健康方案证据不足"
    if rule_key == "have_companionship":
        if answer_mentions and risk_count:
            return "emerging_hijacked", "有萌芽，受旧认知牵制"
        if answer_mentions:
            return "emerging", "有萌芽，仍需外显"
        return "missing", "尚未进入稳定回答"
    if rule_key == "have_security":
        if risk_count:
            return "obscured_by_risk", "受信任风险遮蔽"
        if answer_mentions:
            return "partially_caught", "部分被接住"
        return "missing", "尚未形成保障感"
    if rule_key == "have_value":
        if risk_count and not answer_mentions:
            return "blocked_by_security", "被保障问题前置阻断"
        if answer_mentions:
            return "thin_signal", "有弱信号，仍缺故事"
        return "missing", "尚未进入稳定回答"
    if competition_nodes:
        return "competition_referenced", "伴随竞品参照"
    return "observed", "进入观察"


def _find_pillar(pillars: list[dict[str, Any]], key: str) -> dict[str, Any]:
    return next((pillar for pillar in pillars if pillar.get("key") == key), {})


def _term_matches_any(value: Any, cues: tuple[str, ...] | list[str]) -> bool:
    text = _clean_text(value)
    if not text:
        return False
    return any(cue and (cue in text or text in cue) for cue in cues)


def _merge_platform_distributions(nodes: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for node in nodes:
        distribution = node.get("platform_distribution")
        if not isinstance(distribution, dict):
            continue
        for platform, count in distribution.items():
            platform_name = _clean_text(platform)
            if platform_name:
                counter[platform_name] += int(count or 0)
    return dict(counter)


def _unique_texts(values: list[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_text(value)
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output


def _unique_questions(
    strategy_rows: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for strategy_row in strategy_rows:
        for item in strategy_row.get("question_samples") or []:
            if not isinstance(item, dict):
                continue
            question = _clean_text(item.get("question"))
            question_id = _clean_text(item.get("question_id"))
            key = question_id or question
            if not key or key in seen:
                continue
            seen.add(key)
            rows.append({"question_id": question_id, "question": question})
            if len(rows) >= limit:
                return rows
    return rows


def _source_samples_for_terms(
    *,
    source_appendix: list[dict[str, Any]],
    terms: list[Any],
    limit: int,
) -> list[dict[str, Any]]:
    cue_terms = tuple(_clean_text(term) for term in terms if _clean_text(term))
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in source_appendix:
        if not isinstance(item, dict):
            continue
        node_term = _clean_text(item.get("node_term"))
        if cue_terms and not _term_matches_any(node_term, cue_terms):
            continue
        platform = _clean_text(item.get("platform"))
        question = _clean_text(item.get("question"))
        excerpt = _clean_text(item.get("answer_excerpt"))
        key = (platform, question[:40], excerpt[:40])
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "platform": platform,
                "question": question,
                "node_term": node_term,
                "answer_excerpt": excerpt,
            }
        )
        if len(rows) >= limit:
            break
    return rows


def _build_association_actions(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    selected_nodes: list[dict[str, Any]] = []
    seen_node_ids: set[str] = set()
    ranked_nodes = sorted(
        nodes,
        key=lambda item: (
            int(item.get("priority_rank") or 99),
            -int(item.get("gravity_score") or 0),
            str(item.get("term") or ""),
        ),
    )
    for node in [
        *ranked_nodes[:12],
        *[item for item in ranked_nodes if item.get("is_risk_term")][:4],
    ]:
        node_id = _clean_text(node.get("node_id"))
        if not node_id or node_id in seen_node_ids:
            continue
        seen_node_ids.add(node_id)
        selected_nodes.append(node)
    for node in selected_nodes[:16]:
        action_type = _action_type(node)
        target_platforms = _action_target_platforms(node)
        target_audience = _action_target_audience(node)
        target_scene = _action_target_scene(node)
        goal_metric = _action_goal_metric(
            node,
            action_type,
            target_platforms=target_platforms,
        )
        actions.append(
            {
                "id": f"association_{action_type}_{node.get('node_id')}",
                "action_type": action_type,
                "action_label": _action_label(action_type),
                "title": _action_title(node, action_type),
                "node_id": node.get("node_id"),
                "node_term": node.get("term"),
                "orbit": node.get("orbit"),
                "business_tag": node.get("business_tag"),
                "priority": _action_priority(node, action_type),
                "priority_reason": _action_priority_reason(node, action_type),
                "target_platforms": target_platforms,
                "target_audience": target_audience,
                "target_scene": target_scene,
                "goal_metric": goal_metric,
                "reason": node.get("orbit_reason"),
                "expected_impact": _expected_impact(action_type),
                "execution_steps": _execution_steps(
                    node,
                    action_type,
                    target_platforms=target_platforms,
                    target_scene=target_scene,
                ),
                "review_criteria": _action_review_criteria(
                    node,
                    action_type,
                    goal_metric=goal_metric,
                ),
                "next_question_suggestion": _action_next_question(node, action_type),
                "evidence_refs": (node.get("evidence_samples") or [])[:6],
            }
        )
    return actions


def _action_type(node: dict[str, Any]) -> str:
    if node.get("business_tag") == "竞争关系":
        return "differentiate"
    if node.get("is_risk_term"):
        return "translate"
    if node.get("orbit") in {"core_near", "strong"}:
        return "amplify"
    if node.get("term_origin") == "strategy":
        return "build_evidence"
    return "build_path"


def _action_label(action_type: str) -> str:
    return {
        "differentiate": "区分竞争",
        "translate": "澄清风险",
        "amplify": "放大资产",
        "build_evidence": "补战略证据",
        "build_path": "补连接路径",
    }.get(action_type, "继续观察")


def _action_title(node: dict[str, Any], action_type: str) -> str:
    label = _action_label(action_type)
    return f"{label}：{node.get('term')}"


def _expected_impact(action_type: str) -> str:
    return {
        "differentiate": "降低竞品参照对用户问题入口的占用。",
        "translate": "降低旧认知对品牌解释的占用。",
        "amplify": "提升已绑定资产的稳定重复。",
        "build_evidence": "让战略词获得更多回答证据。",
        "build_path": "把机会线索讲成可被回答引用的路径。",
    }.get(action_type, "持续追踪节点变化。")


def _action_target_platforms(node: dict[str, Any]) -> list[str]:
    distribution = node.get("platform_distribution")
    if not isinstance(distribution, dict):
        return []
    return [
        platform
        for platform, _count in sorted(
            distribution.items(),
            key=lambda item: (-int(item[1] or 0), str(item[0])),
        )
        if _clean_text(platform)
    ][:3]


def _action_target_audience(node: dict[str, Any]) -> str:
    return _join_terms(
        [item for item in node.get("primary_audience_segments") or [] if item],
        "核心题库人群",
    )


def _action_target_scene(node: dict[str, Any]) -> str:
    return _join_terms(
        [item for item in node.get("primary_opportunity_points") or [] if item],
        "相关生活场景",
    )


def _action_priority(node: dict[str, Any], action_type: str) -> str:
    if node.get("is_risk_term") or action_type in {"differentiate", "translate"}:
        return "high"
    score = int(node.get("gravity_score") or 0)
    if score >= 60:
        return "high"
    if score >= 35:
        return "medium"
    return "low"


def _action_priority_reason(node: dict[str, Any], action_type: str) -> str:
    if action_type == "differentiate":
        return "竞品参照会占用用户问题入口，需要优先拆清场景。"
    if action_type == "translate":
        return "风险认知会干扰品牌解释，需要优先补澄清材料。"
    if action_type == "amplify":
        return "该节点已经靠近中心，应尽快沉淀成跨平台内容资产。"
    if action_type == "build_evidence":
        return "该战略词已进入回答视野，需要补足可引用证据。"
    return "该线索已有回答证据，可以通过问题和内容继续拉近。"


def _action_goal_metric(
    node: dict[str, Any],
    action_type: str,
    *,
    target_platforms: list[str],
) -> str:
    current_platforms = int(node.get("platform_count") or len(target_platforms))
    current_answers = int(node.get("answer_count") or node.get("evidence_count") or 0)
    if action_type in {"differentiate", "translate"}:
        return "下一轮同类问题中风险或竞品提及下降，正向解释样本增加。"
    if action_type == "amplify":
        return (
            f"下一轮至少 {max(current_platforms, 2)} 个平台继续提及，"
            f"有效回答不低于 {max(current_answers, 3)} 条。"
        )
    if action_type == "build_evidence":
        return "下一轮进入近端机会或稳定资产，且至少覆盖 2 个平台。"
    return "下一轮距离分下降，平台覆盖不少于本轮。"


def _action_review_criteria(
    node: dict[str, Any],
    action_type: str,
    *,
    goal_metric: str,
) -> str:
    term = _clean_text(node.get("term"))
    if action_type in {"differentiate", "translate"}:
        return f"复测{term}相关问题，检查风险/竞品提及是否下降；目标：{goal_metric}"
    return f"复测{term}相关问题，检查位置是否向中心移动；目标：{goal_metric}"


def _action_next_question(node: dict[str, Any], action_type: str) -> str:
    term = _clean_text(node.get("term")) or "这个方向"
    scene = _action_target_scene(node)
    if action_type == "differentiate":
        return f"在{scene}场景里，用户为什么选择安利而不选择{term}？"
    if action_type == "translate":
        return f"用户担心{term}时，安利能提供哪些事实和服务边界？"
    if action_type == "amplify":
        return f"安利如何把{term}做成用户容易理解、可长期坚持的方案？"
    if action_type == "build_evidence":
        return f"安利在{scene}里如何证明{term}有真实价值？"
    return f"安利如何把{term}从普通建议变成品牌可被引用的连接路径？"


def _execution_steps(
    node: dict[str, Any],
    action_type: str,
    *,
    target_platforms: list[str],
    target_scene: str,
) -> list[str]:
    term = _clean_text(node.get("term"))
    platforms = _join_terms(target_platforms, "本轮有效平台")
    if action_type == "differentiate":
        return [
            f"整理{term}出现的{target_scene}问题场景。",
            "补充安利在同场景下的差异化证据。",
            f"用{platforms}复测竞品参照是否下降。",
        ]
    if action_type == "translate":
        return [
            f"整理{term}出现的原文语境。",
            "补充澄清内容和替代表达。",
            f"用{platforms}复测风险是否下降。",
        ]
    if action_type == "amplify":
        return [
            f"把{term}沉淀为稳定内容素材。",
            "补充跨平台都能引用的事实。",
            f"用{platforms}观察它是否继续贴近中心品牌。",
        ]
    if action_type == "build_evidence":
        return [
            f"围绕{term}补问题和证据。",
            "给出人群场景、产品证据和真实案例。",
            f"用{platforms}观察它是否向内移动。",
        ]
    return [
        f"拆清{term}连接品牌的路径。",
        "补充可引用的短证据链。",
        f"用{platforms}复测路径是否稳定。",
    ]


def _build_question_scope(question_bank: list[dict[str, Any]]) -> dict[str, Any]:
    audience_segments = _counter_values_from_records(question_bank, "audience_segment")
    probe_types = _counter_values_from_records(question_bank, "probe_type")
    opportunity_points = _counter_values_from_records(
        question_bank, "opportunity_point"
    )
    life_scenes = _counter_values_from_records(question_bank, "life_scene")
    return {
        "center_term": "安利",
        "center_terms": ["安利"],
        "question_count": len(question_bank),
        "question_bank_count": len(question_bank),
        "question_set_version": _question_set_version(question_bank),
        "question_sources": dict(
            Counter(
                _clean_text(item.get("source")) or "fetch_result"
                for item in question_bank
            )
        ),
        "audience_segments": audience_segments,
        "probe_types": probe_types,
        "opportunity_points": opportunity_points,
        "life_scenes": life_scenes,
        "sample_questions": question_bank[:8],
        "definition_sentence": (
            f"本轮使用 {len(question_bank)} 个问题，观察平台回答如何把安利带入健康、"
            "事业、社群和生活场景。"
        ),
    }


def _build_question_bank(fetch_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(fetch_results or [], start=1):
        if not isinstance(row, dict):
            continue
        question_id = (
            _clean_text(row.get("question_id") or row.get("id")) or f"q_{index:03d}"
        )
        if question_id in seen:
            continue
        seen.add(question_id)
        questions.append(
            {
                "id": question_id,
                "text": _clean_text(row.get("question_text") or row.get("question")),
                "source": _clean_text(row.get("source")) or "fetch_result",
                "audience_segment": _clean_text(row.get("audience_segment")),
                "core_anxiety": _clean_text(row.get("core_anxiety")),
                "life_scene": _clean_text(row.get("life_scene")),
                "opportunity_point": _clean_text(row.get("opportunity_point")),
                "probe_type": _clean_text(row.get("probe_type")),
                "mother_theme": _clean_text(row.get("mother_theme")),
                "question_type": _clean_text(row.get("question_type")),
                "metadata_status": _clean_text(row.get("metadata_status")),
                "question_set_version": _clean_text(row.get("question_set_version")),
            }
        )
    return questions


def _fetch_result_status_counts(fetch_results: list[dict[str, Any]]) -> dict[str, int]:
    total = 0
    valid = 0
    failed = 0
    empty = 0
    for row in fetch_results or []:
        if not isinstance(row, dict):
            continue
        platform_results = row.get("platform_results")
        if not isinstance(platform_results, list):
            continue
        for platform_result in platform_results:
            if not isinstance(platform_result, dict):
                continue
            total += 1
            answer_text = _answer_text(platform_result)
            if answer_text:
                valid += 1
            elif (
                platform_result.get("success") is False
                or platform_result.get("error")
                or platform_result.get("error_message")
            ):
                failed += 1
            else:
                empty += 1
    return {
        "total_answer_count": total,
        "valid_answer_count": valid,
        "failed_answer_count": failed,
        "empty_answer_count": empty,
    }


def _fetch_status_by_platform(
    fetch_results: list[dict[str, Any]],
) -> dict[str, dict[str, int]]:
    rows: dict[str, dict[str, int]] = {}
    for row in fetch_results or []:
        if not isinstance(row, dict):
            continue
        platform_results = row.get("platform_results")
        if not isinstance(platform_results, list):
            continue
        for platform_result in platform_results:
            if not isinstance(platform_result, dict):
                continue
            platform = _normalize_platform(platform_result.get("platform"))
            item = rows.setdefault(
                platform,
                {
                    "total_answer_count": 0,
                    "valid_answer_count": 0,
                    "failed_answer_count": 0,
                    "empty_answer_count": 0,
                },
            )
            item["total_answer_count"] += 1
            if _answer_text(platform_result):
                item["valid_answer_count"] += 1
            elif (
                platform_result.get("success") is False
                or platform_result.get("error")
                or platform_result.get("error_message")
            ):
                item["failed_answer_count"] += 1
            else:
                item["empty_answer_count"] += 1
    return rows


def _all_platform_names(
    fetch_results: list[dict[str, Any]],
    signals: list[dict[str, Any]],
) -> list[str]:
    names = {
        _clean_text(signal.get("platform"))
        for signal in signals
        if _clean_text(signal.get("platform"))
    }
    for row in fetch_results or []:
        if not isinstance(row, dict):
            continue
        for platform_result in row.get("platform_results") or []:
            if isinstance(platform_result, dict):
                names.add(_normalize_platform(platform_result.get("platform")))
    return sorted(name for name in names if name)


def _valid_platform_names(
    fetch_results: list[dict[str, Any]],
    signals: list[dict[str, Any]],
) -> list[str]:
    names = {
        _clean_text(signal.get("platform"))
        for signal in signals
        if _clean_text(signal.get("platform"))
        and _clean_text(signal.get("relation_type")) not in EXCLUDED_RELATION_TYPES
    }
    for row in fetch_results or []:
        if not isinstance(row, dict):
            continue
        for platform_result in row.get("platform_results") or []:
            if not isinstance(platform_result, dict):
                continue
            platform = _normalize_platform(platform_result.get("platform"))
            if platform and _answer_text(platform_result):
                names.add(platform)
    return sorted(name for name in names if name)


def _platform_names(
    fetch_results: list[dict[str, Any]],
    signals: list[dict[str, Any]],
) -> list[str]:
    return _valid_platform_names(fetch_results, signals) or _all_platform_names(
        fetch_results,
        signals,
    )


def _answer_text(platform_result: dict[str, Any]) -> str:
    answer_payload = (
        platform_result.get("answer")
        if isinstance(platform_result.get("answer"), dict)
        else {}
    )
    return _clean_text(
        answer_payload.get("content")
        or platform_result.get("answer_text")
        or platform_result.get("content")
        or platform_result.get("text")
    )


def _strategy_status(
    *,
    answer_mentions: int,
    platform_count: int,
    question_count: int,
    stance_summary: dict[str, int] | None = None,
) -> str:
    stance_summary = stance_summary or {}
    supportive = int(stance_summary.get("supportive") or 0)
    caution = int(stance_summary.get("skeptical") or 0)
    risk = int(stance_summary.get("risk") or 0) + int(
        stance_summary.get("competitive") or 0
    )
    risk_like = caution + risk
    if answer_mentions <= 0 and question_count <= 0:
        return "missing"
    if risk >= max(supportive, 1) and risk >= 2:
        return "risk"
    if risk_like >= max(supportive, 1) and risk_like >= 3:
        return "partial"
    if (
        answer_mentions >= 3
        and platform_count >= 2
        and supportive >= 3
        and (risk_like == 0 or (risk_like <= 1 and supportive >= risk_like * 4))
    ):
        return "validated"
    if answer_mentions > 0 or question_count > 0:
        return "partial"
    return "missing"


def _strategy_interpretation(
    *,
    term: str,
    status: str,
    answer_mentions: int,
    platform_count: int,
    stance_summary: dict[str, int] | None = None,
) -> str:
    stance_summary = stance_summary or {}
    supportive = int(stance_summary.get("supportive") or 0)
    skeptical = int(stance_summary.get("skeptical") or 0)
    risk = int(stance_summary.get("risk") or 0) + int(
        stance_summary.get("competitive") or 0
    )
    if status == "validated":
        return (
            f"{term}获得 {supportive or answer_mentions} 条正向回答支撑，"
            f"覆盖 {platform_count} 个平台。"
        )
    if status == "risk":
        return (
            f"{term}被 {answer_mentions} 条回答提及，"
            f"其中 {risk or skeptical} 条带有风险、质疑或竞争语境。"
        )
    if status == "partial":
        if skeptical or risk:
            return (
                f"{term}已有回答线索，覆盖 {platform_count} 个平台，"
                f"但同时出现 {skeptical + risk} 条风险或质疑语境。"
            )
        return f"{term}有问题或回答线索，回答重复还不够稳定。"
    return f"{term}在本轮回答里缺少可用证据。"


def _platform_outcomes(
    samples: list[dict[str, Any]],
    *,
    platforms: list[str],
) -> list[dict[str, Any]]:
    by_platform: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in samples:
        platform = _clean_text(sample.get("platform"))
        if platform:
            by_platform[platform].append(sample)
    platform_names = sorted(
        set([_clean_text(item) for item in platforms if _clean_text(item)])
        | set(by_platform.keys())
    )
    return [
        {
            "platform": platform,
            "answer_count": len(rows),
            "status": "mentioned" if rows else "not_mentioned",
            "sample_excerpt": (
                _clean_text(rows[0].get("answer_excerpt")) if rows else ""
            ),
            "stance": _dominant_stance(_stance_summary(rows)),
            "stance_summary": _stance_summary(rows),
        }
        for platform in platform_names
        for rows in [by_platform.get(platform, [])]
        if platform
    ]


def _stance_summary(samples: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for sample in samples:
        counter[_evidence_stance(sample)] += 1
    return {
        "supportive": counter.get("supportive", 0),
        "neutral": counter.get("neutral", 0),
        "skeptical": counter.get("skeptical", 0),
        "risk": counter.get("risk", 0),
        "competitive": counter.get("competitive", 0),
    }


def _evidence_stance(sample: dict[str, Any]) -> str:
    relation_type = _clean_text(sample.get("relation_type"))
    context_polarity = _clean_text(sample.get("context_polarity"))
    text = " ".join(
        _clean_text(sample.get(key))
        for key in ("answer_excerpt", "center_context_excerpt", "question")
        if _clean_text(sample.get(key))
    )
    if relation_type == "COMPETES_WITH":
        return "competitive"
    if relation_type == "RISKS_AS":
        return "risk"
    if relation_type == "RISK_DENIED":
        return "supportive"
    if context_polarity == "negative":
        return "skeptical"
    if any(cue in text for cue in SKEPTICAL_CONTEXT_CUES):
        return "skeptical"
    if any(cue in text for cue in SUPPORTIVE_CONTEXT_CUES):
        return "supportive"
    return "neutral"


def _dominant_stance(stance_summary: dict[str, int]) -> str:
    if not sum(int(value or 0) for value in stance_summary.values()):
        return "not_mentioned"
    ordered = ("risk", "competitive", "skeptical", "supportive", "neutral")
    return max(ordered, key=lambda key: int(stance_summary.get(key) or 0))


def _strategy_validation_label(status: str, stance_summary: dict[str, int]) -> str:
    if status == "validated":
        return "已被回答接住"
    if status == "risk":
        return "风险遮蔽"
    if (
        int(stance_summary.get("skeptical") or 0)
        or int(stance_summary.get("risk") or 0)
        or int(stance_summary.get("competitive") or 0)
    ):
        return "部分验证，伴随质疑"
    if status == "partial":
        return "部分验证"
    return "尚未验证"


def _strategy_decision_tier(
    *,
    status: str,
    answer_mentions: int,
    platform_count: int,
    stance_summary: dict[str, int],
) -> str:
    skeptical = int(stance_summary.get("skeptical") or 0)
    risk = int(stance_summary.get("risk") or 0) + int(
        stance_summary.get("competitive") or 0
    )
    if status == "risk" or risk >= 2:
        return "risk_first"
    if status == "validated" and answer_mentions >= 30 and platform_count >= 3:
        return "amplify"
    if skeptical or status == "partial":
        return "evidence_building"
    return "observe"


def _strategy_evidence_band(
    *,
    status: str,
    answer_mentions: int,
    platform_count: int,
    node_score: int,
    stance_summary: dict[str, int],
) -> str:
    supportive = int(stance_summary.get("supportive") or 0)
    skeptical = int(stance_summary.get("skeptical") or 0)
    risk_like = int(stance_summary.get("risk") or 0) + int(
        stance_summary.get("competitive") or 0
    )
    if status == "risk" or (risk_like >= max(supportive, 1) and risk_like >= 2):
        return "risk_first"
    if (
        status == "validated"
        and node_score >= 60
        and answer_mentions >= 20
        and platform_count >= 3
    ):
        return "stable_amplify"
    if status == "validated" or node_score >= 50 or platform_count >= 2:
        return "near_build"
    if answer_mentions > 0 or skeptical:
        return "far_probe"
    return "question_gap"


def _strategy_action_recommendation(
    *,
    term: str,
    evidence_band: str,
    status: str,
    answer_mentions: int,
    platform_count: int,
    stance_summary: dict[str, int],
) -> str:
    risk_like = int(stance_summary.get("risk") or 0) + int(
        stance_summary.get("competitive") or 0
    )
    skeptical = int(stance_summary.get("skeptical") or 0)
    lane = _strategy_lane(term)
    if evidence_band == "stable_amplify":
        return _strategy_stable_action(term, lane, answer_mentions, platform_count)
    if evidence_band == "risk_first" or status == "risk":
        return _strategy_risk_action(term, lane, risk_like + skeptical)
    if evidence_band == "near_build":
        return _strategy_near_action(term, lane, answer_mentions, platform_count)
    if evidence_band == "far_probe":
        return _strategy_far_action(term, lane)
    return _strategy_gap_action(term, lane)


def _strategy_lane(term: str) -> str:
    if any(
        cue in term
        for cue in ("财务", "保障", "事业", "安利人", "价值", "再出发", "成长")
    ):
        return "career"
    if any(cue in term for cue in ("关系", "陪伴", "社群", "一起")):
        return "relationship"
    if any(cue in term for cue in ("绿色", "和谐", "环境")):
        return "green"
    if any(
        cue in term
        for cue in ("健康", "抗衰", "长寿", "活力", "营养", "身体", "情绪", "大健康")
    ):
        return "health"
    return "general"


def _strategy_stable_action(
    term: str,
    lane: str,
    answer_mentions: int,
    platform_count: int,
) -> str:
    focus = {
        "relationship": "沉淀关系陪伴案例，区分社群支持和熟人销售压力",
        "career": "整理收入边界、合规说明和真实参与路径",
        "green": "补齐家庭环境健康、净水净化和绿色生活的产品证据",
        "health": "沉淀科学依据、产品组合和人群使用场景",
    }.get(lane, "整理为可复用的品牌解释和原文证据包")
    return (
        f"把{term}进入放大清单，优先{focus}；下轮看是否至少 "
        f"{max(platform_count, 3)} 个平台继续自然提及，回答样本不低于 {max(answer_mentions, 10)} 条。"
    )


def _strategy_risk_action(term: str, lane: str, risk_count: int) -> str:
    focus = {
        "relationship": "补社群边界、陪伴机制和非强销售场景，降低熟人压力联想",
        "career": "先写清收入预期、投入成本、合规边界和不承诺收益的表达",
        "green": "把环保理念落到具体产品、检测依据和家庭场景，避免停留在口号",
        "health": "补科学依据、适用边界和不可替代医疗建议的说明",
    }.get(lane, "先补澄清证据、替代表达和可核验事实")
    return (
        f"{term}先处理质疑语境：{focus}；下轮目标是相关质疑低于本轮 "
        f"{max(risk_count, 1)} 条，且正向样本增加。"
    )


def _strategy_near_action(
    term: str,
    lane: str,
    answer_mentions: int,
    platform_count: int,
) -> str:
    focus = {
        "relationship": "增加退休后陪伴、朋友网络和社群支持类问题",
        "career": "增加第二曲线、长期参与、收入预期和合规收益边界类问题",
        "green": "增加家庭清洁、净水、空气净化和绿色生活方式问题",
        "health": "增加具体健康方案、长期管理和产品组合问题",
    }.get(lane, "增加品牌锚定题和场景题")
    return (
        f"围绕{term}{focus}，同时补 2 条可引用原文和 1 组品牌事实；"
        f"下轮目标是证据超过 {max(answer_mentions + 3, 6)} 条，并保持 {max(platform_count, 2)} 个以上平台覆盖。"
    )


def _strategy_far_action(term: str, lane: str) -> str:
    focus = {
        "relationship": "先验证这个词是否能自然连接到人群关系和社群陪伴",
        "career": "先验证它是否会被平台理解成事业机会、个人成长或收入想象",
        "green": "先验证平台会把它理解为家庭环境健康，还是普通公益表达",
        "health": "先验证它会落到具体健康方案，还是停留在宽泛健康口号",
    }.get(lane, "先验证平台会如何解释这个词")
    return f"先把{term}保留为观察对象，{focus}；下轮至少拿到 2 个平台的可读原文。"


def _strategy_gap_action(term: str, lane: str) -> str:
    focus = {
        "relationship": "补一条点名安利的关系题和一条不点名的陪伴场景题",
        "career": "补一条事业机会边界题和一条退休后价值感场景题",
        "green": "补一条家庭环境健康题和一条产品证据题",
        "health": "补一条长期健康管理题和一条具体解决方案题",
    }.get(lane, "补一条品牌锚定题和一条场景题")
    return f"{term}当前证据不足，先{focus}；形成可展示节点后再进入战略验证。"


def _counter_values_from_records(
    records: list[dict[str, Any]],
    key: str,
    limit: int = 6,
) -> list[str]:
    counter: Counter[str] = Counter()
    for record in records:
        text = _clean_text(record.get(key))
        if text:
            counter[text] += 1
    return _top_counter_values(counter, limit)


def _top_counter_values(counter: Counter[str], limit: int = 3) -> list[str]:
    return [value for value, _count in counter.most_common(limit) if value]


def _question_set_version(question_bank: list[dict[str, Any]]) -> str | None:
    for item in question_bank:
        text = _clean_text(item.get("question_set_version"))
        if text:
            return text
    return None


def _is_risk_entity(entity: AmwayEntityDefinition, acc: _EntityAccumulator) -> bool:
    if entity.entity_type == "Competitor":
        return True
    if entity.entity_type == "RiskLabel":
        return _has_risk_relation(acc)
    return any(
        cue in entity.canonical_name
        for cue in ("风险", "传销", "夸大", "压力", "智商税")
    ) and _has_risk_relation(acc)


def _has_risk_relation(acc: _EntityAccumulator) -> bool:
    return any(relation in RISK_RELATION_TYPES for relation in acc.relation_types)


def _is_contextual_risk_entity(
    entity: AmwayEntityDefinition,
    acc: _EntityAccumulator,
) -> bool:
    graph_policy = (
        entity.graph_policy.model_dump()
        if hasattr(entity.graph_policy, "model_dump")
        else entity.graph_policy
    )
    if (
        isinstance(graph_policy, dict)
        and graph_policy.get("risk_view") == "not_allowed"
        and entity.entity_id not in RISK_CONTEXT_ENTITY_IDS
    ):
        return False
    if entity.entity_id in RISK_CONTEXT_ENTITY_IDS:
        return _has_risk_relation(acc)
    if entity.entity_type == "Touchpoint" and _has_risk_relation(acc):
        return True
    return False


def _has_accumulator_negative_context(acc: _EntityAccumulator) -> bool:
    if any(
        _clean_text(signal.get("context_polarity")) == "negative"
        for signal in acc.signals
    ):
        return True
    context_text = _accumulator_context_text(acc)
    return any(cue in context_text for cue in SKEPTICAL_CONTEXT_CUES)


def _accumulator_context_text(acc: _EntityAccumulator) -> str:
    parts: list[str] = []
    for signal in acc.signals:
        parts.extend(
            _clean_text(signal.get(key))
            for key in (
                "question",
                "matched_text",
                "evidence_text",
                "center_context_excerpt",
            )
            if _clean_text(signal.get(key))
        )
        cues = signal.get("risk_context_cues")
        if isinstance(cues, list):
            parts.extend(_clean_text(item) for item in cues if _clean_text(item))
    return " ".join(parts)


def _term_origin(entity: AmwayEntityDefinition) -> str:
    if entity.entity_type in STRATEGY_ENTITY_TYPES:
        return "strategy"
    return "answer"


def _normalize_center_terms(
    center_terms: list[str] | None,
    registry: AmwayEntityOntologyRegistry,
) -> list[str]:
    terms = [_clean_text(item) for item in center_terms or [] if _clean_text(item)]
    if terms:
        return terms[:1]
    return [registry.definition.center_brand_policy.default_center_brand]


def _normalize_platform(value: Any) -> str:
    text = _clean_text(value)
    aliases = {
        "deepseek": "DeepSeek",
        "kimi": "Kimi",
        "moonshot": "Kimi",
        "doubao": "豆包",
        "豆包": "豆包",
        "yuanbao": "元宝",
        "元宝": "元宝",
        "chatgpt": "ChatGPT",
        "gpt": "ChatGPT",
    }
    return aliases.get(text.lower(), text or "Unknown")


def _safe_node_id(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_]+", "_", value).strip("_") or "entity"


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
