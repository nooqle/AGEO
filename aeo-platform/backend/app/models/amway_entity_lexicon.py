"""Amway entity lexicon editable override models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.snapshot import JSONText

if TYPE_CHECKING:
    from app.models.entity import Entity
    from app.models.organization import Organization
    from app.models.user import User


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AmwayEntityLexiconOverride(Base):
    """User-maintained overlay for the bundled Amway entity ontology."""

    __tablename__ = "amway_entity_lexicon_overrides"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "lexicon_entity_id",
            name="uq_amway_entity_lexicon_override_entity_entry",
        ),
        Index(
            "ix_amway_entity_lexicon_override_entity_deleted", "entity_id", "is_deleted"
        ),
        Index("ix_amway_entity_lexicon_override_type", "entity_type"),
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
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    lexicon_entity_id: Mapped[str] = mapped_column(String(120), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(160), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aliases: Mapped[list | None] = mapped_column(JSONText, nullable=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    related_terms: Mapped[list | None] = mapped_column(JSONText, nullable=True)
    semantic_definition: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    graph_policy: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    source_policy: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    review_status: Mapped[str] = mapped_column(
        String(32), default="approved", nullable=False
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
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

    entity: Mapped["Entity"] = relationship("Entity", backref="amway_lexicon_overrides")
    organization: Mapped["Organization | None"] = relationship(
        "Organization",
        backref="amway_lexicon_overrides",
    )
    created_by_user: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[created_by_user_id],
    )
    updated_by_user: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[updated_by_user_id],
    )
