"""Monitoring Alert model -- records detected metric anomalies."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.snapshot import JSONText

if TYPE_CHECKING:
    from app.models.entity import Entity
    from app.models.monitoring_schedule import MonitoringSchedule
    from app.models.snapshot import AnalysisSnapshot
    from app.models.user import User


class AlertSeverity(str, PyEnum):
    """Alert severity level."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(str, PyEnum):
    """Alert lifecycle status."""

    UNREAD = "unread"
    READ = "read"
    DISMISSED = "dismissed"
    ACTIONED = "actioned"


class MonitoringAlert(Base):
    """Records a detected metric anomaly from continuous monitoring.

    Created by the AlertService when a scheduled analysis detects
    a significant change. Displayed in the notification center.
    """

    __tablename__ = "monitoring_alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("monitoring_schedules.id", ondelete="SET NULL"),
        nullable=True,
    )
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Alert content
    severity: Mapped[AlertSeverity] = mapped_column(
        Enum(AlertSeverity),
        nullable=False,
        index=True,
    )
    status: Mapped[AlertStatus] = mapped_column(
        Enum(AlertStatus),
        default=AlertStatus.UNREAD,
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    # Metric details
    metric_name: Mapped[str] = mapped_column(String(50), nullable=False)
    previous_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_absolute: Mapped[float] = mapped_column(Float, nullable=False)
    change_percentage: Mapped[float] = mapped_column(Float, nullable=False)

    # Extended details (JSON)
    details: Mapped[dict | None] = mapped_column(JSONText, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User", backref="monitoring_alerts")
    entity: Mapped["Entity"] = relationship(
        "Entity", backref="monitoring_alerts"
    )
    schedule: Mapped["MonitoringSchedule | None"] = relationship(
        "MonitoringSchedule", backref="alerts"
    )
    snapshot: Mapped["AnalysisSnapshot | None"] = relationship(
        "AnalysisSnapshot", backref="alerts"
    )

    def __repr__(self) -> str:
        return (
            f"<MonitoringAlert(id={self.id}, entity={self.entity_id}, "
            f"metric={self.metric_name}, severity={self.severity})>"
        )
