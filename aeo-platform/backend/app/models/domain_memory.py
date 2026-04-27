"""Domain identity and brand relation memory models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.snapshot import JSONText


class DomainIdentityRecord(Base):
    """Stable semantic identity for a canonical domain."""

    __tablename__ = "domain_identity_records"
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    canonical_domain: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="other",
        index=True,
    )
    site_category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="unresolved",
        index=True,
    )
    resolved_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    evidence_payload: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class BrandDomainRelation(Base):
    """Relation between a brand/entity and a canonical domain."""

    __tablename__ = "brand_domain_relations"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "brand_name",
            "canonical_domain",
            name="uq_brand_domain_relation_scope",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    brand_name: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    relation_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="unknown",
        index=True,
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="unresolved",
        index=True,
    )
    resolved_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    evidence_payload: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
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
