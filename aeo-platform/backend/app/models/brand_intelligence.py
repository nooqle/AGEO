"""Durable AI brand intelligence objects.

These tables are the first persistence surface for the "brand world" that
agents will operate over. They intentionally sit beside the existing workflow
state and output messages so A3/A4/A5 can adopt dual-write incrementally.
"""

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
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

from app.core.database import Base
from app.models.snapshot import JSONText

if TYPE_CHECKING:
    from app.models.entity import Entity
    from app.models.message import Message
    from app.models.session import Session
    from app.models.user import User


class BrandCompetitorEntity(Base):
    """A durable competitor object for one monitored brand."""

    __tablename__ = "brand_competitor_entities"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "session_id",
            "competitor_key",
            name="uq_brand_competitor_entity_session_key",
        ),
        Index("ix_brand_competitors_entity_status", "entity_id", "status"),
        Index("ix_brand_competitors_name", "normalized_name"),
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
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    competitor_key: Mapped[str] = mapped_column(String(120), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    website: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    competition_type: Mapped[str] = mapped_column(
        String(80), default="", nullable=False
    )
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        default="suggested",
        nullable=False,
        index=True,
    )
    source_payload: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
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

    entity: Mapped["Entity"] = relationship("Entity", backref="brand_competitors")
    session: Mapped["Session | None"] = relationship(
        "Session",
        backref="brand_competitors",
    )


class BrandAudiencePersona(Base):
    """A durable audience persona object for brand scenario analysis."""

    __tablename__ = "brand_audience_personas"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "session_id",
            "persona_id",
            name="uq_brand_audience_persona_session_id",
        ),
        Index("ix_brand_personas_entity_status", "entity_id", "status"),
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
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    persona_id: Mapped[str] = mapped_column(String(120), nullable=False)
    persona_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    segment: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    priority: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default="generated",
        nullable=False,
        index=True,
    )
    source_payload: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
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

    entity: Mapped["Entity"] = relationship("Entity", backref="brand_personas")
    session: Mapped["Session | None"] = relationship(
        "Session",
        backref="brand_personas",
    )
    scenarios: Mapped[list["BrandUsageScenario"]] = relationship(
        "BrandUsageScenario",
        back_populates="persona",
        lazy="selectin",
    )


class BrandUsageScenario(Base):
    """A durable usage or decision scenario tied to a persona."""

    __tablename__ = "brand_usage_scenarios"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "session_id",
            "scenario_key",
            name="uq_brand_usage_scenario_session_key",
        ),
        Index("ix_brand_scenarios_entity_status", "entity_id", "status"),
        Index("ix_brand_scenarios_persona", "persona_object_id"),
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
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    persona_object_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brand_audience_personas.id", ondelete="SET NULL"),
        nullable=True,
    )
    scenario_key: Mapped[str] = mapped_column(String(120), nullable=False)
    scenario_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    decision_stage: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default="generated",
        nullable=False,
        index=True,
    )
    source_payload: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
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

    entity: Mapped["Entity"] = relationship("Entity", backref="brand_scenarios")
    session: Mapped["Session | None"] = relationship(
        "Session",
        backref="brand_scenarios",
    )
    persona: Mapped["BrandAudiencePersona | None"] = relationship(
        "BrandAudiencePersona",
        back_populates="scenarios",
    )


class BrandIntelligenceQuestion(Base):
    """A durable simulated question for one brand analysis world."""

    __tablename__ = "brand_intelligence_questions"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "session_id",
            "question_id",
            name="uq_brand_intel_question_entity_session_question",
        ),
        Index("ix_brand_intel_questions_entity_status", "entity_id", "status"),
        Index("ix_brand_intel_questions_category", "category"),
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
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    question_id: Mapped[str] = mapped_column(String(120), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    subcategory: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    user_intent: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    decision_stage: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default="generated",
        nullable=False,
        index=True,
    )
    source_payload: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
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

    entity: Mapped["Entity"] = relationship("Entity", backref="brand_questions")
    session: Mapped["Session | None"] = relationship(
        "Session",
        backref="brand_questions",
    )
    answers: Mapped[list["BrandPlatformAnswer"]] = relationship(
        "BrandPlatformAnswer",
        back_populates="question",
        lazy="selectin",
    )


