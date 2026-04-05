"""Deterministic runtime policy helpers for orchestrator recovery and redirects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class RuntimePolicyAction:
    """Structured runtime action consumed before the orchestrator asks the model."""

    action_type: str
    reason: str
    tool_name: str | None = None
    tool_args: dict[str, Any] = field(default_factory=dict)
    reply_text: str = ""
    source_step: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_state_payload(self) -> dict[str, Any]:
        return {
            "action_type": self.action_type,
            "reason": self.reason,
            "tool_name": self.tool_name,
            "tool_args": dict(self.tool_args or {}),
            "reply_text": self.reply_text,
            "source_step": self.source_step,
            "metadata": dict(self.metadata or {}),
        }


def build_next_required_action(
    *,
    tool_name: str,
    reason: str,
    tool_args: Mapping[str, Any] | None = None,
    reply_text: str = "",
    source_step: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return RuntimePolicyAction(
        action_type="run_tool",
        reason=reason,
        tool_name=tool_name,
        tool_args=dict(tool_args or {}),
        reply_text=reply_text,
        source_step=source_step,
        metadata=dict(metadata or {}),
    ).to_state_payload()


def parse_next_required_action(
    payload: Mapping[str, Any] | None,
) -> RuntimePolicyAction | None:
    if not payload:
        return None
    action_type = str(payload.get("action_type") or "").strip()
    reason = str(payload.get("reason") or "").strip()
    tool_name = str(payload.get("tool_name") or "").strip() or None
    if action_type != "run_tool" or not reason or not tool_name:
        return None
    return RuntimePolicyAction(
        action_type=action_type,
        reason=reason,
        tool_name=tool_name,
        tool_args=dict(payload.get("tool_args") or {}),
        reply_text=str(payload.get("reply_text") or "").strip(),
        source_step=str(payload.get("source_step") or "").strip() or None,
        metadata=dict(payload.get("metadata") or {}),
    )


def clear_runtime_policy_fields() -> dict[str, Any]:
    return {
        "next_required_action": None,
        "last_validation_result": None,
        "last_harness_decision": None,
    }


def _extract_latest_user_text(state: Mapping[str, Any]) -> str:
    history = list(state.get("orchestrator_history") or [])
    for item in reversed(history):
        if str(item.get("role") or "") == "user":
            text = str(item.get("content") or "").strip()
            if text:
                return text

    messages = list(state.get("messages") or [])
    for item in reversed(messages):
        role = getattr(item, "type", None) or getattr(item, "role", None)
        if role != "human" and role != "user":
            continue
        text = getattr(item, "content", "")
        if isinstance(text, str) and text.strip():
            return text.strip()
    return ""


def resolve_answer_fetch_mode_policy(
    state: Mapping[str, Any],
    tool_args: Mapping[str, Any] | None,
) -> tuple[str | None, str]:
    """Resolve the safest answer_fetch mode before falling back to ask_user."""

    args = dict(tool_args or {})
    explicit_mode = str(args.get("fetch_mode") or "").strip().lower()
    if explicit_mode in {"fast", "full"}:
        return explicit_mode, "tool_args_explicit"

    latest_user_text = _extract_latest_user_text(state).lower()
    full_keywords = ("完整", "全量", "浏览器", "full", "重新抓全部", "全部重跑")
    fast_keywords = ("快速", "fast", "先快速", "先跑一版")
    if any(keyword in latest_user_text for keyword in full_keywords):
        return "full", "user_intent_full"
    if any(keyword in latest_user_text for keyword in fast_keywords):
        return "fast", "user_intent_fast"

    existing_mode = str(state.get("fetch_mode") or "").strip().lower()
    if existing_mode in {"fast", "full"}:
        return existing_mode, "reuse_existing_mode"

    if bool(state.get("headless_mode")):
        return "fast", "headless_default_fast"

    has_questions = bool(args.get("custom_questions")) or bool(state.get("questions"))
    has_existing_fetch = bool(state.get("fetch_results"))
    if has_existing_fetch and args.get("platforms"):
        return "fast", "scoped_rerun_default_fast"
    if has_questions:
        return "fast", "question_ready_default_fast"

    return None, "ask_user_required"


def build_alternative_action_catalog(
    state: Mapping[str, Any],
    *,
    failed_step: str | None = None,
    blocker_code: str | None = None,
) -> list[dict[str, Any]]:
    """Build deterministic alternative actions for common runtime blockers."""

    step = str(failed_step or "").strip()
    blocker = str(blocker_code or "").strip()
    has_fetch_results = bool(state.get("fetch_results"))
    has_report = bool(state.get("report")) or bool(state.get("metrics"))

    options: list[dict[str, Any]] = []

    def _append(option: dict[str, Any]) -> None:
        option_id = str(option.get("id") or "")
        if option_id and not any(existing.get("id") == option_id for existing in options):
            options.append(option)

    if blocker in {"fetch_results_missing", "all_platforms_failed", "partial_platform_failure"}:
        _append(
            {
                "id": "run_answer_fetch",
                "label": "先执行答案抓取",
                "description": "补齐抓取结果后再继续分析或生成报告",
                "action_type": "run_tool",
                "tool_name": "answer_fetch",
                "tool_args": {},
            }
        )

    if blocker in {"analysis_context_missing", "artifact_writeback_failed"} or step == "A5":
        if has_fetch_results:
            _append(
                {
                    "id": "run_analysis_report",
                    "label": "重新生成分析报告",
                    "description": "沿用当前抓取结果，刷新正式报告与关键结论",
                    "action_type": "run_tool",
                    "tool_name": "analysis_report_skill",
                    "tool_args": {},
                }
            )

    if step == "A7" or (
        blocker == "artifact_writeback_failed"
        and str((state.get("current_step") or "")).strip() == "A7"
    ):
        if has_fetch_results:
            _append(
                {
                    "id": "run_confidence_signal",
                    "label": "重新执行引用置信度评估",
                    "description": "沿用当前抓取结果，刷新引用可信度分析",
                    "action_type": "run_tool",
                    "tool_name": "confidence_analysis_skill",
                    "tool_args": {},
                }
            )

    if blocker == "analysis_context_missing" and has_report:
        _append(
            {
                "id": "run_post_analysis",
                "label": "继续后续分析",
                "description": "基于当前报告和抓取结果继续深入分析",
                "action_type": "run_tool",
                "tool_name": "post_analysis_skill",
                "tool_args": {"analysis_mode": "drill_down"},
            }
        )

    _append(
        {
            "id": "retry",
            "label": "重新尝试",
            "description": f"再次执行 {step or '当前步骤'}",
        }
    )
    _append(
        {
            "id": "manual",
            "label": "手动提供数据",
            "description": "由您补充缺失信息或直接指定下一步",
        }
    )
    _append(
        {
            "id": "skip",
            "label": "跳过此步骤",
            "description": "接受当前缺口，继续后续流程",
        }
    )
    return options


def summarize_alternative_actions(options: list[Mapping[str, Any]]) -> str:
    prioritized = []
    for option in options:
        label = str(option.get("label") or "").strip()
        description = str(option.get("description") or "").strip()
        if not label:
            continue
        prioritized.append(f"{label}：{description}" if description else label)
        if len(prioritized) >= 2:
            break
    return "；".join(prioritized)
