"""Shared helpers for Amwaychina console API routers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.entity import Entity
from app.models.session import Session
from app.services.access_scope_service import AccessScopeService
from app.services.brand_association_circle_variant import is_amway_association_entity
from app.services.organization_feature_service import (
    FEATURE_AMWAYCHINA_CONSOLE,
    feature_enabled_for_account,
)


def parse_uuid(value: str, field_name: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UUID for {field_name}: {value}",
        ) from exc


def parse_optional_uuid(value: str | None, field_name: str) -> UUID | None:
    if not value:
        return None
    return parse_uuid(value, field_name)


def parse_optional_datetime(value: str | None, field_name: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid datetime for {field_name}: {value}",
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def entity_aliases(entity: Entity) -> list[Any]:
    if not entity.aliases:
        return []
    try:
        value = json.loads(entity.aliases)
    except (TypeError, json.JSONDecodeError):
        return [entity.aliases]
    return value if isinstance(value, list) else [value]


async def require_amway_entity(
    db: AsyncSession,
    current_user: Any,
    entity_id: str,
    *,
    manage: bool = False,
) -> Entity:
    entity_uuid = parse_uuid(entity_id, "entity_id")
    # Only org for access/feature checks — never selectin sessions/messages (auth OOM path).
    result = await db.execute(
        select(Entity)
        .options(selectinload(Entity.organization))
        .where(Entity.id == entity_uuid)
    )
    entity = result.scalar_one_or_none()
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    if not is_amway_association_entity(
        name=entity.name,
        domain=entity.domain,
        aliases=entity_aliases(entity),
    ):
        raise HTTPException(status_code=404, detail="Amway entity not found")
    if not AccessScopeService.can_access_entity(
        entity,
        current_user,
        allow_internal_admin_bypass=False,
    ):
        raise HTTPException(status_code=403, detail="无权访问该安利实体")
    if manage:
        if entity.owner_user_id is None:
            # Preserve the legacy session-owner permission without lazy loading
            # entity.sessions in an AsyncSession or fetching its full graph.
            can_manage = bool(
                await db.scalar(
                    select(
                        select(Session.id)
                        .where(
                            Session.entity_id == entity.id,
                            Session.user_id == current_user.id,
                        )
                        .exists()
                    )
                )
            )
        else:
            can_manage = AccessScopeService.can_manage_entity(
                entity,
                current_user,
                allow_internal_admin_bypass=False,
            )
        if not can_manage:
            raise HTTPException(status_code=403, detail="无权管理该安利实体")
    if not feature_enabled_for_account(
        user_flags=getattr(current_user, "feature_flags", None),
        organization_flags=getattr(entity.organization, "feature_flags", None),
        feature_key=FEATURE_AMWAYCHINA_CONSOLE,
    ):
        raise HTTPException(status_code=403, detail="当前账号未开通安利专项权限")
    return entity


def iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def load_projection_body(projection_payload: Any) -> dict[str, Any] | None:
    if not isinstance(projection_payload, dict):
        return None
    nested = projection_payload.get("association_circle_projection")
    if isinstance(nested, dict) and nested:
        return nested
    return None
