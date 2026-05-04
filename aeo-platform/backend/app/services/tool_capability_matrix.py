"""Unified tool capability matrix for orchestrator and executor routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolCapability:
    """Structured capability metadata for a callable tool or internal primitive."""

    tool_name: str
    capability_type: str
    allowed_callers: tuple[str, ...]
    side_effect_level: str
    artifact_writeback_target: str | None
    confirmation_policy: str
    canonical_route: str | None = None
    notes: str = ""

    def to_state_payload(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "capability_type": self.capability_type,
            "allowed_callers": list(self.allowed_callers),
            "side_effect_level": self.side_effect_level,
            "artifact_writeback_target": self.artifact_writeback_target,
            "confirmation_policy": self.confirmation_policy,
            "canonical_route": self.canonical_route,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ToolAvailabilityConstraint:
    """Current-state availability result for a tool call."""

    tool_name: str
    blocked: bool
    reason: str = ""
    suggested_next_actions: tuple[str, ...] = ()
    source: str = "contextual_tool_gate"

    def to_blocked_result(self) -> dict[str, Any]:
        return {
            "type": "capability_blocked",
            "tool_name": self.tool_name,
            "blocked": self.blocked,
            "reason": self.reason,
            "suggested_next_actions": list(self.suggested_next_actions),
            "source": self.source,
        }


_TOOL_CAPABILITY_MATRIX: dict[str, ToolCapability] = {
    "brand_analysis": ToolCapability(
        tool_name="brand_analysis",
        capability_type="executor_stage",
        allowed_callers=("orchestrator",),
        side_effect_level="state_write",
        artifact_writeback_target="brand_profile",
        confirmation_policy="natural_language_orchestrator",
        canonical_route="a1_brand",
        notes="A1 stage entrypoint for brand + competitor discovery.",
    ),
    "persona_generation": ToolCapability(
        tool_name="persona_generation",
        capability_type="executor_stage",
        allowed_callers=("orchestrator",),
        side_effect_level="artifact_write",
        artifact_writeback_target="marketingPersonas",
        confirmation_policy="ask_user_required",
        canonical_route="a2_persona",
        notes="A2 stage entrypoint; persona role remains distinct from later question generation.",
    ),
    "question_simulation": ToolCapability(
        tool_name="question_simulation",
        capability_type="workflow_stage",
        allowed_callers=("orchestrator",),
        side_effect_level="artifact_write",
        artifact_writeback_target="questionList",
        confirmation_policy="ask_user_required",
        canonical_route="a3_question",
        notes="A3 stage route. Internal generation work should be delegated to question_generation.",
    ),
    "question_generation": ToolCapability(
        tool_name="question_generation",
        capability_type="generation_tool",
        allowed_callers=("a3_question",),
        side_effect_level="none",
        artifact_writeback_target=None,
        confirmation_policy="internal_only",
        canonical_route=None,
        notes="Internal generator primitive used by A3 stage for baseline/persona question drafting.",
    ),
    "answer_fetch": ToolCapability(
        tool_name="answer_fetch",
        capability_type="fetch_tool",
        allowed_callers=("orchestrator", "a4_fetch"),
        side_effect_level="external_read_write",
        artifact_writeback_target="fetch_results",
        confirmation_policy="mode_required",
        canonical_route="a4_fetch",
        notes="A4 fetch entrypoint; may run first-time fetch, platform-scoped rerun, or full-mode rerun.",
    ),
    "aio_answer_fetch": ToolCapability(
        tool_name="aio_answer_fetch",
        capability_type="runtime_tool",
        allowed_callers=("a4_fetch",),
        side_effect_level="external_read_write",
        artifact_writeback_target="fetch_results",
        confirmation_policy="internal_only",
        canonical_route=None,
        notes=(
            "Internal AIO runtime tool used by A4. It owns browser execution, "
            "AuthContext/RunContext binding, and human takeover packets."
        ),
    ),
    "drill_down_analysis": ToolCapability(
        tool_name="drill_down_analysis",
        capability_type="followup_tool",
        allowed_callers=("orchestrator", "post_analysis_executor"),
        side_effect_level="none",
        artifact_writeback_target="chat_reply",
        confirmation_policy="natural_language_orchestrator",
        canonical_route="post_analysis_executor",
        notes="Maps to post_analysis_skill in drill_down mode.",
    ),
    "compare_snapshots": ToolCapability(
        tool_name="compare_snapshots",
        capability_type="followup_tool",
        allowed_callers=("orchestrator", "post_analysis_executor"),
        side_effect_level="artifact_write",
        artifact_writeback_target="report",
        confirmation_policy="natural_language_orchestrator",
        canonical_route="post_analysis_executor",
        notes="Maps to post_analysis_skill in compare_snapshots mode.",
    ),
    "knowledge_lookup": ToolCapability(
        tool_name="knowledge_lookup",
        capability_type="knowledge_tool",
        allowed_callers=("orchestrator",),
        side_effect_level="none",
        artifact_writeback_target=None,
        confirmation_policy="never",
        canonical_route="knowledge_lookup",
    ),
    "knowledge_aggregate": ToolCapability(
        tool_name="knowledge_aggregate",
        capability_type="knowledge_tool",
        allowed_callers=("orchestrator",),
        side_effect_level="none",
        artifact_writeback_target=None,
        confirmation_policy="never",
        canonical_route="knowledge_aggregate",
    ),
    "knowledge_compare": ToolCapability(
        tool_name="knowledge_compare",
        capability_type="knowledge_tool",
        allowed_callers=("orchestrator",),
        side_effect_level="artifact_write",
        artifact_writeback_target="knowledge_compare_result",
        confirmation_policy="never",
        canonical_route="knowledge_compare",
    ),
    "knowledge_export": ToolCapability(
        tool_name="knowledge_export",
        capability_type="knowledge_tool",
        allowed_callers=("orchestrator",),
        side_effect_level="artifact_write",
        artifact_writeback_target="knowledge_export_result",
        confirmation_policy="never",
        canonical_route="knowledge_export",
    ),
}


def get_tool_capability(tool_name: str | None) -> ToolCapability | None:
    if not tool_name:
        return None
    return _TOOL_CAPABILITY_MATRIX.get(str(tool_name).strip())


def validate_tool_capability_access(
    *,
    caller: str,
    tool_name: str | None = None,
    capability: ToolCapability | None = None,
) -> tuple[ToolCapability | None, str | None]:
    resolved_capability = capability or get_tool_capability(tool_name)
    if resolved_capability is None:
        return None, None

    if caller in resolved_capability.allowed_callers:
        return resolved_capability, None

    allowed_callers = "、".join(resolved_capability.allowed_callers) or "无"
    return (
        resolved_capability,
        (
            f"能力 '{resolved_capability.tool_name}' 不允许由 '{caller}' 调用。"
            f"允许调用方：{allowed_callers}。"
        ),
    )


def list_tool_capabilities(*, include_internal: bool = True) -> list[ToolCapability]:
    capabilities = list(_TOOL_CAPABILITY_MATRIX.values())
    if include_internal:
        return capabilities
    return [
        capability
        for capability in capabilities
        if capability.confirmation_policy != "internal_only"
    ]
