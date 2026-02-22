"""A5 Node: Data Analytics and Report Generation.

This module contains the A5 node implementation for analyzing fetch results
and generating comprehensive reports with BWVS metrics.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from langgraph.types import Command

from app.core.utils import extract_domain
from app.workflow.nodes_a4 import PLATFORMS

logger = logging.getLogger(__name__)

# --- 情感分析关键词 ---
_POSITIVE_KEYWORDS = [
    "推荐", "优秀", "领先", "首选", "值得", "最佳", "出色", "优质",
    "创新", "卓越", "领导", "知名", "强大", "受欢迎", "信赖", "可靠",
    "高品质", "好评", "优势", "突出", "一流", "顶尖", "专业",
]
_NEGATIVE_KEYWORDS = [
    "不推荐", "缺点", "问题", "差评", "不足", "劣势", "风险", "争议",
    "质疑", "不好", "差", "落后", "不稳定", "投诉", "负面", "糟糕",
    "不佳", "低质", "不靠谱", "下滑", "亏损",
]

# BWVS v2 weights (V1: global constants, migrate to per-brand config in P2)
BWVS_WEIGHTS = {
    "mention": 40,     # W1: mention rate score weight
    "sentiment": 25,   # W2: sentiment score weight
    "coverage": 20,    # W3: platform coverage weight
    "citation": 15,    # W4: citation quality weight
}
assert sum(BWVS_WEIGHTS.values()) == 100, "BWVS weights must sum to 100"


def _analyze_sentiment(text: str) -> str:
    """基于关键词匹配分析文本情感倾向。

    先匹配否定词（更长更具体），然后将已匹配的否定词位置排除，
    避免 "不推荐" 中的 "推荐" 被误判为正面。

    Returns:
        "positive", "negative", or "neutral"
    """
    if not text:
        return "neutral"

    # 先统计否定关键词，并记录匹配位置
    neg_count = 0
    neg_spans: list[tuple[int, int]] = []
    for kw in _NEGATIVE_KEYWORDS:
        start = 0
        while True:
            idx = text.find(kw, start)
            if idx == -1:
                break
            neg_count += 1
            neg_spans.append((idx, idx + len(kw)))
            start = idx + len(kw)

    # 统计正面关键词，排除被否定词覆盖的位置
    pos_count = 0
    for kw in _POSITIVE_KEYWORDS:
        start = 0
        while True:
            idx = text.find(kw, start)
            if idx == -1:
                break
            # 检查该正面词是否在某个否定词范围内
            shadowed = any(ns <= idx < ne for ns, ne in neg_spans)
            if not shadowed:
                pos_count += 1
            start = idx + len(kw)

    if pos_count > neg_count:
        return "positive"
    elif neg_count > pos_count:
        return "negative"
    else:
        return "neutral"

from app.workflow.state import AgentState
from app.workflow.events import (
    send_progress_event,
    send_stage_result,
)
from app.workflow.nodes import get_llm_model_compat, parse_llm_response
from app.workflow.nodes_streaming import call_llm_streaming
from app.workflow.summaries import generate_a5_summary


async def a5_analytics_node(state: AgentState) -> Command:
    """A5: Analyze fetch results and generate comprehensive report.

    Calculates BWVS metrics and generates executive summary with recommendations.
    Writes AnalysisSnapshot for historical trending.

    Routes between baseline and persona report modes based on analysis_mode.
    """
    session_id = state["session_id"]
    entity_id = state.get("entity_id")
    brand_profile = state.get("brand_profile") or {}
    fetch_results = state.get("fetch_results") or []
    competitors = state.get("competitors") or []
    marketing_personas = state.get("marketing_personas")
    analysis_mode = state.get("analysis_mode") or "persona"
    is_baseline = analysis_mode == "baseline"

    step_message = "开始基线全景分析..." if is_baseline else "开始分析抓取数据..."
    await send_progress_event(
        session_id=session_id,
        step="A5",
        step_name="数据分析报告",
        progress=0.65,
        message=step_message,
    )

    try:
        # Calculate metrics
        metrics = _calculate_metrics(fetch_results, brand_profile)

        # Calculate competitor metrics BEFORE LLM call so they can be
        # included in the prompt (was previously done after LLM, too late)
        competitor_metrics = _calculate_competitor_metrics(fetch_results, competitors)

        await send_progress_event(
            session_id=session_id,
            step="A5",
            step_name="数据分析报告",
            progress=0.75,
            message=f"提及率: {metrics.get('mention_rate', 0):.1%} (BWVS指数: {metrics.get('bwvs_index', 0):.1f})",
        )

        # Stage result: metrics preview before LLM report generation
        metrics_preview_data = {
            "bwvs_index": round(metrics.get("bwvs_index", 0), 1),
            "mention_rate": f"{metrics.get('mention_rate', 0):.1%}",
            "total_mentions": metrics.get("total_mentions", 0),
            "total_questions": metrics.get("total_questions", 0),
            "score_band": (
                "优秀" if metrics.get("bwvs_index", 0) >= 70
                else "良好" if metrics.get("bwvs_index", 0) >= 40
                else "需改进"
            ),
        }
        await send_stage_result(
            session_id, "A5", "数据分析",
            result_type="metrics_preview",
            data=metrics_preview_data,
        )

        # Persist stage result for reconnection replay
        task_id = state.get("task_id")
        if task_id:
            try:
                from app.core.database import AsyncSessionLocal
                from app.services.task_service import TaskService
                from uuid import UUID as _UUID
                async with AsyncSessionLocal() as db:
                    task_svc = TaskService(db)
                    await task_svc.append_stage_result(_UUID(task_id), {
                        "stage": "A5",
                        "result_type": "metrics_preview",
                        "data": metrics_preview_data,
                        "stage_name": "数据分析",
                    })
            except Exception as e:
                logger.warning("[A5] Failed to persist stage_result: %s", e)

        # Query previous snapshot for delta (before LLM call, to include in prompt)
        previous_snapshot_data = None
        if entity_id:
            try:
                from app.core.database import AsyncSessionLocal
                from app.services.snapshot_service import SnapshotService
                async with AsyncSessionLocal() as db:
                    snap_service = SnapshotService(db)
                    prev_snap = await snap_service.get_previous_snapshot(
                        entity_id=entity_id,
                        snapshot_type="baseline" if is_baseline else "persona",
                    )
                    if prev_snap and prev_snap.bwvs_index is not None:
                        previous_snapshot_data = {
                            "date": prev_snap.created_at.strftime("%Y-%m-%d") if prev_snap.created_at else "N/A",
                            "bwvs_index": prev_snap.bwvs_index,
                            "mention_rate": prev_snap.mention_rate,
                            "sentiment_score": prev_snap.sentiment_score,
                            "coverage_score": prev_snap.coverage_score,
                            "citation_score": prev_snap.citation_score,
                        }
            except Exception as snap_err:
                logger.warning("[A5] Failed to query previous snapshot: %s", snap_err)

        # Generate report using LLM -- wrapped in inner try so LLM failure
        # triggers fallback instead of aborting the entire A5 node.
        report_data = None
        try:
            system_prompt = _get_a5_system_prompt(report_type=analysis_mode)
            user_content = _build_a5_user_content(
                brand_profile, metrics, fetch_results, competitors,
                marketing_personas=marketing_personas,
                previous_snapshot=previous_snapshot_data,
                competitor_metrics=competitor_metrics,
                analysis_mode=analysis_mode,
                baseline_metrics=state.get("baseline_metrics"),
                baseline_report=state.get("baseline_report"),
            )

            model = get_llm_model_compat()
            response = await call_llm_streaming(
                session_id=session_id,
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                step="A5",
                step_name="数据分析报告",
                progress_start=0.85,
                progress_end=0.95,
                max_tokens=12288,
            )
            report_data = parse_llm_response(response)

            # 输出校验：关键字段为空时视为 LLM 输出无效，触发 fallback
            if report_data:
                executive_summary = report_data.get("executive_summary", "")
                actionable_recs = report_data.get("actionable_recommendations", [])
                platform_analysis = report_data.get("platform_analysis", [])
                competitor_analysis = report_data.get("competitor_deep_analysis")

                validation_failures = []
                if len(executive_summary) < 80:
                    validation_failures.append(
                        f"executive_summary too short ({len(executive_summary)} chars < 80)"
                    )
                if not actionable_recs:
                    validation_failures.append("actionable_recommendations is empty")
                if not platform_analysis:
                    validation_failures.append("platform_analysis is empty")
                if competitors and not competitor_analysis:
                    validation_failures.append(
                        "competitor_deep_analysis is empty (competitors data available)"
                    )

                if validation_failures:
                    logger.warning(
                        "[A5] LLM output validation failed: %s",
                        "; ".join(validation_failures),
                    )
                    report_data = None  # 触发下方 fallback 分支

        except Exception as llm_err:
            logger.warning(
                "[A5] LLM report generation failed, using fallback: %s",
                llm_err,
            )

        if not report_data:
            report_data = _generate_fallback_report(metrics, brand_profile)
            report_data["_degraded"] = True
            report_data["_degradation_note"] = (
                "本报告基于原始数据自动生成，未经 AI 深度分析"
            )
            from app.workflow.resilience import DegradationRegistry

            await DegradationRegistry.send_degradation_notice(
                session_id, "A5"
            )

        # Normalize report data: ensure all new fields have safe defaults
        report_data = _normalize_report_data(report_data)

        await send_progress_event(
            session_id=session_id,
            step="A5",
            step_name="数据分析报告",
            progress=0.95,
            message="报告生成完成，准备输出...",
        )

        summary = generate_a5_summary(metrics, report_data)

        from app.workflow.events import send_action_log_event
        await send_action_log_event(
            session_id, "agent_summary", summary, step="A5", is_complete=True
        )

        # Build fetch_results summary for analytics service
        fetch_results_summary = []
        for fr in fetch_results:
            for pr in fr.get("platform_results", []):
                fetch_results_summary.append({
                    "platform": pr.get("platform", "unknown"),
                    "success": pr.get("success", False),
                    "has_brand_mention": pr.get("answer", {}).get("has_brand_mention", False),
                    "citations": pr.get("citations", []),
                })

        # --- Snapshot writing + Delta vs previous (single DB session) ---
        is_degraded = report_data.get("_degraded", False)
        snapshot = None
        delta_vs_previous = None
        if entity_id:
            try:
                from app.core.database import AsyncSessionLocal
                from app.services.snapshot_service import SnapshotService
                async with AsyncSessionLocal() as db:
                    snap_service = SnapshotService(db)
                    snapshot = await snap_service.create_completed_snapshot(
                        entity_id=entity_id,
                        session_id=session_id,
                        metrics=metrics,
                        report_data=report_data,
                        competitor_metrics=competitor_metrics,
                        fetch_results_summary=fetch_results_summary,
                        is_degraded=is_degraded,
                        snapshot_type="baseline" if is_baseline else "persona",
                    )
                    logger.info("[A5] Snapshot created: id=%s, bwvs=%.1f", snapshot.id, snapshot.bwvs_index or 0)

                    # Query previous snapshot for delta in the same session
                    previous = await snap_service.get_previous_snapshot(
                        entity_id=entity_id,
                        exclude_snapshot_id=snapshot.id,
                        snapshot_type="baseline" if is_baseline else "persona",
                    )
                    if previous and previous.bwvs_index is not None:
                        current_bwvs = metrics.get("bwvs_index", 0)
                        prev_bwvs = previous.bwvs_index
                        delta_value = current_bwvs - prev_bwvs
                        delta_pct = (delta_value / prev_bwvs * 100) if prev_bwvs else 0
                        delta_vs_previous = {
                            "bwvs_index": {
                                "current": round(current_bwvs, 2),
                                "previous": round(prev_bwvs, 2),
                                "delta": round(delta_value, 2),
                                "percentage": round(delta_pct, 1),
                                "direction": (
                                    "up" if delta_value > 0
                                    else "down" if delta_value < 0
                                    else "stable"
                                ),
                            },
                            "previous_date": previous.created_at.strftime("%Y-%m-%d") if previous.created_at else None,
                            "previous_snapshot_id": str(previous.id),
                        }
            except Exception as snap_err:
                logger.error("[A5] Failed to create snapshot or compute delta: %s", snap_err, exc_info=True)

        # Save and send artifact to Canvas
        from app.workflow.events import save_and_send_artifact
        report_output_type = "report_baseline" if is_baseline else "report"
        report_title = "基线全景分析报告" if is_baseline else "AI 可见性分析报告"
        report_headline = (
            f"{brand_profile.get('brand_name', '品牌')} 基线全景分析报告"
            if is_baseline
            else f"{brand_profile.get('brand_name', '品牌')} AI 可见性分析报告"
        )
        report_category = "baseline" if is_baseline else "scenario"
        await save_and_send_artifact(
            session_id=session_id,
            output_type=report_output_type,
            title=report_title,
            category=report_category,
            data={
                "headline": report_headline,
                "subtitle": f"提及率: {metrics.get('mention_rate', 0):.1%} (BWVS指数: {metrics.get('bwvs_index', 0):.1f})",
                "overallScore": metrics.get("bwvs_index", 0),
                "bwvs_breakdown": metrics.get("bwvs_breakdown", {}),
                "scoreBand": (
                    "优秀" if metrics.get("bwvs_index", 0) >= 70
                    else "良好" if metrics.get("bwvs_index", 0) >= 40
                    else "需改进"
                ),
                "metrics": {
                    "提及率": f"{metrics.get('mention_rate', 0):.1%}",
                    "BWVS指数": metrics.get("bwvs_index", 0),
                    "总问题数": metrics.get("total_questions", 0),
                    "总提及数": metrics.get("total_mentions", 0),
                },
                "insights": [
                    {"type": "strength", "title": s, "description": s}
                    for s in report_data.get("strengths", [])
                ] + [
                    {"type": "weakness", "title": w, "description": w}
                    for w in report_data.get("weaknesses", [])
                ] + [
                    {"type": "opportunity", "title": o, "description": o}
                    for o in report_data.get("opportunities", [])
                ],
                "recommendations": [
                    {
                        "priority": idx + 1,
                        "title": r.get("title", ""),
                        "rationale": r.get("description", ""),
                    }
                    for idx, r in enumerate(report_data.get("recommendations", []))
                ],
                "content": report_data.get("executive_summary", ""),
                # Raw data for enhanced rendering
                "executive_summary": report_data.get("executive_summary", ""),
                "key_findings": report_data.get("key_findings", []),
                "strengths": report_data.get("strengths", []),
                "weaknesses": report_data.get("weaknesses", []),
                "opportunities": report_data.get("opportunities", []),
                "threats": report_data.get("threats", []),
                "action_plan": report_data.get("action_plan", {}),
                "platform_breakdown": metrics.get("platform_breakdown", {}),
                "sentiment_distribution": metrics.get("sentiment_distribution", {}),
                "fetch_results_summary": fetch_results_summary,
                "competitors": competitor_metrics,
                # New enhanced fields
                "metrics_raw": metrics,
                "report_data": report_data,
                "delta_vs_previous": delta_vs_previous,
                "industry_insights": report_data.get("industry_insights"),
                "platform_analysis": report_data.get("platform_analysis", []),
                "competitor_deep_analysis": report_data.get("competitor_deep_analysis"),
                "actionable_recommendations": report_data.get("actionable_recommendations", []),
                "risk_alerts": report_data.get("risk_alerts", []),
            },
        )

        # touchpointMap removed — metrics data is included in the report artifact

        # Update entity status if linked
        entity_id = state.get("entity_id")
        if entity_id:
            try:
                from app.core.database import AsyncSessionLocal
                from app.services.entity_service import EntityService
                async with AsyncSessionLocal() as db:
                    entity_service = EntityService(db)
                    await entity_service.update_entity(
                        entity_id,
                        {
                            "status": "active",
                            "last_analyzed": datetime.now(timezone.utc),
                        },
                    )
                    logger.info(f"[A5] Updated entity {entity_id}: status=active, last_analyzed=now()")
            except Exception as e:
                logger.error(f"[A5] Failed to update entity {entity_id}: {e}")

        # Task milestone: A5 completed (Cycle 3, Module 1)
        task_id = state.get("task_id")
        if task_id:
            try:
                from app.core.database import AsyncSessionLocal
                from app.services.task_service import TaskService
                from uuid import UUID as _UUID
                async with AsyncSessionLocal() as db:
                    task_svc = TaskService(db)
                    snapshot_uuid = snapshot.id if snapshot else None
                    await task_svc.complete_task(
                        _UUID(task_id),
                        snapshot_id=snapshot_uuid,
                    )
            except Exception as te:
                logger.warning("[A5] TaskService complete_task failed: %s", te)

        update_dict: dict[str, Any] = {
            "metrics": metrics,
            "report": report_data,
            "current_step": "A5",
            "progress": 0.95,
        }
        # Baseline mode: also write to baseline_* fields for long-term storage
        if is_baseline:
            update_dict["baseline_metrics"] = metrics
            update_dict["baseline_report"] = report_data
            update_dict["baseline_fetch_results"] = fetch_results

        return Command(update=update_dict)

    except Exception as e:
        from app.workflow.events import send_error_event
        await send_error_event(session_id, "A5", str(e), recoverable=True)
        await send_progress_event(
            session_id=session_id,
            step="A5",
            step_name="数据分析报告",
            progress=1.0,
            message=f"分析过程出错: {str(e)}",
            status="error",
        )

        # Task milestone: A5 failed (Cycle 3, Module 1)
        task_id = state.get("task_id")
        if task_id:
            try:
                from app.core.database import AsyncSessionLocal
                from app.services.task_service import TaskService
                from uuid import UUID as _UUID
                async with AsyncSessionLocal() as db:
                    task_svc = TaskService(db)
                    await task_svc.fail_task(
                        _UUID(task_id),
                        error_message=str(e),
                        error_stage="A5",
                    )
            except Exception as te:
                logger.warning("[A5] TaskService fail_task failed: %s", te)

        return Command(
            update={
                "error_info": {
                    "step": "A5",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                },
                "execution_status": "error",
                "progress": 1.0,
            },
        )


def _calculate_metrics(fetch_results: list, brand_profile: dict) -> dict[str, Any]:
    """Calculate BWVS v2 metrics from fetch results.

    BWVS v2 = W1*mention_score + W2*sentiment_score
              + W3*coverage_score + W4*citation_score
    """
    if not fetch_results:
        return {
            "total_questions": 0,
            "total_mentions": 0,
            "mention_rate": 0.0,
            "bwvs_index": 0.0,
            "bwvs_breakdown": {
                "mention_score": 0.0,
                "sentiment_score": 50.0,
                "coverage_score": 0.0,
                "citation_score": 50.0,
                "weights": dict(BWVS_WEIGHTS),
                "formula": (
                    "BWVS = 40%*提及率 + 25%*情感 + 20%*覆盖度 + 15%*引用质量"
                ),
            },
            "sentiment_distribution": {
                "positive": 0,
                "neutral": 0,
                "negative": 0,
            },
            "platform_breakdown": {},
        }

    total_questions = len(fetch_results)
    total_mentions = 0
    platform_stats: dict[str, dict[str, int]] = {}
    platforms_with_mention: set[str] = set()

    # Sentiment distribution
    sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0}

    # Citation tracking
    total_citations = 0
    official_citations = 0
    brand_domain = extract_domain(brand_profile.get("official_website", ""))

    for result in fetch_results:
        for platform_result in result.get("platform_results", []):
            platform = platform_result.get("platform", "unknown")

            if platform not in platform_stats:
                platform_stats[platform] = {
                    "total": 0,
                    "mentions": 0,
                    "success": 0,
                }

            platform_stats[platform]["total"] += 1

            if platform_result.get("success"):
                platform_stats[platform]["success"] += 1

                answer = platform_result.get("answer", {})
                content = (
                    answer.get("content", "")
                    if isinstance(answer, dict)
                    else str(answer)
                )

                # Sentiment analysis
                sentiment = _analyze_sentiment(content)
                sentiment_counts[sentiment] += 1

                # Brand mention
                has_mention = (
                    answer.get("has_brand_mention", False)
                    if isinstance(answer, dict)
                    else False
                )
                if has_mention:
                    total_mentions += 1
                    platform_stats[platform]["mentions"] += 1
                    platforms_with_mention.add(platform)

                # Citation tracking
                citations = platform_result.get("citations", [])
                for citation in citations:
                    total_citations += 1
                    citation_url = (
                        citation.get("url", "")
                        if isinstance(citation, dict)
                        else ""
                    )
                    citation_domain = extract_domain(citation_url)
                    if brand_domain and citation_domain and (
                        citation_domain.endswith(brand_domain)
                        or brand_domain in citation_domain
                    ):
                        official_citations += 1

    # ---- Dimension 1: Mention score ----
    total_platform_results = sum(p["total"] for p in platform_stats.values())
    mention_rate = (
        total_mentions / total_platform_results
        if total_platform_results > 0
        else 0
    )
    # Amplification factor 1.2: 83.3% mention rate = full score
    mention_score = min(100.0, mention_rate * 120)

    # ---- Dimension 2: Sentiment score ----
    total_analyzed = sum(sentiment_counts.values())
    if total_analyzed > 0:
        pos_ratio = sentiment_counts["positive"] / total_analyzed
        neg_ratio = sentiment_counts["negative"] / total_analyzed
        sentiment_score = max(0.0, min(100.0, (pos_ratio - neg_ratio + 1) * 50))
    else:
        sentiment_score = 50.0  # Neutral default when no data

    # ---- Dimension 3: Platform coverage ----
    # Denominator fixed at len(PLATFORMS)=4, not dynamic
    total_platforms = len(PLATFORMS)
    coverage_score = (
        (len(platforms_with_mention) / total_platforms * 100)
        if total_platforms > 0
        else 0.0
    )

    # ---- Dimension 4: Citation quality ----
    citation_note: str | None = None
    if not brand_domain:
        citation_score = 50.0
        citation_note = "未配置品牌域名，引用质量使用中性默认分"
    elif total_citations > 0:
        citation_score = (official_citations / total_citations) * 100
    else:
        citation_score = 50.0  # Neutral default when no citations

    # ---- BWVS v2 composite score ----
    bwvs_index = (
        BWVS_WEIGHTS["mention"] * mention_score / 100
        + BWVS_WEIGHTS["sentiment"] * sentiment_score / 100
        + BWVS_WEIGHTS["coverage"] * coverage_score / 100
        + BWVS_WEIGHTS["citation"] * citation_score / 100
    )

    breakdown: dict[str, Any] = {
        "mention_score": round(mention_score, 2),
        "sentiment_score": round(sentiment_score, 2),
        "coverage_score": round(coverage_score, 2),
        "citation_score": round(citation_score, 2),
        "weights": dict(BWVS_WEIGHTS),
        "formula": (
            "BWVS = 40%*提及率 + 25%*情感 + 20%*覆盖度 + 15%*引用质量"
        ),
    }
    if citation_note:
        breakdown["citation_note"] = citation_note

    return {
        "total_questions": total_questions,
        "total_mentions": total_mentions,
        "mention_rate": round(mention_rate, 4),
        "bwvs_index": round(bwvs_index, 2),
        "bwvs_breakdown": breakdown,
        "sentiment_distribution": sentiment_counts,
        "platform_breakdown": platform_stats,
    }


def _calculate_competitor_metrics(
    fetch_results: list, competitors: list
) -> list[dict[str, Any]]:
    """从 fetch_results 计算每个竞品的真实指标。

    遍历 fetch_results 的完整结构（非扁平 all_answers），
    保留问题来源信息以追踪竞品出现位置。

    Returns:
        竞品列表，每个包含 name, relevance_score, mention_rate,
        avg_ranking, sentiment, appeared_in
    """
    if not competitors or not fetch_results:
        return [
            {
                "name": c.get("name", ""),
                "relevance_score": c.get("relevance_score", 0),
                "mention_rate": 0,
                "avg_ranking": 0,
                "sentiment": 0,
                "appeared_in": [],
            }
            for c in competitors
        ]

    # Count total successful answers for mention_rate denominator
    total_answers = sum(
        1 for r in fetch_results
        for pr in r.get("platform_results", [])
        if pr.get("success")
    )
    if total_answers == 0:
        return [
            {
                "name": c.get("name", ""),
                "relevance_score": c.get("relevance_score", 0),
                "mention_rate": 0,
                "avg_ranking": 0,
                "sentiment": 0,
                "appeared_in": [],
            }
            for c in competitors
        ]

    competitor_metrics = []
    mention_counts: list[tuple[int, str]] = []

    for c in competitors:
        name = c.get("name", "")
        if not name:
            competitor_metrics.append({
                "name": name,
                "relevance_score": c.get("relevance_score", 0),
                "mention_rate": 0,
                "avg_ranking": 0,
                "sentiment": 0,
                "appeared_in": [],
            })
            continue

        mentions = 0
        sentiment_scores: list[str] = []
        appeared_questions: list[dict] = []

        for result in fetch_results:
            question_text = result.get("question_text", "")
            for pr in result.get("platform_results", []):
                if not pr.get("success"):
                    continue
                answer = pr.get("answer", {})
                content = (
                    answer.get("content", "")
                    if isinstance(answer, dict)
                    else str(answer)
                )
                if content and name.lower() in content.lower():
                    mentions += 1
                    sentiment_scores.append(_analyze_sentiment(content))
                    appeared_questions.append({
                        "question": question_text[:60],
                        "platform": pr.get("platform", ""),
                    })

        mention_rate = mentions / total_answers
        mention_counts.append((mentions, name))

        sentiment_value = 0.0
        if sentiment_scores:
            score_map = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}
            sentiment_value = sum(
                score_map[s] for s in sentiment_scores
            ) / len(sentiment_scores)

        competitor_metrics.append({
            "name": name,
            "relevance_score": c.get("relevance_score", 0),
            "mention_rate": round(mention_rate, 4),
            "avg_ranking": 0,
            "sentiment": round(sentiment_value, 2),
            "appeared_in": appeared_questions[:5],
        })

    # Ranking by mention frequency (more mentions = better rank)
    mention_counts.sort(key=lambda x: x[0], reverse=True)
    name_to_rank = {
        name: rank + 1 for rank, (_, name) in enumerate(mention_counts)
    }
    for cm in competitor_metrics:
        if cm["name"] in name_to_rank:
            cm["avg_ranking"] = name_to_rank[cm["name"]]

    return competitor_metrics


def _get_a5_system_prompt(report_type: str = "persona") -> str:
    """Get A5 system prompt for enhanced 7-section report generation.

    Args:
        report_type: 'baseline' for industry panorama report,
                     'persona' for scenario-specific report.

    v2: Strong data-grounding constraints — every insight must cite actual
    fetch_results content. EEAT framework for recommendations.
    """
    if report_type == "baseline":
        context_intro = """## 报告类型：行业全景基线分析
