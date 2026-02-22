"""Outputs API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.api.deps import get_db, get_current_user
from app.services.session_service import SessionService
from app.services.output_service import OutputService

router = APIRouter(prefix="/sessions/{session_id}/outputs", tags=["outputs"])


@router.get("")
async def get_outputs(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get all outputs."""
    session_service = SessionService(db)
    session = await session_service.get_session(session_id, current_user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    service = OutputService(db)
    outputs = await service.get_outputs(session_id)
    return outputs


@router.get("/{output_id}")
async def get_output(
    session_id: UUID,
    output_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get single output details."""
    session_service = SessionService(db)
    session = await session_service.get_session(session_id, current_user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    service = OutputService(db)
    output = await service.get_output(session_id, output_id)
    if not output:
        raise HTTPException(status_code=404, detail="Output not found")
    return output


@router.get("/{output_id}/export")
async def export_output(
    session_id: UUID,
    output_id: UUID,
    format: str = "pdf",
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Export output."""
    session_service = SessionService(db)
    session = await session_service.get_session(session_id, current_user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    service = OutputService(db)
    try:
        file_path = await service.export_output(session_id, output_id, format)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Output not found")
    except ValueError:
        raise HTTPException(status_code=400, detail="Unsupported format")
    return FileResponse(file_path)
