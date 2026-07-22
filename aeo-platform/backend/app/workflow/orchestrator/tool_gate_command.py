"""Tool availability block Command builder (Phase B close)."""

from __future__ import annotations

import json
from typing import Any, Mapping

from langgraph.types import Command

from app.services.tool_capability_matrix import ToolAvailabilityConstraint

def _build_tool_gate_block_command(
    *,
    state: Mapping[str, Any],
    tool_call,
    reply_text: str,
    new_history: list[dict[str, Any]],
    current_retry_counts: dict[str, Any],
    constraint: ToolAvailabilityConstraint,
) -> Command:
    result_payload = constraint.to_blocked_result()
    new_history.append(
        {
            "role": "tool",
            "content": json.dumps(result_payload, ensure_ascii=False),
            "tool_call_id": tool_call.id or "call_1",
            "name": constraint.tool_name,
        }
    )
    return Command(
        goto="orchestrator",
        update={
            "orchestrator_reply": reply_text,
            "orchestrator_history": new_history,
            "agent_retry_counts": current_retry_counts,
            "last_validation_result": {
                "gate_name": "tool_availability_gate",
                "passed": False,
                "tool_name": constraint.tool_name,
                "reason": constraint.reason,
                "suggested_next_actions": list(constraint.suggested_next_actions),
            },
            "last_harness_decision": {
                "decision_type": "capability_blocked",
                "recoverable": True,
                "tool_name": constraint.tool_name,
                "reason": constraint.reason,
                "suggested_next_actions": list(constraint.suggested_next_actions),
                "source_step": "orchestrator_tool_availability_gate",
                "headless_mode": bool(state.get("headless_mode")),
            },
        },
    )

