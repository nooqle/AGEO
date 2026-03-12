"""A5 Node: Data Analytics and Report Generation.

This module contains the A5 node implementation for analyzing fetch results
and generating comprehensive reports with BWVS metrics.
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from langgraph.types import Command

from app.core.utils import extract_domain
# A5 is being split by responsibility: scenario/report contracts, prompt assembly,
# user-facing sanitization, and persistence are kept in dedicated modules.
from app.workflow.a5 import contract as a5_contract
from app.workflow.a5 import metrics as a5_metrics
from app.workflow.a5 import keywords as a5_keywords
from app.workflow.a5 import prompt as a5_prompt
from app.workflow.a5 import postprocess as a5_postprocess
from app.workflow.a5 import sanitizer as a5_sanitizer
from app.workflow.a5 import sentiment as a5_sentiment
from app.workflow.a5.persistence import build_report_artifact_data
from app.workflow.nodes_a4 import PLATFORMS

logger = logging.getLogger(__name__)

# Shared BWVS weights and sentiment helpers now live in app.workflow.a5.metrics.

from app.workflow.state import AgentState
from app.workflow.events import (
    send_progress_event,
    send_stage_result,
)
from app.workflow.brand_mentions import content_mentions_brand
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
        step="data_analytics",
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

        # Thread 6: precompute scenario-first V2 structures before the LLM call
        # so the prompt can reason about scenarios, risks, and action priorities
        # instead of only aggregate scores.
        source_overview = a5_contract._build_source_overview(metrics.get("citation_analysis", {}))
        mention_sentiment_analysis = a5_sentiment.build_mention_sentiment_analysis(
            fetch_results,
            brand_profile,
            competitors,
        )
        scenario_matrix = a5_contract._build_scenario_matrix(
            fetch_results,
            brand_profile,
            competitors,
            source_overview,
        )
        risk_map = a5_contract._build_risk_map(scenario_matrix)
        competitor_battles = a5_contract._build_competitor_battles(scenario_matrix, competitors)
        action_queue = a5_contract._build_action_queue(scenario_matrix, risk_map)
        summary_metrics = a5_contract._build_summary_metrics(
            metrics,
            scenario_matrix,
            risk_map,
            source_overview,
        )

        await send_progress_event(
            session_id=session_id,
            step="data_analytics",
            step_name="数据分析报告",
            progress=0.75,
            message=(
                f"提及率: {metrics.get('mention_rate', 0):.1%} | "
                f"官网引用率: {summary_metrics.get('official_citation_rate', 0):.1%} | "
                f"高风险问题: {summary_metrics.get('high_risk_scenario_count', 0)} 个"
            ),
        )

        # Stage result: metrics preview before LLM report generation
        metrics_preview_data = {
            "mention_rate": f"{metrics.get('mention_rate', 0):.1%}",
            "official_citation_rate": f"{summary_metrics.get('official_citation_rate', 0):.1%}",
            "scenario_hit_count": summary_metrics.get("scenario_hit_count", 0),
            "missing_high_value_scenario_count": summary_metrics.get("missing_high_value_scenario_count", 0),
            "high_risk_scenario_count": summary_metrics.get("high_risk_scenario_count", 0),
            "total_mentions": metrics.get("total_mentions", 0),
            "total_questions": metrics.get("total_questions", 0),
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
            user_content = a5_prompt._build_a5_user_content(
                brand_profile, metrics, fetch_results, competitors,
                marketing_personas=marketing_personas,
                previous_snapshot=previous_snapshot_data,
                competitor_metrics=competitor_metrics,
                analysis_mode=analysis_mode,
                baseline_metrics=state.get("baseline_metrics"),
                baseline_report=state.get("baseline_report"),
                summary_metrics=summary_metrics,
                scenario_matrix=scenario_matrix,
                competitor_battles=competitor_battles,
                risk_map=risk_map,
                action_queue=action_queue,
                source_overview=source_overview,
            mention_sentiment_analysis=mention_sentiment_analysis,
            )
            model = get_llm_model_compat()

            # --- Call 1: Core report sections ---
            core_prompt = a5_prompt._get_a5_core_prompt(report_type=analysis_mode)
            response1 = await call_llm_streaming(
                session_id=session_id,
                model=model,
                messages=[
                    {"role": "system", "content": core_prompt},
                    {"role": "user", "content": user_content},
                ],
                step="data_analytics",
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
                    supp_prompt = a5_prompt._get_a5_supplementary_prompt(report_type=analysis_mode)
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
                        step="data_analytics",
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
            report_data = a5_postprocess.generate_fallback_report(metrics, brand_profile)
            report_data["_degraded"] = True
            report_data["_degradation_note"] = (
                "本报告基于原始数据自动生成，未经 AI 深度分析"
            )
            from app.workflow.resilience import DegradationRegistry

            await DegradationRegistry.send_degradation_notice(
                session_id, "A5"
            )

        # Normalize report data: ensure all new fields have safe defaults
        report_data = a5_sanitizer._normalize_report_data(report_data)
        report_data = a5_postprocess.enrich_report_data(
            report_data, metrics, competitor_metrics, fetch_results, brand_profile
        )
        report_data = a5_sanitizer._sanitize_user_facing_report(report_data)

        await send_progress_event(
            session_id=session_id,
            step="data_analytics",
            step_name="数据分析报告",
            progress=0.95,
            message="报告生成完成，准备输出...",
        )

        summary = generate_a5_summary(metrics, report_data)

        from app.workflow.events import send_action_log_event
        await send_action_log_event(
            session_id, "agent_summary", summary, step="data_analytics", is_complete=True
        )

        # Build fetch_results summary for analytics service
        fetch_results_summary = []
        recovered_brand_mentions = 0
        for fr in fetch_results:
            for pr in fr.get("platform_results", []):
                answer_payload = pr.get("answer", {}) if isinstance(pr.get("answer"), dict) else {}
                answer_content = answer_payload.get("content", "") if isinstance(answer_payload, dict) else ""
                stored_has_brand_mention = bool(answer_payload.get("has_brand_mention", False)) if isinstance(answer_payload, dict) else False
                computed_has_brand_mention = content_mentions_brand(answer_content, brand_profile)
                if not stored_has_brand_mention and computed_has_brand_mention:
                    recovered_brand_mentions += 1
                fetch_results_summary.append({
                    "platform": pr.get("platform", "unknown"),
                    "success": pr.get("success", False),
                    "has_brand_mention": computed_has_brand_mention,
                    "citations": pr.get("citations", []),
                })

        if recovered_brand_mentions:
            logger.info(
                "[A5] Recovered stale brand-mention flags from fetch results: %d",
                recovered_brand_mentions,
            )

        # Build Report V2 contract fields (thread 5)
        report_v2_sections = a5_contract._build_report_v2_sections(
            report_data,
            summary_metrics,
            scenario_matrix,
            competitor_battles,
            risk_map,
            action_queue,
            source_overview,
            metrics.get("citation_analysis", {}),
            mention_sentiment_analysis,
        )

        report_data["summary_metrics"] = summary_metrics
        report_data["scenario_matrix"] = scenario_matrix
        report_data["competitor_battles"] = competitor_battles
        report_data["risk_map"] = risk_map
        report_data["action_queue"] = action_queue
        report_data["source_overview"] = source_overview
        report_data["mention_sentiment_analysis"] = mention_sentiment_analysis

        # Persist lightweight V2 fields into metrics/raw_data as well so
        # snapshots and downstream analytics can read them without reparsing
        # the full report payload.
        metrics["summary_metrics"] = summary_metrics
        metrics["scenario_matrix"] = scenario_matrix
        metrics["competitor_battles"] = competitor_battles
        metrics["risk_map"] = risk_map
        metrics["action_queue"] = action_queue
        metrics["source_overview"] = source_overview
        metrics["mention_sentiment_analysis"] = mention_sentiment_analysis

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
        report_category = "baseline" if is_baseline else "scenario"
        report_artifact_data = build_report_artifact_data(
            brand_name=brand_profile.get('brand_name', '品牌'),
            is_baseline=is_baseline,
            metrics=metrics,
            report_data=report_data,
            summary_metrics=summary_metrics,
            fetch_results_summary=fetch_results_summary,
            competitor_metrics=competitor_metrics,
            delta_vs_previous=delta_vs_previous,
            report_v2_sections=report_v2_sections,
            scenario_matrix=scenario_matrix,
            competitor_battles=competitor_battles,
            risk_map=risk_map,
            action_queue=action_queue,
            source_overview=source_overview,
            mention_sentiment_analysis=mention_sentiment_analysis,
        )
        artifact_message_id = await save_and_send_artifact(
            session_id=session_id,
            output_type=report_output_type,
            title=report_title,
            category=report_category,
            data=report_artifact_data,
        )
        if not artifact_message_id:
            raise RuntimeError("A5 artifact persistence failed")
        _ca = metrics.get("citation_analysis", {})
        logger.info(
            "[A5][Artifact] citation_analysis in artifact: total=%s, domains=%s",
            _ca.get("total_citations", "MISSING"), _ca.get("unique_domains", "MISSING"),
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
            step="data_analytics",
            step_name="数据分析报告",
            progress=1.0,
            message="分析完成",
            status="completed",
        )

        return Command(update=update_dict)

    except Exception as e:
        error_text = str(e)
        error_category = "system"
        if "artifact persistence failed" in error_text.lower():
            error_category = "system_persistence"
        from app.workflow.events import send_error_event
        await send_error_event(session_id, "A5", str(e), recoverable=True)
        await send_progress_event(
            session_id=session_id,
            step="data_analytics",
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
                    "error": error_text,
                    "category": error_category,
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
                "weights": dict(a5_metrics.BWVS_WEIGHTS),
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
            "keyword_analysis": {},
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
                sentiment = a5_metrics.analyze_sentiment(content)
                sentiment_counts[sentiment] += 1

                # Brand mention
                has_mention = (
                    answer.get("has_brand_mention", False)
                    if isinstance(answer, dict)
                    else False
                )
                if not has_mention:
                    has_mention = content_mentions_brand(content, brand_profile)
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
        a5_metrics.BWVS_WEIGHTS["mention"] * mention_score / 100
        + a5_metrics.BWVS_WEIGHTS["sentiment"] * sentiment_score / 100
        + a5_metrics.BWVS_WEIGHTS["coverage"] * coverage_score / 100
        + a5_metrics.BWVS_WEIGHTS["citation"] * citation_score / 100
    )

    breakdown: dict[str, Any] = {
        "mention_score": round(mention_score, 2),
        "sentiment_score": round(sentiment_score, 2),
        "coverage_score": round(coverage_score, 2),
        "citation_score": round(citation_score, 2),
        "weights": dict(a5_metrics.BWVS_WEIGHTS),
        "formula": (
            "BWVS = 40%*提及率 + 25%*情感 + 20%*覆盖度 + 15%*引用质量"
        ),
    }
    if citation_note:
        breakdown["citation_note"] = citation_note

    # ---- Citation analysis aggregation ----
    logger.info(
        "[A5][Citations] TOTAL: citations=%d, official=%d, unique_domains=%d, brand_domain='%s'",
        total_citations, official_citations, len(domain_stats), brand_domain,
    )
    sorted_domains = sorted(
        domain_stats.items(), key=lambda x: x[1]["count"], reverse=True
    )
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
                "sample_titles": stats["sample_titles"][:3],
            }
            for domain, stats in sorted_domains
        ],
        "platform_citation_stats": platform_citation_stats,
        "note": "引用数据基于各 AI 平台回答中的参考来源提取",
    }

    # ---- Keyword analysis (TF-IDF word cloud) ----
    keyword_analysis = a5_keywords.extract_keyword_analysis(fetch_results, brand_profile)
    if keyword_analysis:
        logger.info(
            "[A5][Keywords] Extracted %d keywords across %d platforms",
            keyword_analysis.get("total_keywords", 0),
            len(keyword_analysis.get("platforms", [])),
        )

    return {
        "total_questions": total_questions,
        "total_mentions": total_mentions,
        "mention_rate": round(mention_rate, 4),
        "bwvs_index": round(bwvs_index, 2),
        "bwvs_breakdown": breakdown,
        "sentiment_distribution": sentiment_counts,
        "platform_breakdown": platform_stats,
        "citation_analysis": citation_analysis,
        "keyword_analysis": keyword_analysis,
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
                    sentiment_scores.append(a5_metrics.analyze_sentiment(content))
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
