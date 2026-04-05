"""Persistent control-plane models for AIO-backed runtime sessions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.snapshot import JSONText
from app.services.aio_runtime_contracts import (
    AioResumeGateResult,
    AioSessionState,
    AioTakeoverState,
)

class AioRuntimeSession(Base):
    """Persistent record for one workspace-scoped AIO runtime session."""

    __tablename__ = "aio_runtime_sessions"
    __table_args__ = (
        Index("ix_aio_runtime_sessions_workspace_id", "workspace_id"),
        Index("ix_aio_runtime_sessions_session_state", "session_state"),
        Index("ix_aio_runtime_sessions_session_id", "session_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    workspace_id: Mapped[str] = mapped_column(String(120), nullable=False)
    sandbox_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    aio_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    home_dir: Mapped[str] = mapped_column(String(255), nullable=False)
    data_root: Mapped[str] = mapped_column(String(255), nullable=False)
    browser_info_json: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    session_state: Mapped[AioSessionState] = mapped_column(
        Enum(
            AioSessionState,
            name="aioruntimesessionstate",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=AioSessionState.PROVISIONING,
        nullable=False,
    )
    holders_json: Mapped[list[str] | None] = mapped_column(JSONText, nullable=True)
    ref_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_takeover_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    automation_lock: Mapped[str | None] = mapped_column(String(255), nullable=True)
    human_takeover_lock: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_healthcheck_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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

    takeovers: Mapped[list["AioRuntimeTakeover"]] = relationship(
        "AioRuntimeTakeover",
        back_populates="session",
        cascade="all, delete-orphan",
        primaryjoin="AioRuntimeSession.session_id==foreign(AioRuntimeTakeover.session_id)",
    )
    platform_states: Mapped[list["AioPlatformRuntimeState"]] = relationship(
        "AioPlatformRuntimeState",
        back_populates="session",
        cascade="all, delete-orphan",
        primaryjoin="AioRuntimeSession.session_id==foreign(AioPlatformRuntimeState.session_id)",
    )


class AioRuntimeTakeover(Base):
    """Persistent record for one AIO human takeover flow."""

    __tablename__ = "aio_runtime_takeovers"
    __table_args__ = (
        Index("ix_aio_runtime_takeovers_takeover_id", "takeover_id", unique=True),
        Index("ix_aio_runtime_takeovers_session_id", "session_id"),
        Index("ix_aio_runtime_takeovers_takeover_state", "takeover_state"),
        Index("ix_aio_runtime_takeovers_request_id", "request_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    takeover_id: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    session_id: Mapped[str] = mapped_column(
        String(120),
        ForeignKey("aio_runtime_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[str] = mapped_column(String(120), nullable=False)
    user_id: Mapped[str] = mapped_column(String(120), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    takeover_state: Mapped[AioTakeoverState] = mapped_column(
        Enum(
            AioTakeoverState,
            name="aioruntimetakeoverstate",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=AioTakeoverState.REQUESTED,
        nullable=False,
    )
    frontend_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    action_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resume_gate_result: Mapped[AioResumeGateResult | None] = mapped_column(
        Enum(
            AioResumeGateResult,
            name="aioresumegateresult",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=True,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
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

    session: Mapped["AioRuntimeSession"] = relationship(
        "AioRuntimeSession",
        back_populates="takeovers",
        primaryjoin="foreign(AioRuntimeTakeover.session_id)==AioRuntimeSession.session_id",
    )


class AioPlatformRuntimeState(Base):
    """Persistent filesystem roots for one workspace/task/platform runtime slice."""

    __tablename__ = "aio_platform_runtime_states"
    __table_args__ = (
        Index(
            "uq_aio_platform_runtime_states_scope",
            "session_id",
            "task_id",
            "platform",
            unique=True,
        ),
        Index("ix_aio_platform_runtime_states_workspace_id", "workspace_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    session_id: Mapped[str] = mapped_column(
        String(120),
        ForeignKey("aio_runtime_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[str] = mapped_column(String(120), nullable=False)
    task_id: Mapped[str] = mapped_column(String(120), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    profile_root: Mapped[str] = mapped_column(String(255), nullable=False)
    run_root: Mapped[str] = mapped_column(String(255), nullable=False)
    cookies_path: Mapped[str] = mapped_column(String(255), nullable=False)
    state_path: Mapped[str] = mapped_column(String(255), nullable=False)
    session_meta_path: Mapped[str] = mapped_column(String(255), nullable=False)
    checkpoint_root: Mapped[str] = mapped_column(String(255), nullable=False)
    snapshot_root: Mapped[str] = mapped_column(String(255), nullable=False)
    download_root: Mapped[str] = mapped_column(String(255), nullable=False)
    extraction_path: Mapped[str] = mapped_column(String(255), nullable=False)
    last_state_save_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_state_load_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    session: Mapped["AioRuntimeSession"] = relationship(
        "AioRuntimeSession",
        back_populates="platform_states",
        primaryjoin="foreign(AioPlatformRuntimeState.session_id)==AioRuntimeSession.session_id",
    )
