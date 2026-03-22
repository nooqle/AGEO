from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class VerificationChannel(str, PyEnum):
    EMAIL = "email"
    PHONE = "phone"


class VerificationPurpose(str, PyEnum):
    REGISTRATION = "registration"
    LOGIN = "login"
    BIND_EMAIL = "bind_email"
    BIND_PHONE = "bind_phone"


def _enum_values(enum_cls: type[PyEnum]) -> list[str]:
    return [item.value for item in enum_cls]


class VerificationChallenge(Base):
    __tablename__ = "verification_challenges"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    channel: Mapped[VerificationChannel] = mapped_column(
        Enum(
            VerificationChannel,
            name="verificationchannel",
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    purpose: Mapped[VerificationPurpose] = mapped_column(
        Enum(
            VerificationPurpose,
            name="verificationpurpose",
            values_callable=_enum_values,
        ),
        nullable=False,
    )
    target: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
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
