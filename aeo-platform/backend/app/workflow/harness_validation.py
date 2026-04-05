"""Runtime validation gates for harness-style execution control."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class HarnessDecision:
    """Runtime governance decision recorded outside model-visible context."""

    decision_type: str
    reason: str
    recoverable: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_state_payload(self) -> dict[str, Any]:
        return {
            "decision_type": self.decision_type,
            "reason": self.reason,
            "recoverable": self.recoverable,
            "metadata": dict(self.metadata or {}),
        }


@dataclass(frozen=True)
class ValidationGateResult:
    """Result of a runtime validation gate."""

    gate_name: str
    passed: bool
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_state_payload(self) -> dict[str, Any]:
        return {
            "gate_name": self.gate_name,
            "passed": self.passed,
            "reason": self.reason,
            "metadata": dict(self.metadata or {}),
        }


def evaluate_skill_preconditions(
    state: Mapping[str, Any],
    contract_payload: Mapping[str, Any] | None,
) -> ValidationGateResult:
    """Evaluate known preconditions declared by the current skill contract."""

    if not contract_payload:
        return ValidationGateResult(
            gate_name="precondition_gate",
            passed=True,
            reason="No skill contract attached to current state.",
        )

    preconditions = [str(item) for item in (contract_payload.get("preconditions") or [])]
    missing: list[str] = []
    for rule in preconditions:
        if rule == "fetch_results_required" and not state.get("fetch_results"):
            missing.append(rule)
        elif rule == "analysis_results_required" and not (
            state.get("fetch_results") or state.get("metrics") or state.get("report")
        ):
            missing.append(rule)
        elif rule == "brand_profile_required" and not state.get("brand_profile"):
            missing.append(rule)

    if missing:
        return ValidationGateResult(
            gate_name="precondition_gate",
            passed=False,
            reason=f"Missing skill preconditions: {', '.join(missing)}",
            metadata={"missing_preconditions": missing},
        )

    return ValidationGateResult(
        gate_name="precondition_gate",
        passed=True,
        reason="Skill preconditions satisfied.",
        metadata={"evaluated_preconditions": preconditions},
    )


def validate_artifact_writeback(
    *,
    gate_name: str,
    artifact_message_id: str | None,
    artifact_key: str | None,
    artifact_kind: str,
    metadata: Mapping[str, Any] | None = None,
) -> ValidationGateResult:
    """Validate that artifact persistence completed before node completion."""

    payload = dict(metadata or {})
    payload.update(
        {
            "artifact_message_id": artifact_message_id or "",
            "artifact_key": artifact_key or "",
            "artifact_kind": artifact_kind,
        }
    )
    if not artifact_message_id:
        return ValidationGateResult(
            gate_name=gate_name,
            passed=False,
            reason=f"{artifact_kind} artifact writeback did not return a persisted message id.",
            metadata=payload,
        )

    return ValidationGateResult(
        gate_name=gate_name,
        passed=True,
        reason=f"{artifact_kind} artifact writeback validated.",
        metadata=payload,
    )


def evaluate_skill_postconditions(
    *,
    state: Mapping[str, Any],
    contract_payload: Mapping[str, Any] | None,
    pending_update: Mapping[str, Any] | None = None,
    artifact_validation: ValidationGateResult | None = None,
) -> ValidationGateResult:
    """Evaluate known postconditions declared by the current skill contract."""

    if not contract_payload:
        return ValidationGateResult(
            gate_name="postcondition_gate",
            passed=True,
            reason="No skill contract attached to current state.",
        )

    pending = dict(pending_update or {})
    postconditions = [str(item) for item in (contract_payload.get("postconditions") or [])]
    missing: list[str] = []
    for rule in postconditions:
        if rule in {"report_artifact_persisted", "confidence_artifact_persisted"}:
            if not artifact_validation or not artifact_validation.passed:
                missing.append(rule)
        elif rule == "metrics_available" and not (
            pending.get("metrics") or state.get("metrics")
        ):
            missing.append(rule)
        elif rule in {"skill_result_recorded", "followup_result_recorded"} and not (
            pending.get("last_skill_result") or state.get("last_skill_result")
        ):
            missing.append(rule)

    if missing:
        return ValidationGateResult(
            gate_name="postcondition_gate",
            passed=False,
            reason=f"Missing skill postconditions: {', '.join(missing)}",
            metadata={"missing_postconditions": missing},
        )

    return ValidationGateResult(
        gate_name="postcondition_gate",
        passed=True,
        reason="Skill postconditions satisfied.",
        metadata={"evaluated_postconditions": postconditions},
    )


def build_harness_decision(
    *,
    decision_type: str,
    reason: str,
    recoverable: bool,
    metadata: Mapping[str, Any] | None = None,
) -> HarnessDecision:
    return HarnessDecision(
        decision_type=decision_type,
        reason=reason,
        recoverable=recoverable,
        metadata=dict(metadata or {}),
    )


def validate_scoped_fetch_merge(
    *,
    platform_filter: list[str] | None,
    preserved_results: list[dict[str, Any]] | None,
    merged_results: list[dict[str, Any]] | None,
) -> ValidationGateResult:
    """Validate that a scoped fetch merge preserves unselected platform results."""

    if not platform_filter:
        return ValidationGateResult(
            gate_name="scoped_fetch_merge_gate",
            passed=True,
            reason="No scoped fetch merge validation required.",
        )

    preserved = list(preserved_results or [])
    merged = list(merged_results or [])
    merged_by_question = {
        str(item.get("question_id") or ""): item for item in merged if item.get("question_id")
    }
    missing_questions: list[str] = []
    missing_platform_pairs: list[str] = []

    for baseline_entry in preserved:
        question_id = str(baseline_entry.get("question_id") or "")
        if not question_id:
            continue
        merged_entry = merged_by_question.get(question_id)
        if not merged_entry:
            missing_questions.append(question_id)
            continue
        merged_platforms = {
            str(platform_result.get("platform") or "").lower()
            for platform_result in merged_entry.get("platform_results", [])
        }
        for baseline_platform in baseline_entry.get("platform_results", []):
            platform_name = str(baseline_platform.get("platform") or "").lower()
            if platform_name and platform_name not in merged_platforms:
                missing_platform_pairs.append(f"{question_id}:{platform_name}")

    if missing_questions or missing_platform_pairs:
        return ValidationGateResult(
            gate_name="scoped_fetch_merge_gate",
            passed=False,
            reason="Scoped fetch merge did not preserve all unselected baseline results.",
            metadata={
                "missing_questions": missing_questions,
                "missing_platform_pairs": missing_platform_pairs,
            },
        )

    return ValidationGateResult(
        gate_name="scoped_fetch_merge_gate",
        passed=True,
        reason="Scoped fetch merge preserved unselected baseline results.",
        metadata={
            "preserved_question_count": len(preserved),
            "merged_question_count": len(merged),
        },
    )


def decide_a4_completion_policy(
    *,
    success_count: int,
    fail_count: int,
    effective_min: int,
    platform_filter: list[str] | None = None,
) -> HarnessDecision:
    """Build a structured harness decision for A4 completion."""

    if success_count <= 0:
        return build_harness_decision(
            decision_type="retry_step",
            reason="A4 completed with zero successful platforms.",
            recoverable=True,
            metadata={
                "step": "A4",
                "blocker_code": "all_platforms_failed",
                "success_count": success_count,
                "fail_count": fail_count,
                "effective_min": effective_min,
                "platform_filter": list(platform_filter or []),
            },
        )

    if success_count < effective_min or fail_count > 0:
        return build_harness_decision(
            decision_type="degraded_continue",
            reason="A4 completed with partial platform failure but still has usable data.",
            recoverable=True,
            metadata={
                "step": "A4",
                "blocker_code": "partial_platform_failure",
                "success_count": success_count,
                "fail_count": fail_count,
                "effective_min": effective_min,
                "platform_filter": list(platform_filter or []),
            },
        )

    return build_harness_decision(
        decision_type="complete_step",
        reason="A4 completion policy passed with sufficient platform coverage.",
        recoverable=False,
        metadata={
            "step": "A4",
            "blocker_code": "none",
            "success_count": success_count,
            "fail_count": fail_count,
            "effective_min": effective_min,
            "platform_filter": list(platform_filter or []),
        },
    )
