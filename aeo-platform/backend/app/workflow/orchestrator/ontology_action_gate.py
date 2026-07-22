"""Ontology action gate decision pure helper (P2 knife 8, cautious)."""

from __future__ import annotations

from typing import Any, Mapping

from app.workflow.orchestrator.ontology_action_feedback import (
    ONTOLOGY_TOOL_ACTION_MAP,
    _find_ontology_action_plan_item,
    _ontology_action_feedback_for_key,
    _ontology_feedback_covers_missing_inputs,
)
from app.workflow.orchestrator.ontology_format import (
    _normalize_ontology_action_feedback_type,
)

def _ontology_action_gate_decision(
    state: Mapping[str, Any] | dict[str, Any] | None,
    tool_name: str | None,
    tool_args: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return a blocking decision when the ontology plan disallows a tool call."""

    if not state:
        return None
    action_key = ONTOLOGY_TOOL_ACTION_MAP.get(str(tool_name or "").strip())
    if not action_key:
        return None
    raw_plan = state.get("ontology_action_plan") or {}
    if not isinstance(raw_plan, dict):
        return None
    action_item = _find_ontology_action_plan_item(raw_plan, action_key)
    if action_item is None:
        return None
    readiness = str(action_item.get("readiness") or "").strip().lower()
    missing_inputs = list(action_item.get("missing_inputs") or [])
    missing_objects = list(action_item.get("missing_objects") or [])
    feedback = _ontology_action_feedback_for_key(state, action_key)
    feedback_type = _normalize_ontology_action_feedback_type(
        feedback.get("feedback_type") if feedback else None
    )
    feedback_action_record_id = str(
        (feedback or {}).get("action_record_id") or ""
    ).strip()
    consumed_by_action_record_id = str(
        (feedback or {}).get("consumed_by_action_record_id") or ""
    ).strip()
    feedback_is_usable = bool(
        feedback_action_record_id and not consumed_by_action_record_id
    )
    has_user_confirmation = bool(feedback_type == "confirm" and feedback_is_usable)
    has_provided_inputs = _ontology_feedback_covers_missing_inputs(
        action_key=action_key,
        missing_inputs=missing_inputs,
        feedback=feedback,
    )
    has_user_input = bool(
        feedback_type == "provide_input" and feedback_is_usable and has_provided_inputs
    )
    if feedback_type == "defer":
        return {
            "kind": "blocked",
            "action_key": action_key,
            "tool_name": tool_name,
            "action": action_item,
            "reason": "用户已在品牌看板暂缓这个操作，系统不能绕过人的反馈继续执行。",
        }
    if missing_objects or readiness == "blocked":
        return {
            "kind": "blocked",
            "action_key": action_key,
            "tool_name": tool_name,
            "action": action_item,
            "reason": action_item.get("reason")
            or "当前情报还缺少执行该操作所需的前置信息。",
        }
    if missing_inputs or readiness == "needs_input":
        if has_user_input:
            if bool(action_item.get("requires_confirmation")):
                return {
                    "kind": "needs_confirmation",
                    "action_key": action_key,
                    "tool_name": tool_name,
                    "action": action_item,
                    "reason": "所需信息已补齐，但这项操作仍需要人的确认，系统不能直接执行。",
                }
            return None
        return {
            "kind": "needs_input",
            "action_key": action_key,
            "tool_name": tool_name,
            "action": action_item,
            "reason": "这项操作还缺少必填信息，不能继续处理。",
        }
    if bool(action_item.get("requires_confirmation")) or readiness == (
        "needs_confirmation"
    ):
        if has_user_confirmation:
            return None
        return {
            "kind": "needs_confirmation",
            "action_key": action_key,
            "tool_name": tool_name,
            "action": action_item,
            "reason": "这项操作需要人的确认，系统不能直接执行。",
        }
    if readiness in {"ready", "ready_with_defaults"}:
        return None
    return {
        "kind": "blocked",
        "action_key": action_key,
        "tool_name": tool_name,
        "action": action_item,
        "reason": "行动计划返回了未知状态，已阻止继续处理。",
    }

