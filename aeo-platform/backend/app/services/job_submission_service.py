"""Unified submission service for task + runtime attempt creation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session
from app.models.task import AnalysisTask, TaskStatus
from app.models.task_run import (
    ExecutorKind,
    LIVE_TASK_RUN_STATUSES,
    TaskRun,
    TaskRunKind,
    TaskRunStatus,
    TaskTriggerSource,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SubmittedJob:
    """Submission result used by current entrypoints."""

    task: AnalysisTask
    run: TaskRun


class JobSubmissionService:
    """Creates a business task and its first durable runtime attempt."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def submit_manual_analysis(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        brand_name: str,
        entity_id: UUID | None = None,
        trigger_source: TaskTriggerSource = TaskTriggerSource.WEBSOCKET,
    ) -> SubmittedJob:
        return await self._submit(
            user_id=user_id,
            session_id=session_id,
            brand_name=brand_name,
            entity_id=entity_id,
            monitoring_schedule_id=None,
            run_kind=TaskRunKind.INITIAL,
            trigger_source=trigger_source,
        )

    async def submit_follow_up_analysis(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        brand_name: str,
        entity_id: UUID | None = None,
        trigger_source: TaskTriggerSource = TaskTriggerSource.WEBSOCKET,
    ) -> SubmittedJob:
        return await self._submit(
            user_id=user_id,
            session_id=session_id,
            brand_name=brand_name,
            entity_id=entity_id,
            monitoring_schedule_id=None,
            run_kind=TaskRunKind.FOLLOW_UP,
            trigger_source=trigger_source,
        )

    async def submit_scheduled_analysis(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        brand_name: str,
        entity_id: UUID,
        monitoring_schedule_id: UUID,
    ) -> SubmittedJob:
        return await self._submit(
            user_id=user_id,
            session_id=session_id,
            brand_name=brand_name,
            entity_id=entity_id,
            monitoring_schedule_id=monitoring_schedule_id,
            run_kind=TaskRunKind.SCHEDULED,
            trigger_source=TaskTriggerSource.SCHEDULER,
        )

    async def submit_existing_task_run(
        self,
        *,
        task_id: UUID,
        run_kind: TaskRunKind,
        trigger_source: TaskTriggerSource,
        executor_kind: ExecutorKind = ExecutorKind.LOCAL_WORKFLOW,
        priority: int = 100,
    ) -> SubmittedJob:
        """Create a new runtime attempt for an existing AnalysisTask."""

        now = datetime.now(timezone.utc)
        async with self.db.begin_nested():
            task_stmt = (
                select(AnalysisTask).where(AnalysisTask.id == task_id).with_for_update()
            )
            task_result = await self.db.execute(task_stmt)
            task = task_result.scalar_one_or_none()
            if task is None:
                raise ValueError(f"AnalysisTask not found: {task_id}")

            live_runs_stmt = (
                select(TaskRun)
                .where(
                    TaskRun.task_id == task_id,
                    TaskRun.status.in_(LIVE_TASK_RUN_STATUSES),
                )
                .order_by(TaskRun.submitted_at.desc())
                .with_for_update()
            )
            live_runs_result = await self.db.execute(live_runs_stmt)
            live_runs = list(live_runs_result.scalars().all())

            if run_kind == TaskRunKind.RESUME_AFTER_INPUT:
                if (
                    len(live_runs) != 1
                    or live_runs[0].status != TaskRunStatus.WAITING_INPUT
                ):
                    raise RuntimeError(
                        "Task must have exactly one waiting_input run before resume"
                    )
                previous_run = live_runs[0]
                previous_run.status = TaskRunStatus.COMPLETED
                previous_run.finished_at = previous_run.finished_at or now
                previous_run.heartbeat_at = now
            elif live_runs:
                raise RuntimeError(
                    f"Task {task_id} already has an active runtime attempt"
                )

            attempt_stmt = select(func.max(TaskRun.attempt_no)).where(
                TaskRun.task_id == task_id
            )
            attempt_no = int((await self.db.execute(attempt_stmt)).scalar() or 0) + 1

            run = TaskRun(
                task_id=task.id,
                run_kind=run_kind,
                trigger_source=trigger_source,
                executor_kind=executor_kind,
                status=TaskRunStatus.QUEUED,
                attempt_no=attempt_no,
                priority=priority,
            )
            self.db.add(run)
            await self.db.flush()

        await self.db.commit()
        await self.db.refresh(task)
        await self.db.refresh(run)

        logger.info(
            "[JobSubmission] Submitted follow-up run %s for task %s "
            "(kind=%s, source=%s)",
            run.id,
            task.id,
            run_kind.value,
            trigger_source.value,
        )
        return SubmittedJob(task=task, run=run)

    async def _submit(
        self,
        *,
        user_id: UUID,
        session_id: UUID | None,
        brand_name: str,
        entity_id: UUID | None,
        monitoring_schedule_id: UUID | None,
        run_kind: TaskRunKind,
        trigger_source: TaskTriggerSource,
        executor_kind: ExecutorKind = ExecutorKind.LOCAL_WORKFLOW,
    ) -> SubmittedJob:
        async with self.db.begin_nested():
            if session_id is not None:
                session_stmt = (
                    select(Session.id).where(Session.id == session_id).with_for_update()
                )
                session_result = await self.db.execute(session_stmt)
                if session_result.scalar_one_or_none() is None:
                    raise ValueError(f"Session not found: {session_id}")

                active_task_stmt = (
                    select(AnalysisTask.id)
                    .where(
                        AnalysisTask.session_id == session_id,
                        AnalysisTask.status.in_(
                            [TaskStatus.PENDING, TaskStatus.RUNNING]
                        ),
                    )
                    .limit(1)
                )
                active_task_result = await self.db.execute(active_task_stmt)
                active_task_id = active_task_result.scalar_one_or_none()
                if active_task_id is not None:
                    raise RuntimeError(
                        f"Session {session_id} already has an active analysis task"
                    )

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
            await self.db.flush()

            run = TaskRun(
                task_id=task.id,
                run_kind=run_kind,
                trigger_source=trigger_source,
                executor_kind=executor_kind,
                status=TaskRunStatus.QUEUED,
                attempt_no=1,
            )
            self.db.add(run)
            await self.db.flush()

        await self.db.commit()
        await self.db.refresh(task)
        await self.db.refresh(run)

        logger.info(
            "[JobSubmission] Submitted task %s / run %s (source=%s, session=%s, schedule=%s)",
            task.id,
            run.id,
            trigger_source.value,
            session_id,
            monitoring_schedule_id,
        )
        return SubmittedJob(task=task, run=run)
