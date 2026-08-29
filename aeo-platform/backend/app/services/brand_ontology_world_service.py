"""Compact ontology world snapshots for orchestrator planning."""

from __future__ import annotations

import re
import time
from collections import Counter
from copy import deepcopy
from typing import Any
from uuid import UUID

from app.models.brand_intelligence import (
    BrandActionRecord,
    BrandIntelligenceQuestion,
    BrandObjectLink,
    BrandPlatformAnswer,
    BrandReportVersion,
    BrandUserDecision,
)
from app.ontology import OntologyRegistry, load_default_ontology
from app.services.brand_ontology_action_planner_service import (
    BrandOntologyActionPlannerService,
)
from app.services.brand_ontology_governance_service import (
    BrandOntologyGovernanceService,
)
from app.services.brand_ontology_legacy_backfill_service import (
    BrandOntologyLegacyBackfillService,
)
from app.services.brand_ontology_object_service import BrandOntologyObjectService
from app.services.brand_knowledge_graph_projection_service import (
    BrandKnowledgeGraphProjectionService,
)
from app.services.brand_association_circle_variant import (
    AMWAY_ASSOCIATION_CENTER_TERMS,
    AMWAY_ASSOCIATION_DASHBOARD_VARIANT,
    BRAND_ASSOCIATION_CIRCLE_ANALYSIS_MODE,
    BRAND_ASSOCIATION_CIRCLE_REPORT_KIND,
    build_amway_association_context,
)
from app.tools.question_generation import complete_association_question_metadata
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

WORLD_OBJECT_TYPES: tuple[str, ...] = (
    "brand_entity",
    "official_website_asset",
    "competitor_entity",
    "audience_persona",
    "usage_scenario",
    "simulated_question",
    "question_set",
    "platform_answer",
    "brand_mention",
    "citation_source",
    "source_domain",
    "evidence_cluster",
    "metric_snapshot",
    "evidence_set",
    "intelligence_finding",
    "report_artifact",
    "monitoring_plan",
    "user_decision",
    "action_record",
)

DEFAULT_SAMPLE_LIMIT = 3
WORLD_SUMMARY_CACHE_TTL_SECONDS = 20
WORLD_SUMMARY_CACHE_MAX_ENTRIES = 64
DASHBOARD_WORLD_PROJECTION_VERSION = 8
REQUIRED_DASHBOARD_WORLD_PROJECTION_KEYS = (
    "summary_projection",
    "evidence_projection",
    "graph_projection",
    "recommendation_projection",
)
CORRUPTED_LABEL_RE = re.compile(r"[?]{3,}")
PHASE_LABELS: dict[str, str] = {
    "missing_brand": "缺少品牌",
    "brand_ready": "品牌已建档",
    "brand_context_ready": "品牌上下文已沉淀",
    "persona_ready": "画像已沉淀",
    "questions_generated": "问题已生成",
    "questions_confirmed": "问题已确认",
    "evidence_ready": "证据已捕获",
    "report_ready": "报告已形成",
    "operating_world": "持续运营中",
}
ACTION_READINESS_LABELS: dict[str, str] = {
    "ready": "系统可执行",
    "ready_with_defaults": "系统可执行",
    "needs_input": "待补信息",
    "needs_confirmation": "待确认",
    "blocked": "被阻止",
}
CORE_RELATIONSHIP_TYPES: frozenset[str] = frozenset(
    {
        "brand_has_intelligence_finding",
        "question_answered_by",
        "platform_answer_has_brand_mention",
        "brand_mention_mentions_brand",
        "brand_mention_mentions_competitor",
        "brand_mention_about_question",
        "platform_answer_cites_source",
        "evidence_set_contains_answer",
        "intelligence_finding_uses_evidence_set",
        "report_contains_intelligence_finding",
        "report_uses_evidence_set",
    }
)
LEGACY_ASSOCIATION_REPORT_TITLES: frozenset[str] = frozenset(
    {
        "Executive Summary｜先给结论",
        "这张圈层图怎么看",
        "战略词证据明细",
        "安利战略词逐项验证",
        "综合战略判断",
        "下一轮追踪建议",
    }
)
STORYLINE_ASSOCIATION_REPORT_SECTION_IDS: frozenset[str] = frozenset(
    {
        "core_verdict",
        "ai_archive",
        "value_pillars",
        "ai_blind_spot",
        "platform_difference",
        "data_to_action",
    }
)
CURRENT_ASSOCIATION_REPORT_SECTION_IDS: frozenset[str] = frozenset(
    {"living_young_autonomy"}
)
CURRENT_ASSOCIATION_REPORT_COPY_CONSTRAINT_VERSION = (
    "human_brand_diagnosis_v19_living_young_evidence_coverage"
)
_world_summary_cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}


def _relationship_visibility(link_type: str) -> str:
    return "core" if link_type in CORE_RELATIONSHIP_TYPES else "supporting"


def _association_report_sections_are_legacy(
    sections: list[dict[str, Any]],
) -> bool:
    titles = {
        str(section.get("title") or "").strip()
        for section in sections
        if isinstance(section, dict)
    }
    if titles & LEGACY_ASSOCIATION_REPORT_TITLES:
        return True

    section_ids = {
        str(section.get("section_id") or "").strip()
        for section in sections
        if isinstance(section, dict)
    }
    is_storyline_report = STORYLINE_ASSOCIATION_REPORT_SECTION_IDS.issubset(section_ids)
    return is_storyline_report and not CURRENT_ASSOCIATION_REPORT_SECTION_IDS.issubset(
        section_ids
    )


