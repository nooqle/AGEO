"""Entity service for brand entity CRUD operations.

Uses SQLAlchemy for persistent storage. Falls back to in-memory
storage if no DB session is provided (backward compat).
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4, UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import Entity, EntityStatus
from app.models.monitoring_alert import MonitoringAlert
from app.models.monitoring_schedule import MonitoringSchedule
from app.models.session import Session
from app.models.snapshot import AnalysisSnapshot

logger = logging.getLogger(__name__)

# In-memory fallback (used when no DB session)
_entities: dict[str, dict[str, Any]] = {}


class EntityService:
    """Manages brand entity CRUD operations."""

    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    def _model_to_dict(self, entity: Entity) -> dict[str, Any]:
        """Convert Entity model to dict."""
        aliases = []
        if entity.aliases:
            try:
                aliases = json.loads(entity.aliases)
            except (json.JSONDecodeError, TypeError):
                aliases = [entity.aliases] if entity.aliases else []

        return {
            "id": str(entity.id),
            "name": entity.name,
            "aliases": aliases,
            "domain": entity.domain or "",
            "industry": entity.industry or "",
            "description": entity.description or "",
            "last_analyzed": entity.last_analyzed.isoformat() if entity.last_analyzed else None,
            "status": entity.status.value if entity.status else "pending",
            "created_at": entity.created_at.isoformat() if entity.created_at else None,
            "updated_at": entity.updated_at.isoformat() if entity.updated_at else None,
        }

    async def list_entities(self) -> list[dict[str, Any]]:
        if self.db:
            result = await self.db.execute(select(Entity).order_by(Entity.created_at.desc()))
            entities = result.scalars().all()
            return [self._model_to_dict(e) for e in entities]
        return list(_entities.values())

    async def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        if self.db:
            try:
                entity = await self.db.get(Entity, UUID(entity_id))
            except ValueError:
                return None
            return self._model_to_dict(entity) if entity else None
        return _entities.get(entity_id)

    async def create_entity(self, data: dict[str, Any]) -> dict[str, Any]:
        if self.db:
            try:
                aliases = data.get("aliases", [])
                entity = Entity(
                    name=data["name"],
                    aliases=json.dumps(aliases, ensure_ascii=False) if aliases else None,
                    domain=data.get("domain", ""),
                    industry=data.get("industry", ""),
                    description=data.get("description", ""),
                    status=EntityStatus.PENDING,
                )
                self.db.add(entity)
                await self.db.commit()
                await self.db.refresh(entity)
                logger.info("[Entity] Created: %s (id=%s)", entity.name, entity.id)
                return self._model_to_dict(entity)
            except Exception:
                await self.db.rollback()
                raise

        # Fallback: in-memory
        entity_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        entity = {
            "id": entity_id,
            "name": data["name"],
            "aliases": data.get("aliases", []),
            "domain": data.get("domain", ""),
            "industry": data.get("industry", ""),
            "description": data.get("description", ""),
            "last_analyzed": None,
            "status": "pending",
            "created_at": now,
            "updated_at": now,
        }
        _entities[entity_id] = entity
        logger.info("[Entity] Created (in-memory): %s (id=%s)", entity["name"], entity_id)
        return entity

    async def update_entity(
        self, entity_id: str, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        if self.db:
            try:
                entity = await self.db.get(Entity, UUID(entity_id))
            except ValueError:
                return None
            if not entity:
                return None
            try:
                if "name" in data and data["name"] is not None:
                    entity.name = data["name"]
                if "aliases" in data and data["aliases"] is not None:
                    entity.aliases = json.dumps(data["aliases"], ensure_ascii=False)
                if "domain" in data and data["domain"] is not None:
                    entity.domain = data["domain"]
                if "industry" in data and data["industry"] is not None:
                    entity.industry = data["industry"]
                if "description" in data and data["description"] is not None:
                    entity.description = data["description"]
                if "status" in data and data["status"] is not None:
                    try:
                        entity.status = EntityStatus(data["status"])
                    except ValueError:
                        logger.warning(f"[Entity] Invalid status value: {data['status']}, skipping")
                if "last_analyzed" in data and data["last_analyzed"] is not None:
                    entity.last_analyzed = data["last_analyzed"]
                entity.updated_at = datetime.now(timezone.utc)
                await self.db.commit()
                await self.db.refresh(entity)
                logger.info("[Entity] Updated: %s (id=%s)", entity.name, entity_id)
                return self._model_to_dict(entity)
            except Exception:
                await self.db.rollback()
                raise

        # Fallback: in-memory
        entity = _entities.get(entity_id)
        if not entity:
            return None
        for key, value in data.items():
            if value is not None and key in entity:
                entity[key] = value
        entity["updated_at"] = datetime.now(timezone.utc).isoformat()
        _entities[entity_id] = entity
        logger.info("[Entity] Updated (in-memory): %s (id=%s)", entity["name"], entity_id)
        return entity

    async def delete_entity(self, entity_id: str) -> bool:
        if self.db:
            try:
                entity = await self.db.get(Entity, UUID(entity_id))
            except ValueError:
                return False
            if not entity:
                return False
            try:
                name = entity.name
                uid = UUID(entity_id)
                # Bulk-delete dependents via SQL DELETE to avoid ORM
                # relationship interference (backref tries SET NULL on
                # NOT NULL columns, causing IntegrityError).
                await self.db.execute(
                    delete(MonitoringAlert).where(MonitoringAlert.entity_id == uid)
                )
                await self.db.execute(
                    delete(MonitoringSchedule).where(MonitoringSchedule.entity_id == uid)
                )
                await self.db.execute(
                    delete(AnalysisSnapshot).where(AnalysisSnapshot.entity_id == uid)
                )
                # Delete sessions (messages cascade via ORM delete-orphan)
                result = await self.db.execute(
                    select(Session).where(Session.entity_id == uid)
                )
                sessions = result.scalars().all()
                for s in sessions:
                    await self.db.delete(s)
                await self.db.delete(entity)
                await self.db.commit()
                logger.info("[Entity] Deleted: %s (id=%s, sessions=%d)", name, entity_id, len(sessions))
                return True
            except Exception:
                await self.db.rollback()
                raise

        # Fallback: in-memory
        if entity_id in _entities:
            name = _entities[entity_id]["name"]
            del _entities[entity_id]
            logger.info("[Entity] Deleted (in-memory): %s (id=%s)", name, entity_id)
            return True
        return False
