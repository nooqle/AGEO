"""Trend analysis engine for monitoring data.

Reads AnalysisSnapshot time series (independent columns only) and computes:
- Period-over-period deltas
- Moving averages (for noise reduction)
- Significant change detection
- Trend direction classification
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.snapshot import AnalysisSnapshot, SnapshotStatus

logger = logging.getLogger(__name__)

# Core metrics stored as independent columns on AnalysisSnapshot
CORE_METRICS = [
    "bwvs_index",
    "mention_rate",
    "sentiment_score",
    "coverage_score",
    "citation_score",
]


class TrendDirection(str, Enum):
    """Overall trend direction for a metric."""

    IMPROVING = "improving"
    DECLINING = "declining"
    STABLE = "stable"
    VOLATILE = "volatile"


@dataclass
class MetricDelta:
    """Change between two consecutive data points."""

    current_value: float | None
    previous_value: float | None
    absolute_change: float
    percentage_change: float
    is_significant: bool
    direction: str  # "up" | "down" | "stable"


@dataclass
class TrendSummary:
    """Summary of a metric's trend over a time range."""

    metric_name: str
    current_value: float | None
    period_delta: MetricDelta | None
    trend_direction: TrendDirection
    data_points: int
    time_range_days: int
    moving_average: float | None
    min_value: float | None
    max_value: float | None


