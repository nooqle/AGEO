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


def _compute_platform_sentiment(fetch_results: list, platform_key: str) -> float:
    """计算指定平台的情感得分 (0-100)。

    遍历 fetch_results，对匹配平台的成功回答进行情感分析，
    将 -1~1 的原始得分映射到 0~100 区间。
    """
    scores: list[float] = []
    for result in fetch_results:
        for pr in result.get("platform_results", []):
            if pr.get("platform", "").lower() != platform_key.lower():
                continue
            if not pr.get("success"):
                continue
            answer = pr.get("answer", {})
            content = (
                answer.get("content", "")
                if isinstance(answer, dict)
                else str(answer)
            )
            s = _analyze_sentiment(content)
            scores.append(
                {"positive": 1.0, "neutral": 0.0, "negative": -1.0}.get(s, 0.0)
            )
    if not scores:
        return 50.0
    return round(max(0.0, min(100.0, (sum(scores) / len(scores) + 1) * 50)), 1)


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

        # Generate report using LLM -- split into 2 calls to stay within
        # token limits and avoid JSON truncation.
        # Call 1 (core): executive_summary, platform_analysis, competitor_deep_analysis,
        #                 actionable_recommendations, key_findings
        # Call 2 (supplementary): industry_insights, SWOT, risk_alerts, action_plan
        report_data = None
        try:
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

            # --- Call 1: Core report sections ---
            core_prompt = _get_a5_core_prompt(report_type=analysis_mode)
            response1 = await call_llm_streaming(
                session_id=session_id,
                model=model,
                messages=[
                    {"role": "system", "content": core_prompt},
                    {"role": "user", "content": user_content},
                ],
                step="A5",
                step_name="数据分析报告（核心章节）",
                progress_start=0.82,
                progress_end=0.90,
                max_tokens=8192,
            )
            core_data = parse_llm_response(response1)

            if core_data:
                report_data = core_data
                logger.info(
                    "[A5] Core report generated: summary=%d chars, platforms=%d, recs=%d",
                    len(core_data.get("executive_summary", "")),
                    len(core_data.get("platform_analysis", [])),
                    len(core_data.get("actionable_recommendations", [])),
                )

                # --- Call 2: Supplementary sections ---
                try:
                    supp_prompt = _get_a5_supplementary_prompt(report_type=analysis_mode)
                    # Include core results summary so LLM can reference them
                    supp_context = (
                        f"{user_content}\n\n"
                        f"## 已完成的核心分析结果\n"
                        f"- 执行摘要: {core_data.get('executive_summary', '')[:200]}\n"
                        f"- 核心发现: {json.dumps(core_data.get('key_findings', [])[:3], ensure_ascii=False)}\n"
                        f"- 平台数量: {len(core_data.get('platform_analysis', []))}\n"
                        f"- 建议数量: {len(core_data.get('actionable_recommendations', []))}\n"
                    )
                    response2 = await call_llm_streaming(
                        session_id=session_id,
                        model=model,
                        messages=[
                            {"role": "system", "content": supp_prompt},
                            {"role": "user", "content": supp_context},
                        ],
                        step="A5",
                        step_name="数据分析报告（补充章节）",
                        progress_start=0.90,
                        progress_end=0.95,
                        max_tokens=6144,
                    )
                    supp_data = parse_llm_response(response2)

                    if supp_data:
                        # Merge supplementary into core report
                        for key in ("industry_insights", "strengths", "weaknesses",
                                    "opportunities", "threats", "risk_alerts",
                                    "action_plan"):
                            if supp_data.get(key):
                                report_data[key] = supp_data[key]
                        logger.info("[A5] Supplementary sections merged successfully")
                    else:
                        logger.warning("[A5] Supplementary LLM call returned no valid JSON, core report still usable")
                except Exception as supp_err:
                    logger.warning("[A5] Supplementary report call failed (core report still usable): %s", supp_err)

            # Partial degradation validation: only reject if executive_summary is missing
            if report_data:
                executive_summary = report_data.get("executive_summary", "")
                if len(executive_summary) < 30:
                    logger.warning(
                        "[A5] executive_summary too short (%d chars), triggering fallback",
                        len(executive_summary),
                    )
                    report_data = None
                else:
                    # Log missing optional sections as warnings, don't invalidate
                    missing = []
                    if not report_data.get("platform_analysis"):
                        missing.append("platform_analysis")
                    if not report_data.get("actionable_recommendations"):
                        missing.append("actionable_recommendations")
                    if competitors and not report_data.get("competitor_deep_analysis"):
                        missing.append("competitor_deep_analysis")
                    if not report_data.get("industry_insights"):
                        missing.append("industry_insights")
                    if not report_data.get("risk_alerts"):
                        missing.append("risk_alerts")
                    if missing:
                        logger.warning("[A5] Report partial: missing sections: %s", ", ".join(missing))

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
        report_data = _enrich_report_data(
            report_data, metrics, competitor_metrics, fetch_results, brand_profile
        )

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
                    {
                        "type": "strength",
                        "title": (s.get("title", str(s)) if isinstance(s, dict) else str(s)),
                        "description": (s.get("evidence", s.get("title", str(s))) if isinstance(s, dict) else str(s)),
                    }
                    for s in report_data.get("strengths", [])
                ] + [
                    {
                        "type": "weakness",
                        "title": (w.get("title", str(w)) if isinstance(w, dict) else str(w)),
                        "description": (w.get("evidence", w.get("title", str(w))) if isinstance(w, dict) else str(w)),
                    }
                    for w in report_data.get("weaknesses", [])
                ] + [
                    {"type": "opportunity", "title": o, "description": o}
                    for o in report_data.get("opportunities", [])
                ],
                "recommendations": [
                    {
                        "priority": idx + 1,
                        "title": r.get("title", ""),
                        "rationale": r.get("action", r.get("improvement_area", "")),
                        "eeat_dimension": r.get("eeat_dimension", ""),
                        "current_strength": r.get("current_strength", ""),
                        "expected_impact": r.get("expected_impact", ""),
                        "difficulty": r.get("difficulty", ""),
                        "timeline": r.get("timeline", ""),
                    }
                    for idx, r in enumerate(report_data.get("actionable_recommendations", []))
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
                "citation_analysis": metrics.get("citation_analysis", {}),
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
            "progress": 1.0,
        }
        # Baseline mode: also write to baseline_* fields for long-term storage
        if is_baseline:
            update_dict["baseline_metrics"] = metrics
            update_dict["baseline_report"] = report_data
            update_dict["baseline_fetch_results"] = fetch_results

        await send_progress_event(
            session_id=session_id,
            step="A5",
            step_name="数据分析报告",
            progress=1.0,
            message="分析完成",
            status="completed",
        )

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
            "citation_analysis": {},
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
    domain_stats: dict[str, dict] = {}  # domain -> {count, is_official, sample_titles}
    platform_citation_stats: dict[str, dict] = {}  # platform -> citation stats

    for result in fetch_results:
        for platform_result in result.get("platform_results", []):
            platform = platform_result.get("platform", "unknown")

            if platform not in platform_stats:
                platform_stats[platform] = {
                    "total": 0,
                    "mentions": 0,
                    "success": 0,
                }

            # Initialize platform citation stats on first encounter
            if platform not in platform_citation_stats:
                platform_citation_stats[platform] = {
                    "total_citations": 0,
                    "official_count": 0,
                    "total_answers": 0,
                    "answers_with_citations": 0,
                }

            platform_stats[platform]["total"] += 1
            platform_citation_stats[platform]["total_answers"] += 1

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
                answer_citation_count = 0
                answer_official_count = 0
                for citation in citations:
                    total_citations += 1
                    answer_citation_count += 1
                    citation_url = (
                        citation.get("url", "")
                        if isinstance(citation, dict)
                        else ""
                    )
                    citation_title = (
                        citation.get("title", "")
                        if isinstance(citation, dict)
                        else ""
                    )
                    citation_domain = extract_domain(citation_url)

                    # Strict official domain matching (fixes ke.com matching nike.com)
                    is_official = bool(
                        brand_domain
                        and citation_domain
                        and (
                            citation_domain == brand_domain
                            or citation_domain.endswith("." + brand_domain)
                        )
                    )

                    # Collect domain stats
                    if citation_domain:
                        if citation_domain not in domain_stats:
                            domain_stats[citation_domain] = {
                                "count": 0,
                                "is_official": is_official,
                                "sample_titles": [],
                            }
                        domain_stats[citation_domain]["count"] += 1
                        if (
                            citation_title
                            and len(domain_stats[citation_domain]["sample_titles"]) < 3
                        ):
                            domain_stats[citation_domain]["sample_titles"].append(
                                citation_title
                            )

                    if is_official:
                        official_citations += 1
                        answer_official_count += 1

                # Update platform citation stats
                platform_citation_stats[platform]["total_citations"] += answer_citation_count
                platform_citation_stats[platform]["official_count"] += answer_official_count
                if answer_citation_count > 0:
                    platform_citation_stats[platform]["answers_with_citations"] += 1

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

    # ---- Citation analysis aggregation ----
    sorted_domains = sorted(
        domain_stats.items(), key=lambda x: x[1]["count"], reverse=True
    )[:10]
    total_cit = max(total_citations, 1)  # avoid division by zero

    citation_analysis: dict[str, Any] = {
        "total_citations": total_citations,
        "unique_domains": len(domain_stats),
        "official_citations": official_citations,
        "official_share": (
            round(official_citations / total_cit * 100, 1)
            if total_citations > 0
            else 0.0
        ),
        "brand_domain": brand_domain or "",
        "top_domains": [
            {
                "domain": domain,
                "count": stats["count"],
                "share": round(stats["count"] / total_cit * 100, 1),
                "is_official": stats["is_official"],
                "sample_titles": stats["sample_titles"][:2],
            }
            for domain, stats in sorted_domains
        ],
        "platform_citation_stats": platform_citation_stats,
        "note": "引用数据基于各 AI 平台回答中的参考来源提取",
    }

    return {
        "total_questions": total_questions,
        "total_mentions": total_mentions,
        "mention_rate": round(mention_rate, 4),
        "bwvs_index": round(bwvs_index, 2),
        "bwvs_breakdown": breakdown,
        "sentiment_distribution": sentiment_counts,
        "platform_breakdown": platform_stats,
        "citation_analysis": citation_analysis,
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


def _get_a5_report_context_intro(report_type: str) -> str:
    """Get context intro section based on report type."""
    if report_type == "baseline":
        return """## 报告类型：行业全景基线分析
本次分析是品牌的行业全景基线分析。问题来源是行业通用的用户搜索问题（非特定画像）。
请从行业全景视角分析品牌的 AI 搜索可见性。

"""
    return """## 报告类型：场景分析报告
本次分析基于特定用户画像/场景。请从目标用户群体视角分析品牌表现。
如果提供了基线参考数据，请在报告中对比场景表现与行业基线的差异。

"""


def _get_a5_core_prompt(report_type: str = "persona") -> str:
    """A5 system prompt for CORE report sections (Call 1 of 2).

    Generates: executive_summary, key_findings, platform_analysis,
    competitor_deep_analysis, actionable_recommendations.
    """
    return _get_a5_report_context_intro(report_type) + """你是 Specta AI 的数据分析专家。基于品牌档案、抓取结果和指标，生成核心分析章节。

## 核心约束
- 所有洞察必须引用 fetch_results 中的具体内容，用具体数字支撑
- 禁止空洞描述如"表现良好"、"总体不错"
- 竞品数据必须从 fetch_results 样本统计，不得凭空生成

## 输出 JSON（5 个核心章节）

{
  "executive_summary": "执行摘要（引用BWVS数值，不少于80字）",
  "key_findings": ["发现1（含数字）", "发现2", "发现3"],
  "platform_analysis": [{
    "platform": "deepseek",
    "platform_name": "DeepSeek",
    "mention_count": 2,
    "avg_citations": 1.5,
    "answer_length_range": "200-400字",
    "actual_quotes": ["实际引用片段"],
    "performance_summary": "表现概述",
    "content_preference": "内容偏好",
    "strengths": ["优势"],
    "weaknesses": ["短板"],
    "optimization_tips": ["具体建议"]
  }],
  "competitor_deep_analysis": {
    "overview": "对比总结（引用数字）",
    "comparison_matrix": [{
      "competitor": "竞品名",
      "brand_mention_rate": 0.45,
      "competitor_mention_rate": 0.30,
      "vs_brand": "低于",
      "advantage_reasons": ["原因"],
      "learnings": ["可借鉴之处"]
    }],
    "differentiation_strategy": "差异化建议"
  },
  "actionable_recommendations": [{
    "priority": "P0",
    "title": "建议标题",
    "eeat_dimension": "E1",
    "current_strength": "当前优势（引用数据）",
    "improvement_area": "改进方向",
    "action": "具体行动",
    "expected_impact": "预期效果（含指标变化）",
    "difficulty": "低/中/高",
    "timeline": "时间"
  }]
}

⚠️ 直接以 { 开头输出 JSON，不要有任何解释或 Markdown 标记。"""


def _get_a5_supplementary_prompt(report_type: str = "persona") -> str:
    """A5 system prompt for SUPPLEMENTARY sections (Call 2 of 2).

    Generates: industry_insights, SWOT, risk_alerts, recommendations, action_plan.
    """
    return _get_a5_report_context_intro(report_type) + """你是 Specta AI 的数据分析专家。核心报告已完成，现在生成补充分析章节。

## 输出 JSON（补充章节）

{
  "industry_insights": {
    "background": "行业背景（标注：基于行业经验）",
    "typical_performance": "典型表现（区分数据来源）",
    "trends": [{"trend": "趋势", "source": "实际数据/行业经验"}],
    "opportunities": ["机会点"]
  },
  "strengths": [{"title": "优势标题", "scenario": "适用场景（如：送礼推荐、香氛科普）", "platforms": ["表现好的平台"], "evidence": "具体数据支撑（引用 fetch_results）", "eeat_factor": "E-E-A-T 中的哪个维度"}],
  "weaknesses": [{"title": "劣势标题", "scenario": "薄弱场景（如：性价比对比、成分分析）", "platforms": ["表现差的平台"], "evidence": "具体数据支撑", "improvement_hint": "改进方向"}],
  "opportunities": ["机会1", "机会2"],
  "threats": ["威胁1", "威胁2"],
  "risk_alerts": [{"level": "high/medium/low", "title": "风险标题", "description": "描述", "trigger_condition": "触发条件", "mitigation": "应对措施"}],
  "action_plan": {"short_term": ["行动"], "medium_term": ["行动"], "long_term": ["行动"]}
}

⚠️ 直接以 { 开头输出 JSON，不要有任何解释或 Markdown 标记。"""


def _get_a5_system_prompt(report_type: str = "persona") -> str:
    """Legacy single-call prompt — kept for reference but no longer used by default."""
    return _get_a5_core_prompt(report_type)


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


def _enrich_report_data(
    report_data: dict[str, Any],
    metrics: dict[str, Any],
    competitor_metrics: list[dict[str, Any]],
    fetch_results: list,
    brand_profile: dict,
) -> dict[str, Any]:
    """用已计算的量化指标充实 LLM 的描述性报告。

    解决前端期望字段名与 LLM 输出字段名不匹配的问题。
    使用 setdefault 保持 LLM 已有值不被覆盖。
    """
    platform_breakdown = metrics.get("platform_breakdown", {})

    # --- 平台分析: 注入计算指标 ---
    platform_analysis = report_data.get("platform_analysis", [])
    for pa in platform_analysis:
        platform_key = str(pa.get("platform") or pa.get("name") or "")

        # Step 1: Map LLM field names → frontend expected names (before setdefault)
        if "performance_summary" in pa and "summary" not in pa:
            pa["summary"] = pa["performance_summary"]
        if "mention_count" in pa and "mentions" not in pa:
            pa["mentions"] = pa["mention_count"]

        # Step 2: Match platform_breakdown keys (case-insensitive)
        pb = None
        for key, val in platform_breakdown.items():
            if key.lower() == platform_key.lower():
                pb = val
                break

        # Step 3: Fill missing fields with calculated values (setdefault preserves LLM/renamed values)
        if pb:
            total = pb.get("total", 0)
            mentions_val = pb.get("mentions", 0)
            pa.setdefault("mentions", mentions_val)
            pa.setdefault("total_questions", total)
            pa.setdefault(
                "mention_rate",
                round(mentions_val / total, 4) if total > 0 else 0.0,
            )
            pa.setdefault(
                "sentiment",
                _compute_platform_sentiment(fetch_results, platform_key),
            )
            pa.setdefault(
                "status",
                "success" if pb.get("success", 0) > 0 else "failed",
            )

    # --- 竞品矩阵: 注入计算指标 ---
    comp_deep = report_data.get("competitor_deep_analysis")
    if isinstance(comp_deep, dict):
        matrix = comp_deep.get("comparison_matrix", [])

        # Build lookup from competitor_metrics
        cm_lookup = {
            cm["name"].lower(): cm
            for cm in competitor_metrics
            if cm.get("name")
        }

        for row in matrix:
            # Map LLM field name → frontend expected name
            if "competitor" in row and "name" not in row:
                row["name"] = row["competitor"]
            if "competitor_mention_rate" in row and "mention_rate" not in row:
                row["mention_rate"] = row["competitor_mention_rate"]

            name_lower = str(
                row.get("name") or row.get("competitor") or ""
            ).lower()
            cm = cm_lookup.get(name_lower)

            if cm:
                row.setdefault("mention_rate", cm.get("mention_rate", 0))
                # Convert sentiment from -1~1 to 0~100
                raw_sentiment = cm.get("sentiment", 0)
                row.setdefault(
                    "sentiment",
                    round(max(0, min(100, (raw_sentiment + 1) * 50)), 1),
                )
                # Coverage: unique platforms / total platforms
                appeared_in = cm.get("appeared_in", [])
                unique_platforms = len(
                    set(
                        a.get("platform", "")
                        for a in appeared_in
                        if a.get("platform")
                    )
                )
                total_platforms = len(PLATFORMS) if PLATFORMS else 4
                coverage = (
                    unique_platforms / total_platforms
                    if total_platforms > 0
                    else 0
                )
                row.setdefault("coverage", round(coverage, 4))

                # Simplified BWVS: same formula as main but citation=50
                mr_score = min(100.0, row.get("mention_rate", 0) * 120)
                sent_score = row.get("sentiment", 50)
                cov_score = row.get("coverage", 0) * 100
                bwvs = (
                    40 * mr_score + 25 * sent_score + 20 * cov_score + 15 * 50
                ) / 100
                row.setdefault("bwvs", round(min(100, bwvs), 1))

        # Insert brand self row at top if not present
        has_self = any(r.get("is_self") for r in matrix)
        if not has_self and brand_profile.get("brand_name"):
            breakdown = metrics.get("bwvs_breakdown", {})
            self_row = {
                "name": brand_profile["brand_name"],
                "is_self": True,
                "bwvs": round(metrics.get("bwvs_index", 0), 1),
                "mention_rate": round(metrics.get("mention_rate", 0), 4),
                "sentiment": round(breakdown.get("sentiment_score", 50), 1),
                "coverage": round(
                    breakdown.get("coverage_score", 0) / 100, 4
                ),
            }
            matrix.insert(0, self_row)

        comp_deep["comparison_matrix"] = matrix

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
