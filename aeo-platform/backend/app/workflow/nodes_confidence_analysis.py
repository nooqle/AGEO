"""Confidence analysis executor node.

This node evaluates citation/source confidence without re-fetching data.
It can consume existing fetch results, imported link lists, or raw user input.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from langgraph.types import Command

from app.workflow.confidence_analysis import (
    build_manual_items_from_link_rows_async,
    build_manual_items_from_raw_input_async,
    generate_confidence_analysis_artifact,
)
from app.workflow.events import send_error_event, send_progress_event
from app.workflow.skill_fact_snapshot import build_skill_fact_snapshot
from app.workflow.skill_state import build_skill_result_update
from app.workflow.state import AgentState

logger = logging.getLogger(__name__)


async def confidence_analysis_executor_node(state: AgentState) -> Command:
    """Generate a confidence-analysis artifact from the best available source."""
    session_id = state["session_id"]
    facts = build_skill_fact_snapshot(state)
    fetch_results = facts.confidence_fetch_results
    tool_args = dict(state.get("tool_call_args") or {})
    source_mode = str(tool_args.get("source_mode") or "auto").strip() or "auto"
    raw_input = str(tool_args.get("raw_input") or "").strip()
    imported_links = list(
        ((state.get("import_source_metadata") or {}).get("imported_links")) or []
    )
    manual_items: list[dict[str, Any]] = []
    material_summary: dict[str, Any] = {"source_mode": source_mode}

    try:
        if source_mode == "raw_input":
            manual_items = await build_manual_items_from_raw_input_async(raw_input)
            fetch_results = []
            material_summary["raw_input_length"] = len(raw_input)
        elif source_mode == "imported_link_list":
            manual_items = await build_manual_items_from_link_rows_async(imported_links)
            fetch_results = []
            material_summary["imported_link_count"] = len(manual_items)
        elif source_mode == "current_fetch_results":
            material_summary["fetch_result_count"] = len(fetch_results or [])
        else:
            if raw_input:
                manual_items = await build_manual_items_from_raw_input_async(raw_input)
                fetch_results = []
                material_summary["source_mode"] = "raw_input"
                material_summary["raw_input_length"] = len(raw_input)
            elif fetch_results:
                material_summary["source_mode"] = "current_fetch_results"
                material_summary["fetch_result_count"] = len(fetch_results)
            elif imported_links:
                manual_items = await build_manual_items_from_link_rows_async(imported_links)
                fetch_results = []
                material_summary["source_mode"] = "imported_link_list"
                material_summary["imported_link_count"] = len(manual_items)
    except ValueError as exc:
        message = str(exc)
        await send_error_event(session_id, "A7", message, recoverable=True)
        return Command(
            update={
                "error_info": {
                    "step": "A7",
                    "error": message,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }
        )

    if not fetch_results and not manual_items:
        message = (
            "当前还没有可评估的材料。请提供链接、文本，导入链接清单，"
            "或先完成答案抓取/分析报告生成。"
        )
        await send_error_event(session_id, "A7", message, recoverable=True)
        return Command(
            update={
                "error_info": {
                    "step": "A7",
                    "error": message,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }
        )

    try:
        await send_progress_event(
            session_id=session_id,
            step="confidence_analysis_skill",
            step_name="引用内容置信度评估",
            progress=0.96,
            message="正在评估引用来源的可信度与结构化质量...",
        )

        await generate_confidence_analysis_artifact(
            session_id=session_id,
            fetch_results=fetch_results,
            manual_items=manual_items,
            brand_profile=facts.brand_profile,
            competitors=facts.competitors,
        )

        await send_progress_event(
            session_id=session_id,
            step="confidence_analysis_skill",
            step_name="引用内容置信度评估",
            progress=1.0,
            message="引用内容置信度评估已完成",
            status="completed",
        )

        return Command(
            update={
                "error_info": None,
                "progress": 1.0,
                **build_skill_result_update(
                    state,
                    skill_key=state.get("current_skill"),
                    tool_name="confidence_analysis_skill",
                    status="completed",
                    summary="引用置信度分析已完成，结果已写入画布 artifact。",
                    executor_ref="confidence_analysis_executor",
                    metadata=material_summary,
                ),
            }
        )
    except Exception as exc:
        logger.exception("[ConfidenceAnalysis] Artifact generation failed: %s", exc)
        await send_error_event(session_id, "A7", str(exc), recoverable=True)
        return Command(
            update={
                "error_info": {
                    "step": "A7",
                    "error": str(exc),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }
        )
