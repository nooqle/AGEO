"""Alert lifecycle management and generation service."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.monitoring_alert import (
    AlertSeverity,
    AlertStatus,
    MonitoringAlert,
)

logger = logging.getLogger(__name__)

# Metric display names for alert messages
METRIC_DISPLAY_NAMES = {
    "bwvs_index": "BWVS 指数",
    "mention_rate": "提及率",
    "sentiment_score": "情感得分",
    "coverage_score": "覆盖度",
    "citation_score": "引用得分",
}


class AlertService:
    """Manages MonitoringAlert creation, delivery, and lifecycle."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # =========================================================================
    # Alert Generation
    # =========================================================================

    async def generate_alerts_for_snapshot(
        self,
        entity_id: UUID,
        user_id: UUID,
        schedule_id: UUID,
        snapshot_id: UUID,
        threshold: float = 10.0,
    ) -> list[MonitoringAlert]:
        """Generate alerts by comparing the new snapshot with the previous one.

        Called after each scheduled analysis completes.
        """
        from app.services.trend_engine import TrendEngine

        trend_engine = TrendEngine(self.db)
        changes = await trend_engine.detect_significant_changes(
            entity_id=entity_id,
            threshold_absolute=threshold,
            threshold_percentage=20.0,
        )

        if not changes:
            return []

        # Get entity name for alert messages
        entity_name = await self._get_entity_name(entity_id)

        alerts: list[MonitoringAlert] = []
        for change in changes:
            severity = self.classify_severity(
                abs(change["change_absolute"]),
                abs(change["change_percentage"]),
            )
            title = self._generate_alert_title(
                entity_name, change["metric"], change
            )
            summary = self.generate_alert_summary(
                entity_name, change["metric"], change
            )

            alert = MonitoringAlert(
                user_id=user_id,
                entity_id=entity_id,
                schedule_id=schedule_id,
                snapshot_id=snapshot_id,
                severity=severity,
                status=AlertStatus.UNREAD,
                title=title,
                summary=summary,
                metric_name=change["metric"],
                previous_value=change["previous"],
                current_value=change["current"],
                change_absolute=change["change_absolute"],
                change_percentage=change["change_percentage"],
                details=change,
            )
            self.db.add(alert)
            alerts.append(alert)

        if alerts:
            await self.db.commit()
            for alert in alerts:
                await self.db.refresh(alert)
            logger.info(
                "[AlertService] Generated %d alerts for entity %s (snapshot=%s)",
                len(alerts),
                entity_id,
                snapshot_id,
            )

        return alerts

    # =========================================================================
    # Query
    # =========================================================================

    async def get_alerts(
        self,
        user_id: UUID,
        *,
        entity_id: UUID | None = None,
        status: AlertStatus | None = None,
        severity: AlertSeverity | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[MonitoringAlert], int]:
        """List alerts for a user with filtering."""
        conditions = [MonitoringAlert.user_id == user_id]
        if entity_id is not None:
            conditions.append(MonitoringAlert.entity_id == entity_id)
        if status is not None:
            conditions.append(MonitoringAlert.status == status)
        if severity is not None:
            conditions.append(MonitoringAlert.severity == severity)

        count_stmt = (
            select(func.count())
            .select_from(MonitoringAlert)
            .where(*conditions)
        )
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0

        query = (
            select(MonitoringAlert)
            .options(selectinload(MonitoringAlert.entity))
            .where(*conditions)
            .order_by(MonitoringAlert.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(query)
        alerts = list(result.scalars().all())
        return alerts, total

    async def get_alert(self, alert_id: UUID) -> MonitoringAlert | None:
        """Get a single alert by ID (eager-loads entity for entity_name)."""
        stmt = (
            select(MonitoringAlert)
            .options(selectinload(MonitoringAlert.entity))
            .where(MonitoringAlert.id == alert_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_unread_count(self, user_id: UUID) -> int:
        """Get count of unread alerts for notification badge."""
        stmt = (
            select(func.count())
            .select_from(MonitoringAlert)
            .where(
                MonitoringAlert.user_id == user_id,
                MonitoringAlert.status == AlertStatus.UNREAD,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def mark_read(self, alert_id: UUID) -> MonitoringAlert | None:
        """Mark an alert as read."""
        alert = await self.get_alert(alert_id)
        if alert is None:
            return None
        alert.status = AlertStatus.READ
        alert.read_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(alert)
        return alert

    async def mark_all_read(self, user_id: UUID) -> int:
        """Mark all unread alerts as read. Returns count updated."""
        now = datetime.now(timezone.utc)
        stmt = (
            update(MonitoringAlert)
            .where(
                MonitoringAlert.user_id == user_id,
                MonitoringAlert.status == AlertStatus.UNREAD,
            )
            .values(
                status=AlertStatus.READ,
                read_at=now,
            )
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount

    async def dismiss_alert(self, alert_id: UUID) -> MonitoringAlert | None:
        """Dismiss an alert."""
        alert = await self.get_alert(alert_id)
        if alert is None:
            return None
        alert.status = AlertStatus.DISMISSED
        await self.db.commit()
        await self.db.refresh(alert)
        return alert

    # =========================================================================
    # Severity Classification
    # =========================================================================

    @staticmethod
    def classify_severity(
        abs_change: float,
        pct_change: float,
    ) -> AlertSeverity:
        """Classify alert severity based on change magnitude.

        Uses the greater of absolute and percentage thresholds.
        """
        if abs_change > 25 or pct_change > 50:
            return AlertSeverity.CRITICAL
        elif abs_change > 15 or pct_change > 25:
            return AlertSeverity.HIGH
        elif abs_change > 5 or pct_change > 10:
            return AlertSeverity.MEDIUM
        else:
            return AlertSeverity.LOW

    # =========================================================================
    # Message Generation
    # =========================================================================

    @staticmethod
    def _generate_alert_title(
        entity_name: str,
        metric_name: str,
        change: dict[str, Any],
    ) -> str:
        """Generate a concise alert title."""
        display_name = METRIC_DISPLAY_NAMES.get(metric_name, metric_name)
        direction = "上升" if change["direction"] == "up" else "下降"
        abs_val = abs(change["change_absolute"])
        return f"{entity_name} 的{display_name}{direction}了 {abs_val:.1f} 分"

    @staticmethod
    def generate_alert_summary(
        entity_name: str,
        metric_name: str,
        change: dict[str, Any],
    ) -> str:
        """Generate a human-readable alert summary."""
        display_name = METRIC_DISPLAY_NAMES.get(metric_name, metric_name)
        direction_cn = "上升" if change["direction"] == "up" else "下降"
        prev = change["previous"]
        cur = change["current"]
        abs_change = change["change_absolute"]
        pct_change = change["change_percentage"]

        summary = (
            f"{entity_name} 的{display_name}从 {prev:.1f} {direction_cn}至 {cur:.1f}"
            f"（变化 {abs_change:+.1f} 分，{pct_change:+.1f}%）。"
        )

        severity = change.get("severity", "medium")
        if severity in ("critical", "high"):
            summary += "这是一个显著的变化，建议进行详细分析了解原因。"
        elif severity == "medium":
            summary += "建议关注后续趋势变化。"

        return summary

    # =========================================================================
    # Helpers
    # =========================================================================

    async def _get_entity_name(self, entity_id: UUID) -> str:
        """Get entity name for alert messages."""
        from app.models.entity import Entity

        entity = await self.db.get(Entity, entity_id)
        return entity.name if entity else "未知品牌"
