"""Minimal runtime dispatcher for claiming and heartbeating task runs."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import AnalysisTask, TaskStatus
from app.models.task_run import (
    ExecutorKind,
    TaskRun,
    TaskRunStatus,
    TaskTriggerSource,
)

logger = logging.getLogger(__name__)


class JobDispatcher:
    """Owns claim/lease semantics for TaskRun records."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def claim_run(
        self,
        *,
        task_id: UUID,
        run_id: UUID,
        lease_owner: str,
        executor_ref: str | None = None,
    ) -> TaskRun | None:
        """Claim a queued run for execution."""

        async with self.db.begin_nested():
            stmt = (
                select(TaskRun)
                .where(
                    TaskRun.id == run_id,
                    TaskRun.task_id == task_id,
                )
                .with_for_update()
            )
            result = await self.db.execute(stmt)
            run = result.scalar_one_or_none()
            if run is None:
                return None

            if run.status != TaskRunStatus.QUEUED:
                logger.info(
                    "[JobDispatcher] Skip claim for run %s: current status=%s",
                    run_id,
                    run.status.value,
                )
                return None

            now = datetime.now(timezone.utc)
            run.status = TaskRunStatus.CLAIMED
            run.lease_owner = lease_owner
            if executor_ref:
                run.executor_ref = executor_ref
            run.heartbeat_at = now
            await self.db.flush()

        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def requeue_expired_runs(
        self,
        *,
        lease_timeout_seconds: int,
        executor_kind: ExecutorKind = ExecutorKind.LOCAL_WORKFLOW,
        trigger_source: TaskTriggerSource | None = None,
        limit: int = 20,
    ) -> int:
        """Requeue stale claimed/running runs whose lease heartbeat expired."""

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=lease_timeout_seconds)

        async with self.db.begin_nested():
            conditions = [
                TaskRun.status.in_(
                    [
                        TaskRunStatus.CLAIMED,
                        TaskRunStatus.RUNNING,
                        TaskRunStatus.CANCELLING,
                    ]
                ),
                TaskRun.executor_kind == executor_kind,
                or_(
                    TaskRun.heartbeat_at.is_(None),
                    TaskRun.heartbeat_at < cutoff,
                ),
            ]
            if trigger_source is not None:
                conditions.append(TaskRun.trigger_source == trigger_source)

            stmt = (
                select(TaskRun)
                .where(*conditions)
                .order_by(TaskRun.heartbeat_at.asc(), TaskRun.submitted_at.asc())
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
            result = await self.db.execute(stmt)
            runs = list(result.scalars().all())
            if not runs:
                return 0

            task_stmt = (
                select(AnalysisTask)
                .where(AnalysisTask.id.in_([run.task_id for run in runs]))
                .with_for_update()
            )
            task_result = await self.db.execute(task_stmt)
            tasks_by_id = {
                task.id: task
                for task in task_result.scalars().all()
            }

            for run in runs:
                task = tasks_by_id.get(run.task_id)
                if task is None:
                    continue

                if run.cancel_requested_at is not None:
                    run.status = TaskRunStatus.CANCELLED
                    run.finished_at = now
                    run.heartbeat_at = now
                    task.status = TaskStatus.CANCELLED
                    task.completed_at = now
                    task.updated_at = now
                    task.progress_message = "任务已取消"
                    continue

                run.status = TaskRunStatus.QUEUED
                run.lease_owner = None
                run.executor_ref = None
                run.started_at = None
                run.heartbeat_at = None
                task.status = TaskStatus.PENDING
                task.updated_at = now
                task.progress_message = "等待恢复执行..."

            await self.db.flush()

        await self.db.commit()
        return len(runs)

    async def claim_next_run(
        self,
        *,
        lease_owner: str,
        executor_kind: ExecutorKind = ExecutorKind.LOCAL_WORKFLOW,
        trigger_source: TaskTriggerSource | None = None,
        executor_ref: str | None = None,
    ) -> TaskRun | None:
        """Claim the next queued run for an executor."""

        async with self.db.begin_nested():
            conditions = [
                TaskRun.status == TaskRunStatus.QUEUED,
                TaskRun.executor_kind == executor_kind,
            ]
            if trigger_source is not None:
                conditions.append(TaskRun.trigger_source == trigger_source)

            stmt = (
                select(TaskRun)
                .where(*conditions)
                .order_by(TaskRun.priority.asc(), TaskRun.submitted_at.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            result = await self.db.execute(stmt)
            run = result.scalar_one_or_none()
            if run is None:
                return None

            now = datetime.now(timezone.utc)
            run.status = TaskRunStatus.CLAIMED
            run.lease_owner = lease_owner
            if executor_ref:
                run.executor_ref = executor_ref
            run.heartbeat_at = now
            await self.db.flush()

        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def heartbeat_run(
        self,
        *,
        task_id: UUID,
        run_id: UUID,
        checkpoint_stage: str | None = None,
        lease_owner: str | None = None,
    ) -> TaskRun | None:
        """Refresh the lease heartbeat for a claimed/running run."""

        stmt = select(TaskRun).where(
            TaskRun.id == run_id,
            TaskRun.task_id == task_id,
        )
        result = await self.db.execute(stmt)
        run = result.scalar_one_or_none()
        if run is None:
            return None
        if run.status not in {
            TaskRunStatus.CLAIMED,
            TaskRunStatus.RUNNING,
            TaskRunStatus.WAITING_INPUT,
            TaskRunStatus.CANCELLING,
        }:
            return run

        run.heartbeat_at = datetime.now(timezone.utc)
        if checkpoint_stage:
            run.checkpoint_stage = checkpoint_stage
        if lease_owner:
            run.lease_owner = lease_owner

        await self.db.commit()
        await self.db.refresh(run)
        return run
