"""Ontology display/format pure helpers (P2 knife 1b)."""

from __future__ import annotations

from typing import Any, Mapping

ONTOLOGY_ACTION_INPUT_TOOL_ARG_ALIASES: dict[str, dict[str, str]] = {
    "generate_question_set": {
        "generation_mode": "mode",
        "question_count": "question_count",
    },
    "generate_report": {
        "report_kind": "report_type",
    },
    "create_monitoring_plan": {
        "cadence": "cadence",
        "question_ids": "question_ids",
    },
    "generate_official_website_evidence_plan": {
        "official_domain": "root_url",
    },
}


def _ontology_status_label(status: str) -> str:
    labels = {
        "not_cited": "未被引用",
        "active": "活跃",
        "observed": "已观测",
        "captured": "已采集",
        "derived": "已归纳",
        "published": "已发布",
        "created": "已创建",
        "suggested": "已建议",
        "failed": "采集失败",
    }
    normalized = str(status or "").strip()
    return labels.get(normalized, normalized or "未知")

def _ontology_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0

def _ontology_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0

def _ontology_brand_label(
    state: Mapping[str, Any],
    ontology_world: dict[str, Any],
) -> str:
    brand = ontology_world.get("brand") or {}
    label = str(brand.get("label") or "").strip() if isinstance(brand, dict) else ""
    return label or str(state.get("brand_name") or "该品牌").strip()

def _ontology_object_summaries(
    ontology_world: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("object_type")): item
        for item in list(ontology_world.get("object_summaries") or [])
        if isinstance(item, dict)
    }

def _source_domain_sort_key(item: dict[str, Any]) -> tuple[int, int, int, str]:
    return (
        _ontology_int(item.get("citation_count")),
        _ontology_int(item.get("answer_count")),
        _ontology_int(item.get("platform_count")),
        str(item.get("domain") or ""),
    )

def _relationship_is_core(item: dict[str, Any]) -> bool:
    link_type = str(item.get("link_type") or "").strip()
    visibility = str(item.get("visibility") or "").strip()
    if visibility == "core":
        return True
    if visibility == "supporting":
        return False
    if "default_visible" in item:
        return bool(item.get("default_visible"))
    return link_type in CORE_RELATIONSHIP_TYPES

def _action_readiness_label(value: Any) -> str:
    labels = {
        "ready": "可进入执行",
        "ready_with_defaults": "可用默认值进入执行",
        "needs_input": "需要补充信息",
        "needs_confirmation": "需要人确认",
        "blocked": "被阻塞",
    }
    normalized = str(value or "").strip()
    return labels.get(normalized, normalized or "待判断")

def _ontology_payload_has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True

def _normalize_ontology_action_feedback_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized.startswith("action_queue_"):
        normalized = normalized.removeprefix("action_queue_")
    if normalized in {"confirm", "confirmed", "accept", "accepted"}:
        return "confirm"
    if normalized in {"provide_input", "input", "input_provided"}:
        return "provide_input"
    if normalized in {"defer", "deferred", "dismiss", "skip"}:
        return "defer"
    return normalized

def _ontology_tool_arg_key_for_input(action_key: str, input_key: str) -> str:
    return (
        ONTOLOGY_ACTION_INPUT_TOOL_ARG_ALIASES.get(action_key, {}).get(input_key)
        or input_key
    )