class TrendEngine:
    """Analyzes metric trends from Snapshot time series.

    Data source: Reads from AnalysisSnapshot independent columns.
    Both manually-triggered and scheduled Snapshots are used.
    """

    MIN_POINTS_FOR_TREND = 3
    MIN_POINTS_FOR_DELTA = 2

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _get_snapshots(
        self, entity_id: UUID, limit: int = 100
    ) -> list[AnalysisSnapshot]:
        """Fetch snapshots ordered by created_at ASC (oldest first)."""
        if isinstance(entity_id, str):
            entity_id = UUID(entity_id)

        stmt = (
            select(AnalysisSnapshot)
            .where(
                AnalysisSnapshot.entity_id == entity_id,
                AnalysisSnapshot.status.in_([
                    SnapshotStatus.COMPLETED,
                    SnapshotStatus.PARTIAL,
                ]),
            )
            .order_by(AnalysisSnapshot.created_at.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_entity_trend_summary(
        self,
        entity_id: UUID,
        metric_names: list[str] | None = None,
    ) -> dict[str, TrendSummary]:
        """Get trend summary for an entity across core metrics.

        Behavior by data point count:
        - 0 points: TrendSummary with all None values
        - 1 point: current_value only, direction=STABLE, no delta
        - 2 points: delta, direction=STABLE (insufficient for trend)
        - 3+ points: Full trend analysis with direction classification
        """
        metrics = metric_names or CORE_METRICS
        snapshots = await self._get_snapshots(entity_id)
        summaries: dict[str, TrendSummary] = {}

        for metric in metrics:
            values = [
                getattr(snap, metric)
                for snap in snapshots
                if getattr(snap, metric, None) is not None
            ]
            n = len(values)

            # Calculate time range
            time_range_days = 0
            if len(snapshots) >= 2:
                first_dt = snapshots[0].created_at
                last_dt = snapshots[-1].created_at
                if first_dt and last_dt:
                    time_range_days = (last_dt - first_dt).days

            current_value = values[-1] if values else None
            period_delta = None
            trend_direction = TrendDirection.STABLE
            moving_avg = None
            min_val = min(values) if values else None
            max_val = max(values) if values else None

            if n >= self.MIN_POINTS_FOR_DELTA:
                period_delta = self._compute_delta(
                    values[-1], values[-2]
                )

            if n >= self.MIN_POINTS_FOR_TREND:
                trend_direction = self.classify_trend_direction(values)
                moving_avg = self.calculate_moving_average(values)

            summaries[metric] = TrendSummary(
                metric_name=metric,
                current_value=current_value,
                period_delta=period_delta,
                trend_direction=trend_direction,
                data_points=n,
                time_range_days=time_range_days,
                moving_average=moving_avg,
                min_value=min_val,
                max_value=max_val,
            )

        return summaries

    async def get_period_deltas(
        self,
        entity_id: UUID,
    ) -> dict[str, MetricDelta]:
        """Get period-over-period deltas (latest vs. previous snapshot).

        Used by Dashboard KPI cards for "+3.2" or "-1.5" indicators.
        Requires at least 2 snapshots.
        """
        snapshots = await self._get_snapshots(entity_id)
        if len(snapshots) < 2:
            return {}

        latest = snapshots[-1]
        previous = snapshots[-2]
        deltas: dict[str, MetricDelta] = {}

        for metric in CORE_METRICS:
            cur = getattr(latest, metric, None)
            prev = getattr(previous, metric, None)
            if cur is not None and prev is not None:
                deltas[metric] = self._compute_delta(cur, prev)

        return deltas

    async def get_trend_data_points(
        self,
        entity_id: UUID,
        metric_name: str = "bwvs_index",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get time series data points for chart rendering."""
        snapshots = await self._get_snapshots(entity_id, limit=limit)

        data_points: list[dict[str, Any]] = []
        prev_value: float | None = None

        for snap in snapshots:
            value = getattr(snap, metric_name, None)
            is_significant = False

            if value is not None and prev_value is not None:
                abs_change = abs(value - prev_value)
                # Significant if > 10 absolute or > 20% relative
                pct_change = (
                    abs(abs_change / prev_value * 100) if prev_value != 0 else 0
                )
                is_significant = abs_change > 10.0 or pct_change > 20.0

            data_points.append({
                "date": (
                    snap.created_at.strftime("%Y-%m-%d")
                    if snap.created_at
                    else None
                ),
                "value": round(value, 4) if value is not None else None,
                "snapshot_id": str(snap.id),
                "triggered_by": snap.triggered_by or "manual",
                "is_significant": is_significant,
            })
            prev_value = value

        return data_points

    async def detect_significant_changes(
        self,
        entity_id: UUID,
        threshold_absolute: float = 10.0,
        threshold_percentage: float = 20.0,
    ) -> list[dict[str, Any]]:
        """Detect significant metric changes between latest two snapshots.

        A change is "significant" if it exceeds EITHER threshold.
        """
        snapshots = await self._get_snapshots(entity_id)
        if len(snapshots) < 2:
            return []

        latest = snapshots[-1]
        previous = snapshots[-2]
        changes: list[dict[str, Any]] = []

        for metric in CORE_METRICS:
            cur = getattr(latest, metric, None)
            prev = getattr(previous, metric, None)
            if cur is None or prev is None:
                continue

            abs_change = cur - prev
            pct_change = (abs_change / prev * 100) if prev != 0 else 0

            if (
                abs(abs_change) >= threshold_absolute
                or abs(pct_change) >= threshold_percentage
            ):
                direction = "up" if abs_change > 0 else "down"
                severity = self._classify_change_severity(
                    abs(abs_change), abs(pct_change)
                )
                changes.append({
                    "metric": metric,
                    "current": cur,
                    "previous": prev,
                    "change_absolute": round(abs_change, 2),
                    "change_percentage": round(pct_change, 1),
                    "direction": direction,
                    "severity": severity,
                })

        return changes

    # =========================================================================
    # Static Analysis Methods
    # =========================================================================

    @staticmethod
    def classify_trend_direction(values: list[float]) -> TrendDirection:
        """Classify overall trend direction from a series of values.

        Uses simple linear regression slope and variance analysis.
        Requires at least 3 values.
        """
        n = len(values)
        if n < 3:
            return TrendDirection.STABLE

        # Simple linear regression: slope = sum((x-xbar)(y-ybar)) / sum((x-xbar)^2)
        x_mean = (n - 1) / 2.0
        y_mean = sum(values) / n

        numerator = sum(
            (i - x_mean) * (v - y_mean) for i, v in enumerate(values)
        )
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return TrendDirection.STABLE

        slope = numerator / denominator

        # Normalize slope relative to mean value
        if y_mean != 0:
            normalized_slope = slope / abs(y_mean) * 100
        else:
            normalized_slope = slope

        # Check for volatility: coefficient of variation
        variance = sum((v - y_mean) ** 2 for v in values) / n
        std_dev = variance ** 0.5
        cv = (std_dev / abs(y_mean) * 100) if y_mean != 0 else 0

        # Thresholds
        SLOPE_THRESHOLD = 2.0  # 2% normalized slope
        VOLATILITY_THRESHOLD = 30.0  # 30% coefficient of variation

        if cv > VOLATILITY_THRESHOLD:
            return TrendDirection.VOLATILE
        elif normalized_slope > SLOPE_THRESHOLD:
            return TrendDirection.IMPROVING
        elif normalized_slope < -SLOPE_THRESHOLD:
            return TrendDirection.DECLINING
        else:
            return TrendDirection.STABLE

    @staticmethod
    def calculate_moving_average(
        values: list[float],
        window_size: int = 3,
    ) -> float | None:
        """Calculate moving average over the last N data points.

        Returns None if fewer than window_size data points available.
        """
        if len(values) < window_size:
            return None
        window = values[-window_size:]
        return round(sum(window) / window_size, 4)

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    @staticmethod
    def _compute_delta(
        current: float,
        previous: float,
        significance_threshold: float = 5.0,
    ) -> MetricDelta:
        """Compute delta between two values."""
        abs_change = current - previous
        pct_change = (abs_change / previous * 100) if previous != 0 else 0
        direction = "up" if abs_change > 0 else "down" if abs_change < 0 else "stable"
        is_significant = (
            abs(abs_change) >= significance_threshold
            or abs(pct_change) >= 15.0
        )
        return MetricDelta(
            current_value=current,
            previous_value=previous,
            absolute_change=round(abs_change, 4),
            percentage_change=round(pct_change, 2),
            is_significant=is_significant,
            direction=direction,
        )

    @staticmethod
    def _classify_change_severity(
        abs_change: float, pct_change: float
    ) -> str:
        """Classify change severity for alert generation."""
        if abs_change > 25 or pct_change > 50:
            return "critical"
        elif abs_change > 15 or pct_change > 25:
            return "high"
        elif abs_change > 5 or pct_change > 10:
            return "medium"
        else:
            return "low"
