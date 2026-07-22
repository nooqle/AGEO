"""Ontology action feedback pure helpers (P2 knife 4, cautious)."""

from __future__ import annotations

from typing import Any, Mapping

from app.workflow.orchestrator.ontology_format import (
    _normalize_ontology_action_feedback_type,
    _ontology_payload_has_value,
    _ontology_tool_arg_key_for_input,
)

ONTOLOGY_TOOL_ACTION_MAP: dict[str, str] = {
    "brand_analysis": "generate_brand_context",
    "persona_generation": "generate_persona_map",
    "question_simulation": "generate_question_set",
    "answer_fetch": "run_answer_fetch",
    "analysis_report_skill": "generate_report",
    "data_analytics": "generate_report",
    "compare_snapshots": "compare_snapshots",
    "site_confidence_assessment_skill": "generate_official_website_evidence_plan",
    "manage_monitoring_schedule": "create_monitoring_plan",
    "create_monitoring_schedule": "create_monitoring_plan",
}

def _ontology_action_feedback_for_key(
    state: Mapping[str, Any] | dict[str, Any] | None,
    action_key: str,
) -> dict[str, Any] | None:
    if not state:
        return None
    raw_world = state.get("ontology_world") or {}
    if not isinstance(raw_world, dict):
        return None
    raw_summary = raw_world.get("action_feedback_summary") or {}
    if not isinstance(raw_summary, dict):
        return None
    raw_latest = raw_summary.get("latest_by_action") or {}
    if not isinstance(raw_latest, dict):
        return None
    feedback = raw_latest.get(action_key)
    return feedback if isinstance(feedback, dict) else None

def _ontology_feedback_covers_missing_inputs(
    *,
    action_key: str,
    missing_inputs: list[Any],
    feedback: dict[str, Any] | None,
) -> bool:
    normalized_missing = [
        str(item).strip() for item in (missing_inputs or []) if str(item).strip()
    ]
    if not normalized_missing:
        return False
    provided_inputs = _ontology_feedback_provided_inputs(feedback)
    if not provided_inputs:
        return False
    provided_keys = set(provided_inputs.keys())
    return all(
        input_key in provided_keys
        or _ontology_tool_arg_key_for_input(action_key, input_key) in provided_keys
        for input_key in normalized_missing
    )

def _ontology_feedback_provided_inputs(
    feedback: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(feedback, dict):
        return {}
    provided_inputs = feedback.get("provided_inputs")
    if not isinstance(provided_inputs, dict):
        return {}
    return {
        str(key).strip(): value
        for key, value in provided_inputs.items()
        if str(key).strip() and _ontology_payload_has_value(value)
    }

def _ontology_confirmed_action_for_tool(
    state: Mapping[str, Any] | dict[str, Any] | None,
    tool_name: str | None,
) -> dict[str, Any] | None:
    action_key = ONTOLOGY_TOOL_ACTION_MAP.get(str(tool_name or "").strip())
    if not action_key:
        return None
    feedback = _ontology_action_feedback_for_key(state, action_key)
    if not feedback:
        return None
    feedback_type = _normalize_ontology_action_feedback_type(
        feedback.get("feedback_type")
    )
    action_record_id = str(feedback.get("action_record_id") or "").strip()
    consumed_by_action_record_id = str(
        feedback.get("consumed_by_action_record_id") or ""
    ).strip()
    if (
        feedback_type != "confirm"
        or not action_record_id
        or consumed_by_action_record_id
    ):
        return None
    return {
        "action_key": action_key,
        "action_record_id": action_record_id,
        "decision_id": feedback.get("decision_id"),
        "decided_at": feedback.get("decided_at"),
    }

def _ontology_action_feedback_for_tool(
    state: Mapping[str, Any] | dict[str, Any] | None,
    tool_name: str | None,
) -> dict[str, Any] | None:
    action_key = ONTOLOGY_TOOL_ACTION_MAP.get(str(tool_name or "").strip())
    if not action_key:
        return None
    feedback = _ontology_action_feedback_for_key(state, action_key)
    if not feedback:
        return None
    feedback_type = _normalize_ontology_action_feedback_type(
        feedback.get("feedback_type")
    )
    action_record_id = str(feedback.get("action_record_id") or "").strip()
    consumed_by_action_record_id = str(
        feedback.get("consumed_by_action_record_id") or ""
    ).strip()
    if feedback_type not in {"confirm", "provide_input"}:
        return None
    if not action_record_id or consumed_by_action_record_id:
        return None
    return {
        "action_key": action_key,
        "feedback_type": feedback_type,
        "action_record_id": action_record_id,
        "decision_id": feedback.get("decision_id"),
        "decided_at": feedback.get("decided_at"),
        "provided_inputs": _ontology_feedback_provided_inputs(feedback),
    }

def _merge_ontology_provided_inputs_into_tool_args(
    *,
    action_key: str,
    tool_args: dict[str, Any],
    provided_inputs: dict[str, Any],
) -> dict[str, Any]:
    if not provided_inputs:
        return tool_args
    merged = dict(tool_args or {})
    for input_key, value in provided_inputs.items():
        target_key = _ontology_tool_arg_key_for_input(action_key, input_key)
        if not _ontology_payload_has_value(merged.get(target_key)):
            merged[target_key] = value
    return merged

def _find_ontology_action_plan_item(
    action_plan: dict[str, Any],
    action_key: str,
) -> dict[str, Any] | None:
    for collection_key in ("action_readiness", "recommended_actions"):
        for raw_item in action_plan.get(collection_key) or []:
            if not isinstance(raw_item, dict):
                continue
            if str(raw_item.get("action_key") or "").strip() == action_key:
                return raw_item
    return None

def _ontology_action_gate_message(
    *,
    kind: str,
    action_name: str,
    action_item: dict[str, Any],
    reason: str,
) -> str:
    if kind == "needs_input":
        missing_inputs = ", ".join(action_item.get("missing_inputs") or [])
        suffix = f"还缺少：{missing_inputs}。" if missing_inputs else ""
        return f"{action_name} 还不能直接执行。{suffix}{reason}"
    if kind == "needs_confirmation":
        return f"{action_name} 需要你确认后才能执行。{reason}"
    missing_objects = action_item.get("missing_objects") or []
    if missing_objects:
        object_labels = ", ".join(
            str(item.get("object_type") or "") for item in missing_objects
        )
        return f"{action_name} 暂时被阻止，缺少前置信息：{object_labels}。{reason}"
    return f"{action_name} 暂时被阻止。{reason}"

def _ontology_action_gate_options(
    kind: str,
    action_item: dict[str, Any],
) -> list[dict[str, str]]:
    action_key = str(action_item.get("action_key") or "action")
    if kind == "needs_confirmation":
        return [
            {
                "id": f"confirm_{action_key}",
                "label": "确认执行",
                "description": "记录这次确认，再继续执行。",
            },
            {
                "id": f"defer_{action_key}",
                "label": "暂不执行",
                "description": "保留当前情报状态，不触发这个操作。",
            },
        ]
    return [
        {
            "id": f"provide_input_{action_key}",
            "label": "补充信息",
            "description": "补齐缺少字段后再重新判断。",
        },
        {
            "id": f"defer_{action_key}",
            "label": "稍后处理",
            "description": "暂时不进入这个操作。",
        },
    ]

