"""Persistence service for nested TaskRun attempts."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_run_child_attempt import (
    TaskRunChildAttempt,
    TaskRunChildAttemptKind,
    TaskRunChildAttemptStatus,
)


class TaskRunChildAttemptService:
    """Manage durable child attempts under a TaskRun."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

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
