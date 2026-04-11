"""A7 Node: Citation confidence analysis.

This node turns existing A4 fetch results into a confidence-signal artifact.
It does not re-fetch data and is intended to run only after A4/A5 are complete.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from langgraph.types import Command

from app.workflow.confidence_analysis import (
    generate_confidence_analysis_artifact as generate_confidence_signal_artifact,
)
from app.workflow.events import send_error_event, send_progress_event
from app.workflow.harness_validation import (
    build_harness_decision,
    evaluate_skill_postconditions,
    evaluate_skill_preconditions,
    validate_artifact_writeback,
)
from app.workflow.skill_fact_snapshot import build_skill_fact_snapshot
from app.workflow.skill_state import (
    build_harness_decision_update,
    build_skill_result_update,
    build_validation_result_update,
)
from app.workflow.state import AgentState

logger = logging.getLogger(__name__)


async def a7_confidence_signal_node(state: AgentState) -> Command:
    """Generate a confidence-signal artifact from existing fetch results."""
    session_id = state["session_id"]
    facts = build_skill_fact_snapshot(state)
    fetch_results = facts.confidence_fetch_results
    precondition_result = evaluate_skill_preconditions(
        state, state.get("current_skill_contract")
    )

    if not precondition_result.passed:
        message = f"A7 前置条件未满足：{precondition_result.reason}"
        await send_error_event(session_id, "A7", message, recoverable=True)
        validation_update = build_validation_result_update(state, precondition_result)
        decision_update = build_harness_decision_update(
            {**state, **validation_update},
            build_harness_decision(
                decision_type="fail_step",
                reason=message,
                recoverable=True,
                metadata={"step": "A7", "gate": "precondition_gate"},
            ),
        )
        return Command(
            update={
                "error_info": {
                    "step": "A7",
                    "error": message,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                "current_step": "A7",
                "execution_status": "error",
                **validation_update,
                **decision_update,
            }
        )

    if not fetch_results:
        message = "当前会话中还没有可评估的引用数据，请先完成答案抓取或分析报告生成。"
        await send_error_event(session_id, "A7", message, recoverable=True)
        decision_update = build_harness_decision_update(
            state,
            build_harness_decision(
                decision_type="fail_step",
                reason=message,
                recoverable=True,
                metadata={"step": "A7", "gate": "data_presence_gate"},
            ),
        )
        return Command(
            update={
                "error_info": {
                    "step": "A7",
                    "error": message,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                "current_step": "A7",
                "execution_status": "error",
                **decision_update,
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

        artifact_result = await generate_confidence_signal_artifact(
            session_id=session_id,
            fetch_results=fetch_results,
            brand_profile=facts.brand_profile,
            competitors=facts.competitors,
        )
        artifact_validation = validate_artifact_writeback(
            gate_name="artifact_writeback_gate",
            artifact_message_id=artifact_result.get("artifact_message_id"),
            artifact_key=artifact_result.get("artifact_key"),
            artifact_kind=artifact_result.get("artifact_kind", "confidence_signal"),
            metadata={"fetch_result_count": len(fetch_results)},
        )
        if not artifact_validation.passed:
            raise RuntimeError(artifact_validation.reason)

        await send_progress_event(
            session_id=session_id,
            step="citation_confidence_analysis",
            step_name="引用内容置信度评估",
            progress=1.0,
            message="引用内容置信度评估已完成",
            status="completed",
        )

        skill_update = build_skill_result_update(
            state,
            skill_key=state.get("current_skill"),
            tool_name="confidence_signal_skill",
            status="completed",
            summary="引用置信度 Skill 已完成，结果已写入画布 artifact。",
            executor_ref="a7_confidence_signal",
            metadata={"fetch_result_count": len(fetch_results)},
        )
        artifact_validation_update = build_validation_result_update(state, artifact_validation)
        validation_state = {**state, **skill_update, **artifact_validation_update}
        postcondition_result = evaluate_skill_postconditions(
            state=state,
            contract_payload=state.get("current_skill_contract"),
            pending_update=skill_update,
            artifact_validation=artifact_validation,
        )
        if not postcondition_result.passed:
            raise RuntimeError(postcondition_result.reason)
        postcondition_validation_update = build_validation_result_update(
            validation_state,
            postcondition_result,
        )
        decision_update = build_harness_decision_update(
            {**validation_state, **postcondition_validation_update},
            build_harness_decision(
                decision_type="complete_skill",
                reason="A7 harness gates passed.",
                recoverable=False,
                metadata={"step": "A7", "fetch_result_count": len(fetch_results)},
            ),
        )
        return Command(
            update={
                "error_info": None,
                "progress": 1.0,
                "confidence_signal_summary": artifact_result.get(
                    "confidence_signal_summary"
                ),
                **skill_update,
                **artifact_validation_update,
                **postcondition_validation_update,
                **decision_update,
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
                "current_step": "A7",
                "execution_status": "error",
                **build_harness_decision_update(
                    state,
                    build_harness_decision(
                        decision_type="retry_step",
                        reason=str(exc),
                        recoverable=True,
                        metadata={"step": "A7"},
                    ),
                ),
            }
        )
