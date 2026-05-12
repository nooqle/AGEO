"""Messages API endpoints."""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Any, Optional

from app.api.deps import get_db, get_current_user
from app.services.session_service import SessionService
from app.services.message_service import MessageService
from app.workflow.graph import get_compiled_workflow

router = APIRouter(prefix="/sessions/{session_id}/messages", tags=["messages"])
logger = logging.getLogger(__name__)


def _state_is_waiting_for_user(state_values: dict[str, Any]) -> bool:
    return bool(
        state_values.get("awaiting_user")
        or state_values.get("execution_status") == "awaiting_user"
        or state_values.get("pending_confirmation")
    )


async def _get_pending_confirmation(session_id: UUID) -> dict[str, Any] | None:
    """Read the durable Orchestrator ask-user state for history hydration."""

    try:
        workflow = await get_compiled_workflow()
        config = {"configurable": {"thread_id": str(session_id)}}
        aget_state = getattr(workflow, "aget_state", None)
        if callable(aget_state):
            current_state = await aget_state(config)
        else:
            current_state = await asyncio.to_thread(workflow.get_state, config)
    except Exception:
        logger.exception(
            "[Messages] Failed to read pending confirmation for session %s",
            session_id,
        )
        return None

    state_values = dict(getattr(current_state, "values", None) or {})
    if not state_values or not _state_is_waiting_for_user(state_values):
        return None

    pending_confirmation = state_values.get("pending_confirmation")
    if not isinstance(pending_confirmation, dict) or not pending_confirmation:
        return None

    options = pending_confirmation.get("options")
    if not isinstance(options, list):
        options = []

    request_id = str(
        pending_confirmation.get("request_id")
        or pending_confirmation.get("step_id")
        or "orchestrator"
    )
    return {
        "request_id": request_id,
        "type": "step_confirmation",
        "message": str(
            pending_confirmation.get("message")
            or state_values.get("progress_message")
            or "请确认后继续。"
        ),
        "options": options,
        "allow_text_input": True,
        "step_id": str(pending_confirmation.get("step_id") or "orchestrator"),
        "step_name": str(pending_confirmation.get("step_name") or "等待用户确认"),
    }


@router.get("")
async def get_messages(
    session_id: UUID,
    limit: int = 50,
    before: Optional[UUID] = None,
    include_pending_confirmation: bool = False,
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
    if include_pending_confirmation:
        pending_confirmation = await _get_pending_confirmation(session_id)
        return {
            "messages": messages,
            "pending_confirmation": pending_confirmation,
        }
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
