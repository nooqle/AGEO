"""Read surface for durable brand intelligence ontology objects."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from app.models.brand_intelligence import (
    BrandActionRecord,
    BrandAudiencePersona,
    BrandCitationSource,
    BrandCompetitorEntity,
    BrandEvidenceSet,
    BrandIntelligenceFinding,
    BrandIntelligenceQuestion,
    BrandMetricSnapshot,
    BrandMention,
    BrandObjectLink,
    BrandPlatformAnswer,
    BrandReportVersion,
    BrandUsageScenario,
    BrandUserDecision,
)
from app.models.entity import Entity
from app.models.monitoring_plan import MonitoringPlan, MonitoringQuestionSet
from app.ontology import OntologyRegistry, load_default_ontology
from app.services.brand_evidence_denoising_service import (
    BrandEvidenceDenoisingService,
)
from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class ObjectModelBinding:
    model: type
    id_field: str = "id"


OBJECT_MODEL_BINDINGS: dict[str, ObjectModelBinding] = {
    "brand_entity": ObjectModelBinding(Entity),
    "competitor_entity": ObjectModelBinding(BrandCompetitorEntity),
    "audience_persona": ObjectModelBinding(BrandAudiencePersona),
    "usage_scenario": ObjectModelBinding(BrandUsageScenario),
    "simulated_question": ObjectModelBinding(BrandIntelligenceQuestion),
    "question_set": ObjectModelBinding(MonitoringQuestionSet),
    "platform_answer": ObjectModelBinding(BrandPlatformAnswer),
    "brand_mention": ObjectModelBinding(BrandMention),
    "citation_source": ObjectModelBinding(BrandCitationSource),
    "metric_snapshot": ObjectModelBinding(BrandMetricSnapshot),
    "evidence_set": ObjectModelBinding(BrandEvidenceSet),
    "intelligence_finding": ObjectModelBinding(BrandIntelligenceFinding),
    "report_artifact": ObjectModelBinding(BrandReportVersion),
    "monitoring_plan": ObjectModelBinding(MonitoringPlan),
    "user_decision": ObjectModelBinding(BrandUserDecision),
    "action_record": ObjectModelBinding(BrandActionRecord),
}


SENSITIVE_OBJECT_PUBLIC_PROPERTIES: dict[str, frozenset[str]] = {
    "competitor_entity": frozenset(
        {
            "id",
            "entity_id",
            "session_id",
            "competitor_key",
            "normalized_name",
            "display_name",
            "website",
            "competition_type",
            "relevance_score",
            "status",
            "created_at",
            "updated_at",
        }
    ),
    "audience_persona": frozenset(
        {
            "id",
            "entity_id",
            "session_id",
            "persona_id",
            "persona_name",
            "description",
            "segment",
            "priority",
            "status",
            "created_at",
            "updated_at",
        }
    ),
    "usage_scenario": frozenset(
        {
            "id",
            "entity_id",
            "session_id",
            "persona_object_id",
            "scenario_key",
            "scenario_name",
            "description",
            "decision_stage",
            "status",
            "created_at",
            "updated_at",
        }
    ),
    "simulated_question": frozenset(
        {
            "id",
            "entity_id",
            "session_id",
            "question_id",
            "question_text",
            "category",
            "subcategory",
            "user_intent",
            "decision_stage",
            "status",
            "created_at",
            "updated_at",
        }
    ),
    "question_set": frozenset(
        {
            "id",
            "entity_id",
            "monitor_mode",
            "status",
            "source",
            "title",
            "version",
            "question_count",
            "source_session_id",
            "source_task_id",
            "confirmed_at",
            "created_at",
            "updated_at",
        }
    ),
    "platform_answer": frozenset(
        {
            "id",
            "entity_id",
            "session_id",
            "question_object_id",
            "question_id",
            "dedupe_key",
            "platform",
            "fetch_method",
            "status",
            "success",
            "brand_mentioned",
            "run_id",
            "duration_ms",
            "captured_at",
            "created_at",
            "updated_at",
        }
    ),
    "citation_source": frozenset(
        {
            "id",
            "entity_id",
            "session_id",
            "answer_id",
            "dedupe_key",
            "url",
            "domain",
            "source_title",
            "confidence",
            "created_at",
            "updated_at",
        }
    ),
    "brand_mention": frozenset(
        {
            "platform",
            "mentioned_brand_name",
            "mention_role",
            "sentiment",
            "quote",
            "confidence",
            "status",
            "captured_at",
            "created_at",
            "updated_at",
        }
    ),
    "metric_snapshot": frozenset(
        {
            "id",
            "entity_id",
            "session_id",
            "report_version_id",
            "snapshot_key",
            "metric_kind",
            "bwvs_index",
            "mention_rate",
            "total_questions",
            "total_mentions",
            "created_at",
            "updated_at",
        }
    ),
    "evidence_set": frozenset(
        {
            "id",
            "entity_id",
            "session_id",
            "evidence_set_type",
            "title",
            "question_count",
            "answer_count",
            "citation_count",
            "created_at",
            "updated_at",
        }
    ),
    "report_artifact": frozenset(
        {
            "id",
            "entity_id",
            "session_id",
            "evidence_set_id",
            "message_id",
            "report_id",
            "version",
            "report_kind",
            "artifact_id",
            "title",
            "summary",
            "created_at",
            "updated_at",
        }
    ),
    "monitoring_plan": frozenset(
        {
            "id",
            "entity_id",
            "monitor_mode",
            "status",
            "title",
            "run_policy",
            "question_count",
            "cadence",
            "next_run_at",
            "last_run_at",
            "created_at",
            "updated_at",
        }
    ),
    "action_record": frozenset(
        {
            "id",
            "entity_id",
            "session_id",
            "parent_action_record_id",
            "actor_type",
            "origin_surface",
            "origin_event_id",
            "action_type",
            "status",
            "requires_confirmation",
            "permission_scope",
            "submitted_at",
            "completed_at",
            "created_at",
        }
    ),
    "user_decision": frozenset(
        {
            "id",
            "entity_id",
            "action_record_id",
            "session_id",
            "decision_type",
            "decision_key",
            "status",
            "origin_surface",
            "origin_event_id",
            "target_object_type",
            "target_object_id",
            "decided_at",
            "created_at",
        }
    ),
    "intelligence_finding": frozenset(
        {
            "id",
            "entity_id",
            "session_id",
            "report_version_id",
            "evidence_set_id",
            "finding_key",
            "title",
            "summary",
            "finding_type",
            "severity",
            "confidence",
            "status",
            "evidence_summary",
            "supporting_question_count",
            "supporting_answer_count",
            "supporting_citation_count",
            "suggested_action_type",
            "created_at",
            "updated_at",
        }
    ),
}


DERIVED_LIFECYCLE_STATUS_BY_OBJECT_TYPE: dict[str, str] = {
    "citation_source": "captured",
    "metric_snapshot": "created",
    "evidence_set": "attached_to_report",
    "report_artifact": "published",
}


LIFECYCLE_STATUS_ALIASES: dict[str, dict[str, str]] = {
    "brand_entity": {
        "inactive": "archived",
    },
    "platform_answer": {
        "completed": "captured",
        "success": "captured",
        "succeeded": "captured",
        "ok": "captured",
        "error": "failed",
        "timeout": "failed",
        "timed_out": "failed",
        "skipped": "failed",
        "pending": "requested",
    },
    "action_record": {
        "completed": "applied",
        "succeeded": "applied",
        "cancelled": "reverted",
        "canceled": "reverted",
    },
    "user_decision": {
        "completed": "applied",
        "succeeded": "applied",
        "cancelled": "reverted",
        "canceled": "reverted",
    },
    "intelligence_finding": {
        "active": "observed",
        "generated": "observed",
        "confirmed": "validated",
        "accepted": "validated",
        "rejected": "dismissed",
        "ignored": "dismissed",
    },
    "brand_mention": {
        "active": "observed",
        "captured": "observed",
        "generated": "observed",
        "accepted": "reviewed",
        "rejected": "dismissed",
        "ignored": "dismissed",
    },
}


DEFAULT_OBJECT_LIST_LIMIT = 50
MAX_OBJECT_LIST_LIMIT = 100
DERIVED_READ_OBJECT_TYPES = {
    "official_website_asset",
    "source_domain",
    "evidence_cluster",
}


class BrandOntologyObjectService:
    """Builds object and relationship payloads for future Object Views."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        registry: OntologyRegistry | None = None,
    ) -> None:
        self.db = db
        self.registry = registry or load_default_ontology()
        self._evidence_summary_cache: dict[tuple[UUID, bool], dict[str, Any]] = {}

    async def build_evidence_summary(
        self,
        *,
        entity_id: UUID,
        include_content_audit: bool = True,
    ) -> dict[str, Any]:
        cache_key = (entity_id, include_content_audit)
        cached = self._evidence_summary_cache.get(cache_key)
        if cached is not None:
            return cached
        summary = await BrandEvidenceDenoisingService(self.db).build_summary(
            entity_id=entity_id,
            include_content_audit=include_content_audit,
        )
        self._evidence_summary_cache[cache_key] = summary
        return summary

    async def get_object(
        self,
        *,
        entity_id: UUID,
        object_type: str,
        object_id: str,
    ) -> dict[str, Any] | None:
        self.registry.require_object_type(object_type)
        if object_type in DERIVED_READ_OBJECT_TYPES:
            return await self._get_derived_object(
                entity_id=entity_id,
                object_type=object_type,
                object_id=object_id,
            )
        binding = OBJECT_MODEL_BINDINGS.get(object_type)
        if binding is None:
            raise ValueError(f"Unsupported object type: {object_type}")
        row = await self._load_row(binding.model, object_id)
        if row is None or not self._belongs_to_entity(row, entity_id, object_type):
            return None
        return self._object_payload(object_type, row)

    async def list_objects(
        self,
        *,
        entity_id: UUID,
        object_type: str,
        limit: int = DEFAULT_OBJECT_LIST_LIMIT,
        offset: int = 0,
        status: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        sort: str = "created_at_desc",
    ) -> dict[str, Any]:
        self.registry.require_object_type(object_type)
        if object_type in DERIVED_READ_OBJECT_TYPES:
            return await self._list_derived_objects(
                entity_id=entity_id,
                object_type=object_type,
                limit=limit,
                offset=offset,
                status=status,
                created_after=created_after,
                created_before=created_before,
                sort=sort,
            )
        binding = OBJECT_MODEL_BINDINGS.get(object_type)
        if binding is None:
            raise ValueError(f"Unsupported object type: {object_type}")

        normalized_limit = _normalize_limit(limit)
        normalized_offset = max(int(offset or 0), 0)
        conditions = self._entity_conditions(
            model=binding.model,
            entity_id=entity_id,
            object_type=object_type,
        )
        conditions.extend(
            self._collection_filter_conditions(
                model=binding.model,
                object_type=object_type,
                status=status,
                created_after=created_after,
                created_before=created_before,
            )
        )
        total = int(
            (
                await self.db.execute(
                    select(func.count()).select_from(binding.model).where(*conditions)
                )
            ).scalar_one()
            or 0
        )
        rows = (
            (
                await self.db.execute(
                    select(binding.model)
                    .where(*conditions)
                    .order_by(self._ordering_column(binding.model, sort=sort))
                    .limit(normalized_limit)
                    .offset(normalized_offset)
                )
            )
            .scalars()
            .all()
        )
        return {
            "object_type": object_type,
            "objects": [self._object_payload(object_type, row) for row in rows],
            "total": total,
            "limit": normalized_limit,
            "offset": normalized_offset,
            "filters": {
                "status": status,
                "created_after": (
                    created_after.isoformat() if created_after is not None else None
                ),
                "created_before": (
                    created_before.isoformat() if created_before is not None else None
                ),
                "sort": sort,
            },
        }

    async def count_lifecycle_statuses(
        self,
        *,
        entity_id: UUID,
        object_type: str,
    ) -> dict[str, int]:
        self.registry.require_object_type(object_type)
        if object_type in DERIVED_READ_OBJECT_TYPES:
            collection = await self._list_derived_objects(
                entity_id=entity_id,
                object_type=object_type,
                limit=MAX_OBJECT_LIST_LIMIT,
                offset=0,
            )
            counts: Counter[str] = Counter(
                str((item.get("lifecycle") or {}).get("status") or "unknown")
                for item in collection.get("objects") or []
            )
            return dict(counts)
        binding = OBJECT_MODEL_BINDINGS.get(object_type)
        if binding is None:
            raise ValueError(f"Unsupported object type: {object_type}")

        conditions = self._entity_conditions(
            model=binding.model,
            entity_id=entity_id,
            object_type=object_type,
        )
        status_column = getattr(binding.model, "status", None)
        if status_column is None:
            total = int(
                (
                    await self.db.execute(
                        select(func.count())
                        .select_from(binding.model)
                        .where(*conditions)
                    )
                ).scalar_one()
                or 0
            )
            derived_status = DERIVED_LIFECYCLE_STATUS_BY_OBJECT_TYPE.get(object_type)
            return {derived_status: total} if total and derived_status else {}

        rows = (
            await self.db.execute(
                select(status_column, func.count())
                .where(*conditions)
                .group_by(status_column)
            )
        ).all()
        counts: dict[str, int] = {}
        for raw_status, count in rows:
            normalized_status = self._normalize_lifecycle_status(
                object_type=object_type,
                raw_status=self._status_to_text(raw_status),
            )
            status_key = normalized_status or "unknown"
            counts[status_key] = counts.get(status_key, 0) + int(count or 0)
        return counts

    async def list_links(
        self,
        *,
        entity_id: UUID,
        object_type: str,
        object_id: str,
        direction: str = "both",
    ) -> list[dict[str, Any]] | None:
        object_payload = await self.get_object(
            entity_id=entity_id,
            object_type=object_type,
            object_id=object_id,
        )
        if object_payload is None:
            return None
        normalized_direction = str(direction or "both").strip().lower()
        conditions = [BrandObjectLink.entity_id == entity_id]
        if normalized_direction == "out":
            conditions.extend(
                [
                    BrandObjectLink.from_object_type == object_type,
                    BrandObjectLink.from_object_id == object_id,
                ]
            )
        elif normalized_direction == "in":
            conditions.extend(
                [
                    BrandObjectLink.to_object_type == object_type,
                    BrandObjectLink.to_object_id == object_id,
                ]
            )
        elif normalized_direction == "both":
            conditions.append(
                (
                    (BrandObjectLink.from_object_type == object_type)
                    & (BrandObjectLink.from_object_id == object_id)
                )
                | (
                    (BrandObjectLink.to_object_type == object_type)
                    & (BrandObjectLink.to_object_id == object_id)
                )
            )
        else:
            raise ValueError("direction must be one of: in, out, both")
        rows = (
            (
                await self.db.execute(
                    select(BrandObjectLink)
                    .where(*conditions)
                    .order_by(BrandObjectLink.created_at)
                )
            )
            .scalars()
            .all()
        )
        return [self._link_payload(row) for row in rows]

    async def get_object_view(
        self,
        *,
        entity_id: UUID,
        object_type: str,
        object_id: str,
        view_key: str | None = None,
    ) -> dict[str, Any] | None:
        object_payload = await self.get_object(
            entity_id=entity_id,
            object_type=object_type,
            object_id=object_id,
        )
        if object_payload is None:
            return None
        view_definition = (
            self.registry.require_object_view(view_key)
            if view_key
            else self._default_view_for_object_type(object_type)
        )
        if view_definition.object_type != object_type:
            raise ValueError(
                f"Object view {view_definition.key} does not support {object_type}"
            )
        links = await self.list_links(
            entity_id=entity_id,
            object_type=object_type,
            object_id=object_id,
            direction="both",
        )
        return {
            "view": view_definition.model_dump(),
            "object": object_payload,
            "links": links,
        }

    async def _get_derived_object(
        self,
        *,
        entity_id: UUID,
        object_type: str,
        object_id: str,
    ) -> dict[str, Any] | None:
        collection = await self._list_derived_objects(
            entity_id=entity_id,
            object_type=object_type,
            limit=MAX_OBJECT_LIST_LIMIT,
            offset=0,
        )
        for item in collection.get("objects") or []:
            if item.get("object_id") == object_id:
                return item
        return None

    async def _list_derived_objects(
        self,
        *,
        entity_id: UUID,
        object_type: str,
        limit: int = DEFAULT_OBJECT_LIST_LIMIT,
        offset: int = 0,
        status: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        sort: str = "created_at_desc",
    ) -> dict[str, Any]:
        normalized_limit = _normalize_limit(limit)
        normalized_offset = max(int(offset or 0), 0)
        status_values = self._status_filter_values(
            object_type=object_type,
            status=status,
        )
        rows = await self._derived_object_rows(
            entity_id=entity_id,
            object_type=object_type,
        )
        if status_values:
            rows = [
                row
                for row in rows
                if str((row.get("lifecycle") or {}).get("status") or "").lower()
                in status_values
            ]
        rows = self._order_derived_objects(rows, sort=sort)
        total = len(rows)
        return {
            "object_type": object_type,
            "objects": rows[normalized_offset : normalized_offset + normalized_limit],
            "total": total,
            "limit": normalized_limit,
            "offset": normalized_offset,
            "filters": {
                "status": status,
                "created_after": (
                    created_after.isoformat() if created_after is not None else None
                ),
                "created_before": (
                    created_before.isoformat() if created_before is not None else None
                ),
                "sort": sort,
            },
        }

    async def _derived_object_rows(
        self,
        *,
        entity_id: UUID,
        object_type: str,
    ) -> list[dict[str, Any]]:
        summary = await self.build_evidence_summary(entity_id=entity_id)
        if object_type == "official_website_asset":
            observation = summary.get("official_website_observation")
            if isinstance(observation, dict):
                return [self._derived_object_payload(object_type, observation)]
            return []

        source_key = (
            "source_domain_summary"
            if object_type == "source_domain"
            else "evidence_clusters"
        )
        return [
            self._derived_object_payload(object_type, item)
            for item in summary.get(source_key) or []
            if isinstance(item, dict)
        ]

    def _derived_object_payload(
        self,
        object_type: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        if object_type == "official_website_asset":
            object_id = str(properties.get("domain") or "official-website")
        elif object_type == "source_domain":
            object_id = str(properties.get("domain") or "")
        else:
            object_id = str(properties.get("cluster_id") or "")
        return {
            "object_type": object_type,
            "object_id": object_id,
            "lifecycle": self._derived_lifecycle_payload(object_type, properties),
            "properties": properties,
        }

    def _derived_lifecycle_payload(
        self,
        object_type: str,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        definition = self.registry.require_object_type(object_type)
        raw_status = (
            str(properties.get("status") or "missing_domain").strip().lower()
            if object_type == "official_website_asset"
            else "derived"
        )
        normalized_status = self._normalize_lifecycle_status(
            object_type=object_type,
            raw_status=raw_status,
        )
        return {
            "status": normalized_status or definition.lifecycle[0],
            "raw_status": raw_status if raw_status != normalized_status else None,
            "allowed_statuses": list(definition.lifecycle),
        }

    @staticmethod
    def _order_derived_objects(
        rows: list[dict[str, Any]],
        *,
        sort: str,
    ) -> list[dict[str, Any]]:
        cleaned = str(sort or "created_at_desc").strip().lower()
        if cleaned not in {
            "created_at_desc",
            "created_at_asc",
            "updated_at_desc",
            "updated_at_asc",
        }:
            raise ValueError(
                "sort must be one of: created_at_desc, created_at_asc, "
                "updated_at_desc, updated_at_asc"
            )
        reverse = cleaned.endswith("_desc")
        return sorted(
            rows,
            key=lambda item: (
                int((item.get("properties") or {}).get("citation_count") or 0),
                str(item.get("object_id") or ""),
            ),
            reverse=reverse,
        )

    async def _load_row(self, model: type, object_id: str) -> Any | None:
        try:
            row_id = UUID(str(object_id))
        except (TypeError, ValueError):
            return None
        return await self.db.get(model, row_id)

    def _default_view_for_object_type(self, object_type: str):
        for view in self.registry.object_views:
            if view.object_type == object_type:
                return view
        raise ValueError(f"No object view registered for {object_type}")

    @staticmethod
    def _belongs_to_entity(row: Any, entity_id: UUID, object_type: str) -> bool:
        if object_type == "brand_entity":
            return getattr(row, "id", None) == entity_id
        row_entity_id = getattr(row, "entity_id", None)
        return row_entity_id == entity_id

    @staticmethod
    def _entity_conditions(
        *,
        model: type,
        entity_id: UUID,
        object_type: str,
    ) -> list[Any]:
        if object_type == "brand_entity":
            return [getattr(model, "id") == entity_id]
        entity_column = getattr(model, "entity_id", None)
        if entity_column is None:
            raise ValueError(f"Object type {object_type} is not entity-scoped")
        return [entity_column == entity_id]

    def _collection_filter_conditions(
        self,
        *,
        model: type,
        object_type: str,
        status: str | None,
        created_after: datetime | None,
        created_before: datetime | None,
    ) -> list[Any]:
        conditions: list[Any] = []
        status_values = self._status_filter_values(
            object_type=object_type,
            status=status,
        )
        status_column = getattr(model, "status", None)
        if status_values and status_column is None:
            derived_status = DERIVED_LIFECYCLE_STATUS_BY_OBJECT_TYPE.get(object_type)
            if derived_status not in status_values:
                conditions.append(getattr(model, "id") == None)  # noqa: E711
        elif status_values:
            conditions.append(status_column.in_(status_values))

        created_at = getattr(model, "created_at", None)
        if created_at is not None and created_after is not None:
            conditions.append(created_at >= created_after)
        if created_at is not None and created_before is not None:
            conditions.append(created_at <= created_before)
        return conditions

    def _status_filter_values(
        self,
        *,
        object_type: str,
        status: str | None,
    ) -> set[str]:
        cleaned = str(status or "").strip().lower()
        if not cleaned:
            return set()
        normalized = self._normalize_lifecycle_status(
            object_type=object_type,
            raw_status=cleaned,
        )
        if normalized is None:
            raise ValueError(f"Invalid lifecycle filter for {object_type}: {status}")
        values = {cleaned, normalized}
        aliases = LIFECYCLE_STATUS_ALIASES.get(object_type, {})
        values.update(raw for raw, alias in aliases.items() if alias == normalized)
        values.update(value.upper() for value in list(values))
        return values

    @staticmethod
    def _ordering_column(model: type, *, sort: str = "created_at_desc") -> Any:
        cleaned = str(sort or "created_at_desc").strip().lower()
        if cleaned not in {
            "created_at_desc",
            "created_at_asc",
            "updated_at_desc",
            "updated_at_asc",
        }:
            raise ValueError(
                "sort must be one of: created_at_desc, created_at_asc, "
                "updated_at_desc, updated_at_asc"
            )
        field_name, direction = cleaned.rsplit("_", 1)
        column = getattr(model, field_name, None)
        if column is None:
            column = getattr(model, "created_at", None)
        if column is None:
            column = getattr(model, "id")
        return asc(column) if direction == "asc" else desc(column)

    def _object_payload(self, object_type: str, row: Any) -> dict[str, Any]:
        return {
            "object_type": object_type,
            "object_id": str(getattr(row, "id")),
            "lifecycle": self._lifecycle_payload(object_type, row),
            "properties": self._row_properties(object_type, row),
        }

    def _lifecycle_payload(self, object_type: str, row: Any) -> dict[str, Any]:
        definition = self.registry.require_object_type(object_type)
        raw_status = self._raw_lifecycle_status(object_type, row)
        normalized_status = self._normalize_lifecycle_status(
            object_type=object_type,
            raw_status=raw_status,
        )
        if normalized_status is None:
            raise ValueError(
                f"Object {object_type}/{getattr(row, 'id', '')} has invalid "
                f"lifecycle status: {raw_status}"
            )
        return {
            "status": normalized_status,
            "raw_status": raw_status if raw_status != normalized_status else None,
            "allowed_statuses": list(definition.lifecycle),
        }

    @staticmethod
    def _raw_lifecycle_status(object_type: str, row: Any) -> str:
        if hasattr(row, "status"):
            return BrandOntologyObjectService._status_to_text(getattr(row, "status"))
        return DERIVED_LIFECYCLE_STATUS_BY_OBJECT_TYPE.get(object_type, "")

    @staticmethod
    def _status_to_text(value: Any) -> str:
        if hasattr(value, "value"):
            return str(value.value)
        return str(value or "")

    def _normalize_lifecycle_status(
        self,
        *,
        object_type: str,
        raw_status: str,
    ) -> str | None:
        cleaned = str(raw_status or "").strip().lower()
        if not cleaned:
            return None
        definition = self.registry.require_object_type(object_type)
        if cleaned in definition.lifecycle:
            return cleaned
        alias = LIFECYCLE_STATUS_ALIASES.get(object_type, {}).get(cleaned)
        if alias in definition.lifecycle:
            return alias
        return None

    @staticmethod
    def _link_payload(row: BrandObjectLink) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "link_type": row.link_type,
            "from_object_type": row.from_object_type,
            "from_object_id": row.from_object_id,
            "to_object_type": row.to_object_type,
            "to_object_id": row.to_object_id,
            "source_action_record_id": (
                str(row.source_action_record_id)
                if row.source_action_record_id
                else None
            ),
            "extra_metadata": row.extra_metadata or {},
            "created_at": row.created_at.isoformat(),
        }

    @staticmethod
    def _row_properties(object_type: str, row: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        public_keys = SENSITIVE_OBJECT_PUBLIC_PROPERTIES.get(object_type)
        for column in row.__table__.columns:
            if public_keys is not None and column.name not in public_keys:
                continue
            value = getattr(row, column.name)
            if isinstance(value, UUID):
                payload[column.name] = str(value)
            elif isinstance(value, datetime):
                payload[column.name] = value.isoformat()
            else:
                payload[column.name] = value
        if object_type == "platform_answer":
            payload["answer_preview"] = _compact_text(
                str(getattr(row, "answer_text", "") or ""),
                limit=220,
            )
        elif object_type == "citation_source":
            payload["snippet_preview"] = _compact_text(
                str(getattr(row, "snippet", "") or ""),
                limit=180,
            )
        return payload


def _normalize_limit(value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_OBJECT_LIST_LIMIT
    return min(max(parsed, 1), MAX_OBJECT_LIST_LIMIT)


def _compact_text(value: str, *, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."
