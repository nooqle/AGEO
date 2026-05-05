from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.task import TaskStatus
from app.services.task_service import _coerce_task_stage_code
from app.workflow.runtime_state_writer import (
    TaskRuntimeStateWriter,
    WorkflowTransition,
    build_transition_from_state,
)


class _FakeTaskService:
    def __init__(self, status: TaskStatus = TaskStatus.RUNNING) -> None:
        self.task = SimpleNamespace(status=status)
        self.calls: list[tuple[str, dict]] = []

    async def get_task(self, task_id):
        return self.task

    async def update_progress(self, task_id, **kwargs):
        self.calls.append(("update_progress", kwargs))

    async def mark_waiting_for_input(self, task_id, **kwargs):
        self.calls.append(("mark_waiting_for_input", kwargs))

    async def complete_task(self, task_id, **kwargs):
        self.calls.append(("complete_task", kwargs))

    async def fail_task(self, task_id, **kwargs):
        self.calls.append(("fail_task", kwargs))

    async def cancel_task(self, task_id, **kwargs):
        self.calls.append(("cancel_task", kwargs))


@pytest.mark.asyncio
async def test_writer_refuses_terminal_downgrade_to_running() -> None:
    service = _FakeTaskService(TaskStatus.COMPLETED)
    writer = TaskRuntimeStateWriter(service)  # type: ignore[arg-type]

    await writer.apply_transition(
        WorkflowTransition(
            task_id=uuid4(),
            status="running",
            stage="A4",
            progress=0.6,
            message="A4 running",
        )
    )

    assert service.calls == []


@pytest.mark.asyncio
async def test_writer_marks_waiting_input_with_progress() -> None:
    service = _FakeTaskService()
    writer = TaskRuntimeStateWriter(service)  # type: ignore[arg-type]
    run_id = uuid4()

    await writer.apply_transition(
        WorkflowTransition(
            task_id=uuid4(),
            run_id=run_id,
            status="waiting_input",
            stage="A4",
            progress=1.0,
            message="等待用户确认下一步",
        )
    )

    assert service.calls == [
        (
            "mark_waiting_for_input",
            {
                "run_id": run_id,
                "checkpoint_stage": "A4",
                "progress": 1.0,
                "progress_message": "等待用户确认下一步",
            },
        )
    ]


@pytest.mark.asyncio
async def test_writer_completes_with_authoritative_stage_and_message() -> None:
    service = _FakeTaskService()
    writer = TaskRuntimeStateWriter(service)  # type: ignore[arg-type]
    run_id = uuid4()

    await writer.apply_transition(
        WorkflowTransition(
            task_id=uuid4(),
            run_id=run_id,
            status="completed",
            stage="A7",
            progress=1.0,
            message="官网 AI 友好度已完成",
        )
    )

    assert service.calls == [
        (
            "complete_task",
            {
                "snapshot_id": None,
                "run_id": run_id,
                "final_stage": "A7",
                "progress_message": "官网 AI 友好度已完成",
            },
        )
    ]


def test_build_transition_from_state_promotes_a4_artifact_waiting_progress() -> None:
    task_id = uuid4()
    run_id = uuid4()

    transition = build_transition_from_state(
        {
            "task_id": str(task_id),
            "run_id": str(run_id),
            "current_step": "A4",
            "progress": 0.6,
            "awaiting_user": True,
            "a4_completion_observation": {"artifact_write_validated": True},
        }
    )

    assert transition is not None
    assert transition.status == "waiting_input"
    assert transition.task_id == task_id
    assert transition.run_id == run_id
    assert transition.progress == 1.0


def test_build_transition_from_state_ignores_stale_a3_confirmation_after_a4() -> None:
    transition = build_transition_from_state(
        {
            "task_id": str(uuid4()),
            "run_id": str(uuid4()),
            "current_step": "A4",
            "execution_status": "running",
            "progress": 0.6,
            "progress_message": "答案抓取完成，正在准备生成分析报告。",
            "awaiting_user": True,
            "pending_confirmation": {"type": "question_set_confirmation"},
            "a4_completion_observation": {
                "artifact_write_validated": True,
                "requires_user_decision": False,
            },
            "a4_canonical_result": {"fetch_results": []},
            "fetch_results": [{"question_id": "q1", "platform_results": []}],
        }
    )

    assert transition is not None
    assert transition.status == "running"
    assert transition.progress == 0.6


def test_build_transition_from_state_keeps_real_a4_user_decision_wait() -> None:
    transition = build_transition_from_state(
        {
            "task_id": str(uuid4()),
            "run_id": str(uuid4()),
            "current_step": "A4",
            "execution_status": "running",
            "progress": 0.6,
            "awaiting_user": True,
            "pending_confirmation": {"type": "step_confirmation"},
            "a4_completion_observation": {
                "artifact_write_validated": True,
                "requires_user_decision": True,
            },
            "fetch_results": [{"question_id": "q1", "platform_results": []}],
        }
    )

    assert transition is not None
    assert transition.status == "waiting_input"
    assert transition.progress == 1.0


def test_build_transition_from_state_uses_a7_completion_message() -> None:
    transition = build_transition_from_state(
        {
            "task_id": str(uuid4()),
            "run_id": str(uuid4()),
            "current_step": "A7",
            "current_skill": "site_confidence_assessment_skill",
            "execution_status": "completed",
            "progress": 1.0,
            "progress_message": "开始分析...",
        }
    )

    assert transition is not None
    assert transition.status == "completed"
    assert transition.stage == "A7"
    assert transition.message == "官网 AI 友好度已完成"


def test_build_transition_from_state_completes_a5_report_with_clean_message() -> None:
    transition = build_transition_from_state(
        {
            "task_id": str(uuid4()),
            "run_id": str(uuid4()),
            "current_step": "A5",
            "current_skill": "analysis_report_skill",
            "execution_status": "completed",
            "progress": 1.0,
            "progress_message": "等待开始...",
            "report": {"report_kind": "panorama"},
        }
    )

    assert transition is not None
    assert transition.status == "completed"
    assert transition.stage == "A5"
    assert transition.progress == 1.0
    assert transition.message == "分析完成"


def test_task_stage_code_coerces_orchestrator_to_db_safe_code() -> None:
    assert _coerce_task_stage_code("orchestrator") == "A0"
    assert _coerce_task_stage_code("analysis_report_skill") == "A5"
    assert len(_coerce_task_stage_code("unexpected_long_runtime_stage")) <= 10