def _upgrade_legacy_association_report_projection(
    *,
    entity_id: UUID,
    latest_report: BrandReportVersion,
    brand_payload: dict[str, Any],
    center_terms: list[str],
    nodes: list[dict[str, Any]],
    evidence_samples: list[dict[str, Any]],
    question_bank: list[dict[str, Any]],
    platform_comparison: list[dict[str, Any]],
    association_actions: list[dict[str, Any]],
    sample_scope: dict[str, Any],
    question_definition: dict[str, Any],
    platform_source_summary: dict[str, Any],
    evidence_findings: list[dict[str, Any]],
    report_outline: list[dict[str, Any]],
    analysis_tool_trace: list[dict[str, Any]],
    source_appendix: list[dict[str, Any]],
    strategy_validation: list[dict[str, Any]],
    risk_map: dict[str, Any],
    fetch_results: list[dict[str, Any]] | None = None,
    tracking_projection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a current report projection from an old stored report payload.

    The stored evidence remains unchanged. This only prevents old report
    narrative sections from leaking into the Amway console when historical
    artifacts predate the storyline report contract.
    """

    from app.workflow.a5.association_circle import (
        build_brand_association_circle_report_artifact,
    )

    association_map = {
        "center_terms": center_terms,
        "nodes": nodes,
        "evidence_samples": evidence_samples,
        "question_bank": question_bank,
    }
    projection_payload = {
        "center_terms": center_terms,
        "nodes": nodes,
        "evidence_samples": evidence_samples,
        "question_bank": question_bank,
        "platform_comparison": platform_comparison,
        "association_actions": association_actions,
        "sample_scope": sample_scope,
        "question_definition": question_definition,
        "platform_source_summary": platform_source_summary,
        "evidence_findings": evidence_findings,
        "report_outline": report_outline,
        "analysis_tool_trace": analysis_tool_trace,
        "source_appendix": source_appendix,
        "strategy_validation": strategy_validation,
        "risk_map": risk_map,
        "tracking_projection": tracking_projection or {},
    }
    calibration_result = {
        "sample_scope": sample_scope,
        "association_map": association_map,
        "association_circle_projection": projection_payload,
        "report_input": {
            "question_scope": question_definition,
            "platform_scope": platform_source_summary,
            "association_map": association_map,
            "strategy_validation": strategy_validation,
            "risk_summary": risk_map,
            "evidence_findings": evidence_findings,
            "source_appendix": source_appendix,
            "association_actions": association_actions,
            "tracking_projection": tracking_projection or {},
        },
    }
    brand_name = str(
        brand_payload.get("label")
        or brand_payload.get("name")
        or (center_terms[0] if center_terms else "安利")
    )
    upgraded = build_brand_association_circle_report_artifact(
        session_id=str(getattr(latest_report, "session_id", None) or "dashboard"),
        entity_id=str(entity_id),
        brand_profile={
            "brand_name": brand_name,
            "official_website": brand_payload.get("domain"),
        },
        fetch_results=fetch_results or [],
        simulated_questions=question_bank,
        center_terms=center_terms,
        entity_calibration_result=calibration_result,
    )
    dashboard_projection = upgraded.get("dashboard_projection")
    dashboard_projection = (
        dashboard_projection if isinstance(dashboard_projection, dict) else {}
    )
    association_projection = dashboard_projection.get("association_circle_projection")
    return association_projection if isinstance(association_projection, dict) else {}


class BrandOntologyWorldService:
    """Builds a small, safe object-world packet for agent planning."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        registry: OntologyRegistry | None = None,
    ) -> None:
        self.db = db
        self.registry = registry or load_default_ontology()
        self.objects = BrandOntologyObjectService(db, registry=self.registry)
        self._snapshot_cache: dict[tuple[Any, ...], dict[str, Any] | None] = {}
        self._dashboard_summary_cache: dict[tuple[Any, ...], dict[str, Any] | None] = {}

    @staticmethod
    def invalidate_cache(entity_id: UUID | str | None = None) -> None:
        """Invalidate lightweight Dashboard world read-through cache."""

        if entity_id is None:
            _world_summary_cache.clear()
            return
        entity_key = str(entity_id)
        for cache_key in list(_world_summary_cache):
            if entity_key in {str(part) for part in cache_key[1:3]}:
                _world_summary_cache.pop(cache_key, None)

    async def build_snapshot(
        self,
        *,
        entity_id: UUID,
        sample_limit: int = DEFAULT_SAMPLE_LIMIT,
        include_action_input_values: bool = False,
        force_refresh: bool = False,
    ) -> dict[str, Any] | None:
        snapshot_cache_key = (
            str(entity_id),
            int(sample_limit or DEFAULT_SAMPLE_LIMIT),
            bool(include_action_input_values),
        )
        if not force_refresh and snapshot_cache_key in self._snapshot_cache:
            cached_snapshot = self._snapshot_cache[snapshot_cache_key]
            return deepcopy(cached_snapshot) if cached_snapshot is not None else None

        brand = await self.objects.get_object(
            entity_id=entity_id,
            object_type="brand_entity",
            object_id=str(entity_id),
        )
        if brand is None:
            self._snapshot_cache[snapshot_cache_key] = None
            return None

        object_summaries: list[dict[str, Any]] = []
        warnings: list[str] = []
        normalized_limit = min(max(int(sample_limit or DEFAULT_SAMPLE_LIMIT), 1), 10)
        for object_type in WORLD_OBJECT_TYPES:
            try:
                collection = await self.objects.list_objects(
                    entity_id=entity_id,
                    object_type=object_type,
                    limit=normalized_limit,
                    offset=0,
                )
            except Exception:
                warnings.append(f"{object_type}: read_failed")
                await self._recover_read_failure()
                continue

            definition = self.registry.require_object_type(object_type)
            objects = list(collection.get("objects") or [])
            sample_lifecycle_counts = Counter(
                str((item.get("lifecycle") or {}).get("status") or "unknown")
                for item in objects
            )
            try:
                lifecycle_counts = await self.objects.count_lifecycle_statuses(
                    entity_id=entity_id,
                    object_type=object_type,
                )
            except Exception:
                warnings.append(f"{object_type}.lifecycle_counts: read_failed")
                await self._recover_read_failure()
                lifecycle_counts = dict(sample_lifecycle_counts)
            object_summaries.append(
                {
                    "object_type": object_type,
                    "display_name": _world_object_display_name(
                        object_type,
                        definition.display_name,
                    ),
                    "total": int(collection.get("total") or 0),
                    "lifecycle_counts": lifecycle_counts,
                    "sample_lifecycle_counts": dict(sample_lifecycle_counts),
                    "samples": [
                        {
                            "object_id": item.get("object_id"),
                            "label": _object_label(item, object_type=object_type),
                            "lifecycle": (item.get("lifecycle") or {}).get("status"),
                        }
                        for item in objects
                    ],
                }
            )

        relationship_counts: dict[str, int] = {}
        try:
            relationship_rows = (
                await self.db.execute(
                    select(BrandObjectLink.link_type, func.count())
                    .where(BrandObjectLink.entity_id == entity_id)
                    .group_by(BrandObjectLink.link_type)
                )
            ).all()
            for link_type, count in relationship_rows:
                normalized_link_type = str(link_type or "")
                if normalized_link_type:
                    relationship_counts[normalized_link_type] = int(count or 0)
        except Exception:
            warnings.append("object_links: read_failed")
            await self._recover_read_failure()

        try:
            finding_feedback_summary = await self._finding_feedback_summary(
                entity_id=entity_id,
            )
        except Exception:
            warnings.append("finding_feedback_summary: read_failed")
            await self._recover_read_failure()
            finding_feedback_summary = _empty_finding_feedback_summary()
        try:
            action_feedback_summary = await self._action_feedback_summary(
                entity_id=entity_id,
                include_input_values=include_action_input_values,
            )
        except Exception:
            warnings.append("action_feedback_summary: read_failed")
            await self._recover_read_failure()
            action_feedback_summary = _empty_action_feedback_summary()
        brand_payload = {
            "object_id": brand.get("object_id"),
            "label": _object_label(brand, object_type="brand_entity"),
            "lifecycle": (brand.get("lifecycle") or {}).get("status"),
        }
        snapshot = {
            "entity_id": str(entity_id),
            "brand": brand_payload,
            "entity": brand_payload,
            "object_summaries": object_summaries,
            "relationship_counts": relationship_counts,
            "available_actions": [
                {
                    "key": action.key,
                    "display_name": action.display_name,
                    "permission_scope": action.permission_scope,
                    "requires_confirmation": action.requires_confirmation,
                }
                for action in self.registry.action_types
            ],
            "finding_feedback_summary": finding_feedback_summary,
            "action_feedback_summary": action_feedback_summary,
            "warnings": warnings,
        }
        snapshot["governance_report"] = await BrandOntologyGovernanceService(
            self.db,
            registry=self.registry,
        ).build_report(
            entity_id=entity_id,
            snapshot=snapshot,
            audit_links=False,
        )
        self._snapshot_cache[snapshot_cache_key] = deepcopy(snapshot)
        return snapshot

    async def ensure_legacy_backfill(
        self,
        *,
        entity_id: UUID,
        force: bool = False,
    ) -> dict[str, Any]:
        """Project older analysis data before reading a Dashboard world."""

        return await BrandOntologyLegacyBackfillService(self.db).run(
            entity_id=entity_id,
            force=force,
        )

    async def build_dashboard_summary(
        self,
        *,
        entity_id: UUID,
        actor_id: UUID | None = None,
        sample_limit: int = DEFAULT_SAMPLE_LIMIT,
        include_action_input_values: bool = False,
        include_official_content_audit: bool = True,
        force_refresh: bool = False,
    ) -> dict[str, Any] | None:
        """Build the Dashboard-facing brand object world summary."""

        cache_key = (
            "dashboard",
            DASHBOARD_WORLD_PROJECTION_VERSION,
            str(entity_id),
            str(actor_id) if actor_id else "",
            int(sample_limit or DEFAULT_SAMPLE_LIMIT),
            bool(include_action_input_values),
            bool(include_official_content_audit),
        )
        if not force_refresh:
            instance_cached = self._dashboard_summary_cache.get(cache_key)
            if _dashboard_summary_cache_is_current(instance_cached):
                return (
                    deepcopy(instance_cached) if instance_cached is not None else None
                )
            if instance_cached is not None:
                self._dashboard_summary_cache.pop(cache_key, None)
            shared_cached = _read_world_summary_cache(cache_key)
            if shared_cached is not None:
                self._dashboard_summary_cache[cache_key] = deepcopy(shared_cached)
                return shared_cached

        snapshot = await self.build_snapshot(
            entity_id=entity_id,
            sample_limit=sample_limit,
            include_action_input_values=include_action_input_values,
            force_refresh=force_refresh,
        )
        if snapshot is None:
            self._dashboard_summary_cache[cache_key] = None
            return None
        evidence_summary = await self.objects.build_evidence_summary(
            entity_id=entity_id,
            include_content_audit=include_official_content_audit,
        )
        snapshot_for_plan = {
            **snapshot,
            "official_website_observation": evidence_summary.get(
                "official_website_observation"
            ),
        }
        action_plan = BrandOntologyActionPlannerService(
            registry=self.registry,
        ).build_plan(
            ontology_world=snapshot_for_plan,
            state={
                "brand_entity_id": str(entity_id),
                **({"actor_id": str(actor_id)} if actor_id else {}),
            },
        )
        relationship_counts = snapshot.get("relationship_counts") or {}
        intelligence_findings = await self._latest_intelligence_findings(
            entity_id=entity_id,
        )
        governance_report = await BrandOntologyGovernanceService(
            self.db,
            registry=self.registry,
        ).build_report(
            entity_id=entity_id,
            snapshot=snapshot,
            action_plan=action_plan,
            audit_links=True,
        )
        action_queue = _action_queue_from_plan(
            action_plan,
            snapshot.get("action_feedback_summary"),
        )
        world_phase = (
            action_plan.get("world_phase") if isinstance(action_plan, dict) else None
        )
        core_relationships, supporting_relationships = _split_relationship_summary(
            self._relationship_summary(
                relationship_counts,
            )
        )
        graph_projections = await BrandKnowledgeGraphProjectionService(self.db).build(
            entity_id=entity_id,
            action_queue=action_queue,
        )
        association_circle_projection = await self._association_circle_projection(
            entity_id=entity_id,
            snapshot=snapshot,
        )
        dashboard_summary = {
            **snapshot,
            "projection_version": DASHBOARD_WORLD_PROJECTION_VERSION,
            "governance_report": governance_report,
            "relationship_summary": core_relationships,
            "supporting_relationship_summary": supporting_relationships,
            "intelligence_findings": intelligence_findings,
            **evidence_summary,
            **graph_projections,
            "action_queue": action_queue,
            "world_phase": world_phase,
            "gaps": (action_plan.get("gaps") if isinstance(action_plan, dict) else []),
            "task_flow": _task_flow_summary(
                snapshot=snapshot,
                action_queue=action_queue,
                world_phase=world_phase,
            ),
        }
        if association_circle_projection:
            dashboard_summary["dashboard_variant"] = association_circle_projection.get(
                "dashboard_variant"
            )
            dashboard_summary["analysis_mode"] = association_circle_projection.get(
                "analysis_mode"
            )
            dashboard_summary["center_terms"] = association_circle_projection.get(
                "center_terms"
            )
            dashboard_summary["association_circle_projection"] = (
                association_circle_projection
            )
            dashboard_summary["recommendation_projection"] = (
                _merge_association_actions_into_recommendations(
                    dashboard_summary.get("recommendation_projection"),
                    association_circle_projection.get("association_actions"),
                )
            )
        self._dashboard_summary_cache[cache_key] = deepcopy(dashboard_summary)
        _write_world_summary_cache(cache_key, dashboard_summary)
        return dashboard_summary

    async def build_association_circle_dashboard_summary(
        self,
        *,
        entity_id: UUID,
        entity_name: str | None = None,
        entity_domain: str | None = None,
        entity_aliases: list[Any] | tuple[Any, ...] | None = None,
    ) -> dict[str, Any] | None:
        """Build the light Dashboard world payload needed by the Amway Console."""

        variant_context = build_amway_association_context(
            name=entity_name,
            domain=entity_domain,
            aliases=entity_aliases,
        )
        if not variant_context:
            return None

        brand = {
            "id": str(entity_id),
            "label": entity_name or "Amway",
            "domain": entity_domain,
            "aliases": list(entity_aliases or []),
        }
        projection = await self._association_circle_projection(
            entity_id=entity_id,
            snapshot={"brand": brand},
        )
        if projection is None:
            return None

        recommendation_projection = _merge_association_actions_into_recommendations(
            {
                "recommendations": [],
                "sample_status": {"status": projection.get("status")},
            },
            projection.get("association_actions"),
        )
        sample_scope = projection.get("sample_scope")
        sample_scope = sample_scope if isinstance(sample_scope, dict) else {}
        return {
            "projection_version": DASHBOARD_WORLD_PROJECTION_VERSION,
            "brand": brand,
            "dashboard_variant": projection.get("dashboard_variant")
            or AMWAY_ASSOCIATION_DASHBOARD_VARIANT,
            "analysis_mode": projection.get("analysis_mode")
            or BRAND_ASSOCIATION_CIRCLE_ANALYSIS_MODE,
            "report_kind": projection.get("report_kind")
            or BRAND_ASSOCIATION_CIRCLE_REPORT_KIND,
            "center_terms": projection.get("center_terms")
            or variant_context.get("center_terms")
            or list(AMWAY_ASSOCIATION_CENTER_TERMS),
            "enabled_surfaces": variant_context.get("enabled_surfaces") or [],
            "association_circle_projection": projection,
            "summary_projection": {
                "brand": brand,
                "sample_scope": sample_scope,
            },
            "evidence_projection": {
                "samples": projection.get("evidence_samples") or [],
            },
            "graph_projection": {
                "nodes": projection.get("nodes") or [],
            },
            "recommendation_projection": recommendation_projection,
            "action_queue": [],
            "task_flow": {
                "stage": projection.get("status") or "not_generated",
            },
        }

    async def _fetch_results_for_association_report(
        self,
        *,
        entity_id: UUID,
        latest_report: BrandReportVersion,
        question_bank: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        session_id = getattr(latest_report, "session_id", None)
        question_lookup: dict[str, dict[str, Any]] = {}
        for index, item in enumerate(question_bank, start=1):
            if not isinstance(item, dict):
                continue
            question_id = str(item.get("id") or item.get("question_id") or "").strip()
            if not question_id:
                question_id = f"q_{index:03d}"
            question_lookup[question_id] = item

        async def load_answers(use_session: bool) -> list[BrandPlatformAnswer]:
            query = select(BrandPlatformAnswer).where(
                BrandPlatformAnswer.entity_id == entity_id
            )
            if use_session and session_id is not None:
                query = query.where(BrandPlatformAnswer.session_id == session_id)
            query = query.order_by(
                BrandPlatformAnswer.question_id,
                BrandPlatformAnswer.platform,
                BrandPlatformAnswer.captured_at,
            )
            result = await self.db.execute(query)
            return list(result.scalars().all())

        try:
            answers = await load_answers(use_session=True)
            if not answers and session_id is not None:
                answers = await load_answers(use_session=False)
        except Exception:
            await self._recover_read_failure()
            return []

        grouped: dict[str, dict[str, Any]] = {}
        for answer in answers:
            question_id = str(getattr(answer, "question_id", "") or "").strip()
            if not question_id:
                question_id = f"answer_question_{len(grouped) + 1:03d}"
            question_payload = question_lookup.get(question_id, {})
            question_text = str(
                question_payload.get("text")
                or question_payload.get("question")
                or question_payload.get("question_text")
                or question_id
            ).strip()
            row = grouped.setdefault(
                question_id,
                {
                    "question_id": question_id,
                    "question_text": question_text,
                    "question": question_text,
                    "platform_results": [],
                    "audience_segment": question_payload.get("audience_segment"),
                    "core_anxiety": question_payload.get("core_anxiety"),
                    "life_scene": question_payload.get("life_scene"),
                    "opportunity_point": question_payload.get("opportunity_point"),
                    "probe_type": question_payload.get("probe_type"),
                    "mother_theme": question_payload.get("mother_theme"),
                    "question_type": question_payload.get("question_type"),
                },
            )
            answer_text = str(getattr(answer, "answer_text", "") or "").strip()
            row["platform_results"].append(
                {
                    "platform": str(getattr(answer, "platform", "") or "").strip(),
                    "success": bool(getattr(answer, "success", False))
                    and bool(answer_text),
                    "answer": {"content": answer_text},
                    "answer_text": answer_text,
                }
            )
        return list(grouped.values())

    async def _association_circle_projection(
        self,
        *,
        entity_id: UUID,
        snapshot: dict[str, Any],
    ) -> dict[str, Any] | None:
        brand_payload = snapshot.get("brand") if isinstance(snapshot, dict) else {}
        brand_payload = brand_payload if isinstance(brand_payload, dict) else {}
        variant_context = build_amway_association_context(
            name=brand_payload.get("label"),
        )
        latest_report: BrandReportVersion | None = None
        try:
            latest_report = (
                await self.db.execute(
                    select(BrandReportVersion)
                    .where(
                        BrandReportVersion.entity_id == entity_id,
                        BrandReportVersion.report_kind
                        == BRAND_ASSOCIATION_CIRCLE_REPORT_KIND,
                    )
                    .order_by(
                        desc(BrandReportVersion.updated_at),
                        desc(BrandReportVersion.version),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
        except Exception:
            await self._recover_read_failure()
            latest_report = None

        if latest_report is None and not variant_context:
            return None

        payload = (
            latest_report.payload
            if latest_report is not None and isinstance(latest_report.payload, dict)
            else {}
        )
        dashboard_projection = payload.get("dashboard_projection")
        dashboard_projection = (
            dashboard_projection if isinstance(dashboard_projection, dict) else {}
        )
        raw_circle_projection = dashboard_projection.get(
            "association_circle_projection"
        )
        raw_circle_projection = (
            raw_circle_projection if isinstance(raw_circle_projection, dict) else {}
        )
        association_circle = payload.get("association_circle")
        association_circle = (
            association_circle if isinstance(association_circle, dict) else {}
        )
        nodes = raw_circle_projection.get("nodes")
        if not isinstance(nodes, list):
            nodes = association_circle.get("nodes")
        evidence_samples = raw_circle_projection.get("evidence_samples")
        if not isinstance(evidence_samples, list):
            evidence_samples = association_circle.get("evidence_samples")
        association_evidence_samples = association_circle.get("evidence_samples")
        if isinstance(association_evidence_samples, list) and (
            not isinstance(evidence_samples, list)
            or len(association_evidence_samples) > len(evidence_samples)
        ):
            evidence_samples = association_evidence_samples
        question_bank = raw_circle_projection.get("question_bank")
        if not isinstance(question_bank, list):
            question_bank = payload.get("question_bank")
        if not isinstance(question_bank, list):
            question_bank = association_circle.get("question_bank")
        platform_comparison = payload.get("platform_comparison")
        if not isinstance(platform_comparison, list):
            platform_comparison = []
        association_actions = payload.get("association_actions")
        if not isinstance(association_actions, list):
            association_actions = raw_circle_projection.get("association_actions")
        if not isinstance(association_actions, list):
            association_actions = []
        sample_scope = payload.get("sample_scope")
        sample_scope = sample_scope if isinstance(sample_scope, dict) else {}
        executive_summary = payload.get("executive_summary")
        executive_summary = (
            executive_summary if isinstance(executive_summary, dict) else {}
        )
        report_narrative_sections = raw_circle_projection.get(
            "report_narrative_sections"
        )
        if not isinstance(report_narrative_sections, list):
            report_narrative_sections = payload.get("report_narrative_sections")
        if not isinstance(report_narrative_sections, list):
            report_narrative_sections = []
        question_definition = raw_circle_projection.get("question_definition")
        if not isinstance(question_definition, dict):
            question_definition = payload.get("question_definition")
        question_definition = (
            question_definition if isinstance(question_definition, dict) else {}
        )
        platform_source_summary = raw_circle_projection.get(
            "platform_source_summary"
        )
        if not isinstance(platform_source_summary, dict):
            platform_source_summary = payload.get("platform_source_summary")
        platform_source_summary = (
            platform_source_summary
            if isinstance(platform_source_summary, dict)
            else {}
        )
        evidence_findings = raw_circle_projection.get("evidence_findings")
        if not isinstance(evidence_findings, list):
            evidence_findings = payload.get("evidence_findings")
        payload_evidence_findings = payload.get("evidence_findings")
        if isinstance(payload_evidence_findings, list) and (
            not isinstance(evidence_findings, list)
            or len(payload_evidence_findings) > len(evidence_findings)
        ):
            evidence_findings = payload_evidence_findings
        if not isinstance(evidence_findings, list):
            evidence_findings = []
        report_outline = raw_circle_projection.get("report_outline")
        if not isinstance(report_outline, list):
            report_outline = payload.get("report_outline")
        if not isinstance(report_outline, list):
            report_outline = []
        analysis_tool_trace = raw_circle_projection.get("analysis_tool_trace")
        if not isinstance(analysis_tool_trace, list):
            analysis_tool_trace = payload.get("analysis_tool_trace")
        if not isinstance(analysis_tool_trace, list):
            analysis_tool_trace = []
        source_appendix = raw_circle_projection.get("source_appendix")
        if not isinstance(source_appendix, list):
            source_appendix = payload.get("source_appendix")
        payload_source_appendix = payload.get("source_appendix")
        if isinstance(payload_source_appendix, list) and (
            not isinstance(source_appendix, list)
            or len(payload_source_appendix) > len(source_appendix)
        ):
            source_appendix = payload_source_appendix
        if not isinstance(source_appendix, list):
            source_appendix = []
        report_quality_checks = raw_circle_projection.get("report_quality_checks")
        if not isinstance(report_quality_checks, dict):
            report_quality_checks = payload.get("report_quality_checks")
        report_quality_checks = (
            report_quality_checks if isinstance(report_quality_checks, dict) else {}
        )
        copy_constraints = raw_circle_projection.get("copy_constraints")
        if not isinstance(copy_constraints, dict):
            copy_constraints = payload.get("copy_constraints")
        copy_constraints = (
            copy_constraints if isinstance(copy_constraints, dict) else {}
        )
        strategy_validation = raw_circle_projection.get("strategy_validation")
        if not isinstance(strategy_validation, list):
            strategy_validation = payload.get("strategy_validation")
        strategy_validation = (
            strategy_validation if isinstance(strategy_validation, list) else []
        )
        risk_map = raw_circle_projection.get("risk_map")
        if not isinstance(risk_map, dict):
            risk_map = payload.get("risk_summary")
        risk_map = risk_map if isinstance(risk_map, dict) else {}
        generated_from = raw_circle_projection.get("generated_from")
        if not isinstance(generated_from, str) or not generated_from.strip():
            generated_from = payload.get("generated_from")
        generated_from = (
            generated_from
            if isinstance(generated_from, str) and generated_from.strip()
            else None
        )
        center_terms = (
            (variant_context or {}).get("center_terms")
            or payload.get("center_terms")
            or raw_circle_projection.get("center_terms")
            or list(AMWAY_ASSOCIATION_CENTER_TERMS)
        )
        if not isinstance(center_terms, list):
            center_terms = list(AMWAY_ASSOCIATION_CENTER_TERMS)
        nodes = nodes if isinstance(nodes, list) else []
        evidence_samples = (
            evidence_samples if isinstance(evidence_samples, list) else []
        )
        question_bank = question_bank if isinstance(question_bank, list) else []
        if not question_bank and evidence_samples:
            question_bank = await self._latest_question_bank_for_entity(entity_id)
        if not question_bank and evidence_samples:
            question_bank = _question_bank_from_evidence_samples(evidence_samples)
        if (
            latest_report is not None
            and nodes
            and (
                not report_narrative_sections
                or _association_report_sections_are_legacy(report_narrative_sections)
                or str(copy_constraints.get("version") or "").strip()
                != CURRENT_ASSOCIATION_REPORT_COPY_CONSTRAINT_VERSION
            )
        ):
            try:
                full_fetch_results = await self._fetch_results_for_association_report(
                    entity_id=entity_id,
                    latest_report=latest_report,
                    question_bank=question_bank,
                )
                upgraded_projection = _upgrade_legacy_association_report_projection(
                    entity_id=entity_id,
                    latest_report=latest_report,
                    brand_payload=brand_payload,
                    center_terms=center_terms,
                    nodes=nodes,
                    evidence_samples=evidence_samples,
                    question_bank=question_bank,
                    platform_comparison=platform_comparison,
                    association_actions=association_actions,
                    sample_scope=sample_scope,
                    question_definition=question_definition,
                    platform_source_summary=platform_source_summary,
                    evidence_findings=evidence_findings,
                    report_outline=report_outline,
                    analysis_tool_trace=analysis_tool_trace,
                    source_appendix=source_appendix,
                    strategy_validation=strategy_validation,
                    risk_map=risk_map,
                    fetch_results=full_fetch_results,
                    tracking_projection=raw_circle_projection.get(
                        "tracking_projection"
                    )
                    if isinstance(
                        raw_circle_projection.get("tracking_projection"),
                        dict,
                    )
                    else payload.get("tracking_projection")
                    if isinstance(payload.get("tracking_projection"), dict)
                    else {},
                )
            except Exception:
                upgraded_projection = {}
            if upgraded_projection:
                report_narrative_sections = (
                    upgraded_projection.get("report_narrative_sections")
                    if isinstance(
                        upgraded_projection.get("report_narrative_sections"),
                        list,
                    )
                    else report_narrative_sections
                )
                question_definition = (
                    upgraded_projection.get("question_definition")
                    if isinstance(upgraded_projection.get("question_definition"), dict)
                    else question_definition
                )
                platform_source_summary = (
                    upgraded_projection.get("platform_source_summary")
                    if isinstance(
                        upgraded_projection.get("platform_source_summary"),
                        dict,
                    )
                    else platform_source_summary
                )
                evidence_findings = (
                    upgraded_projection.get("evidence_findings")
                    if isinstance(upgraded_projection.get("evidence_findings"), list)
                    else evidence_findings
                )
                report_outline = (
                    upgraded_projection.get("report_outline")
                    if isinstance(upgraded_projection.get("report_outline"), list)
                    else report_outline
                )
                analysis_tool_trace = (
                    upgraded_projection.get("analysis_tool_trace")
                    if isinstance(upgraded_projection.get("analysis_tool_trace"), list)
                    else analysis_tool_trace
                )
                source_appendix = (
                    upgraded_projection.get("source_appendix")
                    if isinstance(upgraded_projection.get("source_appendix"), list)
                    else source_appendix
                )
                report_quality_checks = (
                    upgraded_projection.get("report_quality_checks")
                    if isinstance(
                        upgraded_projection.get("report_quality_checks"),
                        dict,
                    )
                    else report_quality_checks
                )
                copy_constraints = (
                    upgraded_projection.get("copy_constraints")
                    if isinstance(upgraded_projection.get("copy_constraints"), dict)
                    else copy_constraints
                )
        status = "not_generated"
        if latest_report is not None:
            status = "sample_limited" if len(nodes) == 0 else "ready"
        projection_nodes = _association_projection_nodes_with_risk(
            nodes=nodes,
            risk_map=risk_map,
            non_risk_limit=80,
            total_limit=110,
        )
        return {
            "dashboard_variant": (
                (variant_context or {}).get("dashboard_variant")
                or AMWAY_ASSOCIATION_DASHBOARD_VARIANT
            ),
            "analysis_mode": BRAND_ASSOCIATION_CIRCLE_ANALYSIS_MODE,
            "report_kind": BRAND_ASSOCIATION_CIRCLE_REPORT_KIND,
            "status": status,
            "center_terms": center_terms,
            "nodes": projection_nodes,
            "evidence_samples": _prioritize_association_evidence_for_nodes(
                projection_nodes,
                evidence_samples,
                limit=80,
            ),
            "question_bank": question_bank[:200],
            "platform_comparison": platform_comparison[:20],
            "association_actions": association_actions[:20],
            "strategy_validation": strategy_validation[:80],
            "risk_map": risk_map,
            "generated_from": generated_from,
            "report_narrative_sections": report_narrative_sections[:20],
            "question_definition": question_definition,
            "platform_source_summary": platform_source_summary,
            "evidence_findings": _prioritize_association_findings_for_nodes(
                projection_nodes,
                evidence_findings,
                limit=50,
            ),
            "report_outline": report_outline[:20],
            "analysis_tool_trace": analysis_tool_trace[:20],
            "source_appendix": _diversify_association_source_appendix(
                source_appendix,
                limit=80,
            ),
            "report_quality_checks": report_quality_checks,
            "copy_constraints": copy_constraints,
            "sample_scope": sample_scope,
            "executive_summary": executive_summary,
            "report_id": latest_report.report_id if latest_report else None,
            "artifact_id": latest_report.artifact_id if latest_report else None,
            "updated_at": (
                latest_report.updated_at.isoformat() if latest_report else None
            ),
        }

    async def _latest_question_bank_for_entity(
        self,
        entity_id: UUID,
    ) -> list[dict[str, Any]]:
        try:
            result = await self.db.execute(
                select(BrandIntelligenceQuestion)
                .where(BrandIntelligenceQuestion.entity_id == entity_id)
                .order_by(
                    desc(BrandIntelligenceQuestion.updated_at),
                    desc(BrandIntelligenceQuestion.created_at),
                )
                .limit(200)
            )
            rows = list(result.scalars().all())
        except Exception:
            await self._recover_read_failure()
            return []
        if not rows:
            return []
        latest_session_id = rows[0].session_id
        if latest_session_id is not None:
            rows = [row for row in rows if row.session_id == latest_session_id]
        rows.sort(key=lambda row: str(row.question_id or ""))
        return _question_bank_from_brand_questions(rows)

    def _relationship_summary(
        self,
        relationship_counts: dict[str, int],
    ) -> list[dict[str, Any]]:
        summary: list[dict[str, Any]] = []
        for link_type, count in sorted(relationship_counts.items()):
            definition = self.registry.get_link_type(link_type)
            visibility = _relationship_visibility(link_type)
            summary.append(
                {
                    "link_type": link_type,
                    "display_name": (
                        definition.display_name if definition else link_type
                    ),
                    "from_object": (definition.from_object if definition else None),
                    "to_object": (definition.to_object if definition else None),
                    "count": int(count or 0),
                    "visibility": visibility,
                    "default_visible": visibility == "core",
                }
            )
        return summary

    async def _latest_intelligence_findings(
        self,
        *,
        entity_id: UUID,
    ) -> list[dict[str, Any]]:
        try:
            collection = await self.objects.list_objects(
                entity_id=entity_id,
                object_type="intelligence_finding",
                limit=4,
                offset=0,
                sort="updated_at_desc",
            )
        except Exception:
            return []

        findings: list[dict[str, Any]] = []
        for item in collection.get("objects") or []:
            if not isinstance(item, dict):
                continue
            properties = item.get("properties") or {}
            if not isinstance(properties, dict):
                properties = {}
            findings.append(
                {
                    "object_id": item.get("object_id"),
                    "title": _compact(
                        str(properties.get("title") or "未命名情报判断"),
                        limit=96,
                    ),
                    "summary": _compact(str(properties.get("summary") or ""), 240),
                    "finding_type": properties.get("finding_type") or "observation",
                    "severity": properties.get("severity") or "medium",
                    "confidence": properties.get("confidence"),
                    "status": (item.get("lifecycle") or {}).get("status"),
                    "evidence_summary": _compact(
                        str(properties.get("evidence_summary") or ""),
                        180,
                    ),
                    "supporting_question_count": int(
                        properties.get("supporting_question_count") or 0
                    ),
                    "supporting_answer_count": int(
                        properties.get("supporting_answer_count") or 0
                    ),
                    "supporting_citation_count": int(
                        properties.get("supporting_citation_count") or 0
                    ),
                    "suggested_action_type": (
                        properties.get("suggested_action_type") or ""
                    ),
                    "updated_at": properties.get("updated_at"),
                }
            )
        return findings

    async def _recover_read_failure(self) -> None:
        try:
            await self.db.rollback()
        except Exception:
            return

    async def _finding_feedback_summary(
        self,
        *,
        entity_id: UUID,
    ) -> dict[str, Any]:
        rows = (
            (
                await self.db.execute(
                    select(BrandUserDecision)
                    .where(
                        BrandUserDecision.entity_id == entity_id,
                        BrandUserDecision.target_object_type == "intelligence_finding",
                    )
                    .order_by(desc(BrandUserDecision.decided_at))
                    .limit(20)
                )
            )
            .scalars()
            .all()
        )
        by_type: Counter[str] = Counter()
        latest: list[dict[str, Any]] = []
        correction_count = 0
        correction_without_text_count = 0
        dismissed_count = 0
        validated_count = 0
        for row in rows:
            feedback_type = _normalize_feedback_type(row.decision_type)
            by_type[feedback_type] += 1
            if feedback_type == "correct":
                correction_count += 1
                if not str(row.feedback_text or "").strip():
                    correction_without_text_count += 1
            elif feedback_type == "dismiss":
                dismissed_count += 1
            elif feedback_type == "validate":
                validated_count += 1
            latest.append(
                {
                    "decision_id": str(row.id),
                    "finding_id": row.target_object_id,
                    "feedback_type": feedback_type,
                    "status": row.status,
                    "has_feedback_text": bool(str(row.feedback_text or "").strip()),
                    "decided_at": row.decided_at.isoformat(),
                }
            )
        return {
            "total": len(rows),
            "by_feedback_type": dict(by_type),
            "validated_count": validated_count,
            "dismissed_count": dismissed_count,
            "correction_count": correction_count,
            "correction_without_text_count": correction_without_text_count,
            "latest": latest[:5],
        }

    async def _action_feedback_summary(
        self,
        *,
        entity_id: UUID,
        include_input_values: bool = False,
    ) -> dict[str, Any]:
        rows = (
            (
                await self.db.execute(
                    select(BrandUserDecision)
                    .where(
                        BrandUserDecision.entity_id == entity_id,
                        BrandUserDecision.decision_type
                        == "ontology_action_queue_feedback",
                    )
                    .order_by(desc(BrandUserDecision.decided_at))
                    .limit(50)
                )
            )
            .scalars()
            .all()
        )
        by_type: Counter[str] = Counter()
        latest: list[dict[str, Any]] = []
        latest_by_action: dict[str, dict[str, Any]] = {}
        feedback_action_ids = [
            row.action_record_id for row in rows if row.action_record_id is not None
        ]
        consumed_by_parent: dict[str, BrandActionRecord] = {}
        if feedback_action_ids:
            child_rows = (
                (
                    await self.db.execute(
                        select(BrandActionRecord)
                        .where(
                            BrandActionRecord.parent_action_record_id.in_(
                                feedback_action_ids
                            )
                        )
                        .order_by(desc(BrandActionRecord.submitted_at))
                    )
                )
                .scalars()
                .all()
            )
            for child in child_rows:
                parent_id = str(child.parent_action_record_id or "")
                if parent_id and parent_id not in consumed_by_parent:
                    consumed_by_parent[parent_id] = child
        for row in rows:
            action_key, fallback_feedback_type = _parse_action_feedback_key(
                row.decision_key,
            )
            payload = row.input_payload if isinstance(row.input_payload, dict) else {}
            action_key = str(payload.get("target_action_key") or action_key).strip()
            feedback_type = _normalize_action_feedback_type(
                payload.get("feedback_type") or fallback_feedback_type
            )
            if not action_key:
                continue
            by_type[feedback_type] += 1
            consumed_child = consumed_by_parent.get(str(row.action_record_id or ""))
            consumed_at = (
                consumed_child.completed_at or consumed_child.submitted_at
                if consumed_child is not None
                else None
            )
            provided_inputs = (
                payload.get("provided_inputs")
                if isinstance(payload.get("provided_inputs"), dict)
                else {}
            )
            item = {
                "decision_id": str(row.id),
                "action_record_id": (
                    str(row.action_record_id) if row.action_record_id else None
                ),
                "action_key": action_key,
                "feedback_type": feedback_type,
                "status": row.status,
                "has_feedback_text": bool(str(row.feedback_text or "").strip()),
                "decided_at": row.decided_at.isoformat(),
                "consumed_by_action_record_id": (
                    str(consumed_child.id) if consumed_child is not None else None
                ),
                "consumed_by_action_type": (
                    consumed_child.action_type if consumed_child is not None else None
                ),
                "consumed_at": consumed_at.isoformat() if consumed_at else None,
                "provided_input_keys": sorted(str(key) for key in provided_inputs),
            }
            if include_input_values and provided_inputs:
                item["provided_inputs"] = provided_inputs
            latest.append(item)
            latest_by_action.setdefault(action_key, item)
        return {
            "total": len(latest),
            "by_feedback_type": dict(by_type),
            "latest": latest[:10],
            "latest_by_action": latest_by_action,
        }


def _empty_finding_feedback_summary() -> dict[str, Any]:
    return {
        "total": 0,
        "by_feedback_type": {},
        "validated_count": 0,
        "dismissed_count": 0,
        "correction_count": 0,
        "correction_without_text_count": 0,
        "latest": [],
    }


def _empty_action_feedback_summary() -> dict[str, Any]:
    return {
        "total": 0,
        "by_feedback_type": {},
        "latest": [],
        "latest_by_action": {},
    }


def _read_world_summary_cache(cache_key: tuple[Any, ...]) -> dict[str, Any] | None:
    cached = _world_summary_cache.get(cache_key)
    if cached is None:
        return None
    cached_at, payload = cached
    if time.time() - cached_at > WORLD_SUMMARY_CACHE_TTL_SECONDS:
        _world_summary_cache.pop(cache_key, None)
        return None
    if not _dashboard_summary_cache_is_current(payload):
        _world_summary_cache.pop(cache_key, None)
        return None
    return deepcopy(payload)


def _write_world_summary_cache(
    cache_key: tuple[Any, ...],
    payload: dict[str, Any],
) -> None:
    if len(_world_summary_cache) >= WORLD_SUMMARY_CACHE_MAX_ENTRIES:
        oldest_key = min(
            _world_summary_cache.items(),
            key=lambda item: item[1][0],
        )[0]
        _world_summary_cache.pop(oldest_key, None)
    _world_summary_cache[cache_key] = (time.time(), deepcopy(payload))


def _association_action_to_recommendation(action: dict[str, Any]) -> dict[str, Any]:
    node_term = str(action.get("node_term") or "圈层节点")
    action_label = str(action.get("action_label") or "圈层行动")
    return {
        "id": str(action.get("id") or f"association_action_{node_term}"),
        "title": str(action.get("title") or f"{action_label}：{node_term}"),
        "target_metric": "brand_association_circle",
        "reason": str(action.get("reason") or ""),
        "impact": str(action.get("expected_impact") or ""),
        "expected_impact": str(action.get("expected_impact") or ""),
        "review_criteria": str(action.get("review_criteria") or ""),
        "priority": str(action.get("priority") or "medium"),
        "next_action": "ask_chat",
        "cta_label": "生成追问",
        "content_brief": str(action.get("next_question_suggestion") or ""),
        "content_format": "圈层行动",
        "execution_steps": list(action.get("execution_steps") or [])[:5],
        "evidence_refs": list(action.get("evidence_refs") or [])[:8],
        "content_directions": [
            {
                "title": action_label,
                "angle": node_term,
                "evidence": str(action.get("business_tag") or ""),
            }
        ],
    }


def _merge_association_actions_into_recommendations(
    recommendation_projection: Any,
    association_actions: Any,
) -> dict[str, Any]:
    projection = (
        deepcopy(recommendation_projection)
        if isinstance(recommendation_projection, dict)
        else {}
    )
    recommendations = projection.get("recommendations")
    if not isinstance(recommendations, list):
        recommendations = []
    if not isinstance(projection.get("sample_status"), dict):
        projection["sample_status"] = {
            "is_ready": bool(association_actions),
            "status": "ready" if association_actions else "needs_answer_samples",
            "status_label": "圈层行动可跟进" if association_actions else "等待圈层样本",
            "reason": (
                "已根据品牌联想圈层生成跟进行动。"
                if association_actions
                else "需要先抓取回答并生成圈层报告。"
            ),
        }

    seen_ids = {
        str(item.get("id")) for item in recommendations if isinstance(item, dict)
    }
    for action in association_actions or []:
        if not isinstance(action, dict):
            continue
        item = _association_action_to_recommendation(action)
        if item["id"] in seen_ids:
            continue
        recommendations.append(item)
        seen_ids.add(item["id"])
    projection["recommendations"] = recommendations
    return projection


def _association_projection_nodes_with_risk(
    *,
    nodes: list[dict[str, Any]],
    risk_map: dict[str, Any],
    non_risk_limit: int,
    total_limit: int,
) -> list[dict[str, Any]]:
    """Keep risk and competition nodes visible in the Amway Console projection."""

    result: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_node(node: Any) -> None:
        if not isinstance(node, dict):
            return
        node_id = str(node.get("node_id") or "").strip()
        if not node_id or node_id in seen:
            return
        seen.add(node_id)
        result.append(node)

    normal_nodes = [
        node
        for node in nodes
        if not node.get("is_risk_term") and node.get("orbit") != "risk_shadow"
    ]
    for node in normal_nodes[:non_risk_limit]:
        add_node(node)

    if isinstance(risk_map, dict):
        for key in ("risk_nodes", "competition_nodes", "nodes"):
            risk_nodes = risk_map.get(key)
            if not isinstance(risk_nodes, list):
                continue
            for node in risk_nodes:
                add_node(node)

    if len(result) < total_limit:
        for node in nodes:
            add_node(node)
            if len(result) >= total_limit:
                break
    return result[:total_limit]


def _dashboard_summary_cache_is_current(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    try:
        version = int(payload.get("projection_version") or 0)
    except (TypeError, ValueError):
        return False
    if version < DASHBOARD_WORLD_PROJECTION_VERSION:
        return False
    for key in REQUIRED_DASHBOARD_WORLD_PROJECTION_KEYS:
        if not isinstance(payload.get(key), dict):
            return False
    recommendation_projection = payload.get("recommendation_projection") or {}
    if not isinstance(recommendation_projection.get("recommendations"), list):
        return False
    if not isinstance(recommendation_projection.get("sample_status"), dict):
        return False
    sample_scope = (payload.get("summary_projection") or {}).get("sample_scope")
    if not isinstance(sample_scope, dict):
        return False
    association_circle_projection = payload.get("association_circle_projection")
    if isinstance(association_circle_projection, dict) and (
        association_circle_projection.get("status") == "ready"
    ):
        if not association_circle_projection.get("generated_from"):
            return False
        if not isinstance(
            association_circle_projection.get("strategy_validation"), list
        ):
            return False
        if not isinstance(association_circle_projection.get("risk_map"), dict):
            return False
    return True


def _split_relationship_summary(
    relationships: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    core: list[dict[str, Any]] = []
    supporting: list[dict[str, Any]] = []
    for item in relationships:
        target = core if item.get("visibility") == "core" else supporting
        target.append(item)
    return core, supporting


def _task_flow_summary(
    *,
    snapshot: dict[str, Any],
    action_queue: list[dict[str, Any]],
    world_phase: str | None,
) -> dict[str, Any]:
    questions = _summary_total(snapshot, "simulated_question")
    answers = _summary_total(snapshot, "platform_answer")
    citations = _summary_total(snapshot, "citation_source")
    findings = _summary_total(snapshot, "intelligence_finding")
    reports = _summary_total(snapshot, "report_artifact")
    monitoring = _summary_total(snapshot, "monitoring_plan")
    evidence_readiness = _evidence_readiness_label(
        question_count=questions,
        answer_count=answers,
        citation_count=citations,
        report_count=reports,
    )
    stage = _resolve_task_stage(
        questions=questions,
        answers=answers,
        citations=citations,
        findings=findings,
        reports=reports,
        monitoring=monitoring,
    )
    human_items = [item for item in action_queue if _is_human_action_queue_item(item)]
    feedbackable_items = [
        item
        for item in action_queue
        if not _is_action_feedback_resolved(item)
        and str(item.get("readiness") or "") == "ready_with_defaults"
    ]
    ready_items = [
        item
        for item in action_queue
        if str(item.get("readiness") or "") in {"ready", "ready_with_defaults"}
    ]
    blocked_items = [
        item for item in action_queue if str(item.get("readiness") or "") == "blocked"
    ]
    owner_label = (
        "需要人反馈"
        if human_items
        else (
            "人可调整，系统执行"
            if feedbackable_items
            else ("系统可执行" if ready_items else "等待前置信息")
        )
    )
    next_action = (
        human_items[0]
        if human_items
        else (
            feedbackable_items[0]
            if feedbackable_items
            else (
                ready_items[0]
                if ready_items
                else (blocked_items[0] if blocked_items else None)
            )
        )
    )
    risk_label = (
        "人不反馈会阻塞处理"
        if human_items
        else (
            _compact(str(blocked_items[0].get("reason") or "存在阻塞事项"), 80)
            if blocked_items
            else stage["risk_label"]
        )
    )
    return {
        "title": stage["title"],
        "stage_label": f"{PHASE_LABELS.get(str(world_phase or ''), str(world_phase or '缺少阶段'))} · {evidence_readiness}",
        "owner_label": owner_label,
        "objective": stage["objective"],
        "expected_output": stage["expected_output"],
        "risk_label": risk_label,
        "action_label": "处理反馈项" if human_items else "继续分析",
        "action_prompt": _task_flow_prompt(stage=stage, next_action=next_action),
        "steps": [
            {
                "key": "brand",
                "label": "品牌建档",
                "status": "complete",
                "owner": "system",
                "summary": "品牌已经成为后续情报的主语。",
                "evidence": "已建档",
            },
            {
                "key": "questions",
                "label": "建立问题池",
                "status": "complete" if questions else "current",
                "owner": "system" if questions else stage["owner"],
                "summary": (
                    "已经知道要从哪些问题观察品牌。"
                    if questions
                    else "先定义用户会问什么，后续回答和报告才有边界。"
                ),
                "evidence": f"{questions} 个问题",
            },
            {
                "key": "answers",
                "label": "抓取回答证据",
                "status": (
                    "complete" if answers else ("current" if questions else "waiting")
                ),
                "owner": "system" if answers or not questions else stage["owner"],
                "summary": (
                    "回答证据已经开始支撑后续判断。"
                    if answers
                    else (
                        "用问题池去观察平台如何描述品牌。"
                        if questions
                        else "等待问题池建立。"
                    )
                ),
                "evidence": f"{answers} 条回答",
            },
            {
                "key": "citations",
                "label": "追溯引用来源",
                "status": (
                    "complete" if citations else ("current" if answers else "waiting")
                ),
                "owner": "system" if citations or not answers else stage["owner"],
                "summary": (
                    "已经能解释平台回答的部分依据。"
                    if citations
                    else (
                        "需要知道平台回答背后的来源。" if answers else "等待回答证据。"
                    )
                ),
                "evidence": f"{citations} 个来源",
            },
            {
                "key": "findings",
                "label": "形成情报判断",
                "status": (
                    "complete"
                    if findings or reports
                    else ("current" if answers or citations else "waiting")
                ),
                "owner": (
                    "system"
                    if findings or reports or not (answers or citations)
                    else stage["owner"]
                ),
                "summary": (
                    "证据已经沉淀成可复核判断或报告。"
                    if findings or reports
                    else (
                        "把回答、来源和指标压缩成业务判断。"
                        if answers or citations
                        else "等待证据形成。"
                    )
                ),
                "evidence": f"{findings} 条判断",
            },
            {
                "key": "monitoring",
                "label": "进入持续运营",
                "status": (
                    "complete"
                    if monitoring
                    else ("current" if reports or findings else "waiting")
                ),
                "owner": (
                    "system"
                    if monitoring or not (reports or findings)
                    else stage["owner"]
                ),
                "summary": (
                    "品牌情报已经进入周期观察。"
                    if monitoring
                    else (
                        "把一次分析变成持续观察。"
                        if reports or findings
                        else "等待报告或判断。"
                    )
                ),
                "evidence": f"{monitoring} 个计划",
            },
        ],
    }


def _summary_total(snapshot: dict[str, Any], object_type: str) -> int:
    for item in snapshot.get("object_summaries") or []:
        if isinstance(item, dict) and item.get("object_type") == object_type:
            return int(item.get("total") or 0)
    return 0


def _question_bank_from_evidence_samples(
    evidence_samples: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    question_bank: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(evidence_samples, start=1):
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        if not question:
            continue
        question_id = str(item.get("question_id") or f"evidence_question_{index:03d}")
        key = question_id or question
        if key in seen:
            continue
        seen.add(key)
        question_bank.append(
            {
                "id": question_id,
                "text": question,
                "audience_segment": item.get("audience_segment"),
                "core_anxiety": item.get("core_anxiety"),
                "life_scene": item.get("life_scene"),
                "opportunity_point": item.get("opportunity_point"),
                "probe_type": item.get("probe_type"),
                "mother_theme": item.get("mother_theme"),
                "question_type": item.get("question_type"),
                "mentions_amway": item.get("mentions_amway"),
                "life_stage": item.get("life_stage"),
                "four_have": item.get("four_have"),
                "touchpoint": item.get("touchpoint"),
                "monitoring_purpose": item.get("monitoring_purpose"),
                "metadata_status": "from_evidence_sample",
                "source": "evidence_sample",
            }
        )
    return question_bank


def _question_bank_from_brand_questions(
    rows: list[BrandIntelligenceQuestion],
) -> list[dict[str, Any]]:
    question_bank: list[dict[str, Any]] = []
    for row in rows:
        payload = row.source_payload if isinstance(row.source_payload, dict) else {}
        item = {
            "id": row.question_id,
            "text": row.question_text,
            "category": row.category or payload.get("category"),
            "intent": row.user_intent or payload.get("intent"),
            "stage": row.decision_stage or payload.get("stage"),
            "audience_segment": payload.get("audience_segment")
            or payload.get("life_stage"),
            "core_anxiety": payload.get("core_anxiety"),
            "life_scene": payload.get("life_scene")
            or payload.get("touchpoint")
            or payload.get("mother_theme"),
            "opportunity_point": payload.get("opportunity_point")
            or payload.get("monitoring_purpose")
            or payload.get("mother_theme"),
            "probe_type": payload.get("probe_type") or payload.get("question_type"),
            "mother_theme": payload.get("mother_theme"),
            "question_type": payload.get("question_type"),
            "mentions_amway": payload.get("mentions_amway"),
            "life_stage": payload.get("life_stage"),
            "four_have": payload.get("four_have"),
            "touchpoint": payload.get("touchpoint"),
            "monitoring_purpose": payload.get("monitoring_purpose"),
            "center_terms": payload.get("center_terms"),
            "question_set_version": payload.get("question_set_version"),
            "metadata_status": payload.get("metadata_status")
            or "from_question_projection",
            "source": "brand_intelligence_question",
        }
        missing_core = not all(
            item.get(key)
            for key in (
                "audience_segment",
                "core_anxiety",
                "life_scene",
                "opportunity_point",
                "probe_type",
            )
        )
        if missing_core:
            inferred = complete_association_question_metadata(
                {**payload, "text": row.question_text},
                center_terms=payload.get("center_terms")
                or list(AMWAY_ASSOCIATION_CENTER_TERMS),
            )
            for key, value in inferred.items():
                if item.get(key) in (None, "", []):
                    item[key] = value
            item["metadata_status"] = "inferred_needs_review"
        question_bank.append(item)
    return question_bank


def _evidence_readiness_label(
    *,
    question_count: int,
    answer_count: int,
    citation_count: int,
    report_count: int,
) -> str:
    if report_count > 0:
        return "已成报告"
    if answer_count > 0 and citation_count > 0:
        return "证据成型"
    if answer_count > 0:
        return "已有回答"
    if question_count > 0:
        return "问题已定"
    return "待建立"


def _resolve_task_stage(
    *,
    questions: int,
    answers: int,
    citations: int,
    findings: int,
    reports: int,
    monitoring: int,
) -> dict[str, str]:
    if not questions:
        return {
            "title": "先建立可执行的问题池",
            "objective": "品牌情报先确定用户会问什么，再进入报告写作。问题池会决定后续抓取回答、追溯来源和形成判断的边界。",
            "expected_output": "一组可执行问题",
            "risk_label": "没有问题池就无法验证品牌表现",
            "owner": "shared",
        }
    if not answers:
        return {
            "title": "抓取平台回答证据",
            "objective": "当前已经有问题边界，下一步要观察平台如何回答这些问题，才能判断品牌是否被推荐、忽略或误解。",
            "expected_output": "平台回答",
            "risk_label": "只有问题，没有真实回答证据",
            "owner": "system",
        }
    if not citations:
        return {
            "title": "补齐引用来源",
            "objective": "回答只能说明平台说了什么，引用来源才能解释它为什么这么说，并帮助团队判断内容和渠道缺口。",
            "expected_output": "引用来源",
            "risk_label": "证据可信度不足",
            "owner": "system",
        }
    if not findings and not reports:
        return {
            "title": "沉淀情报判断",
            "objective": "把问题、回答和来源压缩成业务判断，让团队知道推荐优势、误解风险、竞品压制和内容机会在哪里。",
            "expected_output": "情报判断或报告",
            "risk_label": "证据还没有变成业务判断",
            "owner": "system",
        }
    if not monitoring:
        return {
            "title": "转入持续监测",
            "objective": "一次分析只能说明当前状态，持续监测才能观察品牌推荐变化、证据缺口变化和优化效果。",
            "expected_output": "监测计划",
            "risk_label": "无法持续观察变化",
            "owner": "shared",
        }
    return {
        "title": "持续运营品牌情报",
        "objective": "系统已经能围绕品牌持续积累问题、回答、来源、判断和处理记录，下一步重点是复盘变化和处理新的反馈。",
        "expected_output": "持续更新的品牌情报",
        "risk_label": "需要定期复核判断质量",
        "owner": "shared",
    }


def _task_flow_prompt(
    *,
    stage: dict[str, str],
    next_action: dict[str, Any] | None,
) -> str:
    if next_action:
        readiness = str(next_action.get("readiness") or "")
        action_text = (
            f"当前建议事项是「{next_action.get('display_name') or next_action.get('action_key')}」，"
            f"状态是「{ACTION_READINESS_LABELS.get(readiness, readiness or '未知')}」。"
        )
    else:
        action_text = "当前没有明确建议事项。"
    return (
        f"请基于当前品牌情报推进「{stage['title']}」。"
        f"{action_text}先说明缺口、需要我反馈什么、系统会通过哪个处理步骤继续，"
        "所有需要确认的步骤都要先获得明确反馈。"
    )


def _is_action_feedback_resolved(item: dict[str, Any]) -> bool:
    return str(item.get("user_feedback_state") or "") in {
        "confirmed",
        "input_provided",
        "deferred",
    }


def _is_human_action_queue_item(item: dict[str, Any]) -> bool:
    if _is_action_feedback_resolved(item):
        return False
    readiness = str(item.get("readiness") or "")
    return bool(item.get("requires_confirmation")) or readiness in {
        "needs_input",
        "needs_confirmation",
    }


def _world_object_display_name(object_type: str, fallback: str) -> str:
    labels = {
        "evidence_cluster": "证据主题",
        "platform_answer": "平台回答",
        "action_record": "处理记录",
    }
    return labels.get(object_type, fallback)


def _object_label(item: dict[str, Any], *, object_type: str = "") -> str:
    properties = item.get("properties") or {}
    object_type = str(
        object_type or item.get("object_type") or properties.get("object_type") or ""
    )
    if object_type == "evidence_cluster":
        evidence_label = _evidence_cluster_sample_label(properties)
        if evidence_label:
            return evidence_label
    for key in (
        "name",
        "display_name",
        "normalized_name",
        "persona_name",
        "scenario_name",
        "topic_label",
        "question_text",
        "title",
        "source_title",
        "domain",
        "url",
        "platform",
        "action_type",
        "decision_type",
        "report_id",
        "snapshot_key",
        "evidence_set_type",
    ):
        value = str(properties.get(key) or "").strip()
        if value:
            label = _compact(value)
            if _looks_like_internal_question_label(label):
                continue
            return label
    fallback = str(item.get("object_id") or "")
    if _looks_like_internal_question_label(fallback):
        return "综合证据主题"
    return fallback


def _evidence_cluster_sample_label(properties: dict[str, Any]) -> str:
    topic_label = _compact(str(properties.get("topic_label") or ""))
    title = _compact(str(properties.get("title") or ""))
    source_role_label = _compact(str(properties.get("source_role_label") or ""))
    topic = ""
    for candidate in (topic_label, title):
        if not candidate or _looks_like_internal_question_label(candidate):
            continue
        topic = candidate
        break
    if not topic:
        topic = "综合证据主题"
    if source_role_label and source_role_label not in topic:
        return f"{topic} · {source_role_label}"
    return topic


def _compact(value: str, limit: int = 80) -> str:
    text = " ".join(str(value or "").split())
    if CORRUPTED_LABEL_RE.search(text):
        return "样本内容待修复"
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


def _looks_like_internal_question_label(value: str) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    normalized = text.replace(" ", "")
    return bool(
        normalized.startswith("q_")
        or normalized.startswith("q-")
        or normalized.startswith("问题q_")
        or normalized.startswith("问题q-")
        or normalized.startswith("question_")
        or normalized.startswith("question-")
        or "问题q_" in normalized
        or "问题q-" in normalized
        or "q_001" in normalized
        or "q-001" in normalized
    )


def _normalize_feedback_type(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"confirm", "accept", "validated"}:
        return "validate"
    if normalized in {"reject", "dismissed"}:
        return "dismiss"
    if normalized in {"revise", "revision"}:
        return "correct"
    return normalized or "feedback"


def _action_queue_from_plan(
    action_plan: dict[str, Any] | None,
    action_feedback_summary: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(action_plan, dict):
        return []
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    latest_by_action = {}
    if isinstance(action_feedback_summary, dict):
        raw_latest = action_feedback_summary.get("latest_by_action") or {}
        if isinstance(raw_latest, dict):
            latest_by_action = raw_latest
    for source_key in ("needs_human_confirmation", "recommended_actions"):
        for raw_item in action_plan.get(source_key) or []:
            if not isinstance(raw_item, dict):
                continue
            action_key = str(raw_item.get("action_key") or "").strip()
            if not action_key or action_key in seen:
                continue
            seen.add(action_key)
            feedback = latest_by_action.get(action_key) or {}
            if not isinstance(feedback, dict):
                feedback = {}
            feedback_type = _normalize_action_feedback_type(
                feedback.get("feedback_type")
            )
            user_feedback_state = _action_feedback_state(feedback_type)
            priority = _action_queue_priority(raw_item)
            if user_feedback_state != "none":
                priority += 20
            items.append(
                {
                    "action_key": action_key,
                    "display_name": raw_item.get("display_name") or action_key,
                    "readiness": raw_item.get("readiness") or "blocked",
                    "priority": priority,
                    "permission_scope": raw_item.get("permission_scope"),
                    "requires_confirmation": bool(
                        raw_item.get("requires_confirmation")
                    ),
                    "missing_inputs": list(raw_item.get("missing_inputs") or []),
                    "defaulted_inputs": _public_defaulted_inputs(
                        raw_item.get("defaulted_inputs")
                    ),
                    "missing_objects": list(raw_item.get("missing_objects") or []),
                    "reason": raw_item.get("reason") or "",
                    "source": _public_action_source(raw_item.get("source")),
                    "target_object_type": raw_item.get("target_object_type"),
                    "target_object_id": raw_item.get("target_object_id"),
                    "feedback_type": raw_item.get("feedback_type"),
                    "latest_feedback_type": feedback_type or None,
                    "latest_feedback_at": feedback.get("decided_at"),
                    "latest_feedback_status": feedback.get("status"),
                    "user_feedback_state": user_feedback_state,
                    "has_user_feedback": user_feedback_state != "none",
                    "provided_input_keys": list(
                        feedback.get("provided_input_keys") or []
                    ),
                    "consumed_by_action_record_id": (
                        feedback.get("consumed_by_action_record_id")
                    ),
                    "consumed_by_action_type": feedback.get("consumed_by_action_type"),
                }
            )
    return sorted(items, key=lambda item: (item["priority"], item["display_name"]))


def _public_action_source(value: Any) -> str:
    source = str(value or "").strip()
    if not source or source == "ontology_world":
        return "brand_world"
    return _public_source_text(source)


def _prioritize_association_evidence_for_nodes(
    nodes: list[dict[str, Any]],
    evidence_items: list[Any],
    *,
    limit: int,
) -> list[Any]:
    if not evidence_items:
        return []
    refs: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        for ref in node.get("evidence_samples") or []:
            ref_text = str(ref or "").strip()
            if ref_text and ref_text not in refs:
                refs.append(ref_text)
    by_id = {
        str(item.get("evidence_id") or "").strip(): item
        for item in evidence_items
        if isinstance(item, dict) and str(item.get("evidence_id") or "").strip()
    }
    selected: list[Any] = []
    selected_ids: set[int] = set()
    selected_evidence_ids: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        for ref in node.get("evidence_samples") or []:
            ref_text = str(ref or "").strip()
            if not ref_text or ref_text in selected_evidence_ids:
                continue
            item = by_id.get(ref_text)
            if item is None:
                continue
            selected.append(item)
            selected_ids.add(id(item))
            selected_evidence_ids.add(ref_text)
            break
        if len(selected) >= limit:
            return selected
    for ref in refs:
        if ref in selected_evidence_ids:
            continue
        item = by_id.get(ref)
        if item is None:
            continue
        selected.append(item)
        selected_ids.add(id(item))
        selected_evidence_ids.add(ref)
        if len(selected) >= limit:
            return selected
    for item in evidence_items:
        if id(item) in selected_ids:
            continue
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def _diversify_association_source_appendix(
    evidence_items: list[Any],
    *,
    limit: int,
) -> list[Any]:
    if not evidence_items:
        return []
    selected: list[Any] = []
    selected_ids: set[int] = set()
    selected_keys: set[str] = set()

    def item_key(item: Any) -> str:
        if not isinstance(item, dict):
            return ""
        key_parts = [
            str(item.get("evidence_id") or "").strip(),
            str(item.get("question_id") or "").strip(),
            str(item.get("platform") or item.get("source_platform") or "").strip(),
            str(item.get("node_term") or "").strip(),
        ]
        return "|".join(key_parts)

    def add(item: Any) -> None:
        if len(selected) >= limit:
            return
        item_identity = id(item)
        if item_identity in selected_ids:
            return
        key = item_key(item)
        if key and key in selected_keys:
            return
        selected.append(item)
        selected_ids.add(item_identity)
        if key:
            selected_keys.add(key)

    seen_platforms: set[str] = set()
    seen_questions: set[str] = set()
    platforms = []
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        platform = str(item.get("platform") or item.get("source_platform") or "").strip()
        if platform and platform not in platforms:
            platforms.append(platform)

    for platform in platforms:
        platform_items = [
            item
            for item in evidence_items
            if isinstance(item, dict)
            and str(
                item.get("platform") or item.get("source_platform") or ""
            ).strip()
            == platform
        ]
        item = next(
            (
                candidate
                for candidate in platform_items
                if str(candidate.get("question_id") or "").strip()
                and str(candidate.get("question_id") or "").strip()
                not in seen_questions
            ),
            platform_items[0] if platform_items else None,
        )
        if item is None or platform in seen_platforms:
            continue
        add(item)
        seen_platforms.add(platform)
        question_id = str(item.get("question_id") or "").strip()
        if question_id:
            seen_questions.add(question_id)
        if len(selected) >= limit:
            return selected

    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        question_id = str(item.get("question_id") or "").strip()
        if not question_id or question_id in seen_questions:
            continue
        add(item)
        seen_questions.add(question_id)
        if len(selected) >= limit:
            return selected

    for item in evidence_items:
        add(item)
        if len(selected) >= limit:
            break
    return selected


def _prioritize_association_findings_for_nodes(
    nodes: list[dict[str, Any]],
    findings: list[Any],
    *,
    limit: int,
) -> list[Any]:
    if not findings:
        return []
    node_ids = {
        str(node.get("node_id") or "").strip()
        for node in nodes
        if isinstance(node, dict) and str(node.get("node_id") or "").strip()
    }
    terms = {
        str(node.get("term") or "").strip()
        for node in nodes
        if isinstance(node, dict) and str(node.get("term") or "").strip()
    }
    selected: list[Any] = []
    rest: list[Any] = []
    seen_keys: set[str] = set()
    for item in findings:
        if not isinstance(item, dict):
            rest.append(item)
            continue
        key = "|".join(
            [
                str(item.get("node_id") or "").strip(),
                str(item.get("node_term") or "").strip(),
                str(item.get("claim") or "").strip(),
            ]
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        matches_node = (
            str(item.get("node_id") or "").strip() in node_ids
            or str(item.get("node_term") or "").strip() in terms
        )
        if matches_node:
            selected.append(item)
        else:
            rest.append(item)
    return (selected + rest)[:limit]


def _public_defaulted_inputs(raw_inputs: Any) -> list[dict[str, Any]]:
    inputs: list[dict[str, Any]] = []
    for raw_item in raw_inputs or []:
        if not isinstance(raw_item, dict):
            continue
        item = dict(raw_item)
        if "source" in item:
            item["source"] = _public_source_text(item.get("source"))
        inputs.append(item)
    return inputs


def _public_source_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return (
        text.replace("ontology_world", "brand_world")
        .replace("official_website_asset", "official_website")
    )


def _action_queue_priority(item: dict[str, Any]) -> int:
    readiness = str(item.get("readiness") or "").strip().lower()
    if readiness in {"needs_confirmation", "needs_input"}:
        return 1
    if readiness in {"ready", "ready_with_defaults"}:
        return 2
    return 3


def _parse_action_feedback_key(decision_key: str | None) -> tuple[str, str]:
    value = str(decision_key or "").strip()
    if ":" not in value:
        return value, ""
    action_key, feedback_type = value.rsplit(":", 1)
    return action_key.strip(), feedback_type.strip()


def _normalize_action_feedback_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized.startswith("action_queue_"):
        normalized = normalized.removeprefix("action_queue_")
    if normalized in {"confirm", "confirmed", "accept", "accepted"}:
        return "confirm"
    if normalized in {"provide_input", "input", "input_provided"}:
        return "provide_input"
    if normalized in {"defer", "deferred", "dismiss", "skip"}:
        return "defer"
    return normalized


def _action_feedback_state(feedback_type: str) -> str:
    if feedback_type == "confirm":
        return "confirmed"
    if feedback_type == "provide_input":
        return "input_provided"
    if feedback_type == "defer":
        return "deferred"
    return "none"
