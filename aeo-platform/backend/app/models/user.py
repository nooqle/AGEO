from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.entity import Entity
    from app.models.organization import Organization
    from app.models.session import Session


class UserStatus(str, PyEnum):
    PENDING_REVIEW = "pending_review"
    ACTIVE = "active"
    DISABLED = "disabled"
    REJECTED = "rejected"


class UserRole(str, PyEnum):
    INTERNAL_ADMIN = "internal_admin"
    CUSTOMER_USER = "customer_user"


def _enum_values(enum_cls: type[PyEnum]) -> list[str]:
    return [item.value for item in enum_cls]


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="userstatus", values_callable=_enum_values),
        default=UserStatus.PENDING_REVIEW,
        nullable=False,
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="userrole", values_callable=_enum_values),
        default=UserRole.CUSTOMER_USER,
        nullable=False,
    )
    job_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    sessions: Mapped[list["Session"]] = relationship(
        "Session",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    organization: Mapped["Organization | None"] = relationship(
        "Organization",
        back_populates="users",
        lazy="selectin",
    )
    owned_entities: Mapped[list["Entity"]] = relationship(
        "Entity",
        back_populates="owner",
        lazy="selectin",
        foreign_keys="Entity.owner_user_id",
    )

    @property
    def organization_name(self) -> str | None:
        if self.organization is None:
            return None
        return self.organization.legal_name
