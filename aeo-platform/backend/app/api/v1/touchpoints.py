"""Touchpoint API endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.touchpoint_service import TouchpointService

router = APIRouter(prefix="/touchpoints", tags=["touchpoints"])


@router.get("/tree")
async def get_touchpoint_tree(
    brand_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Get touchpoint tree for a brand."""
    service = TouchpointService(db)
    return await service.get_tree(brand_id)
