"""A5 Node: Data Analytics and Report Generation.

This module contains the A5 node implementation for analyzing fetch results
and generating comprehensive reports with BWVS metrics.
"""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from langgraph.types import Command

from app.core.utils import extract_domain
from app.workflow.brand_mentions import content_mentions_brand, extract_brand_aliases

# A5 is being split by responsibility: scenario/report contracts, prompt assembly,
# user-facing sanitization, and persistence are kept in dedicated modules.
from app.workflow.a5 import metrics as a5_metrics
from app.workflow.a5 import keywords as a5_keywords
from app.workflow.a5.canonical import (
    build_canonical_report_artifact,
    normalize_report_kind,
)
from app.workflow.events import (
    send_error_event,
    send_progress_event,
    send_stage_result,
)
from app.workflow.harness_validation import (
    build_harness_decision,
    evaluate_skill_postconditions,
    evaluate_skill_preconditions,
    validate_a4_canonical_result,
    validate_artifact_writeback,
)
from app.workflow.nodes_a4 import PLATFORMS
from app.workflow.skill_state import (
    build_harness_decision_update,
    build_skill_result_update,
    build_validation_result_update,
)
from app.workflow.skill_fact_snapshot import build_skill_fact_snapshot
from app.workflow.state import AgentState
from app.workflow.summaries import generate_a5_summary

logger = logging.getLogger(__name__)

# Shared BWVS weights and sentiment helpers now live in app.workflow.a5.metrics.


def _resolved_report_kind_from_output(
    metadata: dict[str, Any], output_data: dict[str, Any]
) -> str | None:
    return (
        str(
            metadata.get("report_kind")
            or output_data.get("report_kind")
            or (output_data.get("meta") or {}).get("report_kind")
            or ""
        ).strip()
        or None
    )


def _pick_latest_panorama_baseline_report(
    messages: list[dict[str, Any]],
    existing_report: dict[str, Any] | None = None,
    existing_report_id: str | None = None,
) -> tuple[dict[str, Any], str | None]:
    resolved_existing_report = dict(existing_report or {})
    resolved_existing_id = (
        str(
            existing_report_id
            or resolved_existing_report.get("artifact_id")
            or resolved_existing_report.get("report_id")
            or ""
        ).strip()
        or None
    )
    if isinstance(resolved_existing_report.get("metric_bundle"), dict):
        return resolved_existing_report, resolved_existing_id

    latest_payload: dict[str, Any] | None = None
    latest_id: str | None = None
    for message in messages:
        if str(message.get("output_type") or "") != "report":
            continue
        metadata = dict(message.get("metadata") or {})
        output_data = dict(message.get("output_data") or {})
        if _resolved_report_kind_from_output(metadata, output_data) != "panorama":
            continue
        if not isinstance(output_data.get("metric_bundle"), dict):
            continue
        latest_payload = {
            **output_data,
            "artifact_id": metadata.get("artifact_id")
            or output_data.get("artifact_id"),
            "report_id": message.get("id") or output_data.get("report_id"),
        }
        latest_id = (
            str(
                latest_payload.get("artifact_id")
                or latest_payload.get("report_id")
                or ""
            ).strip()
            or None
        )

    if latest_payload:
        return latest_payload, latest_id
    return resolved_existing_report, resolved_existing_id


async def _resolve_scenario_baseline_context(
    session_id: str,
    existing_report: dict[str, Any] | None = None,
    existing_report_id: str | None = None,
) -> tuple[dict[str, Any], str | None]:
    resolved_existing_report, resolved_existing_id = (
        _pick_latest_panorama_baseline_report(
            [],
            existing_report=existing_report,
            existing_report_id=existing_report_id,
        )
    )
    if isinstance(resolved_existing_report.get("metric_bundle"), dict):
        return resolved_existing_report, resolved_existing_id

    try:
        from app.core.database import AsyncSessionLocal
        from app.services.message_service import MessageService

        async with AsyncSessionLocal() as db:
            message_service = MessageService(db)
            messages = await message_service.get_messages(UUID(session_id), limit=300)
        return _pick_latest_panorama_baseline_report(
            messages,
            existing_report=existing_report,
            existing_report_id=existing_report_id,
        )
    except Exception as exc:
        logger.warning(
            "[A5] Failed to resolve latest panorama baseline for scenario report: %s",
            exc,
        )
        return resolved_existing_report, resolved_existing_id


