"""Editable Amway entity lexicon service."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.amway_entity_lexicon import AmwayEntityLexiconOverride
from app.models.entity import Entity
from app.ontology import (
    AmwayEntityDefinition,
    AmwayEntityOntologyRegistry,
    load_default_amway_entity_ontology,
)


EDITABLE_REVIEW_STATUSES = {"approved", "pending_review", "rejected", "merged"}


class AmwayEntityLexiconService:
    """Provides a persisted overlay on top of the bundled Amway ontology."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        base_registry: AmwayEntityOntologyRegistry | None = None,
    ) -> None:
        self.db = db
        self.base_registry = base_registry or load_default_amway_entity_ontology()

    async def registry_for_entity(self, entity_id: UUID) -> AmwayEntityOntologyRegistry:
        entries = await self.merged_entities_for_entity(entity_id)
        definition = self.base_registry.definition.model_copy(
            update={"entities": tuple(entries)}
        )
        return AmwayEntityOntologyRegistry(definition)

    async def payload_for_entity(self, entity_id: UUID) -> dict[str, Any]:
        overrides = await self._overrides_for_entity(entity_id)
        overrides_by_id = {item.lexicon_entity_id: item for item in overrides}
        deleted_ids = {
            item.lexicon_entity_id for item in overrides if bool(item.is_deleted)
        }
        entries = await self.merged_entities_for_entity(entity_id)
        default_ids = {item.entity_id for item in self.base_registry.entities}
        return {
            "ontology_id": self.base_registry.definition.ontology_id,
            "version": self.base_registry.definition.version,
            "entity_types": [
                item.model_dump() for item in self.base_registry.entity_types
            ],
            "entries": [
                _entry_to_payload(
                    entry,
                    origin=(
                        "custom"
                        if entry.entity_id not in default_ids
                        else (
                            "overridden"
                            if entry.entity_id in overrides_by_id
                            else "default"
                        )
                    ),
                    deleted=False,
                    updated_at=(
                        _iso(overrides_by_id[entry.entity_id].updated_at)
                        if entry.entity_id in overrides_by_id
                        else None
                    ),
                )
                for entry in entries
            ],
            "deleted_entry_ids": sorted(deleted_ids),
        }

    async def merged_entities_for_entity(
        self,
        entity_id: UUID,
    ) -> list[AmwayEntityDefinition]:
        merged_by_id = {item.entity_id: item for item in self.base_registry.entities}
        for override in await self._overrides_for_entity(entity_id):
            if override.is_deleted:
                merged_by_id.pop(override.lexicon_entity_id, None)
                continue
            merged_by_id[override.lexicon_entity_id] = _override_to_definition(
                override,
                base=self.base_registry.get_entity(override.lexicon_entity_id),
            )
        return list(merged_by_id.values())

    async def create_entry(
        self,
        *,
        entity: Entity,
        current_user_id: UUID | None,
        payload: dict[str, Any],
    ) -> AmwayEntityLexiconOverride:
        canonical_name = _required_text(payload.get("canonical_name"), "canonical_name")
        entity_type = _required_text(payload.get("entity_type"), "entity_type")
        self.base_registry.require_entity_type(entity_type)
        now = datetime.now(timezone.utc)
        row = AmwayEntityLexiconOverride(
            entity_id=entity.id,
            organization_id=entity.organization_id,
            lexicon_entity_id=str(
                payload.get("entity_id") or f"custom_{uuid.uuid4().hex[:20]}"
            ),
            canonical_name=canonical_name,
            entity_type=entity_type,
            aliases=_string_list(payload.get("aliases")),
            description=_text(payload.get("description")),
            related_terms=_string_list(payload.get("related_terms")),
            graph_policy=_graph_policy_for_payload(payload, entity_type),
            source_policy=_source_policy_for_payload(payload),
            review_status=_review_status(payload.get("review_status")),
            is_deleted=False,
            created_by_user_id=current_user_id,
            updated_by_user_id=current_user_id,
            created_at=now,
            updated_at=now,
        )
        _override_to_definition(row, base=None)
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def update_entry(
        self,
        *,
        entity: Entity,
        lexicon_entity_id: str,
        current_user_id: UUID | None,
        payload: dict[str, Any],
    ) -> AmwayEntityLexiconOverride:
        entity_id = _required_text(lexicon_entity_id, "entity_id")
        base = self.base_registry.get_entity(entity_id)
        row = await self._override_for_entry(entity.id, entity_id)
        if row is None:
            if base is None:
                raise ValueError("实体词不存在。")
            row = _row_from_base_entity(
                entity=entity,
                base=base,
                current_user_id=current_user_id,
            )
            self.db.add(row)

        if "canonical_name" in payload:
            row.canonical_name = _required_text(
                payload.get("canonical_name"), "canonical_name"
            )
        if "entity_type" in payload:
            entity_type = _required_text(payload.get("entity_type"), "entity_type")
            self.base_registry.require_entity_type(entity_type)
            row.entity_type = entity_type
        if "aliases" in payload:
            row.aliases = _string_list(payload.get("aliases"))
        if "description" in payload:
            row.description = _text(payload.get("description"))
        if "related_terms" in payload:
            row.related_terms = _string_list(payload.get("related_terms"))
        if "graph_policy" in payload:
            row.graph_policy = _graph_policy_for_payload(payload, row.entity_type)
        if "review_status" in payload:
            row.review_status = _review_status(payload.get("review_status"))
        row.source_policy = _source_policy_for_payload(payload, base=row.source_policy)
        row.is_deleted = False
        row.updated_by_user_id = current_user_id
        row.updated_at = datetime.now(timezone.utc)
        _override_to_definition(row, base=base)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def delete_entry(
        self,
        *,
        entity: Entity,
        lexicon_entity_id: str,
        current_user_id: UUID | None,
    ) -> AmwayEntityLexiconOverride:
        entity_id = _required_text(lexicon_entity_id, "entity_id")
        base = self.base_registry.get_entity(entity_id)
        row = await self._override_for_entry(entity.id, entity_id)
        if row is None:
            if base is None:
                raise ValueError("实体词不存在。")
            row = _row_from_base_entity(
                entity=entity,
                base=base,
                current_user_id=current_user_id,
            )
            self.db.add(row)
        row.is_deleted = True
        row.updated_by_user_id = current_user_id
        row.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def _overrides_for_entity(
        self,
        entity_id: UUID,
    ) -> list[AmwayEntityLexiconOverride]:
        result = await self.db.execute(
            select(AmwayEntityLexiconOverride)
            .where(AmwayEntityLexiconOverride.entity_id == entity_id)
            .order_by(AmwayEntityLexiconOverride.created_at)
        )
        return list(result.scalars().all())

    async def _override_for_entry(
        self,
        entity_id: UUID,
        lexicon_entity_id: str,
    ) -> AmwayEntityLexiconOverride | None:
        result = await self.db.execute(
            select(AmwayEntityLexiconOverride).where(
                AmwayEntityLexiconOverride.entity_id == entity_id,
                AmwayEntityLexiconOverride.lexicon_entity_id == lexicon_entity_id,
            )
        )
        return result.scalar_one_or_none()


