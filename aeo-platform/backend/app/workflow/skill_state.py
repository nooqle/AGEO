"""Helpers for skill-aware workflow state updates."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.workflow.harness_validation import HarnessDecision, ValidationGateResult
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


def build_validation_result_update(
    state: AgentState,
    result: ValidationGateResult,
) -> dict[str, Any]:
    history = list(state.get("validation_history") or [])
    entry = result.to_state_payload()
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    history.append(entry)
    return {
        "last_validation_result": entry,
        "validation_history": history,
    }


def build_harness_decision_update(
    state: AgentState,
    decision: HarnessDecision,
) -> dict[str, Any]:
    history = list(state.get("harness_decision_history") or [])
    entry = decision.to_state_payload()
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    history.append(entry)
    return {
        "last_harness_decision": entry,
        "harness_decision_history": history,
    }


def _iter_skill_prompt_sections(state: AgentState) -> list[dict[str, Any]]:
    sections = list(state.get("current_skill_prompt_sections") or [])
    if sections:
        return sections

    contract = state.get("current_skill_contract") or {}
    contract_sections = list(contract.get("prompt_sections") or [])
    if contract_sections:
        return contract_sections

    sections = []
    package_context = str(state.get("current_skill_package_context") or "").strip()
    if package_context:
        sections.append(
            {
                "key": "legacy_skill_package",
                "title": "技能包上下文",
                "body": package_context,
            }
        )

    profile_overlay = str(state.get("current_skill_prompt_overlay") or "").strip()
    if profile_overlay:
        sections.append(
            {
                "key": "legacy_skill_profile_overlay",
                "title": "技能补充画像",
                "body": profile_overlay,
            }
        )
    return sections


def apply_skill_prompt_context(state: AgentState, prompt: str) -> str:
    """Append structured skill sections to an executor prompt."""

    sections: list[str] = []
    for section in _iter_skill_prompt_sections(state):
        body = str(section.get("body") or "").strip()
        if not body:
            continue
        title = str(section.get("title") or "技能上下文").strip()
        sections.append(f"## {title}\n{body}")

    if not sections:
        return prompt
    return f"{prompt}\n\n" + "\n\n".join(sections)
