"""Brand Space board runtime, graph update, and report guardrail models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.snapshot import JSONText

if TYPE_CHECKING:
    from app.models.brand_intelligence import BrandReportVersion
    from app.models.brand_intelligence_run import BrandIntelligenceRun
    from app.models.entity import Entity
    from app.models.task import AnalysisTask
    from app.models.user import User


def _now() -> datetime:
    return datetime.now(timezone.utc)


class BoardRun(Base):
    """A Brand Space canvas run for one brand and board template."""

    __tablename__ = "board_runs"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "created_by_user_id",
            "origin_event_id",
            name="uq_board_runs_entity_user_origin_event",
        ),
        Index("ix_board_runs_entity_status", "entity_id", "status"),
        Index("ix_board_runs_entity_updated", "entity_id", "updated_at"),
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
    brand_intelligence_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brand_intelligence_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    analysis_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    origin_event_id: Mapped[str | None] = mapped_column(
        String(180),
        nullable=True,
        index=True,
    )
    board_id: Mapped[str] = mapped_column(
        String(120),
        default="ai_visibility_monitor",
        nullable=False,
    )
    template_id: Mapped[str] = mapped_column(
        String(120),
        default="ai_visibility_monitor:v0.1",
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(40),
        default="running",
        nullable=False,
        index=True,
    )
    is_scaffold: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    input_scope: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    active_node_ids: Mapped[list | None] = mapped_column(JSONText, nullable=True)
    output_refs: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        onupdate=_now,
        nullable=False,
    )

    entity: Mapped["Entity"] = relationship("Entity", backref="board_runs")
    created_by_user: Mapped["User | None"] = relationship("User", backref="board_runs")
    brand_intelligence_run: Mapped["BrandIntelligenceRun | None"] = relationship(
        "BrandIntelligenceRun",
        backref="board_runs",
    )
    analysis_task: Mapped["AnalysisTask | None"] = relationship(
        "AnalysisTask",
        backref="board_runs",
    )


class BoardNodeRun(Base):
    """Runtime state for one node inside a Brand Space board run."""

    __tablename__ = "board_node_runs"
    __table_args__ = (
        UniqueConstraint("board_run_id", "node_id", name="uq_board_node_runs_run_node"),
        Index("ix_board_node_runs_board_status", "board_run_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    board_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("board_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id: Mapped[str] = mapped_column(String(120), nullable=False)
    node_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    subtitle: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="queued", nullable=False)
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    position: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    metrics: Mapped[list | None] = mapped_column(JSONText, nullable=True)
    output_artifact_ids: Mapped[list | None] = mapped_column(JSONText, nullable=True)
    config: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        onupdate=_now,
        nullable=False,
    )

    board_run: Mapped["BoardRun"] = relationship("BoardRun", backref="node_runs")


class BoardArtifact(Base):
    """Registered intermediate artifact for a Brand Space board run."""

    __tablename__ = "board_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "board_run_id",
            "artifact_key",
            name="uq_board_artifacts_run_key",
        ),
        Index("ix_board_artifacts_entity_type", "entity_id", "artifact_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    artifact_key: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    board_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("board_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("board_node_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    artifact_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        nullable=False,
    )

    entity: Mapped["Entity"] = relationship("Entity", backref="board_artifacts")
    board_run: Mapped["BoardRun"] = relationship("BoardRun", backref="artifacts")
    node_run: Mapped["BoardNodeRun | None"] = relationship(
        "BoardNodeRun",
        backref="artifacts",
    )


class BoardRuntimeEvent(Base):
    """Append-only event emitted by the board runtime."""

    __tablename__ = "board_runtime_events"
    __table_args__ = (
        Index("ix_board_runtime_events_run_sequence", "board_run_id", "sequence"),
        Index("ix_board_runtime_events_entity_created", "entity_id", "created_at"),
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
    board_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("board_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(40), default="info", nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        nullable=False,
    )

    entity: Mapped["Entity"] = relationship("Entity", backref="board_runtime_events")
    board_run: Mapped["BoardRun"] = relationship("BoardRun", backref="events")


class GraphUpdate(Base):
    """A graph-state update produced by a Brand Space board run."""

    __tablename__ = "graph_updates"
    __table_args__ = (
        Index("ix_graph_updates_entity_status", "entity_id", "status"),
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
    board_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("board_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    before_graph_version: Mapped[str] = mapped_column(String(80), default="v0.0.0", nullable=False)
    after_graph_version: Mapped[str] = mapped_column(String(80), default="v0.1.0", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="needs_review", nullable=False)
    summary: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    graph_snapshot: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        onupdate=_now,
        nullable=False,
    )

    entity: Mapped["Entity"] = relationship("Entity", backref="graph_updates")
    board_run: Mapped["BoardRun | None"] = relationship("BoardRun", backref="graph_updates")
    created_by_user: Mapped["User | None"] = relationship("User", backref="graph_updates")


class GraphPatch(Base):
    """One proposed graph mutation with score and evidence metadata."""

    __tablename__ = "graph_patches"
    __table_args__ = (
        Index("ix_graph_patches_update_status", "graph_update_id", "status"),
        Index("ix_graph_patches_entity_type", "entity_id", "patch_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    graph_update_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("graph_updates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    patch_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="needs_review", nullable=False)
    title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    affected_object_type: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    affected_object_id: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    relation_type: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    connection_strength: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_or_risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    before_payload: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    after_payload: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    score_breakdown: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    evidence_refs: Mapped[list | None] = mapped_column(JSONText, nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        onupdate=_now,
        nullable=False,
    )

    graph_update: Mapped["GraphUpdate"] = relationship("GraphUpdate", backref="patches")
    entity: Mapped["Entity"] = relationship("Entity", backref="graph_patches")
    reviewed_by_user: Mapped["User | None"] = relationship(
        "User",
        backref="reviewed_graph_patches",
    )


class ReportGuardrailResult(Base):
    """Structured validation result for a graph-update report."""

    __tablename__ = "report_guardrail_results"
    __table_args__ = (
        Index("ix_report_guardrails_update_severity", "graph_update_id", "severity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    graph_update_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("graph_updates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    report_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brand_report_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    guardrail_key: Mapped[str] = mapped_column(String(120), nullable=False)
    severity: Mapped[str] = mapped_column(String(40), default="pass", nullable=False)
    title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_now,
        nullable=False,
    )

    graph_update: Mapped["GraphUpdate"] = relationship(
        "GraphUpdate",
        backref="report_guardrails",
    )
    report_version: Mapped["BrandReportVersion | None"] = relationship(
        "BrandReportVersion",
        backref="guardrail_results",
    )