本次分析是品牌的行业全景基线分析。问题来源是行业通用的用户搜索问题（非特定画像）。
请从行业全景视角分析品牌的 AI 搜索可见性：
- 品牌在整个行业 AI 搜索生态中的位置
- 哪些竞品在行业通用问题中更常被提及
- 行业级别的内容优化建议
- 所有指标和建议以"行业基线"为参照系

"""
    else:
        context_intro = """## 报告类型：场景分析报告
本次分析基于特定用户画像/场景。请从目标用户群体视角分析品牌表现。
如果提供了基线参考数据，请在报告中对比场景表现与行业基线的差异。

"""
    return context_intro + """你是 Specta AI 平台的数据分析专家和战略顾问，擅长基于品牌AI可见性数据，生成深度洞察和可执行的战略建议。

## 任务
基于提供的品牌档案、竞品信息、抓取结果（fetch_results）和核心指标，生成一份专业的品牌AI可见性分析报告。

## 核心约束（违反则报告无效）

### 数据引用要求
- 所有洞察必须引用 fetch_results 中的具体内容，例如："豆包在回答中多次提到X特征"、"DeepSeek 的3条样本中有2条未提及品牌"
- 明确区分两类来源：「实际数据」（来自 fetch_results 样本）和「行业经验」（来自你的知识库）
- 禁止使用"该平台表现良好"、"总体来看不错"等空洞描述，必须用具体数字支撑