async def a5_analytics_node(state: AgentState) -> Command:
    """A5: Analyze fetch results and generate comprehensive report.

    Calculates BWVS metrics and generates executive summary with recommendations.
    Writes AnalysisSnapshot for historical trending.

    Routes between baseline and persona report modes based on analysis_mode.
    """
    session_id = state["session_id"]
    entity_id = state.get("entity_id")
    canonical_fetch_validation = validate_a4_canonical_result(state)
    if not canonical_fetch_validation.passed:
        message = f"A5 前置条件未满足：{canonical_fetch_validation.reason}"
        await send_error_event(session_id, "A5", message, recoverable=True)
        validation_update = build_validation_result_update(
            state, canonical_fetch_validation
        )
        decision_update = build_harness_decision_update(
            {**state, **validation_update},
            build_harness_decision(
                decision_type="fail_step",
                reason=message,
                recoverable=True,
                metadata={
                    "step": "A5",
                    "gate": canonical_fetch_validation.gate_name,
                    "blocker_code": canonical_fetch_validation.metadata.get(
                        "blocker_code"
                    )
                    or "fetch_results_missing",
                },
            ),
        )
        return Command(
            update={
                "error_info": {
                    "step": "A5",
                    "error": message,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                "current_step": "A5",
                "execution_status": "error",
                **validation_update,
                **decision_update,
            }
        )

    facts = build_skill_fact_snapshot(state)
    brand_profile = facts.brand_profile
    fetch_results = facts.fetch_results
    competitors = facts.competitors
    report_kind = normalize_report_kind(facts.analysis_mode or "scenario")
    analysis_mode = "baseline" if report_kind == "panorama" else "persona"
    is_baseline = report_kind == "panorama"
    precondition_result = evaluate_skill_preconditions(
        state, state.get("current_skill_contract")
    )

    if not precondition_result.passed:
        message = f"A5 前置条件未满足：{precondition_result.reason}"
        await send_error_event(session_id, "A5", message, recoverable=True)
        validation_update = build_validation_result_update(state, precondition_result)
        decision_update = build_harness_decision_update(
            {**state, **validation_update},
            build_harness_decision(
                decision_type="fail_step",
                reason=message,
                recoverable=True,
                metadata={"step": "A5", "gate": "precondition_gate"},
            ),
        )
        return Command(
            update={
                "error_info": {
                    "step": "A5",
                    "error": message,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                "current_step": "A5",
                "execution_status": "error",
                **validation_update,
                **decision_update,
            }
        )

    step_message = "开始品牌全景分析..." if is_baseline else "开始分析抓取数据..."
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

        baseline_report = state.get("baseline_report")
        baseline_report_id = state.get("baseline_report_id")
        if report_kind == "scenario":
            baseline_report, baseline_report_id = (
                await _resolve_scenario_baseline_context(
                    session_id=session_id,
                    existing_report=(
                        baseline_report if isinstance(baseline_report, dict) else None
                    ),
                    existing_report_id=(
                        str(baseline_report_id).strip() if baseline_report_id else None
                    ),
                )
            )

        canonical_report = build_canonical_report_artifact(
            session_id=session_id,
            entity_id=entity_id,
            analysis_mode=analysis_mode,
            brand_profile=brand_profile,
            competitors=competitors,
            fetch_results=fetch_results,
            simulated_questions=state.get("simulated_questions"),
            base_metrics=metrics,
            baseline_report=(
                baseline_report if isinstance(baseline_report, dict) else None
            ),
            baseline_report_id=(
                baseline_report_id if isinstance(baseline_report_id, str) else None
            ),
        )
        summary_metrics = canonical_report.get("metric_bundle", {})
        skill_outputs = canonical_report.get("skill_outputs", {})
        question_mapper = (
            skill_outputs.get("question_coverage_mapper", {})
            if isinstance(skill_outputs, dict)
            else {}
        )
        sentiment_parser = (
            skill_outputs.get("sentiment_reason_parser", {})
            if isinstance(skill_outputs, dict)
            else {}
        )
        scenario_matrix = (
            question_mapper.get("question_rows", [])
            if isinstance(question_mapper, dict)
            else []
        )
        source_overview = (
            summary_metrics.get("source_summary", {})
            if isinstance(summary_metrics, dict)
            else {}
        )
        mention_sentiment_analysis = {
            "brand": {
                "summary": (
                    summary_metrics.get("sentiment_distribution", {})
                    if isinstance(summary_metrics, dict)
                    else {}
                ),
                "items": (
                    sentiment_parser.get("items", [])
                    if isinstance(sentiment_parser, dict)
                    else []
                ),
            }
        }

        await send_progress_event(
            session_id=session_id,
            step="data_analytics",
            step_name="数据分析报告",
            progress=0.75,
            message=(
                f"提及率: {(summary_metrics.get('mention_rate') or 0):.1%} | "
                f"内容引用率: {(summary_metrics.get('content_citation_rate') or 0):.1%} | "
                f"场景覆盖: {summary_metrics.get('scenario_hit_count', 0)}/{summary_metrics.get('scenario_total', 0)}"
            ),
        )

        # Stage result: metrics preview before LLM report generation
        metrics_preview_data = {
            "mention_rate": f"{(summary_metrics.get('mention_rate') or 0):.1%}",
            "content_citation_rate": (
                f"{(summary_metrics.get('content_citation_rate') or 0):.1%}"
            ),
            "scenario_hit_count": summary_metrics.get("scenario_hit_count", 0),
            "scenario_total": summary_metrics.get("scenario_total", 0),
            "accuracy_status": None,
            "total_mentions": summary_metrics.get("brand_mentioned_answer_count", 0),
            "total_questions": summary_metrics.get("total_questions", 0),
        }
        await send_stage_result(
            session_id,
            "A5",
            "数据分析",
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
                    await task_svc.append_stage_result(
                        _UUID(task_id),
                        {
                            "stage": "A5",
                            "result_type": "metrics_preview",
                            "data": metrics_preview_data,
                            "stage_name": "数据分析",
                        },
                    )
            except Exception as e:
                logger.warning("[A5] Failed to persist stage_result: %s", e)

        # Query previous snapshot for delta (before LLM call, to include in prompt)
        report_data = canonical_report

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
            session_id,
            "agent_summary",
            summary,
            step="data_analytics",
            is_complete=True,
        )

        # Build fetch_results summary for analytics service
        fetch_results_summary = []
        recovered_brand_mentions = 0
        for fr in fetch_results:
            for pr in fr.get("platform_results", []):
                answer_payload = (
                    pr.get("answer", {}) if isinstance(pr.get("answer"), dict) else {}
                )
                answer_content = (
                    answer_payload.get("content", "")
                    if isinstance(answer_payload, dict)
                    else ""
                )
                stored_has_brand_mention = (
                    bool(answer_payload.get("has_brand_mention", False))
                    if isinstance(answer_payload, dict)
                    else False
                )
                computed_has_brand_mention = content_mentions_brand(
                    answer_content, brand_profile
                )
                if not stored_has_brand_mention and computed_has_brand_mention:
                    recovered_brand_mentions += 1
                fetch_results_summary.append(
                    {
                        "platform": pr.get("platform", "unknown"),
                        "success": pr.get("success", False),
                        "has_brand_mention": computed_has_brand_mention,
                        "citations": pr.get("citations", []),
                    }
                )

        if recovered_brand_mentions:
            logger.info(
                "[A5] Recovered stale brand-mention flags from fetch results: %d",
                recovered_brand_mentions,
            )

        metric_bundle = report_data.get("metric_bundle", {})
        metrics_for_state = {
            **metric_bundle,
            "platform_breakdown": metrics.get("platform_breakdown", {}),
            "citation_analysis": metrics.get("citation_analysis", {}),
            "keyword_analysis": metrics.get("keyword_analysis", {}),
            "summary_metrics": summary_metrics,
            "scenario_matrix": scenario_matrix,
            "source_overview": source_overview,
            "mention_sentiment_analysis": mention_sentiment_analysis,
        }

        triggered_by = (
            "scheduled"
            if state.get("headless_mode") or state.get("monitoring_schedule_id")
            else "manual"
        )

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
                        metrics=metrics_for_state,
                        report_data=report_data,
                        competitor_metrics=competitor_metrics,
                        fetch_results_summary=fetch_results_summary,
                        is_degraded=is_degraded,
                        triggered_by=triggered_by,
                        snapshot_type="panorama" if is_baseline else "scenario",
                    )
                    logger.info(
                        "[A5] Snapshot created: id=%s, bwvs=%.1f",
                        snapshot.id,
                        snapshot.bwvs_index or 0,
                    )

                    # Query previous snapshot for delta in the same session
                    previous = await snap_service.get_previous_snapshot(
                        entity_id=entity_id,
                        exclude_snapshot_id=snapshot.id,
                        snapshot_type="panorama" if is_baseline else "scenario",
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
                                    "up"
                                    if delta_value > 0
                                    else "down" if delta_value < 0 else "stable"
                                ),
                            },
                            "previous_date": (
                                previous.created_at.strftime("%Y-%m-%d")
                                if previous.created_at
                                else None
                            ),
                            "previous_snapshot_id": str(previous.id),
                        }
            except Exception as snap_err:
                logger.error(
                    "[A5] Failed to create snapshot or compute delta: %s",
                    snap_err,
                    exc_info=True,
                )

        # Save and send artifact to Canvas
        from app.workflow.events import save_and_send_artifact

        report_output_type = "report"
        report_kind = "panorama" if is_baseline else "scenario"
        report_title = "品牌全景分析报告" if is_baseline else "用户场景分析报告"
        report_category = report_kind
        artifact_key = f"{session_id}_{report_output_type}_{report_kind}"
        task_run_id = str(state.get("run_id") or "").strip()
        if task_run_id and (
            state.get("monitoring_schedule_id") or state.get("headless_mode")
        ):
            artifact_key = f"{artifact_key}_{task_run_id}"
        report_artifact_data = {
            **report_data,
            "fetch_results_summary": fetch_results_summary,
            "competitors": competitor_metrics,
            "delta_vs_previous": delta_vs_previous,
            "triggered_by": triggered_by,
        }
        artifact_message_id = await save_and_send_artifact(
            session_id=session_id,
            output_type=report_output_type,
            title=report_title,
            category=report_category,
            data=report_artifact_data,
            artifact_key=artifact_key,
        )
        artifact_validation = validate_artifact_writeback(
            gate_name="artifact_writeback_gate",
            artifact_message_id=artifact_message_id,
            artifact_key=artifact_key,
            artifact_kind="geo_report",
            metadata={
                "analysis_mode": analysis_mode,
                "report_kind": report_kind,
                "triggered_by": triggered_by,
            },
        )
        if not artifact_validation.passed:
            raise RuntimeError(artifact_validation.reason)
        _ca = metrics.get("citation_analysis", {})
        logger.info(
            "[A5][Artifact] citation_analysis in artifact: total=%s, domains=%s",
            _ca.get("total_citations", "MISSING"),
            _ca.get("unique_domains", "MISSING"),
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
                    logger.info(
                        f"[A5] Updated entity {entity_id}: status=active, last_analyzed=now()"
                    )
            except Exception as e:
                logger.error(f"[A5] Failed to update entity {entity_id}: {e}")

        update_dict: dict[str, Any] = {
            "metrics": metrics_for_state,
            "report": report_artifact_data,
            "snapshot_id": str(snapshot.id) if snapshot else None,
            "current_step": "A5",
            "progress": 1.0,
        }
        skill_update = build_skill_result_update(
            state,
            skill_key=state.get("current_skill"),
            tool_name="analysis_report_skill",
            status="completed",
            summary="分析报告 Skill 已完成，报告与关键指标已更新。",
            executor_ref="a5_data_analytics",
            metadata={
                "analysis_mode": analysis_mode,
                "mention_rate": metrics_for_state.get("mention_rate"),
                "report_type": report_artifact_data.get("report_kind"),
            },
        )
        update_dict.update(skill_update)
        artifact_validation_update = build_validation_result_update(
            state, artifact_validation
        )
        validation_state = {**state, **update_dict, **artifact_validation_update}
        postcondition_result = evaluate_skill_postconditions(
            state=state,
            contract_payload=state.get("current_skill_contract"),
            pending_update=update_dict,
            artifact_validation=artifact_validation,
        )
        if not postcondition_result.passed:
            raise RuntimeError(postcondition_result.reason)
        postcondition_validation_update = build_validation_result_update(
            validation_state,
            postcondition_result,
        )
        decision_update = build_harness_decision_update(
            {**validation_state, **postcondition_validation_update},
            build_harness_decision(
                decision_type="complete_skill",
                reason="A5 harness gates passed.",
                recoverable=False,
                metadata={"step": "A5", "analysis_mode": analysis_mode},
            ),
        )
        update_dict.update(artifact_validation_update)
        update_dict.update(postcondition_validation_update)
        update_dict.update(decision_update)
        # Baseline mode: also write to baseline_* fields for long-term storage
        if is_baseline:
            update_dict["baseline_metrics"] = metrics_for_state
            update_dict["baseline_report"] = report_artifact_data
            update_dict["baseline_fetch_results"] = fetch_results

        await send_progress_event(
            session_id=session_id,
            step="data_analytics",
            step_name="数据分析报告",
            progress=1.0,
            message="分析完成",
            status="completed",
        )

        return Command(
            update={
                **update_dict,
                "execution_status": "completed",
                "awaiting_user": False,
                "pending_confirmation": None,
                "orchestrator_reply": summary,
            },
        )

    except Exception as e:
        error_text = str(e)
        error_category = "system"
        if (
            "artifact writeback" in error_text.lower()
            or "artifact persistence" in error_text.lower()
        ):
            error_category = "system_persistence"

        await send_error_event(session_id, "A5", str(e), recoverable=True)
        await send_progress_event(
            session_id=session_id,
            step="data_analytics",
            step_name="数据分析报告",
            progress=1.0,
            message=f"分析过程出错: {str(e)}",
            status="error",
        )

        return Command(
            update={
                "current_step": "A5",
                "error_info": {
                    "step": "A5",
                    "error": error_text,
                    "category": error_category,
                    "timestamp": datetime.now().isoformat(),
                },
                "execution_status": "error",
                "progress": 1.0,
                **build_harness_decision_update(
                    state,
                    build_harness_decision(
                        decision_type="retry_step",
                        reason=error_text,
                        recoverable=True,
                        metadata={"step": "A5", "error_category": error_category},
                    ),
                ),
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
                "formula": ("BWVS = 40%*提及率 + 25%*情感 + 20%*覆盖度 + 15%*引用质量"),
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
    successful_answers = 0
    platform_stats: dict[str, dict[str, int]] = {}
    platforms_with_mention: set[str] = set()

    # Sentiment distribution
    sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0}

    # Citation tracking
    total_citations = 0
    official_citations = 0
    branded_citations = 0
    brand_domain = extract_domain(brand_profile.get("official_website", ""))
    brand_aliases = extract_brand_aliases(brand_profile)
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
                    "branded_count": 0,
                    "total_answers": 0,
                    "answers_with_citations": 0,
                }

            platform_stats[platform]["total"] += 1
            platform_citation_stats[platform]["total_answers"] += 1

            if platform_result.get("success"):
                platform_stats[platform]["success"] += 1
                successful_answers += 1

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
                answer_branded_count = 0
                for citation in citations:
                    total_citations += 1
                    answer_citation_count += 1
                    citation_url = (
                        citation.get("url", "") if isinstance(citation, dict) else ""
                    )
                    citation_title = (
                        citation.get("title", "") if isinstance(citation, dict) else ""
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

                    citation_text = f"{citation_title} {citation_url}".lower()
                    if is_official or any(
                        alias.lower() in citation_text for alias in brand_aliases
                    ):
                        branded_citations += 1
                        answer_branded_count += 1

                # Update platform citation stats
                platform_citation_stats[platform][
                    "total_citations"
                ] += answer_citation_count
                platform_citation_stats[platform][
                    "official_count"
                ] += answer_official_count
                platform_citation_stats[platform][
                    "branded_count"
                ] += answer_branded_count
                if answer_citation_count > 0:
                    platform_citation_stats[platform]["answers_with_citations"] += 1

    # ---- Dimension 1: Mention score ----
    mention_rate = total_mentions / successful_answers if successful_answers > 0 else 0
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
        "formula": ("BWVS = 40%*提及率 + 25%*情感 + 20%*覆盖度 + 15%*引用质量"),
    }
    if citation_note:
        breakdown["citation_note"] = citation_note

    # ---- Citation analysis aggregation ----
    logger.info(
        "[A5][Citations] TOTAL: citations=%d, official=%d, unique_domains=%d, brand_domain='%s'",
        total_citations,
        official_citations,
        len(domain_stats),
        brand_domain,
    )
    sorted_domains = sorted(
        domain_stats.items(), key=lambda x: x[1]["count"], reverse=True
    )
    total_cit = max(total_citations, 1)  # avoid division by zero

    citation_analysis: dict[str, Any] = {
        "total_citations": total_citations,
        "unique_domains": len(domain_stats),
        "official_citations": official_citations,
        "branded_citations": branded_citations,
        "official_share": (
            round(official_citations / total_cit * 100, 1)
            if total_citations > 0
            else 0.0
        ),
        "brand_content_citation_rate": (
            round(branded_citations / total_cit * 100, 1)
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
    keyword_analysis = a5_keywords.extract_keyword_analysis(
        fetch_results, brand_profile
    )
    if keyword_analysis:
        logger.info(
            "[A5][Keywords] Extracted %d keywords across %d platforms",
            keyword_analysis.get("total_keywords", 0),
            len(keyword_analysis.get("platforms", [])),
        )

    return {
        "total_questions": total_questions,
        "total_mentions": total_mentions,
        "successful_answers": successful_answers,
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
        1
        for r in fetch_results
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
            competitor_metrics.append(
                {
                    "name": name,
                    "relevance_score": c.get("relevance_score", 0),
                    "mention_rate": 0,
                    "avg_ranking": 0,
                    "sentiment": 0,
                    "appeared_in": [],
                }
            )
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
                    appeared_questions.append(
                        {
                            "question": question_text[:60],
                            "platform": pr.get("platform", ""),
                        }
                    )

        mention_rate = mentions / total_answers
        mention_counts.append((mentions, name))

        sentiment_value = 0.0
        if sentiment_scores:
            score_map = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}
            sentiment_value = sum(score_map[s] for s in sentiment_scores) / len(
                sentiment_scores
            )

        competitor_metrics.append(
            {
                "name": name,
                "relevance_score": c.get("relevance_score", 0),
                "mention_rate": round(mention_rate, 4),
                "avg_ranking": 0,
                "sentiment": round(sentiment_value, 2),
                "appeared_in": appeared_questions[:5],
            }
        )

    # Ranking by mention frequency (more mentions = better rank)
    mention_counts.sort(key=lambda x: x[0], reverse=True)
    name_to_rank = {name: rank + 1 for rank, (_, name) in enumerate(mention_counts)}
    for cm in competitor_metrics:
        if cm["name"] in name_to_rank:
            cm["avg_ranking"] = name_to_rank[cm["name"]]

    return competitor_metrics
