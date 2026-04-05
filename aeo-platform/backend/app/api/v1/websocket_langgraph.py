"""WebSocket handlers for LangGraph workflow integration.

This module provides WebSocket endpoints that integrate with the LangGraph workflow.
Adapted for orchestrator-based dynamic routing (no hardcoded EXECUTION_STEPS).
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, TypedDict
from uuid import UUID

from fastapi import APIRouter, WebSocket
from langchain_core.messages import HumanMessage, AIMessage

from app.workflow.graph import get_compiled_workflow
from app.workflow.state import AgentState
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.task_run import LIVE_TASK_RUN_STATUSES
from app.models.task_run_child_attempt import TaskRunChildAttemptStatus
from app.services.message_service import MessageService
from app.services.entity_service import EntityService
from app.services.session_event_publisher import session_event_publisher
from app.services.task_service import TaskService
from app.services.task_run_child_attempt_service import TaskRunChildAttemptService
from app.services.aio_session_manager import aio_session_manager
from app.models.session import Session
from app.models.message import Message, MessageType
from app.workflow.confidence_analysis import (
    append_confidence_analysis_manual_items_async,
)
from app.workflow.browser_action_runtime import (
    clear_session_browser_action_requests,
    get_browser_action_request,
    get_session_browser_action_requests,
    infer_browser_action_state,
    resolve_browser_action_request,
    update_browser_action_request,
)
from app.workflow.confirmation import resolve_confirmation_selection

from sqlalchemy import select

logger = logging.getLogger(__name__)
router = APIRouter()
ws_session_manager = session_event_publisher


# ---------------------------------------------------------------------------
# Confirmation Protocol Types
# ---------------------------------------------------------------------------
# These TypedDicts define the structured selection payloads sent by the
# frontend via the ``confirmation`` WebSocket event.  The ``type`` field
# discriminates between variants.


class PersonaPathSelection(TypedDict):
    """Frontend sends this when the user selects personas from the pipeline."""

    type: Literal["persona_path_selection"]
    selectedPersonaIds: list[str]
    selectedPersonaNames: list[str]


class SkipSelection(TypedDict):
    """Frontend sends this when the user clicks 'skip' on persona selection."""

    type: Literal["skip"]


# Union of all structured confirmation payloads
ConfirmationSelection = PersonaPathSelection | SkipSelection


# Step progression for inferring progress from restored state
_STEP_PROGRESS: dict[str, float] = {
    "A1": 0.2,
    "A2": 0.35,
    "A3": 0.5,
    "A4": 0.6,
    "A7": 0.75,
    "A5": 0.9,
}

_SUPPORTED_TOOL_MODES = {"confidence_analysis"}


async def _emit_session_error(
    session_id: str,
    payload: dict[str, Any],
) -> None:
    """Emit a session-scoped error through the shared event publisher."""

    await session_event_publisher.emit_to_session(
        session_id,
        "error",
        payload,
        bypass_runtime_guard=True,
    )


def _state_is_waiting_for_user(state_values: dict[str, Any]) -> bool:
    """Return True when the workflow ended because it needs user input."""

    return bool(
        state_values.get("awaiting_user")
        or state_values.get("execution_status") == "awaiting_user"
        or state_values.get("pending_confirmation")
    )


def _build_waiting_input_message(state_values: dict[str, Any]) -> str:
    """Build a concise task progress message for waiting-input states."""

    pending_confirmation = state_values.get("pending_confirmation") or {}
    step_name = pending_confirmation.get("step_name")
    if step_name:
        return f"等待用户确认：{step_name}"
    progress_message = state_values.get("progress_message")
    if isinstance(progress_message, str) and progress_message.strip():
        return progress_message
    return "等待用户输入..."


def _takeover_bundle_is_reusable(takeover: Any) -> bool:
    """Return True only when an existing takeover bundle is still safe to reuse."""

    if not isinstance(takeover, dict):
        return False

    takeover_id = takeover.get("takeover_id")
    expires_at = takeover.get("expires_at")
    required_paths = (
        "canvas_config_path",
        "vnc_url_path",
        "heartbeat_path",
        "resolve_path",
        "cancel_path",
    )
    if not isinstance(takeover_id, str) or not takeover_id.strip():
        return False
    if not isinstance(expires_at, str) or not expires_at.strip():
        return False
    if any(not isinstance(takeover.get(path), str) for path in required_paths):
        return False

    normalized = expires_at.replace("Z", "+00:00")
    try:
        expires_dt = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    if expires_dt.tzinfo is None:
        expires_dt = expires_dt.replace(tzinfo=timezone.utc)
    return expires_dt > datetime.now(timezone.utc)


async def _rehydrate_aio_takeover_bundle(
    *,
    request_id: str,
    platform: str,
    action_type: str,
    message: str,
    task_id: UUID,
    task_run_id: UUID,
    user_id: UUID,
) -> dict[str, Any] | None:
    """Re-issue an AIO takeover bundle for a durable waiting_input record."""

    if not settings.AIO_ENABLED or not settings.AIO_BASE_URL:
        return None

    try:
        session = await aio_session_manager.ensure_workspace_session(
            workspace_id=str(user_id),
        )
        takeover = await aio_session_manager.create_takeover_access(
            session_id=session.session_id,
            user_id=str(user_id),
            platform=platform,
            mode=settings.AIO_DEFAULT_ACCESS_MODE,
            reason=message or action_type,
            request_id=request_id,
            task_id=str(task_id),
            run_id=str(task_run_id),
            action_type=action_type,
        )
    except Exception:
        logger.exception(
            "[WebSocket] Failed to rehydrate AIO takeover for request %s (platform=%s task_id=%s)",
            request_id,
            platform,
            task_id,
        )
        return None

    return {
        "takeover_id": takeover.takeover_id,
        "mode": takeover.mode,
        "canvas_config_path": f"/api/v1/aio/takeovers/{takeover.takeover_id}/canvas-config",
        "vnc_url_path": f"/api/v1/aio/takeovers/{takeover.takeover_id}/vnc-url",
        "heartbeat_path": f"/api/v1/aio/takeovers/{takeover.takeover_id}/heartbeat",
        "resolve_path": f"/api/v1/aio/takeovers/{takeover.takeover_id}/resolve",
        "cancel_path": f"/api/v1/aio/takeovers/{takeover.takeover_id}/cancel",
        "expires_at": takeover.expires_at.isoformat(),
    }


async def replay_pending_browser_actions_to_websocket(
    websocket: WebSocket,
    session_id: str,
) -> None:
    """Replay unresolved browser-action requests to a freshly connected socket."""

    raw_pending_requests = await get_session_browser_action_requests(session_id)
    runtime_request_count = len(raw_pending_requests)
    pending_requests: list[dict[str, Any]] = []

    try:
        async with AsyncSessionLocal() as db:
            task_service = TaskService(db)
            await task_service.reconcile_terminal_task_live_runs(UUID(session_id))
            active_task = await task_service.get_session_active_task(UUID(session_id))
            authoritative_task_id = (
                active_task.id if active_task is not None else None
            )
            authoritative_run_id = None
            if active_task is not None:
                loaded_runs = active_task.__dict__.get("task_runs") or []
                live_run = next(
                    (
                        run
                        for run in loaded_runs
                        if getattr(run, "status", None) in LIVE_TASK_RUN_STATUSES
                    ),
                    None,
                )
                authoritative_run_id = getattr(live_run, "id", None)

            service = TaskRunChildAttemptService(db)
            if authoritative_task_id is None:
                db_attempts = []
            else:
                db_attempts = await service.list_waiting_input_replay_records_for_session(
                    UUID(session_id),
                    task_id=authoritative_task_id,
                    task_run_id=authoritative_run_id,
                )
    except Exception:
        logger.exception(
            "[WebSocket] Failed to query waiting_input child attempts for session %s",
            session_id,
        )
        db_attempts = []
        authoritative_run_id = None

    attempts_by_request_id = {
        attempt.request_id: attempt
        for attempt in db_attempts
        if getattr(attempt, "request_id", None)
    }
    authoritative_request_ids = set(attempts_by_request_id.keys())

    filtered_runtime_count = 0
    for request in raw_pending_requests:
        request_id = request.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            continue

        request_run_id = request.get("run_id")
        if authoritative_run_id is not None:
            if isinstance(request_run_id, str) and request_run_id:
                if request_run_id != str(authoritative_run_id):
                    filtered_runtime_count += 1
                    continue
            elif authoritative_request_ids and request_id not in authoritative_request_ids:
                filtered_runtime_count += 1
                continue
        elif authoritative_request_ids and request_id not in authoritative_request_ids:
            filtered_runtime_count += 1
            continue
        elif not authoritative_request_ids:
            filtered_runtime_count += 1
            continue

        pending_requests.append(request)

    seen_request_ids: set[str] = {
        request.get("request_id")
        for request in pending_requests
        if isinstance(request.get("request_id"), str)
    }

    runtime_rehydrated_count = 0
    for request in pending_requests:
        request_id = request.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            continue
        existing_takeover = request.get("takeover")
        if _takeover_bundle_is_reusable(existing_takeover):
            continue

        attempt = attempts_by_request_id.get(request_id)
        if attempt is None:
            continue

        takeover = await _rehydrate_aio_takeover_bundle(
            request_id=request_id,
            platform=attempt.platform,
            action_type=attempt.action_type,
            message=attempt.message,
            task_id=attempt.task_id,
            task_run_id=attempt.task_run_id,
            user_id=attempt.user_id,
        )
        if not isinstance(takeover, dict):
            continue

        request["takeover"] = takeover
        runtime_rehydrated_count += 1
        request_state = request.get("state")
        await update_browser_action_request(
            request_id,
            state=(
                request_state
                if isinstance(request_state, str)
                else infer_browser_action_state(attempt.action_type)
            ),
            takeover=takeover,
        )

    db_fallback_count = 0
    for attempt in db_attempts:
        request_id = attempt.request_id
        if not request_id or request_id in seen_request_ids:
            continue
        takeover = await _rehydrate_aio_takeover_bundle(
            request_id=request_id,
            platform=attempt.platform,
            action_type=attempt.action_type,
            message=attempt.message,
            task_id=attempt.task_id,
            task_run_id=attempt.task_run_id,
            user_id=attempt.user_id,
        )
        pending_requests.append(
            {
                "request_id": request_id,
                "platform": attempt.platform,
                "action_type": attempt.action_type,
                "message": attempt.message,
                "action_hint": attempt.action_hint,
                "progress": attempt.progress,
                "state": infer_browser_action_state(attempt.action_type),
                "takeover": takeover,
            }
        )
        seen_request_ids.add(request_id)
        db_fallback_count += 1

    if not pending_requests:
        return

    logger.info(
        "[WebSocket] Replaying %d browser-action request(s) for session %s "
        "(runtime=%d, runtime_filtered=%d, runtime_rehydrated=%d, db_fallback=%d)",
        len(pending_requests),
        session_id,
        runtime_request_count,
        filtered_runtime_count,
        runtime_rehydrated_count,
        db_fallback_count,
    )

    for request in pending_requests:
        request_id = request.get("request_id")
        platform = request.get("platform")
        state = request.get("state")
        action_type = request.get("action_type")
        message = request.get("message")
        progress = request.get("progress")
        if not all(
            isinstance(value, str)
            for value in [request_id, platform, state, action_type, message]
        ):
            continue

        payload: dict[str, Any] = {
            "platform": platform,
            "state": state,
            "message": message,
            "progress": float(progress or 0.0),
            "requires_action": True,
            "action_hint": request.get("action_hint"),
            "request_id": request_id,
        }
        takeover = request.get("takeover")
        if isinstance(takeover, dict):
            payload["takeover"] = takeover

        await session_event_publisher.emit_to_websocket(
            websocket,
            "browser_state",
            payload,
        )
        await session_event_publisher.emit_to_websocket(
            websocket,
            "browser_user_action",
            {
                **payload,
                "action_type": action_type,
            },
        )


def _is_persona_selection_confirmation(
    selection: str | dict[str, Any] | None,
    option_id: str,
) -> bool:
    """Return True when the confirmation payload targets A2 persona selection."""

    if isinstance(selection, dict):
        selection_type = selection.get("type")
        return selection_type in {"persona_path_selection", "skip"}

    normalized = option_id.strip().lower()
    if normalized == "skip":
        return True
    if isinstance(selection, str):
        return selection.strip().lower() == "skip"
    return False


def _validate_confirmation_request_id(
    state_values: dict[str, Any],
    request_id: str,
    selection: str | dict[str, Any] | None,
    option_id: str,
) -> tuple[bool, bool]:
    """Validate request_id against current pending confirmation.

    Returns:
        (allowed, used_legacy_fallback)
    """

    pending_confirmation = state_values.get("pending_confirmation") or {}
    if not isinstance(pending_confirmation, dict):
        return True, False

    pending_request_id = pending_confirmation.get("request_id")
    pending_step_id = pending_confirmation.get("step_id")
    expected_request_id = (
        pending_request_id.strip() if isinstance(pending_request_id, str) else ""
    )
    step_id = pending_step_id.strip() if isinstance(pending_step_id, str) else ""

    if step_id != "A2_PERSONA_SELECTION":
        return True, False

    if not expected_request_id:
        return True, False

    if request_id:
        return request_id == expected_request_id, False

    is_legacy_persona_selection = (
        step_id == "A2_PERSONA_SELECTION"
        and _is_persona_selection_confirmation(selection, option_id)
    )
    return is_legacy_persona_selection, is_legacy_persona_selection


def _has_reusable_runtime_context(state_values: dict[str, Any]) -> bool:
    """Return True when state contains prior orchestration context to continue."""

    if state_values.get("task_id") or state_values.get("run_id"):
        return True

    reusable_keys = (
        "brand_profile",
        "competitors",
        "competitive_landscape",
        "marketing_personas",
        "simulated_questions",
        "questions",
        "fetch_results",
        "metrics",
        "report",
        "baseline_questions",
        "baseline_fetch_results",
        "baseline_metrics",
        "baseline_report",
    )
    if any(state_values.get(key) for key in reusable_keys):
        return True

    history = state_values.get("orchestrator_history") or []
    return any(
        isinstance(item, dict) and item.get("role") in {"assistant", "agent"}
        for item in history
    )


def _reset_follow_up_runtime_state(state_values: dict[str, Any]) -> None:
    """Clear stale blockers before resuming orchestration from a prior session."""

    state_values["awaiting_user"] = False
    state_values["pending_confirmation"] = None
    state_values["error_info"] = None
    state_values["execution_status"] = "running"


def _normalize_attachment_refs(raw_attachments: Any) -> list[dict[str, Any]]:
    """Normalize attachment refs from websocket payload."""

    normalized: list[dict[str, Any]] = []
    if not isinstance(raw_attachments, list):
        return normalized

    for item in raw_attachments:
        if not isinstance(item, dict):
            continue
        file_id = str(item.get("file_id") or item.get("id") or "").strip()
        if not file_id:
            continue
        normalized.append(
            {
                "file_id": file_id,
                "name": str(item.get("name") or "").strip(),
                "mime_type": str(
                    item.get("mime_type") or item.get("type") or ""
                ).strip(),
                "size": int(item.get("size") or 0),
                "sheet_hint": str(item.get("sheet_hint") or "").strip() or None,
            }
        )
    return normalized


def _normalize_tool_mode(raw_tool_mode: Any) -> str | None:
    candidate = str(raw_tool_mode or "").strip()
    if candidate in _SUPPORTED_TOOL_MODES:
        return candidate
    return None


def _build_attachment_summary(attachments: list[dict[str, Any]]) -> str:
    if not attachments:
        return ""
    names = [attachment.get("name") or "未命名表格" for attachment in attachments]
    if len(names) == 1:
        return f"用户上传了表格附件：{names[0]}"
    return "用户上传了多个表格附件：" + "、".join(names)


def _resolve_task_label(
    *,
    brand_name: str,
    content: str,
    attachments: list[dict[str, Any]],
    tool_mode: str | None = None,
) -> str:
    candidate_brand = brand_name.strip()
    if candidate_brand:
        return candidate_brand

    if tool_mode == "confidence_analysis":
        if attachments:
            attachment_name = str(attachments[0].get("name") or "").strip()
            attachment_stem = Path(attachment_name).stem.strip()
            if attachment_stem:
                return f"置信度分析：{attachment_stem}"
        return "置信度分析"

    candidate_content = content.strip()
    if candidate_content:
        return candidate_content

    if attachments:
        attachment_name = str(attachments[0].get("name") or "").strip()
        attachment_stem = Path(attachment_name).stem.strip()
        if attachment_stem:
            return f"表格导入：{attachment_stem}"

    return "表格导入任务"


async def _ensure_manual_session_is_idle(
    *,
    session_id: str,
    allowed_waiting_task_id: str | None = None,
) -> None:
    """Reject new manual work when the session already has an active task."""

    from app.services.runtime_coordinator import runtime_coordinator
    from app.models.task_run import TaskRunStatus
    from app.services.task_service import TaskService

    if await runtime_coordinator.has_live_session_execution(session_id):
        raise RuntimeError("当前任务尚未完全停止，请稍候再试。")

    async with AsyncSessionLocal() as db:
        task_service = TaskService(db)
        await task_service.reconcile_terminal_task_live_runs(UUID(session_id))
        live_pairs = await task_service.list_session_live_runs(UUID(session_id))
        if not live_pairs:
            return

        active_task, latest_run = live_pairs[0]
        if (
            allowed_waiting_task_id is not None
            and str(active_task.id) == allowed_waiting_task_id
            and latest_run is not None
            and latest_run.status == TaskRunStatus.WAITING_INPUT
        ):
            return

        raise RuntimeError("当前任务仍在执行，请等待完成或先停止后再继续。")


async def _submit_resume_run(
    task_id: str | None,
    *,
    trigger_source: str = "websocket",
) -> str | None:
    """Create and start a new runtime attempt when a paused flow resumes."""

    if not task_id:
        return None

    try:
        from app.models.task_run import TaskRunKind, TaskTriggerSource
        from app.services.job_dispatcher import JobDispatcher
        from app.services.job_submission_service import JobSubmissionService
        from app.services.task_service import TaskService

        async with AsyncSessionLocal() as db:
            submission_service = JobSubmissionService(db)
            submitted = await submission_service.submit_existing_task_run(
                task_id=UUID(task_id),
                run_kind=TaskRunKind.RESUME_AFTER_INPUT,
                trigger_source=TaskTriggerSource(trigger_source),
            )
            dispatcher = JobDispatcher(db)
            await dispatcher.claim_run(
                task_id=submitted.task.id,
                run_id=submitted.run.id,
                lease_owner=f"ws:{submitted.task.session_id}",
                executor_ref=f"session:{submitted.task.session_id}",
            )
            task_service = TaskService(db)
            await task_service.start_task(
                submitted.task.id,
                run_id=submitted.run.id,
                lease_owner=f"ws:{submitted.task.session_id}",
            )
            logger.info(
                "[LangGraph] Submitted resume run %s for task %s",
                submitted.run.id,
                submitted.task.id,
            )
            return str(submitted.run.id)
    except Exception as exc:
        logger.warning("[LangGraph] Failed to submit resume run: %s", exc)
        return None


async def _is_waiting_task_resumable(task_id: str | None) -> bool:
    """Return True when durable state still allows a waiting-input resume."""

    if not task_id:
        return False

    from app.models.task import TaskStatus
    from app.models.task_run import TaskRunStatus
    from app.services.task_service import TaskService

    async with AsyncSessionLocal() as db:
        task_service = TaskService(db)
        task = await task_service.get_task(UUID(task_id))
        if task is None or task.status != TaskStatus.RUNNING:
            return False

        loaded_runs = task.__dict__.get("task_runs") or []
        latest_run = loaded_runs[0] if loaded_runs else None
        return bool(
            latest_run is not None and latest_run.status == TaskRunStatus.WAITING_INPUT
        )


async def _submit_manual_task(
    *,
    user_id: UUID,
    session_id: str,
    brand_name: str,
    entity_id: str | None,
    run_kind: Literal["initial", "follow_up"],
    trigger_source: str = "websocket",
) -> tuple[str, str]:
    """Create, claim, and start a manual runtime task for the session."""

    from app.models.task_run import TaskRunKind, TaskTriggerSource
    from app.services.job_dispatcher import JobDispatcher
    from app.services.job_submission_service import JobSubmissionService
    from app.services.task_service import TaskService

    async with AsyncSessionLocal() as db:
        task_service = TaskService(db)
        active_task = await task_service.get_session_active_task(UUID(session_id))
        if active_task is not None:
            raise RuntimeError("当前任务仍在执行，请等待完成或先停止后再继续。")

        submission_service = JobSubmissionService(db)
        if run_kind == TaskRunKind.FOLLOW_UP.value:
            submitted = await submission_service.submit_follow_up_analysis(
                user_id=user_id,
                session_id=UUID(session_id),
                brand_name=brand_name,
                entity_id=UUID(entity_id) if entity_id else None,
                trigger_source=TaskTriggerSource(trigger_source),
            )
        else:
            submitted = await submission_service.submit_manual_analysis(
                user_id=user_id,
                session_id=UUID(session_id),
                brand_name=brand_name,
                entity_id=UUID(entity_id) if entity_id else None,
                trigger_source=TaskTriggerSource(trigger_source),
            )

        dispatcher = JobDispatcher(db)
        await dispatcher.claim_run(
            task_id=submitted.task.id,
            run_id=submitted.run.id,
            lease_owner=_lease_owner_for_session(session_id),
            executor_ref=f"session:{session_id}",
        )
        await task_service.start_task(
            submitted.task.id,
            run_id=submitted.run.id,
            lease_owner=_lease_owner_for_session(session_id),
        )

        logger.info(
            "[LangGraph] Submitted manual task %s / run %s for session %s " "(kind=%s)",
            submitted.task.id,
            submitted.run.id,
            session_id,
            run_kind,
        )
        return str(submitted.task.id), str(submitted.run.id)


def _lease_owner_for_session(session_id: str) -> str:
    """Return a stable lease owner identifier for local WebSocket execution."""

    return f"ws:{session_id}"


async def _bind_current_local_execution(
    *,
    session_id: str,
    task_id: str | None,
    run_id: str | None,
) -> None:
    """Bind the currently running coroutine to the durable TaskRun."""

    if not task_id or not run_id:
        return

    current_task = asyncio.current_task()
    if current_task is None:
        return

    from app.services.runtime_coordinator import runtime_coordinator

    await runtime_coordinator.register_local_execution(
        session_id=session_id,
        task_id=UUID(task_id),
        run_id=UUID(run_id),
        lease_owner=_lease_owner_for_session(session_id),
        execution_task=current_task,
    )


async def _finalize_cancelled_runtime_if_requested(
    *,
    task_id: str | None,
    run_id: str | None,
) -> None:
    """Finalize a cancelled runtime attempt when the stop request is durable."""

    if not task_id:
        return

    from app.services.task_service import TaskService

    async with AsyncSessionLocal() as db:
        task_service = TaskService(db)
        await task_service.finalize_cancel_if_requested(
            UUID(task_id),
            run_id=UUID(run_id) if run_id else None,
        )


async def _sync_runtime_after_stream(workflow, config: dict[str, Any]) -> None:
    """Persist runtime state after a stream run finishes."""

    try:
        current_state = workflow.get_state(config)
        if not current_state or not current_state.values:
            return

        state_values = dict(current_state.values)
        from app.services.task_service import TaskService

        task_id = state_values.get("task_id")
        run_id = state_values.get("run_id")
        if not task_id or not run_id:
            return

        async with AsyncSessionLocal() as db:
            task_service = TaskService(db)
            if _state_is_waiting_for_user(state_values):
                await task_service.mark_waiting_for_input(
                    UUID(task_id),
                    run_id=UUID(run_id),
                    checkpoint_stage=state_values.get("current_step"),
                    progress_message=_build_waiting_input_message(state_values),
                )
                return

            if state_values.get("execution_status") == "completed":
                await task_service.complete_task(
                    UUID(task_id),
                    run_id=UUID(run_id),
                )
    except Exception as exc:
        logger.warning("[LangGraph] Failed to sync final runtime state: %s", exc)


async def rebuild_state_from_db(
    session_id: str, entity_id: str | None = None
) -> dict[str, Any]:
    """Rebuild AgentState from database messages when MemorySaver state is lost.

    Scans all OUTPUT messages for the session and reconstructs agent outputs
    (brand_profile, competitors, personas, questions, fetch_results, metrics, report).
    Also rebuilds orchestrator_history from user/agent message pairs.

    Returns:
        A dict compatible with AgentState fields.
    """
    state: dict[str, Any] = {
        "session_id": session_id,
        "user_id": None,
        "entity_id": entity_id,
        "messages": [],
        "brand_name": "",
        "official_website": "",
        "industry_hint": "",
        # A1
        "brand_profile": None,
        "competitors": None,
        "competitive_landscape": None,
        # A2
        "marketing_personas": None,
        # A3
        "simulated_questions": None,
        "questions": None,
        # A4
        "fetch_results": None,
        # A5
        "metrics": None,
        "report": None,
        # Execution control
        "current_step": "",
        "execution_status": "running",
        "progress": 0.0,
        "progress_message": "恢复中...",
        # Human-in-loop
        "pending_confirmation": None,
        "user_decisions": {},
        # Error
        "error_info": None,
        # Orchestrator
        "orchestrator_history": [],
        "orchestrator_reply": None,
        "next_action": None,
        "awaiting_user": False,
        "tool_call_args": None,
        "tool_call_id": None,
        "current_skill": None,
        "current_skill_family": None,
        "current_skill_package_key": None,
        "current_skill_package_name": None,
        "current_skill_package_path": None,
        "current_skill_package_context": None,
        "current_skill_prompt_overlay": None,
        "last_skill_result": None,
        "skill_history": [],
        "pending_table_intake": None,
        "table_intake_result": None,
        "confirmed_import_action": None,
        "import_source_metadata": None,
        "selected_tool_mode": None,
        "latest_user_input": None,
        "agent_retry_counts": {},
        # Execution control flags
        "auto_trigger_a5": False,
        "headless_mode": False,
        # Cycle 3 fields
        "task_id": None,
        "run_id": None,
        "platform_filter": None,
        "preserved_fetch_results": None,
        # Baseline Analysis (Issue #4)
        "analysis_mode": None,
        "baseline_questions": None,
        "baseline_fetch_results": None,
        "baseline_metrics": None,
        "baseline_report": None,
    }

    async with AsyncSessionLocal() as db:
        # 1. Fetch entity info for brand_name / domain / industry
        if entity_id:
            try:
                entity_service = EntityService(db)
                entity_data = await entity_service.get_entity(entity_id)
                if entity_data:
                    state["brand_name"] = entity_data.get("name", "")
                    state["official_website"] = entity_data.get("domain", "")
                    state["industry_hint"] = entity_data.get("industry", "")
            except Exception as e:
                logger.warning(f"[Restore] Failed to load entity: {e}")

        # 2. Fetch all messages for this session
        message_service = MessageService(db)
        messages = await message_service.get_messages(
            session_id=UUID(session_id), limit=500
        )

        # 3. Recover the latest active task/run context if it still exists
        try:
            from app.services.task_service import TaskService

            task_service = TaskService(db)
            active_task = await task_service.get_session_active_task(UUID(session_id))
            if active_task:
                state["task_id"] = str(active_task.id)
                state["progress_message"] = (
                    active_task.progress_message or state["progress_message"]
                )
                loaded_runs = active_task.__dict__.get("task_runs") or []
                if loaded_runs:
                    latest_run = loaded_runs[0]
                    state["run_id"] = str(latest_run.id)
                    if latest_run.status.value == "waiting_input":
                        state["execution_status"] = "awaiting_user"
                        state["awaiting_user"] = True
        except Exception as e:
            logger.warning(f"[Restore] Failed to load active task context: {e}")

    highest_step = ""
    latest_attachment_turn: dict[str, Any] | None = None
    latest_import_artifact_sequence = 0

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "") or ""
        msg_type = msg.get("type", "text")
        sequence = int(msg.get("sequence") or 0)
        metadata = msg.get("metadata") if isinstance(msg.get("metadata"), dict) else {}

        # Rebuild orchestrator_history from user/agent text messages
        if role == "user":
            attachments = _normalize_attachment_refs(metadata.get("attachments", []))
            tool_mode = _normalize_tool_mode(metadata.get("tool_mode"))
            replayed_content = content
            if attachments:
                attachment_summary = _build_attachment_summary(attachments)
                replayed_content = (
                    f"{content}\n\n{attachment_summary}"
                    if content
                    else attachment_summary
                )
                latest_attachment_turn = {
                    "sequence": sequence,
                    "attachments": attachments,
                    "user_message": content,
                }
            state["selected_tool_mode"] = tool_mode
            state["latest_user_input"] = content
            state["orchestrator_history"].append(
                {"role": "user", "content": replayed_content}
            )
            state["messages"].append(HumanMessage(content=replayed_content))
        elif role == "agent" and msg_type == "text" and content:
            state["orchestrator_history"].append(
                {"role": "assistant", "content": content}
            )
            state["messages"].append(AIMessage(content=content))

        # Extract artifacts from OUTPUT messages
        if msg_type == "output":
            output_type = msg.get("output_type", "")
            output_data = msg.get("output_data")
            if not output_data:
                continue
            # output_data may be a dict (already parsed) or a JSON string
            if isinstance(output_data, str):
                try:
                    output_data = json.loads(output_data)
                except (json.JSONDecodeError, TypeError):
                    continue
            if not isinstance(output_data, dict):
                continue

            if output_type == "workflow":
                current_step = output_data.get("currentStep", "")
                # A1 workflow output
                bp = output_data.get("brandProfile") or output_data.get("brand_profile")
                if bp:
                    state["brand_profile"] = bp
                comps = output_data.get("competitors")
                if comps:
                    state["competitors"] = comps
                cl = output_data.get("competitive_landscape")
                if cl:
                    state["competitive_landscape"] = cl
                # A2 workflow output
                personas = output_data.get("personas") or output_data.get(
                    "user_personas"
                )
                mp = output_data.get("marketingPersonas") or output_data.get(
                    "marketing_personas"
                )
                if personas or mp:
                    state["marketing_personas"] = mp or {"user_personas": personas}
                if output_data.get("artifact_kind") == "brand_competitor_import":
                    latest_import_artifact_sequence = max(
                        latest_import_artifact_sequence, sequence
                    )
                # Track highest step
                if current_step and current_step > highest_step:
                    highest_step = current_step

            elif output_type == "pipeline":
                # A2 pipeline artifact — restore marketing_personas if present
                mp = output_data.get("marketing_personas")
                if mp:
                    state["marketing_personas"] = mp

            elif output_type == "questionList":
                sq = output_data.get("simulatedQuestions") or output_data.get(
                    "simulated_questions"
                )
                if sq:
                    state["simulated_questions"] = sq
                    if sq.get("generation_mode") == "uploaded_list":
                        latest_import_artifact_sequence = max(
                            latest_import_artifact_sequence, sequence
                        )
                q = output_data.get("questions")
                if q:
                    state["questions"] = q
                    if any(
                        isinstance(item, dict)
                        and item.get("source") == "uploaded_table"
                        for item in q
                    ):
                        latest_import_artifact_sequence = max(
                            latest_import_artifact_sequence, sequence
                        )
                # Baseline mode questions
                if state.get("analysis_mode") == "baseline":
                    state["baseline_questions"] = q or sq
                if "A3" > highest_step:
                    highest_step = "A3"

            elif output_type == "fetchResults":
                fr = output_data.get("fetchResults") or output_data.get("fetch_results")
                if fr:
                    state["fetch_results"] = fr
                if "A4" > highest_step:
                    highest_step = "A4"

            elif output_type == "report":
                state["metrics"] = output_data.get("metrics") or {
                    "bwvs_index": output_data.get("overallScore", 0),
                }
                state["report"] = {
                    "executive_summary": output_data.get("executive_summary", ""),
                    "key_findings": output_data.get("key_findings", []),
                    "strengths": output_data.get("strengths", []),
                    "weaknesses": output_data.get("weaknesses", []),
                    "opportunities": output_data.get("opportunities", []),
                    "threats": output_data.get("threats", []),
                    "recommendations": output_data.get("recommendations", []),
                    "action_plan": output_data.get("action_plan", {}),
                }
                if "A5" > highest_step:
                    highest_step = "A5"

            elif output_type == "report_baseline":
                state["analysis_mode"] = "baseline"
                state["baseline_metrics"] = output_data.get("metrics_raw") or {
                    "bwvs_index": output_data.get("overallScore", 0),
                }
                state["baseline_report"] = {
                    "executive_summary": output_data.get("executive_summary", ""),
                    "key_findings": output_data.get("key_findings", []),
                    "strengths": output_data.get("strengths", []),
                    "weaknesses": output_data.get("weaknesses", []),
                }
                if "A5" > highest_step:
                    highest_step = "A5"

            elif output_type == "dataTable":
                if output_data.get("artifact_kind") == "source_link_list":
                    rows = output_data.get("rows") or []
                    if isinstance(rows, list):
                        import_source_metadata = dict(
                            state.get("import_source_metadata") or {}
                        )
                        import_source_metadata["imported_link_list_count"] = len(rows)
                        import_source_metadata["imported_links"] = rows
                        state["import_source_metadata"] = import_source_metadata
                    latest_import_artifact_sequence = max(
                        latest_import_artifact_sequence, sequence
                    )
                    if not highest_step or highest_step < "A7":
                        highest_step = "A7"

    if (
        latest_attachment_turn
        and latest_import_artifact_sequence < latest_attachment_turn["sequence"]
        and not state.get("pending_table_intake")
        and not state.get("confirmed_import_action")
    ):
        attachments = latest_attachment_turn.get("attachments") or []
        if attachments:
            state["pending_table_intake"] = {
                "attachments": attachments,
                "user_message": latest_attachment_turn.get("user_message", ""),
            }
            import_source_metadata = dict(state.get("import_source_metadata") or {})
            import_source_metadata.setdefault("source_type", "uploaded_table")
            import_source_metadata["attachments"] = attachments
            state["import_source_metadata"] = import_source_metadata

    # Set progress based on highest completed step
    if highest_step:
        state["current_step"] = highest_step
        state["progress"] = _STEP_PROGRESS.get(highest_step, 0.0)
        state["progress_message"] = f"已完成 {highest_step} 阶段"

    # Backfill brand_name from brand_profile if entity lookup didn't provide it
    # This prevents LLM hallucination when brand_name is empty but brand_profile exists
    if not state["brand_name"] and state.get("brand_profile"):
        bp_name = state["brand_profile"].get("brand_name", "")
        if bp_name:
            state["brand_name"] = bp_name
            logger.info(
                f"[Restore] Backfilled brand_name from brand_profile: {bp_name}"
            )

    logger.info(
        f"[Restore] Rebuilt state for session {session_id}: "
        f"step={highest_step}, history_len={len(state['orchestrator_history'])}, "
        f"has_brand={state['brand_profile'] is not None}, "
        f"has_competitors={state['competitors'] is not None}, "
        f"brand_name={state['brand_name']!r}"
    )

    return state


async def handle_user_message_langgraph(
    websocket: WebSocket | None, session_id: str, data: dict
):
    """Handle user message using LangGraph workflow.

    For new conversations: initializes state and starts orchestrator.
    For continued conversations (after user confirmation): adds user message
    to orchestrator_history and restarts from orchestrator.
    """
    content = data.get("content", "")
    context = data.get("context", [])
    brand_name = data.get("brand_name", "")
    official_website = data.get("official_website", "")
    industry_hint = data.get("industry_hint", "")
    trigger_source = data.get("trigger_source", "websocket")
    persist_user_message = bool(data.get("persist_user_message", True))
    existing_message_id = data.get("message_id")
    client_message_id = data.get("clientMessageId") or data.get("client_message_id")
    attachments = _normalize_attachment_refs(data.get("attachments", []))
    tool_mode = _normalize_tool_mode(data.get("tool_mode"))

    # Build context-enhanced content for orchestrator
    enhanced_content = content
    if context:
        context_parts = []
        type_names = {
            "profile": "用户画像",
            "scenario": "使用场景",
            "intent": "互动意图",
        }
        for ctx in context:
            ctx_type = ctx.get("type", "")
            ctx_label = ctx.get("label", "")
            context_parts.append(f"[{type_names.get(ctx_type, ctx_type)}: {ctx_label}]")
        enhanced_content = (
            (enhanced_content + "\n\n" if enhanced_content else "")
            + "附加上下文: "
            + " ".join(context_parts)
        )
    if attachments:
        attachment_summary = _build_attachment_summary(attachments)
        if enhanced_content:
            enhanced_content = f"{enhanced_content}\n\n{attachment_summary}"
        else:
            enhanced_content = attachment_summary
    task_label = _resolve_task_label(
        brand_name=brand_name,
        content=content,
        attachments=attachments,
        tool_mode=tool_mode,
    )

    logger.info(
        f"[LangGraph] Processing message for session {session_id}: {content[:50]}..."
    )

    # Immediate acknowledgement — reduce perceived latency
    await session_event_publisher.emit_to_session(
        session_id,
        "thought_delta",
        {
            "content": "正在理解您的需求...",
            "is_delta": False,
            "is_complete": False,
        },
        bypass_runtime_guard=True,
    )

    # Save user message to database + lookup entity from session
    entity_id: str | None = None
    session_user_id: UUID | None = None
    async with AsyncSessionLocal() as db:
        if persist_user_message:
            message_service = MessageService(db)
            try:
                user_metadata: dict[str, Any] = {"tool_mode": tool_mode}
                if attachments:
                    user_metadata["attachments"] = attachments
                saved = await message_service.save_message(
                    session_id=UUID(session_id),
                    role="user",
                    content=content,
                    metadata=user_metadata or None,
                )
                existing_message_id = str(saved["id"])
            except Exception as e:
                logger.error(f"[LangGraph] Error saving user message: {e}")

        if existing_message_id:
            await session_event_publisher.emit_to_session(
                session_id,
                "user_message_ack",
                {
                    "message_id": existing_message_id,
                    "content": content,
                    "client_message_id": client_message_id,
                },
            )

        # Look up session's associated entity to auto-inject brand info
        try:
            result = await db.execute(
                select(Session).where(Session.id == UUID(session_id))
            )
            session_obj = result.scalar_one_or_none()
            if session_obj and session_obj.entity_id:
                session_user_id = session_obj.user_id
                entity_id = str(session_obj.entity_id)
                entity_service = EntityService(db)
                entity_data = await entity_service.get_entity(entity_id)
                if entity_data:
                    # Auto-inject brand info from entity (if not provided by client)
                    if not brand_name:
                        brand_name = entity_data.get("name", "")
                    if not official_website:
                        official_website = entity_data.get("domain", "")
                    if not industry_hint:
                        industry_hint = entity_data.get("industry", "")
                    logger.info(
                        f"[LangGraph] Auto-injected entity info: "
                        f"brand={brand_name}, domain={official_website}, "
                        f"industry={industry_hint}"
                    )
            elif session_obj:
                session_user_id = session_obj.user_id
        except Exception as e:
            logger.error(f"[LangGraph] Error looking up entity: {e}")

    # Reset layer accumulator for this execution round
    from app.workflow.events import reset_session_layers

    reset_session_layers(session_id)

    workflow = None
    config = None
    skip_final_save = False
    runtime_task_id: str | None = None
    runtime_run_id: str | None = None
    try:
        # Get compiled workflow
        workflow = await get_compiled_workflow()

        # Configure thread (using session_id as thread_id)
        config = {
            "configurable": {
                "thread_id": session_id,
            }
        }

        # Check if there's an existing state (continued conversation)
        # If this session was just recalled, bypass stale checkpointer state
        # and force rebuild from DB (which reflects the post-recall reality).
        existing_state = None
        from app.services.runtime_coordinator import runtime_coordinator

        if await runtime_coordinator.consume_recalled_session(session_id):
            logger.info(
                f"[LangGraph] Session {session_id} was recalled, bypassing checkpointer"
            )
        else:
            try:
                existing_state = workflow.get_state(config)
            except Exception:
                pass

        if existing_state and existing_state.values:
            # Continued conversation: add user message to orchestrator history
            state_values = dict(existing_state.values)
            if _has_reusable_runtime_context(state_values):
                logger.info(
                    "[LangGraph] EXISTING state path: has_sq=%s, has_q=%s, has_fr=%s, history_len=%d",
                    "yes" if state_values.get("simulated_questions") else "NO",
                    "yes" if state_values.get("questions") else "NO",
                    "yes" if state_values.get("fetch_results") else "NO",
                    len(state_values.get("orchestrator_history", [])),
                )
                await _ensure_manual_session_is_idle(
                    session_id=session_id,
                    allowed_waiting_task_id=state_values.get("task_id"),
                )
                resumed_run_id = None
                follow_up_task_id = state_values.get("task_id")
                follow_up_brand_name = (
                    brand_name or state_values.get("brand_name") or content
                )
                if _state_is_waiting_for_user(
                    state_values
                ) and await _is_waiting_task_resumable(state_values.get("task_id")):
                    resume_kwargs: dict[str, Any] = {}
                    if trigger_source != "websocket":
                        resume_kwargs["trigger_source"] = trigger_source
                    resumed_run_id = await _submit_resume_run(
                        state_values.get("task_id"),
                        **resume_kwargs,
                    )
                    if state_values.get("task_id") and resumed_run_id is None:
                        raise RuntimeError(
                            "Failed to submit resume runtime attempt for waiting task"
                        )
                else:
                    if session_user_id is None:
                        raise RuntimeError(
                            "Missing session user context for follow-up task"
                        )
                    submit_kwargs: dict[str, Any] = {
                        "user_id": session_user_id,
                        "session_id": session_id,
                        "brand_name": follow_up_brand_name,
                        "entity_id": entity_id or state_values.get("entity_id"),
                        "run_kind": "follow_up",
                    }
                    if trigger_source != "websocket":
                        submit_kwargs["trigger_source"] = trigger_source
                    follow_up_task_id, resumed_run_id = await _submit_manual_task(
                        **submit_kwargs
                    )
                runtime_task_id = follow_up_task_id
                runtime_run_id = resumed_run_id or state_values.get("run_id")
                await _bind_current_local_execution(
                    session_id=session_id,
                    task_id=runtime_task_id,
                    run_id=runtime_run_id,
                )
                history = list(state_values.get("orchestrator_history", []))
                history.append(
                    {
                        "role": "user",
                        "content": enhanced_content,
                    }
                )

                # Set A3 mode based on context profiles
                user_decisions = dict(state_values.get("user_decisions", {}))
                profile_contexts = [c for c in context if c.get("type") == "profile"]
                if profile_contexts:
                    user_decisions["a3_mode"] = "persona"
                    user_decisions["selected_persona_ids"] = [
                        c.get("label", "") for c in profile_contexts
                    ]

                # Restart from orchestrator with updated history
                update_state: dict[str, Any] = {
                    "orchestrator_history": history,
                    "user_decisions": user_decisions,
                    "user_id": (
                        str(session_user_id)
                        if session_user_id
                        else state_values.get("user_id")
                    ),
                    "messages": list(state_values.get("messages", []))
                    + [HumanMessage(content=enhanced_content)],
                    "task_id": follow_up_task_id,
                    "run_id": resumed_run_id or state_values.get("run_id"),
                    "selected_tool_mode": tool_mode,
                    "latest_user_input": content,
                }
                _reset_follow_up_runtime_state(update_state)
                if attachments:
                    update_state["pending_table_intake"] = {
                        "attachments": attachments,
                        "user_message": content,
                    }
                    update_state["table_intake_result"] = None
                    update_state["confirmed_import_action"] = None
                    update_state["import_source_metadata"] = {
                        "source_type": "uploaded_table",
                        "attachments": attachments,
                    }
                    if tool_mode:
                        update_state["import_source_metadata"][
                            "requested_tool_mode"
                        ] = tool_mode

                # Stream workflow execution from orchestrator
                async for event in workflow.astream(update_state, config=config):
                    await _process_langgraph_event(session_id, event)
                await _sync_runtime_after_stream(workflow, config)
                return
        else:
            # MemorySaver has no state — try restoring from DB
            try:
                restored = await rebuild_state_from_db(session_id, entity_id)
                logger.info(
                    "[LangGraph] REBUILD path: has_sq=%s, has_q=%s, has_fr=%s, history_len=%d",
                    "yes" if restored.get("simulated_questions") else "NO",
                    "yes" if restored.get("questions") else "NO",
                    "yes" if restored.get("fetch_results") else "NO",
                    len(restored.get("orchestrator_history", [])),
                )
                if _has_reusable_runtime_context(restored):
                    logger.info(
                        f"[LangGraph] Restored state from DB for session {session_id}"
                    )
                    await _ensure_manual_session_is_idle(
                        session_id=session_id,
                        allowed_waiting_task_id=restored.get("task_id"),
                    )
                    resumed_run_id = None
                    restored_task_id = restored.get("task_id")
                    restored_brand_name = (
                        brand_name or restored.get("brand_name") or content
                    )
                    if _state_is_waiting_for_user(
                        restored
                    ) and await _is_waiting_task_resumable(restored.get("task_id")):
                        resume_kwargs = {}
                        if trigger_source != "websocket":
                            resume_kwargs["trigger_source"] = trigger_source
                        resumed_run_id = await _submit_resume_run(
                            restored.get("task_id"),
                            **resume_kwargs,
                        )
                        if restored.get("task_id") and resumed_run_id is None:
                            raise RuntimeError(
                                "Failed to submit resume runtime attempt during DB restore"
                            )
                    else:
                        if session_user_id is None:
                            raise RuntimeError(
                                "Missing session user context for restored follow-up task"
                            )
                        submit_kwargs = {
                            "user_id": session_user_id,
                            "session_id": session_id,
                            "brand_name": restored_brand_name,
                            "entity_id": entity_id or restored.get("entity_id"),
                            "run_kind": "follow_up",
                        }
                        if trigger_source != "websocket":
                            submit_kwargs["trigger_source"] = trigger_source
                        restored_task_id, resumed_run_id = await _submit_manual_task(
                            **submit_kwargs
                        )
                    runtime_task_id = restored_task_id
                    runtime_run_id = resumed_run_id or restored.get("run_id")
                    await _bind_current_local_execution(
                        session_id=session_id,
                        task_id=runtime_task_id,
                        run_id=runtime_run_id,
                    )
                    restored["orchestrator_history"].append(
                        {"role": "user", "content": enhanced_content}
                    )
                    restored["messages"] = list(restored.get("messages", [])) + [
                        HumanMessage(content=enhanced_content)
                    ]
                    _reset_follow_up_runtime_state(restored)
                    restored["task_id"] = restored_task_id
                    restored["run_id"] = resumed_run_id or restored.get("run_id")
                    restored["selected_tool_mode"] = tool_mode
                    restored["latest_user_input"] = content
                    # Set A3 mode based on context profiles
                    profile_contexts = [
                        c for c in context if c.get("type") == "profile"
                    ]
                    if profile_contexts:
                        user_decisions = dict(restored.get("user_decisions", {}))
                        user_decisions["a3_mode"] = "persona"
                        user_decisions["selected_persona_ids"] = [
                            c.get("label", "") for c in profile_contexts
                        ]
                        restored["user_decisions"] = user_decisions
                    if attachments:
                        restored["pending_table_intake"] = {
                            "attachments": attachments,
                            "user_message": content,
                        }
                        restored["table_intake_result"] = None
                        restored["confirmed_import_action"] = None
                        restored["import_source_metadata"] = {
                            "source_type": "uploaded_table",
                            "attachments": attachments,
                        }
                        if tool_mode:
                            restored["import_source_metadata"][
                                "requested_tool_mode"
                            ] = tool_mode
                    async for event in workflow.astream(restored, config=config):
                        await _process_langgraph_event(session_id, event)
                    await _sync_runtime_after_stream(workflow, config)
                    return
            except Exception as e:
                logger.warning(f"[LangGraph] DB state restoration failed: {e}")

            # Cycle 3, Module 1: Create AnalysisTask before starting workflow
            created_task_id: str | None = None
            created_run_id: str | None = None
            try:
                await _ensure_manual_session_is_idle(session_id=session_id)
                if session_user_id is None:
                    raise RuntimeError("Missing session user context for initial task")
                submit_kwargs = {
                    "user_id": session_user_id,
                    "session_id": session_id,
                    "brand_name": task_label,
                    "entity_id": entity_id,
                    "run_kind": "initial",
                }
                if trigger_source != "websocket":
                    submit_kwargs["trigger_source"] = trigger_source
                created_task_id, created_run_id = await _submit_manual_task(
                    **submit_kwargs
                )
                runtime_task_id = created_task_id
                runtime_run_id = created_run_id
            except Exception as task_err:
                logger.error(
                    "[LangGraph] Failed to submit AnalysisTask: %s",
                    task_err,
                    exc_info=True,
                )
                error_payload = {
                    "step": "runtime",
                    "error": "任务初始化失败，分析未启动，请稍后重试。",
                    "recoverable": True,
                }
                await _emit_session_error(session_id, error_payload)
                return

            # New conversation: initialize full state
            initial_state: AgentState = {
                "session_id": session_id,
                "user_id": str(session_user_id) if session_user_id else None,
                "entity_id": entity_id,
                "messages": [HumanMessage(content=enhanced_content)],
                "brand_name": (
                    brand_name
                    or (content if tool_mode != "confidence_analysis" else "")
                ),
                "official_website": official_website,
                "industry_hint": industry_hint,
                # A1 outputs
                "brand_profile": None,
                "competitors": None,
                "competitive_landscape": None,
                # A2 outputs
                "marketing_personas": None,
                # A3 outputs
                "simulated_questions": None,
                "questions": None,
                # A4 outputs
                "fetch_results": None,
                # A5 outputs
                "metrics": None,
                "report": None,
                # Execution control
                "current_step": "",
                "execution_status": "running",
                "progress": 0.0,
                "progress_message": "开始分析...",
                # Human-in-loop (legacy, kept for compatibility)
                "pending_confirmation": None,
                "user_decisions": {},
                # Error handling
                "error_info": None,
                # Orchestrator state
                "orchestrator_history": [
                    {"role": "user", "content": enhanced_content},
                ],
                "orchestrator_reply": None,
                "next_action": None,
                "awaiting_user": False,
                "tool_call_args": None,
                "tool_call_id": None,
                "current_skill": None,
                "current_skill_family": None,
                "current_skill_package_key": None,
                "current_skill_package_name": None,
                "current_skill_package_path": None,
                "current_skill_package_context": None,
                "current_skill_prompt_overlay": None,
                "last_skill_result": None,
                "skill_history": [],
                "pending_table_intake": (
                    {
                        "attachments": attachments,
                        "user_message": content,
                    }
                    if attachments
                    else None
                ),
                "table_intake_result": None,
                "confirmed_import_action": None,
                "import_source_metadata": (
                    {
                        "source_type": "uploaded_table",
                        "attachments": attachments,
                    }
                    if attachments
                    else None
                ),
                "selected_tool_mode": tool_mode,
                "latest_user_input": content,
                # Cycle 3: Task persistence + multi-turn
                "task_id": created_task_id,
                "run_id": created_run_id,
                "platform_filter": None,
                "preserved_fetch_results": None,
                # Baseline Analysis (Issue #4)
                "analysis_mode": None,
                "baseline_questions": None,
                "baseline_fetch_results": None,
                "baseline_metrics": None,
                "baseline_report": None,
                # Execution control flags
                "auto_trigger_a5": False,
                "headless_mode": False,
                "agent_retry_counts": {},
            }

            # Stream workflow execution
            await _bind_current_local_execution(
                session_id=session_id,
                task_id=runtime_task_id,
                run_id=runtime_run_id,
            )
            async for event in workflow.astream(initial_state, config=config):
                await _process_langgraph_event(session_id, event)
            await _sync_runtime_after_stream(workflow, config)

    except asyncio.CancelledError:
        logger.info(f"[LangGraph] Workflow cancelled for session {session_id}")
        await _finalize_cancelled_runtime_if_requested(
            task_id=runtime_task_id,
            run_id=runtime_run_id,
        )
        skip_final_save = True
        raise  # Let finally block and _on_agent_done handle cleanup

    except Exception as e:
        import traceback

        error_msg = str(e) or repr(e) or "未知错误"
        error_type = type(e).__name__
        logger.error(
            f"[LangGraph] Error processing message: [{error_type}] {error_msg}"
        )
        traceback.print_exc()

        error_payload = {
            "step": "workflow",
            "error": f"处理消息时出错: {error_msg}",
            "recoverable": True,
        }
        await _emit_session_error(session_id, error_payload)
    finally:
        # Always save final agent message, even if astream raised an exception
        if workflow and config and not skip_final_save:
            try:
                await _save_final_message(session_id, workflow, config)
            except Exception as save_err:
                logger.error(f"[LangGraph] Error saving final message: {save_err}")


async def _process_langgraph_event(session_id: str, event: dict):
    """Process a LangGraph event.

    With the new orchestrator architecture, most events are sent directly
    via the events module (send_reply_event, send_action_log_event, etc.)
    from within the nodes themselves. This handler only processes
    high-level LangGraph lifecycle events.
    """
    # LangGraph astream returns node output dicts like {"orchestrator": {...}}
    # We mainly log these for debugging; actual WebSocket events are sent
    # from within the nodes via the events module.
    for node_name, node_output in event.items():
        logger.debug(f"[LangGraph] Node '{node_name}' completed")

        # Check if workflow reached an error state
        if isinstance(node_output, dict):
            error_info = node_output.get("error_info")
            if error_info:
                logger.warning(
                    f"[LangGraph] Error in {error_info.get('step', '?')}: "
                    f"{error_info.get('error', 'unknown')}"
                )


async def _save_final_message(session_id: str, workflow, config: dict):
    """Save final agent message to database, including accumulated layers."""
    from app.workflow.events import pop_accumulated_layers

    # Always pop layers to prevent memory leak, regardless of final_state
    layers = pop_accumulated_layers(session_id)

    try:
        # Get final state
        final_state = workflow.get_state(config)

        if final_state and final_state.values:
            state_values = final_state.values

            # Build content from orchestrator reply or report summary
            orchestrator_reply = state_values.get("orchestrator_reply", "")
            report = state_values.get("report") or {}
            metrics = state_values.get("metrics") or {}
            layered_reply = ""
            if isinstance(layers, dict):
                layered_reply = str(layers.get("replyText", "") or "").strip()

            if layered_reply:
                content = layered_reply
            elif orchestrator_reply:
                content = orchestrator_reply
            elif report:
                content = report.get("executive_summary", "分析完成")
            else:
                content = "分析完成"

            logger.info(
                f"[LangGraph] Saving agent message ({len(content)} chars) for session {session_id}"
            )

            async with AsyncSessionLocal() as db:
                message_service = MessageService(db)
                await message_service.save_message(
                    session_id=UUID(session_id),
                    role="agent",
                    content=content,
                    metadata={
                        "metrics": metrics,
                        "report_summary": report.get("key_findings", []),
                        "layers": layers,
                    },
                )
            logger.info(f"[LangGraph] Agent message saved for session {session_id}")
        else:
            logger.warning(
                f"[LangGraph] No final state to save for session {session_id}"
            )
    except Exception as e:
        logger.error(f"[LangGraph] Error saving final message: {e}")


async def handle_confirmation_langgraph(
    websocket: WebSocket, session_id: str, data: dict
):
    """Handle user confirmation/selection for LangGraph workflow.

    With the orchestrator architecture, confirmations are handled by adding
    the user's selection to orchestrator_history and restarting the workflow.
    """
    selection = data.get("selection", "")
    option_id = data.get("option_id", "")
    message = data.get("message", "")
    request_id = data.get("request_id", "")

    # Build a user message from the confirmation
    # selection can be a string (inline button label) or dict (structured selection)
    if isinstance(selection, dict):
        # Extract readable text from structured selection
        user_content = (
            message
            or selection.get("label", "")
            or selection.get("optionId", "")
            or option_id
            or "确认继续"
        )
    else:
        user_content = message or selection or option_id or "确认继续"

    logger.info(
        f"[LangGraph] Received confirmation for session {session_id}: "
        f"user_content={user_content!r}, selection={selection!r}"
    )

    workflow = None
    config = None
    skip_final_save = False
    runtime_task_id: str | None = None
    runtime_run_id: str | None = None
    try:
        workflow = await get_compiled_workflow()
        config = {
            "configurable": {
                "thread_id": session_id,
            }
        }

        # Get current state
        current_state = workflow.get_state(config)
        if not current_state or not current_state.values:
            await _emit_session_error(session_id, {"message": "无法获取当前工作流状态"})
            return

        state_values = dict(current_state.values)
        if not await _is_waiting_task_resumable(state_values.get("task_id")):
            await _emit_session_error(
                session_id,
                {
                    "message": "当前确认已失效，请重新发起分析。",
                    "recoverable": True,
                },
            )
            return

        request_allowed, used_legacy_request_fallback = (
            _validate_confirmation_request_id(
                state_values=state_values,
                request_id=request_id if isinstance(request_id, str) else "",
                selection=selection if isinstance(selection, (str, dict)) else None,
                option_id=option_id if isinstance(option_id, str) else "",
            )
        )
        if not request_allowed:
            await _emit_session_error(
                session_id,
                {
                    "message": "当前确认已失效，请重新发起分析。",
                    "recoverable": True,
                },
            )
            return
        if used_legacy_request_fallback:
            logger.info(
                "[LangGraph] Accepting legacy persona confirmation without request_id for session %s",
                session_id,
            )

        resumed_run_id = await _submit_resume_run(state_values.get("task_id"))
        if state_values.get("task_id") and resumed_run_id is None:
            raise RuntimeError(
                "Failed to submit resume runtime attempt for confirmation flow"
            )
        runtime_task_id = state_values.get("task_id")
        runtime_run_id = resumed_run_id or state_values.get("run_id")
        await _bind_current_local_execution(
            session_id=session_id,
            task_id=runtime_task_id,
            run_id=runtime_run_id,
        )
        history = list(state_values.get("orchestrator_history", []))
        user_decisions = dict(state_values.get("user_decisions", {}))

        resolution = resolve_confirmation_selection(
            selection=selection if isinstance(selection, (str, dict)) else None,
            option_id=option_id if isinstance(option_id, str) else "",
            user_content=user_content,
            user_decisions=user_decisions,
            state_values=state_values,
        )
        user_content = resolution.user_content
        user_decisions = resolution.user_decisions

        # Persist the normalized confirmation as a chat message so it survives refresh
        async with AsyncSessionLocal() as db:
            message_service = MessageService(db)
            try:
                confirmation_metadata = {
                    "tool_mode": state_values.get("selected_tool_mode"),
                }
                saved = await message_service.save_message(
                    session_id=UUID(session_id),
                    role="user",
                    content=user_content,
                    metadata=confirmation_metadata,
                )
                await session_event_publisher.emit_to_session(
                    session_id,
                    "user_message_ack",
                    {"message_id": str(saved["id"]), "content": user_content},
                )
            except Exception as e:
                logger.error(f"[LangGraph] Error saving confirmation message: {e}")

        history.append(
            {
                "role": "user",
                "content": user_content,
            }
        )

        # Restart workflow from orchestrator
        update_state: dict[str, Any] = {
            "orchestrator_history": history,
            "user_decisions": user_decisions,
            "awaiting_user": False,
            "pending_confirmation": None,
            "execution_status": "running",
            "user_id": state_values.get("user_id"),
            "run_id": resumed_run_id or state_values.get("run_id"),
            "selected_tool_mode": state_values.get("selected_tool_mode"),
            "latest_user_input": user_content,
        }
        if state_values.get("fetch_mode"):
            update_state["fetch_mode"] = state_values["fetch_mode"]
        update_state.update(resolution.state_updates)

        async for event in workflow.astream(update_state, config=config):
            await _process_langgraph_event(session_id, event)
        await _sync_runtime_after_stream(workflow, config)

    except asyncio.CancelledError:
        logger.info(
            f"[LangGraph] Confirmation workflow cancelled for session {session_id}"
        )
        await _finalize_cancelled_runtime_if_requested(
            task_id=runtime_task_id,
            run_id=runtime_run_id,
        )
        skip_final_save = True
        raise
    except Exception as e:
        import traceback

        error_msg = str(e) or repr(e) or "未知错误"
        error_type = type(e).__name__
        logger.error(
            f"[LangGraph] Error handling confirmation: [{error_type}] {error_msg}"
        )
        traceback.print_exc()

        # Use consistent error format matching events.py send_error_event
        await _emit_session_error(
            session_id,
            {
                "step": "confirmation",
                "error": f"处理确认时出错: {error_msg}",
                "recoverable": True,
            },
        )
    finally:
        # Always save final agent message after confirmation workflow
        if workflow and config and not skip_final_save:
            try:
                await _save_final_message(session_id, workflow, config)
            except Exception as save_err:
                logger.error(
                    f"[LangGraph] Error saving final message after confirmation: {save_err}"
                )


async def handle_recall_langgraph(
    websocket: WebSocket, session_id: str, data: dict
) -> None:
    """Handle recall: delete target message and everything after it.

    Pure DB deletion — no automatic re-execution. The user will edit
    the message content in the input box and manually re-send, which
    goes through the normal handle_user_message path.
    """
    message_id = data.get("message_id")
    if not message_id:
        await _emit_session_error(session_id, {"message": "缺少 message_id"})
        return

    # 1. Delete target message and everything after in DB
    async with AsyncSessionLocal() as db:
        svc = MessageService(db)
        result = await svc.rollback_from(UUID(session_id), UUID(message_id))

    if result.get("status") == "not_found":
        await _emit_session_error(
            session_id,
            {
                "message": "回退失败：消息不存在或无权限",
                "recoverable": True,
            },
        )
        return

    deleted = result.get("deleted_count", 0)
    logger.info(f"[Recall] Deleted {deleted} messages from session {session_id}")

    # 2. Mark session so next handle_user_message bypasses stale checkpointer
    from app.services.runtime_coordinator import runtime_coordinator

    await runtime_coordinator.mark_session_recalled(session_id)

    # 3. Notify frontend
    await session_event_publisher.emit_to_session(
        session_id,
        "recall_complete",
        {"message_id": message_id, "deleted_count": deleted},
    )


async def handle_stop_langgraph(websocket: WebSocket, session_id: str) -> None:
    """Request cancellation for the active task and stop the local executor."""

    from app.services.runtime_coordinator import runtime_coordinator
    from app.services.task_service import TaskService

    cancelled_task = None
    async with AsyncSessionLocal() as db:
        task_service = TaskService(db)
        active_task = await task_service.get_session_active_task(UUID(session_id))
        if active_task is not None:
            loaded_runs = active_task.__dict__.get("task_runs") or []
            latest_run = loaded_runs[0] if loaded_runs else None
            cancelled_task = await task_service.cancel_task(
                active_task.id,
                run_id=latest_run.id if latest_run is not None else None,
            )

    await runtime_coordinator.cancel_session_execution(session_id)
    await clear_session_browser_action_requests(
        session_id,
        unresolved_status=TaskRunChildAttemptStatus.CANCELLED,
        error_message="任务已取消",
    )

    await session_event_publisher.emit_to_session(
        session_id,
        "execution_stopped",
        {
            "task_id": str(cancelled_task.id) if cancelled_task else None,
            "status": "cancelled" if cancelled_task else "idle",
            "completed_stages": [],
            "pending_stages": [],
        },
    )


# Export for use in main websocket server
__all__ = [
    "handle_user_message_langgraph",
    "handle_confirmation_langgraph",
    "handle_stop_langgraph",
    "handle_browser_action_resolution_langgraph",
    "handle_artifact_action_langgraph",
    "handle_recall_langgraph",
]


async def _load_output_by_artifact_id(
    session_id: str,
    artifact_id: str,
) -> tuple[Message | None, dict[str, Any] | None]:
    """Load the latest OUTPUT message by persisted artifact id metadata."""
    async with AsyncSessionLocal() as db:
        query = (
            select(Message)
            .where(
                Message.session_id == UUID(session_id),
                Message.type == MessageType.OUTPUT,
            )
            .order_by(Message.sequence.desc())
        )
        result = await db.execute(query)
        messages = result.scalars().all()

    for message in messages:
        metadata = None
        if message.extra_metadata:
            try:
                metadata = json.loads(message.extra_metadata)
            except Exception:
                metadata = None
        if not isinstance(metadata, dict) or metadata.get("output_id") != artifact_id:
            continue

        output_data = None
        if message.output_data:
            try:
                output_data = json.loads(message.output_data)
            except Exception:
                output_data = None

        if isinstance(output_data, dict):
            return message, output_data
    return None, None


async def handle_artifact_action_langgraph(
    websocket: WebSocket, session_id: str, data: dict
) -> None:
    """Handle artifact-scoped actions without polluting the chat transcript."""
    artifact_id = data.get("artifact_id", "")
    action = data.get("action", "")
    payload = data.get("payload", {}) or {}
    raw_input = payload.get("raw_input", "") if isinstance(payload, dict) else ""

    from app.workflow.events import save_and_send_artifact, send_artifact_patch

    if not artifact_id:
        await _emit_session_error(
            session_id,
            {"message": "缺少 artifact_id", "recoverable": True},
        )
        return

    if action != "extra_evaluate":
        await _emit_session_error(
            session_id,
            {"message": "不支持的交付物动作", "recoverable": True},
        )
        return

    message, existing_report = await _load_output_by_artifact_id(
        session_id, artifact_id
    )
    if not existing_report:
        await _emit_session_error(
            session_id,
            {"message": "未找到对应的置信度报告交付物", "recoverable": True},
        )
        return

    if existing_report.get("report_kind") not in {
        "confidence_signal",
        "confidence_analysis",
    }:
        await _emit_session_error(
            session_id,
            {"message": "当前交付物不支持额外评估", "recoverable": True},
        )
        return

    await send_artifact_patch(
        session_id=session_id,
        artifact_id=artifact_id,
        patch={
            "status": {
                "phase": "running",
                "message": "正在生成额外评估…",
            }
        },
        status="running",
        message="正在生成额外评估…",
    )

    try:
        updated_report = await append_confidence_analysis_manual_items_async(
            existing_report, raw_input=raw_input
        )
    except ValueError as exc:
        await send_artifact_patch(
            session_id=session_id,
            artifact_id=artifact_id,
            patch={
                "status": {
                    "phase": "error",
                    "message": str(exc),
                }
            },
            status="error",
            message=str(exc),
        )
        return

    await save_and_send_artifact(
        session_id=session_id,
        output_type="report",
        title=message.content if message else "置信度报告",
        data=updated_report,
        artifact_key=artifact_id,
    )


async def handle_browser_action_resolution_langgraph(
    websocket: WebSocket, session_id: str, data: dict
) -> None:
    """Resolve a pending browser user-action handoff request."""
    request_id = data.get("request_id", "")
    resolution = data.get("resolution", "")

    if not request_id or resolution not in {"completed", "skip"}:
        await _emit_session_error(
            session_id,
            {"message": "浏览器操作确认参数无效", "recoverable": True},
        )
        return

    request = await get_browser_action_request(request_id)
    if request is None or request.session_id != session_id:
        logger.warning(
            "[LangGraph] Browser action request missing from runtime registry, trying DB fallback: request_id=%s session_id=%s request_session=%s",
            request_id,
            session_id,
            request.session_id if request is not None else None,
        )
        async with AsyncSessionLocal() as db:
            service = TaskRunChildAttemptService(db)
            fallback_attempt = (
                await service.get_waiting_input_for_session_by_request_id(
                    session_id=UUID(session_id),
                    request_id=request_id,
                )
            )
            if fallback_attempt is None:
                await _emit_session_error(
                    session_id,
                    {"message": "未找到对应的浏览器操作请求", "recoverable": True},
                )
                return
            await service.resolve_by_request_id(request_id, resolution=resolution)
            await session_event_publisher.emit_to_session(
                session_id,
                "browser_user_action_ack",
                {
                    "request_id": request_id,
                    "platform": fallback_attempt.platform,
                    "action_type": fallback_attempt.action_type,
                    "resolution": resolution,
                    "stale_runtime": True,
                },
            )
            return

    await resolve_browser_action_request(request_id, resolution)
    await session_event_publisher.emit_to_session(
        session_id,
        "browser_user_action_ack",
        {
            "request_id": request_id,
            "platform": request.platform,
            "action_type": request.action_type,
            "resolution": resolution,
        },
    )
