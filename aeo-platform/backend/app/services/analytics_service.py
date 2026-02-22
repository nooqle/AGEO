"""Analytics service for Dashboard data aggregation.

Queries the database for analysis results and aggregates them into
dashboard-friendly formats (KPI, trends, platform breakdowns, etc.).

Data sources:
- Messages table: output_data JSON field from A5 OUTPUT messages
- LangGraph state: metrics, report, fetch_results, competitors (via checkpoint)
"""

import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.models.message import Message, MessageType, MessageRole
from app.models.session import Session
from app.core.utils import extract_domain

logger = logging.getLogger(__name__)

# AEO metric thresholds — configurable benchmarks for status evaluation
AEO_THRESHOLDS = {
    "bwvs_index": {"benchmark": 50.0, "good": 50.0, "warning": 30.0},
    "mention_rate": {"benchmark": 0.30, "good": 0.30, "warning": 0.15},
    "total_questions": {"benchmark": 50, "good": 50, "warning": 20},
    "total_mentions": {"benchmark": 15, "good": 15, "warning": 5},
}


def _aeo_status(value: float, metric_key: str) -> str:
    """Evaluate metric status based on configurable thresholds."""
    thresholds = AEO_THRESHOLDS.get(metric_key, {"good": 50, "warning": 30})
    if value >= thresholds["good"]:
        return "good"
    if value >= thresholds["warning"]:
        return "warning"
    return "poor"