### 平台差异分析必须包含量化指标
每个平台必须给出：
- 实际提及次数（从 platform_breakdown 中读取）
- 引用数量（从样本的 citations_count 读取）
- 回答字数范围（从样本的 answer_excerpt 估算）
- 品牌被提及时的具体表述片段（直接引用 answer_excerpt 中的文字）

### 竞品对比必须有量化对照表
comparison_matrix 中每个竞品必须包含实际计算的 mention_rate（从 fetch_results 中出现的竞品名称统计），不得凭空生成数字。
如果某竞品在 fetch_results 样本中完全未出现，明确标注"样本中未出现"，mention_rate 填 0。

## 报告结构要求（7 章节）

### 1. 执行摘要 (executive_summary)
- 一句话核心结论，必须引用实际 BWVS 数值（如"该品牌 BWVS 指数为 35.4，低于行业均值约 20 点，主要短板在 DeepSeek 平台覆盖率仅 33%"）
- BWVS 综合评分及评级
- 3 个最关键发现（每条必须有数字依据）
- 字数不少于 80 字

### 2. 行业洞察 (industry_insights)
- background（行业背景）：必须说明该行业在 AI 搜索中的整体格局，标注「基于行业经验」
- typical_performance（典型表现）：引用 fetch_results 中的具体内容说明本品牌与典型表现的差距，标注哪些来自「实际数据」
- trends（行业趋势）：列出 2-3 条，每条区分是「实际数据支撑」还是「行业经验推断」
- opportunities（机会点）：结合本次 fetch_results 的发现，指出具体机会

