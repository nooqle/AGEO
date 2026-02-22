"""Messages API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional

from app.api.deps import get_db, get_current_user
from app.services.session_service import SessionService
from app.services.message_service import MessageService
from app.services.agent_orchestrator import AgentOrchestrator

router = APIRouter(prefix="/sessions/{session_id}/messages", tags=["messages"])


@router.get("")
async def get_messages(
    session_id: UUID,
    limit: int = 50,
    before: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get message list."""
    session_service = SessionService(db)
    session = await session_service.get_session(session_id, current_user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    service = MessageService(db)
    messages = await service.get_messages(session_id, limit=limit, before=before)
    return messages


@router.post("")
async def send_message(
    session_id: UUID,
    message: dict,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Send user message.

    Message will be saved, Agent processing runs in background.
    Real-time progress pushed via WebSocket.
    """
    session_service = SessionService(db)
    session = await session_service.get_session(session_id, current_user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    orchestrator = AgentOrchestrator(str(session_id), db)
    background_tasks.add_task(
        process_message_task,
        orchestrator,
        message.get("content", ""),
    )

    return {"status": "processing", "message": "Message received, processing"}


async def process_message_task(orchestrator: AgentOrchestrator, content: str):
    """Background task: process message."""
    async for event in orchestrator.process_message(content):
        pass  # Events already pushed via WebSocket


@router.delete("/{message_id}/after")
async def rollback_to_message(
    session_id: UUID,
    message_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Rollback: delete all content after specified message.
    """
    session_service = SessionService(db)
    session = await session_service.get_session(session_id, current_user.id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    service = MessageService(db)
    result = await service.rollback_after(session_id, message_id)
    return result
