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
    BrandObjectLink,
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
DASHBOARD_WORLD_PROJECTION_VERSION = 4
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
_world_summary_cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}


def _relationship_visibility(link_type: str) -> str:
    return "core" if link_type in CORE_RELATIONSHIP_TYPES else "supporting"


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
            if instance_cached is not None:
                return (
                    deepcopy(instance_cached) if instance_cached is not None else None
                )
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
        self._dashboard_summary_cache[cache_key] = deepcopy(dashboard_summary)
        _write_world_summary_cache(cache_key, dashboard_summary)
        return dashboard_summary

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
            "objective": "品牌情报不是先写报告，而是先确定用户会问什么。问题池会决定后续抓取回答、追溯来源和形成判断的边界。",
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
        "不要直接跳过需要确认的步骤。"
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
