from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class RegistrationApplicationStatus(str, PyEnum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


def _enum_values(enum_cls: type[PyEnum]) -> list[str]:
    return [item.value for item in enum_cls]


class RegistrationApplication(Base):
    __tablename__ = "registration_applications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    organization_name: Mapped[str] = mapped_column(String(255), nullable=False)
    job_title: Mapped[str] = mapped_column(String(255), nullable=False)
    applicant_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[RegistrationApplicationStatus] = mapped_column(
        Enum(
            RegistrationApplicationStatus,
            name="registrationapplicationstatus",
            values_callable=_enum_values,
        ),
        default=RegistrationApplicationStatus.PENDING_REVIEW,
        nullable=False,
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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

    reviewed_by: Mapped["User | None"] = relationship(
        "User",
        lazy="selectin",
        foreign_keys=[reviewed_by_user_id],
    )
    approved_user: Mapped["User | None"] = relationship(
        "User",
        lazy="selectin",
        foreign_keys=[approved_user_id],
    )
