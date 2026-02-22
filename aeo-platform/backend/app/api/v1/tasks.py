"""Task API endpoints for analysis task lifecycle management."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.task import TaskStatus
from app.services.task_service import TaskService, task_to_dict

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions/{session_id}/tasks", tags=["tasks"])


def _parse_uuid(value: str, field_name: str = "id") -> UUID:
    """Parse a string as UUID, raising 400 on invalid format."""
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UUID for {field_name}: {value}",
        )


@router.get("")
async def list_session_tasks(
    session_id: str,
    status_filter: str | None = None,
    limit: int = 20,
    offset: int = 0,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List tasks for a session."""
    sid = _parse_uuid(session_id, "session_id")
    service = TaskService(db)
    task_status = None
    if status_filter:
        try:
            task_status = TaskStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}",
            )

    tasks, total = await service.list_tasks(
        user_id=current_user.id,
        session_id=sid,
        status=task_status,
        limit=limit,
        offset=offset,
    )
    return {
        "tasks": [task_to_dict(t) for t in tasks],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/active")
async def get_active_task(
    session_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the active (PENDING/RUNNING) task for a session."""
    sid = _parse_uuid(session_id, "session_id")
    service = TaskService(db)
    task = await service.get_session_active_task(sid)
    if task is None:
        return {"task": None}
    # Verify ownership
    if task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    return {"task": task_to_dict(task)}


@router.get("/{task_id}")
async def get_task(
    session_id: str,
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get a specific task."""
    sid = _parse_uuid(session_id, "session_id")
    tid = _parse_uuid(task_id, "task_id")
    service = TaskService(db)
    task = await service.get_task(tid)
    if not task or str(task.session_id) != str(sid):
        raise HTTPException(status_code=404, detail="Task not found")
    if task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    return {"task": task_to_dict(task)}


# ---------------------------------------------------------------------------
# Global tasks router (not scoped to session)
# ---------------------------------------------------------------------------
global_tasks_router = APIRouter(prefix="/tasks", tags=["tasks"])


@global_tasks_router.get("")
async def list_user_tasks(
    status_filter: str | None = None,
    triggered_by: str | None = None,
    limit: int = 20,
    offset: int = 0,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all tasks for the current user across all sessions.

    Args:
        triggered_by: Filter by trigger type ("manual" or "scheduled").
                      Filtering is done at the SQL layer for correct
                      pagination counts.
    """
    from app.models.task import AnalysisTask

    service = TaskService(db)
    task_status = None
    if status_filter:
        try:
            task_status = TaskStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}",
            )

    # Determine schedule filter from triggered_by
    # "scheduled" -> has monitoring_schedule_id (is not None)
    # "manual"    -> no monitoring_schedule_id (is None)
    scheduled_filter: bool | None = None
    if triggered_by == "scheduled":
        scheduled_filter = True
    elif triggered_by == "manual":
        scheduled_filter = False

    tasks, total = await service.list_tasks(
        user_id=current_user.id,
        status=task_status,
        is_scheduled=scheduled_filter,
        limit=limit,
        offset=offset,
    )

    return {
        "tasks": [task_to_dict(t) for t in tasks],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/{task_id}/cancel")
async def cancel_task(
    session_id: str,
    task_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a running task (marks status only -- Review T8)."""
    _parse_uuid(session_id, "session_id")
    tid = _parse_uuid(task_id, "task_id")
    service = TaskService(db)
    task = await service.get_task(tid)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    if task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    if task.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel task with status: {task.status.value}",
        )

    cancelled = await service.cancel_task(tid)
    return {"task": task_to_dict(cancelled) if cancelled else None}
