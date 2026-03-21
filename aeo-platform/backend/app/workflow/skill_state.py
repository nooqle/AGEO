"""Helpers for skill-aware workflow state updates."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.workflow.state import AgentState


def build_skill_result_update(
    state: AgentState,
    *,
    skill_key: str | None,
    tool_name: str,
    status: str,
    summary: str,
    executor_ref: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not skill_key:
        return {}

    history = list(state.get("skill_history") or [])
    entry = {
        "skill_key": skill_key,
        "skill_profile": state.get("current_skill_profile"),
        "tool_name": tool_name,
        "status": status,
        "summary": summary,
        "executor_ref": executor_ref,
        "metadata": metadata or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    history.append(entry)

    return {
        "current_skill": skill_key,
        "last_skill_result": entry,
        "skill_history": history,
    }
