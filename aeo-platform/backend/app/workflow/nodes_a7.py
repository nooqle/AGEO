"""A7 Node: Citation confidence analysis.

This node turns existing A4 fetch results into a confidence-signal artifact.
It does not re-fetch data and is intended to run only after A4/A5 are complete.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from langgraph.types import Command

from app.workflow.a7.confidence_signal import generate_confidence_signal_artifact
from app.workflow.events import send_error_event, send_progress_event
from app.workflow.state import AgentState

logger = logging.getLogger(__name__)


async def a7_confidence_signal_node(state: AgentState) -> Command:
    """Generate a confidence-signal artifact from existing fetch results."""
    session_id = state["session_id"]
    fetch_results = state.get("fetch_results") or state.get("baseline_fetch_results") or []

    if not fetch_results:
        message = "当前会话中还没有可评估的引用数据，请先完成答案抓取或分析报告生成。"
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
            step="citation_confidence_analysis",
            step_name="引用内容置信度评估",
            progress=0.96,
            message="正在评估引用来源的可信度与结构化质量...",
        )

        await generate_confidence_signal_artifact(
            session_id=session_id,
            fetch_results=fetch_results,
            brand_profile=state.get("brand_profile"),
            competitors=state.get("competitors"),
        )

        await send_progress_event(
            session_id=session_id,
            step="citation_confidence_analysis",
            step_name="引用内容置信度评估",
            progress=1.0,
            message="引用内容置信度评估已完成",
            status="completed",
        )

        return Command(
            update={
                "error_info": None,
                "progress": 1.0,
            }
        )
    except Exception as exc:
        logger.exception("[A7] Confidence signal generation failed: %s", exc)
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
