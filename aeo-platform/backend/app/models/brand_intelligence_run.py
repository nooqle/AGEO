"""Product-level run state for brand intelligence workflows."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.snapshot import JSONText

if TYPE_CHECKING:
    from app.models.entity import Entity
    from app.models.session import Session
    from app.models.task import AnalysisTask
    from app.models.user import User


class BrandIntelligenceRunStatus(str, PyEnum):
    """Dashboard-facing brand intelligence run lifecycle."""

    NOT_STARTED = "not_started"
    PLANNING_QUESTIONS = "planning_questions"
    WAITING_SCOPE_CONFIRMATION = "waiting_scope_confirmation"
    FETCHING_ANSWERS = "fetching_answers"
    WAITING_TAKEOVER = "waiting_takeover"
    ANALYZING_METRICS = "analyzing_metrics"
    BUILDING_WORLD = "building_world"
    GENERATING_RECOMMENDATIONS = "generating_recommendations"
    WAITING_USER = "waiting_user"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


BRAND_INTELLIGENCE_ACTIVE_RUN_STATUSES: tuple[str, ...] = (
    BrandIntelligenceRunStatus.NOT_STARTED.value,
    BrandIntelligenceRunStatus.PLANNING_QUESTIONS.value,
    BrandIntelligenceRunStatus.WAITING_SCOPE_CONFIRMATION.value,
    BrandIntelligenceRunStatus.FETCHING_ANSWERS.value,
    BrandIntelligenceRunStatus.WAITING_TAKEOVER.value,
    BrandIntelligenceRunStatus.ANALYZING_METRICS.value,
    BrandIntelligenceRunStatus.BUILDING_WORLD.value,
    BrandIntelligenceRunStatus.GENERATING_RECOMMENDATIONS.value,
    BrandIntelligenceRunStatus.WAITING_USER.value,
)

BRAND_INTELLIGENCE_TERMINAL_RUN_STATUSES: tuple[str, ...] = (
    BrandIntelligenceRunStatus.COMPLETED.value,
    BrandIntelligenceRunStatus.FAILED.value,
    BrandIntelligenceRunStatus.CANCELLED.value,
)


class BrandIntelligenceRun(Base):
    """A product-level task center run for one brand intelligence workflow.

    This model is intentionally separate from AnalysisTask. AnalysisTask remains
    the runtime execution layer; BrandIntelligenceRun is the Dashboard-facing
    state source that can survive Chat navigation and projection refreshes.
    """

    __tablename__ = "brand_intelligence_runs"
    __table_args__ = (
        Index("ix_brand_intelligence_runs_entity_status", "entity_id", "status"),
        Index("ix_brand_intelligence_runs_entity_updated", "entity_id", "updated_at"),
        Index("ix_brand_intelligence_runs_analysis_task", "analysis_task_id"),
        Index("ix_brand_intelligence_runs_origin_event", "origin_event_id"),
        Index("ix_brand_intelligence_runs_requires_user", "requires_user_action"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    origin_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    analysis_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    origin_surface: Mapped[str] = mapped_column(
        String(80), default="dashboard", nullable=False
    )
    origin_event_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(
        String(40),
        default=BrandIntelligenceRunStatus.NOT_STARTED.value,
        nullable=False,
        index=True,
    )
    stage: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    message: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    run_goal: Mapped[str] = mapped_column(Text, default="", nullable=False)
    analysis_mode: Mapped[str] = mapped_column(
        String(40), default="panorama", nullable=False
    )
    input_scope: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    sample_scope: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    output_refs: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    requires_user_action: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    user_action_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    blocking_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
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

    entity: Mapped["Entity"] = relationship("Entity", backref="brand_intelligence_runs")
    created_by_user: Mapped["User | None"] = relationship(
        "User",
        backref="brand_intelligence_runs",
    )
    origin_session: Mapped["Session | None"] = relationship(
        "Session",
        backref="brand_intelligence_runs",
    )
    analysis_task: Mapped["AnalysisTask | None"] = relationship(
        "AnalysisTask",
        backref="brand_intelligence_run",
    )