### 3. 平台差异分析 (platform_analysis)
对每个在 platform_breakdown 中有数据的平台，逐一分析，每个平台必须包含：
- mention_count（提及次数，从 platform_breakdown 读取）
- avg_citations（平均引用数，从样本 citations_count 计算均值）
- answer_length_range（回答字数范围，从 answer_excerpt 估算，格式如"200-400字"）
- actual_quotes（实际引用片段，从 answer_excerpt 中摘录 1-2 句品牌相关文字，若无提及则填"样本中未提及品牌"）
- content_preference（该平台内容偏好，说明依据）
- strengths（品牌在该平台的优势，必须结合 actual_quotes 说明）
- weaknesses（品牌短板，必须结合数据说明）
- optimization_tips（优化建议，具体到内容类型/关键词/结构）

### 4. 竞品深度对比 (competitor_deep_analysis)
如果有竞品数据，必须包含：
- overview（整体对比总结，引用实际 mention_rate 数字）
- comparison_matrix（量化对照表，每个竞品必须有字段）：
  - competitor（竞品名）
  - brand_mention_rate（本品牌提及率，来自 metrics）
  - competitor_mention_rate（竞品提及率，从 fetch_results 样本统计；若样本中未出现则为 0 并标注"样本未出现"）
  - vs_brand（高于/低于/持平，基于上述数字判断）
  - advantage_reasons（竞品优势原因，若有数据支撑则引用；若无则标注"推断"）
  - learnings（本品牌可借鉴之处，具体化）
