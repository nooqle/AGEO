"""Monitoring Schedule model -- defines automated periodic analysis configuration."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.snapshot import JSONText

if TYPE_CHECKING:
    from app.models.entity import Entity
    from app.models.monitoring_plan import MonitoringPlan
    from app.models.task import AnalysisTask
    from app.models.user import User


class ScheduleFrequency(str, PyEnum):
    """Monitoring frequency options."""

    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"


class ScheduleStatus(str, PyEnum):
    """Schedule lifecycle status."""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"


class MonitoringSchedule(Base):
    """Defines an automated periodic analysis configuration for a brand entity.

    Design notes:
    - Legacy schedules without a plan keep one active schedule per entity/mode.
    - Plan-backed schedules are independent so multiple active plans can run.
    - Each scheduled execution creates an AnalysisTask (via monitoring_schedule_id FK).
    - The scheduler reads active schedules and creates tasks when next_run_at <= now().
    - Chat-first: schedules can be created via natural language OR settings UI.
    """

    __tablename__ = "monitoring_schedules"

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
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    monitoring_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("monitoring_plans.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Schedule configuration
    frequency: Mapped[ScheduleFrequency] = mapped_column(
        Enum(ScheduleFrequency),
        default=ScheduleFrequency.WEEKLY,
        nullable=False,
    )
    status: Mapped[ScheduleStatus] = mapped_column(
        Enum(ScheduleStatus),
        default=ScheduleStatus.ACTIVE,
        nullable=False,
        index=True,
    )

    # Preferred execution time (hour of day, 0-23)
    preferred_hour: Mapped[int] = mapped_column(
        Integer, default=3, nullable=False
    )

    # Timezone for preferred_hour interpretation (IANA timezone string)
    timezone: Mapped[str] = mapped_column(
        String(50), default="Asia/Shanghai", nullable=False
    )

    # Platform configuration (JSON list of platform names)
    platforms: Mapped[list | None] = mapped_column(
        JSONText, nullable=True
    )
    monitor_mode: Mapped[str] = mapped_column(
        String(32), default="panorama", nullable=False, index=True
    )
    question_set_ids: Mapped[list | None] = mapped_column(
        JSONText, nullable=True
    )
    endpoint_ids: Mapped[list | None] = mapped_column(
        JSONText, nullable=True
    )
    run_policy: Mapped[str] = mapped_column(
        String(32), default="quick", nullable=False
    )

    # Alert configuration
    alert_on_significant_change: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    alert_threshold_bwvs: Mapped[float] = mapped_column(
        Float, default=10.0, nullable=False
    )

    # Execution tracking
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    total_runs: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    max_failures: Mapped[int] = mapped_column(
        Integer, default=3, nullable=False
    )

    # Baseline data for monitoring reuse (first run saves A1+A3 output,
    # subsequent runs skip A1-A3 and only re-run A4+A5 with same questions)
    baseline_data: Mapped[dict | None] = mapped_column(
        JSONText, nullable=True
    )

    # Optional limits
    max_runs: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    end_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Timestamps
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

    # Relationships
    user: Mapped["User"] = relationship("User", backref="monitoring_schedules")
    entity: Mapped["Entity"] = relationship(
        "Entity", backref="monitoring_schedules"
    )
    monitoring_plan: Mapped["MonitoringPlan | None"] = relationship(
        "MonitoringPlan",
        back_populates="schedules",
        foreign_keys=[monitoring_plan_id],
    )
    tasks: Mapped[list["AnalysisTask"]] = relationship(
        "AnalysisTask",
        back_populates="schedule",
        foreign_keys="AnalysisTask.monitoring_schedule_id",
    )

    def __repr__(self) -> str:
        return (
            f"<MonitoringSchedule(id={self.id}, entity={self.entity_id}, "
            f"freq={self.frequency}, status={self.status})>"
        )
