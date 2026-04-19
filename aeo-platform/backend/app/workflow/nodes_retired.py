"""Retired workflow nodes kept only for checkpoint-safe recovery."""

from __future__ import annotations

from datetime import datetime, timezone

from langgraph.types import Command

from app.workflow.events import send_error_event
from app.workflow.harness_validation import build_harness_decision
from app.workflow.skill_state import build_harness_decision_update
from app.workflow.state import AgentState


async def retired_confidence_executor_node(state: AgentState) -> Command:
    """Gracefully fail historical confidence checkpoints after retirement."""

    session_id = state["session_id"]
    message = (
            "旧版引用来源评估能力已退役，当前系统不再继续该步骤。"
            "如需评估官网，请改为对当前监测品牌自己的官网发起官网 AI 友好度评估。"
    )
    await send_error_event(session_id, "A7", message, recoverable=True)
    decision_update = build_harness_decision_update(
        state,
        build_harness_decision(
            decision_type="fail_step",
            reason=message,
            recoverable=True,
            metadata={"step": "A7", "gate": "retired_confidence_skill"},
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
