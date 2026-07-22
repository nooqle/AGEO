"""Build orchestrator LLM message history (P2 knife 8, cautious)."""

from __future__ import annotations

import logging
from typing import Any, Mapping

from app.workflow.orchestrator.agent_result_summary import (
    _build_agent_result_summary,
)
from app.workflow.orchestrator.message_builders import (
    _inject_runtime_reminder_message,
)

logger = logging.getLogger(__name__)

def build_orchestrator_messages(
    state: Mapping[str, Any],
    runtime_reminder_message: str | None = None,
) -> list[dict[str, Any]]:
    """Build message history for the orchestrator LLM call.

    If the last message in history is an assistant message with tool_calls
    but no matching tool result, inject one from the agent's output in state.
    """
    history = state.get("orchestrator_history", [])
    if not history:
        # First call: use the user's original message with full brand context
        brand_name = state.get("brand_name", "")
        industry = state.get("industry_hint", "")
        website = state.get("official_website", "")
        context_parts = [f"请帮我分析品牌：{brand_name}"]
        if industry:
            context_parts.append(f"（行业：{industry}）")
        if website:
            context_parts.append(f"（官网：{website}）")
        return _inject_runtime_reminder_message(
            [{"role": "user", "content": "".join(context_parts)}],
            runtime_reminder_message,
        )

    # Limit history to last 20 messages to prevent context growth
    MAX_HISTORY = 20
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]

    messages = list(history)

    # Check if the last message is an assistant with tool_calls but no tool result follows
    if (
        messages
        and messages[-1].get("role") == "assistant"
        and messages[-1].get("tool_calls")
    ):
        # Missing tool result — inject one
        tool_calls = messages[-1]["tool_calls"]
        tc = tool_calls[0]
        tc_id = tc.get("id", state.get("tool_call_id", "call_1"))
        tc_name = tc.get("function", {}).get("name", "")

        summary = _build_agent_result_summary(state, tc_name)
        tool_msg: dict[str, Any] = {
            "role": "tool",
            "content": summary,
            "tool_call_id": tc_id,
        }
        if tc_name:
            tool_msg["name"] = tc_name
        messages.append(tool_msg)
        logger.info(
            f"[Orchestrator] Injected tool result for {tc_name} "
            f"(tool_call_id={tc_id}): {summary[:80]}..."
        )

    return _inject_runtime_reminder_message(messages, runtime_reminder_message)

