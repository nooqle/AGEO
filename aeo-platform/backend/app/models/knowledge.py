"""Knowledge Workspace models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.snapshot import JSONText

if TYPE_CHECKING:
    pass


class KnowledgeRecord(Base):
    """Canonical evidence object stored for Knowledge Workspace."""

    __tablename__ = "knowledge_records"
    __table_args__ = (
        Index(
            "ix_knowledge_records_entity_occurred_at",
            "entity_id",
            "occurred_at",
        ),
        Index(
            "ix_knowledge_records_brand_occurred_at",
            "brand_name",
            "occurred_at",
        ),
        Index(
            "ix_knowledge_records_entity_source_occurred_at",
            "entity_id",
            "source_type",
            "occurred_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    entity_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    session_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    task_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    run_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )

    source_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    brand_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    question_id: Mapped[str | None] = mapped_column(
        String(120), nullable=True, index=True
    )
    question_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    competitor_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    search_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
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

    segments: Mapped[list["KnowledgeSegment"]] = relationship(
        "KnowledgeSegment",
        back_populates="record",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="KnowledgeSegment.segment_index.asc()",
    )

    def __repr__(self) -> str:
        return f"<KnowledgeRecord(id={self.id}, source_type={self.source_type}, title={self.title})>"


class KnowledgeSegment(Base):
    """Retrieval-oriented text segment for a knowledge record."""

    __tablename__ = "knowledge_segments"
    __table_args__ = (
        UniqueConstraint(
            "record_id", "segment_index", name="uq_knowledge_segment_order"
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    record_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("knowledge_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    search_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    extra_metadata: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    record: Mapped["KnowledgeRecord"] = relationship(
        "KnowledgeRecord",
        back_populates="segments",
    )

    def __repr__(self) -> str:
        return f"<KnowledgeSegment(id={self.id}, record_id={self.record_id}, idx={self.segment_index})>"
