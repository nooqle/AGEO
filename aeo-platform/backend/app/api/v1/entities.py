"""Entity CRUD API endpoints."""

import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.schemas.entity import EntityCreate, EntityUpdate
from app.services.brand_action_service import BrandActionService
from app.services.entity_service import EntityService

router = APIRouter(prefix="/entities", tags=["entities"])


@router.get("/")
async def list_entities(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List all brand entities."""
    service = EntityService(db)
    return await service.list_entities(
        current_user,
        allow_internal_admin_bypass=False,
    )


@router.get("/{entity_id}")
async def get_entity(
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get entity by ID."""
    service = EntityService(db)
    entity = await service.get_entity(
        entity_id,
        current_user,
        allow_internal_admin_bypass=False,
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


@router.post("/", status_code=201)
async def create_entity(
    data: EntityCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a new brand entity."""
    service = EntityService(db)
    try:
        return await service.create_entity(data.model_dump(), current_user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{entity_id}")
async def update_entity(
    entity_id: str,
    data: EntityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Update an existing entity."""
    service = EntityService(db)
    updates = data.model_dump(exclude_none=True)
    try:
        entity = await service.update_entity(
            entity_id,
            updates,
            current_user,
            commit=False,
        )
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        if updates:
            action_service = BrandActionService(db)
            entity_uuid = UUID(str(entity["id"]))
            await action_service.record_applied_action(
                entity_id=entity_uuid,
                user_id=current_user.id,
                actor_type="user",
                origin_surface="entity_api",
                origin_event_id=_entity_update_origin_event_id(entity["id"], updates),
                action_type="update_brand_profile",
                input_payload={
                    "actor_id": str(current_user.id),
                    "profile_patch": updates,
                },
                output_payload={
                    "updated_fields": sorted(updates.keys()),
                },
                decision_type="update_brand_profile",
                decision_key="entity_profile_update",
            )
        await db.commit()
    except PermissionError as exc:
        await db.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return entity


@router.delete("/{entity_id}", status_code=204)
async def delete_entity(
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete an entity."""
    service = EntityService(db)
    try:
        deleted = await service.delete_entity(entity_id, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Entity not found")


def _entity_update_origin_event_id(entity_id: str, updates: dict) -> str:
    canonical = json.dumps(
        {"entity_id": str(entity_id), "updates": updates},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:16]
    return f"entity-update:{entity_id}:{digest}"