class AnalyticsService:
    """Aggregates analysis data for the Dashboard."""

    def __init__(self, db: AsyncSession):
        self.db = db

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

    async def _get_all_outputs(self, brand_id: str | None = None) -> list[dict[str, Any]]:
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
                    data["_output_type"] = msg.output_type
                    data["_created_at"] = msg.created_at.isoformat() if msg.created_at else None
                    outputs.append(data)
                except (json.JSONDecodeError, TypeError):
                    continue
        return outputs

    def _extract_metrics(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Extract metrics from output data (supports nested structures)."""
        if "metrics" in data:
            return data["metrics"]
        if "bwvs_index" in data or "mention_rate" in data:
            return data
        return None

    def _extract_report(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Extract report from output data."""
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
        if "fetch_results_summary" in data and isinstance(data["fetch_results_summary"], list):
            return [{"platform_results": data["fetch_results_summary"]}]
        if "results" in data and isinstance(data["results"], list):
            return data["results"]
        return []

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
        platform_breakdown = metrics.get("platform_breakdown", {})
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
                        AnalysisSnapshot.status.in_([
                            SnapshotStatus.COMPLETED,
                            SnapshotStatus.PARTIAL,
                        ]),
                    )
                    .order_by(AnalysisSnapshot.created_at)
                    .limit(100)
                )
                result = await self.db.execute(query)
                snapshots = result.scalars().all()

                for snap in snapshots:
                    if snap.bwvs_index is not None:
                        visibility_points.append({
                            "date": snap.created_at.strftime("%Y-%m-%d"),
                            "score": round(snap.bwvs_index, 2),
                            "snapshot_id": str(snap.id),
                        })
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
                        visibility_points.append({
                            "date": created_at[:10],
                            "score": round(bwvs, 2),
                        })

        return {"visibility": visibility_points}

    async def get_platform_data(
        self, brand_id: str | None
    ) -> dict[str, Any]:
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
                        ps["mentionRate"] = stats.get("mention_rate", mentions / total if total > 0 else ps["mentionRate"])
                        ps["totalQueries"] = stats.get("total_queries", total or ps["totalQueries"])
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

    async def get_source_data(
        self, brand_id: str | None
    ) -> dict[str, Any]:
        """Get source distribution data from fetch results citations."""
        outputs = await self._get_all_outputs(brand_id=brand_id)

        source_counts: dict[str, int] = {}
        total = 0

        for output in outputs:
            fetch_results = self._extract_fetch_results(output)
            for fr in fetch_results:
                results_list = fr.get("platform_results", [fr] if "platform" in fr else [])
                for pr in results_list:
                    citations = pr.get("citations", [])
                    for citation in citations:
                        source = citation.get("domain") or citation.get("source") or citation.get("url", "unknown")
                        # Extract domain from URL
                        if source.startswith("http"):
                            source = extract_domain(source) or source
                        source_counts[source] = source_counts.get(source, 0) + 1
                        total += 1

        sources = []
        for source, count in sorted(source_counts.items(), key=lambda x: -x[1])[:20]:
            sources.append({
                "source": source,
                "count": count,
                "percentage": round(count / total * 100, 1) if total > 0 else 0,
            })

        return {"sources": sources}

    async def get_aeo_metrics(
        self, brand_id: str | None
    ) -> dict[str, Any]:
        """Get AEO performance metrics."""
        outputs = await self._get_all_outputs(brand_id=brand_id)

        aeo_metrics = []
        for output in outputs:
            metrics = self._extract_metrics(output)
            if not metrics:
                continue

            bwvs = metrics.get("bwvs_index", 0)
            mention_rate = metrics.get("mention_rate", 0)
            total_questions = metrics.get("total_questions", 0)
            total_mentions = metrics.get("total_mentions", 0)

            aeo_metrics = [
                {
                    "metric": "BWVS 指数",
                    "value": round(bwvs, 1),
                    "benchmark": AEO_THRESHOLDS["bwvs_index"]["benchmark"],
                    "status": _aeo_status(bwvs, "bwvs_index"),
                },
                {
                    "metric": "提及率",
                    "value": round(mention_rate * 100, 1),
                    "benchmark": AEO_THRESHOLDS["mention_rate"]["benchmark"] * 100,
                    "status": _aeo_status(mention_rate, "mention_rate"),
                },
                {
                    "metric": "总问题数",
                    "value": total_questions,
                    "benchmark": AEO_THRESHOLDS["total_questions"]["benchmark"],
                    "status": _aeo_status(total_questions, "total_questions"),
                },
                {
                    "metric": "总提及数",
                    "value": total_mentions,
                    "benchmark": AEO_THRESHOLDS["total_mentions"]["benchmark"],
                    "status": _aeo_status(total_mentions, "total_mentions"),
                },
            ]

            # Append BWVS v2 breakdown dimension metrics
            breakdown = metrics.get("bwvs_breakdown", {})
            if breakdown:
                aeo_metrics.extend([
                    {
                        "metric": "提及率得分",
                        "value": round(
                            breakdown.get("mention_score", 0), 1
                        ),
                        "benchmark": 60,
                        "status": _aeo_status(
                            breakdown.get("mention_score", 0), "bwvs_index"
                        ),
                        "weight": "40%",
                    },
                    {
                        "metric": "情感得分",
                        "value": round(
                            breakdown.get("sentiment_score", 50), 1
                        ),
                        "benchmark": 60,
                        "status": _aeo_status(
                            breakdown.get("sentiment_score", 50), "bwvs_index"
                        ),
                        "weight": "25%",
                    },
                    {
                        "metric": "平台覆盖度",
                        "value": round(
                            breakdown.get("coverage_score", 0), 1
                        ),
                        "benchmark": 75,
                        "status": _aeo_status(
                            breakdown.get("coverage_score", 0), "bwvs_index"
                        ),
                        "weight": "20%",
                    },
                    {
                        "metric": "引用质量",
                        "value": round(
                            breakdown.get("citation_score", 50), 1
                        ),
                        "benchmark": 50,
                        "status": _aeo_status(
                            breakdown.get("citation_score", 50), "bwvs_index"
                        ),
                        "weight": "15%",
                    },
                ])

            break  # Use first found metrics

        return {"aeoMetrics": aeo_metrics}

    async def get_sentiment_data(
        self, brand_id: str | None
    ) -> dict[str, Any]:
        """Get sentiment analysis data (deprecated - returns empty array)."""
        # Sentiment analysis feature removed as per product decision
        return {"sentiment": []}

    async def get_competitor_data(
        self, brand_id: str | None
    ) -> dict[str, Any]:
        """Get competitor comparison data from analysis results."""
        outputs = await self._get_all_outputs(brand_id=brand_id)

        competitors = []
        for output in outputs:
            comp_list = self._extract_competitors(output)
            if comp_list:
                for comp in comp_list:
                    competitors.append({
                        "name": comp.get("name", "Unknown"),
                        "visibility": comp.get("relevance_score", 0),
                        "mentionRate": comp.get("mention_rate", 0),
                        "avgRanking": comp.get("avg_ranking", 0),
                        "sentiment": max(0, (comp.get("sentiment", 0) + 1) / 2),
                    })
                break

            # Also check report for competitor mentions
            report = self._extract_report(output)
            if report and "competitors" in report:
                for comp in report["competitors"]:
                    if isinstance(comp, dict):
                        competitors.append({
                            "name": comp.get("name", "Unknown"),
                            "visibility": comp.get("visibility", 0),
                            "mentionRate": comp.get("mention_rate", 0),
                            "avgRanking": comp.get("avg_ranking", 0),
                            "sentiment": max(0, (comp.get("sentiment", 0) + 1) / 2),
                        })
                break

        return {"competitors": competitors}