def _entry_to_payload(
    entry: AmwayEntityDefinition,
    *,
    origin: str,
    deleted: bool,
    updated_at: str | None,
) -> dict[str, Any]:
    payload = entry.model_dump()
    payload.update(
        {
            "id": entry.entity_id,
            "origin": origin,
            "is_deleted": deleted,
            "updated_at": updated_at,
        }
    )
    return payload


def _override_to_definition(
    row: AmwayEntityLexiconOverride,
    *,
    base: AmwayEntityDefinition | None,
) -> AmwayEntityDefinition:
    return AmwayEntityDefinition.model_validate(
        {
            "entity_id": row.lexicon_entity_id,
            "canonical_name": row.canonical_name
            or (base.canonical_name if base else ""),
            "entity_type": row.entity_type or (base.entity_type if base else ""),
            "aliases": tuple(
                _string_list(
                    row.aliases
                    if row.aliases is not None
                    else base.aliases if base else []
                )
            ),
            "description": row.description or (base.description if base else ""),
            "related_terms": tuple(
                _string_list(
                    row.related_terms
                    if row.related_terms is not None
                    else base.related_terms if base else []
                )
            ),
            "graph_policy": row.graph_policy
            or (
                base.graph_policy.model_dump()
                if base
                else _default_graph_policy(row.entity_type)
            ),
            "source_policy": row.source_policy
            or (base.source_policy.model_dump() if base else _default_source_policy()),
            "review_status": row.review_status
            or (base.review_status if base else "approved"),
        }
    )


