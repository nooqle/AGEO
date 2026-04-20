"""Knowledge Workspace nodes."""

from __future__ import annotations

import hashlib
import json
import logging

from langgraph.types import Command

from app.core.database import AsyncSessionLocal
from app.services.knowledge_workspace_service import KnowledgeWorkspaceService
from app.workflow.events import save_and_send_artifact
from app.workflow.state import AgentState

logger = logging.getLogger(__name__)


def _resolve_knowledge_query(state: AgentState, tool_args: dict[str, object]) -> str:
    explicit_query = str(tool_args.get("query") or "").strip()
    if explicit_query:
        return explicit_query

    for item in reversed(list(state.get("orchestrator_history") or [])):
        if item.get("role") == "user":
            fallback_query = str(item.get("content") or "").strip()
            if fallback_query:
                return fallback_query
    return ""


def _build_export_artifact_key(
    state: AgentState,
    result: dict[str, object],
    tool_args: dict[str, object],
) -> str:
    scope = {
        "brand_name": result.get("brand_name"),
        "query": str(tool_args.get("query") or "").strip(),
        "analysis_period": result.get("analysis_period"),
        "source_types": result.get("source_types") or [],
        "platforms": result.get("platforms") or [],
        "platform": str(tool_args.get("platform") or "").strip(),
        "competitor_name": str(tool_args.get("competitor_name") or "").strip(),
        "domain": str(tool_args.get("domain") or "").strip(),
        "start_date": str(tool_args.get("start_date") or "").strip(),
        "end_date": str(tool_args.get("end_date") or "").strip(),
        "title": result.get("title"),
    }
    scope_digest = hashlib.sha1(
        json.dumps(scope, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    return f"{state['session_id']}_knowledge_export_{scope_digest}"


async def knowledge_lookup_node(state: AgentState) -> Command:
    """Look up historical evidence from Knowledge Workspace."""

    tool_args = state.get("tool_call_args") or {}
    query = _resolve_knowledge_query(state, tool_args)
    source_types = tool_args.get("source_types") or None
    platform = str(tool_args.get("platform") or "").strip() or None
    competitor_name = str(tool_args.get("competitor_name") or "").strip() or None
    domain = str(tool_args.get("domain") or "").strip() or None
    limit = int(tool_args.get("limit") or 8)

    brand_name = (
        (state.get("brand_profile") or {}).get("brand_name")
        or state.get("brand_name")
        or None
    )

    if not query:
        return Command(
            update={
                "knowledge_lookup_result": {
                    "status": "miss",
                    "query": query,
                    "matches": [],
                    "reason": "missing_query",
                }
            }
        )

    try:
        async with AsyncSessionLocal() as db:
            service = KnowledgeWorkspaceService(db)
            result = await service.lookup(
                query=query,
                entity_id=state.get("entity_id"),
                brand_name=brand_name,
                source_types=source_types,
                platform=platform,
                competitor_name=competitor_name,
                domain=domain,
                limit=max(min(limit, 12), 1),
            )
    except Exception as exc:
        logger.warning("[Knowledge] lookup failed: %s", exc)
        result = {
            "status": "miss",
            "query": query,
            "matches": [],
            "reason": "lookup_failed",
            "error": str(exc),
        }

    return Command(
        update={
            "knowledge_lookup_result": result,
            "current_step": "KNOWLEDGE",
        }
    )


async def knowledge_aggregate_node(state: AgentState) -> Command:
    """Aggregate historical evidence for analysis/export style tasks."""

    tool_args = state.get("tool_call_args") or {}
    query = _resolve_knowledge_query(state, tool_args)
    brand_name = (
        (state.get("brand_profile") or {}).get("brand_name")
        or state.get("brand_name")
        or None
    )

    try:
        async with AsyncSessionLocal() as db:
            service = KnowledgeWorkspaceService(db)
            result = await service.aggregate(
                query=query,
                entity_id=state.get("entity_id"),
                brand_name=brand_name,
                source_types=tool_args.get("source_types") or None,
                group_by=str(tool_args.get("group_by") or "source_type"),
                platform=str(tool_args.get("platform") or "").strip() or None,
                competitor_name=str(tool_args.get("competitor_name") or "").strip()
                or None,
                domain=str(tool_args.get("domain") or "").strip() or None,
                start_date=str(tool_args.get("start_date") or "").strip() or None,
                end_date=str(tool_args.get("end_date") or "").strip() or None,
                limit=int(tool_args.get("limit") or 20),
            )
    except Exception as exc:
        logger.warning("[Knowledge] aggregate failed: %s", exc)
        result = {
            "status": "miss",
            "groups": [],
            "reason": "aggregate_failed",
            "error": str(exc),
        }

    return Command(
        update={
            "knowledge_aggregate_result": result,
            "current_step": "KNOWLEDGE",
        }
    )


async def knowledge_compare_node(state: AgentState) -> Command:
    """Compare historical evidence across the latest two analysis windows."""

    tool_args = state.get("tool_call_args") or {}
    brand_name = (
        (state.get("brand_profile") or {}).get("brand_name")
        or state.get("brand_name")
        or None
    )

    try:
        async with AsyncSessionLocal() as db:
            service = KnowledgeWorkspaceService(db)
            result = await service.compare(
                entity_id=state.get("entity_id"),
                brand_name=brand_name,
                compare_by=str(tool_args.get("compare_by") or "platform"),
                source_types=tool_args.get("source_types") or None,
                limit=int(tool_args.get("limit") or 12),
            )
    except Exception as exc:
        logger.warning("[Knowledge] compare failed: %s", exc)
        result = {
            "status": "miss",
            "comparisons": [],
            "reason": "compare_failed",
            "error": str(exc),
        }

    return Command(
        update={
            "knowledge_compare_result": result,
            "current_step": "KNOWLEDGE",
        }
    )


async def knowledge_export_node(state: AgentState) -> Command:
    """Export historical evidence into a data-table artifact."""

    tool_args = state.get("tool_call_args") or {}
    query = _resolve_knowledge_query(state, tool_args)
    brand_name = (
        (state.get("brand_profile") or {}).get("brand_name")
        or state.get("brand_name")
        or None
    )

    try:
        async with AsyncSessionLocal() as db:
            service = KnowledgeWorkspaceService(db)
            result = await service.export_table(
                query=query,
                entity_id=state.get("entity_id"),
                brand_name=brand_name,
                source_types=tool_args.get("source_types") or None,
                platform=str(tool_args.get("platform") or "").strip() or None,
                competitor_name=str(tool_args.get("competitor_name") or "").strip()
                or None,
                domain=str(tool_args.get("domain") or "").strip() or None,
                start_date=str(tool_args.get("start_date") or "").strip() or None,
                end_date=str(tool_args.get("end_date") or "").strip() or None,
                limit=int(tool_args.get("limit") or 200),
            )
    except Exception as exc:
        logger.warning("[Knowledge] export failed: %s", exc)
        result = {
            "status": "miss",
            "reason": "export_failed",
            "error": str(exc),
            "rows": [],
            "columns": [],
        }

    if result.get("status") == "hit":
        artifact_id = _build_export_artifact_key(
            state,
            result,
            {**tool_args, "query": query},
        )
        artifact_data = {
            "artifact_kind": "knowledge_export",
            "brand_name": result.get("brand_name"),
            "analysis_period": result.get("analysis_period"),
            "export_title": result.get("title"),
            "description": result.get("description"),
            "itemCount": result.get("item_count", 0),
            "truncated": bool(result.get("truncated")),
            "has_more_records": bool(result.get("has_more_records")),
            "export_limit": result.get("export_limit"),
            "metrics": result.get("summary_metrics") or {},
            "columns": result.get("columns") or [],
            "rows": result.get("rows") or [],
        }
        artifact_message_id = await save_and_send_artifact(
            session_id=state["session_id"],
            output_type="dataTable",
            title=str(result.get("title") or "过往资料表"),
            data=artifact_data,
            artifact_key=artifact_id,
        )
        result["artifact_id"] = artifact_id
        result["artifact_message_id"] = artifact_message_id

    return Command(
        update={
            "knowledge_export_result": result,
            "current_step": "KNOWLEDGE",
        }
    )
