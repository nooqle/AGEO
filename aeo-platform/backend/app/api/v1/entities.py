"""Entity CRUD API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.schemas.entity import EntityCreate, EntityUpdate
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
        entity = await service.update_entity(entity_id, updates, current_user)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
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
