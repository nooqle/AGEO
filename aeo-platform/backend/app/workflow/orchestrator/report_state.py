"""Report completion predicates for orchestrator (P2 knife 1)."""

from __future__ import annotations

from typing import Any, Mapping

def _is_completed_analysis_report_state(state: Mapping[str, Any]) -> bool:
    """Return True when A5 has produced a final report for this run."""

    if str(state.get("execution_status") or "").lower() != "completed":
        return False
    if state.get("awaiting_user") or state.get("pending_confirmation"):
        return False

    current_step = str(state.get("current_step") or "").strip()
    current_skill = str(state.get("current_skill") or "").strip()
    next_action = str(state.get("next_action") or "").strip()
    is_report_context = (
        current_step == "A5"
        or current_skill in {"analysis_report_skill", "data_analytics"}
        or next_action in {"a5_analytics", "data_analytics"}
    )
    if not is_report_context:
        return False

    return bool(
        state.get("report")
        or state.get("baseline_report")
        or (state.get("metrics") and state.get("fetch_results"))
    )

