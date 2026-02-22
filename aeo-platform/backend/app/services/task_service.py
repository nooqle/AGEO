"""Task lifecycle management service.

IMPORTANT (Review C2/T1): TaskService is NOT injected into events.py.
Instead, it is called directly at key milestones within agent node
functions (e.g., a1_brand_node, a5_analytics_node). This preserves
the existing events.py function signatures and avoids responsibility
bloat in the event system.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import AnalysisTask, TaskStatus

logger = logging.getLogger(__name__)


class TaskService:
    """Manages AnalysisTask CRUD and lifecycle transitions."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_task(
        self,
        *,
        user_id: UUID,
        session_id: UUID | None,
        brand_name: str,
        entity_id: UUID | None = None,
        monitoring_schedule_id: UUID | None = None,
    ) -> AnalysisTask:
        """Create a new analysis task.

        session_id is None for scheduled (headless) tasks.
        monitoring_schedule_id links to the schedule that triggered this task.
        """
        task = AnalysisTask(
            user_id=user_id,
            session_id=session_id,
            brand_name=brand_name,
            entity_id=entity_id,
            monitoring_schedule_id=monitoring_schedule_id,
            status=TaskStatus.PENDING,
            progress=0.0,
            progress_message="等待开始...",
        )
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        logger.info(
            "[TaskService] Created task %s for brand '%s' (session=%s, schedule=%s)",
            task.id, brand_name, session_id, monitoring_schedule_id,
        )
        return task

    async def start_task(self, task_id: UUID) -> None:
        """Transition task from PENDING to RUNNING."""
        await self.db.execute(
            update(AnalysisTask)
            .where(AnalysisTask.id == task_id)
            .values(
                status=TaskStatus.RUNNING,
                started_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        await self.db.commit()

    async def update_progress(
        self,
        task_id: UUID,
        *,
        stage: str,
        progress: float,
        message: str,
        status: TaskStatus = TaskStatus.RUNNING,
    ) -> None:
        """Update task progress.

        Called at key milestones in agent nodes (not from events.py).
        """
        await self.db.execute(
            update(AnalysisTask)
            .where(AnalysisTask.id == task_id)
            .values(
                current_stage=stage,
                progress=progress,
                progress_message=message,
                status=status,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await self.db.commit()

    async def append_stage_result(
        self,
        task_id: UUID,
        stage_result: dict[str, Any],
    ) -> None:
        """Append a stage_result to the cache (for reconnection replay).

        CONCURRENCY (Review C1/T2): Uses SELECT FOR UPDATE within a
        transaction to prevent lost updates from concurrent writes.
        """
        # Use a nested transaction for the row lock
        async with self.db.begin_nested():
            stmt = (
                select(AnalysisTask)
                .where(AnalysisTask.id == task_id)
                .with_for_update()
            )
            result = await self.db.execute(stmt)
            task = result.scalar_one_or_none()
            if task is None:
                logger.warning(
                    "[TaskService] Task %s not found for append_stage_result",
                    task_id,
                )
                return

            cache = list(task.stage_results_cache or [])
            cache.append(stage_result)
            task.stage_results_cache = cache
            task.updated_at = datetime.now(timezone.utc)
            await self.db.flush()

        await self.db.commit()

    async def complete_task(
        self,
        task_id: UUID,
        *,
        snapshot_id: UUID | None = None,
    ) -> AnalysisTask | None:
        """Mark task as completed, optionally linking to a snapshot.

        CANCELLATION CHECK (Review T8): Before marking COMPLETED, checks
        if task.status == CANCELLED. If so, skips the transition and returns
        early -- the user's cancellation intent takes precedence.
        """
        stmt = select(AnalysisTask).where(AnalysisTask.id == task_id)
        result = await self.db.execute(stmt)
        task = result.scalar_one_or_none()
        if task is None:
            return None

        if task.status == TaskStatus.CANCELLED:
            logger.info(
                "[TaskService] Task %s was CANCELLED, skipping COMPLETED transition",
                task_id,
            )
            return task

        task.status = TaskStatus.COMPLETED
        task.progress = 1.0
        task.progress_message = "分析完成"
        task.completed_at = datetime.now(timezone.utc)
        task.updated_at = datetime.now(timezone.utc)
        if snapshot_id is not None:
            task.snapshot_id = snapshot_id

        await self.db.commit()
        await self.db.refresh(task)
        logger.info("[TaskService] Task %s completed (snapshot=%s)", task_id, snapshot_id)
        return task

    async def fail_task(
        self,
        task_id: UUID,
        *,
        error_message: str,
        error_stage: str,
    ) -> AnalysisTask | None:
        """Mark task as failed with error details."""
        stmt = select(AnalysisTask).where(AnalysisTask.id == task_id)
        result = await self.db.execute(stmt)
        task = result.scalar_one_or_none()
        if task is None:
            return None

        task.status = TaskStatus.FAILED
        task.error_message = error_message
        task.error_stage = error_stage
        task.completed_at = datetime.now(timezone.utc)
        task.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(task)
        logger.warning(
            "[TaskService] Task %s FAILED at %s: %s",
            task_id, error_stage, error_message[:100],
        )
        return task

    async def cancel_task(self, task_id: UUID) -> AnalysisTask | None:
        """Mark task as cancelled.

        NOTE (Review T8): This only marks the database status as CANCELLED.
        It does NOT stop the running LangGraph workflow. The workflow will
        continue to completion, but complete_task() will detect the CANCELLED
        status and skip the COMPLETED transition.
        """
        stmt = select(AnalysisTask).where(AnalysisTask.id == task_id)
        result = await self.db.execute(stmt)
        task = result.scalar_one_or_none()
        if task is None:
            return None

        task.status = TaskStatus.CANCELLED
        task.completed_at = datetime.now(timezone.utc)
        task.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(task)
        logger.info("[TaskService] Task %s cancelled", task_id)
        return task

    async def get_task(self, task_id: UUID) -> AnalysisTask | None:
        """Get a single task by ID."""
        stmt = select(AnalysisTask).where(AnalysisTask.id == task_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_session_active_task(
        self, session_id: UUID
    ) -> AnalysisTask | None:
        """Get the active (PENDING/RUNNING) task for a session."""
        stmt = (
            select(AnalysisTask)
            .where(
                AnalysisTask.session_id == session_id,
                AnalysisTask.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]),
            )
            .order_by(AnalysisTask.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_tasks(
        self,
        user_id: UUID,
        *,
        session_id: UUID | None = None,
        status: TaskStatus | None = None,
        is_scheduled: bool | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[AnalysisTask], int]:
        """Get tasks for a user, optionally filtered by status, session, and trigger type.

        Args:
            is_scheduled: If True, only tasks with monitoring_schedule_id (scheduled).
                          If False, only tasks without monitoring_schedule_id (manual).
                          If None, no filter applied.
        """
        conditions = [AnalysisTask.user_id == user_id]
        if session_id is not None:
            conditions.append(AnalysisTask.session_id == session_id)
        if status is not None:
            conditions.append(AnalysisTask.status == status)
        if is_scheduled is True:
            conditions.append(AnalysisTask.monitoring_schedule_id.isnot(None))
        elif is_scheduled is False:
            conditions.append(AnalysisTask.monitoring_schedule_id.is_(None))

        # Count total
        count_stmt = (
            select(func.count())
            .select_from(AnalysisTask)
            .where(*conditions)
        )
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0

        # Fetch page
        query = (
            select(AnalysisTask)
            .where(*conditions)
            .order_by(AnalysisTask.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(query)
        tasks = list(result.scalars().all())

        return tasks, total

    async def recover_orphan_tasks(self, timeout_minutes: int = 30) -> int:
        """Recover orphan tasks on server startup (Review C6/T9).

        Scans for tasks that are stale:
        - RUNNING with started_at older than cutoff
        - PENDING with created_at older than cutoff (never started)

        Marks them as FAILED with appropriate error message.
        Returns the count of recovered (marked FAILED) tasks.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)

        stmt = (
            select(AnalysisTask)
            .where(
                or_(
                    # RUNNING tasks that exceeded timeout
                    (AnalysisTask.status == TaskStatus.RUNNING)
                    & (AnalysisTask.started_at < cutoff),
                    # PENDING tasks that were never picked up
                    (AnalysisTask.status == TaskStatus.PENDING)
                    & (AnalysisTask.created_at < cutoff),
                )
            )
        )
        result = await self.db.execute(stmt)
        orphans = list(result.scalars().all())

        for task in orphans:
            task.status = TaskStatus.FAILED
            task.error_message = "服务器重启导致任务中断，请重新执行分析。"
            task.error_stage = task.current_stage or "unknown"
            task.completed_at = datetime.now(timezone.utc)
            task.updated_at = datetime.now(timezone.utc)

        if orphans:
            await self.db.commit()

        return len(orphans)


def task_to_dict(task: AnalysisTask) -> dict[str, Any]:
    """Convert AnalysisTask to API-friendly dict."""
    return {
        "id": str(task.id),
        "user_id": str(task.user_id),
        "session_id": str(task.session_id) if task.session_id else None,
        "entity_id": str(task.entity_id) if task.entity_id else None,
        "brand_name": task.brand_name,
        "status": task.status.value if task.status else "pending",
        "current_stage": task.current_stage,
        "progress": task.progress,
        "progress_message": task.progress_message,
        "stage_results_cache": task.stage_results_cache,
        "snapshot_id": str(task.snapshot_id) if task.snapshot_id else None,
        "error_message": task.error_message,
        "error_stage": task.error_stage,
        "monitoring_schedule_id": (
            str(task.monitoring_schedule_id)
            if task.monitoring_schedule_id
            else None
        ),
        "triggered_by": "scheduled" if task.monitoring_schedule_id else "manual",
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }
