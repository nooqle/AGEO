import pytest
from langgraph.graph import END

from app.workflow import orchestrator_node as orchestrator_module
from app.workflow.orchestrator_node import _is_completed_analysis_report_state


def test_completed_analysis_report_state_is_terminal() -> None:
    assert _is_completed_analysis_report_state(
        {
            "current_step": "A5",
            "current_skill": "analysis_report_skill",
            "next_action": "a5_analytics",
            "execution_status": "completed",
            "progress": 1.0,
            "report": {"report_kind": "panorama"},
            "metrics": {"mention_rate": 0.67},
        }
    )


def test_completed_analysis_report_state_does_not_override_user_wait() -> None:
    assert not _is_completed_analysis_report_state(
        {
            "current_step": "A5",
            "current_skill": "analysis_report_skill",
            "execution_status": "completed",
            "awaiting_user": True,
            "pending_confirmation": {"step_id": "next_step"},
            "report": {"report_kind": "panorama"},
        }
    )


def test_completed_non_report_state_is_not_final_report_terminal() -> None:
    assert not _is_completed_analysis_report_state(
        {
            "current_step": "A7",
            "current_skill": "site_confidence_assessment_skill",
            "execution_status": "completed",
            "report": {"report_kind": "panorama"},
        }
    )


@pytest.mark.asyncio
async def test_orchestrator_ends_completed_report_without_llm(monkeypatch) -> None:
    monkeypatch.setattr(
        orchestrator_module,
        "_build_workflow_steps",
        lambda state: [{"status": "completed"}],
    )
    monkeypatch.setattr(
        orchestrator_module,
        "send_action_log_event",
        _async_noop,
    )
    monkeypatch.setattr(orchestrator_module, "send_plan_event", _async_noop)
    monkeypatch.setattr("app.workflow.events.send_progress_event", _async_noop)
    monkeypatch.setattr("app.workflow.events.send_execution_complete", _async_noop)

    def _fail_if_llm_is_called():
        raise AssertionError("completed report should not call orchestrator LLM")

    monkeypatch.setattr(
        orchestrator_module,
        "get_orchestrator_llm_model",
        _fail_if_llm_is_called,
    )

    command = await orchestrator_module.orchestrator_node(
        {
            "session_id": "session-final-report",
            "next_action": "a5_analytics",
            "current_step": "A5",
            "current_skill": "analysis_report_skill",
            "execution_status": "completed",
            "progress": 1.0,
            "report": {"report_kind": "panorama"},
            "metrics": {"mention_rate": 0.67},
            "fetch_results": [{"question_id": "q1", "platform_results": []}],
        }
    )

    assert command.goto == END
    assert command.update["execution_status"] == "completed"
    assert command.update["progress"] == 1.0
    assert command.update["next_required_action"] is None


async def _async_noop(*args, **kwargs) -> None:
    return None
