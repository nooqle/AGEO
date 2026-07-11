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
from app.workflow.a5.association_circle import (
    ARTIFACT_KIND as ASSOCIATION_CIRCLE_ARTIFACT_KIND,
    REPORT_KIND as ASSOCIATION_CIRCLE_REPORT_KIND,
    build_brand_association_circle_report_artifact,
    is_association_circle_mode,
)
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
_UNKNOWN_SOURCE_VALUES = {
    "",
    "unknown",
    "other",
    "n/a",
    "na",
    "缺乏特征，无法识别",
    "缺乏特征，无法识别。",
}


def _clean_source_value(value: Any) -> str:
    text = str(value or "").strip()
    if text.lower() in _UNKNOWN_SOURCE_VALUES or text in _UNKNOWN_SOURCE_VALUES:
        return ""
    return text


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


def _association_center_terms_from_state(state: AgentState) -> list[str] | None:
    """Resolve optional center terms from run input without creating a side channel."""

    for key in ("active_center_term", "center_term"):
        value = state.get(key)
        text = str(value or "").strip()
        if text:
            return [text]

    for key in ("center_terms", "brand_center_terms"):
        value = state.get(key)
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]

    dashboard_context = state.get("dashboard_context")
    if isinstance(dashboard_context, dict):
        for key in ("active_center_term", "center_term"):
            text = str(dashboard_context.get(key) or "").strip()
            if text:
                return [text]
        value = dashboard_context.get("center_terms")
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]

    input_scope = state.get("input_scope")
    if isinstance(input_scope, dict):
        for key in ("active_center_term", "center_term"):
            text = str(input_scope.get(key) or "").strip()
            if text:
                return [text]
        value = input_scope.get("center_terms")
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
    return None


def _association_entity_calibration_from_state(
    state: AgentState,
) -> dict[str, Any] | None:
    value = state.get("entity_calibration_result")
    if isinstance(value, dict):
        return value

    canonical = state.get("a4_canonical_result")
    if isinstance(canonical, dict):
        value = canonical.get("entity_calibration_result")
        if isinstance(value, dict):
            return value
    return None


def _resolve_a5_analysis_mode(state: AgentState, facts_mode: Any) -> str:
    """Resolve A5 report routing from the official run context first."""

    candidates: list[Any] = []
    for container_key in ("dashboard_context", "input_scope", "tool_call_args"):
        container = state.get(container_key)
        if isinstance(container, dict):
            candidates.extend(
                [
                    container.get("analysis_mode"),
                    container.get("report_kind"),
                    container.get("a3_mode"),
                ]
            )

    user_decisions = state.get("user_decisions")
    if isinstance(user_decisions, dict):
        candidates.extend(
            [
                user_decisions.get("analysis_mode"),
                user_decisions.get("report_kind"),
                user_decisions.get("a3_mode"),
            ]
        )

    for candidate in candidates:
        if is_association_circle_mode(candidate):
            return ASSOCIATION_CIRCLE_REPORT_KIND

    for candidate in (facts_mode, state.get("analysis_mode")):
        text = str(candidate or "").strip()
        if text:
            return text
    return "scenario"


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


def _uuid_or_none(value: object) -> UUID | None:
    try:
        return UUID(str(value)) if value else None
    except (TypeError, ValueError):
        return None


async def _persist_brand_intelligence_report(
    *,
    state: AgentState,
    report_kind: str,
    title: str,
    artifact_key: str,
    artifact_message_id: str,
    payload: dict[str, Any],
) -> None:
    """Dual-write A5 report output into the durable brand intelligence layer."""

    entity_uuid = _uuid_or_none(state.get("entity_id"))
    if entity_uuid is None:
        return
    session_uuid = _uuid_or_none(state.get("session_id"))
    if session_uuid is None:
        logger.info(
            "[A5] Skipping brand intelligence report projection for non-UUID session"
        )
        return
    message_uuid = _uuid_or_none(artifact_message_id)
    try:
        from app.core.database import AsyncSessionLocal
        from app.services.brand_action_service import BrandActionService
        from app.services.brand_intelligence_projection_service import (
            BrandIntelligenceProjectionService,
        )

        async with AsyncSessionLocal() as db:
            action_service = BrandActionService(db)
            action_record = await action_service.start_action(
                entity_id=entity_uuid,
                session_id=session_uuid,
                user_id=_uuid_or_none(state.get("user_id")),
                parent_action_record_id=_uuid_or_none(
                    state.get("latest_user_action_record_id")
                ),
                actor_type="agent",
                origin_surface="workflow_node",
                origin_event_id=(
                    str(state.get("run_id") or artifact_message_id or "") or None
                ),
                action_type="generate_report",
                input_payload={
                    "report_kind": report_kind,
                    "artifact_id": artifact_key,
                },
            )
            service = BrandIntelligenceProjectionService(db)
            try:
                report_version = await service.persist_report_artifact(
                    entity_id=entity_uuid,
                    session_id=session_uuid,
                    report_kind=report_kind,
                    title=title,
                    artifact_id=artifact_key,
                    payload=payload,
                    message_id=message_uuid,
                    source_action_record_id=action_record.id,
                )
                await action_service.complete_action(
                    action_record,
                    output_payload={
                        "report_version_id": str(report_version.id),
                        "report_id": report_version.report_id,
                        "version": report_version.version,
                    },
                )
                await db.commit()
            except Exception as inner_exc:
                await action_service.fail_action(
                    action_record,
                    error_message=str(inner_exc),
                )
                await db.commit()
                raise
        logger.info(
            "[A5] Brand intelligence report projected: report_id=%s version=%s",
            report_version.report_id,
            report_version.version,
        )
    except Exception as exc:
        logger.warning("[A5] Brand intelligence report projection failed: %s", exc)


