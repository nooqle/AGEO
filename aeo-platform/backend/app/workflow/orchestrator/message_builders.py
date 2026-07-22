"""Message construction helpers for orchestrator (P2 knife 1)."""

from __future__ import annotations

import json
from typing import Any

def _build_orchestrator_assistant_message(
    *,
    reply_text: str,
    tool_call_result: Any | None,
    raw_thinking_text: str,
) -> dict[str, Any]:
    assistant_msg: dict[str, Any] = {
        "role": "assistant",
        "content": reply_text,
    }
    if raw_thinking_text and tool_call_result:
        assistant_msg["reasoning_content"] = raw_thinking_text
    if tool_call_result:
        assistant_msg["tool_calls"] = [
            {
                "id": tool_call_result.id or "call_1",
                "type": "function",
                "function": {
                    "name": tool_call_result.name,
                    "arguments": json.dumps(
                        tool_call_result.arguments, ensure_ascii=False
                    ),
                },
            }
        ]
    return assistant_msg

def _inject_runtime_reminder_message(
    messages: list[dict[str, Any]],
    runtime_reminder_message: str | None,
) -> list[dict[str, Any]]:
    reminder = str(runtime_reminder_message or "").strip()
    if not reminder:
        return messages

    reminder_message = {"role": "user", "content": reminder}
    if messages and messages[-1].get("role") == "user":
        return [*messages[:-1], reminder_message, messages[-1]]
    return [*messages, reminder_message]

