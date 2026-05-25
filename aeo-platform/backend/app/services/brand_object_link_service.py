"""Relationship writer for durable brand intelligence objects."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand_intelligence import BrandObjectLink
from app.ontology import OntologyRegistry, load_default_ontology
from app.services.brand_ontology_object_service import BrandOntologyObjectService


class BrandObjectLinkService:
    """Owns idempotent object relationship writes."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        registry: OntologyRegistry | None = None,
    ) -> None:
        self.db = db
        self.registry = registry or load_default_ontology()
        self.objects = BrandOntologyObjectService(db, registry=self.registry)

    async def ensure_link(
        self,
        *,
        entity_id: UUID,
        link_type: str,
        from_object_type: str,
        from_object_id: str,
        to_object_type: str,
        to_object_id: str,
        source_action_record_id: UUID | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> BrandObjectLink:
        self._validate_link_contract(
            link_type=link_type,
            from_object_type=from_object_type,
            from_object_id=from_object_id,
            to_object_type=to_object_type,
            to_object_id=to_object_id,
        )
        await self._validate_link_objects_exist(
            entity_id=entity_id,
            from_object_type=from_object_type,
            from_object_id=from_object_id,
            to_object_type=to_object_type,
            to_object_id=to_object_id,
        )
        query = select(BrandObjectLink).where(
            BrandObjectLink.entity_id == entity_id,
            BrandObjectLink.link_type == link_type,
            BrandObjectLink.from_object_type == from_object_type,
            BrandObjectLink.from_object_id == from_object_id,
            BrandObjectLink.to_object_type == to_object_type,
            BrandObjectLink.to_object_id == to_object_id,
        )
        row = (await self.db.execute(query)).scalar_one_or_none()
        if row is None:
            row = BrandObjectLink(
                entity_id=entity_id,
                link_type=link_type,
                from_object_type=from_object_type,
                from_object_id=from_object_id,
                to_object_type=to_object_type,
                to_object_id=to_object_id,
            )
            self.db.add(row)
        if source_action_record_id is not None and row.source_action_record_id is None:
            row.source_action_record_id = source_action_record_id
        if extra_metadata is not None:
            row.extra_metadata = {**(row.extra_metadata or {}), **extra_metadata}
        return row

    def _validate_link_contract(
        self,
        *,
        link_type: str,
        from_object_type: str,
        from_object_id: str,
        to_object_type: str,
        to_object_id: str,
    ) -> None:
        definition = self.registry.require_link_type(link_type)
        if definition.from_object != from_object_type:
            raise ValueError(
                f"Link {link_type} expects from_object={definition.from_object}, "
                f"got {from_object_type}"
            )
        if definition.to_object != to_object_type:
            raise ValueError(
                f"Link {link_type} expects to_object={definition.to_object}, "
                f"got {to_object_type}"
            )
        if not str(from_object_id or "").strip():
            raise ValueError("from_object_id is required")
        if not str(to_object_id or "").strip():
            raise ValueError("to_object_id is required")

    async def _validate_link_objects_exist(
        self,
        *,
        entity_id: UUID,
        from_object_type: str,
        from_object_id: str,
        to_object_type: str,
        to_object_id: str,
    ) -> None:
        from_object = await self.objects.get_object(
            entity_id=entity_id,
            object_type=from_object_type,
            object_id=from_object_id,
        )
        if from_object is None:
            raise ValueError(
                f"Link source object not found: {from_object_type}/{from_object_id}"
            )
        to_object = await self.objects.get_object(
            entity_id=entity_id,
            object_type=to_object_type,
            object_id=to_object_id,
        )
        if to_object is None:
            raise ValueError(
                f"Link target object not found: {to_object_type}/{to_object_id}"
            )
