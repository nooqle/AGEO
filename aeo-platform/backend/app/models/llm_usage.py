"""LLM usage record model for token/cost observability."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.snapshot import JSONText

if TYPE_CHECKING:
    from app.models.session import Session
    from app.models.task import AnalysisTask


class LLMUsageRecord(Base):
    """Stores one provider-reported token usage event."""

    __tablename__ = "llm_usage_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    skill_key: Mapped[str | None] = mapped_column(
        String(120), nullable=True, index=True
    )
    step: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    step_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    raw_session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cached_prompt_tokens: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    billable_prompt_tokens: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    estimated_cost_cache_aware: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )
    currency: Mapped[str] = mapped_column(String(10), default="CNY", nullable=False)

    extra_metadata: Mapped[dict | None] = mapped_column(JSONText, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    task: Mapped["AnalysisTask | None"] = relationship(
        "AnalysisTask",
        back_populates="llm_usage_records",
    )
    session: Mapped["Session | None"] = relationship(
        "Session",
        backref="llm_usage_records",
    )

    def __repr__(self) -> str:
        return (
            f"<LLMUsageRecord(id={self.id}, provider={self.provider}, "
            f"model={self.model_name}, total_tokens={self.total_tokens}, "
            f"latency_ms={self.latency_ms})>"
        )
