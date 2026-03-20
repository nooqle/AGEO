"""Runtime execution attempt model for durable task orchestration."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.task import AnalysisTask
    from app.models.task_run_child_attempt import TaskRunChildAttempt


def _enum_values(enum_cls: type[PyEnum]) -> list[str]:
    """Persist enum values instead of enum member names."""

    return [member.value for member in enum_cls]


class TaskRunStatus(str, PyEnum):
    """Execution attempt lifecycle status."""

    QUEUED = "queued"
    CLAIMED = "claimed"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    FAILED = "failed"
    COMPLETED = "completed"


LIVE_TASK_RUN_STATUSES = (
    TaskRunStatus.QUEUED,
    TaskRunStatus.CLAIMED,
    TaskRunStatus.RUNNING,
    TaskRunStatus.WAITING_INPUT,
    TaskRunStatus.CANCELLING,
)


class TaskRunKind(str, PyEnum):
    """Reason a new execution attempt was created."""

    INITIAL = "initial"
    SCHEDULED = "scheduled"
    RESUME_AFTER_INPUT = "resume_after_input"
    RETRY = "retry"
    FOLLOW_UP = "follow_up"


class TaskTriggerSource(str, PyEnum):
    """Which external entrypoint submitted the run."""

    WEBSOCKET = "websocket"
    SCHEDULER = "scheduler"
    MESSAGES_API = "messages_api"
    SYSTEM_RETRY = "system_retry"


class ExecutorKind(str, PyEnum):
    """Execution backend used by the runtime."""

    LOCAL_WORKFLOW = "local_workflow"
    SANDBOX_WORKFLOW = "sandbox_workflow"
    CELERY_FETCH = "celery_fetch"
    EXTERNAL = "external"


class TaskRun(Base):
    """One durable execution attempt for an analysis task."""

    __tablename__ = "task_runs"
    __table_args__ = (
        Index(
            "uq_task_runs_live_per_task",
            "task_id",
            unique=True,
            postgresql_where=text(
                "status IN ('queued','claimed','running','waiting_input','cancelling')"
            ),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_kind: Mapped[TaskRunKind] = mapped_column(
        Enum(
            TaskRunKind,
            name="taskrunkind",
            values_callable=_enum_values,
        ),
        default=TaskRunKind.INITIAL,
        nullable=False,
    )
    trigger_source: Mapped[TaskTriggerSource] = mapped_column(
        Enum(
            TaskTriggerSource,
            name="tasktriggersource",
            values_callable=_enum_values,
        ),
        nullable=False,
        index=True,
    )
    executor_kind: Mapped[ExecutorKind] = mapped_column(
        Enum(
            ExecutorKind,
            name="executorkind",
            values_callable=_enum_values,
        ),
        default=ExecutorKind.LOCAL_WORKFLOW,
        nullable=False,
        index=True,
    )
    status: Mapped[TaskRunStatus] = mapped_column(
        Enum(
            TaskRunStatus,
            name="taskrunstatus",
            values_callable=_enum_values,
        ),
        default=TaskRunStatus.QUEUED,
        nullable=False,
        index=True,
    )
    attempt_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    lease_owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    executor_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    checkpoint_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    checkpoint_payload_ref: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    error_kind: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    task: Mapped["AnalysisTask"] = relationship(
        "AnalysisTask",
        back_populates="task_runs",
    )
    child_attempts: Mapped[list["TaskRunChildAttempt"]] = relationship(
        "TaskRunChildAttempt",
        back_populates="task_run",
        cascade="all, delete-orphan",
        order_by="TaskRunChildAttempt.created_at.desc()",
    )

    def __repr__(self) -> str:
        return (
            f"<TaskRun(id={self.id}, task_id={self.task_id}, status={self.status}, "
            f"kind={self.run_kind}, source={self.trigger_source})>"
        )