class BrandPlatformAnswer(Base):
    """A captured answer from one AI platform for one simulated question."""

    __tablename__ = "brand_platform_answers"
    __table_args__ = (
        UniqueConstraint(
            "dedupe_key",
            name="uq_brand_platform_answers_dedupe_key",
        ),
        Index("ix_brand_platform_answers_entity_platform", "entity_id", "platform"),
        Index("ix_brand_platform_answers_question_id", "question_id"),
        Index("ix_brand_platform_answers_status", "status"),
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
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    question_object_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brand_intelligence_questions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    question_id: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    fetch_method: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="captured", nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    brand_mentioned: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    answer_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    answer_payload: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
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

    entity: Mapped["Entity"] = relationship("Entity", backref="brand_platform_answers")
    session: Mapped["Session | None"] = relationship(
        "Session",
        backref="brand_platform_answers",
    )
    question: Mapped["BrandIntelligenceQuestion | None"] = relationship(
        "BrandIntelligenceQuestion",
        back_populates="answers",
    )
    citations: Mapped[list["BrandCitationSource"]] = relationship(
        "BrandCitationSource",
        back_populates="answer",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    mentions: Mapped[list["BrandMention"]] = relationship(
        "BrandMention",
        back_populates="answer",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class BrandMention(Base):
    """A durable fact that a platform answer mentioned a brand."""

    __tablename__ = "brand_mentions"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "dedupe_key",
            name="uq_brand_mentions_entity_dedupe_key",
        ),
        Index("ix_brand_mentions_entity_role", "entity_id", "mention_role"),
        Index("ix_brand_mentions_answer_id", "answer_id"),
        Index("ix_brand_mentions_question_object_id", "question_object_id"),
        Index("ix_brand_mentions_sentiment", "sentiment"),
        Index(
            "ix_brand_mentions_target_object",
            "mentioned_object_type",
            "mentioned_object_id",
        ),
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
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    answer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brand_platform_answers.id", ondelete="CASCADE"),
        nullable=True,
    )
    question_object_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brand_intelligence_questions.id", ondelete="SET NULL"),
        nullable=True,
    )
    report_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brand_report_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    mentioned_brand_key: Mapped[str] = mapped_column(
        String(160), default="", nullable=False
    )
    mentioned_brand_name: Mapped[str] = mapped_column(
        String(255), default="", nullable=False
    )
    mentioned_object_type: Mapped[str] = mapped_column(
        String(120), default="", nullable=False
    )
    mentioned_object_id: Mapped[str] = mapped_column(
        String(255), default="", nullable=False
    )
    mention_role: Mapped[str] = mapped_column(
        String(40), default="target_brand", nullable=False
    )
    sentiment: Mapped[str] = mapped_column(
        String(32), default="neutral", nullable=False
    )
    quote: Mapped[str] = mapped_column(Text, default="", nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="observed", nullable=False)
    source_payload: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
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

    entity: Mapped["Entity"] = relationship("Entity", backref="brand_mentions")
    session: Mapped["Session | None"] = relationship(
        "Session",
        backref="brand_mentions",
    )
    answer: Mapped["BrandPlatformAnswer | None"] = relationship(
        "BrandPlatformAnswer",
        back_populates="mentions",
    )
    question: Mapped["BrandIntelligenceQuestion | None"] = relationship(
        "BrandIntelligenceQuestion",
        backref="brand_mentions",
    )
    report_version: Mapped["BrandReportVersion | None"] = relationship(
        "BrandReportVersion",
        backref="brand_mentions",
    )


