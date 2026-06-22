"""Organization feature entitlement helpers."""

from __future__ import annotations

import json
from typing import Any

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


async def ensure_amwaychina_console_entity(
    db: AsyncSession,
    organization: Organization,
) -> Entity:
    for entity in organization.entities:
        aliases = []
        if entity.aliases:
            try:
                aliases = json.loads(entity.aliases)
            except (TypeError, json.JSONDecodeError):
                aliases = [entity.aliases]
        if is_amway_association_entity(
            name=entity.name,
            domain=entity.domain,
            aliases=aliases,
        ):
            if entity.status != EntityStatus.ACTIVE:
                entity.status = EntityStatus.ACTIVE
            entity.visibility_scope = EntityVisibilityScope.ORGANIZATION
            entity.organization_id = organization.id
            entity.owner_user_id = None
            await db.flush()
            return entity

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
