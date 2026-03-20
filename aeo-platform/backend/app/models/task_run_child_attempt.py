"""Durable child attempts for task runs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.task_run import TaskRun


def _enum_values(enum_cls: type[PyEnum]) -> list[str]:
    """Persist enum values instead of enum member names."""

    return [member.value for member in enum_cls]


class TaskRunChildAttemptKind(str, PyEnum):
    """Supported child attempt types."""

    A4_BROWSER_ACTION = "a4_browser_action"


class TaskRunChildAttemptStatus(str, PyEnum):
    """Lifecycle for nested task-run attempts."""

    WAITING_INPUT = "waiting_input"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    FAILED = "failed"
    EXPIRED = "expired"


class TaskRunChildAttempt(Base):
    """Durable record for nested execution attempts under a TaskRun."""

    __tablename__ = "task_run_child_attempts"
    __table_args__ = (
        Index("ix_task_run_child_attempts_run_id", "task_run_id"),
        Index("ix_task_run_child_attempts_status", "status"),
        Index("ix_task_run_child_attempts_request_id", "request_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    task_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("task_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    child_kind: Mapped[TaskRunChildAttemptKind] = mapped_column(
        Enum(
            TaskRunChildAttemptKind,
            name="taskrunchildattemptkind",
            values_callable=_enum_values,
        ),
        default=TaskRunChildAttemptKind.A4_BROWSER_ACTION,
        nullable=False,
    )
    status: Mapped[TaskRunChildAttemptStatus] = mapped_column(
        Enum(
            TaskRunChildAttemptStatus,
            name="taskrunchildattemptstatus",
            values_callable=_enum_values,
        ),
        default=TaskRunChildAttemptStatus.WAITING_INPUT,
        nullable=False,
    )
    step: Mapped[str] = mapped_column(String(50), default="A4", nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    request_id: Mapped[str] = mapped_column(String(120), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    action_hint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    resolution: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    task_run: Mapped["TaskRun"] = relationship(
        "TaskRun",
        back_populates="child_attempts",
    )

    def __repr__(self) -> str:
        return (
            f"<TaskRunChildAttempt(id={self.id}, run_id={self.task_run_id}, "
            f"kind={self.child_kind}, status={self.status}, request_id={self.request_id})>"
        )
