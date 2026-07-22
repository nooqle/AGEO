"""Orchestrator package — extracted modules (P2 split).

Public entry remains ``app.workflow.orchestrator_node`` for graph wiring.
"""

from app.workflow.orchestrator.message_builders import (
    _build_orchestrator_assistant_message,
    _inject_runtime_reminder_message,
)
from app.workflow.orchestrator.report_state import _is_completed_analysis_report_state
from app.workflow.orchestrator.run_context import (
    _get_latest_user_message,
    get_input_scope,
    get_recipe_meta_from_state,
    parse_recipe_meta_from_mapping,
)
from app.workflow.orchestrator.text_normalize import (
    _compact_text,
    _contains_non_negated_keyword,
    _extract_exact_datetime_scope_text,
    _is_english_dominant_text,
    _normalize_internal_analysis_mode,
    _normalize_public_knowledge_text,
    _normalize_public_report_kind,
)

__all__ = [
    "_build_orchestrator_assistant_message",
    "_compact_text",
    "_contains_non_negated_keyword",
    "_extract_exact_datetime_scope_text",
    "_get_latest_user_message",
    "_inject_runtime_reminder_message",
    "_is_completed_analysis_report_state",
    "_is_english_dominant_text",
    "_normalize_internal_analysis_mode",
    "_normalize_public_knowledge_text",
    "_normalize_public_report_kind",
    "get_input_scope",
    "get_recipe_meta_from_state",
    "parse_recipe_meta_from_mapping",
]