- differentiation_strategy（差异化建议，结合实际数据）

### 5. 可执行优化建议 (actionable_recommendations)，遵循 EEAT 框架
EEAT = Experience（经验）/ Expertise（专业性）/ Authoritativeness（权威性）/ Trustworthiness（可信度）
每条建议必须：
- 对应一个 EEAT 维度（eeat_dimension: "E1"/"E2"/"A"/"T"）
- 明确区分：①当前做得好的具体特征（current_strength，结合 fetch_results 数据）②需要增强的具体场景/内容/数据方向（improvement_area）
- expected_impact 必须引用具体指标变化（如"预计将 DeepSeek 提及率从当前 33% 提升至 50%+"）
- 至少生成 3 条建议，覆盖不同 EEAT 维度

### 6. SWOT 分析 (strengths, weaknesses, opportunities, threats)
每项 2-4 条，每条必须附带具体数据支撑（引用 metrics 或 fetch_results 中的数字）

### 7. 风险提示 (risk_alerts)
品牌当前面临的 AI 可见性风险，每条必须说明具体触发条件和数据依据

## 输出格式
请严格按照以下 JSON 格式输出：

{
  "executive_summary": "执行摘要文本（必须引用具体BWVS数值，不少于80字）...",
  "key_findings": ["发现1（含数字）", "发现2（含数字）", "发现3（含数字）"],
  "industry_insights": {
    "background": "行业背景（标注：基于行业经验）",
    "typical_performance": "同行业典型表现（区分：实际数据/行业经验）",
    "trends": [{"trend": "趋势描述", "source": "实际数据/行业经验"}],
    "opportunities": ["机会1（结合本次fetch_results发现）"]
  },
  "platform_analysis": [{
    "platform": "deepseek",
    "platform_name": "DeepSeek",
    "mention_count": 2,
    "avg_citations": 1.5,
    "answer_length_range": "200-400字",
    "actual_quotes": ["实际引用片段1"],
    "performance_summary": "基于数据的表现概述",
    "content_preference": "内容偏好（说明依据）",
    "strengths": ["优势1（引用actual_quotes）"],
    "weaknesses": ["短板1（引用数字）"],
    "optimization_tips": ["具体建议1（内容类型/关键词/结构）"]
  }],
  "competitor_deep_analysis": {
    "overview": "整体对比总结（引用mention_rate数字）",
    "comparison_matrix": [{
      "competitor": "竞品名",
      "brand_mention_rate": 0.45,
      "competitor_mention_rate": 0.30,
      "vs_brand": "低于",
      "advantage_reasons": ["原因1（标注：数据支撑/推断）"],
      "learnings": ["具体可借鉴之处"]
    }],
    "differentiation_strategy": "差异化建议（结合实际数据）"
  },
  "actionable_recommendations": [{
    "priority": "P0",
    "title": "建议标题",
    "eeat_dimension": "E1",
    "current_strength": "当前做得好的地方（引用fetch_results具体数据）",
    "improvement_area": "需要增强的具体场景/内容/数据方向",
    "action": "具体行动步骤",
    "expected_impact": "预期效果（引用具体指标变化，如：将X平台提及率从N%提升至M%）",
    "difficulty": "低/中/高",
    "timeline": "预计时间"
  }],
  "strengths": ["优势1（含数字依据）", "优势2（含数字依据）"],
  "weaknesses": ["劣势1（含数字依据）", "劣势2（含数字依据）"],
  "opportunities": ["机会1（结合fetch_results）", "机会2"],
  "threats": ["威胁1（含触发条件）", "威胁2"],
  "risk_alerts": [{"level": "high/medium/low", "title": "风险标题", "description": "描述（含数据依据）", "trigger_condition": "触发条件", "mitigation": "应对措施"}],
  "recommendations": [{"title": "标题", "description": "描述", "expected_impact": "预期效果", "difficulty": "高/中/低", "priority": "P0/P1/P2"}],
  "action_plan": {"short_term": ["行动1"], "medium_term": ["行动1"], "long_term": ["行动1"]}
}

