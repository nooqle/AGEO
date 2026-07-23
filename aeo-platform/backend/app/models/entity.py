"""Entity model for brand entities."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.session import Session
    from app.models.user import User


class EntityStatus(str, PyEnum):
    """Entity status enum."""

    ACTIVE = "active"
    PENDING = "pending"
    INACTIVE = "inactive"


class EntityVisibilityScope(str, PyEnum):
    PERSONAL = "personal"
    ORGANIZATION = "organization"


def _enum_values(enum_cls: type[PyEnum]) -> list[str]:
    return [item.value for item in enum_cls]


class Entity(Base):
    """Brand entity model."""

    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    aliases: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON array stored as text
    domain: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    industry: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[EntityStatus] = mapped_column(
        Enum(EntityStatus),
        default=EntityStatus.PENDING,
        nullable=False,
    )
    visibility_scope: Mapped[EntityVisibilityScope] = mapped_column(
        Enum(
            EntityVisibilityScope,
            name="entityvisibilityscope",
            values_callable=_enum_values,
        ),
        default=EntityVisibilityScope.PERSONAL,
        nullable=False,
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    last_analyzed: Mapped[datetime | None] = mapped_column(
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

    # Relationships
    sessions: Mapped[list["Session"]] = relationship(
        "Session", back_populates="entity", lazy="select"
    )
    owner: Mapped["User | None"] = relationship(
        "User",
        back_populates="owned_entities",
        lazy="select",
        foreign_keys=[owner_user_id],
    )
    organization: Mapped["Organization | None"] = relationship(
        "Organization",
        back_populates="entities",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Entity(id={self.id}, name={self.name})>"
