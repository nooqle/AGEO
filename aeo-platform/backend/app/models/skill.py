"""Skill registry models for coarse-grained public skills."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.snapshot import JSONText

if TYPE_CHECKING:
    from app.models.user import User


class SkillExecutorKind(str, PyEnum):
    BUILTIN = "builtin"
    CONFIGURED_TEMPLATE = "configured_template"


class SkillCostClass(str, PyEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SkillLatencyClass(str, PyEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SkillConfirmationPolicy(str, PyEnum):
    NEVER = "never"
    OPTIONAL = "optional"
    REQUIRED = "required"


class SkillScopeKind(str, PyEnum):
    GLOBAL = "global"
    WORKSPACE = "workspace"
    ENTITY = "entity"


@dataclass(frozen=True)
class BuiltinSkillSpec:
    skill_key: str
    display_name: str
    description: str
    executor_kind: SkillExecutorKind
    executor_ref: str
    intent_signals: list[str]
    prerequisites: list[str]
    artifact_types: list[str]
    default_params: dict[str, Any]
    prompt_overlay: str | None
    cost_class: SkillCostClass
    latency_class: SkillLatencyClass
    confirmation_policy: SkillConfirmationPolicy
    enabled: bool = True
    version: int = 1


class SkillDefinition(Base):
    __tablename__ = "skill_definitions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    skill_key: Mapped[str] = mapped_column(
        String(120), unique=True, nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    executor_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    executor_ref: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    template_skill_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    intent_signals: Mapped[list[str]] = mapped_column(
        JSONText, default=list, nullable=False
    )
    prerequisites: Mapped[list[str]] = mapped_column(
        JSONText, default=list, nullable=False
    )
    artifact_types: Mapped[list[str]] = mapped_column(
        JSONText, default=list, nullable=False
    )
    default_params: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    prompt_overlay: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_class: Mapped[str] = mapped_column(
        String(16), default=SkillCostClass.MEDIUM.value, nullable=False
    )
    latency_class: Mapped[str] = mapped_column(
        String(16), default=SkillLatencyClass.MEDIUM.value, nullable=False
    )
    confirmation_policy: Mapped[str] = mapped_column(
        String(16),
        default=SkillConfirmationPolicy.OPTIONAL.value,
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_builtin: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
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

    created_by_user: Mapped["User | None"] = relationship("User")
    versions: Mapped[list["SkillVersion"]] = relationship(
        "SkillVersion",
        back_populates="skill",
        cascade="all, delete-orphan",
        order_by="desc(SkillVersion.version)",
    )
    assignments: Mapped[list["SkillAssignment"]] = relationship(
        "SkillAssignment",
        back_populates="skill",
        cascade="all, delete-orphan",
    )


class SkillVersion(Base):
    __tablename__ = "skill_versions"
    __table_args__ = (
        UniqueConstraint("skill_id", "version", name="uq_skill_versions_skill_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skill_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    config_payload: Mapped[dict] = mapped_column(JSONText, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    skill: Mapped["SkillDefinition"] = relationship(
        "SkillDefinition", back_populates="versions"
    )


class SkillAssignment(Base):
    __tablename__ = "skill_assignments"
    __table_args__ = (
        UniqueConstraint(
            "skill_id",
            "scope_kind",
            "scope_ref",
            name="uq_skill_assignments_scope",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skill_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scope_kind: Mapped[str] = mapped_column(
        String(16),
        default=SkillScopeKind.GLOBAL.value,
        nullable=False,
    )
    scope_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
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

    skill: Mapped["SkillDefinition"] = relationship(
        "SkillDefinition", back_populates="assignments"
    )
