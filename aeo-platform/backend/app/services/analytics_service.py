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
        if "metrics_raw" in data and isinstance(data["metrics_raw"], dict):
            return data["metrics_raw"]
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

    async def _get_report_like_outputs(
        self, brand_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get recent report artifacts only, ordered from newest to oldest."""
        outputs = await self._get_all_outputs(brand_id=brand_id)
        return [
            output for output in outputs
            if output.get("_output_type") in {"report", "report_baseline"}
        ]

    def _extract_v2_payload(self, data: dict[str, Any]) -> dict[str, Any]:
        """Extract V2 contract fields from artifact, report_data, or metrics_raw."""
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
            "citation_analysis": data.get("citation_analysis")
            or nested_report.get("citation_analysis")
            or metrics_raw.get("citation_analysis")
            or {},
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
            top_domains.append({
                "domain": item.get("domain", ""),
                "count": int(item.get("count", 0) or 0),
                "share": round(max(0.0, min(1.0, float(share or 0))), 4),
                "is_official": bool(item.get("is_official", False)),
            })

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
                    "official_citation_rate": round(platform_official / platform_total, 4) if platform_total > 0 else 0.0,
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
            "official_citation_rate": round(official_citations / total_citations, 4) if total_citations > 0 else 0.0,
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
            "official_citation_rate": float(source_overview.get("official_citation_rate", 0) or 0),
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
            "officialCitationPresent": bool(row.get("official_citation_present", False)),
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
            "competitorOnlyScenarios": int(row.get("competitor_only_scenarios", 0) or 0),
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
                    "officialCitationRate": float(stats.get("official_citation_rate", 0) or 0),
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
                    self._risk_rank("high" if row.get("pressure_level") == "high" else "medium"),
                    -(int(row.get("competitor_only_scenarios", 0) or 0)),
                ),
            )
            if item.get("competitor")
        ][:5]

        rows = []
        for scenario in scenario_matrix:
            brand_state = "absent"
            if scenario.get("brand_present"):
                brand_state = "win" if scenario.get("battle_status") in {"advantage", "defend"} else "present"

            brand_states = {
                "本品牌": {
                    "state": brand_state,
                    "officialCited": bool(scenario.get("official_citation_present", False)),
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

            rows.append({
                "scenarioId": scenario.get("scenario_id", ""),
                "scenarioLabel": scenario.get("scenario_label", ""),
                "scenarioPriority": scenario.get("scenario_priority", "medium"),
                "winnerBrand": (scenario.get("winner_brands", []) or [""])[0],
                "battleStatus": scenario.get("battle_status", "missing"),
                "recommendedFocus": scenario.get("action_hint", ""),
                "brandStates": brand_states,
            })
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
        current_summary = current_payload["summary_metrics"] or self._fallback_summary_metrics(current)
        current_scenarios = current_payload["scenario_matrix"] or []
        current_competitors = current_payload["competitor_battles"] or []
        current_actions = current_payload["action_queue"] or []

        previous_summary: dict[str, Any] | None = None
        if previous:
            prev_payload = self._extract_v2_payload(previous)
            previous_summary = prev_payload["summary_metrics"] or self._fallback_summary_metrics(previous)

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
                self._scenario_priority_rank(str(row.get("scenario_priority", "medium"))),
                self._risk_rank(str(row.get("risk_level", "low"))),
                str(row.get("scenario_label", "")),
            ),
        )
        sorted_competitors = sorted(
            [row for row in current_competitors if isinstance(row, dict)],
            key=lambda row: (
                self._risk_rank("high" if row.get("pressure_level") == "high" else "medium"),
                -(int(row.get("competitor_only_scenarios", 0) or 0)),
                str(row.get("competitor", "")),
            ),
        )
        sorted_actions = sorted(
            [row for row in current_actions if isinstance(row, dict)],
            key=lambda row: (int(row.get("priority", 3) or 3), str(row.get("scenario_label", ""))),
        )

        return {
            "kpi": {
                "brandMentionRate": current_summary.get("brand_mention_rate"),
                "officialCitationRate": current_summary.get("official_citation_rate"),
                "effectiveScenarioCount": current_summary.get("scenario_hit_count"),
                "missingHighValueScenarioCount": current_summary.get("missing_high_value_scenario_count"),
                "highRiskScenarioCount": current_summary.get("high_risk_scenario_count"),
                "mentionRateTrend": trend_value("brand_mention_rate"),
                "officialCitationRateTrend": trend_value("official_citation_rate"),
                "effectiveScenarioTrend": trend_value("scenario_hit_count"),
                "missingHighValueScenarioTrend": trend_value("missing_high_value_scenario_count"),
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
            "actionQueue": [
                self._to_action_camel(row) for row in sorted_actions[:5]
            ],
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
        scenarios = [
            row for row in payload["scenario_matrix"]
            if isinstance(row, dict)
        ]
        scenarios = sorted(
            scenarios,
            key=lambda row: (
                self._scenario_priority_rank(str(row.get("scenario_priority", "medium"))),
                self._risk_rank(str(row.get("risk_level", "low"))),
                str(row.get("scenario_label", "")),
            ),
        )
        platforms = sorted({
            str(platform)
            for row in scenarios
            for platform in row.get("present_platforms", []) or []
            if platform
        })
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
            row for row in payload["competitor_battles"]
            if isinstance(row, dict)
        ]
        competitors = sorted(
            competitors,
            key=lambda row: (
                self._risk_rank("high" if row.get("pressure_level") == "high" else "medium"),
                -(int(row.get("competitor_only_scenarios", 0) or 0)),
                str(row.get("competitor", "")),
            ),
        )
        scenarios = [
            row for row in payload["scenario_matrix"]
            if isinstance(row, dict)
        ]
        scenarios = sorted(
            scenarios,
            key=lambda row: (
                self._scenario_priority_rank(str(row.get("scenario_priority", "medium"))),
                self._risk_rank(str(row.get("risk_level", "low"))),
                str(row.get("scenario_label", "")),
            ),
        )
        return {
            "competitors": [self._to_competitor_battle_camel(row) for row in competitors],
            "scenarioMatrix": self._build_competitor_matrix_rows(scenarios, competitors),
        }

    async def get_sources_v2(self, brand_id: str | None) -> dict[str, Any]:
        """Get Dashboard V2 source overview."""
        report_outputs = await self._get_report_like_outputs(brand_id=brand_id)
        current = report_outputs[0] if report_outputs else None
        if not current:
            return {"sourceOverview": {}}

        payload = self._extract_v2_payload(current)
        source_overview = payload["source_overview"] or self._fallback_source_overview(current)
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

