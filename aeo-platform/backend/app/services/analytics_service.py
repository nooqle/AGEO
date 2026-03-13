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
                    metadata = None
                    if msg.extra_metadata:
                        try:
                            metadata = json.loads(msg.extra_metadata)
                        except (json.JSONDecodeError, TypeError):
                            metadata = None
                    data["_output_type"] = msg.output_type
                    data["_created_at"] = msg.created_at.isoformat() if msg.created_at else None
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
                    outputs.append(data)
                except (json.JSONDecodeError, TypeError):
                    continue
        return outputs

    def _is_dashboard_report_output(self, output: dict[str, Any]) -> bool:
        """Return True when the artifact is an A5 report suitable for dashboard boards."""
        output_type = str(output.get("_output_type") or "")
        artifact_kind = str(
            output.get("_artifact_kind")
            or output.get("artifact_kind")
            or ""
        ).strip().lower()
        report_kind = str(
            output.get("_report_kind")
            or output.get("report_kind")
            or ""
        ).strip().lower()

        if artifact_kind == "confidence_signal" or report_kind == "confidence_signal":
            return False
        if output_type == "report_baseline":
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
        query = (
            select(Message)
            .where(
                Message.role == MessageRole.ASSISTANT,
                Message.type == MessageType.OUTPUT,
                Message.output_type.in_(("report", "report_baseline")),
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
                data["_created_at"] = msg.created_at.isoformat() if msg.created_at else None
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
                if self._is_dashboard_report_output(data):
                    outputs.append(data)
            except (json.JSONDecodeError, TypeError):
                continue
        return outputs

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
            "mention_sentiment_analysis": pick("mention_sentiment_analysis", {}),
            "citation_analysis": data.get("citation_analysis")
            or nested_report.get("citation_analysis")
            or metrics_raw.get("citation_analysis")
            or {},
        }

    def _extract_report_data(self, data: dict[str, Any]) -> dict[str, Any]:
        report_data = data.get("report_data")
        return report_data if isinstance(report_data, dict) else {}

    def _extract_platform_analysis(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        report_data = self._extract_report_data(data)
        platform_analysis = report_data.get("platform_analysis", data.get("platform_analysis", []))
        return [item for item in platform_analysis if isinstance(item, dict)] if isinstance(platform_analysis, list) else []

    def _extract_competitor_deep_analysis(self, data: dict[str, Any]) -> dict[str, Any]:
        report_data = self._extract_report_data(data)
        competitor_deep_analysis = report_data.get(
            "competitor_deep_analysis",
            data.get("competitor_deep_analysis", {}),
        )
        return competitor_deep_analysis if isinstance(competitor_deep_analysis, dict) else {}

    def _legacy_sentiment_summary(self, data: dict[str, Any]) -> dict[str, int]:
        metrics = self._extract_metrics(data) or {}
        raw = metrics.get("sentiment_distribution", data.get("sentiment_distribution", {}))
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
        if any(token in lowered for token in ["缺失", "不足", "短板", "风险", "偏弱", "负向"]):
            return "negative"
        return "neutral"

    def _sentiment_summary_from_mentions(self, mentions: list[dict[str, Any]]) -> dict[str, int]:
        summary = {"positive": 0, "neutral": 0, "negative": 0}
        for item in mentions:
            sentiment = str(item.get("sentiment", "neutral") or "neutral").strip().lower()
            if sentiment not in summary:
                sentiment = "neutral"
            summary[sentiment] += 1
        return summary

    def _legacy_brand_mentions_from_fetch_results(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        fetch_results = self._extract_fetch_results(data)
        mentions: list[dict[str, Any]] = []

        for question_index, row in enumerate(fetch_results, start=1):
            if not isinstance(row, dict):
                continue

            scenario_id = str(row.get("question_id") or row.get("id") or f"legacy-question-{question_index}")
            scenario_label = str(
                row.get("question_text")
                or row.get("query")
                or row.get("question")
                or row.get("title")
                or ""
            ).strip()
            platform_results = row.get("platform_results", []) if isinstance(row.get("platform_results"), list) else []

            # 仅当旧数据里真实保留了问题或查询文本时，才重建问题级提及明细。
            if not scenario_label:
                continue

            for platform_index, item in enumerate(platform_results, start=1):
                if not isinstance(item, dict) or not item.get("success"):
                    continue

                answer = item.get("answer", {}) if isinstance(item.get("answer"), dict) else {}
                has_brand_mention = bool(
                    answer.get("has_brand_mention") if isinstance(answer, dict) else item.get("has_brand_mention", False)
                )
                if not has_brand_mention:
                    continue

                content = str(answer.get("content") or item.get("content") or item.get("answer_text") or "")
                citations = item.get("citations", []) if isinstance(item.get("citations"), list) else []
                citation_domains: list[str] = []
                citation_titles: list[str] = []
                citation_urls: list[str] = []
                for citation in citations:
                    if not isinstance(citation, dict):
                        continue
                    url = str(citation.get("url", "") or "").strip()
                    domain = str(citation.get("domain") or extract_domain(url) or citation.get("source") or "").strip()
                    title = str(citation.get("title", "") or "").strip()
                    if domain and domain not in citation_domains:
                        citation_domains.append(domain)
                    if title and title not in citation_titles:
                        citation_titles.append(title)
                    if url and url not in citation_urls:
                        citation_urls.append(url)

                mentions.append({
                    "scenarioId": scenario_id or f"legacy-question-{question_index}-{platform_index}",
                    "scenarioLabel": scenario_label or f"问题 {question_index}",
                    "platform": str(item.get("platform") or item.get("platform_name") or ""),
                    "sentiment": self._legacy_sentiment_label(answer.get("sentiment"), content),
                    "evidence": content[:280].strip(),
                    "citationDomains": citation_domains,
                    "citationTitles": citation_titles,
                    "citationUrls": citation_urls,
                    "officialCitationPresent": False,
                })

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
                normalized.append({
                    "scenarioId": str(row.get("scenario_id", f"legacy-{index + 1}")),
                    "scenarioLabel": str(label),
                    "reason": str(reason),
                    "platforms": [str(platform) for platform in platforms if platform],
                })
            elif row:
                normalized.append({
                    "scenarioId": f"legacy-{index + 1}",
                    "scenarioLabel": str(row),
                    "reason": default_reason,
                    "platforms": [],
                })
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
            self._extract_report_data(data).get("weaknesses", data.get("weaknesses", [])),
            "该场景仍需要补强品牌提及和证据表现。",
        )

        # 旧报告若未保存原始 fetch_results，就无法重建真实的问题级提及明细。
        # 这里不再从 platform_analysis 反推伪问题，避免顶部统计和下方问题列表口径不一致。
        brand_mentions = self._legacy_brand_mentions_from_fetch_results(data)

        comparison_matrix = competitor_deep_analysis.get("comparison_matrix", [])
        comparison_matrix = comparison_matrix if isinstance(comparison_matrix, list) else []
        leading_competitors = []
        competitor_mentions: list[dict[str, Any]] = []
        for row in comparison_matrix[:3]:
            if not isinstance(row, dict):
                continue
            competitor_only = int(row.get("competitor_only_scenarios", 0) or 0)
            shared = int(row.get("shared_scenarios", 0) or 0)
            pressure = "high" if competitor_only >= max(shared, 1) else "medium" if (competitor_only or shared) else "low"
            leading_competitors.append({
                "competitor": str(row.get("competitor", "")),
                "pressureLevel": pressure,
                "competitorOnlyScenarios": competitor_only,
                "sentimentSummary": {"positive": 0, "neutral": shared + competitor_only, "negative": 0},
            })
            for conflict_index, scenario in enumerate((row.get("top_conflict_scenarios") or [])[:3]):
                competitor_mentions.append({
                    "competitor": str(row.get("competitor", "")),
                    "scenarioId": f"legacy-competitor-{conflict_index + 1}",
                    "scenarioLabel": str(scenario),
                    "platform": "",
                    "sentiment": "neutral",
                    "evidence": "该竞品在该场景被频繁共同提及或独占提及。",
                    "citationDomains": [],
                    "citationTitles": [],
                    "officialCitationPresent": False,
                })

        sentiment_summary = self._sentiment_summary_from_mentions(brand_mentions)
        mention_count = len(brand_mentions)
        total_questions = int((self._extract_metrics(data) or {}).get("total_questions", 0) or 0)
        leading_competitor = leading_competitors[0]["competitor"] if leading_competitors else "暂无明显竞品压力"
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

    def _build_legacy_source_board(self, data: dict[str, Any], source_overview: dict[str, Any]) -> dict[str, Any]:
        brand_domain = str(source_overview.get("brand_domain", "") or "")
        fetch_results_summary = data.get("fetch_results_summary", [])
        fetch_results_summary = fetch_results_summary if isinstance(fetch_results_summary, list) else []

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
            citations = row.get("citations", []) if isinstance(row.get("citations"), list) else []
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
                title = str(citation.get("title") or citation.get("source") or domain or "")
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
                "platform": platform,
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
                {"platform": platform or "unknown", "total": 0, "cited": 0, "official": 0},
            )
            platform_row["total"] += 1
            platform_row["cited"] += 1
            if official_present:
                platform_row["official"] += 1

        source_headline = (
            f"在 {total_brand_mentions} 条提及品牌的回答里，有 {cited_brand_answers} 条引用了品牌相关内容，"
            f"其中 {len(official_cases)} 条来自官网，{len(non_official_cases)} 条来自第三方站点。"
        )

        platform_citation_stats = source_overview.get("platform_citation_stats", {}) or {}
        platform_rows = []
        for platform, stats in platform_stats.items():
            stat_payload = platform_citation_stats.get(platform, {}) if isinstance(platform_citation_stats, dict) else {}
            total = int(stats.get("total", 0) or 0)
            cited = int(stats.get("cited", 0) or 0)
            platform_rows.append({
                "platform": platform,
                "contentCitationRate": round(cited / total, 4) if total else 0.0,
                "officialCitationRate": float(stat_payload.get("official_citation_rate", 0) or 0),
                "topDomains": [
                    {
                        "domain": domain_item.get("domain", ""),
                        "count": int(domain_item.get("count", 0) or 0),
                    }
                    for domain_item in stat_payload.get("top_domains", []) or []
                    if isinstance(domain_item, dict)
                ],
            })

        return {
            "contentCitationRate": round(cited_brand_answers / total_brand_mentions, 4) if total_brand_mentions else None,
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
        strengths = self._extract_report_data(data).get("strengths", data.get("strengths", []))
        weaknesses = self._extract_report_data(data).get("weaknesses", data.get("weaknesses", []))
        risk_alerts = self._extract_report_data(data).get("risk_alerts", data.get("risk_alerts", []))
        mention_value = float(mention_rate or metrics.get("mention_rate", 0) or 0)
        total_questions = float(metrics.get("total_questions", 0) or 0)
        total_mentions = float(metrics.get("total_mentions", 0) or 0)

        platform_coverage_count = len([item for item in platform_analysis if int(item.get("mentions", item.get("mention_count", 0)) or 0) > 0])
        platform_coverage_rate = min(1.0, platform_coverage_count / 4) if platform_coverage_count else 0.0
        scenario_coverage_rate = min(1.0, (total_mentions / total_questions)) if total_questions else mention_value
        positive_total = sentiment_summary["positive"] + sentiment_summary["neutral"] + sentiment_summary["negative"]
        positive_rate = (sentiment_summary["positive"] / positive_total) if positive_total else 0.0
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
        strongest_dimension = sorted_dimensions[-1]["label"] if sorted_dimensions else ""
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
        """Get legacy metric cards using current product-facing wording."""
        outputs = await self._get_all_outputs(brand_id=brand_id)

        def inverse_status(value: int | float | None, good: float, warning: float) -> str:
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
                aeo_metrics.append({
                    "metric": "品牌提及率",
                    "value": round(float(mention_rate) * 100, 1),
                    "benchmark": 30.0,
                    "status": _aeo_status(float(mention_rate), "mention_rate"),
                })

            if official_citation_rate is not None:
                citation_rate = float(official_citation_rate)
                aeo_metrics.append({
                    "metric": "官网引用率",
                    "value": round(citation_rate * 100, 1),
                    "benchmark": 20.0,
                    "status": "good" if citation_rate >= 0.20 else "warning" if citation_rate >= 0.08 else "poor",
                })

            if scenario_hit_count is not None:
                hit_count = int(scenario_hit_count)
                aeo_metrics.append({
                    "metric": "有效场景数",
                    "value": hit_count,
                    "benchmark": 5,
                    "status": "good" if hit_count >= 5 else "warning" if hit_count >= 2 else "poor",
                })

            if missing_count is not None:
                missing = int(missing_count)
                aeo_metrics.append({
                    "metric": "缺席高价值场景",
                    "value": missing,
                    "benchmark": 2,
                    "status": inverse_status(missing, good=1, warning=3),
                })

            if high_risk_count is not None:
                high_risk = int(high_risk_count)
                aeo_metrics.append({
                    "metric": "高风险场景",
                    "value": high_risk,
                    "benchmark": 1,
                    "status": inverse_status(high_risk, good=0, warning=2),
                })

            if aeo_metrics:
                break

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
    async def get_dashboard_home_v2(self, brand_id: str | None) -> dict[str, Any]:
        """Get Dashboard homepage three-board aggregate data."""
        report_outputs = await self._get_report_like_outputs(brand_id=brand_id)
        current = report_outputs[0] if report_outputs else None
        if not current:
            return {
                "summary": {"headline": "尚未生成分析结果，完成首次分析后即可查看首页三看板。"},
                "mentionBoard": {
                    "mentionRate": None,
                    "headline": "暂无提及数据。",
                    "sentimentSummary": {"positive": 0, "neutral": 0, "negative": 0},
                    "leadingCompetitors": [],
                    "report": {
                        "brandMentions": [],
                        "competitorMentions": [],
                        "strongScenarios": [],
                        "weakScenarios": [],
                    },
                },
                "sourceBoard": {
                    "contentCitationRate": None,
                    "citedAnswerCount": 0,
                    "citedContentCount": 0,
                    "headline": "暂无内容引用数据。",
                    "report": {
                        "officialCases": [],
                        "nonOfficialCases": [],
                        "officialContents": [],
                        "nonOfficialContents": [],
                        "topDomains": [],
                        "platformStats": [],
                    },
                },
                "radarBoard": {
                    "headline": "暂无雷达数据。",
                    "strongestDimension": "",
                    "weakestDimension": "",
                    "dimensions": [],
                },
                "monitoringEntry": {
                    "title": "持续监测",
                    "description": "追踪提及率、官网引用率和风险变化。",
                    "ctaLabel": "进入监测",
                },
            }

        payload = self._extract_v2_payload(current)
        summary = payload.get("summary_metrics") or self._fallback_summary_metrics(current)
        source_overview = payload.get("source_overview") or self._fallback_source_overview(current)
        scenario_matrix = [row for row in payload.get("scenario_matrix", []) if isinstance(row, dict)]
        competitor_battles = [row for row in payload.get("competitor_battles", []) if isinstance(row, dict)]
        risk_map = [row for row in payload.get("risk_map", []) if isinstance(row, dict)]
        mention_payload = payload.get("mention_sentiment_analysis") or {}
        brand_payload = mention_payload.get("brand", {}) if isinstance(mention_payload, dict) else {}
        competitor_payloads = mention_payload.get("competitors", []) if isinstance(mention_payload, dict) else []
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
                    "reason": row.get("evidence") or row.get("action_hint") or "需要继续观察该场景。",
                    "platforms": row.get("present_platforms", []) or [],
                }
                for row in rows
            ]

        brand_summary = normalize_sentiment_summary(brand_payload.get("summary"))
        brand_mentions = [row for row in brand_payload.get("items", []) if isinstance(row, dict)]
        brand_mentions = sorted(
            brand_mentions,
            key=lambda row: (
                self._risk_rank(str(next((item.get("risk_level", "medium") for item in scenario_matrix if item.get("scenario_id") == row.get("scenario_id")), "medium"))),
                str(row.get("scenario_label", "")),
            ),
        )

        legacy_mention_board = self._build_legacy_mention_board(current, summary.get("brand_mention_rate"))
        if not brand_mentions:
            brand_mentions = legacy_mention_board["report"]["brandMentions"]

        normalized_mentions = []
        for item in brand_mentions:
            if not isinstance(item, dict):
                continue
            scenario_id = str(item.get("scenario_id", item.get("scenarioId", "")) or "")
            scenario_label = str(item.get("scenario_label", item.get("scenarioLabel", "")) or "")
            platform = str(item.get("platform", "") or "")
            sentiment = str(item.get("sentiment", "neutral") or "neutral")
            evidence = str(item.get("evidence", "") or "")
            citation_domains = item.get("citation_domains", item.get("citationDomains", [])) or []
            citation_titles = item.get("citation_titles", item.get("citationTitles", [])) or []
            citation_urls = item.get("citation_urls", item.get("citationUrls", [])) or []
            official_present = bool(item.get("official_citation_present", item.get("officialCitationPresent", False)))
            if not scenario_id and not scenario_label:
                continue
            normalized_mentions.append({
                "scenario_id": scenario_id,
                "scenario_label": scenario_label,
                "platform": platform,
                "sentiment": sentiment,
                "evidence": evidence,
                "citation_domains": [str(domain) for domain in citation_domains if domain],
                "citation_titles": [str(title) for title in citation_titles if title],
                "citation_urls": [str(url) for url in citation_urls if url],
                "official_citation_present": official_present,
            })
        brand_mentions = normalized_mentions
        brand_summary = self._sentiment_summary_from_mentions(brand_mentions)

        top_competitors = sorted(
            competitor_battles,
            key=lambda row: (
                self._risk_rank("high" if row.get("pressure_level") == "high" else "medium"),
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
                    item for item in competitor_payloads
                    if isinstance(item, dict) and str(item.get("competitor", "")) == str(competitor.get("competitor", ""))
                ),
                {},
            )
            sentiment_summary = normalize_sentiment_summary(payload_row.get("summary"))
            competitor_summaries.append({
                "competitor": competitor.get("competitor", ""),
                "pressureLevel": competitor.get("pressure_level", "medium"),
                "competitorOnlyScenarios": int(competitor.get("competitor_only_scenarios", 0) or 0),
                "sentimentSummary": sentiment_summary,
            })
            for item in payload_row.get("items", [])[:4]:
                if not isinstance(item, dict):
                    continue
                competitor_mentions.append({
                    "competitor": payload_row.get("competitor", ""),
                    "scenarioId": item.get("scenario_id", ""),
                    "scenarioLabel": item.get("scenario_label", ""),
                    "platform": item.get("platform", ""),
                    "sentiment": item.get("sentiment", "neutral"),
                    "evidence": item.get("evidence", ""),
                    "citationDomains": item.get("citation_domains", []) or [],
                    "citationTitles": item.get("citation_titles", []) or [],
                    "officialCitationPresent": bool(item.get("official_citation_present", False)),
                })
        if not competitor_summaries:
            competitor_summaries = legacy_mention_board["leadingCompetitors"]
        if not competitor_mentions:
            competitor_mentions = legacy_mention_board["report"]["competitorMentions"]

        mention_rate = summary.get("brand_mention_rate")
        if mention_rate is None:
            mention_rate = metrics.get("mention_rate")
        scenario_total = int(summary.get("scenario_total", len(scenario_matrix)) or metrics.get("total_questions") or len(scenario_matrix) or 0)
        unique_brand_scenarios = {
            str(item.get("scenario_id") or item.get("scenario_label") or "")
            for item in brand_mentions
            if (item.get("scenario_id") or item.get("scenario_label"))
        }
        scenario_hit_count = len(unique_brand_scenarios)
        if unique_brand_scenarios and scenario_total > 0:
            mention_rate = round(len(unique_brand_scenarios) / scenario_total, 4)
        leading_competitor_name = competitor_summaries[0]["competitor"] if competitor_summaries else "暂无明显竞品压力"
        mention_headline = (
            f"品牌当前在 {scenario_hit_count}/{scenario_total or 0} 个场景进入回答，"
            f"正向提及 {brand_summary['positive']} 条，主要竞争压力来自 {leading_competitor_name}。"
        )

        cited_brand_mentions = [
            item for item in brand_mentions
            if (item.get("citation_domains") or item.get("citation_titles"))
        ]
        official_cases = [item for item in cited_brand_mentions if bool(item.get("official_citation_present", False))]
        non_official_cases = [item for item in cited_brand_mentions if not bool(item.get("official_citation_present", False))]

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

        official_question_cases = [to_citation_case(item, True) for item in official_cases[:8]]
        non_official_question_cases = [to_citation_case(item, False) for item in non_official_cases[:8]]

        def unique_content_rows(items: list[dict[str, Any]], is_official: bool) -> list[dict[str, Any]]:
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
                    rows.append({
                        "title": title or fallback_domain or "未命名引用内容",
                        "domain": fallback_domain or None,
                        "isOfficial": is_official,
                    })
            return rows[:12]

        official_contents = unique_content_rows(official_cases, True)
        non_official_contents = unique_content_rows(non_official_cases, False)
        content_citation_rate = (len(cited_brand_mentions) / len(brand_mentions)) if brand_mentions else None
        legacy_source_board = self._build_legacy_source_board(current, source_overview)
        if content_citation_rate is None or (content_citation_rate == 0 and legacy_source_board["citedAnswerCount"] > 0):
            content_citation_rate = legacy_source_board["contentCitationRate"]
        if not official_question_cases:
            official_question_cases = legacy_source_board["report"]["officialCases"]
        if not non_official_question_cases:
            non_official_question_cases = legacy_source_board["report"]["nonOfficialCases"]
        if not official_contents:
            official_contents = legacy_source_board["report"]["officialContents"]
        if not non_official_contents:
            non_official_contents = legacy_source_board["report"]["nonOfficialContents"]

        platform_stat_map = source_overview.get("platform_citation_stats", {}) or {}
        platform_rows = []
        for platform_name in sorted({str(item.get("platform", "") or "") for item in brand_mentions if item.get("platform")}):
            platform_mentions = [item for item in brand_mentions if str(item.get("platform", "") or "") == platform_name]
            platform_cited = [item for item in platform_mentions if (item.get("citation_domains") or item.get("citation_titles"))]
            stats = platform_stat_map.get(platform_name, {}) if isinstance(platform_stat_map, dict) else {}
            platform_rows.append({
                "platform": platform_name,
                "contentCitationRate": round(len(platform_cited) / len(platform_mentions), 4) if platform_mentions else 0.0,
                "officialCitationRate": float(stats.get("official_citation_rate", 0) or 0),
                "topDomains": [
                    {
                        "domain": domain_item.get("domain", ""),
                        "count": int(domain_item.get("count", 0) or 0),
                    }
                    for domain_item in stats.get("top_domains", []) or []
                    if isinstance(domain_item, dict)
                ],
            })
        if not platform_rows:
            platform_rows = legacy_source_board["report"]["platformStats"]

        source_headline = (
            f"在 {len(brand_mentions)} 条提及品牌的回答里，有 {len(cited_brand_mentions)} 条引用了品牌相关内容，"
            f"其中 {len(official_cases)} 条来自官网，{len(non_official_cases)} 条来自第三方站点。"
        )
        if not cited_brand_mentions and legacy_source_board["headline"]:
            source_headline = legacy_source_board["headline"]

        platform_coverage_count = float(summary.get("platform_coverage_count") or 0)
        platform_total_count = float(summary.get("platform_total_count") or max(platform_coverage_count, 1) or 1)
        platform_coverage_rate = min(1.0, platform_coverage_count / platform_total_count) if platform_total_count else 0.0
        scenario_effective_rate = summary.get("scenario_effective_rate")
        if scenario_effective_rate is None:
            scenario_effective_rate = (scenario_hit_count / scenario_total) if scenario_total else 0.0

        high_priority_rows = [row for row in scenario_matrix if str(row.get("scenario_priority", "medium")) == "high"]
        high_priority_hits = [row for row in high_priority_rows if bool(row.get("brand_present", False))]
        audience_coverage_rate = (
            (len(high_priority_hits) / len(high_priority_rows)) if high_priority_rows else platform_coverage_rate
        )

        sentiment_total = brand_summary["positive"] + brand_summary["neutral"] + brand_summary["negative"]
        positive_rate = (brand_summary["positive"] / sentiment_total) if sentiment_total else 0.0
        missing_count = float(summary.get("missing_high_value_scenario_count") or 0)
        high_risk_count = float(summary.get("high_risk_scenario_count") or 0)
        risk_control_score = max(0.0, min(100.0, 100.0 - min(100.0, missing_count * 12 + high_risk_count * 18)))

        radar_dimensions = [
            {
                "id": "industry_influence",
                "label": "行业影响",
                "score": round(max(0.0, min(100.0, (float(mention_rate or 0) * 100 * 0.7) + (platform_coverage_rate * 100 * 0.3)))),
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
                "score": round(max(0.0, min(100.0, float(scenario_effective_rate or 0) * 100))),
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
        strongest_dimension = sorted_dimensions[-1]["label"] if sorted_dimensions else ""
        radar_headline = f"当前最大优势在 {strongest_dimension}，最大短板在 {weakest_dimension}。"
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

        return {
            "summary": {
                "headline": summary_headline,
            },
            "mentionBoard": {
                "mentionRate": mention_rate,
                "headline": mention_headline if brand_mentions else legacy_mention_board["headline"],
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
                            "officialCitationPresent": bool(item.get("official_citation_present", False)),
                        }
                        for item in brand_mentions[:10]
                    ],
                    "competitorMentions": competitor_mentions[:12],
                    "strongScenarios": (
                        scenario_insight_rows([
                        row for row in scenario_matrix
                        if bool(row.get("brand_present", False)) and str(row.get("battle_status", "")) in {"advantage", "defend"}
                    ][:4])
                        if scenario_matrix else legacy_mention_board["report"]["strongScenarios"]
                    ),
                    "weakScenarios": (
                        scenario_insight_rows([
                        row for row in scenario_matrix
                        if str(row.get("battle_status", "")) in {"missing", "contested"}
                    ][:6])
                        if scenario_matrix else legacy_mention_board["report"]["weakScenarios"]
                    ),
                },
            },
            "sourceBoard": {
                "contentCitationRate": content_citation_rate,
                "citedAnswerCount": len(cited_brand_mentions) or legacy_source_board["citedAnswerCount"],
                "citedContentCount": len(official_contents) + len(non_official_contents) or legacy_source_board["citedContentCount"],
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
                    ] or legacy_source_board["report"]["topDomains"],
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

