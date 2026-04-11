"""Task API endpoints for analysis task lifecycle management."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.task import TaskStatus
from app.services.access_scope_service import AccessScopeService
from app.services.llm_usage_service import LLMUsageService
from app.services.runtime_coordinator import runtime_coordinator
from app.services.task_service import TaskService, task_run_to_dict, task_to_dict

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

    tasks, total = await service.list_tasks_for_viewer(
        viewer=current_user,
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
    await service.reconcile_terminal_task_live_runs(sid)
    task = await service.get_session_active_task(sid)
    if task is None:
        return {"task": None}
    if not AccessScopeService.can_access_task(task, current_user):
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
    task = await service.get_task_for_viewer(tid, current_user)
    if not task or str(task.session_id) != str(sid):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task": task_to_dict(task)}


@router.get("/{task_id}/runs")
async def get_task_runs(
    session_id: str,
    task_id: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List runtime attempts for a specific task."""

    sid = _parse_uuid(session_id, "session_id")
    tid = _parse_uuid(task_id, "task_id")
    service = TaskService(db)
    task = await service.get_task_for_viewer(tid, current_user)
    if not task or str(task.session_id) != str(sid):
        raise HTTPException(status_code=404, detail="Task not found")

    runs = await service.get_task_runs(tid, limit=limit)
    return {
        "task_id": str(task.id),
        "runs": [task_run_to_dict(run) for run in runs],
        "limit": limit,
    }


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

    tasks, total = await service.list_tasks_for_viewer(
        viewer=current_user,
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


@global_tasks_router.get("/observability")
async def get_llm_observability(
    days: int = 30,
    limit: int = 20,
    entity_id: str | None = None,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return aggregated LLM observability metrics for the current user."""
    parsed_entity_id = _parse_uuid(entity_id, "entity_id") if entity_id else None
    usage_service = LLMUsageService(db)
    snapshot = await usage_service.get_observability_snapshot(
        user_id=current_user.id,
        entity_id=parsed_entity_id,
        days=days,
        limit=limit,
    )
    return snapshot


@router.post("/{task_id}/cancel")
async def cancel_task(
    session_id: str,
    task_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a task and request the local executor to stop if it is active."""
    _parse_uuid(session_id, "session_id")
    tid = _parse_uuid(task_id, "task_id")
    service = TaskService(db)
    task = await service.get_task_for_viewer(tid, current_user)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    if task.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅任务发起人可取消任务",
        )
    if task.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel task with status: {task.status.value}",
        )

    loaded_runs = task.__dict__.get("task_runs") or []
    latest_run = loaded_runs[0] if loaded_runs else None
    cancelled = await service.cancel_task(
        tid,
        run_id=latest_run.id if latest_run is not None else None,
    )
    await runtime_coordinator.cancel_task_execution(
        tid,
        session_id=str(task.session_id) if task.session_id else None,
    )
    return {"task": task_to_dict(cancelled) if cancelled else None}
