"""Prompt evidence rendering helpers (P2 knife 5, cautious)."""

from __future__ import annotations

from typing import Any, Mapping

from app.workflow.orchestrator_context_packets import (
    RecentEvidencePacket,
    render_recent_evidence_packet,
)
from app.workflow.orchestrator_instruction_defense import (
    build_instruction_defense_context,
    detect_instruction_injection,
)
from app.workflow.orchestrator.history_query import _session_was_recalled
from app.workflow.orchestrator.run_context import _get_latest_user_message
from app.workflow.orchestrator.session_tool_surface import _KNOWLEDGE_TOOL_NAMES

_RECENT_EVIDENCE_PROMPT_PRIORITY: dict[str, int] = {
    "uploaded_input": 0,
    "current_fetch": 1,
    "current_artifact": 2,
    "knowledge_lookup": 3,
    "knowledge_compare": 4,
    "knowledge_aggregate": 5,
    "knowledge_export": 6,
}

def _render_recent_evidence_for_prompt(packet: RecentEvidencePacket) -> str:
    if not packet.items:
        return ""

    ranked_items = sorted(
        packet.items,
        key=lambda item: (
            _RECENT_EVIDENCE_PROMPT_PRIORITY.get(item.source, 99),
            -int(item.relevance_score),
            item.title,
        ),
    )
    top_items = tuple(ranked_items[:3])
    if not top_items:
        return ""
    return render_recent_evidence_packet(RecentEvidencePacket(items=top_items))

def _should_render_history_availability(
    state: Mapping[str, Any],
    hidden_tool_names: set[str],
) -> bool:
    if _session_was_recalled(state):
        return False
    if _KNOWLEDGE_TOOL_NAMES.issubset(hidden_tool_names):
        return False
    manifest = state.get("knowledge_manifest") or {}
    available_sources = manifest.get("available_sources") or {}
    return any(bool(value) for value in available_sources.values())

def _should_render_instruction_defense(
    state: Mapping[str, Any],
    recent_evidence_packet: RecentEvidencePacket,
) -> bool:
    defense_context = build_instruction_defense_context(state, recent_evidence_packet)
    if (
        defense_context.prompt_disclosure_request
        or defense_context.suspicious_evidence_count
    ):
        return True
    latest_user_message = _get_latest_user_message(state)
    return detect_instruction_injection(latest_user_message)

