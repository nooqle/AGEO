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

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.task import AnalysisTask, TaskStatus
from app.models.task_run import TaskRun, TaskRunStatus, TaskTriggerSource
from app.models.task_run_child_attempt import TaskRunChildAttempt
from app.models.user import User
from app.services.access_scope_service import AccessScopeService
from app.services.runtime_coordinator import runtime_coordinator
from app.services.task_event_bus import TaskStatusChangedEvent

logger = logging.getLogger(__name__)


def _is_stale_waiting_message(message: str | None) -> bool:
    if not message:
        return False
    return message.startswith("等待用户确认")


def _resolved_running_progress_message(
    task: AnalysisTask, latest_run: TaskRun | None
) -> str:
    """Normalize stale waiting copy after a resume run has already started."""

    progress_message = task.progress_message or ""
    if (
        task.status == TaskStatus.RUNNING
        and latest_run is not None
        and latest_run.status != TaskRunStatus.WAITING_INPUT
        and _is_stale_waiting_message(progress_message)
    ):
        return "正在继续分析..."
    return progress_message


class TaskService:
    """Manages AnalysisTask CRUD and lifecycle transitions."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _reload_task_with_runs(self, task_id: UUID) -> AnalysisTask | None:
        """Reload a task with its runtime attempts for event publishing."""

        stmt = (
            select(AnalysisTask)
            .options(
                selectinload(AnalysisTask.task_runs).selectinload(
                    TaskRun.child_attempts
                )
            )
            .where(AnalysisTask.id == task_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _publish_task_status_change(
        self,
        task_id: UUID,
    ) -> AnalysisTask | None:
        """Publish a committed task lifecycle event through the domain bus."""

        task = await self._reload_task_with_runs(task_id)
        if task is None:
            return None

        await runtime_coordinator.publish_task_status(
            TaskStatusChangedEvent(
                session_id=str(task.session_id) if task.session_id else None,
                status=task.status.value if task.status else "pending",
                task=task_to_dict(task),
            )
        )
        return task

    async def _get_target_run(
        self,
        task_id: UUID,
        run_id: UUID | None = None,
    ) -> TaskRun | None:
        if run_id is not None:
            stmt = select(TaskRun).where(
                TaskRun.id == run_id,
                TaskRun.task_id == task_id,
            )
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()

        active_stmt = (
            select(TaskRun)
            .where(
                TaskRun.task_id == task_id,
                TaskRun.status.in_(
                    [
                        TaskRunStatus.QUEUED,
                        TaskRunStatus.CLAIMED,
                        TaskRunStatus.RUNNING,
                        TaskRunStatus.WAITING_INPUT,
                        TaskRunStatus.CANCELLING,
                    ]
                ),
            )
            .order_by(TaskRun.submitted_at.desc())
            .limit(1)
        )
        active_result = await self.db.execute(active_stmt)
        active_run = active_result.scalar_one_or_none()
        if active_run is not None:
            return active_run

        fallback_stmt = (
            select(TaskRun)
            .where(TaskRun.task_id == task_id)
            .order_by(TaskRun.submitted_at.desc())
            .limit(1)
        )
        fallback_result = await self.db.execute(fallback_stmt)
        return fallback_result.scalar_one_or_none()

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
            task.id,
            brand_name,
            session_id,
            monitoring_schedule_id,
        )
        return task

    async def start_task(
        self,
        task_id: UUID,
        *,
        run_id: UUID | None = None,
        lease_owner: str | None = None,
    ) -> None:
        """Transition task from PENDING to RUNNING."""
        now = datetime.now(timezone.utc)
        stmt = select(AnalysisTask).where(AnalysisTask.id == task_id)
        result = await self.db.execute(stmt)
        task = result.scalar_one_or_none()
        if task is None:
            return

        previous_status = task.status
        task.status = TaskStatus.RUNNING
        task.started_at = task.started_at or now
        if previous_status in {
            TaskStatus.CANCELLED,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
        }:
            task.completed_at = None
            task.error_message = None
            task.error_stage = None
            if not task.progress_message or task.progress_message in {
                "任务已取消",
                "分析完成",
            }:
                task.progress_message = "任务已恢复执行..."
        elif _is_stale_waiting_message(task.progress_message):
            task.progress_message = "正在继续分析..."
        task.updated_at = now

        run = await self._get_target_run(task_id, run_id)
        if run is not None:
            run.status = TaskRunStatus.RUNNING
            run.started_at = run.started_at or now
            run.heartbeat_at = now
            if lease_owner:
                run.lease_owner = lease_owner

        await self.db.commit()
        await self._publish_task_status_change(task.id)

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
        now = datetime.now(timezone.utc)
        stmt = select(AnalysisTask).where(AnalysisTask.id == task_id)
        result = await self.db.execute(stmt)
        task = result.scalar_one_or_none()
        if task is None:
            return

        task.current_stage = stage
        task.progress = progress
        task.progress_message = message
        task.status = status
        task.updated_at = now

        run = await self._get_target_run(task_id)
        if run is not None:
            if run.status == TaskRunStatus.CLAIMED:
                run.status = TaskRunStatus.RUNNING
                run.started_at = run.started_at or now
            run.checkpoint_stage = stage
            run.heartbeat_at = now

        await self.db.commit()
        await self._publish_task_status_change(task.id)

    async def mark_waiting_for_input(
        self,
        task_id: UUID,
        *,
        run_id: UUID | None = None,
        checkpoint_stage: str | None = None,
        progress_message: str | None = None,
    ) -> AnalysisTask | None:
        """Mark the current execution attempt as waiting for user input."""

        stmt = select(AnalysisTask).where(AnalysisTask.id == task_id)
        result = await self.db.execute(stmt)
        task = result.scalar_one_or_none()
        if task is None:
            return None

        now = datetime.now(timezone.utc)
        task.status = TaskStatus.RUNNING
        task.completed_at = None
        if checkpoint_stage:
            task.current_stage = checkpoint_stage
        if progress_message:
            task.progress_message = progress_message[:255]
        task.updated_at = now

        run = await self._get_target_run(task_id, run_id)
        if run is not None:
            run.status = TaskRunStatus.WAITING_INPUT
            run.checkpoint_stage = checkpoint_stage or run.checkpoint_stage
            run.heartbeat_at = now
            run.finished_at = None

        await self.db.commit()
        return await self._publish_task_status_change(task.id)

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
                select(AnalysisTask).where(AnalysisTask.id == task_id).with_for_update()
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
        run_id: UUID | None = None,
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

        run = await self._get_target_run(task_id, run_id)
        now = datetime.now(timezone.utc)

        if task.status == TaskStatus.CANCELLED:
            logger.info(
                "[TaskService] Task %s was CANCELLED, skipping COMPLETED transition",
                task_id,
            )
            if run is not None and run.status != TaskRunStatus.CANCELLED:
                run.status = TaskRunStatus.CANCELLED
                run.finished_at = now
                run.heartbeat_at = now
                await self.db.commit()
                return await self._publish_task_status_change(task.id)
            return await self._reload_task_with_runs(task.id)

        task.status = TaskStatus.COMPLETED
        task.progress = 1.0
        task.progress_message = "分析完成"
        task.completed_at = now
        task.updated_at = now
        if snapshot_id is not None:
            task.snapshot_id = snapshot_id

        if run is not None:
            run.status = TaskRunStatus.COMPLETED
            run.finished_at = now
            run.heartbeat_at = now

        await self.db.commit()
        published_task = await self._publish_task_status_change(task.id)
        logger.info(
            "[TaskService] Task %s completed (snapshot=%s)", task_id, snapshot_id
        )
        return published_task

    async def fail_task(
        self,
        task_id: UUID,
        *,
        error_message: str,
        error_stage: str,
        run_id: UUID | None = None,
    ) -> AnalysisTask | None:
        """Mark task as failed with error details."""
        stmt = select(AnalysisTask).where(AnalysisTask.id == task_id)
        result = await self.db.execute(stmt)
        task = result.scalar_one_or_none()
        if task is None:
            return None

        run = await self._get_target_run(task_id, run_id)
        now = datetime.now(timezone.utc)

        if task.status == TaskStatus.CANCELLED:
            logger.info(
                "[TaskService] Task %s was CANCELLED, skipping FAILED transition",
                task_id,
            )
            if run is not None and run.status != TaskRunStatus.CANCELLED:
                run.status = TaskRunStatus.CANCELLED
                run.finished_at = now
                run.heartbeat_at = now
                await self.db.commit()
                return await self._publish_task_status_change(task.id)
            return await self._reload_task_with_runs(task.id)

        task.status = TaskStatus.FAILED
        task.error_message = error_message
        task.error_stage = error_stage
        task.completed_at = now
        task.updated_at = now

        if run is not None and run.status != TaskRunStatus.CANCELLED:
            run.status = TaskRunStatus.FAILED
            run.error_kind = error_stage
            run.error_message = error_message
            run.finished_at = now
            run.heartbeat_at = now

        await self.db.commit()
        published_task = await self._publish_task_status_change(task.id)
        logger.warning(
            "[TaskService] Task %s FAILED at %s: %s",
            task_id,
            error_stage,
            error_message[:100],
        )
        return published_task

    async def cancel_task(
        self,
        task_id: UUID,
        *,
        run_id: UUID | None = None,
    ) -> AnalysisTask | None:
        """Mark task as cancelled.

        The runtime layer is responsible for honoring the persisted cancel
        request and stopping the active executor cooperatively.
        """
        stmt = select(AnalysisTask).where(AnalysisTask.id == task_id)
        result = await self.db.execute(stmt)
        task = result.scalar_one_or_none()
        if task is None:
            return None

        run = await self._get_target_run(task_id, run_id)
        now = datetime.now(timezone.utc)
        task.status = TaskStatus.CANCELLED
        task.progress_message = "任务已取消"
        task.completed_at = now
        task.updated_at = now

        if run is not None:
            run.cancel_requested_at = now
            run.heartbeat_at = now
            if run.status == TaskRunStatus.RUNNING:
                run.status = TaskRunStatus.CANCELLING
            else:
                run.status = TaskRunStatus.CANCELLED
                run.finished_at = now

        await self.db.commit()
        published_task = await self._publish_task_status_change(task.id)
        logger.info("[TaskService] Task %s cancelled", task_id)
        return published_task

    async def finalize_cancel_if_requested(
        self,
        task_id: UUID,
        *,
        run_id: UUID | None = None,
    ) -> AnalysisTask | None:
        """Collapse a cooperative cancel into a durable final CANCELLED state."""

        stmt = select(AnalysisTask).where(AnalysisTask.id == task_id)
        result = await self.db.execute(stmt)
        task = result.scalar_one_or_none()
        if task is None:
            return None

        run = await self._get_target_run(task_id, run_id)
        cancellation_requested = task.status == TaskStatus.CANCELLED or (
            run is not None
            and (
                run.cancel_requested_at is not None
                or run.status
                in {
                    TaskRunStatus.CANCELLING,
                    TaskRunStatus.CANCELLED,
                }
            )
        )
        if not cancellation_requested:
            return await self._reload_task_with_runs(task.id)

        now = datetime.now(timezone.utc)
        task.status = TaskStatus.CANCELLED
        task.progress_message = "任务已取消"
        task.completed_at = task.completed_at or now
        task.updated_at = now

        if run is not None:
            run.status = TaskRunStatus.CANCELLED
            run.cancel_requested_at = run.cancel_requested_at or now
            run.finished_at = run.finished_at or now
            run.heartbeat_at = now

        await self.db.commit()
        published_task = await self._publish_task_status_change(task.id)
        logger.info(
            "[TaskService] Task %s cancel finalized (run=%s)",
            task_id,
            run_id,
        )
        return published_task

    async def get_task(self, task_id: UUID) -> AnalysisTask | None:
        """Get a single task by ID."""
        stmt = (
            select(AnalysisTask)
            .options(
                selectinload(AnalysisTask.task_runs).selectinload(
                    TaskRun.child_attempts
                )
            )
            .where(AnalysisTask.id == task_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_task_for_viewer(
        self,
        task_id: UUID,
        viewer: User,
    ) -> AnalysisTask | None:
        stmt = (
            select(AnalysisTask)
            .options(
                selectinload(AnalysisTask.task_runs).selectinload(
                    TaskRun.child_attempts
                )
            )
            .where(
                AnalysisTask.id == task_id,
                AccessScopeService.task_visibility_filter(viewer),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_task_run(self, task_id: UUID, run_id: UUID) -> TaskRun | None:
        """Get a single runtime attempt by task/run identity."""

        stmt = (
            select(TaskRun)
            .options(selectinload(TaskRun.child_attempts))
            .where(
                TaskRun.id == run_id,
                TaskRun.task_id == task_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_session_active_task(self, session_id: UUID) -> AnalysisTask | None:
        """Get the active (PENDING/RUNNING) task for a session."""
        stmt = (
            select(AnalysisTask)
            .options(
                selectinload(AnalysisTask.task_runs).selectinload(
                    TaskRun.child_attempts
                )
            )
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
        count_stmt = select(func.count()).select_from(AnalysisTask).where(*conditions)
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0

        # Fetch page
        query = (
            select(AnalysisTask)
            .options(
                selectinload(AnalysisTask.task_runs).selectinload(
                    TaskRun.child_attempts
                )
            )
            .where(*conditions)
            .order_by(AnalysisTask.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(query)
        tasks = list(result.scalars().all())

        return tasks, total

    async def list_tasks_for_viewer(
        self,
        viewer: User,
        *,
        session_id: UUID | None = None,
        status: TaskStatus | None = None,
        is_scheduled: bool | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[AnalysisTask], int]:
        conditions = [AccessScopeService.task_visibility_filter(viewer)]
        if session_id is not None:
            conditions.append(AnalysisTask.session_id == session_id)
        if status is not None:
            conditions.append(AnalysisTask.status == status)
        if is_scheduled is True:
            conditions.append(AnalysisTask.monitoring_schedule_id.isnot(None))
        elif is_scheduled is False:
            conditions.append(AnalysisTask.monitoring_schedule_id.is_(None))

        count_stmt = select(func.count()).select_from(AnalysisTask).where(*conditions)
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0

        query = (
            select(AnalysisTask)
            .options(
                selectinload(AnalysisTask.task_runs).selectinload(
                    TaskRun.child_attempts
                )
            )
            .where(*conditions)
            .order_by(AnalysisTask.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(query)
        tasks = list(result.scalars().all())
        return tasks, total

    async def get_task_runs(
        self,
        task_id: UUID,
        *,
        limit: int = 20,
    ) -> list[TaskRun]:
        """List runtime attempts for a task, newest first."""

        stmt = (
            select(TaskRun)
            .options(selectinload(TaskRun.child_attempts))
            .where(TaskRun.task_id == task_id)
            .order_by(TaskRun.submitted_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

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
            .options(selectinload(AnalysisTask.task_runs))
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
        recovered_count = 0

        for task in orphans:
            loaded_runs = task.__dict__.get("task_runs") or []
            latest_run = loaded_runs[0] if loaded_runs else None
            if latest_run is not None and latest_run.status in {
                TaskRunStatus.QUEUED,
                TaskRunStatus.WAITING_INPUT,
            }:
                logger.info(
                    "[TaskService] Skip orphan recovery for task %s: "
                    "latest run is %s",
                    task.id,
                    latest_run.status.value,
                )
                continue

            if (
                latest_run is not None
                and latest_run.trigger_source == TaskTriggerSource.SCHEDULER
                and latest_run.status
                in {
                    TaskRunStatus.CLAIMED,
                    TaskRunStatus.RUNNING,
                    TaskRunStatus.CANCELLING,
                }
            ):
                logger.info(
                    "[TaskService] Skip orphan recovery for scheduled task %s: "
                    "latest run is %s and will be recovered by scheduler runtime",
                    task.id,
                    latest_run.status.value,
                )
                continue

            task.status = TaskStatus.FAILED
            task.error_message = "服务器重启导致任务中断，请重新执行分析。"
            task.error_stage = task.current_stage or "unknown"
            task.completed_at = datetime.now(timezone.utc)
            task.updated_at = datetime.now(timezone.utc)
            recovered_count += 1

        if recovered_count:
            await self.db.commit()

        return recovered_count


def task_to_dict(task: AnalysisTask) -> dict[str, Any]:
    """Convert AnalysisTask to API-friendly dict."""
    loaded_runs = task.__dict__.get("task_runs")
    latest_run = loaded_runs[0] if loaded_runs else None
    return {
        "id": str(task.id),
        "user_id": str(task.user_id),
        "session_id": str(task.session_id) if task.session_id else None,
        "entity_id": str(task.entity_id) if task.entity_id else None,
        "brand_name": task.brand_name,
        "status": task.status.value if task.status else "pending",
        "current_stage": task.current_stage,
        "progress": task.progress,
        "progress_message": _resolved_running_progress_message(task, latest_run),
        "llm_call_count": task.llm_call_count,
        "llm_prompt_tokens": task.llm_prompt_tokens,
        "llm_completion_tokens": task.llm_completion_tokens,
        "llm_total_tokens": task.llm_total_tokens,
        "llm_cached_prompt_tokens": task.llm_cached_prompt_tokens,
        "llm_billable_prompt_tokens": task.llm_billable_prompt_tokens,
        "llm_total_latency_ms": task.llm_total_latency_ms,
        "llm_estimated_cost": task.llm_estimated_cost,
        "llm_estimated_cost_cache_aware": task.llm_estimated_cost_cache_aware,
        "stage_results_cache": task.stage_results_cache,
        "snapshot_id": str(task.snapshot_id) if task.snapshot_id else None,
        "error_message": task.error_message,
        "error_stage": task.error_stage,
        "monitoring_schedule_id": (
            str(task.monitoring_schedule_id) if task.monitoring_schedule_id else None
        ),
        "triggered_by": "scheduled" if task.monitoring_schedule_id else "manual",
        "latest_run": task_run_to_dict(latest_run) if latest_run else None,
        "task_runs": (
            [task_run_to_dict(run) for run in loaded_runs]
            if loaded_runs is not None
            else None
        ),
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


def task_run_to_dict(run: TaskRun) -> dict[str, Any]:
    """Convert TaskRun to API-friendly dict."""

    loaded_child_attempts = run.__dict__.get("child_attempts")
    return {
        "id": str(run.id),
        "task_id": str(run.task_id),
        "run_kind": run.run_kind.value,
        "trigger_source": run.trigger_source.value,
        "executor_kind": run.executor_kind.value,
        "status": run.status.value,
        "attempt_no": run.attempt_no,
        "priority": run.priority,
        "lease_owner": run.lease_owner,
        "executor_ref": run.executor_ref,
        "checkpoint_stage": run.checkpoint_stage,
        "checkpoint_payload_ref": run.checkpoint_payload_ref,
        "error_kind": run.error_kind,
        "error_message": run.error_message,
        "cancel_requested_at": (
            run.cancel_requested_at.isoformat() if run.cancel_requested_at else None
        ),
        "heartbeat_at": run.heartbeat_at.isoformat() if run.heartbeat_at else None,
        "submitted_at": run.submitted_at.isoformat() if run.submitted_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "child_attempts": (
            [
                task_run_child_attempt_to_dict(attempt)
                for attempt in loaded_child_attempts
            ]
            if loaded_child_attempts is not None
            else None
        ),
    }


def task_run_child_attempt_to_dict(run: TaskRunChildAttempt) -> dict[str, Any]:
    """Convert nested runtime attempt to API-friendly dict."""

    return {
        "id": str(run.id),
        "task_run_id": str(run.task_run_id),
        "child_kind": run.child_kind.value,
        "status": run.status.value,
        "step": run.step,
        "platform": run.platform,
        "action_type": run.action_type,
        "request_id": run.request_id,
        "message": run.message,
        "action_hint": run.action_hint,
        "progress": run.progress,
        "resolution": run.resolution,
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        "resolved_at": run.resolved_at.isoformat() if run.resolved_at else None,
    }
