"""Analysis Task model -- tracks lifecycle of each analysis pipeline execution."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import (Boolean, DateTime, Enum, Float, ForeignKey, Integer,
                        String, Text)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.snapshot import JSONText  # Reuse from Cycle 2

if TYPE_CHECKING:
    from app.models.entity import Entity
    from app.models.llm_usage import LLMUsageRecord
    from app.models.monitoring_schedule import MonitoringSchedule
    from app.models.session import Session
    from app.models.task_run import TaskRun
    from app.models.user import User


class TaskStatus(str, PyEnum):
    """Task lifecycle status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AnalysisTask(Base):
    """Tracks each analysis pipeline execution.

    Created when user initiates a brand analysis.
    Updated as workflow progresses through A1-A5.
    Referenced by frontend for task list and reconnection.

    Design note: AnalysisTask has a many-to-one relationship with Session.
    A single session may contain multiple tasks over time (e.g., initial analysis
    followed by a scoped re-run via answer_fetch). Each task represents one pipeline execution.
    """

    __tablename__ = "analysis_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=True,  # Nullable for scheduled (headless) tasks
        index=True,
    )
    # Link to monitoring schedule (null for manual analyses)
    monitoring_schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("monitoring_schedules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Task metadata
    brand_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus),
        default=TaskStatus.PENDING,
        nullable=False,
        index=True,
    )
    current_stage: Mapped[str] = mapped_column(String(10), default="", nullable=False)

    # Progress tracking
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    progress_message: Mapped[str] = mapped_column(
        String(255), default="", nullable=False
    )

    # LLM usage aggregate
    llm_call_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    llm_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    llm_completion_tokens: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    llm_total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    llm_cached_prompt_tokens: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    llm_billable_prompt_tokens: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    llm_total_latency_ms: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    llm_estimated_cost: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )
    llm_estimated_cost_cache_aware: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )

    # Stage results snapshot (for reconnection replay)
    #
    # CONCURRENCY NOTE (Review C1/T2): This JSON column is subject to concurrent
    # read-modify-write from multiple async tasks. All writes to this field MUST
    # use SELECT FOR UPDATE row-level locking within a transaction:
    #   async with db.begin():
    #       task = await db.execute(
    #           select(AnalysisTask).where(...).with_for_update()
    #       )
    #       # modify stage_results_cache
    #       await db.flush()
    stage_results_cache: Mapped[dict | None] = mapped_column(JSONText, nullable=True)

    # Result references
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Error info (if failed)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_stage: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Notification preferences
    notify_on_complete: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", backref="analysis_tasks")
    session: Mapped["Session | None"] = relationship(
        "Session", backref="analysis_tasks"
    )
    entity: Mapped["Entity | None"] = relationship("Entity", backref="analysis_tasks")
    schedule: Mapped["MonitoringSchedule | None"] = relationship(
        "MonitoringSchedule",
        back_populates="tasks",
        foreign_keys=[monitoring_schedule_id],
    )
    llm_usage_records: Mapped[list["LLMUsageRecord"]] = relationship(
        "LLMUsageRecord",
        back_populates="task",
        cascade="all, delete-orphan",
    )
    task_runs: Mapped[list["TaskRun"]] = relationship(
        "TaskRun",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskRun.submitted_at.desc()",
    )

    def __repr__(self) -> str:
        return (
            f"<AnalysisTask(id={self.id}, brand={self.brand_name}, "
            f"status={self.status}, stage={self.current_stage})>"
        )
