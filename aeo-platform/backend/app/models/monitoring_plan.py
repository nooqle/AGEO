"""Monitoring question set, plan, run, and evidence models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.snapshot import JSONText

if TYPE_CHECKING:
    from app.models.entity import Entity
    from app.models.monitoring_schedule import MonitoringSchedule
    from app.models.user import User


class QuestionSetStatus(str, PyEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    ARCHIVED = "archived"


class QuestionSetSource(str, PyEnum):
    CHAT_GENERATED = "chat_generated"
    IMPORTED = "imported"
    MANUAL = "manual"
    REPORT_SEEDED = "report_seeded"


class MonitoringPlanStatus(str, PyEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class MonitoringRunPolicy(str, PyEnum):
    QUICK = "quick"
    FULL_BROWSER = "full_browser"
    MANUAL = "manual"


class MonitoringRunStatus(str, PyEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class MonitoringQuestionSet(Base):
    """A user-confirmable question set used by monitoring plans."""

    __tablename__ = "monitoring_question_sets"

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
    monitor_mode: Mapped[str] = mapped_column(
        String(32), default="panorama", nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default=QuestionSetStatus.DRAFT.value, nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(
        String(32),
        default=QuestionSetSource.CHAT_GENERATED.value,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    questions: Mapped[list | None] = mapped_column(JSONText, nullable=True)
    question_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    extra_metadata: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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

    user: Mapped["User"] = relationship("User", backref="monitoring_question_sets")
    entity: Mapped["Entity"] = relationship(
        "Entity", backref="monitoring_question_sets"
    )


class MonitoringPlan(Base):
    """A confirmed monitoring plan composed from one or more question sets."""

    __tablename__ = "monitoring_plans"

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
    monitor_mode: Mapped[str] = mapped_column(
        String(32), default="panorama", nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default=MonitoringPlanStatus.DRAFT.value, nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    question_set_ids: Mapped[list | None] = mapped_column(JSONText, nullable=True)
    endpoint_ids: Mapped[list | None] = mapped_column(JSONText, nullable=True)
    run_policy: Mapped[str] = mapped_column(
        String(32), default=MonitoringRunPolicy.QUICK.value, nullable=False
    )
    frequency: Mapped[str] = mapped_column(String(32), default="weekly", nullable=False)
    preferred_hour: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    timezone: Mapped[str] = mapped_column(
        String(50), default="Asia/Shanghai", nullable=False
    )
    extra_metadata: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
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

    user: Mapped["User"] = relationship("User", backref="monitoring_plans")
    entity: Mapped["Entity"] = relationship("Entity", backref="monitoring_plans")
    schedules: Mapped[list["MonitoringSchedule"]] = relationship(
        "MonitoringSchedule",
        back_populates="monitoring_plan",
        foreign_keys="MonitoringSchedule.monitoring_plan_id",
    )


class MonitoringRun(Base):
    """A user-visible monitoring run linked to scheduler task execution."""

    __tablename__ = "monitoring_runs"

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
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("monitoring_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("monitoring_schedules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    task_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("task_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_snapshots.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32), default=MonitoringRunStatus.PENDING.value, nullable=False, index=True
    )
    run_policy: Mapped[str] = mapped_column(
        String(32), default=MonitoringRunPolicy.QUICK.value, nullable=False
    )
    monitor_mode: Mapped[str] = mapped_column(
        String(32), default="panorama", nullable=False, index=True
    )
    endpoint_ids: Mapped[list | None] = mapped_column(JSONText, nullable=True)
    question_set_ids: Mapped[list | None] = mapped_column(JSONText, nullable=True)
    question_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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

    plan: Mapped["MonitoringPlan"] = relationship("MonitoringPlan", backref="runs")


class MonitoringEvidenceRecord(Base):
    """Evidence row extracted from a monitoring run's A4/A5 payload."""

    __tablename__ = "monitoring_evidence_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    monitoring_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("monitoring_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("monitoring_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    question_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    endpoint_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    endpoint_label: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    platform: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    fetch_method: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    answer_status: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    cited_domains: Mapped[list | None] = mapped_column(JSONText, nullable=True)
    raw_evidence: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    run: Mapped["MonitoringRun"] = relationship(
        "MonitoringRun", backref="evidence_records"
    )
