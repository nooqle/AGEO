"""Persistence service for nested TaskRun attempts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import AnalysisTask
from app.models.task_run import TaskRun
from app.models.task_run_child_attempt import (
    TaskRunChildAttempt,
    TaskRunChildAttemptKind,
    TaskRunChildAttemptStatus,
)


@dataclass(frozen=True, slots=True)
class WaitingInputReplayRecord:
    """Replay payload for unresolved browser-action attempts."""

    request_id: str
    platform: str
    action_type: str
    message: str
    action_hint: str | None
    progress: float
    task_id: UUID
    task_run_id: UUID
    user_id: UUID


class TaskRunChildAttemptService:
    """Manage durable child attempts under a TaskRun."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _finalize_superseded_waiting_inputs(
        self,
        *,
        task_run_id: UUID,
        platform: str,
        action_type: str,
        exclude_request_id: str | None = None,
    ) -> int:
        """Mark older unresolved browser-action requests as superseded.

        One task run should only surface one active waiting_input request for the
        same platform/action pair. Keeping stale duplicates around causes replay
        to reopen obsolete takeover modals after the user has already handled the
        newest blocker.
        """

        stmt = (
            select(TaskRunChildAttempt)
            .where(TaskRunChildAttempt.task_run_id == task_run_id)
            .where(
                TaskRunChildAttempt.child_kind
                == TaskRunChildAttemptKind.A4_BROWSER_ACTION
            )
            .where(TaskRunChildAttempt.platform == platform)
            .where(TaskRunChildAttempt.action_type == action_type)
            .where(
                TaskRunChildAttempt.status == TaskRunChildAttemptStatus.WAITING_INPUT
            )
            .where(TaskRunChildAttempt.resolved_at.is_(None))
        )
        if exclude_request_id:
            stmt = stmt.where(TaskRunChildAttempt.request_id != exclude_request_id)

        result = await self.db.execute(stmt)
        attempts = list(result.scalars().all())
        if not attempts:
            return 0

        now = datetime.now(timezone.utc)
        for attempt in attempts:
            attempt.status = TaskRunChildAttemptStatus.SKIPPED
            attempt.resolution = "superseded"
            attempt.error_message = "已被更新的浏览器接管请求替代"
            attempt.resolved_at = now
            attempt.updated_at = now
        return len(attempts)

    async def create_browser_action_attempt(
        self,
        *,
        task_run_id: UUID,
        request_id: str,
        platform: str,
        action_type: str,
        message: str,
        action_hint: str | None,
        progress: float,
        step: str = "A4",
    ) -> TaskRunChildAttempt:
        await self._finalize_superseded_waiting_inputs(
            task_run_id=task_run_id,
            platform=platform,
            action_type=action_type,
        )
        attempt = TaskRunChildAttempt(
            task_run_id=task_run_id,
            child_kind=TaskRunChildAttemptKind.A4_BROWSER_ACTION,
            status=TaskRunChildAttemptStatus.WAITING_INPUT,
            step=step,
            platform=platform,
            action_type=action_type,
            request_id=request_id,
            message=message,
            action_hint=action_hint,
            progress=progress,
        )
        self.db.add(attempt)
        await self.db.commit()
        await self.db.refresh(attempt)
        return attempt

    async def get_by_request_id(self, request_id: str) -> TaskRunChildAttempt | None:
        stmt = select(TaskRunChildAttempt).where(
            TaskRunChildAttempt.request_id == request_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def resolve_by_request_id(
        self,
        request_id: str,
        *,
        resolution: str,
    ) -> TaskRunChildAttempt | None:
        attempt = await self.get_by_request_id(request_id)
        if attempt is None:
            return None

        if attempt.status != TaskRunChildAttemptStatus.WAITING_INPUT:
            return attempt

        now = datetime.now(timezone.utc)
        attempt.resolution = resolution
        attempt.status = (
            TaskRunChildAttemptStatus.COMPLETED
            if resolution == "completed"
            else TaskRunChildAttemptStatus.SKIPPED
        )
        attempt.resolved_at = now
        attempt.updated_at = now
        await self._finalize_superseded_waiting_inputs(
            task_run_id=attempt.task_run_id,
            platform=attempt.platform,
            action_type=attempt.action_type,
            exclude_request_id=request_id,
        )
        await self.db.commit()
        await self.db.refresh(attempt)
        return attempt

    async def finalize_unresolved_by_request_id(
        self,
        request_id: str,
        *,
        final_status: TaskRunChildAttemptStatus,
        error_message: str | None = None,
    ) -> TaskRunChildAttempt | None:
        attempt = await self.get_by_request_id(request_id)
        if attempt is None:
            return None

        if attempt.status != TaskRunChildAttemptStatus.WAITING_INPUT:
            return attempt

        now = datetime.now(timezone.utc)
        attempt.status = final_status
        attempt.error_message = error_message
        attempt.resolved_at = now
        attempt.updated_at = now
        await self.db.commit()
        await self.db.refresh(attempt)
        return attempt

    async def list_waiting_input_for_session(
        self,
        session_id: UUID,
    ) -> list[TaskRunChildAttempt]:
        """List unresolved browser-action attempts bound to one session."""

        stmt = (
            select(TaskRunChildAttempt)
            .join(TaskRun, TaskRun.id == TaskRunChildAttempt.task_run_id)
            .join(AnalysisTask, AnalysisTask.id == TaskRun.task_id)
            .where(AnalysisTask.session_id == session_id)
            .where(
                TaskRunChildAttempt.child_kind
                == TaskRunChildAttemptKind.A4_BROWSER_ACTION
            )
            .where(
                TaskRunChildAttempt.status == TaskRunChildAttemptStatus.WAITING_INPUT
            )
            .where(TaskRunChildAttempt.resolved_at.is_(None))
            .order_by(TaskRunChildAttempt.updated_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_waiting_input_for_session_by_request_id(
        self,
        *,
        session_id: UUID,
        request_id: str,
    ) -> TaskRunChildAttempt | None:
        """Return one unresolved browser-action attempt for a session/request pair."""

        stmt = (
            select(TaskRunChildAttempt)
            .join(TaskRun, TaskRun.id == TaskRunChildAttempt.task_run_id)
            .join(AnalysisTask, AnalysisTask.id == TaskRun.task_id)
            .where(AnalysisTask.session_id == session_id)
            .where(
                TaskRunChildAttempt.child_kind
                == TaskRunChildAttemptKind.A4_BROWSER_ACTION
            )
            .where(TaskRunChildAttempt.request_id == request_id)
            .where(
                TaskRunChildAttempt.status == TaskRunChildAttemptStatus.WAITING_INPUT
            )
            .where(TaskRunChildAttempt.resolved_at.is_(None))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_waiting_input_replay_records_for_session(
        self,
        session_id: UUID,
        *,
        task_id: UUID | None = None,
        task_run_id: UUID | None = None,
    ) -> list[WaitingInputReplayRecord]:
        """Return unresolved browser-action attempts with task/user context."""

        stmt = (
            select(
                TaskRunChildAttempt.request_id,
                TaskRunChildAttempt.platform,
                TaskRunChildAttempt.action_type,
                TaskRunChildAttempt.message,
                TaskRunChildAttempt.action_hint,
                TaskRunChildAttempt.progress,
                AnalysisTask.id.label("task_id"),
                TaskRun.id.label("task_run_id"),
                AnalysisTask.user_id.label("user_id"),
            )
            .join(TaskRun, TaskRun.id == TaskRunChildAttempt.task_run_id)
            .join(AnalysisTask, AnalysisTask.id == TaskRun.task_id)
            .where(AnalysisTask.session_id == session_id)
            .where(
                TaskRunChildAttempt.child_kind
                == TaskRunChildAttemptKind.A4_BROWSER_ACTION
            )
            .where(
                TaskRunChildAttempt.status == TaskRunChildAttemptStatus.WAITING_INPUT
            )
            .where(TaskRunChildAttempt.resolved_at.is_(None))
            .order_by(TaskRunChildAttempt.updated_at.desc())
        )
        if task_id is not None:
            stmt = stmt.where(AnalysisTask.id == task_id)
        if task_run_id is not None:
            stmt = stmt.where(TaskRun.id == task_run_id)
        result = await self.db.execute(stmt)
        rows = result.all()
        deduped_rows = []
        seen_keys: set[tuple[str, str, str]] = set()
        for row in rows:
            if task_id is not None and getattr(row, "task_id", None) != task_id:
                continue
            if task_run_id is not None and getattr(row, "task_run_id", None) != task_run_id:
                continue
            dedupe_key = (
                str(row.task_id),
                str(row.platform or ""),
                str(row.action_type or ""),
            )
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            deduped_rows.append(row)
        return [
            WaitingInputReplayRecord(
                request_id=row.request_id,
                platform=row.platform,
                action_type=row.action_type,
                message=row.message,
                action_hint=row.action_hint,
                progress=row.progress,
                task_id=row.task_id,
                task_run_id=row.task_run_id,
                user_id=row.user_id,
            )
            for row in deduped_rows
        ]
