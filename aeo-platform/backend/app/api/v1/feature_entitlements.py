from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.entity import Entity, EntityStatus
from app.models.organization import Organization, OrganizationStatus
from app.services.brand_association_circle_variant import (
    AMWAY_ASSOCIATION_DASHBOARD_VARIANT,
    build_amway_association_context,
)
from app.services.organization_feature_service import (
    FEATURE_AMWAYCHINA_CONSOLE,
    ensure_amwaychina_console_entity,
    feature_enabled_for_account,
    find_amway_association_entities,
)

router = APIRouter(prefix="/feature-entitlements", tags=["feature-entitlements"])


def _entity_aliases(entity: Entity) -> list[Any]:
    if not entity.aliases:
        return []
    try:
        value = json.loads(entity.aliases)
    except (TypeError, json.JSONDecodeError):
        return [entity.aliases]
    return value if isinstance(value, list) else [value]


def _disabled_payload(reason: str) -> dict[str, Any]:
    return {
        "enabled": False,
        "reason": reason,
        "entity_id": None,
        "entity_name": None,
        "dashboard_variant": AMWAY_ASSOCIATION_DASHBOARD_VARIANT,
        "center_terms": [],
    }


@router.get("/amwaychina")
async def get_amwaychina_entitlement(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if current_user.organization_id is None:
        return _disabled_payload("organization_required")

    # Query Organization alone — do not depend on relationship collections that
    # may have been noload'd on the same Session during get_current_user.
    result = await db.execute(
        select(Organization).where(Organization.id == current_user.organization_id)
    )
    organization = result.scalar_one_or_none()
    if organization is None or organization.status != OrganizationStatus.ACTIVE:
        return _disabled_payload("organization_inactive")

    if not feature_enabled_for_account(
        user_flags=getattr(current_user, "feature_flags", None),
        organization_flags=organization.feature_flags,
        feature_key=FEATURE_AMWAYCHINA_CONSOLE,
    ):
        return _disabled_payload("feature_not_enabled")

    # Always list entities via Entity table (idempotent; survives identity-map noload).
    matched = await find_amway_association_entities(db, organization.id)
    amway_entities: list[tuple[Entity, list[Any]]] = []
    for entity in matched:
        if entity.status != EntityStatus.ACTIVE:
            continue
        amway_entities.append((entity, _entity_aliases(entity)))

    if not amway_entities:
        entity = await ensure_amwaychina_console_entity(db, organization)
        await db.commit()
        await db.refresh(entity)
        aliases = _entity_aliases(entity)
        amway_entities.append((entity, aliases))

    entity, aliases = sorted(
        amway_entities,
        key=lambda item: item[0].updated_at,
        reverse=True,
    )[0]
    context = build_amway_association_context(
        name=entity.name,
        domain=entity.domain,
        aliases=aliases,
    ) or {}
    return {
        "enabled": True,
        "reason": "enabled",
        "entity_id": str(entity.id),
        "entity_name": entity.name,
        "dashboard_variant": context.get(
            "dashboard_variant",
            AMWAY_ASSOCIATION_DASHBOARD_VARIANT,
        ),
        "center_terms": context.get("center_terms", []),
    }
