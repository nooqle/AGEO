"""Append-only orchestration events for transparent memory (Wave B)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.flow_orchestration_event import FlowOrchestrationEvent

# Keep list short for UI
DEFAULT_LIMIT = 20
MAX_LIMIT = 50


def event_to_dict(row: FlowOrchestrationEvent) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "entity_id": str(row.entity_id),
        "event_type": row.event_type,
        "summary": row.summary,
        "payload": row.payload if isinstance(row.payload, dict) else {},
        "created_by_user_id": (
            str(row.created_by_user_id) if row.created_by_user_id else None
        ),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def append_event(
    db: AsyncSession,
    *,
    entity_id: UUID,
    event_type: str,
    summary: str,
    payload: dict[str, Any] | None = None,
    created_by_user_id: UUID | None = None,
    commit: bool = True,
) -> FlowOrchestrationEvent:
    row = FlowOrchestrationEvent(
        entity_id=entity_id,
        event_type=str(event_type or "unknown")[:64],
        summary=str(summary or "")[:500],
        payload=payload if isinstance(payload, dict) else None,
        created_by_user_id=created_by_user_id,
    )
    db.add(row)
    if commit:
        await db.commit()
        await db.refresh(row)
    else:
        await db.flush()
    return row


async def list_events(
    db: AsyncSession,
    *,
    entity_id: UUID,
    limit: int = DEFAULT_LIMIT,
) -> list[FlowOrchestrationEvent]:
    lim = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    result = await db.execute(
        select(FlowOrchestrationEvent)
        .where(FlowOrchestrationEvent.entity_id == entity_id)
        .order_by(desc(FlowOrchestrationEvent.created_at))
        .limit(lim)
    )
    return list(result.scalars().all())