async def _run_association_circle_report(
    *,
    state: AgentState,
    session_id: str,
    entity_id: str | None,
    brand_profile: dict[str, Any],
    fetch_results: list[dict[str, Any]],
    analysis_mode: str,
    report_kind: str,
) -> Command:
    await send_progress_event(
        session_id=session_id,
        step="data_analytics",
        step_name="品牌联想圈层分析",
        progress=0.65,
        message="开始解析多平台回答中的品牌联想节点...",
    )
    try:
        report_data = build_brand_association_circle_report_artifact(
            session_id=session_id,
            entity_id=entity_id,
            brand_profile=brand_profile,
            fetch_results=fetch_results,
            simulated_questions=state.get("simulated_questions"),
            center_terms=_association_center_terms_from_state(state),
            entity_calibration_result=_association_entity_calibration_from_state(
                state
            ),
        )
        association_circle = (
            report_data.get("association_circle")
            if isinstance(report_data.get("association_circle"), dict)
            else {}
        )
        nodes = (
            association_circle.get("nodes")
            if isinstance(association_circle, dict)
            else []
        )
        sample_scope = (
            report_data.get("sample_scope")
            if isinstance(report_data.get("sample_scope"), dict)
            else {}
        )
        await send_progress_event(
            session_id=session_id,
            step="data_analytics",
            step_name="品牌联想圈层分析",
            progress=0.85,
            message=(
                f"已解析 {len(nodes or [])} 个联想节点，"
                f"有效回答 {sample_scope.get('valid_answer_count', 0)} 条。"
            ),
        )

        from app.workflow.events import save_and_send_artifact

        report_output_type = "report"
        report_title = str(report_data.get("title") or "品牌联想圈层报告")
        artifact_key = f"{session_id}_{report_output_type}_{report_kind}"
        artifact_message_id = await save_and_send_artifact(
            session_id=session_id,
            output_type=report_output_type,
            title=report_title,
            category=report_kind,
            data=report_data,
            artifact_key=artifact_key,
        )
        artifact_validation = validate_artifact_writeback(
            gate_name="artifact_writeback_gate",
            artifact_message_id=artifact_message_id,
            artifact_key=artifact_key,
            artifact_kind=ASSOCIATION_CIRCLE_ARTIFACT_KIND,
            metadata={
                "analysis_mode": analysis_mode,
                "report_kind": report_kind,
                "node_count": len(nodes or []),
            },
        )
        if not artifact_validation.passed:
            raise RuntimeError(artifact_validation.reason)
        await _persist_brand_intelligence_report(
            state=state,
            report_kind=report_kind,
            title=report_title,
            artifact_key=artifact_key,
            artifact_message_id=artifact_message_id,
            payload=report_data,
        )
        fetch_results_summary: list[dict[str, Any]] = []
        platform_breakdown: dict[str, dict[str, int]] = {}
        for fetch_result in fetch_results or []:
            if not isinstance(fetch_result, dict):
                continue
            question_text = str(
                fetch_result.get("question")
                or fetch_result.get("question_text")
                or ""
            ).strip()
            platform_results = fetch_result.get("platform_results")
            if not isinstance(platform_results, list):
                continue
            for platform_result in platform_results:
                if not isinstance(platform_result, dict):
                    continue
                platform = str(platform_result.get("platform") or "unknown").strip()
                platform_stats = platform_breakdown.setdefault(
                    platform,
                    {"success": 0, "failed": 0, "empty": 0, "total": 0},
                )
                platform_stats["total"] += 1
                answer_payload = (
                    platform_result.get("answer")
                    if isinstance(platform_result.get("answer"), dict)
                    else {}
                )
                answer_content = str(
                    answer_payload.get("content")
                    or platform_result.get("answer_text")
                    or platform_result.get("content")
                    or ""
                ).strip()
                has_content = bool(answer_content)
                is_success = bool(platform_result.get("success"))
                if is_success and has_content:
                    platform_stats["success"] += 1
                elif is_success:
                    platform_stats["empty"] += 1
                else:
                    platform_stats["failed"] += 1
                fetch_results_summary.append(
                    {
                        "platform": platform,
                        "success": is_success,
                        "has_content": has_content,
                        "question": question_text,
                        "citations": platform_result.get("citations", []),
                    }
                )
        executive_summary = (
            report_data.get("executive_summary")
            if isinstance(report_data.get("executive_summary"), dict)
            else {}
        )
        summary = str(
            executive_summary.get("one_line_judgment") or "品牌联想圈层分析已完成。"
        )
        metrics_for_state = {
            "summary_metrics": report_data.get("summary_metrics") or [],
            "sample_scope": sample_scope,
            "association_node_count": len(nodes or []),
            "bwvs_index": None,
            "mention_rate": (
                round(
                    float(sample_scope.get("valid_answer_count") or 0)
                    / float(sample_scope.get("total_answer_count") or 1),
                    4,
                )
                if sample_scope.get("total_answer_count")
                else 0.0
            ),
            "total_questions": int(sample_scope.get("question_count") or 0),
            "total_mentions": int(sample_scope.get("valid_answer_count") or 0),
            "platform_breakdown": platform_breakdown,
        }
        triggered_by = (
            "scheduled"
            if state.get("headless_mode") or state.get("monitoring_schedule_id")
            else "manual"
        )
        monitoring_metadata = {
            "monitoring_schedule_id": state.get("monitoring_schedule_id"),
            "monitoring_plan_id": state.get("monitoring_plan_id"),
            "question_set_ids": state.get("question_set_ids") or [],
            "endpoint_ids": state.get("endpoint_ids") or [],
            "run_policy": state.get("run_policy"),
        }
        monitoring_metadata = {
            key: value for key, value in monitoring_metadata.items() if value
        }
        snapshot = None
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
                        competitor_metrics=None,
                        fetch_results_summary=fetch_results_summary,
                        fetch_results=fetch_results,
                        entity_extraction_result=(
                            state.get("entity_extraction_result")
                            if isinstance(state.get("entity_extraction_result"), dict)
                            else None
                        ),
                        entity_calibration_result=(
                            _association_entity_calibration_from_state(state)
                        ),
                        is_degraded=not nodes,
                        triggered_by=triggered_by,
                        snapshot_type=report_kind,
                        monitoring_metadata=monitoring_metadata or None,
                    )
                    logger.info(
                        "[A5] Association circle snapshot created: id=%s, nodes=%s",
                        snapshot.id,
                        len(nodes or []),
                    )
            except Exception as snap_err:
                logger.error(
                    "[A5] Failed to create association circle snapshot: %s",
                    snap_err,
                    exc_info=True,
                )
        update_dict: dict[str, Any] = {
            "metrics": metrics_for_state,
            "report": report_data,
            "snapshot_id": str(snapshot.id) if snapshot else None,
            "current_step": "A5",
            "progress": 1.0,
        }
        skill_update = build_skill_result_update(
            state,
            skill_key=state.get("current_skill"),
            tool_name="analysis_report_skill",
            status="completed",
            summary="品牌联想圈层报告 Skill 已完成，报告与节点证据已更新。",
            executor_ref="a5_data_analytics",
            metadata={
                "analysis_mode": analysis_mode,
                "report_type": report_kind,
                "association_node_count": len(nodes or []),
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
                reason="A5 association circle harness gates passed.",
                recoverable=False,
                metadata={"step": "A5", "analysis_mode": analysis_mode},
            ),
        )
        update_dict.update(artifact_validation_update)
        update_dict.update(postcondition_validation_update)
        update_dict.update(decision_update)
        await send_progress_event(
            session_id=session_id,
            step="data_analytics",
            step_name="品牌联想圈层分析",
            progress=1.0,
            message="品牌联想圈层分析完成",
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
        await send_error_event(session_id, "A5", error_text, recoverable=True)
        await send_progress_event(
            session_id=session_id,
            step="data_analytics",
            step_name="品牌联想圈层分析",
            progress=1.0,
            message=f"品牌联想圈层分析出错: {error_text}",
            status="error",
        )
        return Command(
            update={
                "current_step": "A5",
                "error_info": {
                    "step": "A5",
                    "error": error_text,
                    "category": "system",
                    "timestamp": datetime.now().isoformat(),
                },
                "execution_status": "error",
                "awaiting_user": False,
            }
        )


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
    raw_analysis_mode = _resolve_a5_analysis_mode(state, facts.analysis_mode)
    is_association_circle = is_association_circle_mode(raw_analysis_mode)
    report_kind = (
        ASSOCIATION_CIRCLE_REPORT_KIND
        if is_association_circle
        else normalize_report_kind(raw_analysis_mode)
    )
    analysis_mode = (
        ASSOCIATION_CIRCLE_REPORT_KIND
        if is_association_circle
        else "baseline" if report_kind == "panorama" else "persona"
    )
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

    if is_association_circle:
        return await _run_association_circle_report(
            state=state,
            session_id=session_id,
            entity_id=entity_id,
            brand_profile=brand_profile,
            fetch_results=fetch_results,
            analysis_mode=analysis_mode,
            report_kind=report_kind,
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
        monitoring_metadata = {
            "monitoring_schedule_id": state.get("monitoring_schedule_id"),
            "monitoring_plan_id": state.get("monitoring_plan_id"),
            "question_set_ids": state.get("question_set_ids") or [],
            "endpoint_ids": state.get("endpoint_ids") or [],
            "run_policy": state.get("run_policy"),
        }
        monitoring_metadata = {
            key: value for key, value in monitoring_metadata.items() if value
        }

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
                        monitoring_metadata=monitoring_metadata or None,
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
            "monitoring": monitoring_metadata or None,
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
        await _persist_brand_intelligence_report(
            state=state,
            report_kind=report_kind,
            title=report_title,
            artifact_key=artifact_key,
            artifact_message_id=artifact_message_id,
            payload=report_artifact_data,
        )
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
                    citation_metadata = (
                        citation.get("metadata", {})
                        if isinstance(citation, dict)
                        and isinstance(citation.get("metadata"), dict)
                        else {}
                    )
                    url_intelligence = (
                        citation.get("url_intelligence")
                        if isinstance(citation, dict)
                        and isinstance(citation.get("url_intelligence"), dict)
                        else (
                            citation_metadata.get("url_intelligence")
                            if isinstance(
                                citation_metadata.get("url_intelligence"), dict
                            )
                            else {}
                        )
                    )
                    site_category = _clean_source_value(
                        citation.get("site_category")
                        if isinstance(citation, dict)
                        else ""
                    ) or _clean_source_value(citation_metadata.get("site_category"))
                    if not site_category and isinstance(url_intelligence, dict):
                        site_category = _clean_source_value(
                            url_intelligence.get("category")
                        )
                    source_type = _clean_source_value(
                        citation.get("source_type")
                        if isinstance(citation, dict)
                        else ""
                    ) or _clean_source_value(citation_metadata.get("source_type"))
                    if not source_type and site_category:
                        source_type = site_category
                    display_name = _clean_source_value(
                        citation.get("site_display_name")
                        if isinstance(citation, dict)
                        else ""
                    ) or _clean_source_value(
                        citation.get("site_name") if isinstance(citation, dict) else ""
                    )
                    if not display_name and isinstance(url_intelligence, dict):
                        display_name = _clean_source_value(
                            url_intelligence.get("site_name")
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
                                "display_names": {},
                                "source_types": {},
                                "site_categories": {},
                            }
                        domain_stats[citation_domain]["count"] += 1
                        domain_stats[citation_domain]["is_official"] = bool(
                            domain_stats[citation_domain]["is_official"] or is_official
                        )
                        if display_name:
                            display_names = domain_stats[citation_domain][
                                "display_names"
                            ]
                            display_names[display_name] = (
                                display_names.get(display_name, 0) + 1
                            )
                        if source_type:
                            source_types = domain_stats[citation_domain]["source_types"]
                            source_types[source_type] = (
                                source_types.get(source_type, 0) + 1
                            )
                        if site_category:
                            site_categories = domain_stats[citation_domain][
                                "site_categories"
                            ]
                            site_categories[site_category] = (
                                site_categories.get(site_category, 0) + 1
                            )
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
                "display_name": (
                    max(
                        stats["display_names"],
                        key=stats["display_names"].get,
                    )
                    if stats.get("display_names")
                    else ""
                ),
                "count": stats["count"],
                "share": round(stats["count"] / total_cit * 100, 1),
                "is_official": stats["is_official"],
                "source_type": (
                    max(stats["source_types"], key=stats["source_types"].get)
                    if stats.get("source_types")
                    else ("official" if stats["is_official"] else "unknown")
                ),
                "site_category": (
                    max(
                        stats["site_categories"],
                        key=stats["site_categories"].get,
                    )
                    if stats.get("site_categories")
                    else None
                ),
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
