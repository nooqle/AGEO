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
        "skill_family": state.get("current_skill_family") or skill_key,
        "skill_package_key": state.get("current_skill_package_key"),
        "skill_package_name": state.get("current_skill_package_name"),
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


def apply_skill_prompt_context(state: AgentState, prompt: str) -> str:
    """Append package guidance and profile overlay to an executor prompt."""

    sections: list[str] = []
    package_context = str(state.get("current_skill_package_context") or "").strip()
    if package_context:
        sections.append(f"[Skill Package]\n{package_context}")

    profile_overlay = str(state.get("current_skill_prompt_overlay") or "").strip()
    if profile_overlay:
        sections.append(f"[Skill Profile Overlay]\n{profile_overlay}")

    if not sections:
        return prompt
    return f"{prompt}\n\n" + "\n\n".join(sections)
