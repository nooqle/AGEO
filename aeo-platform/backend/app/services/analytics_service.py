"""Analytics service for Dashboard data aggregation.

Queries the database for analysis results and aggregates them into
dashboard-friendly formats (KPI, trends, platform breakdowns, etc.).

Data sources:
- Messages table: output_data JSON field from A5 OUTPUT messages
- LangGraph state: metrics, report, fetch_results, competitors (via checkpoint)
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.models.message import Message, MessageType, MessageRole
from app.models.monitoring_plan import (
    MonitoringEvidenceRecord,
    MonitoringPlan,
    MonitoringRun,
    MonitoringRunStatus,
    MonitoringQuestionSet,
)
from app.models.monitoring_schedule import MonitoringSchedule, ScheduleStatus
from app.models.snapshot import AnalysisSnapshot, SnapshotStatus
from app.models.session import Session
from app.models.user import User
from app.core.utils import extract_domain
from app.services.access_scope_service import AccessScopeService
from app.services.monitoring_plan_service import (
    ENDPOINT_REGISTRY,
    MonitoringPlanService,
)
from app.workflow.a5.diagnosis import extract_geo_report_diagnosis

logger = logging.getLogger(__name__)

# AEO metric thresholds — configurable benchmarks for status evaluation
AEO_THRESHOLDS = {
    "bwvs_index": {"benchmark": 50.0, "good": 50.0, "warning": 30.0},
    "mention_rate": {"benchmark": 0.30, "good": 0.30, "warning": 0.15},
    "total_questions": {"benchmark": 50, "good": 50, "warning": 20},
    "total_mentions": {"benchmark": 15, "good": 15, "warning": 5},
}

SOURCE_TYPE_LABELS = {
    "official": "官网 / 官方文档",
    "authority_media": "官媒 / 权威机构",
    "vertical_media": "行业媒体",
    "community": "社区 / 论坛 / 问答",
    "video_or_content": "视频 / 内容平台",
    "other": "其他",
}

REPORT_KIND_LABELS = {
    "panorama": "品牌全景分析报告",
    "scenario": "用户场景分析报告",
}

QUESTION_SCOPE_LABELS = {
    "brand_direct": "品牌直问",
    "comparison": "横向比较",
    "how_to_choose": "选型决策",
    "trend": "趋势判断",
    "risk": "风险顾虑",
    "risk_or_problem": "风险顾虑",
    "purchase": "购买决策",
    "value": "价值评估",
}

EMPTY_SCOPE_LABELS = {"其他", "--", "-", "未知", "other", "unknown"}

DASHBOARD_MONITOR_MODE_ALIASES = {
    "panorama": "panorama",
    "panorama_monitoring": "panorama",
    "baseline": "panorama",
    "scenario": "scenario",
    "scenario_monitoring": "scenario",
    "persona": "scenario",
}

PLATFORM_LABELS = {
    "deepseek": "DeepSeek",
    "kimi": "Kimi",
    "doubao": "豆包",
    "yuanbao": "元宝",
    "hunyuan": "元宝",
}

DASHBOARD_REPORT_DEFAULT_LIMIT = 20
DASHBOARD_REPORT_MONITOR_MODE_SCAN_LIMIT = 200
DASHBOARD_DEFAULT_DATE_RANGE_DAYS = 30

DASHBOARD_TREND_METRIC_ALIASES = {
    "bwvs": "bwvs_index",
    "bwvs_index": "bwvs_index",
    "brand_visibility": "bwvs_index",
    "mention": "mention_rate",
    "mention_rate": "mention_rate",
    "sentiment": "sentiment_score",
    "sentiment_score": "sentiment_score",
    "coverage": "coverage_score",
    "coverage_score": "coverage_score",
    "citation": "content_citation_rate",
    "citation_score": "content_citation_rate",
    "content_citation_rate": "content_citation_rate",
    "official_conversion_rate": "official_conversion_rate",
}

DASHBOARD_TREND_METRIC_LABELS = {
    "bwvs_index": "品牌可见度",
    "mention_rate": "提及率",
    "sentiment_score": "情感倾向",
    "coverage_score": "平台覆盖",
    "content_citation_rate": "内容引用率",
    "official_conversion_rate": "官网转化率",
}

NEGATIVE_TOPIC_LABELS = {
    "price": "价格与成本",
    "deployment": "维护与使用复杂度",
    "service": "服务与便利性",
    "ecosystem": "兼容与生态",
    "case": "案例与验证",
    "usability": "使用门槛",
    "credibility": "信息可信度",
    "other": "其他",
}

ANSWER_STATE_LABELS = {
    "no_brand": "未提及品牌",
    "competitor_only": "仅提竞品",
    "monitor_only": "仅提本品牌",
    "monitor_plus_others": "品牌同台",
}


def _aeo_status(value: float, metric_key: str) -> str:
    """Evaluate metric status based on configurable thresholds."""
    thresholds = AEO_THRESHOLDS.get(metric_key, {"good": 50, "warning": 30})
    if value >= thresholds["good"]:
        return "good"
    if value >= thresholds["warning"]:
        return "warning"
    return "poor"


def _executive_summary_text(data: dict[str, Any]) -> str:
    summary = data.get("executive_summary")
    if isinstance(summary, dict):
        one_line = str(summary.get("one_line_judgment") or "").strip()
        if one_line:
            return one_line
    for key in ("executive_summary_text", "subtitle", "executive_summary"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "最近一轮报告已经生成，可直接查看核心指标和引用分布。"


class AnalyticsService:
    """Aggregates analysis data for the Dashboard."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        viewer: User | None = None,
        allow_internal_admin_bypass: bool = True,
    ):
        self.db = db
        self.viewer = viewer
        self.allow_internal_admin_bypass = allow_internal_admin_bypass

    async def _get_latest_output(
        self, output_type: str | None = None, brand_id: str | None = None
    ) -> dict[str, Any] | None:
        """Get the most recent OUTPUT message's output_data.

        Args:
            output_type: Filter by output_type (e.g., 'report', 'chart').
                         If None, returns the latest OUTPUT message.
            brand_id: Filter by brand entity ID via Session.entity_id.
        """
        query = (
            select(Message)
            .where(
                Message.role == MessageRole.ASSISTANT,
                Message.type == MessageType.OUTPUT,
            )
            .order_by(desc(Message.created_at))
        )
        query = query.join(Session, Message.session_id == Session.id)
        if self.viewer is not None:
            query = query.where(
                AccessScopeService.session_visibility_filter(
                    self.viewer,
                    allow_internal_admin_bypass=self.allow_internal_admin_bypass,
                )
            )
        if brand_id:
            try:
                brand_uuid = UUID(brand_id)
            except (ValueError, AttributeError):
                return None
            query = query.where(Session.entity_id == brand_uuid)
        else:
            query = query.where(Session.entity_id.isnot(None))
        if output_type:
            query = query.where(Message.output_type == output_type)
        query = query.limit(1)

        result = await self.db.execute(query)
        msg = result.scalar_one_or_none()
        if msg and msg.output_data:
            try:
                return json.loads(msg.output_data)
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Failed to parse output_data for message {msg.id}")
        return None

    async def _get_all_outputs(
        self, brand_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get all OUTPUT messages' output_data."""
        query = (
            select(Message)
            .where(
                Message.role == MessageRole.ASSISTANT,
                Message.type == MessageType.OUTPUT,
            )
            .order_by(desc(Message.created_at))
            .limit(20)
        )
        query = query.join(Session, Message.session_id == Session.id)
        if self.viewer is not None:
            query = query.where(
                AccessScopeService.session_visibility_filter(
                    self.viewer,
                    allow_internal_admin_bypass=self.allow_internal_admin_bypass,
                )
            )
        if brand_id:
            try:
                brand_uuid = UUID(brand_id)
            except (ValueError, AttributeError):
                return []
            query = query.where(Session.entity_id == brand_uuid)
        else:
            query = query.where(Session.entity_id.isnot(None))
        result = await self.db.execute(query)
        messages = result.scalars().all()

        outputs = []
        for msg in messages:
            if msg.output_data:
                try:
                    data = json.loads(msg.output_data)
                    metadata = None
                    if msg.extra_metadata:
                        try:
                            metadata = json.loads(msg.extra_metadata)
                        except (json.JSONDecodeError, TypeError):
                            metadata = None
                    data["_output_type"] = msg.output_type
                    data["_created_at"] = (
                        msg.created_at.isoformat() if msg.created_at else None
                    )
                    data["_artifact_kind"] = (
                        metadata.get("artifact_kind")
                        if isinstance(metadata, dict)
                        else None
                    )
                    data["_report_kind"] = (
                        metadata.get("report_kind")
                        if isinstance(metadata, dict)
                        else None
                    )
                    data["_triggered_by"] = data.get("triggered_by") or (
                        metadata.get("triggered_by")
                        if isinstance(metadata, dict)
                        else None
                    )
                    outputs.append(data)
                except (json.JSONDecodeError, TypeError):
                    continue
        return outputs

    def _is_dashboard_report_output(self, output: dict[str, Any]) -> bool:
        """Return True when the artifact is an A5 report suitable for dashboard boards."""
        output_type = str(output.get("_output_type") or "")
        artifact_kind = (
            str(output.get("_artifact_kind") or output.get("artifact_kind") or "")
            .strip()
            .lower()
        )
        report_kind = (
            str(output.get("_report_kind") or output.get("report_kind") or "")
            .strip()
            .lower()
        )

        if artifact_kind in {
            "confidence_signal",
            "confidence_analysis",
        } or report_kind in {
            "confidence_signal",
            "confidence_analysis",
        }:
            return False
        if artifact_kind == "geo_report" and report_kind in {"panorama", "scenario"}:
            return True
        if output_type != "report":
            return False

        # A5 reports carry V2 dashboard fields; A7 confidence signal reports do not.
        v2_keys = (
            "summary_metrics",
            "scenario_matrix",
            "competitor_battles",
            "risk_map",
            "action_queue",
            "source_overview",
            "mention_sentiment_analysis",
        )
        if any(key in output for key in v2_keys):
            return True

        report_data = output.get("report_data")
        if isinstance(report_data, dict) and any(key in report_data for key in v2_keys):
            return True

        metrics_raw = output.get("metrics_raw")
        if isinstance(metrics_raw, dict) and any(key in metrics_raw for key in v2_keys):
            return True

        return False

    def _normalize_dashboard_monitor_mode(self, value: str | None) -> str | None:
        normalized = str(value or "").strip().lower()
        if not normalized:
            return None
        return DASHBOARD_MONITOR_MODE_ALIASES.get(normalized)

    def _dashboard_report_kind(self, output: dict[str, Any]) -> str:
        meta = output.get("meta")
        meta = meta if isinstance(meta, dict) else {}
        dashboard_projection = output.get("dashboard_projection")
        dashboard_projection = (
            dashboard_projection if isinstance(dashboard_projection, dict) else {}
        )
        report_kind = (
            output.get("_report_kind")
            or output.get("report_kind")
            or meta.get("report_kind")
            or dashboard_projection.get("report_kind")
        )
        return (
            self._normalize_dashboard_monitor_mode(str(report_kind or "")) or "panorama"
        )

    def _matches_dashboard_monitor_mode(
        self,
        output: dict[str, Any],
        monitor_mode: str | None,
    ) -> bool:
        if not monitor_mode:
            return True
        return self._dashboard_report_kind(output) == monitor_mode

    def _extract_metrics(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Extract metrics from output data (supports nested structures)."""
        if "metric_bundle" in data and isinstance(data["metric_bundle"], dict):
            return data["metric_bundle"]
        if "metrics" in data:
            return data["metrics"]
        if "metrics_raw" in data and isinstance(data["metrics_raw"], dict):
            return data["metrics_raw"]
        if "bwvs_index" in data or "mention_rate" in data:
            return data
        return None

    def _extract_report(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Extract report from output data."""
        if data.get("artifact_kind") == "geo_report":
            return data
        if "report" in data:
            return data["report"]
        if "executive_summary" in data:
            return data
        return None

    def _extract_competitors(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract competitor data from output."""
        if "competitors" in data and isinstance(data["competitors"], list):
            return data["competitors"]
        return []

    def _extract_fetch_results(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract fetch results from output.

        Supports both raw fetch_results (nested with platform_results)
        and the flat fetch_results_summary written by A5.
        """
        if "fetch_results" in data and isinstance(data["fetch_results"], list):
            return data["fetch_results"]
        # A5 saves a flattened summary for analytics
        if "fetch_results_summary" in data and isinstance(
            data["fetch_results_summary"], list
        ):
            return [{"platform_results": data["fetch_results_summary"]}]
        if "results" in data and isinstance(data["results"], list):
            return data["results"]
        return []

    async def _get_report_like_outputs(
        self,
        brand_id: str | None = None,
        monitor_mode: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get recent report artifacts only, ordered from newest to oldest."""
        query = (
            select(Message)
            .where(
                Message.role == MessageRole.ASSISTANT,
                Message.type == MessageType.OUTPUT,
                Message.output_type == "report",
            )
            .order_by(desc(Message.created_at))
            .limit(
                DASHBOARD_REPORT_MONITOR_MODE_SCAN_LIMIT
                if monitor_mode
                else DASHBOARD_REPORT_DEFAULT_LIMIT
            )
        )
        query = query.join(Session, Message.session_id == Session.id)
        if self.viewer is not None:
            query = query.where(
                AccessScopeService.session_visibility_filter(
                    self.viewer,
                    allow_internal_admin_bypass=self.allow_internal_admin_bypass,
                )
            )
        if brand_id:
            try:
                brand_uuid = UUID(brand_id)
            except (ValueError, AttributeError):
                return []
            query = query.where(Session.entity_id == brand_uuid)
        else:
            query = query.where(Session.entity_id.isnot(None))

        result = await self.db.execute(query)
        messages = result.scalars().all()

        outputs: list[dict[str, Any]] = []
        for msg in messages:
            if not msg.output_data:
                continue
            try:
                data = json.loads(msg.output_data)
                metadata = None
                if msg.extra_metadata:
                    try:
                        metadata = json.loads(msg.extra_metadata)
                    except (json.JSONDecodeError, TypeError):
                        metadata = None
                data["_output_type"] = msg.output_type
                data["_created_at"] = (
                    msg.created_at.isoformat() if msg.created_at else None
                )
                data["_message_id"] = str(msg.id)
                data["_session_id"] = str(msg.session_id)
                data["_artifact_id"] = (
                    metadata.get("output_id")
                    if isinstance(metadata, dict)
                    and isinstance(metadata.get("output_id"), str)
                    else None
                )
                data["_artifact_kind"] = (
                    metadata.get("artifact_kind")
                    if isinstance(metadata, dict)
                    else None
                )
                data["_report_kind"] = (
                    metadata.get("report_kind") if isinstance(metadata, dict) else None
                )
                data["_triggered_by"] = data.get("triggered_by") or (
                    metadata.get("triggered_by") if isinstance(metadata, dict) else None
                )
                if self._is_dashboard_report_output(
                    data
                ) and self._matches_dashboard_monitor_mode(data, monitor_mode):
                    outputs.append(data)
            except (json.JSONDecodeError, TypeError):
                continue
        return outputs

    async def _get_latest_snapshot_report_source(
        self,
        brand_id: str | None = None,
        monitor_mode: str | None = None,
    ) -> dict[str, Any] | None:
        """Get latest snapshot-backed report payload for dashboard home."""
        if not brand_id:
            return None
        try:
            brand_uuid = UUID(brand_id)
        except (ValueError, AttributeError):
            return None

        query = (
            select(AnalysisSnapshot)
            .where(
                AnalysisSnapshot.entity_id == brand_uuid,
                AnalysisSnapshot.triggered_by == "scheduled",
            )
            .order_by(desc(AnalysisSnapshot.created_at))
            .limit(DASHBOARD_REPORT_MONITOR_MODE_SCAN_LIMIT if monitor_mode else 1)
        )
        result = await self.db.execute(query)
        snapshots = result.scalars().all()
        selected_snapshot = None
        selected_raw_data: dict[str, Any] = {}
        for snapshot in snapshots:
            raw_data = snapshot.raw_data if isinstance(snapshot.raw_data, dict) else {}
            snapshot_source = {
                "_report_kind": str(
                    raw_data.get("report_kind") or snapshot.snapshot_type or ""
                )
            }
            if self._matches_dashboard_monitor_mode(snapshot_source, monitor_mode):
                selected_snapshot = snapshot
                selected_raw_data = raw_data
                break
        if selected_snapshot is None:
            return None

        snapshot = selected_snapshot
        raw_data = selected_raw_data
        report_data = raw_data.get("report_data", {})
        report_data = report_data if isinstance(report_data, dict) else {}
        if not report_data:
            return None

        payload = {
            **report_data,
            "metric_bundle": (
                raw_data.get("metric_bundle")
                if isinstance(raw_data.get("metric_bundle"), dict)
                else report_data.get("metric_bundle")
            ),
            "comparison_bundle": (
                raw_data.get("comparison_bundle")
                if isinstance(raw_data.get("comparison_bundle"), dict)
                else report_data.get("comparison_bundle")
            ),
            "dashboard_projection": (
                raw_data.get("dashboard_projection")
                if isinstance(raw_data.get("dashboard_projection"), dict)
                else report_data.get("dashboard_projection")
            ),
            "_output_type": "report",
            "_created_at": (
                snapshot.created_at.isoformat() if snapshot.created_at else None
            ),
            "_session_id": str(snapshot.session_id) if snapshot.session_id else "",
            "_artifact_id": "",
            "_artifact_kind": "geo_report",
            "_report_kind": str(
                raw_data.get("report_kind") or snapshot.snapshot_type or ""
            ),
            "_triggered_by": str(snapshot.triggered_by or ""),
        }
        return payload

    def _dashboard_date_range_days(self, date_range: str | None) -> int:
        normalized = str(date_range or "").strip().lower()
        aliases = {
            "week": 7,
            "7d": 7,
            "last_7_days": 7,
            "month": 30,
            "30d": 30,
            "last_30_days": 30,
            "quarter": 90,
            "90d": 90,
            "last_90_days": 90,
        }
        if normalized in aliases:
            return aliases[normalized]
        if normalized.isdigit():
            return max(1, min(365, int(normalized)))
        return DASHBOARD_DEFAULT_DATE_RANGE_DAYS

    def _snapshot_monitor_mode(self, snapshot: AnalysisSnapshot) -> str:
        raw_data = snapshot.raw_data if isinstance(snapshot.raw_data, dict) else {}
        return (
            self._normalize_dashboard_monitor_mode(
                str(raw_data.get("report_kind") or snapshot.snapshot_type or "")
            )
            or "panorama"
        )

    def _snapshot_to_report_payload(self, snapshot: AnalysisSnapshot) -> dict[str, Any] | None:
        raw_data = snapshot.raw_data if isinstance(snapshot.raw_data, dict) else {}
        report_data = raw_data.get("report_data")
        report_data = report_data if isinstance(report_data, dict) else {}
        if not report_data:
            return None
        return {
            **report_data,
            "metric_bundle": (
                raw_data.get("metric_bundle")
                if isinstance(raw_data.get("metric_bundle"), dict)
                else report_data.get("metric_bundle")
            ),
            "comparison_bundle": (
                raw_data.get("comparison_bundle")
                if isinstance(raw_data.get("comparison_bundle"), dict)
                else report_data.get("comparison_bundle")
            ),
            "dashboard_projection": (
                raw_data.get("dashboard_projection")
                if isinstance(raw_data.get("dashboard_projection"), dict)
                else report_data.get("dashboard_projection")
            ),
            "_output_type": "report",
            "_created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
            "_session_id": str(snapshot.session_id) if snapshot.session_id else "",
            "_artifact_id": "",
            "_artifact_kind": "geo_report",
            "_report_kind": self._snapshot_monitor_mode(snapshot),
            "_triggered_by": str(snapshot.triggered_by or ""),
        }

    async def _get_dashboard_snapshots(
        self,
        *,
        brand_id: str | None,
        monitor_mode: str | None,
        date_range_days: int,
    ) -> list[AnalysisSnapshot]:
        if not brand_id:
            return []
        try:
            brand_uuid = UUID(brand_id)
        except (ValueError, AttributeError):
            return []
        since = datetime.now(timezone.utc) - timedelta(days=date_range_days)
        query = (
            select(AnalysisSnapshot)
            .where(
                AnalysisSnapshot.entity_id == brand_uuid,
                AnalysisSnapshot.status.in_(
                    [SnapshotStatus.COMPLETED, SnapshotStatus.PARTIAL]
                ),
                AnalysisSnapshot.created_at >= since,
            )
            .order_by(AnalysisSnapshot.created_at)
            .limit(500)
        )
        result = await self.db.execute(query)
        snapshots = list(result.scalars().all())
        if not monitor_mode:
            return snapshots
        return [
            snapshot
            for snapshot in snapshots
            if self._snapshot_monitor_mode(snapshot) == monitor_mode
        ]

    def _normalize_trend_metric(self, metric: str | None) -> str:
        normalized = str(metric or "").strip().lower()
        return DASHBOARD_TREND_METRIC_ALIASES.get(normalized, "mention_rate")

    def _normalize_rate_value(self, metric: str, value: float | None) -> float | None:
        if value is None:
            return None
        if metric in {
            "mention_rate",
            "content_citation_rate",
            "official_conversion_rate",
        } and 1 < value <= 100:
            return value / 100
        return value

    def _first_numeric(self, *values: Any) -> float | None:
        for value in values:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
        return None

    def _metric_from_mapping(self, mapping: dict[str, Any], metric: str) -> float | None:
        if not isinstance(mapping, dict):
            return None
        candidate_keys = {
            "bwvs_index": ["bwvs_index", "bwvs", "brand_visibility"],
            "mention_rate": ["mention_rate", "brand_mention_rate", "visibility_rate"],
            "sentiment_score": ["sentiment_score", "sentiment"],
            "coverage_score": [
                "coverage_score",
                "platform_coverage_rate",
                "scenario_effective_rate",
            ],
            "content_citation_rate": [
                "content_citation_rate",
                "official_citation_rate",
                "citation_rate",
                "citation_score",
            ],
            "official_conversion_rate": [
                "official_conversion_rate",
                "official_citation_rate",
            ],
        }.get(metric, [metric])
        for key in candidate_keys:
            value = self._first_numeric(mapping.get(key))
            if value is not None:
                return self._normalize_rate_value(metric, value)
        return None

    def _snapshot_metric_value(
        self,
        snapshot: AnalysisSnapshot,
        metric: str,
    ) -> float | None:
        column_value = None
        if metric in {"bwvs_index", "mention_rate", "sentiment_score", "coverage_score"}:
            column_value = self._first_numeric(getattr(snapshot, metric, None))
        elif metric == "content_citation_rate":
            column_value = self._first_numeric(snapshot.citation_score)
        if column_value is not None:
            return self._normalize_rate_value(metric, column_value)

        raw_data = snapshot.raw_data if isinstance(snapshot.raw_data, dict) else {}
        report_data = raw_data.get("report_data")
        report_data = report_data if isinstance(report_data, dict) else {}
        dashboard_projection = raw_data.get("dashboard_projection")
        dashboard_projection = (
            dashboard_projection if isinstance(dashboard_projection, dict) else {}
        )
        source_summary = raw_data.get("source_summary")
        source_summary = source_summary if isinstance(source_summary, dict) else {}
        candidates = [
            raw_data,
            raw_data.get("metric_bundle") if isinstance(raw_data.get("metric_bundle"), dict) else {},
            raw_data.get("metrics") if isinstance(raw_data.get("metrics"), dict) else {},
            report_data,
            report_data.get("metric_bundle") if isinstance(report_data.get("metric_bundle"), dict) else {},
            report_data.get("metrics") if isinstance(report_data.get("metrics"), dict) else {},
            dashboard_projection.get("headline_metrics")
            if isinstance(dashboard_projection.get("headline_metrics"), dict)
            else {},
            source_summary,
        ]
        for candidate in candidates:
            value = self._metric_from_mapping(candidate, metric)
            if value is not None:
                return value
        return None

    def _trend_direction(self, change_absolute: float | None) -> str:
        if change_absolute is None:
            return "stable"
        if abs(change_absolute) < 0.0001:
            return "stable"
        return "improving" if change_absolute > 0 else "declining"

    def _summarize_trend_points(
        self,
        *,
        metric: str,
        label: str,
        points: list[dict[str, Any]],
        series_id: str = "overall",
        group_by: str = "overall",
    ) -> dict[str, Any]:
        ordered = sorted(points, key=lambda item: str(item.get("date") or ""))
        values = [item.get("value") for item in ordered if isinstance(item.get("value"), (int, float))]
        current_value = values[-1] if values else None
        previous_value = values[-2] if len(values) >= 2 else None
        change_absolute = (
            float(current_value) - float(previous_value)
            if current_value is not None and previous_value is not None
            else None
        )
        change_percentage = (
            (change_absolute / abs(float(previous_value))) * 100
            if change_absolute is not None and previous_value not in (None, 0)
            else None
        )
        average_value = sum(float(value) for value in values) / len(values) if values else None
        return {
            "id": series_id,
            "label": label,
            "metric": metric,
            "metric_label": DASHBOARD_TREND_METRIC_LABELS.get(metric, metric),
            "group_by": group_by,
            "points": ordered,
            "data_point_count": len(values),
            "current_value": current_value,
            "previous_value": previous_value,
            "average_value": average_value,
            "change_absolute": change_absolute,
            "change_percentage": change_percentage,
            "direction": self._trend_direction(change_absolute),
        }

    def _period_summary_from_snapshots(
        self,
        snapshots: list[AnalysisSnapshot],
        *,
        date_range_days: int,
    ) -> dict[str, Any]:
        series = []
        for metric in [
            "mention_rate",
            "bwvs_index",
            "official_conversion_rate",
            "content_citation_rate",
        ]:
            points = []
            for snapshot in snapshots:
                value = self._snapshot_metric_value(snapshot, metric)
                if value is None:
                    continue
                points.append(
                    {
                        "date": snapshot.created_at.date().isoformat()
                        if snapshot.created_at
                        else "",
                        "value": value,
                        "snapshot_id": str(snapshot.id),
                    }
                )
            series.append(
                self._summarize_trend_points(
                    metric=metric,
                    label=DASHBOARD_TREND_METRIC_LABELS.get(metric, metric),
                    points=points,
                    series_id=metric,
                    group_by="overall",
                )
            )
        return {
            "date_range_days": date_range_days,
            "period_label": f"近 {date_range_days} 天",
            "data_point_count": len(snapshots),
            "metrics": series,
        }

    def _empty_period_summary(self, date_range_days: int) -> dict[str, Any]:
        return {
            "date_range_days": date_range_days,
            "period_label": f"近 {date_range_days} 天",
            "data_point_count": 0,
            "metrics": [],
        }

    def _dashboard_period_rollup_from_snapshots(
        self,
        snapshots: list[AnalysisSnapshot],
    ) -> dict[str, Any]:
        platform_rows: dict[str, dict[str, Any]] = {}
        negative_topics_by_platform: dict[str, dict[str, int]] = defaultdict(dict)
        brand_counts: dict[str, int] = defaultdict(int)
        current_brand = ""
        answer_count = 0

        for snapshot in snapshots:
            payload = self._snapshot_to_report_payload(snapshot) or {}
            input_bundle = payload.get("input_bundle")
            input_bundle = input_bundle if isinstance(input_bundle, dict) else {}
            meta = input_bundle.get("meta")
            meta = meta if isinstance(meta, dict) else {}
            brand_master = input_bundle.get("brand_master")
            brand_master = brand_master if isinstance(brand_master, dict) else {}
            if not current_brand:
                current_brand = str(
                    brand_master.get("monitor_brand")
                    or meta.get("brand_name")
                    or payload.get("brand_name")
                    or ""
                ).strip()

            answers = input_bundle.get("answers")
            if not isinstance(answers, list):
                continue

            for answer in answers:
                if not isinstance(answer, dict) or answer.get("status") != "ok":
                    continue
                platform = str(answer.get("platform") or "").strip()
                if not platform:
                    continue
                answer_count += 1
                fetch_method = self._answer_fetch_method(answer)
                source_label = self._ai_source_label(platform, fetch_method)
                source_key = f"{platform.lower()}:{fetch_method or 'unknown'}"
                row = platform_rows.setdefault(
                    source_key,
                    {
                        "platform": source_label,
                        "platformId": platform.lower(),
                        "fetchMethod": fetch_method or None,
                        "status": "unknown",
                        "answerCount": 0,
                        "brandMentionCount": 0,
                        "positiveCount": 0,
                        "negativeCount": 0,
                    },
                )
                row["answerCount"] += 1

                raw_mentioned_brands = answer.get("mentioned_brands")
                mentioned_brands = (
                    raw_mentioned_brands if isinstance(raw_mentioned_brands, list) else []
                )
                answer_brands = {
                    str(brand).strip()
                    for brand in mentioned_brands
                    if str(brand).strip()
                }
                if answer.get("mentioned_monitor_brand") and current_brand:
                    answer_brands.add(current_brand)
                for brand in answer_brands:
                    brand_counts[brand] += 1

                if answer.get("mentioned_monitor_brand"):
                    row["brandMentionCount"] += 1
                    sentiment = str(answer.get("sentiment") or "neutral")
                    if sentiment == "positive":
                        row["positiveCount"] += 1
                    elif sentiment == "negative":
                        row["negativeCount"] += 1
                    raw_negative_topics = answer.get("negative_topics")
                    negative_topics = (
                        raw_negative_topics if isinstance(raw_negative_topics, list) else []
                    )
                    for topic in negative_topics:
                        topic_key = str(topic or "").strip()
                        if not topic_key:
                            continue
                        topics = negative_topics_by_platform.setdefault(source_key, {})
                        topics[topic_key] = topics.get(topic_key, 0) + 1

        for source_key, row in platform_rows.items():
            if row["negativeCount"] > row["positiveCount"] and row["negativeCount"] > 0:
                row["status"] = "risk"
            elif row["brandMentionCount"] > 0:
                row["status"] = "good"
            elif row["answerCount"] > 0:
                row["status"] = "watch"
            topics = negative_topics_by_platform.get(source_key, {})
            if topics:
                row["mainConcern"] = self._negative_topic_label(
                    sorted(topics.items(), key=lambda item: (-item[1], item[0]))[0][0]
                )

        platform_diagnosis = sorted(
            platform_rows.values(),
            key=lambda row: (
                row["status"] == "risk",
                row["brandMentionCount"],
                row["answerCount"],
                row["platform"],
            ),
            reverse=True,
        )
        mention_ranking = [
            {
                "rank": index + 1,
                "brand": brand,
                "mentionRate": round(count / answer_count, 4) if answer_count else None,
                "mentionCount": count,
                "isCurrentBrand": bool(current_brand and brand == current_brand),
            }
            for index, (brand, count) in enumerate(
                sorted(brand_counts.items(), key=lambda item: (-item[1], item[0]))[:10]
            )
        ]

        return {
            "platformDiagnosis": platform_diagnosis,
            "mentionRanking": mention_ranking,
            "periodAnswerCount": answer_count,
        }

    def _augment_home_with_period_context(
        self,
        home: dict[str, Any],
        *,
        monitoring_plan: dict[str, Any] | None,
        period_summary: dict[str, Any],
        recent_issue: dict[str, Any] | None,
        period_rollup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        home["monitoringPlan"] = monitoring_plan
        home["periodSummary"] = period_summary
        home["dataPointCount"] = int(period_summary.get("data_point_count") or 0)
        home["recentIssue"] = recent_issue
        period_rollup = period_rollup if isinstance(period_rollup, dict) else {}
        if "platformDiagnosis" in period_rollup:
            home["platformDiagnosis"] = period_rollup["platformDiagnosis"]
        if "mentionRanking" in period_rollup:
            home["mentionRanking"] = period_rollup["mentionRanking"]
        if "periodAnswerCount" in period_rollup:
            home["periodAnswerCount"] = period_rollup["periodAnswerCount"]
        home["todoItems"] = self._build_dashboard_todo_items(
            home,
            monitoring_plan=monitoring_plan,
            period_summary=period_summary,
        )

        summary_by_metric = {
            str(item.get("metric")): item
            for item in period_summary.get("metrics", []) or []
            if isinstance(item, dict)
        }
        for metric in home.get("metrics", []) or []:
            if not isinstance(metric, dict):
                continue
            metric_summary = summary_by_metric.get(str(metric.get("id") or ""))
            if not metric_summary:
                continue
            metric["dataPointCount"] = metric_summary.get("data_point_count")
            metric["averageValue"] = metric_summary.get("average_value")
            metric["changeAbsolute"] = metric_summary.get("change_absolute")
            metric["trend"] = metric_summary
        return home

    def _build_dashboard_todo_items(
        self,
        home: dict[str, Any],
        *,
        monitoring_plan: dict[str, Any] | None,
        period_summary: dict[str, Any],
    ) -> list[dict[str, Any]]:
        latest_report = home.get("latestReport")
        latest_report = latest_report if isinstance(latest_report, dict) else {}
        report_title = str(latest_report.get("title") or "").strip()
        report_ref = str(
            latest_report.get("artifactId")
            or latest_report.get("outputId")
            or latest_report.get("sessionId")
            or ""
        ).strip()
        report_created_at = str(latest_report.get("createdAt") or "").strip()
        has_latest_report = bool(
            (report_ref or report_created_at)
            and report_title
            and report_title != "暂无最新报告"
        )
        monitor_mode = (
            str(
                latest_report.get("reportKind")
                or (monitoring_plan or {}).get("monitor_mode")
                or "panorama"
            )
            .strip()
            .lower()
        )
        monitor_mode = self._normalize_dashboard_monitor_mode(monitor_mode) or "panorama"

        has_complete_plan = self._dashboard_monitoring_plan_is_complete(
            monitoring_plan
        )
        data_point_count = int(period_summary.get("data_point_count") or 0)

        items: list[dict[str, Any]] = []
        if not has_latest_report and not monitoring_plan and data_point_count == 0:
            items.append(
                {
                    "id": "analysis_setup_incomplete",
                    "kind": "analysis_setup_incomplete",
                    "priority": 1,
                    "title": "完成品牌基本信息与问题生成",
                    "description": "当前品牌还没有完成基础分析流程。先通过 AI 对话补齐品牌信息，并生成问题集。",
                    "action": "ai_conversation",
                    "actionLabel": "AI 对话处理",
                    "monitorMode": monitor_mode,
                }
            )
            return items

        if not has_complete_plan:
            items.append(
                {
                    "id": "monitoring_plan_incomplete",
                    "kind": "monitoring_plan_incomplete",
                    "priority": 2,
                    "title": "完成分析计划设置",
                    "description": "问题集或分析结果已存在，但自动分析计划还没有启用。",
                    "action": "setup_plan",
                    "actionLabel": "设置分析计划",
                    "monitorMode": monitor_mode,
                    "monitoringPlanId": (monitoring_plan or {}).get("id"),
                }
            )
            return items

        if has_latest_report and report_ref:
            items.append(
                {
                    "id": f"unread_latest_report:{report_ref}",
                    "kind": "unread_latest_report",
                    "priority": 3,
                    "title": "查看新的分析报告",
                    "description": "已有新的 A5 完整报告生成，建议先查看报告再继续处理后续分析。",
                    "action": "latest_report",
                    "actionLabel": "查看报告",
                    "monitorMode": monitor_mode,
                    "refId": report_ref,
                    "reportCreatedAt": report_created_at or None,
                }
            )
        return items

    async def _get_recent_monitoring_issue(
        self,
        *,
        brand_id: str | None,
        monitor_mode: str | None,
    ) -> dict[str, Any] | None:
        if not brand_id:
            return None
        try:
            brand_uuid = UUID(brand_id)
        except (ValueError, AttributeError):
            return None
        stale_before = datetime.now(timezone.utc) - timedelta(hours=2)
        result = await self.db.execute(
            select(MonitoringRun)
            .where(
                MonitoringRun.entity_id == brand_uuid,
                MonitoringRun.monitor_mode
                == (monitor_mode or MonitoringPlanService.normalize_monitor_mode("panorama")),
            )
            .order_by(desc(MonitoringRun.updated_at))
            .limit(30)
        )
        runs = list(result.scalars().all())
        selected: MonitoringRun | None = None
        issue_kind = "failed"
        for run in runs:
            if run.status == MonitoringRunStatus.FAILED.value:
                selected = run
                issue_kind = "failed"
                break
            updated_at = run.updated_at or run.created_at
            if updated_at and updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            if (
                run.status in {MonitoringRunStatus.PENDING.value, MonitoringRunStatus.RUNNING.value}
                and updated_at
                and updated_at < stale_before
            ):
                selected = run
                issue_kind = "stale"
                break
        if selected is None:
            return None

        plan_title = ""
        if selected.plan_id:
            plan = await self.db.get(MonitoringPlan, selected.plan_id)
            plan_title = plan.title if plan else ""
        return {
            "id": str(selected.id),
            "type": issue_kind,
            "status": selected.status,
            "title": "自动监测运行失败" if issue_kind == "failed" else "自动监测可能卡住",
            "error_stage": selected.error_stage or "monitoring_run",
            "error_message": selected.error_message
            or ("运行长时间未完成，请通过 AI 对话查看上下文。" if issue_kind == "stale" else ""),
            "monitor_mode": selected.monitor_mode,
            "monitoring_plan_id": str(selected.plan_id),
            "monitoring_run_id": str(selected.id),
            "plan_title": plan_title,
            "question_count": int(selected.question_count or 0),
            "endpoint_ids": selected.endpoint_ids or [],
            "endpoint_labels": MonitoringPlanService.endpoint_ids_to_labels(
                selected.endpoint_ids or []
            ),
            "question_set_ids": selected.question_set_ids or [],
            "created_at": selected.created_at.isoformat() if selected.created_at else None,
            "updated_at": selected.updated_at.isoformat() if selected.updated_at else None,
        }

    def _is_successful_evidence(self, evidence: MonitoringEvidenceRecord) -> bool:
        status = str(evidence.answer_status or "").strip().lower()
        return status in {"", "ok", "success", "completed"}

    def _evidence_mentions_brand(self, evidence: MonitoringEvidenceRecord) -> bool:
        raw = evidence.raw_evidence if isinstance(evidence.raw_evidence, dict) else {}
        for key in (
            "mentioned_monitor_brand",
            "brand_present",
            "monitor_brand_present",
            "is_mentioned",
        ):
            if isinstance(raw.get(key), bool):
                return bool(raw[key])
        state = str(raw.get("answer_state") or raw.get("state") or "").strip().lower()
        if state in {"monitor_only", "monitor_plus_others", "brand_present"}:
            return True
        if state in {"no_brand", "competitor_only"}:
            return False
        return False

    def _endpoint_metric_from_accumulator(
        self,
        metric: str,
        accumulator: dict[str, int],
    ) -> float | None:
        answered = accumulator.get("answered", 0)
        total = accumulator.get("total", 0)
        if metric in {"mention_rate", "bwvs_index"}:
            if not answered:
                return None
            value = accumulator.get("mentioned", 0) / answered
            return round(value * 100, 2) if metric == "bwvs_index" else round(value, 4)
        if metric in {"content_citation_rate", "official_conversion_rate"}:
            if not answered:
                return None
            return round(accumulator.get("cited", 0) / answered, 4)
        if metric == "coverage_score":
            if not total:
                return None
            return round(answered / total, 4)
        return None

    async def get_monitoring_trends_v2(
        self,
        *,
        brand_id: str,
        monitor_mode: str | None = None,
        metric: str = "mention_rate",
        group_by: str = "overall",
        endpoint_id: str | None = None,
        question_set_id: str | None = None,
        date_range: str | None = None,
    ) -> dict[str, Any]:
        """Return monitoring trends grouped by overall, endpoint, or question set."""
        try:
            brand_uuid = UUID(brand_id)
        except (ValueError, AttributeError):
            return {
                "metric": self._normalize_trend_metric(metric),
                "group_by": group_by,
                "monitor_mode": self._normalize_dashboard_monitor_mode(monitor_mode)
                or "panorama",
                "date_range_days": self._dashboard_date_range_days(date_range),
                "series": [],
                "data_point_count": 0,
            }

        normalized_metric = self._normalize_trend_metric(metric)
        normalized_group_by = str(group_by or "overall").strip().lower()
        if normalized_group_by not in {"overall", "endpoint", "question_set"}:
            normalized_group_by = "overall"
        normalized_monitor_mode = (
            self._normalize_dashboard_monitor_mode(monitor_mode) or "panorama"
        )
        date_range_days = self._dashboard_date_range_days(date_range)
        since = datetime.now(timezone.utc) - timedelta(days=date_range_days)

        snapshots = await self._get_dashboard_snapshots(
            brand_id=brand_id,
            monitor_mode=normalized_monitor_mode,
            date_range_days=date_range_days,
        )
        snapshot_by_id = {str(snapshot.id): snapshot for snapshot in snapshots}

        if normalized_group_by == "overall":
            points = []
            for snapshot in snapshots:
                value = self._snapshot_metric_value(snapshot, normalized_metric)
                if value is None:
                    continue
                points.append(
                    {
                        "date": snapshot.created_at.date().isoformat()
                        if snapshot.created_at
                        else "",
                        "value": value,
                        "snapshot_id": str(snapshot.id),
                        "data_point_count": 1,
                    }
                )
            series = [
                self._summarize_trend_points(
                    metric=normalized_metric,
                    label="总览",
                    points=points,
                    series_id="overall",
                    group_by="overall",
                )
            ]
        elif normalized_group_by == "question_set":
            run_result = await self.db.execute(
                select(MonitoringRun)
                .where(
                    MonitoringRun.entity_id == brand_uuid,
                    MonitoringRun.monitor_mode == normalized_monitor_mode,
                    MonitoringRun.status.in_(
                        [
                            MonitoringRunStatus.COMPLETED.value,
                            MonitoringRunStatus.PARTIAL.value,
                        ]
                    ),
                    MonitoringRun.snapshot_id.is_not(None),
                    MonitoringRun.created_at >= since,
                )
                .order_by(MonitoringRun.created_at)
                .limit(500)
            )
            runs = [
                run
                for run in run_result.scalars().all()
                if str(run.snapshot_id) in snapshot_by_id
            ]
            series_points: dict[str, list[dict[str, Any]]] = defaultdict(list)
            observed_question_set_ids: set[str] = set()
            for run in runs:
                question_set_ids = [str(item) for item in run.question_set_ids or []]
                if question_set_id:
                    question_set_ids = [
                        item for item in question_set_ids if item == question_set_id
                    ]
                if not question_set_ids:
                    continue
                snapshot = snapshot_by_id[str(run.snapshot_id)]
                value = self._snapshot_metric_value(snapshot, normalized_metric)
                if value is None:
                    continue
                for qsid in question_set_ids:
                    observed_question_set_ids.add(qsid)
                    series_points[qsid].append(
                        {
                            "date": snapshot.created_at.date().isoformat()
                            if snapshot.created_at
                            else "",
                            "value": value,
                            "snapshot_id": str(snapshot.id),
                            "run_id": str(run.id),
                            "data_point_count": 1,
                        }
                    )
            labels: dict[str, str] = {}
            if observed_question_set_ids:
                ids = [UUID(item) for item in observed_question_set_ids]
                question_set_result = await self.db.execute(
                    select(MonitoringQuestionSet).where(
                        MonitoringQuestionSet.id.in_(ids)
                    )
                )
                labels = {
                    str(item.id): item.title or "问题集"
                    for item in question_set_result.scalars().all()
                }
            series = [
                self._summarize_trend_points(
                    metric=normalized_metric,
                    label=labels.get(qsid, "问题集"),
                    points=points,
                    series_id=qsid,
                    group_by="question_set",
                )
                for qsid, points in sorted(series_points.items())
            ]
        else:
            run_result = await self.db.execute(
                select(MonitoringRun)
                .where(
                    MonitoringRun.entity_id == brand_uuid,
                    MonitoringRun.monitor_mode == normalized_monitor_mode,
                    MonitoringRun.status.in_(
                        [
                            MonitoringRunStatus.COMPLETED.value,
                            MonitoringRunStatus.PARTIAL.value,
                        ]
                    ),
                    MonitoringRun.created_at >= since,
                )
                .order_by(MonitoringRun.created_at)
                .limit(500)
            )
            runs = list(run_result.scalars().all())
            run_by_id = {str(run.id): run for run in runs}
            if not run_by_id:
                series = []
            else:
                evidence_result = await self.db.execute(
                    select(MonitoringEvidenceRecord)
                    .where(
                        MonitoringEvidenceRecord.entity_id == brand_uuid,
                        MonitoringEvidenceRecord.monitoring_run_id.in_(
                            [UUID(item) for item in run_by_id]
                        ),
                        MonitoringEvidenceRecord.created_at >= since,
                    )
                    .order_by(MonitoringEvidenceRecord.created_at)
                    .limit(5000)
                )
                evidence_rows = list(evidence_result.scalars().all())
                grouped: dict[tuple[str, str], dict[str, int]] = defaultdict(
                    lambda: {"total": 0, "answered": 0, "mentioned": 0, "cited": 0}
                )
                for evidence in evidence_rows:
                    if endpoint_id and evidence.endpoint_id != endpoint_id:
                        continue
                    run = run_by_id.get(str(evidence.monitoring_run_id))
                    if run is None:
                        continue
                    date_source = run.completed_at or evidence.created_at
                    date_label = (
                        date_source.date().isoformat() if date_source else ""
                    )
                    key = (str(evidence.endpoint_id or ""), date_label)
                    grouped[key]["total"] += 1
                    if self._is_successful_evidence(evidence):
                        grouped[key]["answered"] += 1
                    if self._evidence_mentions_brand(evidence):
                        grouped[key]["mentioned"] += 1
                    if evidence.cited_domains:
                        grouped[key]["cited"] += 1

                series_points: dict[str, list[dict[str, Any]]] = defaultdict(list)
                for (endpoint_key, date_label), accumulator in grouped.items():
                    value = self._endpoint_metric_from_accumulator(
                        normalized_metric,
                        accumulator,
                    )
                    if value is None:
                        continue
                    series_points[endpoint_key].append(
                        {
                            "date": date_label,
                            "value": value,
                            "data_point_count": accumulator.get("answered", 0),
                        }
                    )
                series = [
                    self._summarize_trend_points(
                        metric=normalized_metric,
                        label=ENDPOINT_REGISTRY.get(endpoint_key, {}).get(
                            "display_name",
                            endpoint_key,
                        ),
                        points=points,
                        series_id=endpoint_key,
                        group_by="endpoint",
                    )
                    for endpoint_key, points in sorted(series_points.items())
                ]

        return {
            "metric": normalized_metric,
            "metric_label": DASHBOARD_TREND_METRIC_LABELS.get(
                normalized_metric,
                normalized_metric,
            ),
            "group_by": normalized_group_by,
            "monitor_mode": normalized_monitor_mode,
            "date_range_days": date_range_days,
            "period_label": f"近 {date_range_days} 天",
            "series": series,
            "data_point_count": sum(
                int(item.get("data_point_count") or 0)
                for item in series
                if isinstance(item, dict)
            ),
        }

    def _select_latest_home_source(
        self,
        latest_output: dict[str, Any] | None,
        latest_snapshot: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        return latest_output or latest_snapshot

    def _extract_v2_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        """Extract V2 contract fields from artifact, report_data, or metrics_raw."""
        dashboard_projection = data.get("dashboard_projection")
        if isinstance(dashboard_projection, dict):
            sections_payload = data.get("sections")
            sections_payload = (
                sections_payload if isinstance(sections_payload, dict) else {}
            )
            return {
                "summary_metrics": data.get("metric_bundle", {}),
                "scenario_matrix": data.get("scenario_matrix", []),
                "competitor_battles": data.get("competitor_battles", []),
                "risk_map": sections_payload.get("risk_map", []),
                "action_queue": sections_payload.get("recommendations_board", {}).get(
                    "items", []
                ),
                "source_overview": data.get("source_overview", {}),
                "mention_sentiment_analysis": data.get(
                    "mention_sentiment_analysis", {}
                ),
                "citation_analysis": data.get("source_overview", {}),
                "diagnosis_modules": extract_geo_report_diagnosis(data),
            }
        nested_report = data.get("report_data")
        nested_report = nested_report if isinstance(nested_report, dict) else {}
        metrics_raw = data.get("metrics_raw")
        metrics_raw = metrics_raw if isinstance(metrics_raw, dict) else {}

        def pick(key: str, default: Any) -> Any:
            if key in data:
                return data.get(key, default)
            if key in nested_report:
                return nested_report.get(key, default)
            if key in metrics_raw:
                return metrics_raw.get(key, default)
            return default

        return {
            "summary_metrics": pick("summary_metrics", {}),
            "scenario_matrix": pick("scenario_matrix", []),
            "competitor_battles": pick("competitor_battles", []),
            "risk_map": pick("risk_map", []),
            "action_queue": pick("action_queue", []),
            "source_overview": pick("source_overview", {}),
            "mention_sentiment_analysis": pick("mention_sentiment_analysis", {}),
            "citation_analysis": data.get("citation_analysis")
            or nested_report.get("citation_analysis")
            or metrics_raw.get("citation_analysis")
            or {},
            "diagnosis_modules": pick("diagnosis_modules", {})
            or extract_geo_report_diagnosis(data),
        }

    def _extract_report_data(self, data: dict[str, Any]) -> dict[str, Any]:
        report_data = data.get("report_data")
        return report_data if isinstance(report_data, dict) else {}

    def _source_type_label(self, source_type: str | None) -> str:
        normalized = str(source_type or "").strip().lower()
        return SOURCE_TYPE_LABELS.get(normalized, SOURCE_TYPE_LABELS["other"])

    def _report_kind_label(self, report_kind: str | None) -> str:
        normalized = str(report_kind or "").strip().lower()
        return REPORT_KIND_LABELS.get(normalized, "分析报告")

    def _platform_label(self, platform: str | None) -> str:
        normalized = str(platform or "").strip()
        return PLATFORM_LABELS.get(normalized.lower(), normalized)

    def _normalize_fetch_method(self, value: Any) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"api", "app_api", "llm_api", "messages_api"}:
            return "api"
        if normalized in {"browser", "web", "webpage", "web_page", "网页版"}:
            return "browser"
        return ""

    def _answer_fetch_method(self, answer: dict[str, Any]) -> str:
        provenance = answer.get("provenance")
        provenance = provenance if isinstance(provenance, dict) else {}
        return self._normalize_fetch_method(
            answer.get("fetch_method")
            or answer.get("fetchMethod")
            or answer.get("source_variant")
            or answer.get("sourceVariant")
            or provenance.get("source_type")
        )

    def _ai_source_label(
        self,
        platform: str | None,
        fetch_method: str | None = None,
    ) -> str:
        normalized_platform = str(platform or "").strip().lower()
        normalized_method = self._normalize_fetch_method(fetch_method)
        if normalized_platform in {"doubao", "豆包"}:
            if normalized_method == "api":
                return "豆包API"
            if normalized_method == "browser":
                return "豆包网页版"
            return "豆包"
        if normalized_platform in {"yuanbao", "hunyuan", "元宝"}:
            if normalized_method == "api":
                return "元宝API"
            if normalized_method == "browser":
                return "元宝网页版"
            return "元宝"
        if normalized_platform in {"kimi", "kimi k1.5", "kimi-k1.5"}:
            if normalized_method == "api":
                return "Kimi API"
            if normalized_method == "browser":
                return "Kimi 网页版"
            return "Kimi"
        if normalized_platform in {"deepseek", "deep seek"}:
            if normalized_method == "api":
                return "DeepSeek API"
            return "DeepSeek网页版"
        return self._platform_label(platform)

    def _negative_topic_label(self, topic: str | None) -> str:
        normalized = str(topic or "").strip().lower()
        return NEGATIVE_TOPIC_LABELS.get(normalized, str(topic or "").strip())

    def _answer_state_label(self, state: str | None) -> str:
        normalized = str(state or "").strip().lower()
        return ANSWER_STATE_LABELS.get(normalized, str(state or "").strip())

    def _build_dashboard_home_from_projection(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any] | None:
        dashboard_projection = data.get("dashboard_projection")
        metric_bundle = data.get("metric_bundle")
        input_bundle = data.get("input_bundle")
        if (
            not isinstance(dashboard_projection, dict)
            or not isinstance(metric_bundle, dict)
            or not isinstance(input_bundle, dict)
        ):
            return None

        source_summary = metric_bundle.get("source_summary", {})
        source_summary = source_summary if isinstance(source_summary, dict) else {}
        questions = input_bundle.get("questions", [])
        questions = [question for question in questions if isinstance(question, dict)]

        meta = data.get("meta")
        meta = meta if isinstance(meta, dict) else {}
        raw_report_kind = (
            data.get("_report_kind")
            or data.get("report_kind")
            or meta.get("report_kind")
            or dashboard_projection.get("report_kind")
        )
        report_kind = (
            self._normalize_dashboard_monitor_mode(str(raw_report_kind or ""))
            or "panorama"
        )
        triggered_by = (
            str(data.get("_triggered_by") or data.get("triggered_by") or "")
            .strip()
            .lower()
        )
        summary_headline = _executive_summary_text(data)
        session_id = str(data.get("_session_id") or "")
        answers_for_scope = [
            answer
            for answer in input_bundle.get("answers", []) or []
            if isinstance(answer, dict) and answer.get("status") == "ok"
        ]

        raw_source_types = source_summary.get("source_type_breakdown", {})
        source_types = []
        if isinstance(raw_source_types, dict):
            source_types = [
                {
                    "key": key,
                    "label": self._source_type_label(key),
                    "share": value if isinstance(value, (int, float)) else None,
                }
                for key, value in raw_source_types.items()
                if isinstance(value, (int, float)) and value > 0
            ]
            source_types.sort(key=lambda item: (-(item["share"] or 0), item["label"]))

        top_domains = [
            {
                "domain": str(item.get("domain", "") or ""),
                "displayName": str(
                    item.get("display_name")
                    or item.get("site_name")
                    or item.get("domain")
                    or ""
                ),
                "count": int(item.get("count", 0) or 0),
                "share": (
                    item.get("share")
                    if isinstance(item.get("share"), (int, float))
                    else None
                ),
                "isOfficial": bool(item.get("is_official", False)),
                "sourceType": str(item.get("source_type", "") or "other"),
                "sourceTypeLabel": self._source_type_label(
                    str(item.get("source_type", "") or "other")
                ),
                "siteCategory": str(item.get("site_category", "") or ""),
            }
            for item in source_summary.get("top_domains", []) or []
            if isinstance(item, dict) and item.get("domain")
        ][:8]

        question_items = []
        seen_question_texts = set()
        for question in questions:
            question_text = str(question.get("question_text") or "").strip()
            if not question_text or question_text in seen_question_texts:
                continue
            seen_question_texts.add(question_text)
            question_items.append(
                {
                    "questionId": str(question.get("question_id", "") or ""),
                    "questionText": question_text,
                    "scene": str(question.get("scene", "") or ""),
                }
            )

        def build_latest_report_context() -> dict[str, Any]:
            question_count = len(question_items)
            platform_labels = sorted(
                {
                    self._ai_source_label(
                        str(answer.get("platform") or ""),
                        self._answer_fetch_method(answer),
                    )
                    for answer in answers_for_scope
                    if answer.get("platform")
                }
            )
            sample_parts = []
            if question_count:
                sample_parts.append(f"{question_count} 个问题")
            if platform_labels:
                sample_parts.append(f"{len(platform_labels)} 个 AI 来源")
            if answers_for_scope:
                sample_parts.append(f"{len(answers_for_scope)} 条有效回答")

            scene_labels = []
            seen_scenes = set()
            for item in question_items:
                scene = str(item.get("scene") or "").strip()
                scene = QUESTION_SCOPE_LABELS.get(scene, scene)
                if not scene or scene in EMPTY_SCOPE_LABELS:
                    continue
                if scene in seen_scenes:
                    continue
                seen_scenes.add(scene)
                scene_labels.append(scene)
                if len(scene_labels) >= 3:
                    break

            if report_kind == "scenario":
                scope_label = "用户场景口径"
                scope_description = (
                    "以下指标仅基于本轮用户场景问题集，不代表完整品牌全景。"
                )
                question_set_label = (
                    "、".join(scene_labels) if scene_labels else "本轮用户场景问题集"
                )
            else:
                scope_label = "品牌全景口径"
                scope_description = (
                    "以下指标来自本轮品牌全景问题集，用于观察整体 AI 可见度。"
                )
                question_set_label = (
                    "、".join(scene_labels) if scene_labels else "本轮品牌全景问题集"
                )

            return {
                "scopeLabel": scope_label,
                "scopeDescription": scope_description,
                "questionSetLabel": question_set_label,
                "sampleSummary": " · ".join(sample_parts),
                "questionPreview": [
                    item["questionText"]
                    for item in question_items[:3]
                    if item.get("questionText")
                ],
            }

        mention_rate = metric_bundle.get("brand_visibility")
        if not isinstance(mention_rate, (int, float)):
            mention_rate = metric_bundle.get("mention_rate")

        official_conversion_rate = metric_bundle.get("official_conversion_rate")
        if not isinstance(official_conversion_rate, (int, float)):
            official_conversion_rate = source_summary.get("official_conversion_rate")

        answer_sample_count = int(
            metric_bundle.get("successful_answers")
            or metric_bundle.get("total_answers")
            or 0
        )
        current_brand = str(
            data.get("brand_name") or meta.get("brand_name") or ""
        ).strip()
        home_v4 = dashboard_projection.get("home_v4")
        home_v4 = home_v4 if isinstance(home_v4, dict) else {}

        def numeric(value: Any) -> float | int | None:
            return value if isinstance(value, (int, float)) else None

        def build_word_cloud() -> dict[str, Any]:
            positive_rows = []
            for item in metric_bundle.get("top_positive_reasons", []) or []:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("display") or item.get("reason") or "").strip()
                if not text:
                    continue
                positive_rows.append(
                    {
                        "text": text,
                        "weight": numeric(item.get("rate")) or 0,
                        "sentiment": "positive",
                    }
                )

            negative_rows = []
            for item in metric_bundle.get("top_negative_topics", []) or []:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("display") or item.get("topic") or "").strip()
                if not text:
                    continue
                negative_rows.append(
                    {
                        "text": text,
                        "weight": numeric(item.get("rate")) or 0,
                        "sentiment": "negative",
                        "count": int(item.get("count", 0) or 0),
                    }
                )

            return {"positive": positive_rows, "negative": negative_rows}

        def build_platform_diagnosis() -> list[dict[str, Any]]:
            answers = input_bundle.get("answers", [])
            answers = [
                answer
                for answer in answers
                if isinstance(answer, dict) and answer.get("status") == "ok"
            ]
            platform_rows: dict[str, dict[str, Any]] = {}
            negative_topics_by_platform: dict[str, dict[str, int]] = {}

            for answer in answers:
                platform = str(answer.get("platform") or "").strip()
                if not platform:
                    continue
                fetch_method = self._answer_fetch_method(answer)
                source_label = self._ai_source_label(platform, fetch_method)
                source_key = f"{platform.strip().lower()}:{fetch_method or 'unknown'}"
                row = platform_rows.setdefault(
                    source_key,
                    {
                        "platform": source_label,
                        "platformId": platform.strip().lower(),
                        "fetchMethod": fetch_method or None,
                        "status": "unknown",
                        "answerCount": 0,
                        "brandMentionCount": 0,
                        "positiveCount": 0,
                        "negativeCount": 0,
                    },
                )
                row["answerCount"] += 1
                if answer.get("mentioned_monitor_brand"):
                    row["brandMentionCount"] += 1
                    sentiment = str(answer.get("sentiment") or "neutral")
                    if sentiment == "positive":
                        row["positiveCount"] += 1
                    elif sentiment == "negative":
                        row["negativeCount"] += 1
                    for topic in answer.get("negative_topics", []) or []:
                        if not topic:
                            continue
                        topics = negative_topics_by_platform.setdefault(source_key, {})
                        topic_key = str(topic)
                        topics[topic_key] = topics.get(topic_key, 0) + 1

            for source_key, row in platform_rows.items():
                if (
                    row["negativeCount"] > row["positiveCount"]
                    and row["negativeCount"] > 0
                ):
                    row["status"] = "risk"
                elif row["brandMentionCount"] > 0:
                    row["status"] = "good"
                elif row["answerCount"] > 0:
                    row["status"] = "watch"
                topics = negative_topics_by_platform.get(source_key, {})
                if topics:
                    row["mainConcern"] = self._negative_topic_label(
                        sorted(topics.items(), key=lambda item: (-item[1], item[0]))[0][
                            0
                        ]
                    )

            return sorted(
                platform_rows.values(),
                key=lambda row: (
                    row["status"] == "risk",
                    row["brandMentionCount"],
                    row["platform"],
                ),
                reverse=True,
            )

        question_diagnostics = metric_bundle.get("question_diagnostics", {})
        question_diagnostics = (
            question_diagnostics if isinstance(question_diagnostics, dict) else {}
        )
        risk_rows = [
            row
            for row in question_diagnostics.get("risk_rows", []) or []
            if isinstance(row, dict)
        ]
        question_rows = [
            row
            for row in question_diagnostics.get("question_rows", []) or []
            if isinstance(row, dict)
        ]

        def build_risks() -> list[dict[str, Any]]:
            rows = []
            for item in sorted(
                risk_rows,
                key=lambda row: (
                    str(row.get("risk_level") or ""),
                    str(row.get("question_text") or ""),
                ),
            )[:4]:
                title = str(
                    item.get("question_text") or item.get("scene") or ""
                ).strip()
                if not title:
                    continue
                topics = item.get("negative_topics", []) or []
                rows.append(
                    {
                        "title": title,
                        "level": (
                            "high" if item.get("risk_level") == "high" else "medium"
                        ),
                        "platform": "、".join(
                            self._platform_label(str(platform))
                            for platform in item.get("present_platforms", []) or []
                            if platform
                        ),
                        "evidence": "、".join(
                            self._negative_topic_label(str(topic))
                            for topic in topics
                            if topic
                        )
                        or self._answer_state_label(
                            str(item.get("answer_state") or "")
                        ),
                    }
                )
            return rows

        def build_advantages() -> list[dict[str, Any]]:
            rows = []
            candidates = [
                row
                for row in question_rows
                if row.get("brand_present")
                and str(row.get("risk_level") or "") in {"low", "medium"}
            ]
            candidates.sort(
                key=lambda row: (
                    -len(row.get("present_platforms", []) or []),
                    str(row.get("question_text") or ""),
                )
            )
            for item in candidates[:4]:
                title = str(
                    item.get("question_text") or item.get("scene") or ""
                ).strip()
                if not title:
                    continue
                platforms = item.get("present_platforms", []) or []
                rows.append(
                    {
                        "title": title,
                        "platformCount": len(platforms),
                        "evidence": "、".join(
                            self._platform_label(str(platform))
                            for platform in platforms
                            if platform
                        ),
                    }
                )
            return rows

        def build_mention_ranking() -> list[dict[str, Any]]:
            rows = []
            for item in metric_bundle.get("top_brand_ranking", []) or []:
                if not isinstance(item, dict):
                    continue
                brand = str(item.get("brand") or "").strip()
                rank = item.get("rank")
                mention_count = int(item.get("brand_presence_count", 0) or 0)
                if not brand or not isinstance(rank, int):
                    continue
                rows.append(
                    {
                        "rank": rank,
                        "brand": brand,
                        "mentionRate": (
                            round(mention_count / answer_sample_count, 4)
                            if answer_sample_count
                            else None
                        ),
                        "mentionCount": mention_count,
                        "isCurrentBrand": bool(
                            current_brand and brand == current_brand
                        ),
                    }
                )
            return rows[:10]

        source_structure = {
            "officialConversionRate": (
                official_conversion_rate
                if isinstance(official_conversion_rate, (int, float))
                else None
            ),
            "sourceTypes": source_types,
            "topDomains": top_domains,
        }

        return {
            "summary": {"headline": summary_headline},
            "latestReport": {
                "title": str(data.get("title") or "分析报告"),
                "subtitle": summary_headline,
                "reportKind": report_kind,
                "reportKindLabel": self._report_kind_label(report_kind),
                **build_latest_report_context(),
                "badgeLabel": "自动监测" if triggered_by == "scheduled" else None,
                "triggeredBy": triggered_by or None,
                "sessionId": session_id,
                "artifactId": str(
                    data.get("_artifact_id") or data.get("_message_id") or ""
                ),
                "outputId": str(data.get("_message_id") or ""),
                "createdAt": str(data.get("_created_at") or ""),
                "actionLabel": "打开报告",
            },
            "metrics": [
                {
                    "id": "mention_rate",
                    "label": "提及率",
                    "value": (
                        mention_rate if isinstance(mention_rate, (int, float)) else None
                    ),
                    "format": "percent",
                    "subtitle": "",
                },
                {
                    "id": "brand_rank",
                    "label": "排名",
                    "value": (
                        metric_bundle.get("brand_rank")
                        if isinstance(metric_bundle.get("brand_rank"), int)
                        else None
                    ),
                    "format": "rank",
                    "subtitle": "",
                },
                {
                    "id": "official_conversion_rate",
                    "label": "官网转化率",
                    "value": (
                        official_conversion_rate
                        if isinstance(official_conversion_rate, (int, float))
                        else None
                    ),
                    "format": "percent",
                    "subtitle": "",
                },
                {
                    "id": "negative_rate",
                    "label": "负向率",
                    "value": (
                        metric_bundle.get("negative_rate")
                        if isinstance(metric_bundle.get("negative_rate"), (int, float))
                        else None
                    ),
                    "format": "percent",
                    "subtitle": "",
                },
            ],
            "wordCloud": home_v4.get("wordCloud")
            or home_v4.get("word_cloud")
            or build_word_cloud(),
            "platformDiagnosis": build_platform_diagnosis()
            or home_v4.get("platformDiagnosis")
            or home_v4.get("platform_diagnosis"),
            "risks": home_v4.get("risks") or build_risks(),
            "advantages": home_v4.get("advantages") or build_advantages(),
            "mentionRanking": home_v4.get("mentionRanking")
            or home_v4.get("mention_ranking")
            or build_mention_ranking(),
            "sourceStructure": home_v4.get("sourceStructure")
            or home_v4.get("source_structure")
            or source_structure,
            "citationDistribution": {
                "summary": "",
                "sourceTypes": source_types,
                "topDomains": top_domains,
            },
            "relatedQuestions": {
                "summary": "",
                "items": question_items,
            },
            "diagnosisModules": extract_geo_report_diagnosis(data),
        }

    def _extract_platform_analysis(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        report_data = self._extract_report_data(data)
        platform_analysis = report_data.get(
            "platform_analysis", data.get("platform_analysis", [])
        )
        return (
            [item for item in platform_analysis if isinstance(item, dict)]
            if isinstance(platform_analysis, list)
            else []
        )

    def _extract_competitor_deep_analysis(self, data: dict[str, Any]) -> dict[str, Any]:
        report_data = self._extract_report_data(data)
        competitor_deep_analysis = report_data.get(
            "competitor_deep_analysis",
            data.get("competitor_deep_analysis", {}),
        )
        return (
            competitor_deep_analysis
            if isinstance(competitor_deep_analysis, dict)
            else {}
        )

    def _legacy_sentiment_summary(self, data: dict[str, Any]) -> dict[str, int]:
        metrics = self._extract_metrics(data) or {}
        raw = metrics.get(
            "sentiment_distribution", data.get("sentiment_distribution", {})
        )
        raw = raw if isinstance(raw, dict) else {}

        def read_count(key: str) -> int:
            value = raw.get(key, 0)
            if isinstance(value, (int, float)):
                if 0 < float(value) <= 1:
                    return int(round(float(value) * 100))
                return int(round(float(value)))
            return 0

        return {
            "positive": read_count("positive"),
            "neutral": read_count("neutral"),
            "negative": read_count("negative"),
        }

    def _legacy_sentiment_label(self, value: Any, fallback_text: str = "") -> str:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"positive", "neutral", "negative"}:
                return normalized
        if isinstance(value, (int, float)):
            if float(value) > 0.2:
                return "positive"
            if float(value) < -0.2:
                return "negative"
        lowered = fallback_text.lower()
        if any(token in lowered for token in ["优势", "较强", "领先", "正向", "推荐"]):
            return "positive"
        if any(
            token in lowered
            for token in ["缺失", "不足", "短板", "风险", "偏弱", "负向"]
        ):
            return "negative"
        return "neutral"

    def _sentiment_summary_from_mentions(
        self, mentions: list[dict[str, Any]]
    ) -> dict[str, int]:
        summary = {"positive": 0, "neutral": 0, "negative": 0}
        for item in mentions:
            sentiment = (
                str(item.get("sentiment", "neutral") or "neutral").strip().lower()
            )
            if sentiment not in summary:
                sentiment = "neutral"
            summary[sentiment] += 1
        return summary

    def _legacy_brand_mentions_from_fetch_results(
        self, data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        fetch_results = self._extract_fetch_results(data)
        mentions: list[dict[str, Any]] = []

        for question_index, row in enumerate(fetch_results, start=1):
            if not isinstance(row, dict):
                continue

            scenario_id = str(
                row.get("question_id")
                or row.get("id")
                or f"legacy-question-{question_index}"
            )
            scenario_label = str(
                row.get("question_text")
                or row.get("query")
                or row.get("question")
                or row.get("title")
                or ""
            ).strip()
            platform_results = (
                row.get("platform_results", [])
                if isinstance(row.get("platform_results"), list)
                else []
            )

            # 仅当旧数据里真实保留了问题或查询文本时，才重建问题级提及明细。
            if not scenario_label:
                continue

            for platform_index, item in enumerate(platform_results, start=1):
                if not isinstance(item, dict) or not item.get("success"):
                    continue

                answer = (
                    item.get("answer", {})
                    if isinstance(item.get("answer"), dict)
                    else {}
                )
                has_brand_mention = bool(
                    answer.get("has_brand_mention")
                    if isinstance(answer, dict)
                    else item.get("has_brand_mention", False)
                )
                if not has_brand_mention:
                    continue

                content = str(
                    answer.get("content")
                    or item.get("content")
                    or item.get("answer_text")
                    or ""
                )
                citations = (
                    item.get("citations", [])
                    if isinstance(item.get("citations"), list)
                    else []
                )
                citation_domains: list[str] = []
                citation_titles: list[str] = []
                citation_urls: list[str] = []
                for citation in citations:
                    if not isinstance(citation, dict):
                        continue
                    url = str(citation.get("url", "") or "").strip()
                    domain = str(
                        citation.get("domain")
                        or extract_domain(url)
                        or citation.get("source")
                        or ""
                    ).strip()
                    title = str(citation.get("title", "") or "").strip()
                    if domain and domain not in citation_domains:
                        citation_domains.append(domain)
                    if title and title not in citation_titles:
                        citation_titles.append(title)
                    if url and url not in citation_urls:
                        citation_urls.append(url)

                mentions.append(
                    {
                        "scenarioId": scenario_id
                        or f"legacy-question-{question_index}-{platform_index}",
                        "scenarioLabel": scenario_label or f"问题 {question_index}",
                        "platform": str(
                            item.get("platform") or item.get("platform_name") or ""
                        ),
                        "sentiment": self._legacy_sentiment_label(
                            answer.get("sentiment"), content
                        ),
                        "evidence": content[:280].strip(),
                        "citationDomains": citation_domains,
                        "citationTitles": citation_titles,
                        "citationUrls": citation_urls,
                        "officialCitationPresent": False,
                    }
                )

        return mentions

    def _legacy_scenario_insight_rows(
        self,
        rows: Any,
        default_reason: str,
    ) -> list[dict[str, Any]]:
        items = rows if isinstance(rows, list) else []
        normalized: list[dict[str, Any]] = []
        for index, row in enumerate(items):
            if isinstance(row, dict):
                label = (
                    row.get("scenario_label")
                    or row.get("scenario")
                    or row.get("title")
                    or row.get("label")
                    or f"场景 {index + 1}"
                )
                reason = (
                    row.get("evidence")
                    or row.get("description")
                    or row.get("reason")
                    or row.get("title")
                    or default_reason
                )
                platforms = row.get("platforms") or row.get("present_platforms") or []
                normalized.append(
                    {
                        "scenarioId": str(
                            row.get("scenario_id", f"legacy-{index + 1}")
                        ),
                        "scenarioLabel": str(label),
                        "reason": str(reason),
                        "platforms": [
                            str(platform) for platform in platforms if platform
                        ],
                    }
                )
            elif row:
                normalized.append(
                    {
                        "scenarioId": f"legacy-{index + 1}",
                        "scenarioLabel": str(row),
                        "reason": default_reason,
                        "platforms": [],
                    }
                )
        return normalized

    def _build_legacy_mention_board(
        self,
        data: dict[str, Any],
        mention_rate: float | None,
    ) -> dict[str, Any]:
        competitor_deep_analysis = self._extract_competitor_deep_analysis(data)
        strengths = self._legacy_scenario_insight_rows(
            self._extract_report_data(data).get("strengths", data.get("strengths", [])),
            "品牌已经在该场景建立一定存在感。",
        )
        weaknesses = self._legacy_scenario_insight_rows(
            self._extract_report_data(data).get(
                "weaknesses", data.get("weaknesses", [])
            ),
            "该场景仍需要补强品牌提及和证据表现。",
        )

        # 旧报告若未保存原始 fetch_results，就无法重建真实的问题级提及明细。
        # 这里不再从 platform_analysis 反推伪问题，避免顶部统计和下方问题列表口径不一致。
        brand_mentions = self._legacy_brand_mentions_from_fetch_results(data)

        comparison_matrix = competitor_deep_analysis.get("comparison_matrix", [])
        comparison_matrix = (
            comparison_matrix if isinstance(comparison_matrix, list) else []
        )
        leading_competitors = []
        competitor_mentions: list[dict[str, Any]] = []
        for row in comparison_matrix[:3]:
            if not isinstance(row, dict):
                continue
            competitor_only = int(row.get("competitor_only_scenarios", 0) or 0)
            shared = int(row.get("shared_scenarios", 0) or 0)
            pressure = (
                "high"
                if competitor_only >= max(shared, 1)
                else "medium" if (competitor_only or shared) else "low"
            )
            leading_competitors.append(
                {
                    "competitor": str(row.get("competitor", "")),
                    "pressureLevel": pressure,
                    "competitorOnlyScenarios": competitor_only,
                    "sentimentSummary": {
                        "positive": 0,
                        "neutral": shared + competitor_only,
                        "negative": 0,
                    },
                }
            )
            for conflict_index, scenario in enumerate(
                (row.get("top_conflict_scenarios") or [])[:3]
            ):
                competitor_mentions.append(
                    {
                        "competitor": str(row.get("competitor", "")),
                        "scenarioId": f"legacy-competitor-{conflict_index + 1}",
                        "scenarioLabel": str(scenario),
                        "platform": "",
                        "sentiment": "neutral",
                        "evidence": "该竞品在该场景被频繁共同提及或独占提及。",
                        "citationDomains": [],
                        "citationTitles": [],
                        "officialCitationPresent": False,
                    }
                )

        sentiment_summary = self._sentiment_summary_from_mentions(brand_mentions)
        mention_count = len(brand_mentions)
        total_questions = int(
            (self._extract_metrics(data) or {}).get("total_questions", 0) or 0
        )
        leading_competitor = (
            leading_competitors[0]["competitor"]
            if leading_competitors
            else "暂无明显竞品压力"
        )
        headline = (
            f"品牌当前约在 {mention_count}/{total_questions or 0} 个问题中被提及，"
            f"其中正向提及 {sentiment_summary['positive']} 条，主要竞争压力来自 {leading_competitor}。"
        )

        return {
            "mentionRate": mention_rate,
            "headline": headline,
            "sentimentSummary": sentiment_summary,
            "leadingCompetitors": leading_competitors,
            "report": {
                "brandMentions": brand_mentions[:10],
                "competitorMentions": competitor_mentions[:12],
                "strongScenarios": strengths[:4],
                "weakScenarios": weaknesses[:6],
            },
        }

    def _build_legacy_source_board(
        self, data: dict[str, Any], source_overview: dict[str, Any]
    ) -> dict[str, Any]:
        brand_domain = str(source_overview.get("brand_domain", "") or "")
        fetch_results_summary = data.get("fetch_results_summary", [])
        fetch_results_summary = (
            fetch_results_summary if isinstance(fetch_results_summary, list) else []
        )

        total_brand_mentions = 0
        cited_brand_answers = 0
        official_cases: list[dict[str, Any]] = []
        non_official_cases: list[dict[str, Any]] = []
        unique_contents: set[tuple[str, str]] = set()
        platform_stats: dict[str, dict[str, Any]] = {}

        for index, row in enumerate(fetch_results_summary):
            if not isinstance(row, dict) or not row.get("has_brand_mention"):
                continue
            total_brand_mentions += 1
            platform = str(row.get("platform", "") or "")
            citations = (
                row.get("citations", [])
                if isinstance(row.get("citations"), list)
                else []
            )
            if not citations:
                continue
            cited_brand_answers += 1

            citation_domains: list[str] = []
            citation_titles: list[str] = []
            official_present = False
            for citation in citations:
                if not isinstance(citation, dict):
                    continue
                domain = str(
                    citation.get("domain")
                    or extract_domain(str(citation.get("url", "") or ""))
                    or citation.get("source")
                    or ""
                )
                title = str(
                    citation.get("title") or citation.get("source") or domain or ""
                )
                if domain:
                    citation_domains.append(domain)
                if title:
                    citation_titles.append(title)
                if brand_domain and domain == brand_domain:
                    official_present = True
                if title or domain:
                    unique_contents.add((title or domain, domain))

            case = {
                "scenarioId": f"legacy-citation-{index + 1}",
                "scenarioLabel": f"{platform or '平台'} 引用样本 {index + 1}",
                "platform": self._platform_label(platform),
                "matchedAnswer": "",
                "citationDomains": citation_domains,
                "citationTitles": citation_titles[:3],
                "isOfficial": official_present,
            }
            if official_present:
                official_cases.append(case)
            else:
                non_official_cases.append(case)

            platform_row = platform_stats.setdefault(
                platform or "unknown",
                {
                    "platform": platform or "unknown",
                    "total": 0,
                    "cited": 0,
                    "official": 0,
                },
            )
            platform_row["total"] += 1
            platform_row["cited"] += 1
            if official_present:
                platform_row["official"] += 1

        source_headline = (
            f"在 {total_brand_mentions} 条提及品牌的回答里，有 {cited_brand_answers} 条引用了品牌相关内容，"
            f"其中 {len(official_cases)} 条来自官网，{len(non_official_cases)} 条来自第三方站点。"
        )

        platform_citation_stats = (
            source_overview.get("platform_citation_stats", {}) or {}
        )
        platform_rows = []
        for platform, stats in platform_stats.items():
            stat_payload = (
                platform_citation_stats.get(platform, {})
                if isinstance(platform_citation_stats, dict)
                else {}
            )
            total = int(stats.get("total", 0) or 0)
            cited = int(stats.get("cited", 0) or 0)
            platform_rows.append(
                {
                    "platform": platform,
                    "contentCitationRate": round(cited / total, 4) if total else 0.0,
                    "officialCitationRate": float(
                        stat_payload.get("official_citation_rate", 0) or 0
                    ),
                    "topDomains": [
                        {
                            "domain": domain_item.get("domain", ""),
                            "count": int(domain_item.get("count", 0) or 0),
                        }
                        for domain_item in stat_payload.get("top_domains", []) or []
                        if isinstance(domain_item, dict)
                    ],
                }
            )

        return {
            "contentCitationRate": (
                round(cited_brand_answers / total_brand_mentions, 4)
                if total_brand_mentions
                else None
            ),
            "citedAnswerCount": cited_brand_answers,
            "citedContentCount": len(unique_contents),
            "headline": source_headline,
            "report": {
                "officialCases": official_cases[:8],
                "nonOfficialCases": non_official_cases[:8],
                "officialContents": [
                    {"title": title, "domain": domain or None, "isOfficial": True}
                    for title, domain in list(unique_contents)[:12]
                    if brand_domain and domain == brand_domain
                ],
                "nonOfficialContents": [
                    {"title": title, "domain": domain or None, "isOfficial": False}
                    for title, domain in list(unique_contents)[:12]
                    if not brand_domain or domain != brand_domain
                ],
                "topDomains": [
                    {
                        "domain": item.get("domain", ""),
                        "count": int(item.get("count", 0) or 0),
                        "share": float(item.get("share", 0) or 0),
                        "isOfficial": bool(item.get("is_official", False)),
                    }
                    for item in source_overview.get("top_domains", []) or []
                    if isinstance(item, dict)
                ],
                "platformStats": platform_rows,
            },
        }

    def _build_legacy_radar_board(
        self,
        data: dict[str, Any],
        mention_rate: float | None,
    ) -> dict[str, Any]:
        metrics = self._extract_metrics(data) or {}
        platform_analysis = self._extract_platform_analysis(data)
        weaknesses = self._extract_report_data(data).get(
            "weaknesses", data.get("weaknesses", [])
        )
        risk_alerts = self._extract_report_data(data).get(
            "risk_alerts", data.get("risk_alerts", [])
        )
        sentiment_summary = self._legacy_sentiment_summary(data)
        mention_value = float(mention_rate or metrics.get("mention_rate", 0) or 0)
        total_questions = float(metrics.get("total_questions", 0) or 0)
        total_mentions = float(metrics.get("total_mentions", 0) or 0)

        platform_coverage_count = len(
            [
                item
                for item in platform_analysis
                if int(item.get("mentions", item.get("mention_count", 0)) or 0) > 0
            ]
        )
        platform_coverage_rate = (
            min(1.0, platform_coverage_count / 4) if platform_coverage_count else 0.0
        )
        scenario_coverage_rate = (
            min(1.0, (total_mentions / total_questions))
            if total_questions
            else mention_value
        )
        positive_total = (
            sentiment_summary["positive"]
            + sentiment_summary["neutral"]
            + sentiment_summary["negative"]
        )
        positive_rate = (
            (sentiment_summary["positive"] / positive_total) if positive_total else 0.0
        )
        risk_penalty = min(100.0, len(weaknesses) * 12 + len(risk_alerts) * 16)

        radar_dimensions = [
            {
                "id": "industry_influence",
                "label": "行业影响",
                "score": round(max(0.0, min(100.0, mention_value * 100))),
                "summary": "基于品牌提及率估算行业可见度。",
            },
            {
                "id": "audience_coverage",
                "label": "人群覆盖",
                "score": round(max(0.0, min(100.0, platform_coverage_rate * 100))),
                "summary": "当前以平台进入情况作为人群覆盖代理指标。",
            },
            {
                "id": "scenario_coverage",
                "label": "场景覆盖",
                "score": round(max(0.0, min(100.0, scenario_coverage_rate * 100))),
                "summary": "根据提及问题数与总问题数估算场景覆盖。",
            },
            {
                "id": "risk_control",
                "label": "风险控制",
                "score": round(max(0.0, min(100.0, 100.0 - risk_penalty))),
                "summary": "根据短板场景和风险提示估算风险控制表现。",
            },
            {
                "id": "positive_sentiment",
                "label": "积极情绪",
                "score": round(max(0.0, min(100.0, positive_rate * 100))),
                "summary": "反映品牌被提及时的正向情绪占比。",
            },
        ]
        sorted_dimensions = sorted(radar_dimensions, key=lambda item: item["score"])
        weakest_dimension = sorted_dimensions[0]["label"] if sorted_dimensions else ""
        strongest_dimension = (
            sorted_dimensions[-1]["label"] if sorted_dimensions else ""
        )
        return {
            "headline": f"当前最大优势在 {strongest_dimension}，最大短板在 {weakest_dimension}。",
            "strongestDimension": strongest_dimension,
            "weakestDimension": weakest_dimension,
            "dimensions": radar_dimensions,
        }

    def _fallback_source_overview(self, data: dict[str, Any]) -> dict[str, Any]:
        """Build V2 source overview from legacy citation_analysis."""
        citation_analysis = self._extract_v2_payload(data).get("citation_analysis", {})
        if not isinstance(citation_analysis, dict):
            citation_analysis = {}

        total_citations = int(citation_analysis.get("total_citations", 0) or 0)
        official_citations = int(citation_analysis.get("official_citations", 0) or 0)
        top_domains = []
        for item in citation_analysis.get("top_domains", []) or []:
            if not isinstance(item, dict):
                continue
            share = item.get("share", 0) or 0
            if isinstance(share, (int, float)) and share > 1:
                share = share / 100
            top_domains.append(
                {
                    "domain": item.get("domain", ""),
                    "count": int(item.get("count", 0) or 0),
                    "share": round(max(0.0, min(1.0, float(share or 0))), 4),
                    "is_official": bool(item.get("is_official", False)),
                }
            )

        platform_citation_stats = {}
        raw_platform_stats = citation_analysis.get("platform_citation_stats", {}) or {}
        if isinstance(raw_platform_stats, dict):
            for platform, stats in raw_platform_stats.items():
                if not isinstance(stats, dict):
                    continue
                platform_total = int(stats.get("total_citations", 0) or 0)
                platform_official = int(stats.get("official_count", 0) or 0)
                platform_citation_stats[str(platform)] = {
                    "total_citations": platform_total,
                    "official_citations": platform_official,
                    "official_citation_rate": (
                        round(platform_official / platform_total, 4)
                        if platform_total > 0
                        else 0.0
                    ),
                    "unique_domains": int(stats.get("unique_domains", 0) or 0),
                    "top_domains": [
                        {
                            "domain": domain_item.get("domain", ""),
                            "count": int(domain_item.get("count", 0) or 0),
                        }
                        for domain_item in stats.get("top_domains", []) or []
                        if isinstance(domain_item, dict)
                    ],
                }

        return {
            "official_citation_rate": (
                round(official_citations / total_citations, 4)
                if total_citations > 0
                else 0.0
            ),
            "official_citations": official_citations,
            "total_citations": total_citations,
            "unique_domains": int(citation_analysis.get("unique_domains", 0) or 0),
            "brand_domain": citation_analysis.get("brand_domain", "") or "",
            "top_domains": top_domains,
            "platform_citation_stats": platform_citation_stats,
            "note": "官网引用率口径为官网引用次数 / 总引用次数。",
        }

    def _fallback_summary_metrics(self, data: dict[str, Any]) -> dict[str, Any]:
        """Fallback V2 summary metrics from legacy metrics when new fields are absent."""
        # Compatibility mode must not fabricate scenario-level numbers.
        # Returning None here lets the V2 UI render explicit empty states instead of false zeros.
        metrics = self._extract_metrics(data) or {}
        source_overview = self._fallback_source_overview(data)
        mention_rate = float(metrics.get("mention_rate", 0) or 0)
        return {
            "brand_mention_rate": mention_rate,
            "official_citation_rate": float(
                source_overview.get("official_citation_rate", 0) or 0
            ),
            "platform_coverage_count": None,
            "platform_total_count": None,
            "scenario_total": None,
            "scenario_hit_count": None,
            "missing_high_value_scenario_count": None,
            "high_risk_scenario_count": None,
            "scenario_effective_rate": None,
            "status_summary": "当前缺少场景级聚合数据，以下为兼容模式下的概览。",
        }

    def _scenario_priority_rank(self, priority: str) -> int:
        order = {"high": 0, "medium": 1, "low": 2}
        return order.get(str(priority).lower(), 9)

    def _risk_rank(self, severity: str) -> int:
        order = {"high": 0, "medium": 1, "low": 2}
        return order.get(str(severity).lower(), 9)

    def _to_scenario_row_camel(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "scenarioId": row.get("scenario_id", ""),
            "scenarioLabel": row.get("scenario_label", ""),
            "scenarioPriority": row.get("scenario_priority", "medium"),
            "brandPresent": bool(row.get("brand_present", False)),
            "presentPlatforms": row.get("present_platforms", []) or [],
            "officialCitationPresent": bool(
                row.get("official_citation_present", False)
            ),
            "officialSourceDomains": row.get("official_source_domains", []) or [],
            "competitorsPresent": row.get("competitors_present", []) or [],
            "winnerBrands": row.get("winner_brands", []) or [],
            "battleStatus": row.get("battle_status", "missing"),
            "riskLevel": row.get("risk_level", "low"),
            "evidence": row.get("evidence", ""),
            "queryExamples": row.get("query_examples", []) or [],
            "actionHint": row.get("action_hint", ""),
            "confidence": row.get("confidence", 0),
        }

    def _to_competitor_battle_camel(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "competitor": row.get("competitor", ""),
            "sharedScenarios": int(row.get("shared_scenarios", 0) or 0),
            "competitorOnlyScenarios": int(
                row.get("competitor_only_scenarios", 0) or 0
            ),
            "brandOnlyScenarios": int(row.get("brand_only_scenarios", 0) or 0),
            "pressureLevel": row.get("pressure_level", "low"),
            "topConflictScenarios": row.get("top_conflict_scenarios", []) or [],
        }

    def _to_source_overview_camel(self, row: dict[str, Any]) -> dict[str, Any]:
        platform_stats = row.get("platform_citation_stats", {}) or {}
        return {
            "officialCitationRate": float(row.get("official_citation_rate", 0) or 0),
            "officialCitations": int(row.get("official_citations", 0) or 0),
            "totalCitations": int(row.get("total_citations", 0) or 0),
            "uniqueDomains": int(row.get("unique_domains", 0) or 0),
            "brandDomain": row.get("brand_domain", "") or "",
            "topDomains": [
                {
                    "domain": item.get("domain", ""),
                    "count": int(item.get("count", 0) or 0),
                    "share": float(item.get("share", 0) or 0),
                    "isOfficial": bool(item.get("is_official", False)),
                }
                for item in row.get("top_domains", []) or []
                if isinstance(item, dict)
            ],
            "platformCitationStats": {
                platform: {
                    "totalCitations": int(stats.get("total_citations", 0) or 0),
                    "officialCitations": int(stats.get("official_citations", 0) or 0),
                    "officialCitationRate": float(
                        stats.get("official_citation_rate", 0) or 0
                    ),
                    "uniqueDomains": int(stats.get("unique_domains", 0) or 0),
                    "topDomains": [
                        {
                            "domain": domain_item.get("domain", ""),
                            "count": int(domain_item.get("count", 0) or 0),
                        }
                        for domain_item in stats.get("top_domains", []) or []
                        if isinstance(domain_item, dict)
                    ],
                }
                for platform, stats in platform_stats.items()
                if isinstance(stats, dict)
            },
            "note": row.get("note", "") or "",
        }

    def _to_risk_camel(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "riskId": row.get("risk_id", ""),
            "riskType": row.get("risk_type", ""),
            "scenarioId": row.get("scenario_id", ""),
            "scenarioLabel": row.get("scenario_label", ""),
            "severity": row.get("severity", "low"),
            "reason": row.get("reason", ""),
            "evidence": row.get("evidence", ""),
            "mitigationHint": row.get("mitigation_hint", ""),
        }

    def _to_action_camel(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "priority": row.get("priority", 3),
            "scenarioId": row.get("scenario_id", ""),
            "scenarioLabel": row.get("scenario_label", ""),
            "action": row.get("action", ""),
            "target": row.get("target", ""),
            "relatedCompetitors": row.get("related_competitors", []) or [],
            "ownerHint": row.get("owner_hint", ""),
            "expectedImpact": row.get("expected_impact", ""),
            "difficulty": row.get("difficulty", "medium"),
        }

    def _build_competitor_matrix_rows(
        self,
        scenario_matrix: list[dict[str, Any]],
        competitors: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        top_competitors = [
            item.get("competitor", "")
            for item in sorted(
                competitors,
                key=lambda row: (
                    self._risk_rank(
                        "high" if row.get("pressure_level") == "high" else "medium"
                    ),
                    -(int(row.get("competitor_only_scenarios", 0) or 0)),
                ),
            )
            if item.get("competitor")
        ][:5]

        rows = []
        for scenario in scenario_matrix:
            brand_state = "absent"
            if scenario.get("brand_present"):
                brand_state = (
                    "win"
                    if scenario.get("battle_status") in {"advantage", "defend"}
                    else "present"
                )

            brand_states = {
                "本品牌": {
                    "state": brand_state,
                    "officialCited": bool(
                        scenario.get("official_citation_present", False)
                    ),
                }
            }
            competitors_present = scenario.get("competitors_present", []) or []
            winner_brands = scenario.get("winner_brands", []) or []
            for competitor_name in top_competitors:
                if competitor_name in competitors_present:
                    state = "win" if competitor_name in winner_brands else "present"
                else:
                    state = "absent"
                brand_states[competitor_name] = {
                    "state": state,
                    "officialCited": False,
                }

            rows.append(
                {
                    "scenarioId": scenario.get("scenario_id", ""),
                    "scenarioLabel": scenario.get("scenario_label", ""),
                    "scenarioPriority": scenario.get("scenario_priority", "medium"),
                    "winnerBrand": (scenario.get("winner_brands", []) or [""])[0],
                    "battleStatus": scenario.get("battle_status", "missing"),
                    "recommendedFocus": scenario.get("action_hint", ""),
                    "brandStates": brand_states,
                }
            )
        return rows

    async def get_overview(
        self, brand_id: str | None, date_range: str
    ) -> dict[str, Any]:
        """Get KPI overview: visibility, mention rate, SOV."""
        outputs = await self._get_all_outputs(brand_id=brand_id)

        # Try to find metrics in any output
        metrics = None
        for output in outputs:
            metrics = self._extract_metrics(output)
            if metrics:
                break

        if not metrics:
            return {
                "kpi": {
                    "brandVisibility": None,
                    "mentionRate": None,
                    "shareOfVoice": None,
                    "visibilityTrend": None,
                    "mentionTrend": None,
                    "sovTrend": None,
                }
            }

        bwvs = metrics.get("bwvs_index", 0)
        mention_rate = metrics.get("mention_rate", 0)
        # SOV can be derived from platform breakdown or competitor comparison
        sov = metrics.get("share_of_voice", mention_rate * 0.8 if mention_rate else 0)

        kpi: dict[str, Any] = {
            "brandVisibility": bwvs,
            "mentionRate": mention_rate,
            "shareOfVoice": sov,
            "visibilityTrend": metrics.get("visibility_trend"),
            "mentionTrend": metrics.get("mention_trend"),
            "sovTrend": metrics.get("sov_trend"),
        }

        # BWVS v2 breakdown pass-through
        bwvs_breakdown = metrics.get("bwvs_breakdown")
        if bwvs_breakdown:
            kpi["bwvsBreakdown"] = bwvs_breakdown

        return {"kpi": kpi}

    async def get_visibility_data(
        self, brand_id: str | None, date_range: str
    ) -> dict[str, Any]:
        """Get visibility trend data.

        Prioritizes AnalysisSnapshot table (structured, fast).
        Falls back to Message.output_data parsing for legacy data.
        """
        visibility_points: list[dict[str, Any]] = []

        # 1) Prefer Snapshot table when brand_id is available
        if brand_id:
            try:
                from app.models.snapshot import AnalysisSnapshot, SnapshotStatus

                query = (
                    select(AnalysisSnapshot)
                    .where(
                        AnalysisSnapshot.entity_id == UUID(brand_id),
                        AnalysisSnapshot.status.in_(
                            [
                                SnapshotStatus.COMPLETED,
                                SnapshotStatus.PARTIAL,
                            ]
                        ),
                    )
                    .order_by(AnalysisSnapshot.created_at)
                    .limit(100)
                )
                result = await self.db.execute(query)
                snapshots = result.scalars().all()

                for snap in snapshots:
                    if snap.bwvs_index is not None:
                        visibility_points.append(
                            {
                                "date": snap.created_at.strftime("%Y-%m-%d"),
                                "score": round(snap.bwvs_index, 2),
                                "snapshot_id": str(snap.id),
                            }
                        )
            except Exception as snap_err:
                logger.warning("Failed to query snapshots for visibility: %s", snap_err)

        # 2) Fall back to legacy Message-based data if insufficient
        if len(visibility_points) < 2:
            outputs = await self._get_all_outputs(brand_id=brand_id)
            for output in outputs:
                metrics = self._extract_metrics(output)
                if metrics:
                    created_at = output.get("_created_at", "")
                    bwvs = metrics.get("bwvs_index", 0)
                    if bwvs and created_at:
                        visibility_points.append(
                            {
                                "date": created_at[:10],
                                "score": round(bwvs, 2),
                            }
                        )

        return {"visibility": visibility_points}

    async def get_platform_data(self, brand_id: str | None) -> dict[str, Any]:
        """Get platform comparison data from fetch results."""
        outputs = await self._get_all_outputs(brand_id=brand_id)

        platform_stats: dict[str, dict[str, Any]] = {}

        for output in outputs:
            # Check metrics for platform_breakdown
            metrics = self._extract_metrics(output)
            if metrics and "platform_breakdown" in metrics:
                for platform, stats in metrics["platform_breakdown"].items():
                    if platform not in platform_stats:
                        platform_stats[platform] = {
                            "platform": platform,
                            "mentionRate": 0,
                            "avgRanking": 0,
                            "sentiment": 0,
                            "totalQueries": 0,
                        }
                    ps = platform_stats[platform]
                    if isinstance(stats, dict):
                        # A5 _calculate_metrics uses total/mentions/success keys
                        total = stats.get("total", 0)
                        mentions = stats.get("mentions", 0)
                        ps["mentionRate"] = stats.get(
                            "mention_rate",
                            mentions / total if total > 0 else ps["mentionRate"],
                        )
                        ps["totalQueries"] = stats.get(
                            "total_queries", total or ps["totalQueries"]
                        )
                        ps["sentiment"] = stats.get("sentiment", ps["sentiment"])
                    elif isinstance(stats, (int, float)):
                        ps["mentionRate"] = stats

            # Also aggregate from fetch_results
            fetch_results = self._extract_fetch_results(output)
            for fr in fetch_results:
                for pr in fr.get("platform_results", []):
                    pname = pr.get("platform", "unknown")
                    if pname not in platform_stats:
                        platform_stats[pname] = {
                            "platform": pname,
                            "mentionRate": 0,
                            "avgRanking": 0,
                            "sentiment": 0,
                            "totalQueries": 0,
                            "_mentions": 0,
                            "_total": 0,
                        }
                    ps = platform_stats[pname]
                    ps["_total"] = ps.get("_total", 0) + 1
                    if pr.get("success") and pr.get("answer", {}).get("content"):
                        ps["_mentions"] = ps.get("_mentions", 0) + 1

        # Compute mention rates from raw counts
        platforms = []
        for ps in platform_stats.values():
            total = ps.pop("_total", 0)
            mentions = ps.pop("_mentions", 0)
            if total > 0 and ps["mentionRate"] == 0:
                ps["mentionRate"] = round(mentions / total, 3)
            ps["totalQueries"] = ps.get("totalQueries", 0) or total
            platforms.append(ps)

        return {"platforms": platforms}

    async def get_source_data(self, brand_id: str | None) -> dict[str, Any]:
        """Get source distribution data from fetch results citations."""
        outputs = await self._get_all_outputs(brand_id=brand_id)

        source_counts: dict[str, int] = {}
        total = 0

        for output in outputs:
            fetch_results = self._extract_fetch_results(output)
            for fr in fetch_results:
                results_list = fr.get(
                    "platform_results", [fr] if "platform" in fr else []
                )
                for pr in results_list:
                    citations = pr.get("citations", [])
                    for citation in citations:
                        source = (
                            citation.get("domain")
                            or citation.get("source")
                            or citation.get("url", "unknown")
                        )
                        # Extract domain from URL
                        if source.startswith("http"):
                            source = extract_domain(source) or source
                        source_counts[source] = source_counts.get(source, 0) + 1
                        total += 1

        sources = []
        for source, count in sorted(source_counts.items(), key=lambda x: -x[1])[:20]:
            sources.append(
                {
                    "source": source,
                    "count": count,
                    "percentage": round(count / total * 100, 1) if total > 0 else 0,
                }
            )

        return {"sources": sources}

    async def get_aeo_metrics(self, brand_id: str | None) -> dict[str, Any]:
        """Get legacy metric cards using current product-facing wording."""
        outputs = await self._get_all_outputs(brand_id=brand_id)

        def inverse_status(
            value: int | float | None, good: float, warning: float
        ) -> str:
            if value is None:
                return "warning"
            if value <= good:
                return "good"
            if value <= warning:
                return "warning"
            return "poor"

        aeo_metrics: list[dict[str, Any]] = []
        for output in outputs:
            payload = self._extract_v2_payload(output)
            summary_metrics = payload.get("summary_metrics", {})
            if not isinstance(summary_metrics, dict) or not summary_metrics:
                summary_metrics = self._fallback_summary_metrics(output)

            source_overview = payload.get("source_overview", {})
            if not isinstance(source_overview, dict) or not source_overview:
                source_overview = self._fallback_source_overview(output)

            mention_rate = summary_metrics.get("brand_mention_rate")
            official_citation_rate = source_overview.get(
                "official_citation_rate",
                summary_metrics.get("official_citation_rate"),
            )
            scenario_hit_count = summary_metrics.get("scenario_hit_count")
            missing_count = summary_metrics.get("missing_high_value_scenario_count")
            high_risk_count = summary_metrics.get("high_risk_scenario_count")

            if mention_rate is not None:
                aeo_metrics.append(
                    {
                        "metric": "品牌提及率",
                        "value": round(float(mention_rate) * 100, 1),
                        "benchmark": 30.0,
                        "status": _aeo_status(float(mention_rate), "mention_rate"),
                    }
                )

            if official_citation_rate is not None:
                citation_rate = float(official_citation_rate)
                aeo_metrics.append(
                    {
                        "metric": "官网引用率",
                        "value": round(citation_rate * 100, 1),
                        "benchmark": 20.0,
                        "status": (
                            "good"
                            if citation_rate >= 0.20
                            else "warning" if citation_rate >= 0.08 else "poor"
                        ),
                    }
                )

            if scenario_hit_count is not None:
                hit_count = int(scenario_hit_count)
                aeo_metrics.append(
                    {
                        "metric": "有效场景数",
                        "value": hit_count,
                        "benchmark": 5,
                        "status": (
                            "good"
                            if hit_count >= 5
                            else "warning" if hit_count >= 2 else "poor"
                        ),
                    }
                )

            if missing_count is not None:
                missing = int(missing_count)
                aeo_metrics.append(
                    {
                        "metric": "缺席高价值场景",
                        "value": missing,
                        "benchmark": 2,
                        "status": inverse_status(missing, good=1, warning=3),
                    }
                )

            if high_risk_count is not None:
                high_risk = int(high_risk_count)
                aeo_metrics.append(
                    {
                        "metric": "高风险场景",
                        "value": high_risk,
                        "benchmark": 1,
                        "status": inverse_status(high_risk, good=0, warning=2),
                    }
                )

            if aeo_metrics:
                break

        return {"aeoMetrics": aeo_metrics}

    async def get_sentiment_data(self, brand_id: str | None) -> dict[str, Any]:
        """Get sentiment analysis data (deprecated - returns empty array)."""
        # Sentiment analysis feature removed as per product decision
        return {"sentiment": []}

    async def get_competitor_data(self, brand_id: str | None) -> dict[str, Any]:
        """Get competitor comparison data from analysis results."""
        outputs = await self._get_all_outputs(brand_id=brand_id)

        competitors = []
        for output in outputs:
            comp_list = self._extract_competitors(output)
            if comp_list:
                for comp in comp_list:
                    competitors.append(
                        {
                            "name": comp.get("name", "Unknown"),
                            "visibility": comp.get("relevance_score", 0),
                            "mentionRate": comp.get("mention_rate", 0),
                            "avgRanking": comp.get("avg_ranking", 0),
                            "sentiment": max(0, (comp.get("sentiment", 0) + 1) / 2),
                        }
                    )
                break

            # Also check report for competitor mentions
            report = self._extract_report(output)
            if report and "competitors" in report:
                for comp in report["competitors"]:
                    if isinstance(comp, dict):
                        competitors.append(
                            {
                                "name": comp.get("name", "Unknown"),
                                "visibility": comp.get("visibility", 0),
                                "mentionRate": comp.get("mention_rate", 0),
                                "avgRanking": comp.get("avg_ranking", 0),
                                "sentiment": max(0, (comp.get("sentiment", 0) + 1) / 2),
                            }
                        )
                break

        return {"competitors": competitors}

    async def get_overview_v2(
        self, brand_id: str | None, date_range: str
    ) -> dict[str, Any]:
        """Get Dashboard V2 overview data."""
        report_outputs = await self._get_report_like_outputs(brand_id=brand_id)
        current = report_outputs[0] if report_outputs else None
        previous = report_outputs[1] if len(report_outputs) > 1 else None

        if not current:
            return {
                "kpi": {
                    "brandMentionRate": None,
                    "officialCitationRate": None,
                    "effectiveScenarioCount": None,
                    "missingHighValueScenarioCount": None,
                    "highRiskScenarioCount": None,
                    "mentionRateTrend": None,
                    "officialCitationRateTrend": None,
                    "effectiveScenarioTrend": None,
                    "missingHighValueScenarioTrend": None,
                    "highRiskScenarioTrend": None,
                },
                "summary": {"statusSummary": ""},
                "topScenarios": [],
                "competitorPressure": [],
                "actionQueue": [],
            }

        current_payload = self._extract_v2_payload(current)
        current_summary = current_payload[
            "summary_metrics"
        ] or self._fallback_summary_metrics(current)
        current_scenarios = current_payload["scenario_matrix"] or []
        current_competitors = current_payload["competitor_battles"] or []
        current_actions = current_payload["action_queue"] or []

        previous_summary: dict[str, Any] | None = None
        if previous:
            prev_payload = self._extract_v2_payload(previous)
            previous_summary = prev_payload[
                "summary_metrics"
            ] or self._fallback_summary_metrics(previous)

        def trend_value(key: str) -> int | float | None:
            if not previous_summary:
                return None
            current_value = current_summary.get(key)
            previous_value = previous_summary.get(key)
            if current_value is None or previous_value is None:
                return None
            return round(current_value - previous_value, 4)

        sorted_scenarios = sorted(
            [row for row in current_scenarios if isinstance(row, dict)],
            key=lambda row: (
                self._scenario_priority_rank(
                    str(row.get("scenario_priority", "medium"))
                ),
                self._risk_rank(str(row.get("risk_level", "low"))),
                str(row.get("scenario_label", "")),
            ),
        )
        sorted_competitors = sorted(
            [row for row in current_competitors if isinstance(row, dict)],
            key=lambda row: (
                self._risk_rank(
                    "high" if row.get("pressure_level") == "high" else "medium"
                ),
                -(int(row.get("competitor_only_scenarios", 0) or 0)),
                str(row.get("competitor", "")),
            ),
        )
        sorted_actions = sorted(
            [row for row in current_actions if isinstance(row, dict)],
            key=lambda row: (
                int(row.get("priority", 3) or 3),
                str(row.get("scenario_label", "")),
            ),
        )

        return {
            "kpi": {
                "brandMentionRate": current_summary.get("brand_mention_rate"),
                "officialCitationRate": current_summary.get("official_citation_rate"),
                "effectiveScenarioCount": current_summary.get("scenario_hit_count"),
                "missingHighValueScenarioCount": current_summary.get(
                    "missing_high_value_scenario_count"
                ),
                "highRiskScenarioCount": current_summary.get(
                    "high_risk_scenario_count"
                ),
                "mentionRateTrend": trend_value("brand_mention_rate"),
                "officialCitationRateTrend": trend_value("official_citation_rate"),
                "effectiveScenarioTrend": trend_value("scenario_hit_count"),
                "missingHighValueScenarioTrend": trend_value(
                    "missing_high_value_scenario_count"
                ),
                "highRiskScenarioTrend": trend_value("high_risk_scenario_count"),
            },
            "summary": {
                "statusSummary": current_summary.get("status_summary", ""),
            },
            "topScenarios": [
                self._to_scenario_row_camel(row) for row in sorted_scenarios[:5]
            ],
            "competitorPressure": [
                self._to_competitor_battle_camel(row) for row in sorted_competitors[:5]
            ],
            "actionQueue": [self._to_action_camel(row) for row in sorted_actions[:5]],
        }

    async def get_scenarios_v2(self, brand_id: str | None) -> dict[str, Any]:
        """Get Dashboard V2 scenario table data."""
        report_outputs = await self._get_report_like_outputs(brand_id=brand_id)
        current = report_outputs[0] if report_outputs else None
        if not current:
            return {
                "scenarios": [],
                "total": 0,
                "filters": {
                    "priorities": ["high", "medium", "low"],
                    "riskLevels": ["high", "medium", "low"],
                    "battleStatuses": ["advantage", "defend", "contested", "missing"],
                    "platforms": ["deepseek", "kimi", "doubao", "hunyuan"],
                },
            }

        payload = self._extract_v2_payload(current)
        scenarios = [row for row in payload["scenario_matrix"] if isinstance(row, dict)]
        scenarios = sorted(
            scenarios,
            key=lambda row: (
                self._scenario_priority_rank(
                    str(row.get("scenario_priority", "medium"))
                ),
                self._risk_rank(str(row.get("risk_level", "low"))),
                str(row.get("scenario_label", "")),
            ),
        )
        platforms = sorted(
            {
                str(platform)
                for row in scenarios
                for platform in row.get("present_platforms", []) or []
                if platform
            }
        )
        return {
            "scenarios": [self._to_scenario_row_camel(row) for row in scenarios],
            "total": len(scenarios),
            "filters": {
                "priorities": ["high", "medium", "low"],
                "riskLevels": ["high", "medium", "low"],
                "battleStatuses": ["advantage", "defend", "contested", "missing"],
                "platforms": platforms or ["deepseek", "kimi", "doubao", "hunyuan"],
            },
        }

    async def get_competitor_battles_v2(self, brand_id: str | None) -> dict[str, Any]:
        """Get Dashboard V2 competitor battle data."""
        report_outputs = await self._get_report_like_outputs(brand_id=brand_id)
        current = report_outputs[0] if report_outputs else None
        if not current:
            return {"competitors": [], "scenarioMatrix": []}

        payload = self._extract_v2_payload(current)
        competitors = [
            row for row in payload["competitor_battles"] if isinstance(row, dict)
        ]
        competitors = sorted(
            competitors,
            key=lambda row: (
                self._risk_rank(
                    "high" if row.get("pressure_level") == "high" else "medium"
                ),
                -(int(row.get("competitor_only_scenarios", 0) or 0)),
                str(row.get("competitor", "")),
            ),
        )
        scenarios = [row for row in payload["scenario_matrix"] if isinstance(row, dict)]
        scenarios = sorted(
            scenarios,
            key=lambda row: (
                self._scenario_priority_rank(
                    str(row.get("scenario_priority", "medium"))
                ),
                self._risk_rank(str(row.get("risk_level", "low"))),
                str(row.get("scenario_label", "")),
            ),
        )
        return {
            "competitors": [
                self._to_competitor_battle_camel(row) for row in competitors
            ],
            "scenarioMatrix": self._build_competitor_matrix_rows(
                scenarios, competitors
            ),
        }

    async def get_sources_v2(self, brand_id: str | None) -> dict[str, Any]:
        """Get Dashboard V2 source overview."""
        report_outputs = await self._get_report_like_outputs(brand_id=brand_id)
        current = report_outputs[0] if report_outputs else None
        if not current:
            return {"sourceOverview": {}}

        payload = self._extract_v2_payload(current)
        source_overview = payload["source_overview"] or self._fallback_source_overview(
            current
        )
        return {"sourceOverview": self._to_source_overview_camel(source_overview)}

    async def get_risks_actions_v2(self, brand_id: str | None) -> dict[str, Any]:
        """Get Dashboard V2 risks and action queue."""
        report_outputs = await self._get_report_like_outputs(brand_id=brand_id)
        current = report_outputs[0] if report_outputs else None
        if not current:
            return {"risks": [], "actionQueue": []}

        payload = self._extract_v2_payload(current)
        risks = [row for row in payload["risk_map"] if isinstance(row, dict)]
        actions = [row for row in payload["action_queue"] if isinstance(row, dict)]
        risks = sorted(
            risks,
            key=lambda row: (
                self._risk_rank(str(row.get("severity", "low"))),
                str(row.get("scenario_label", "")),
            ),
        )
        actions = sorted(
            actions,
            key=lambda row: (
                int(row.get("priority", 3) or 3),
                str(row.get("scenario_label", "")),
            ),
        )
        return {
            "risks": [self._to_risk_camel(row) for row in risks],
            "actionQueue": [self._to_action_camel(row) for row in actions],
        }

    async def _get_dashboard_monitoring_plan(
        self,
        *,
        brand_id: str | None,
        monitor_mode: str | None,
    ) -> dict[str, Any] | None:
        if not brand_id or self.viewer is None:
            return None
        try:
            brand_uuid = UUID(brand_id)
        except (ValueError, AttributeError):
            return None
        try:
            service = MonitoringPlanService(self.db)
            normalized_mode = (
                self._normalize_dashboard_monitor_mode(monitor_mode) or "panorama"
            )
            active_schedule = await self._get_dashboard_active_schedule(
                brand_uuid=brand_uuid,
                monitor_mode=normalized_mode,
            )
            plan_summary = None
            try:
                plan = await service.get_entity_plan(
                    user_id=self.viewer.id,
                    entity_id=brand_uuid,
                    monitor_mode=normalized_mode,
                )
                plan_summary = (
                    await service.plan_to_dict(plan) if plan is not None else None
                )
            except Exception as exc:
                logger.warning(
                    "[Dashboard] Failed to load monitoring plan detail: %s",
                    exc,
                )
            schedule_summary = self._dashboard_monitoring_plan_from_schedule(
                active_schedule,
                fallback_plan=plan_summary,
            )
            if self._dashboard_monitoring_plan_is_complete(schedule_summary):
                return schedule_summary
            return plan_summary
        except Exception as exc:
            logger.warning("[Dashboard] Failed to load monitoring plan: %s", exc)
            return None

    async def _get_dashboard_active_schedule(
        self,
        *,
        brand_uuid: UUID,
        monitor_mode: str,
    ) -> MonitoringSchedule | None:
        if self.viewer is None:
            return None
        result = await self.db.execute(
            select(MonitoringSchedule)
            .where(
                AccessScopeService.schedule_visibility_filter(self.viewer),
                MonitoringSchedule.entity_id == brand_uuid,
                MonitoringSchedule.monitor_mode == monitor_mode,
                MonitoringSchedule.status == ScheduleStatus.ACTIVE,
            )
            .order_by(desc(MonitoringSchedule.updated_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _dashboard_monitoring_plan_is_complete(
        monitoring_plan: dict[str, Any] | None,
    ) -> bool:
        if not monitoring_plan:
            return False
        plan_status = str(monitoring_plan.get("status") or "").strip().lower()
        question_count = int(monitoring_plan.get("question_count") or 0)
        endpoint_ids = monitoring_plan.get("endpoint_ids") or []
        return bool(
            plan_status == "active"
            and question_count > 0
            and isinstance(endpoint_ids, list)
            and len(endpoint_ids) > 0
        )

    @staticmethod
    def _dashboard_endpoint_ids_from_schedule(
        schedule: MonitoringSchedule,
    ) -> list[str]:
        endpoint_ids = [
            str(item).strip()
            for item in schedule.endpoint_ids or []
            if str(item).strip() in ENDPOINT_REGISTRY
        ]
        if endpoint_ids:
            return endpoint_ids

        platform_endpoint_map = {
            "doubao": "doubao_api",
            "yuanbao": "yuanbao_api",
            "hunyuan": "yuanbao_api",
            "kimi": "kimi_api",
            "deepseek": "deepseek_browser",
        }
        normalized: list[str] = []
        for raw_platform in schedule.platforms or []:
            platform = str(raw_platform or "").strip().lower()
            endpoint_id = platform_endpoint_map.get(platform)
            if endpoint_id and endpoint_id not in normalized:
                normalized.append(endpoint_id)
        return normalized

    def _dashboard_monitoring_plan_from_schedule(
        self,
        schedule: MonitoringSchedule | None,
        *,
        fallback_plan: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if schedule is None:
            return None
        baseline = (
            schedule.baseline_data
            if isinstance(schedule.baseline_data, dict)
            else {}
        )
        questions = baseline.get("questions")
        question_count = len(questions) if isinstance(questions, list) else 0
        endpoint_ids = self._dashboard_endpoint_ids_from_schedule(schedule)
        question_set_ids = [
            str(item)
            for item in (
                schedule.question_set_ids
                or (fallback_plan or {}).get("question_set_ids")
                or []
            )
            if str(item).strip()
        ]
        monitor_mode = (
            self._normalize_dashboard_monitor_mode(schedule.monitor_mode)
            or self._normalize_dashboard_monitor_mode(
                (fallback_plan or {}).get("monitor_mode")
            )
            or "panorama"
        )
        default_question_set_label = (
            "用户场景问题集" if monitor_mode == "scenario" else "品牌全景问题集"
        )
        plan_id = (
            str(schedule.monitoring_plan_id) if schedule.monitoring_plan_id else ""
        )
        return {
            "id": plan_id or f"schedule:{schedule.id}",
            "user_id": str(schedule.user_id),
            "entity_id": str(schedule.entity_id),
            "monitor_mode": monitor_mode,
            "status": "active",
            "title": (fallback_plan or {}).get("title") or "自动监测计划",
            "question_set_ids": question_set_ids,
            "question_set_label": (fallback_plan or {}).get("question_set_label")
            or default_question_set_label,
            "question_count": question_count,
            "endpoint_ids": endpoint_ids,
            "endpoint_labels": MonitoringPlanService.endpoint_ids_to_labels(
                endpoint_ids
            ),
            "run_policy": schedule.run_policy or "quick",
            "frequency": schedule.frequency.value if schedule.frequency else "weekly",
            "preferred_hour": schedule.preferred_hour,
            "timezone": schedule.timezone,
            "schedule_id": str(schedule.id),
            "schedule_status": schedule.status.value if schedule.status else "active",
            "created_at": schedule.created_at.isoformat(),
            "updated_at": schedule.updated_at.isoformat(),
        }

    async def get_dashboard_home_v2(
        self,
        brand_id: str | None,
        monitor_mode: str | None = None,
        date_range: str | None = None,
    ) -> dict[str, Any]:
        """Get Dashboard homepage summary data with period Snapshot aggregation."""
        normalized_monitor_mode = self._normalize_dashboard_monitor_mode(monitor_mode)
        date_range_days = self._dashboard_date_range_days(date_range)
        monitoring_plan = await self._get_dashboard_monitoring_plan(
            brand_id=brand_id,
            monitor_mode=normalized_monitor_mode,
        )
        recent_issue = await self._get_recent_monitoring_issue(
            brand_id=brand_id,
            monitor_mode=normalized_monitor_mode,
        )
        period_snapshots = await self._get_dashboard_snapshots(
            brand_id=brand_id,
            monitor_mode=normalized_monitor_mode,
            date_range_days=date_range_days,
        )
        period_summary = self._period_summary_from_snapshots(
            period_snapshots,
            date_range_days=date_range_days,
        )
        period_rollup = self._dashboard_period_rollup_from_snapshots(period_snapshots)
        latest_period_snapshot = period_snapshots[-1] if period_snapshots else None
        current = (
            self._snapshot_to_report_payload(latest_period_snapshot)
            if latest_period_snapshot
            else None
        )
        if current is None:
            report_outputs = await self._get_report_like_outputs(
                brand_id=brand_id,
                monitor_mode=normalized_monitor_mode,
            )
            latest_output = report_outputs[0] if report_outputs else None
            latest_snapshot = await self._get_latest_snapshot_report_source(
                brand_id=brand_id,
                monitor_mode=normalized_monitor_mode,
            )
            current = self._select_latest_home_source(latest_output, latest_snapshot)
        if not period_snapshots:
            period_summary = self._empty_period_summary(date_range_days)
        if not current:
            return self._augment_home_with_period_context(
                {
                "summary": {"headline": "暂无最近分析"},
                "latestReport": {
                    "title": "暂无最新报告",
                    "subtitle": "",
                    "reportKind": None,
                    "reportKindLabel": None,
                    "sessionId": "",
                    "artifactId": "",
                    "outputId": "",
                    "createdAt": "",
                    "actionLabel": "打开报告",
                },
                "metrics": [
                    {
                        "id": "mention_rate",
                        "label": "提及率",
                        "value": None,
                        "format": "percent",
                        "subtitle": "",
                    },
                    {
                        "id": "brand_rank",
                        "label": "排名",
                        "value": None,
                        "format": "rank",
                        "subtitle": "",
                    },
                    {
                        "id": "official_conversion_rate",
                        "label": "官网转化率",
                        "value": None,
                        "format": "percent",
                        "subtitle": "",
                    },
                ],
                "citationDistribution": {
                    "summary": "",
                    "sourceTypes": [],
                    "topDomains": [],
                },
                "relatedQuestions": {
                    "summary": "",
                    "items": [],
                },
                },
                monitoring_plan=monitoring_plan,
                period_summary=period_summary,
                recent_issue=recent_issue,
                period_rollup=period_rollup,
            )

        projection_home = self._build_dashboard_home_from_projection(current)
        if projection_home is not None:
            return self._augment_home_with_period_context(
                projection_home,
                monitoring_plan=monitoring_plan,
                period_summary=period_summary,
                recent_issue=recent_issue,
                period_rollup=period_rollup,
            )

        payload = self._extract_v2_payload(current)
        summary = payload.get("summary_metrics") or self._fallback_summary_metrics(
            current
        )
        source_overview = payload.get(
            "source_overview"
        ) or self._fallback_source_overview(current)
        scenario_matrix = [
            row for row in payload.get("scenario_matrix", []) if isinstance(row, dict)
        ]
        competitor_battles = [
            row
            for row in payload.get("competitor_battles", [])
            if isinstance(row, dict)
        ]
        mention_payload = payload.get("mention_sentiment_analysis") or {}
        brand_payload = (
            mention_payload.get("brand", {})
            if isinstance(mention_payload, dict)
            else {}
        )
        competitor_payloads = (
            mention_payload.get("competitors", [])
            if isinstance(mention_payload, dict)
            else []
        )
        metrics = self._extract_metrics(current) or {}

        def normalize_sentiment_summary(raw: Any) -> dict[str, int]:
            raw = raw if isinstance(raw, dict) else {}
            return {
                "positive": int(raw.get("positive", 0) or 0),
                "neutral": int(raw.get("neutral", 0) or 0),
                "negative": int(raw.get("negative", 0) or 0),
            }

        def scenario_insight_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
            return [
                {
                    "scenarioId": row.get("scenario_id", ""),
                    "scenarioLabel": row.get("scenario_label", ""),
                    "reason": row.get("evidence")
                    or row.get("action_hint")
                    or "需要继续观察该场景。",
                    "platforms": row.get("present_platforms", []) or [],
                }
                for row in rows
            ]

        brand_summary = normalize_sentiment_summary(brand_payload.get("summary"))
        brand_mentions = [
            row for row in brand_payload.get("items", []) if isinstance(row, dict)
        ]
        brand_mentions = sorted(
            brand_mentions,
            key=lambda row: (
                self._risk_rank(
                    str(
                        next(
                            (
                                item.get("risk_level", "medium")
                                for item in scenario_matrix
                                if item.get("scenario_id") == row.get("scenario_id")
                            ),
                            "medium",
                        )
                    )
                ),
                str(row.get("scenario_label", "")),
            ),
        )

        legacy_mention_board = self._build_legacy_mention_board(
            current, summary.get("brand_mention_rate")
        )
        if not brand_mentions:
            brand_mentions = legacy_mention_board["report"]["brandMentions"]

        normalized_mentions = []
        for item in brand_mentions:
            if not isinstance(item, dict):
                continue
            scenario_id = str(item.get("scenario_id", item.get("scenarioId", "")) or "")
            scenario_label = str(
                item.get("scenario_label", item.get("scenarioLabel", "")) or ""
            )
            platform = str(item.get("platform", "") or "")
            sentiment = str(item.get("sentiment", "neutral") or "neutral")
            evidence = str(item.get("evidence", "") or "")
            citation_domains = (
                item.get("citation_domains", item.get("citationDomains", [])) or []
            )
            citation_titles = (
                item.get("citation_titles", item.get("citationTitles", [])) or []
            )
            citation_urls = (
                item.get("citation_urls", item.get("citationUrls", [])) or []
            )
            official_present = bool(
                item.get(
                    "official_citation_present",
                    item.get("officialCitationPresent", False),
                )
            )
            if not scenario_id and not scenario_label:
                continue
            normalized_mentions.append(
                {
                    "scenario_id": scenario_id,
                    "scenario_label": scenario_label,
                    "platform": platform,
                    "sentiment": sentiment,
                    "evidence": evidence,
                    "citation_domains": [
                        str(domain) for domain in citation_domains if domain
                    ],
                    "citation_titles": [
                        str(title) for title in citation_titles if title
                    ],
                    "citation_urls": [str(url) for url in citation_urls if url],
                    "official_citation_present": official_present,
                }
            )
        brand_mentions = normalized_mentions
        brand_summary = self._sentiment_summary_from_mentions(brand_mentions)

        top_competitors = sorted(
            competitor_battles,
            key=lambda row: (
                self._risk_rank(
                    "high" if row.get("pressure_level") == "high" else "medium"
                ),
                -(int(row.get("competitor_only_scenarios", 0) or 0)),
                str(row.get("competitor", "")),
            ),
        )[:3]
        if not top_competitors and legacy_mention_board["leadingCompetitors"]:
            top_competitors = [
                {
                    "competitor": row.get("competitor", ""),
                    "pressure_level": row.get("pressureLevel", "medium"),
                    "competitor_only_scenarios": row.get("competitorOnlyScenarios", 0),
                }
                for row in legacy_mention_board["leadingCompetitors"]
            ]

        competitor_summaries = []
        competitor_mentions: list[dict[str, Any]] = []
        for competitor in top_competitors:
            payload_row = next(
                (
                    item
                    for item in competitor_payloads
                    if isinstance(item, dict)
                    and str(item.get("competitor", ""))
                    == str(competitor.get("competitor", ""))
                ),
                {},
            )
            sentiment_summary = normalize_sentiment_summary(payload_row.get("summary"))
            competitor_summaries.append(
                {
                    "competitor": competitor.get("competitor", ""),
                    "pressureLevel": competitor.get("pressure_level", "medium"),
                    "competitorOnlyScenarios": int(
                        competitor.get("competitor_only_scenarios", 0) or 0
                    ),
                    "sentimentSummary": sentiment_summary,
                }
            )
            for item in payload_row.get("items", [])[:4]:
                if not isinstance(item, dict):
                    continue
                competitor_mentions.append(
                    {
                        "competitor": payload_row.get("competitor", ""),
                        "scenarioId": item.get("scenario_id", ""),
                        "scenarioLabel": item.get("scenario_label", ""),
                        "platform": item.get("platform", ""),
                        "sentiment": item.get("sentiment", "neutral"),
                        "evidence": item.get("evidence", ""),
                        "citationDomains": item.get("citation_domains", []) or [],
                        "citationTitles": item.get("citation_titles", []) or [],
                        "officialCitationPresent": bool(
                            item.get("official_citation_present", False)
                        ),
                    }
                )
        if not competitor_summaries:
            competitor_summaries = legacy_mention_board["leadingCompetitors"]
        if not competitor_mentions:
            competitor_mentions = legacy_mention_board["report"]["competitorMentions"]

        mention_rate = summary.get("brand_mention_rate")
        if mention_rate is None:
            mention_rate = metrics.get("mention_rate")
        scenario_total = int(
            summary.get("scenario_total", len(scenario_matrix))
            or metrics.get("total_questions")
            or len(scenario_matrix)
            or 0
        )
        unique_brand_scenarios = {
            str(item.get("scenario_id") or item.get("scenario_label") or "")
            for item in brand_mentions
            if (item.get("scenario_id") or item.get("scenario_label"))
        }
        scenario_hit_count = len(unique_brand_scenarios)
        if unique_brand_scenarios and scenario_total > 0:
            mention_rate = round(len(unique_brand_scenarios) / scenario_total, 4)
        leading_competitor_name = (
            competitor_summaries[0]["competitor"]
            if competitor_summaries
            else "暂无明显竞品压力"
        )
        mention_headline = (
            f"品牌当前在 {scenario_hit_count}/{scenario_total or 0} 个场景进入回答，"
            f"正向提及 {brand_summary['positive']} 条，主要竞争压力来自 {leading_competitor_name}。"
        )

        cited_brand_mentions = [
            item
            for item in brand_mentions
            if (item.get("citation_domains") or item.get("citation_titles"))
        ]
        official_cases = [
            item
            for item in cited_brand_mentions
            if bool(item.get("official_citation_present", False))
        ]
        non_official_cases = [
            item
            for item in cited_brand_mentions
            if not bool(item.get("official_citation_present", False))
        ]

        def to_citation_case(item: dict[str, Any], is_official: bool) -> dict[str, Any]:
            return {
                "scenarioId": item.get("scenario_id", ""),
                "scenarioLabel": item.get("scenario_label", ""),
                "platform": item.get("platform", ""),
                "matchedAnswer": item.get("evidence", ""),
                "citationDomains": item.get("citation_domains", []) or [],
                "citationTitles": item.get("citation_titles", []) or [],
                "citationUrls": item.get("citation_urls", []) or [],
                "isOfficial": is_official,
                "aiceScore": item.get("aice_score"),
                "aiceDimensions": item.get("aice_dimensions"),
            }

        official_question_cases = [
            to_citation_case(item, True) for item in official_cases[:8]
        ]
        non_official_question_cases = [
            to_citation_case(item, False) for item in non_official_cases[:8]
        ]

        def unique_content_rows(
            items: list[dict[str, Any]], is_official: bool
        ) -> list[dict[str, Any]]:
            rows = []
            seen: set[tuple[str, str]] = set()
            for item in items:
                domains = item.get("citation_domains", []) or []
                titles = item.get("citation_titles", []) or []
                fallback_domain = domains[0] if domains else ""
                for title in titles or [""]:
                    key = (title or fallback_domain, fallback_domain)
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(
                        {
                            "title": title or fallback_domain or "未命名引用内容",
                            "domain": fallback_domain or None,
                            "isOfficial": is_official,
                        }
                    )
            return rows[:12]

        official_contents = unique_content_rows(official_cases, True)
        non_official_contents = unique_content_rows(non_official_cases, False)
        content_citation_rate = (
            (len(cited_brand_mentions) / len(brand_mentions))
            if brand_mentions
            else None
        )
        legacy_source_board = self._build_legacy_source_board(current, source_overview)
        if content_citation_rate is None or (
            content_citation_rate == 0 and legacy_source_board["citedAnswerCount"] > 0
        ):
            content_citation_rate = legacy_source_board["contentCitationRate"]
        if not official_question_cases:
            official_question_cases = legacy_source_board["report"]["officialCases"]
        if not non_official_question_cases:
            non_official_question_cases = legacy_source_board["report"][
                "nonOfficialCases"
            ]
        if not official_contents:
            official_contents = legacy_source_board["report"]["officialContents"]
        if not non_official_contents:
            non_official_contents = legacy_source_board["report"]["nonOfficialContents"]

        platform_stat_map = source_overview.get("platform_citation_stats", {}) or {}
        platform_rows = []
        for platform_name in sorted(
            {
                str(item.get("platform", "") or "")
                for item in brand_mentions
                if item.get("platform")
            }
        ):
            platform_mentions = [
                item
                for item in brand_mentions
                if str(item.get("platform", "") or "") == platform_name
            ]
            platform_cited = [
                item
                for item in platform_mentions
                if (item.get("citation_domains") or item.get("citation_titles"))
            ]
            stats = (
                platform_stat_map.get(platform_name, {})
                if isinstance(platform_stat_map, dict)
                else {}
            )
            platform_rows.append(
                {
                    "platform": platform_name,
                    "contentCitationRate": (
                        round(len(platform_cited) / len(platform_mentions), 4)
                        if platform_mentions
                        else 0.0
                    ),
                    "officialCitationRate": float(
                        stats.get("official_citation_rate", 0) or 0
                    ),
                    "topDomains": [
                        {
                            "domain": domain_item.get("domain", ""),
                            "count": int(domain_item.get("count", 0) or 0),
                        }
                        for domain_item in stats.get("top_domains", []) or []
                        if isinstance(domain_item, dict)
                    ],
                }
            )
        if not platform_rows:
            platform_rows = legacy_source_board["report"]["platformStats"]

        source_headline = (
            f"在 {len(brand_mentions)} 条提及品牌的回答里，有 {len(cited_brand_mentions)} 条引用了品牌相关内容，"
            f"其中 {len(official_cases)} 条来自官网，{len(non_official_cases)} 条来自第三方站点。"
        )
        if not cited_brand_mentions and legacy_source_board["headline"]:
            source_headline = legacy_source_board["headline"]

        platform_coverage_count = float(summary.get("platform_coverage_count") or 0)
        platform_total_count = float(
            summary.get("platform_total_count") or max(platform_coverage_count, 1) or 1
        )
        platform_coverage_rate = (
            min(1.0, platform_coverage_count / platform_total_count)
            if platform_total_count
            else 0.0
        )
        scenario_effective_rate = summary.get("scenario_effective_rate")
        if scenario_effective_rate is None:
            scenario_effective_rate = (
                (scenario_hit_count / scenario_total) if scenario_total else 0.0
            )

        high_priority_rows = [
            row
            for row in scenario_matrix
            if str(row.get("scenario_priority", "medium")) == "high"
        ]
        high_priority_hits = [
            row for row in high_priority_rows if bool(row.get("brand_present", False))
        ]
        audience_coverage_rate = (
            (len(high_priority_hits) / len(high_priority_rows))
            if high_priority_rows
            else platform_coverage_rate
        )

        sentiment_total = (
            brand_summary["positive"]
            + brand_summary["neutral"]
            + brand_summary["negative"]
        )
        positive_rate = (
            (brand_summary["positive"] / sentiment_total) if sentiment_total else 0.0
        )
        missing_count = float(summary.get("missing_high_value_scenario_count") or 0)
        high_risk_count = float(summary.get("high_risk_scenario_count") or 0)
        risk_control_score = max(
            0.0,
            min(100.0, 100.0 - min(100.0, missing_count * 12 + high_risk_count * 18)),
        )

        radar_dimensions = [
            {
                "id": "industry_influence",
                "label": "行业影响",
                "score": round(
                    max(
                        0.0,
                        min(
                            100.0,
                            (float(mention_rate or 0) * 100 * 0.7)
                            + (platform_coverage_rate * 100 * 0.3),
                        ),
                    )
                ),
                "summary": "基于品牌提及率和平台覆盖估算行业可见度。",
            },
            {
                "id": "audience_coverage",
                "label": "人群覆盖",
                "score": round(max(0.0, min(100.0, audience_coverage_rate * 100))),
                "summary": "当前以高优先级场景覆盖和平台触达作为人群覆盖代理指标。",
            },
            {
                "id": "scenario_coverage",
                "label": "场景覆盖",
                "score": round(
                    max(0.0, min(100.0, float(scenario_effective_rate or 0) * 100))
                ),
                "summary": "反映品牌已进入回答的场景覆盖比例。",
            },
            {
                "id": "risk_control",
                "label": "风险控制",
                "score": round(risk_control_score),
                "summary": "根据高风险场景和缺席高价值场景反推风险控制表现。",
            },
            {
                "id": "positive_sentiment",
                "label": "积极情绪",
                "score": round(max(0.0, min(100.0, positive_rate * 100))),
                "summary": "反映品牌被提及时的正向情绪占比。",
            },
        ]
        if all(dimension["score"] == 0 for dimension in radar_dimensions):
            legacy_radar_board = self._build_legacy_radar_board(current, mention_rate)
            radar_dimensions = legacy_radar_board["dimensions"]
        sorted_dimensions = sorted(radar_dimensions, key=lambda row: row["score"])
        weakest_dimension = sorted_dimensions[0]["label"] if sorted_dimensions else ""
        strongest_dimension = (
            sorted_dimensions[-1]["label"] if sorted_dimensions else ""
        )
        radar_headline = (
            f"当前最大优势在 {strongest_dimension}，最大短板在 {weakest_dimension}。"
        )
        if not strongest_dimension and not weakest_dimension:
            legacy_radar_board = self._build_legacy_radar_board(current, mention_rate)
            strongest_dimension = legacy_radar_board["strongestDimension"]
            weakest_dimension = legacy_radar_board["weakestDimension"]
            radar_headline = legacy_radar_board["headline"]
            radar_dimensions = legacy_radar_board["dimensions"]

        summary_headline = (
            f"品牌提及已建立基础，但内容引用与风险控制仍需强化；"
            f"当前最值得优先查看的是 {leading_competitor_name} 带来的竞争压力与内容证据缺口。"
        )
        if not scenario_matrix and legacy_mention_board["headline"]:
            summary_headline = (
                f"当前首页使用兼容模式读取历史报告：提及率、内容引用与竞争压力已经可见，"
                f"建议优先查看 {leading_competitor_name} 的竞争问题和主要引用来源。"
            )

        home_payload = {
            "summary": {
                "headline": summary_headline,
            },
            "monitoringPlan": monitoring_plan,
            "mentionBoard": {
                "mentionRate": mention_rate,
                "headline": (
                    mention_headline
                    if brand_mentions
                    else legacy_mention_board["headline"]
                ),
                "sentimentSummary": brand_summary,
                "leadingCompetitors": competitor_summaries,
                "report": {
                    "brandMentions": [
                        {
                            "scenarioId": item.get("scenario_id", ""),
                            "scenarioLabel": item.get("scenario_label", ""),
                            "platform": item.get("platform", ""),
                            "sentiment": item.get("sentiment", "neutral"),
                            "evidence": item.get("evidence", ""),
                            "citationDomains": item.get("citation_domains", []) or [],
                            "citationTitles": item.get("citation_titles", []) or [],
                            "citationUrls": item.get("citation_urls", []) or [],
                            "officialCitationPresent": bool(
                                item.get("official_citation_present", False)
                            ),
                        }
                        for item in brand_mentions[:10]
                    ],
                    "competitorMentions": competitor_mentions[:12],
                    "strongScenarios": (
                        scenario_insight_rows(
                            [
                                row
                                for row in scenario_matrix
                                if bool(row.get("brand_present", False))
                                and str(row.get("battle_status", ""))
                                in {"advantage", "defend"}
                            ][:4]
                        )
                        if scenario_matrix
                        else legacy_mention_board["report"]["strongScenarios"]
                    ),
                    "weakScenarios": (
                        scenario_insight_rows(
                            [
                                row
                                for row in scenario_matrix
                                if str(row.get("battle_status", ""))
                                in {"missing", "contested"}
                            ][:6]
                        )
                        if scenario_matrix
                        else legacy_mention_board["report"]["weakScenarios"]
                    ),
                },
            },
            "sourceBoard": {
                "contentCitationRate": content_citation_rate,
                "citedAnswerCount": len(cited_brand_mentions)
                or legacy_source_board["citedAnswerCount"],
                "citedContentCount": len(official_contents) + len(non_official_contents)
                or legacy_source_board["citedContentCount"],
                "headline": source_headline,
                "report": {
                    "officialCases": official_question_cases,
                    "nonOfficialCases": non_official_question_cases,
                    "officialContents": official_contents,
                    "nonOfficialContents": non_official_contents,
                    "topDomains": [
                        {
                            "domain": item.get("domain", ""),
                            "count": int(item.get("count", 0) or 0),
                            "share": float(item.get("share", 0) or 0),
                            "isOfficial": bool(item.get("is_official", False)),
                        }
                        for item in source_overview.get("top_domains", []) or []
                        if isinstance(item, dict)
                    ]
                    or legacy_source_board["report"]["topDomains"],
                    "platformStats": platform_rows,
                },
            },
            "radarBoard": {
                "headline": radar_headline,
                "strongestDimension": strongest_dimension,
                "weakestDimension": weakest_dimension,
                "dimensions": radar_dimensions,
            },
            "monitoringEntry": {
                "title": "持续监测",
                "description": "持续追踪提及率、官网引用率和风险变化，及时发现异常波动。",
                "ctaLabel": "进入监测",
            },
        }
        return self._augment_home_with_period_context(
            home_payload,
            monitoring_plan=monitoring_plan,
            period_summary=period_summary,
            recent_issue=recent_issue,
            period_rollup=period_rollup,
        )
