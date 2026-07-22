"""Amwaychina flow recipe APIs (org / entity scoped production-line presets)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.v1.amwaychina_common import parse_uuid, require_amway_entity
from app.models.flow_topology import FlowTopologyRecord
from app.services import flow_topology_recipe_service as recipes
from sqlalchemy import select

router = APIRouter(tags=["amwaychina"])


class RecipeCreateBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = None
    # organization = org-wide; entity = brand/project (requires entity_id)
    scope: str = Field(default="entity", pattern="^(organization|entity)$")
    entity_id: str | None = None
    topology: dict[str, Any] | None = None
    # If true, copy topology from entity's current flow_topologies
    from_current: bool = False


class RecipeUpdateBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    topology: dict[str, Any] | None = None
    # Wave B4: overwrite recipe topology from entity's current production line
    from_current: bool = False


class RecipeApplyBody(BaseModel):
    expected_version: int | None = None


@router.get("/flow-recipes")
async def list_flow_recipes(
    entity_id: str | None = Query(
        None, description="Brand entity id — returns org + this entity recipes"
    ),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not entity_id:
        raise HTTPException(
            status_code=400,
            detail="请提供 entity_id 以列出组织与该品牌可见配方",
        )
    entity = await require_amway_entity(db, current_user, entity_id)
    if entity.organization_id is None:
        return {"recipes": []}
    rows = await recipes.list_recipes(
        db,
        organization_id=entity.organization_id,
        entity_id=entity.id,
    )
    return {"recipes": [recipes.recipe_to_dict(r) for r in rows]}


@router.post("/flow-recipes", status_code=201)
async def create_flow_recipe(
    body: RecipeCreateBody,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.scope == "entity":
        if not body.entity_id:
            raise HTTPException(status_code=400, detail="品牌级配方需要 entity_id")
        entity = await require_amway_entity(
            db, current_user, body.entity_id, manage=True
        )
        if entity.organization_id is None:
            raise HTTPException(status_code=400, detail="实体未绑定组织，无法创建配方")
        org_id = entity.organization_id
        entity_id = entity.id
        topology = body.topology
        if body.from_current:
            row = (
                await db.execute(
                    select(FlowTopologyRecord).where(
                        FlowTopologyRecord.entity_id == entity.id
                    )
                )
            ).scalar_one_or_none()
            topology = (
                row.topology
                if row is not None and isinstance(row.topology, dict)
                else {}
            )
        if topology is None:
            raise HTTPException(status_code=400, detail="请提供 topology 或 from_current")
    else:
        # organization scope — still need an entity for auth context
        if not body.entity_id:
            raise HTTPException(
                status_code=400,
                detail="创建组织级配方时请提供 entity_id 用于鉴权上下文",
            )
        entity = await require_amway_entity(
            db, current_user, body.entity_id, manage=True
        )
        if entity.organization_id is None:
            raise HTTPException(status_code=400, detail="实体未绑定组织，无法创建配方")
        org_id = entity.organization_id
        entity_id = None
        topology = body.topology
        if body.from_current:
            row = (
                await db.execute(
                    select(FlowTopologyRecord).where(
                        FlowTopologyRecord.entity_id == entity.id
                    )
                )
            ).scalar_one_or_none()
            topology = (
                row.topology
                if row is not None and isinstance(row.topology, dict)
                else {}
            )
        if topology is None:
            raise HTTPException(status_code=400, detail="请提供 topology 或 from_current")

    user_id = None
    try:
        user_id = UUID(str(current_user.id))
    except (TypeError, ValueError):
        user_id = None

    row = await recipes.create_recipe(
        db,
        organization_id=org_id,
        entity_id=entity_id,
        name=body.name,
        description=body.description,
        topology=topology,
        created_by_user_id=user_id,
    )
    # Wave B1: log save (use auth entity id for brand context)
    try:
        from app.services import flow_orchestration_event_service as orch_events

        log_entity_id = entity.id
        await orch_events.append_event(
            db,
            entity_id=log_entity_id,
            event_type="save_recipe",
            summary=f"另存配方「{row.name}」（{'组织' if row.entity_id is None else '本品牌'}）",
            payload={"recipe_id": str(row.id), "scope": "organization" if row.entity_id is None else "entity"},
            created_by_user_id=user_id,
        )
    except Exception:
        pass
    return recipes.recipe_to_dict(row)


@router.patch("/flow-recipes/{recipe_id}")
async def update_flow_recipe(
    recipe_id: str,
    body: RecipeUpdateBody,
    entity_id: str = Query(..., description="Auth context brand entity"),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entity = await require_amway_entity(db, current_user, entity_id, manage=True)
    if entity.organization_id is None:
        raise HTTPException(status_code=400, detail="实体未绑定组织")
    rid = parse_uuid(recipe_id, "recipe_id")
    row = await recipes.get_recipe(
        db, recipe_id=rid, organization_id=entity.organization_id
    )
    if row.entity_id is not None and row.entity_id != entity.id:
        raise HTTPException(status_code=403, detail="无权修改其他品牌的配方")
    topology = body.topology
    event_type = "update_recipe"
    if body.from_current:
        topo_row = (
            await db.execute(
                select(FlowTopologyRecord).where(
                    FlowTopologyRecord.entity_id == entity.id
                )
            )
        ).scalar_one_or_none()
        topology = (
            topo_row.topology
            if topo_row is not None and isinstance(topo_row.topology, dict)
            else {}
        )
        event_type = "overwrite_recipe"
    updated = await recipes.update_recipe(
        db,
        recipe=row,
        name=body.name,
        description=body.description,
        topology=topology,
    )
    try:
        from app.services import flow_orchestration_event_service as orch_events
        from uuid import UUID as _UUID

        user_id = None
        try:
            user_id = _UUID(str(current_user.id))
        except (TypeError, ValueError):
            user_id = None
        await orch_events.append_event(
            db,
            entity_id=entity.id,
            event_type=event_type,
            summary=(
                f"用当前生产线覆盖配方「{updated.name}」"
                if event_type == "overwrite_recipe"
                else f"更新配方「{updated.name}」"
            ),
            payload={"recipe_id": str(updated.id), "version": updated.version},
            created_by_user_id=user_id,
        )
    except Exception:
        pass
    return recipes.recipe_to_dict(updated)


@router.delete("/flow-recipes/{recipe_id}")
async def delete_flow_recipe(
    recipe_id: str,
    entity_id: str = Query(..., description="Auth context brand entity"),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entity = await require_amway_entity(db, current_user, entity_id, manage=True)
    if entity.organization_id is None:
        raise HTTPException(status_code=400, detail="实体未绑定组织")
    rid = parse_uuid(recipe_id, "recipe_id")
    row = await recipes.get_recipe(
        db, recipe_id=rid, organization_id=entity.organization_id
    )
    if row.entity_id is not None and row.entity_id != entity.id:
        raise HTTPException(status_code=403, detail="无权删除其他品牌的配方")
    await recipes.delete_recipe(db, recipe=row)
    return {"ok": True}


@router.post("/entities/{entity_id}/flow-recipes/{recipe_id}/apply")
async def apply_flow_recipe(
    entity_id: str,
    recipe_id: str,
    body: RecipeApplyBody | None = None,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Directly replace the entity production-line topology with the recipe."""
    entity = await require_amway_entity(db, current_user, entity_id, manage=True)
    if entity.organization_id is None:
        raise HTTPException(status_code=400, detail="实体未绑定组织")
    rid = parse_uuid(recipe_id, "recipe_id")
    recipe = await recipes.get_recipe(
        db, recipe_id=rid, organization_id=entity.organization_id
    )
    body = body or RecipeApplyBody()
    topology, version = await recipes.apply_recipe_to_entity(
        db,
        entity=entity,
        recipe=recipe,
        expected_version=body.expected_version,
    )
    try:
        from app.services import flow_orchestration_event_service as orch_events
        from uuid import UUID as _UUID

        user_id = None
        try:
            user_id = _UUID(str(current_user.id))
        except (TypeError, ValueError):
            user_id = None
        await orch_events.append_event(
            db,
            entity_id=entity.id,
            event_type="apply_recipe",
            summary=f"套用配方「{recipe.name}」",
            payload={"recipe_id": str(recipe.id), "recipe_name": recipe.name},
            created_by_user_id=user_id,
        )
    except Exception:
        pass
    return {
        "topology": topology,
        "version": version,
        "recipe_id": str(recipe.id),
        "recipe_name": recipe.name,
    }


@router.get("/entities/{entity_id}/orchestration-events")
async def list_orchestration_events(
    entity_id: str,
    limit: int = Query(20, ge=1, le=50),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Wave B1: recent visible orchestration changes."""
    from app.services import flow_orchestration_event_service as orch_events

    entity = await require_amway_entity(db, current_user, entity_id)
    rows = await orch_events.list_events(db, entity_id=entity.id, limit=limit)
    return {"events": [orch_events.event_to_dict(r) for r in rows]}
