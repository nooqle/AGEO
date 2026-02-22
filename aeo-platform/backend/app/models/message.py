"""Message model."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.session import Session


class MessageRole(str, PyEnum):
    """Message role enum."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class MessageType(str, PyEnum):
    """Message type enum."""

    TEXT = "text"
    THINKING = "thinking"
    TPAOR = "tpaor"  # Task-Plan-Action-Observation-Result
    OUTPUT = "output"
    ERROR = "error"


class Message(Base):
    """Message model for storing conversation messages."""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Message content
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole), nullable=False)
    type: Mapped[MessageType] = mapped_column(
        Enum(MessageType),
        default=MessageType.TEXT,
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # For TPAOR messages
    task: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    action: Mapped[str | None] = mapped_column(Text, nullable=True)
    observation: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)

    # For output messages
    output_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    output_data: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Metadata
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    extra_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
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

    # Relationships
    session: Mapped["Session"] = relationship("Session", back_populates="messages")
    parent: Mapped["Message | None"] = relationship(
        "Message",
        remote_side="Message.id",
        back_populates="children",
    )
    children: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="parent",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Message(id={self.id}, role={self.role}, type={self.type})>"