def _row_from_base_entity(
    *,
    entity: Entity,
    base: AmwayEntityDefinition,
    current_user_id: UUID | None,
) -> AmwayEntityLexiconOverride:
    now = datetime.now(timezone.utc)
    return AmwayEntityLexiconOverride(
        entity_id=entity.id,
        organization_id=entity.organization_id,
        lexicon_entity_id=base.entity_id,
        canonical_name=base.canonical_name,
        entity_type=base.entity_type,
        aliases=list(base.aliases),
        description=base.description,
        related_terms=list(base.related_terms),
        graph_policy=base.graph_policy.model_dump(),
        source_policy=base.source_policy.model_dump(),
        review_status=base.review_status,
        is_deleted=False,
        created_by_user_id=current_user_id,
        updated_by_user_id=current_user_id,
        created_at=now,
        updated_at=now,
    )


def _graph_policy_for_payload(
    payload: dict[str, Any], entity_type: str
) -> dict[str, str]:
    graph_policy = payload.get("graph_policy")
    if isinstance(graph_policy, dict):
        return {
            "main_orbit": _text(graph_policy.get("main_orbit"))
            or _default_graph_policy(entity_type)["main_orbit"],
            "risk_view": _text(graph_policy.get("risk_view"))
            or _default_graph_policy(entity_type)["risk_view"],
            "target_gap_view": _text(graph_policy.get("target_gap_view"))
            or _default_graph_policy(entity_type)["target_gap_view"],
        }
    return _default_graph_policy(entity_type)


def _default_graph_policy(entity_type: str) -> dict[str, str]:
    if entity_type == "CenterBrand":
        return {
            "main_orbit": "always_center",
            "risk_view": "not_allowed",
            "target_gap_view": "not_allowed",
        }
    if entity_type == "RiskLabel":
        return {
            "main_orbit": "not_allowed",
            "risk_view": "allowed",
            "target_gap_view": "not_allowed",
        }
    if entity_type in {"BrandStrategy", "FourValue", "FlowerDimension"}:
        return {
            "main_orbit": "evidence_only",
            "risk_view": "not_allowed",
            "target_gap_view": "allowed",
        }
    return {
        "main_orbit": "allowed_with_answer_evidence",
        "risk_view": "not_allowed",
        "target_gap_view": "allowed",
    }


def _source_policy_for_payload(
    payload: dict[str, Any],
    *,
    base: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_policy = payload.get("source_policy")
    if isinstance(source_policy, dict):
        return {
            "source_kind": _text(source_policy.get("source_kind")) or "manual",
            "source_document_section": _text(
                source_policy.get("source_document_section")
            )
            or "amwaychina_entity_lexicon",
            "user_confirmed": bool(source_policy.get("user_confirmed", True)),
        }
    if isinstance(base, dict):
        next_policy = dict(base)
        next_policy["user_confirmed"] = True
        return next_policy
    return _default_source_policy()


def _default_source_policy() -> dict[str, Any]:
    return {
        "source_kind": "manual",
        "source_document_section": "amwaychina_entity_lexicon",
        "user_confirmed": True,
    }


def _review_status(value: Any) -> str:
    status = _text(value) or "approved"
    if status not in EDITABLE_REVIEW_STATUSES:
        raise ValueError("review_status 不合法。")
    return status


def _required_text(value: Any, field_name: str) -> str:
    text = _text(value)
    if not text:
        raise ValueError(f"{field_name} 不能为空。")
    return text


def _text(value: Any) -> str:
    return str(value or "").strip()


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items: Iterable[Any] = value.split(",")
    elif isinstance(value, Iterable):
        raw_items = value
    else:
        raw_items = [value]
    items: list[str] = []
    seen: set[str] = set()
    for raw in raw_items:
        text = _text(raw)
        if not text or text in seen:
            continue
        items.append(text)
        seen.add(text)
    return items


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
