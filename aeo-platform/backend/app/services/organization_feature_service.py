"""Organization feature entitlement helpers."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import Entity, EntityStatus, EntityVisibilityScope
from app.models.organization import Organization
from app.services.brand_association_circle_variant import is_amway_association_entity


FEATURE_AMWAYCHINA_CONSOLE = "amwaychina_console"

ALLOWED_FEATURE_FLAGS = {
    FEATURE_AMWAYCHINA_CONSOLE,
}


def normalize_feature_flags(value: Any) -> dict[str, bool]:
    if not isinstance(value, dict):
        return {}
    flags: dict[str, bool] = {}
    for key in ALLOWED_FEATURE_FLAGS:
        flags[key] = bool(value.get(key))
    return flags


def normalize_organization_feature_flags(value: Any) -> dict[str, bool]:
    return normalize_feature_flags(value)


def normalize_user_feature_flags(value: Any) -> dict[str, bool]:
    return normalize_feature_flags(value)


def organization_feature_enabled(value: Any, feature_key: str) -> bool:
    return bool(normalize_organization_feature_flags(value).get(feature_key))


def user_feature_enabled(value: Any, feature_key: str) -> bool:
    return bool(normalize_user_feature_flags(value).get(feature_key))


def feature_enabled_for_account(
    *,
    user_flags: Any,
    organization_flags: Any,
    feature_key: str,
) -> bool:
    return user_feature_enabled(user_flags, feature_key) or organization_feature_enabled(
        organization_flags,
        feature_key,
    )


def _parse_entity_aliases(entity: Entity) -> list[Any]:
    if not entity.aliases:
        return []
    try:
        value = json.loads(entity.aliases)
    except (TypeError, json.JSONDecodeError):
        return [entity.aliases]
    return value if isinstance(value, list) else [value]


async def list_organization_entities(
    db: AsyncSession,
    organization_id: Any,
) -> list[Entity]:
    """Always query Entity table — never trust possibly-noload relationship collections."""
    result = await db.execute(
        select(Entity).where(Entity.organization_id == organization_id)
    )
    return list(result.scalars().all())


async def find_amway_association_entities(
    db: AsyncSession,
    organization_id: Any,
) -> list[Entity]:
    entities = await list_organization_entities(db, organization_id)
    matched: list[Entity] = []
    for entity in entities:
        aliases = _parse_entity_aliases(entity)
        if is_amway_association_entity(
            name=entity.name,
            domain=entity.domain,
            aliases=aliases,
        ):
            matched.append(entity)
    return matched


async def ensure_amwaychina_console_entity(
    db: AsyncSession,
    organization: Organization,
) -> Entity:
    """Idempotent: reuse existing org Amway entity; only create when none exist.

    Uses an explicit Entity query (not ``organization.entities``) so a prior
    ``noload(Organization.entities)`` on the same Session cannot force a
    false-empty create path.
    """
    matched = await find_amway_association_entities(db, organization.id)
    if matched:
        # Prefer newest active, then any matched
        matched.sort(
            key=lambda e: (
                1 if e.status == EntityStatus.ACTIVE else 0,
                e.updated_at or e.created_at,
            ),
            reverse=True,
        )
        entity = matched[0]
        if entity.status != EntityStatus.ACTIVE:
            entity.status = EntityStatus.ACTIVE
        entity.visibility_scope = EntityVisibilityScope.ORGANIZATION
        entity.organization_id = organization.id
        entity.owner_user_id = None
        await db.flush()
        return entity

    # Re-check after potential concurrent create (dev double-mount / parallel GET)
    matched = await find_amway_association_entities(db, organization.id)
    if matched:
        matched.sort(key=lambda e: e.updated_at or e.created_at, reverse=True)
        return matched[0]

    entity = Entity(
        name="安利",
        aliases=json.dumps(
            ["安利", "安利中国", "纽崔莱", "Amway", "Amway China", "Nutrilite"],
            ensure_ascii=False,
        ),
        domain="https://www.amway.com.cn",
        industry="健康生活",
        description="安利中国专属品牌联想圈层 Console 中心品牌组",
        status=EntityStatus.ACTIVE,
        visibility_scope=EntityVisibilityScope.ORGANIZATION,
        owner_user_id=None,
        organization_id=organization.id,
    )
    db.add(entity)
    await db.flush()
    return entity