class BrandCitationSource(Base):
    """A source cited by or attached to a platform answer."""

    __tablename__ = "brand_citation_sources"
    __table_args__ = (
        UniqueConstraint(
            "dedupe_key",
            name="uq_brand_citation_sources_dedupe_key",
        ),
        Index("ix_brand_citation_sources_entity_domain", "entity_id", "domain"),
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
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    answer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brand_platform_answers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    domain: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    source_title: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    snippet: Mapped[str] = mapped_column(Text, default="", nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    citation_payload: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
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

    entity: Mapped["Entity"] = relationship("Entity", backref="brand_citation_sources")
    session: Mapped["Session | None"] = relationship(
        "Session",
        backref="brand_citation_sources",
    )
    answer: Mapped["BrandPlatformAnswer"] = relationship(
        "BrandPlatformAnswer",
        back_populates="citations",
    )


class BrandEvidenceSet(Base):
    """A reusable set of evidence objects used by reports and follow-ups."""

    __tablename__ = "brand_evidence_sets"
    __table_args__ = (
        Index("ix_brand_evidence_sets_entity_type", "entity_id", "evidence_set_type"),
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
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    evidence_set_type: Mapped[str] = mapped_column(
        String(50),
        default="report",
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    definition: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    question_ids: Mapped[list | None] = mapped_column(JSONText, nullable=True)
    answer_ids: Mapped[list | None] = mapped_column(JSONText, nullable=True)
    citation_ids: Mapped[list | None] = mapped_column(JSONText, nullable=True)
    question_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    answer_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    citation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
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

    entity: Mapped["Entity"] = relationship("Entity", backref="brand_evidence_sets")
    session: Mapped["Session | None"] = relationship(
        "Session",
        backref="brand_evidence_sets",
    )


class BrandReportVersion(Base):
    """A versioned report bound to an evidence set."""

    __tablename__ = "brand_report_versions"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "report_id",
            "version",
            name="uq_brand_report_versions_entity_report_version",
        ),
        Index("ix_brand_report_versions_entity_kind", "entity_id", "report_kind"),
        Index(
            "ix_brand_report_versions_entity_publication",
            "entity_id",
            "publication_status",
        ),
        Index("ix_brand_report_versions_artifact_id", "artifact_id"),
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
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    evidence_set_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brand_evidence_sets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    report_id: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    report_kind: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    artifact_id: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    publication_status: Mapped[str] = mapped_column(
        String(40),
        default="draft",
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

    entity: Mapped["Entity"] = relationship("Entity", backref="brand_report_versions")
    session: Mapped["Session | None"] = relationship(
        "Session",
        backref="brand_report_versions",
    )
    evidence_set: Mapped["BrandEvidenceSet | None"] = relationship(
        "BrandEvidenceSet",
        backref="report_versions",
    )
    message: Mapped["Message | None"] = relationship(
        "Message",
        backref="brand_report_versions",
    )


class BrandIntelligenceFinding(Base):
    """A durable business judgment derived from brand evidence."""

    __tablename__ = "brand_intelligence_findings"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "session_id",
            "finding_key",
            name="uq_brand_intelligence_findings_session_key",
        ),
        Index("ix_brand_intel_findings_entity_status", "entity_id", "status"),
        Index("ix_brand_intel_findings_entity_type", "entity_id", "finding_type"),
        Index("ix_brand_intel_findings_report", "report_version_id"),
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
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    report_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brand_report_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    evidence_set_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brand_evidence_sets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    finding_key: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    finding_type: Mapped[str] = mapped_column(
        String(80),
        default="observation",
        nullable=False,
        index=True,
    )
    severity: Mapped[str] = mapped_column(
        String(40),
        default="medium",
        nullable=False,
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        default="observed",
        nullable=False,
        index=True,
    )
    evidence_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    supporting_question_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    supporting_answer_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    supporting_citation_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    suggested_action_type: Mapped[str] = mapped_column(
        String(120),
        default="",
        nullable=False,
    )
    suggested_action_payload: Mapped[dict | None] = mapped_column(
        JSONText,
        nullable=True,
    )
    source_payload: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
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

    entity: Mapped["Entity"] = relationship(
        "Entity",
        backref="brand_intelligence_findings",
    )
    session: Mapped["Session | None"] = relationship(
        "Session",
        backref="brand_intelligence_findings",
    )
    report_version: Mapped["BrandReportVersion | None"] = relationship(
        "BrandReportVersion",
        backref="intelligence_findings",
    )
    evidence_set: Mapped["BrandEvidenceSet | None"] = relationship(
        "BrandEvidenceSet",
        backref="intelligence_findings",
    )


class BrandMetricSnapshot(Base):
    """A durable metrics snapshot derived from a report or monitoring run."""

    __tablename__ = "brand_metric_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "snapshot_key",
            name="uq_brand_metric_snapshots_entity_key",
        ),
        Index("ix_brand_metric_snapshots_entity_kind", "entity_id", "metric_kind"),
        Index("ix_brand_metric_snapshots_report", "report_version_id"),
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
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    report_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brand_report_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    snapshot_key: Mapped[str] = mapped_column(String(120), nullable=False)
    metric_kind: Mapped[str] = mapped_column(
        String(80), default="report", nullable=False
    )
    bwvs_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    mention_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_questions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metric_payload: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
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

    entity: Mapped["Entity"] = relationship("Entity", backref="brand_metric_snapshots")
    session: Mapped["Session | None"] = relationship(
        "Session",
        backref="brand_metric_snapshots",
    )
    report_version: Mapped["BrandReportVersion | None"] = relationship(
        "BrandReportVersion",
        backref="metric_snapshots",
    )


class BrandActionRecord(Base):
    """Audit record for a controlled brand intelligence action."""

    __tablename__ = "brand_action_records"
    __table_args__ = (
        Index("ix_brand_action_records_entity_action", "entity_id", "action_type"),
        Index(
            "ix_brand_action_records_actor_surface",
            "actor_type",
            "origin_surface",
        ),
        Index("ix_brand_action_records_parent", "parent_action_record_id"),
        Index("ix_brand_action_records_status", "status"),
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
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    parent_action_record_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brand_action_records.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_type: Mapped[str] = mapped_column(
        String(32), default="system", nullable=False
    )
    origin_surface: Mapped[str | None] = mapped_column(String(80), nullable=True)
    origin_event_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    action_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="submitted", nullable=False)
    requires_confirmation: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    permission_scope: Mapped[str] = mapped_column(
        String(80), default="", nullable=False
    )
    input_payload: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    output_payload: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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

    entity: Mapped["Entity"] = relationship("Entity", backref="brand_action_records")
    parent_action_record: Mapped["BrandActionRecord | None"] = relationship(
        "BrandActionRecord",
        remote_side=[id],
    )
    session: Mapped["Session | None"] = relationship(
        "Session",
        backref="brand_action_records",
    )
    user: Mapped["User | None"] = relationship(
        "User",
        backref="brand_action_records",
    )


class BrandUserDecision(Base):
    """A user-visible decision or feedback item linked to an action record."""

    __tablename__ = "brand_user_decisions"
    __table_args__ = (
        UniqueConstraint(
            "action_record_id",
            name="uq_brand_user_decisions_action_record",
        ),
        Index("ix_brand_user_decisions_entity_status", "entity_id", "status"),
        Index("ix_brand_user_decisions_user_status", "user_id", "status"),
        Index(
            "ix_brand_user_decisions_target",
            "target_object_type",
            "target_object_id",
        ),
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
    action_record_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brand_action_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    decision_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    decision_key: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="submitted", nullable=False)
    origin_surface: Mapped[str | None] = mapped_column(String(80), nullable=True)
    origin_event_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    target_object_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    target_object_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    feedback_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    input_payload: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    output_payload: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(
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

    entity: Mapped["Entity"] = relationship("Entity", backref="brand_user_decisions")
    action_record: Mapped["BrandActionRecord | None"] = relationship(
        "BrandActionRecord",
        backref=backref("user_decision", uselist=False),
    )
    session: Mapped["Session | None"] = relationship(
        "Session",
        backref="brand_user_decisions",
    )
    user: Mapped["User | None"] = relationship(
        "User",
        backref="brand_user_decisions",
    )


class BrandObjectLink(Base):
    """Generic relationship row between brand intelligence objects."""

    __tablename__ = "brand_object_links"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "link_type",
            "from_object_type",
            "from_object_id",
            "to_object_type",
            "to_object_id",
            name="uq_brand_object_links_edge",
        ),
        Index(
            "ix_brand_object_links_from",
            "from_object_type",
            "from_object_id",
            "link_type",
        ),
        Index(
            "ix_brand_object_links_to",
            "to_object_type",
            "to_object_id",
            "link_type",
        ),
        Index("ix_brand_object_links_entity_link", "entity_id", "link_type"),
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
    link_type: Mapped[str] = mapped_column(String(120), nullable=False)
    from_object_type: Mapped[str] = mapped_column(String(120), nullable=False)
    from_object_id: Mapped[str] = mapped_column(String(255), nullable=False)
    to_object_type: Mapped[str] = mapped_column(String(120), nullable=False)
    to_object_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_action_record_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("brand_action_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    extra_metadata: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    entity: Mapped["Entity"] = relationship("Entity", backref="brand_object_links")
    source_action_record: Mapped["BrandActionRecord | None"] = relationship(
        "BrandActionRecord",
        backref="object_links",
    )
