"""Sessions API endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.api.deps import get_db, get_current_user
from app.models.session import Session as SessionModel, SessionStatus
from app.schemas.session import SessionListResponse
from app.services.session_service import SessionService
from app.services.entity_service import EntityService

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: Optional[SessionStatus] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """获取会话列表。"""
    service = SessionService(db)
    return await service.list_sessions(
        viewer=current_user,
        limit=limit,
        offset=offset,
        status=status,
    )


@router.get("/by-entity/{entity_id}")
async def get_session_by_entity(
    entity_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """查询品牌实体关联的 Session（1:1 映射）。"""
    entity_service = EntityService(db)
    entity = await entity_service.get_entity(str(entity_id), current_user)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    service = SessionService(db)
    session = await service.get_latest_session_by_entity(entity_id, current_user)
    if not session:
        raise HTTPException(status_code=404, detail="No session found for this entity")
    return session


@router.post("")
async def create_session(
    entity_id: Optional[UUID] = Query(default=None, description="关联的品牌实体ID"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create new session, optionally linked to a brand entity."""
    # Validate entity_id exists if provided
    if entity_id:
        entity_service = EntityService(db)
        entity = await entity_service.get_entity(str(entity_id), current_user)
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")

        # 1:1 唯一性检查：如果 entity_id 已有 Session 则返回 409
        existing_conditions = [SessionModel.entity_id == entity_id]
        if entity.get("visibility_scope") == "organization":
            existing_stmt = select(SessionModel.id).where(*existing_conditions)
        else:
            existing_stmt = select(SessionModel.id).where(
                *existing_conditions,
                SessionModel.user_id == current_user.id,
            )
        existing = await db.execute(existing_stmt)
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=409,
                detail="该品牌已有关联的分析会话",
            )

    service = SessionService(db)
    session = await service.create_session(current_user, entity_id=entity_id)
    return session


@router.get("/{session_id}")
async def get_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get session details."""
    service = SessionService(db)
    session = await service.get_session(session_id, current_user)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.delete("/{session_id}")
async def delete_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete session."""
    service = SessionService(db)
    await service.delete_session(session_id, current_user)
    return {"status": "deleted"}
