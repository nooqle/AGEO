"""Tool → graph node mapping (shared; avoid NameError in extracted modules).

Used by orchestrator_node and workflow_progress. Keep registry overlay here so
knife-extracted helpers do not depend on the shell defining TOOL_TO_NODE later.
"""

from __future__ import annotations

TOOL_TO_NODE: dict[str, str] = {
    "brand_analysis": "a1_brand",
    "persona_generation": "a2_persona",
    "question_simulation": "a3_question",
    "answer_fetch": "a4_fetch",
    # 3b-1.2: amway entity extract / circle projection (topology-aware)
    "amway_entity_extract": "amway_extract",
    "amway_circle_projection": "amway_projection",
    "amway_secondary_analysis": "amway_analysis",
    "amway_content_draft": "amway_content",
    "table_intake_skill": "table_intake",
    "analysis_report_skill": "a5_analytics",
    "data_analytics": "a5_analytics",
}

# Remaining static tools (non-amway registry surface)
TOOL_TO_NODE.update(
    {
        "knowledge_lookup": "knowledge_lookup",
        "knowledge_aggregate": "knowledge_aggregate",
        "knowledge_compare": "knowledge_compare",
        "knowledge_export": "knowledge_export",
        "confidence_analysis_skill": "confidence_analysis_executor",
        "site_confidence_assessment_skill": "site_confidence_assessment_executor",
        "post_analysis_skill": "post_analysis_executor",
        "drill_down_analysis": "drill_down",
        "compare_snapshots": "compare_snapshots",
        # Monitoring tools (Cycle 4)
        "manage_monitoring_schedule": "create_monitoring",
        "create_monitoring_schedule": "create_monitoring",
    }
)

# Overlay registry-driven tool→graph mappings (registry wins when present)
try:
    from app.workflow.node_contracts import (
        CANVAS_TO_TOOL as _REGISTRY_CANVAS_TO_TOOL,
        get_contract as _get_contract,
    )

    for _canvas_id, _tool in _REGISTRY_CANVAS_TO_TOOL.items():
        _c = _get_contract(_canvas_id)
        if _c and _c.graph_node and _tool:
            TOOL_TO_NODE[_tool] = _c.graph_node
except Exception:  # pragma: no cover - registry optional at import
    pass
