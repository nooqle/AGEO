"""Authoritative workflow transition writer.

Nodes and skills return facts. The orchestrator/runtime layer converts those
facts into workflow transitions and this module persists the official task
state through TaskService.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Literal
from uuid import UUID

from app.models.task import TaskStatus
from app.services.task_service import TaskService

logger = logging.getLogger(__name__)

WorkflowTransitionStatus = Literal[
    "running",
    "waiting_input",
    "failed",
    "completed",
    "cancelled",
]

_TERMINAL_TASK_STATUSES = {
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
}
_STALE_COMPLETION_MESSAGES = {
    "",
    "开始分析...",
    "等待开始...",
}


@dataclass(frozen=True)
class WorkflowTransition:
    task_id: UUID
    status: WorkflowTransitionStatus
    stage: str
    message: str
    source: str = "orchestrator"
    reason: str | None = None
    run_id: UUID | None = None
    progress: float | None = None
    snapshot_id: UUID | None = None
    error_message: str | None = None


def _coerce_uuid(value: Any) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _coerce_progress(value: Any, *, default: float | None = None) -> float | None:
    try:
        progress = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, progress))


def state_requires_user_input(state: dict[str, Any]) -> bool:
    return bool(
        state.get("awaiting_user")
        or state.get("pending_confirmation")
        or state.get("next_required_action")
        and str((state.get("execution_status") or "")).lower() == "awaiting_user"
    )


def build_transition_from_state(
    state: dict[str, Any],
    *,
    reason: str = "stream_reconcile",
) -> WorkflowTransition | None:
    task_id = _coerce_uuid(state.get("task_id"))
    if task_id is None:
        return None

    run_id = _coerce_uuid(state.get("run_id"))
    stage = str(state.get("current_step") or "orchestrator")
    execution_status = str(state.get("execution_status") or "").lower()
    error_info = state.get("error_info") if isinstance(state.get("error_info"), dict) else {}
    message = str(state.get("progress_message") or "").strip()
    progress = _coerce_progress(state.get("progress"))

    if state_requires_user_input(state):
        observation = state.get("a4_completion_observation")
        if isinstance(observation, dict) and observation.get("artifact_write_validated"):
            progress = max(progress or 0.0, 1.0)
        return WorkflowTransition(
            task_id=task_id,
            run_id=run_id,
            status="waiting_input",
            stage=stage,
            progress=progress,
            message=message or "等待用户确认下一步",
            reason=reason,
        )

    if execution_status == "completed":
        snapshot_id = _coerce_uuid(state.get("snapshot_id"))
        effective_message = "" if message in _STALE_COMPLETION_MESSAGES else message
        completion_message = effective_message or (
            "官网 AI 友好度已完成"
            if stage == "A7"
            or str(state.get("current_skill") or "")
            in {
                "site_confidence_assessment_skill",
                "site_confidence_assessment_executor",
            }
            else "分析完成"
        )
        return WorkflowTransition(
            task_id=task_id,
            run_id=run_id,
            status="completed",
            stage=stage,
            progress=1.0,
            message=completion_message,
            reason=reason,
            snapshot_id=snapshot_id,
        )

    if execution_status in {"error", "failed"} or error_info:
        error_message = str(error_info.get("error") or message or "Workflow failed")
        return WorkflowTransition(
            task_id=task_id,
            run_id=run_id,
            status="failed",
            stage=str(error_info.get("step") or stage),
            progress=progress,
            message=error_message,
            reason=reason,
            error_message=error_message,
        )

    if execution_status == "running" and progress is not None:
        return WorkflowTransition(
            task_id=task_id,
            run_id=run_id,
            status="running",
            stage=stage,
            progress=progress,
            message=message or f"{stage} 执行中",
            reason=reason,
        )

    return None


class TaskRuntimeStateWriter:
    """Persist orchestrator-owned workflow transitions."""

    def __init__(self, task_service: TaskService) -> None:
        self._task_service = task_service

    async def apply_transition(self, transition: WorkflowTransition) -> None:
        task = await self._task_service.get_task(transition.task_id)
        if task is None:
            logger.info(
                "[RuntimeStateWriter] Task %s missing; transition skipped",
                transition.task_id,
            )
            return

        if task.status in _TERMINAL_TASK_STATUSES and transition.status not in {
            "cancelled",
        }:
            logger.info(
                "[RuntimeStateWriter] Refusing %s -> %s downgrade for task %s",
                task.status.value,
                transition.status,
                transition.task_id,
            )
            return

        logger.info(
            "[RuntimeStateWriter] Applying transition task=%s run=%s status=%s "
            "stage=%s progress=%s source=%s reason=%s",
            transition.task_id,
            transition.run_id,
            transition.status,
            transition.stage,
            transition.progress,
            transition.source,
            transition.reason,
        )

        if transition.status == "running":
            await self._task_service.update_progress(
                transition.task_id,
                stage=transition.stage,
                progress=transition.progress or 0.0,
                message=transition.message,
            )
            return

        if transition.status == "waiting_input":
            await self._task_service.mark_waiting_for_input(
                transition.task_id,
                run_id=transition.run_id,
                checkpoint_stage=transition.stage,
                progress=transition.progress,
                progress_message=transition.message,
            )
            return

        if transition.status == "completed":
            await self._task_service.complete_task(
                transition.task_id,
                snapshot_id=transition.snapshot_id,
                run_id=transition.run_id,
                final_stage=transition.stage,
                progress_message=transition.message,
            )
            return

        if transition.status == "failed":
            await self._task_service.fail_task(
                transition.task_id,
                error_message=transition.error_message or transition.message,
                error_stage=transition.stage,
                run_id=transition.run_id,
            )
            return

        if transition.status == "cancelled":
            await self._task_service.cancel_task(
                transition.task_id,
                run_id=transition.run_id,
            )
