"""Executor node for site-level confidence assessment."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from langgraph.types import Command

from app.core.database import AsyncSessionLocal
from app.models.task import AnalysisTask, TaskStatus
from app.services.task_service import TaskService
from app.workflow.events import (
    send_error_event,
    send_progress_event,
)
from app.workflow.harness_validation import (
    build_harness_decision,
    evaluate_skill_postconditions,
    evaluate_skill_preconditions,
    validate_artifact_writeback,
)
from app.workflow.site_confidence_assessment import (
    DEFAULT_MAX_PAGES,
    DEFAULT_SCAN_MODE,
    _normalize_scan_page_limit,
    generate_site_confidence_artifact,
)
from app.workflow.skill_state import (
    build_harness_decision_update,
    build_skill_result_update,
    build_validation_result_update,
)
from app.workflow.state import AgentState

logger = logging.getLogger(__name__)
_LIVE_TASK_STATUSES = {TaskStatus.PENDING, TaskStatus.RUNNING}


def _extract_root_url(tool_args: dict[str, Any], state: AgentState) -> str:
    explicit = str(tool_args.get("root_url") or "").strip()
    if explicit:
        return explicit

    latest_text = str(state.get("latest_user_input") or "").strip()
    match = re.search(r"https?://[^\s]+", latest_text, flags=re.IGNORECASE)
    if match:
        return match.group(0)
    return ""


def _extract_domain(url: str) -> str:
    candidate = str(url or "").strip()
    if not candidate:
        return ""
    if not re.match(r"^https?://", candidate, flags=re.IGNORECASE):
        candidate = f"https://{candidate}"
    match = re.search(r"^https?://([^/?#:]+)", candidate, flags=re.IGNORECASE)
    if not match:
        return ""
    return match.group(1).lower().removeprefix("www.")


def _resolve_monitored_brand_name(state: AgentState) -> str:
    return (
        str((state.get("brand_profile") or {}).get("brand_name") or "").strip()
        or str(state.get("brand_name") or "").strip()
        or "当前监测品牌"
    )


def _resolve_monitored_official_website(state: AgentState) -> str:
    return (
        str((state.get("brand_profile") or {}).get("official_website") or "").strip()
        or str(state.get("official_website") or "").strip()
    )


async def _load_live_task(task_id: str | None) -> UUID | None:
    if not task_id:
        return None
    try:
        task_uuid = UUID(str(task_id))
    except (TypeError, ValueError):
        return None

    async with AsyncSessionLocal() as db:
        task = await db.get(AnalysisTask, task_uuid)
        if task is None or task.status not in _LIVE_TASK_STATUSES:
            return None
    return task_uuid


async def _update_task_progress_if_live(
    task_id: str | None,
    *,
    progress: float,
    message: str,
) -> None:
    task_uuid = await _load_live_task(task_id)
    if task_uuid is None:
        return
    try:
        async with AsyncSessionLocal() as db:
            task_service = TaskService(db)
            await task_service.update_progress(
                task_uuid,
                stage="A7",
                progress=progress,
                message=message,
                status=TaskStatus.RUNNING,
            )
    except Exception as exc:
        logger.warning("[SiteConfidence] TaskService update_progress failed: %s", exc)


async def _complete_task_if_live(task_id: str | None) -> None:
    task_uuid = await _load_live_task(task_id)
    if task_uuid is None:
        return
    try:
        async with AsyncSessionLocal() as db:
            task_service = TaskService(db)
            await task_service.complete_task(task_uuid)
    except Exception as exc:
        logger.warning("[SiteConfidence] TaskService complete_task failed: %s", exc)


async def _fail_task_if_live(task_id: str | None, error_message: str) -> None:
    task_uuid = await _load_live_task(task_id)
    if task_uuid is None:
        return
    try:
        async with AsyncSessionLocal() as db:
            task_service = TaskService(db)
            await task_service.fail_task(
                task_uuid,
                error_message=error_message,
                error_stage="A7",
            )
    except Exception as exc:
        logger.warning("[SiteConfidence] TaskService fail_task failed: %s", exc)


async def site_confidence_assessment_executor_node(state: AgentState) -> Command:
    session_id = state["session_id"]
    task_id = state.get("task_id")
    tool_args = dict(state.get("tool_call_args") or {})
    root_url = _extract_root_url(tool_args, state)
    brand_name = _resolve_monitored_brand_name(state)
    official_website = _resolve_monitored_official_website(state)
    scan_mode = (
        str(tool_args.get("scan_mode") or DEFAULT_SCAN_MODE).strip()
        or DEFAULT_SCAN_MODE
    )
    max_pages = _normalize_scan_page_limit(
        tool_args.get("max_pages") or DEFAULT_MAX_PAGES
    )

    precondition_result = evaluate_skill_preconditions(
        state,
        state.get("current_skill_contract"),
    )
    if not precondition_result.passed:
        message = f"官网 AI 友好度评估前置条件未满足：{precondition_result.reason}"
        await send_error_event(session_id, "A7", message, recoverable=True)
        validation_update = build_validation_result_update(state, precondition_result)
        decision_update = build_harness_decision_update(
            {**state, **validation_update},
            build_harness_decision(
                decision_type="fail_step",
                reason=message,
                recoverable=True,
                metadata={"step": "A7", "gate": "precondition_gate"},
            ),
        )
        return Command(
            update={
                "error_info": {
                    "step": "A7",
                    "error": message,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                "current_step": "A7",
                "execution_status": "error",
                **validation_update,
                **decision_update,
            }
        )

    if not root_url:
        message = "当前没有明确官网地址，无法启动官网 AI 友好度评估。请先提供官网 URL。"
        await send_error_event(session_id, "A7", message, recoverable=True)
        decision_update = build_harness_decision_update(
            state,
            build_harness_decision(
                decision_type="fail_step",
                reason=message,
                recoverable=True,
                metadata={"step": "A7", "gate": "root_url_required"},
            ),
        )
        return Command(
            update={
                "error_info": {
                    "step": "A7",
                    "error": message,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                "current_step": "A7",
                "execution_status": "error",
                **decision_update,
            }
        )

    if not official_website:
        message = (
            f"当前还没有绑定 {brand_name} 的官网地址。"
            "官网 AI 友好度评估当前只服务于被监测品牌自己的官网，请先补齐品牌官网后再执行。"
        )
        await send_error_event(session_id, "A7", message, recoverable=True)
        decision_update = build_harness_decision_update(
            state,
            build_harness_decision(
                decision_type="fail_step",
                reason=message,
                recoverable=True,
                metadata={"step": "A7", "gate": "official_website_required"},
            ),
        )
        return Command(
            update={
                "error_info": {
                    "step": "A7",
                    "error": message,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                "current_step": "A7",
                "execution_status": "error",
                **decision_update,
            }
        )

    requested_domain = _extract_domain(root_url)
    official_domain = _extract_domain(official_website)
    if (
        requested_domain
        and official_domain
        and requested_domain != official_domain
        and not requested_domain.endswith(f".{official_domain}")
        and not official_domain.endswith(f".{requested_domain}")
    ):
        message = (
            f"当前官网评估只允许扫描被监测品牌 {brand_name} 自己的官网。"
            f"当前品牌官网是 {official_website}，但这次请求的是 {root_url}，超出了当前能力边界。"
        )
        await send_error_event(session_id, "A7", message, recoverable=True)
        decision_update = build_harness_decision_update(
            state,
            build_harness_decision(
                decision_type="fail_step",
                reason=message,
                recoverable=True,
                metadata={
                    "step": "A7",
                    "gate": "official_website_scope_guard",
                    "requested_domain": requested_domain,
                    "official_domain": official_domain,
                },
            ),
        )
        return Command(
            update={
                "error_info": {
                    "step": "A7",
                    "error": message,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                "current_step": "A7",
                "execution_status": "error",
                **decision_update,
            }
        )

    try:
        await send_progress_event(
            session_id=session_id,
            step="A7",
            step_name="官网 AI 友好度",
            progress=0.15,
            message="正在发现官网首页及关键一二级页面...",
        )
        await _update_task_progress_if_live(
            task_id,
            progress=0.15,
            message="正在发现官网首页及关键一二级页面...",
        )
        await send_progress_event(
            session_id=session_id,
            step="A7",
            step_name="官网 AI 友好度",
            progress=0.55,
            message="正在评估页面可访问性、语义结构和结构化信号...",
        )
        await _update_task_progress_if_live(
            task_id,
            progress=0.55,
            message="正在评估官网结构和可抓取信号...",
        )

        artifact_result = await generate_site_confidence_artifact(
            session_id=session_id,
            root_url=root_url,
            scan_mode=scan_mode,
            max_pages=max_pages,
        )
        report_data = dict(artifact_result.get("report_data") or {})
        coverage_summary = dict(report_data.get("coverage_summary") or {})
        overall_score = report_data.get("overall_score")
        preview_description = str(report_data.get("preview_description") or "").strip()
        evaluated_pages = int(coverage_summary.get("evaluated_page_count") or 0)
        fetched_pages = int(coverage_summary.get("fetched_page_count") or 0)
        site_confidence_reply = (
            f"官网 AI 友好度报告已生成。当前平均分 {float(overall_score or 0):.1f} / 100，本轮评估 {evaluated_pages} 个页面，成功抓回 {fetched_pages} 个页面。{preview_description}"
            if isinstance(overall_score, (int, float))
            else f"官网 AI 友好度报告已生成。{preview_description}"
        ).strip()
        artifact_validation = validate_artifact_writeback(
            gate_name="artifact_writeback_gate",
            artifact_message_id=artifact_result.get("artifact_message_id"),
            artifact_key=artifact_result.get("artifact_key"),
            artifact_kind=artifact_result.get(
                "artifact_kind", "site_confidence_report"
            ),
            metadata={
                "root_url": root_url,
                "scan_mode": scan_mode,
                "scan_quality_status": report_data.get("scan_quality_status"),
                "evaluated_page_count": coverage_summary.get("evaluated_page_count"),
                "max_pages_applied": report_data.get("max_pages_applied"),
            },
        )
        if not artifact_validation.passed:
            raise RuntimeError(artifact_validation.reason)

        await send_progress_event(
            session_id=session_id,
            step="A7",
            step_name="官网 AI 友好度",
            progress=1.0,
            message="官网 AI 友好度已完成",
            status="completed",
        )
        await _complete_task_if_live(task_id)

        skill_update = build_skill_result_update(
            state,
            skill_key=state.get("current_skill"),
            tool_name=str(
                state.get("current_skill") or "site_confidence_assessment_skill"
            ),
            status="completed",
            summary="官网 AI 友好度报告已写入画布。",
            executor_ref="site_confidence_assessment_executor",
            metadata={
                "root_url": root_url,
                "root_domain": report_data.get("root_domain"),
                "scan_mode": scan_mode,
                "scan_quality_status": report_data.get("scan_quality_status"),
                "evaluated_page_count": coverage_summary.get("evaluated_page_count"),
                "max_pages_applied": report_data.get("max_pages_applied"),
            },
        )
        artifact_validation_update = build_validation_result_update(
            state, artifact_validation
        )
        validation_state = {**state, **skill_update, **artifact_validation_update}
        postcondition_result = evaluate_skill_postconditions(
            state=state,
            contract_payload=state.get("current_skill_contract"),
            pending_update=skill_update,
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
                reason="Site confidence harness gates passed.",
                recoverable=False,
                metadata={
                    "step": "A7",
                    "root_url": root_url,
                    "scan_mode": scan_mode,
                    "scan_quality_status": report_data.get("scan_quality_status"),
                    "max_pages_applied": report_data.get("max_pages_applied"),
                },
            ),
        )
        return Command(
            update={
                "error_info": None,
                "current_step": "A7",
                "progress": 1.0,
                "execution_status": "completed",
                "orchestrator_reply": site_confidence_reply,
                "site_confidence_report_message": site_confidence_reply,
                "site_confidence_report_summary": {
                    "headline": report_data.get("headline"),
                    "root_domain": report_data.get("root_domain"),
                    "overall_score": overall_score,
                    "scan_quality_status": report_data.get("scan_quality_status"),
                },
                **skill_update,
                **artifact_validation_update,
                **postcondition_validation_update,
                **decision_update,
            }
        )
    except Exception as exc:
        logger.exception("[SiteConfidence] Artifact generation failed: %s", exc)
        await send_error_event(session_id, "A7", str(exc), recoverable=True)
        await _fail_task_if_live(task_id, str(exc))
        return Command(
            update={
                "error_info": {
                    "step": "A7",
                    "error": str(exc),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                "current_step": "A7",
                "execution_status": "error",
                **build_harness_decision_update(
                    state,
                    build_harness_decision(
                        decision_type="retry_step",
                        reason=str(exc),
                        recoverable=True,
                        metadata={
                            "step": "A7",
                            "root_url": root_url,
                            "scan_mode": scan_mode,
                            "max_pages_applied": max_pages,
                        },
                    ),
                ),
            }
        )
