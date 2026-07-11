"""Amway China circle tracking snapshots."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.snapshot import JSONText


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AmwayCircleRun(Base):
    __tablename__ = "amway_circle_runs"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "run_sequence",
            name="uq_amway_circle_runs_entity_sequence",
        ),
        UniqueConstraint(
            "brand_intelligence_run_id",
            name="uq_amway_circle_runs_bi_run",
        ),
        UniqueConstraint("id", "entity_id", name="uq_amway_circle_runs_id_entity"),
        Index("ix_amway_circle_runs_entity_created", "entity_id", "created_at"),
        Index("ix_amway_circle_runs_entity_sequence", "entity_id", "run_sequence"),
        Index("ix_amway_circle_runs_status", "status"),
        Index("ix_amway_circle_runs_question_set", "question_set_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    brand_intelligence_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brand_intelligence_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    analysis_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    question_set_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("monitoring_question_sets.id", ondelete="SET NULL"),
        nullable=True,
    )
    run_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    run_label: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    center_term: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    center_terms: Mapped[list] = mapped_column(JSONText, default=list, nullable=False)
    platforms_requested: Mapped[list] = mapped_column(
        JSONText, default=list, nullable=False
    )
    platforms_completed: Mapped[list] = mapped_column(
        JSONText, default=list, nullable=False
    )
    question_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expected_answer_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    valid_answer_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_answer_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    answer_scope: Mapped[dict] = mapped_column(JSONText, default=dict, nullable=False)
    question_signature: Mapped[str] = mapped_column(
        String(80), default="", nullable=False
    )
    lexicon_version: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    lexicon_hash: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    extraction_version: Mapped[str] = mapped_column(
        String(80), default="", nullable=False
    )
    calibration_version: Mapped[str] = mapped_column(
        String(80), default="", nullable=False
    )
    projection_version: Mapped[str] = mapped_column(
        String(80), default="", nullable=False
    )
    include_in_cumulative: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    excluded_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class AmwayCircleAnswer(Base):
    __tablename__ = "amway_circle_answers"
    __table_args__ = (
        UniqueConstraint(
            "circle_run_id",
            "question_id",
            "platform",
            name="uq_amway_circle_answers_run_question_platform",
        ),
        UniqueConstraint(
            "id",
            "circle_run_id",
            name="uq_amway_circle_answers_id_run",
        ),
        ForeignKeyConstraint(
            ["circle_run_id", "entity_id"],
            ["amway_circle_runs.id", "amway_circle_runs.entity_id"],
            ondelete="CASCADE",
        ),
        Index("ix_amway_circle_answers_run_platform", "circle_run_id", "platform"),
        Index("ix_amway_circle_answers_run_question", "circle_run_id", "question_id"),
        Index(
            "ix_amway_circle_answers_run_question_hash",
            "circle_run_id",
            "question_hash",
        ),
        Index("ix_amway_circle_answers_entity_platform", "entity_id", "platform"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    circle_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("amway_circle_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_set_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("monitoring_question_sets.id", ondelete="SET NULL"),
        nullable=True,
    )
    question_id: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    question_hash: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    question_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    question_metadata: Mapped[dict] = mapped_column(
        JSONText, default=dict, nullable=False
    )
    platform: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    platform_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fetch_agent_version: Mapped[str] = mapped_column(
        String(80), default="", nullable=False
    )
    fetch_status: Mapped[str] = mapped_column(
        String(32), default="success", nullable=False
    )
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    mentions_center: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    center_context_type: Mapped[str] = mapped_column(
        String(32), default="none", nullable=False
    )
    answer_quality: Mapped[str] = mapped_column(
        String(32), default="valid", nullable=False
    )
    raw_payload: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class AmwayCircleEntityMention(Base):
    __tablename__ = "amway_circle_entity_mentions"
    __table_args__ = (
        UniqueConstraint(
            "circle_run_id",
            "answer_id",
            "dedupe_key",
            name="uq_amway_mentions_dedupe",
        ),
        UniqueConstraint(
            "id",
            "circle_run_id",
            name="uq_amway_mentions_id_run",
        ),
        ForeignKeyConstraint(
            ["answer_id", "circle_run_id"],
            ["amway_circle_answers.id", "amway_circle_answers.circle_run_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["circle_run_id", "entity_id"],
            ["amway_circle_runs.id", "amway_circle_runs.entity_id"],
            ondelete="CASCADE",
        ),
        Index("ix_amway_mentions_run_entity", "circle_run_id", "canonical_name"),
        Index("ix_amway_mentions_answer", "answer_id"),
        Index("ix_amway_mentions_entity_type", "entity_type"),
        Index("ix_amway_mentions_risk_context", "risk_context"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    circle_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("amway_circle_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    answer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    lexicon_entity_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    canonical_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(32), default="lexicon", nullable=False
    )
    matched_text: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    matched_alias: Mapped[str | None] = mapped_column(String(240), nullable=True)
    context_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    evidence_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    relation_type: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    amway_anchor: Mapped[str] = mapped_column(
        String(32), default="none", nullable=False
    )
    sentiment_context: Mapped[str] = mapped_column(
        String(32), default="neutral", nullable=False
    )
    risk_context: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    extractor_version: Mapped[str] = mapped_column(
        String(80), default="", nullable=False
    )
    dedupe_key: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class AmwayCircleEvidence(Base):
    __tablename__ = "amway_circle_evidence"
    __table_args__ = (
        UniqueConstraint(
            "circle_run_id",
            "evidence_ref",
            name="uq_amway_evidence_run_ref",
        ),
        ForeignKeyConstraint(
            ["answer_id", "circle_run_id"],
            ["amway_circle_answers.id", "amway_circle_answers.circle_run_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["mention_id", "circle_run_id"],
            [
                "amway_circle_entity_mentions.id",
                "amway_circle_entity_mentions.circle_run_id",
            ],
        ),
        Index("ix_amway_evidence_run_ref", "circle_run_id", "evidence_ref"),
        Index("ix_amway_evidence_answer", "answer_id"),
        Index("ix_amway_evidence_platform", "platform"),
        Index("ix_amway_evidence_quote_type", "quote_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    circle_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("amway_circle_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    answer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    mention_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    evidence_ref: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    platform: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    question_id: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    question_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    quote_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    quote_type: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    entity_names: Mapped[list] = mapped_column(JSONText, default=list, nullable=False)
    strategy_terms: Mapped[list] = mapped_column(JSONText, default=list, nullable=False)
    scenario_tags: Mapped[list] = mapped_column(JSONText, default=list, nullable=False)
    source_rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class AmwayCircleNodeSnapshot(Base):
    __tablename__ = "amway_circle_node_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "circle_run_id",
            "node_id",
            name="uq_amway_nodes_run_node",
        ),
        UniqueConstraint(
            "id",
            "circle_run_id",
            name="uq_amway_nodes_id_run",
        ),
        ForeignKeyConstraint(
            ["circle_run_id", "entity_id"],
            ["amway_circle_runs.id", "amway_circle_runs.entity_id"],
            ondelete="CASCADE",
        ),
        Index("ix_amway_nodes_run_track", "circle_run_id", "track"),
        Index("ix_amway_nodes_run_type", "circle_run_id", "entity_type"),
        Index("ix_amway_nodes_run_lexicon", "circle_run_id", "lexicon_entity_id"),
        Index("ix_amway_nodes_run_priority", "circle_run_id", "display_priority"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    circle_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("amway_circle_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    node_id: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    lexicon_entity_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    canonical_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    track: Mapped[str] = mapped_column(String(32), default="watch", nullable=False)
    track_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    mention_answer_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    question_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    platform_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    center_anchor_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    amway_anchor_ratio: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )
    gravity_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    distance_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    stability_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    position_x: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    position_y: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    node_size: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    display_priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    platform_summary: Mapped[dict] = mapped_column(
        JSONText, default=dict, nullable=False
    )
    question_summary: Mapped[dict] = mapped_column(
        JSONText, default=dict, nullable=False
    )
    evidence_refs: Mapped[list] = mapped_column(JSONText, default=list, nullable=False)
    calibration_payload: Mapped[dict] = mapped_column(
        JSONText, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class AmwayCircleEdgeSnapshot(Base):
    __tablename__ = "amway_circle_edge_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "circle_run_id",
            "edge_id",
            name="uq_amway_edges_run_edge",
        ),
        ForeignKeyConstraint(
            ["circle_run_id", "source_node_id"],
            [
                "amway_circle_node_snapshots.circle_run_id",
                "amway_circle_node_snapshots.node_id",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["circle_run_id", "target_node_id"],
            [
                "amway_circle_node_snapshots.circle_run_id",
                "amway_circle_node_snapshots.node_id",
            ],
            ondelete="CASCADE",
        ),
        Index("ix_amway_edges_run_source", "circle_run_id", "source_node_id"),
        Index("ix_amway_edges_run_target", "circle_run_id", "target_node_id"),
        Index("ix_amway_edges_relation", "relation_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    circle_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("amway_circle_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    edge_id: Mapped[str] = mapped_column(String(180), default="", nullable=False)
    source_node_id: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    target_node_id: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    relation_type: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    relation_label: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    strength_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    risk_context: Mapped[str | None] = mapped_column(String(32), nullable=True)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    platform_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    evidence_refs: Mapped[list] = mapped_column(JSONText, default=list, nullable=False)
    edge_payload: Mapped[dict] = mapped_column(JSONText, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class AmwayCircleProjection(Base):
    __tablename__ = "amway_circle_projections"
    __table_args__ = (
        Index(
            "ix_amway_projections_entity_scope",
            "entity_id",
            "projection_scope",
            "is_latest",
        ),
        Index("ix_amway_projections_run", "circle_run_id"),
        Index("ix_amway_projections_as_of", "as_of_run_id"),
        Index("ix_amway_projections_compare", "base_run_id", "target_run_id"),
        Index(
            "uq_amway_latest_projection_scope",
            "entity_id",
            "projection_scope",
            unique=True,
            postgresql_where=text("is_latest = true"),
        ),
        Index(
            "uq_amway_projection_source_hash",
            "entity_id",
            "projection_scope",
            "projection_version",
            "source_run_hash",
            unique=True,
            postgresql_where=text("source_run_hash <> ''"),
        ),
        UniqueConstraint(
            "id",
            "entity_id",
            name="uq_amway_projections_id_entity",
        ),
        UniqueConstraint(
            "id",
            "circle_run_id",
            name="uq_amway_projections_id_run",
        ),
        ForeignKeyConstraint(
            ["circle_run_id", "entity_id"],
            ["amway_circle_runs.id", "amway_circle_runs.entity_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["base_run_id", "entity_id"],
            ["amway_circle_runs.id", "amway_circle_runs.entity_id"],
        ),
        ForeignKeyConstraint(
            ["target_run_id", "entity_id"],
            ["amway_circle_runs.id", "amway_circle_runs.entity_id"],
        ),
        ForeignKeyConstraint(
            ["as_of_run_id", "entity_id"],
            ["amway_circle_runs.id", "amway_circle_runs.entity_id"],
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    circle_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    base_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    target_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    as_of_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    projection_scope: Mapped[str] = mapped_column(
        String(32), default="run", nullable=False
    )
    projection_version: Mapped[str] = mapped_column(
        String(80), default="", nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), default="ready", nullable=False)
    is_latest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_run_ids: Mapped[list] = mapped_column(JSONText, default=list, nullable=False)
    source_run_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_run_hash: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    sample_scope: Mapped[dict] = mapped_column(JSONText, default=dict, nullable=False)
    association_circle_projection: Mapped[dict] = mapped_column(
        JSONText, default=dict, nullable=False
    )
    report_input: Mapped[dict] = mapped_column(JSONText, default=dict, nullable=False)
    compare_summary: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    data_quality: Mapped[dict] = mapped_column(JSONText, default=dict, nullable=False)
    built_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class AmwayCircleReport(Base):
    __tablename__ = "amway_circle_reports"
    __table_args__ = (
        Index("ix_amway_reports_entity_scope", "entity_id", "report_scope"),
        Index("ix_amway_reports_projection", "projection_id"),
        Index("ix_amway_reports_run", "circle_run_id"),
        ForeignKeyConstraint(
            ["projection_id", "entity_id"],
            ["amway_circle_projections.id", "amway_circle_projections.entity_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["projection_id", "circle_run_id"],
            ["amway_circle_projections.id", "amway_circle_projections.circle_run_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["circle_run_id", "entity_id"],
            ["amway_circle_runs.id", "amway_circle_runs.entity_id"],
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    projection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("amway_circle_projections.id", ondelete="CASCADE"),
        nullable=False,
    )
    circle_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("amway_circle_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    report_scope: Mapped[str] = mapped_column(String(32), default="run", nullable=False)
    report_version: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    title: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    markdown_body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    structured_body: Mapped[dict] = mapped_column(
        JSONText, default=dict, nullable=False
    )
    source_report_input: Mapped[dict] = mapped_column(
        JSONText, default=dict, nullable=False
    )
    source_projection_hash: Mapped[str] = mapped_column(
        String(80), default="", nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class AmwayCircleExport(Base):
    __tablename__ = "amway_circle_exports"
    __table_args__ = (
        Index("ix_amway_exports_entity_created", "entity_id", "created_at"),
        Index("ix_amway_exports_projection", "projection_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    projection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("amway_circle_projections.id", ondelete="CASCADE"),
        nullable=False,
    )
    report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("amway_circle_reports.id", ondelete="SET NULL"),
        nullable=True,
    )
    circle_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("amway_circle_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    export_type: Mapped[str] = mapped_column(String(32), default="html", nullable=False)
    export_scope: Mapped[str] = mapped_column(String(32), default="run", nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, default="", nullable=False)
    content_hash: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    include_graph: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    include_answer_appendix: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class AmwayCircleRuntimeEvent(Base):
    __tablename__ = "amway_circle_runtime_events"
    __table_args__ = (
        UniqueConstraint(
            "circle_run_id",
            "sequence",
            name="uq_amway_events_run_sequence",
        ),
        Index("ix_amway_events_run_sequence", "circle_run_id", "sequence"),
        Index("ix_amway_events_type", "event_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    circle_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("amway_circle_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    stage: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    payload: Mapped[dict] = mapped_column(JSONText, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
