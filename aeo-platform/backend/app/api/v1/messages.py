"""Messages API endpoints."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional

from app.api.deps import get_db, get_current_user
from app.services.session_service import SessionService
from app.services.message_service import MessageService

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
    session = await session_service.get_session(session_id, current_user)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    service = MessageService(db)
    messages = await service.get_messages(session_id, limit=limit, before=before)
    return messages


@router.post("")
async def send_message(
    session_id: UUID,
    message: dict,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Send user message.

    Message processing is queued onto the unified local runtime.
    Real-time progress is still delivered via WebSocket when a client is connected.
    """
    session_service = SessionService(db)
    session = await session_service.get_session(session_id, current_user)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    content = str(message.get("content", "") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message content is required")

    message_service = MessageService(db)
    saved_message = await message_service.save_message(
        session_id=session_id,
        role="user",
        content=content,
    )

    from app.api.v1.websocket_langgraph import handle_user_message_langgraph

    asyncio.create_task(
        handle_user_message_langgraph(
            None,
            str(session_id),
            {
                "content": content,
                "trigger_source": "messages_api",
                "persist_user_message": False,
                "message_id": str(saved_message["id"]),
            },
        )
    )

    return {
        "status": "processing",
        "entrypoint": "messages_api",
        "message": "Message received, runtime started",
        "message_id": str(saved_message["id"]),
    }


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
    session = await session_service.get_session(session_id, current_user)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    service = MessageService(db)
    result = await service.rollback_after(session_id, message_id)
    return result
