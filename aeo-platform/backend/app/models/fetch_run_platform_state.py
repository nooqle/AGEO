"""Authoritative per-platform fetch state for A4/A5 projection."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.snapshot import JSONText

if TYPE_CHECKING:
    from app.models.entity import Entity
    from app.models.session import Session
    from app.models.task import AnalysisTask
    from app.models.task_run import TaskRun
    from app.models.user import User


class FetchRunPlatformState(Base):
    """Durable platform-scoped execution state for a task run."""

    __tablename__ = "fetch_run_platform_states"
    __table_args__ = (
        Index(
            "uq_fetch_run_platform_states_run_platform",
            "task_run_id",
            "platform",
            unique=True,
        ),
        Index("ix_fetch_run_platform_states_task_id", "task_id"),
        Index("ix_fetch_run_platform_states_session_id", "session_id"),
        Index("ix_fetch_run_platform_states_status", "status"),
        Index("ix_fetch_run_platform_states_platform", "platform"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    task_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("task_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=True,
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    auth_state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="unknown",
    )
    latest_packet: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    latest_takeover_request_id: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )
    latest_blocking_fingerprint: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )
    artifact_write_status: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    error_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    timing_json: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
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

    task_run: Mapped["TaskRun"] = relationship("TaskRun", backref="fetch_platform_states")
    task: Mapped["AnalysisTask"] = relationship(
        "AnalysisTask",
        backref="fetch_platform_states",
    )
    session: Mapped["Session | None"] = relationship(
        "Session",
        backref="fetch_platform_states",
    )
    entity: Mapped["Entity | None"] = relationship(
        "Entity",
        backref="fetch_platform_states",
    )
    user: Mapped["User"] = relationship("User", backref="fetch_platform_states")

    def __repr__(self) -> str:
        return (
            f"<FetchRunPlatformState(task_run_id={self.task_run_id}, "
            f"platform={self.platform}, status={self.status})>"
        )
