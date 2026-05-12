import pytest
from app.core.llm import LLMResponse, ToolCallBlock
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
async def test_orchestrator_delegates_completed_report_guidance_to_llm(
    monkeypatch,
) -> None:
    class FakeOrchestratorModel:
        def __init__(self) -> None:
            self.called = False

        def stream(self, **kwargs):
            self.called = True
            yield LLMResponse(content="报告已生成，我会根据当前结果给出下一步选择。")
            yield LLMResponse(
                tool_calls=[
                    ToolCallBlock(
                        name="ask_user",
                        id="ask_report_next_step",
                        arguments={
                            "message": "报告已生成。基于当前报告，建议先确认下一步分析重点：",
                            "options": [
                                {
                                    "id": "source_gap_review",
                                    "label": "核查来源缺口",
                                    "description": "优先检查报告中引用来源不足的问题",
                                },
                                {
                                    "id": "competitor_compare",
                                    "label": "对比主要竞品",
                                    "description": "围绕报告里竞争强度最高的竞品展开",
                                },
                            ],
                        },
                    )
                ],
                finish_reason="tool_calls",
            )

    fake_model = FakeOrchestratorModel()

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
    monkeypatch.setattr(orchestrator_module, "send_reply_event", _async_noop)
    monkeypatch.setattr("app.workflow.events.send_progress_event", _async_noop)
    monkeypatch.setattr(
        orchestrator_module.session_event_publisher,
        "emit_to_session",
        _async_noop,
    )

    monkeypatch.setattr(
        orchestrator_module,
        "get_orchestrator_llm_model",
        lambda: fake_model,
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

    assert fake_model.called is True
    assert command.goto == "wait_for_user"
    assert command.update["awaiting_user"] is True
    pending = command.update["pending_confirmation"]
    assert pending["request_id"] == "ask_report_next_step"
    assert pending["message"] == "报告已生成。基于当前报告，建议先确认下一步分析重点："
    assert pending["options"][0]["id"] == "source_gap_review"
    assert pending["options"][1]["label"] == "对比主要竞品"


async def _async_noop(*args, **kwargs) -> None:
    return None