⚠️ 重要：直接以 { 开头输出 JSON，不要有任何解释或 Markdown 标记。"""


def _build_a5_user_content(
    brand_profile: dict,
    metrics: dict,
    fetch_results: list,
    competitors: list,
    marketing_personas: dict | None = None,
    previous_snapshot: dict | None = None,
    competitor_metrics: list | None = None,
    analysis_mode: str = "persona",
    baseline_metrics: dict | None = None,
    baseline_report: dict | None = None,
) -> str:
    """Build enhanced user content for A5 with structured tables for LLM."""
    sections = []

    # 1. Brand info
    sections.append(
        f"## 品牌信息\n"
        f"- 品牌名称: {brand_profile.get('brand_name', '')}\n"
        f"- 行业: {brand_profile.get('industry', '')}\n"
        f"- 核心产品: {', '.join(brand_profile.get('core_products', []))}\n"
        f"- 品牌定位: {brand_profile.get('brand_positioning', '')}\n"
        f"- 目标受众: {brand_profile.get('target_audience', '')}"
    )

    # 2. Core metrics — platform_breakdown as readable table
    platform_breakdown = metrics.get("platform_breakdown", {})
    if platform_breakdown:
        platform_table_lines = [
            "| 平台 | 总问题数 | 成功获取 | 品牌提及数 | 提及率 |",
            "|------|---------|---------|-----------|--------|",
        ]
        for platform, stats in platform_breakdown.items():
            total = stats.get("total", 0)
            success = stats.get("success", 0)
            mentions_count = stats.get("mentions", 0)
            rate = f"{mentions_count / total:.1%}" if total > 0 else "0.0%"
            platform_table_lines.append(
                f"| {platform} | {total} | {success} | {mentions_count} | {rate} |"
            )
        platform_table = "\n".join(platform_table_lines)
    else:
        platform_table = "暂无平台数据"

    sentiment_dist = metrics.get("sentiment_distribution", {})
    sections.append(
        f"## 核心指标\n"
        f"- 提及率: {metrics.get('mention_rate', 0):.2%}\n"
        f"- BWVS指数: {metrics.get('bwvs_index', 0):.2f}\n"
        f"- 总问题数: {metrics.get('total_questions', 0)}\n"
        f"- 总提及数: {metrics.get('total_mentions', 0)}\n"
        f"- BWVS各维度: 提及={metrics.get('bwvs_breakdown', {}).get('mention_score', 0):.1f}, "
        f"情感={metrics.get('bwvs_breakdown', {}).get('sentiment_score', 0):.1f}, "
        f"覆盖={metrics.get('bwvs_breakdown', {}).get('coverage_score', 0):.1f}, "
        f"引用={metrics.get('bwvs_breakdown', {}).get('citation_score', 0):.1f}\n\n"
        f"### 各平台详细表现\n{platform_table}\n\n"
        f"### 情感分布\n"
        f"- 正面: {sentiment_dist.get('positive', 0)}, "
        f"中性: {sentiment_dist.get('neutral', 0)}, "
        f"负面: {sentiment_dist.get('negative', 0)}"
    )

    # 3. Platform answer samples
    platform_samples = _extract_platform_samples(fetch_results, max_per_platform=3)
    if platform_samples:
        sections.append(
            "## 各平台回答样本\n"
            "（字段说明：answer_excerpt=回答摘录, has_brand_mention=是否提及品牌, "
            "citations_count=引用总数, citation_samples=前3条实际引用链接[url+title]）\n"
            + json.dumps(platform_samples, ensure_ascii=False, indent=2)
        )

    # 4. Competitors — structured quantitative table
    brand_mention_rate = metrics.get("mention_rate", 0)
    if competitor_metrics:
        comp_lines = [
            "## 竞品量化数据",
            f"（本品牌提及率: {brand_mention_rate:.1%}）",
            "",
            "| 竞品名称 | 提及率 | 与本品牌对比 | 情感倾向 | 出现排名 |",
            "|---------|--------|------------|---------|---------|",
        ]
        for cm in competitor_metrics:
            name = cm.get("name", "")
            mr = cm.get("mention_rate", 0)
            sentiment = cm.get("sentiment", 0)
            ranking = cm.get("avg_ranking", 0)
            vs = "高于" if mr > brand_mention_rate else ("低于" if mr < brand_mention_rate else "持平")
            sent_label = "正面" if sentiment > 0.2 else ("负面" if sentiment < -0.2 else "中性")
            comp_lines.append(
                f"| {name} | {mr:.1%} | {vs} | {sent_label}({sentiment:+.2f}) | #{ranking} |"
            )

        # Append appeared_in details
        for cm in competitor_metrics:
            appeared = cm.get("appeared_in", [])
            if appeared:
                comp_lines.append(f"\n**{cm['name']}** 出现在以下问题中：")
                for a in appeared:
                    comp_lines.append(f"  - [{a['platform']}] {a['question']}")

        sections.append("\n".join(comp_lines))
    elif competitors:
        comp_summary = [
            {"name": c.get("name", ""), "relevance_score": c.get("relevance_score", 0)}
            for c in competitors[:8]
        ]
        sections.append(
            f"## 竞品数据\n{json.dumps(comp_summary, ensure_ascii=False, indent=2)}"
        )

    # 5. User personas (if A2 succeeded)
    if marketing_personas:
        personas = marketing_personas.get("user_personas", [])
        if personas:
            persona_summary = [
                {
                    "name": p.get("persona_name", p.get("name", "")),
                    "description": p.get("persona_description", p.get("description", "")),
                    "priority": p.get("persona_priority", p.get("priority", "")),
                }
                for p in personas[:4]
            ]
            sections.append(
                f"## 目标用户画像\n"
                f"{json.dumps(persona_summary, ensure_ascii=False, indent=2)}"
            )

    # 6. Previous snapshot for comparison
    if previous_snapshot:
        sections.append(
            f"## 上次分析数据 (日期: {previous_snapshot.get('date', 'N/A')})\n"
            f"{json.dumps(previous_snapshot, ensure_ascii=False, indent=2)}"
        )

    # Inject baseline context for persona mode comparison
    if analysis_mode == "persona" and baseline_metrics:
        baseline_bwvs = baseline_metrics.get("bwvs_index", 0)
        baseline_mention = baseline_metrics.get("mention_rate", 0)
        baseline_findings = ""
        if baseline_report:
            findings = baseline_report.get("key_findings", [])[:3]
            if findings:
                baseline_findings = "\n".join(f"- {f}" for f in findings)
        sections.append(
            f"## 基线报告参考数据\n"
            f"- 基线 BWVS: {baseline_bwvs:.1f}\n"
            f"- 基线提及率: {baseline_mention:.1%}\n"
            f"- 基线核心发现:\n{baseline_findings}\n\n"
            f"请在场景报告中对比基线数据，说明该场景表现与行业基线的差异。"
            f"在总览部分增加 '场景 BWVS vs 基线 BWVS' 的对比数据。"
        )

    sections.append(
        "\n请生成完整的 7 章节分析报告（执行摘要、行业洞察、平台差异分析、"
        "竞品深度对比、可执行建议、SWOT分析、风险提示）。"
    )

    return "\n\n".join(sections)


def _extract_platform_samples(
    fetch_results: list, max_per_platform: int = 3
) -> dict[str, list[dict]]:
    """从 fetch_results 中提取各平台的回答样本。

    每个平台最多 max_per_platform 条，避免 context 过长。
    优先选取品牌被提及的回答。
    """
    platform_samples: dict[str, list[dict]] = {}

    for fr in fetch_results:
        question_text = fr.get("question_text", "")
        for pr in fr.get("platform_results", []):
            platform = pr.get("platform", "unknown")
            if platform not in platform_samples:
                platform_samples[platform] = []

            if len(platform_samples[platform]) >= max_per_platform:
                continue

            if pr.get("success"):
                answer = pr.get("answer", {})
                content = answer.get("content", "") if isinstance(answer, dict) else str(answer)
                has_mention = answer.get("has_brand_mention", False) if isinstance(answer, dict) else False

                # Truncate long answers
                if len(content) > 500:
                    content = content[:500] + "..."

                citations = pr.get("citations", [])
                # Provide first 3 citation URLs/titles so A5 prompt can reference
                # actual sources when evaluating Authoritativeness (EEAT-A)
                sample_citations = [
                    {
                        "url": c.get("url", ""),
                        "title": c.get("title", "")[:60],
                    }
                    for c in citations[:3]
                    if isinstance(c, dict) and c.get("url")
                ]
                platform_samples[platform].append({
                    "question": question_text[:80],
                    "answer_excerpt": content,
                    "has_brand_mention": has_mention,
                    "citations_count": len(citations),
                    "citation_samples": sample_citations,  # 实际引用链接样本
                })

    return platform_samples


def _normalize_report_data(report_data: dict[str, Any]) -> dict[str, Any]:
    """规范化 LLM 输出的报告数据，处理缺失字段。

    LLM 输出可能漏掉新增的 optional 字段，
    此函数确保所有字段都有安全的默认值。
    """
    # Required fields
    report_data.setdefault("executive_summary", "分析已完成。")
    report_data.setdefault("key_findings", [])
    report_data.setdefault("strengths", [])
    report_data.setdefault("weaknesses", [])
    report_data.setdefault("opportunities", [])
    report_data.setdefault("threats", [])
    report_data.setdefault("recommendations", [])
    report_data.setdefault("action_plan", {})

    # New optional fields -- None or empty list as defaults
    report_data.setdefault("industry_insights", None)
    report_data.setdefault("platform_analysis", [])
    report_data.setdefault("competitor_deep_analysis", None)
    report_data.setdefault("actionable_recommendations", [])
    report_data.setdefault("risk_alerts", [])

    return report_data


def _generate_fallback_report(metrics: dict, brand_profile: dict) -> dict[str, Any]:
    """Generate fallback report when LLM fails.

    Includes all new enhanced fields with safe defaults.
    """
    brand_name = brand_profile.get("brand_name", "品牌")
    mention_rate = metrics.get("mention_rate", 0)
    bwvs_index = metrics.get("bwvs_index", 0)

    # Determine visibility level
    if mention_rate >= 0.7:
        summary = (
            f"{brand_name} 的 AI 搜索可见度分析已完成。"
            f"整体提及率为 {mention_rate:.1%}，BWVS 指数为 {bwvs_index:.1f}，表现优秀。"
        )
    elif mention_rate >= 0.4:
        summary = (
            f"{brand_name} 的 AI 搜索可见度分析已完成。"
            f"整体提及率为 {mention_rate:.1%}，BWVS 指数为 {bwvs_index:.1f}，仍有提升空间。"
        )
    else:
        summary = (
            f"{brand_name} 的 AI 搜索可见度分析已完成。"
            f"整体提及率为 {mention_rate:.1%}，BWVS 指数为 {bwvs_index:.1f}，建议优化内容策略。"
        )

    return {
        "executive_summary": summary,
        "key_findings": [
            f"品牌整体提及率: {mention_rate:.1%}",
            f"BWVS 综合指数: {bwvs_index:.1f}",
        ],
        # New enhanced fields with defaults
        "industry_insights": None,
        "platform_analysis": [],
        "competitor_deep_analysis": None,
        "actionable_recommendations": [],
        "risk_alerts": [],
        # Existing fields
        "strengths": [f"品牌在 AI 搜索中有基础曝光 (提及率 {mention_rate:.1%})"] if mention_rate > 0.1 else [],
        "weaknesses": [],
        "opportunities": ["建议增加品牌相关内容在权威平台的布局"],
        "threats": [],
        "recommendations": [],
        "action_plan": {},
        # Degradation marker
        "_degraded": True,
    }
