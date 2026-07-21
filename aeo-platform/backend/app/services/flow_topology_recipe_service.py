"""CRUD + apply for flow topology recipes (org / entity scope)."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import Entity
from app.models.flow_topology import FlowTopologyRecord
from app.models.flow_topology_recipe import FlowTopologyRecipe
from app.workflow.topology_resolver import validate_topology_document

logger = logging.getLogger(__name__)


def _normalize_topology(raw: Any) -> dict[str, Any]:
    return validate_topology_document(raw if isinstance(raw, dict) else None)


def recipe_to_dict(row: FlowTopologyRecipe) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "organization_id": str(row.organization_id),
        "entity_id": str(row.entity_id) if row.entity_id else None,
        "scope": "entity" if row.entity_id else "organization",
        "name": row.name,
        "description": row.description,
        "topology": row.topology if isinstance(row.topology, dict) else {},
        "version": int(row.version or 1),
        "created_by_user_id": (
            str(row.created_by_user_id) if row.created_by_user_id else None
        ),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def list_recipes(
    db: AsyncSession,
    *,
    organization_id: UUID,
    entity_id: UUID | None = None,
) -> list[FlowTopologyRecipe]:
    """Org-wide recipes + optional entity-scoped recipes for this brand."""
    stmt = select(FlowTopologyRecipe).where(
        FlowTopologyRecipe.organization_id == organization_id
    )
    if entity_id is not None:
        stmt = stmt.where(
            or_(
                FlowTopologyRecipe.entity_id.is_(None),
                FlowTopologyRecipe.entity_id == entity_id,
            )
        )
    else:
        stmt = stmt.where(FlowTopologyRecipe.entity_id.is_(None))
    # Org-wide first, then brand-scoped; newest first within group
    stmt = stmt.order_by(
        FlowTopologyRecipe.entity_id.is_(None).desc(),
        FlowTopologyRecipe.updated_at.desc(),
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_recipe(
    db: AsyncSession,
    *,
    recipe_id: UUID,
    organization_id: UUID,
) -> FlowTopologyRecipe:
    row = (
        await db.execute(
            select(FlowTopologyRecipe).where(
                FlowTopologyRecipe.id == recipe_id,
                FlowTopologyRecipe.organization_id == organization_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="配方不存在")
    return row


async def create_recipe(
    db: AsyncSession,
    *,
    organization_id: UUID,
    entity_id: UUID | None,
    name: str,
    description: str | None,
    topology: dict[str, Any],
    created_by_user_id: UUID | None,
) -> FlowTopologyRecipe:
    name_clean = str(name or "").strip()
    if not name_clean:
        raise HTTPException(status_code=400, detail="配方名称不能为空")
    if len(name_clean) > 120:
        raise HTTPException(status_code=400, detail="配方名称过长（上限 120）")
    try:
        normalized = _normalize_topology(topology)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    row = FlowTopologyRecipe(
        organization_id=organization_id,
        entity_id=entity_id,
        name=name_clean,
        description=(str(description).strip() if description else None) or None,
        topology=normalized,
        created_by_user_id=created_by_user_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def update_recipe(
    db: AsyncSession,
    *,
    recipe: FlowTopologyRecipe,
    name: str | None = None,
    description: str | None = None,
    topology: dict[str, Any] | None = None,
) -> FlowTopologyRecipe:
    if name is not None:
        name_clean = str(name).strip()
        if not name_clean:
            raise HTTPException(status_code=400, detail="配方名称不能为空")
        recipe.name = name_clean
    if description is not None:
        recipe.description = str(description).strip() or None
    if topology is not None:
        try:
            recipe.topology = _normalize_topology(topology)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        recipe.version = int(recipe.version or 1) + 1
    await db.commit()
    await db.refresh(recipe)
    return recipe


async def delete_recipe(db: AsyncSession, *, recipe: FlowTopologyRecipe) -> None:
    await db.delete(recipe)
    await db.commit()


async def apply_recipe_to_entity(
    db: AsyncSession,
    *,
    entity: Entity,
    recipe: FlowTopologyRecipe,
    expected_version: int | None = None,
) -> tuple[dict[str, Any], int]:
    """Replace entity flow_topologies with recipe topology (direct swap)."""
    if recipe.entity_id is not None and recipe.entity_id != entity.id:
        raise HTTPException(
            status_code=400,
            detail="该配方仅适用于其他品牌项目，不能套用到当前品牌",
        )
    if entity.organization_id is None or recipe.organization_id != entity.organization_id:
        raise HTTPException(status_code=403, detail="配方不属于当前组织")

    try:
        normalized = _normalize_topology(recipe.topology)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    row = (
        await db.execute(
            select(FlowTopologyRecord).where(
                FlowTopologyRecord.entity_id == entity.id
            )
        )
    ).scalar_one_or_none()

    if row is None:
        if expected_version is not None and int(expected_version) != 0:
            raise HTTPException(
                status_code=409,
                detail="拓扑版本冲突：记录不存在，请重新加载。",
            )
        row = FlowTopologyRecord(entity_id=entity.id, topology=normalized, version=1)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return normalized, int(row.version or 1)

    if expected_version is not None and int(expected_version) != int(row.version or 1):
        raise HTTPException(
            status_code=409,
            detail=(
                f"拓扑版本冲突：期望 version={expected_version}，"
                f"当前 version={row.version}。"
            ),
        )
    row.topology = normalized
    row.version = int(row.version or 1) + 1
    await db.commit()
    await db.refresh(row)
    return normalized, int(row.version or 1)
