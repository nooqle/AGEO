"""Amway association-circle pipeline nodes (blueprint 3b-1.2).

extract / projection were previously embedded in ``a4_fetch_node``
(``_build_amway_entity_pipeline_update``); they are now standalone LangGraph
nodes so the topology resolver can schedule them independently:

    a4_fetch → amway_extract → amway_projection → a5_analytics

Each hop is gated by its canvas edge (fetch→extract / extract→projection /
projection→report). The execution kernel (extraction/calibration services,
stage-result payloads, snapshot persistence) is moved verbatim — only the
orchestration shell (state in/out + next_required_action) is new.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.types import Command

from app.workflow.events import send_progress_event, send_stage_result
from app.workflow.nodes_a4 import (
    _association_center_terms_from_a4_state,
    _is_association_circle_context,
    _persist_a4_stage_result,
    _persist_amway_calibrated_run_snapshot,
    _uuid_or_none,
)
from app.workflow.runtime_policy_executor import build_next_required_action
from app.workflow.state import AgentState
from app.workflow.topology_resolver import (
    load_flow_topology,
    projection_chain_enabled,
    report_chain_enabled,
)

logger = logging.getLogger(__name__)


async def amway_extract_node(state: AgentState) -> Command:
    """Entity extraction: answers + lexicon → entity signals.

    Input:  state.fetch_results, state.realtime_entity_extraction_result
    Output: state.entity_extraction_result
    Chains: → amway_projection (gated by extract→projection canvas edge)
    """
    session_id = str(state.get("session_id") or "")
    task_id = state.get("task_id")
    fetch_results = list(state.get("fetch_results") or [])

    if not _is_association_circle_context(state) or not fetch_results:
        logger.info(
            "[AmwayExtract] Skipped: association context=%s fetch_results=%d",
            _is_association_circle_context(state),
            len(fetch_results),
        )
        return Command(
            update={
                "entity_extraction_result": None,
                "next_required_action": None,
                "progress_message": "无可用抓取结果，实体抽取未执行。",
            }
        )

    await send_progress_event(
        session_id=session_id,
        step="EXTRACT",
        step_name="实体关系抽取",
        progress=0.68,
        message=f"开始实体关系抽取（{len(fetch_results)} 组问答）",
    )

    from app.services.amway_entity_extraction_service import (
        AmwayEntityExtractionService,
    )

    registry = None
    entity_uuid = _uuid_or_none(state.get("entity_id"))
    if entity_uuid is not None:
        try:
            from app.core.database import AsyncSessionLocal
            from app.services.amway_entity_lexicon_service import (
                AmwayEntityLexiconService,
            )

            async with AsyncSessionLocal() as db:
                registry = await AmwayEntityLexiconService(db).registry_for_entity(
                    entity_uuid
                )
        except Exception as exc:
            logger.warning(
                "[AmwayExtract] Failed to load Amway editable lexicon: %s", exc
            )

    extraction_service = AmwayEntityExtractionService(registry=registry)
    extraction_result = extraction_service.extract_from_fetch_results(fetch_results)

    realtime_extraction_result = state.get("realtime_entity_extraction_result")
    realtime_signal_count = 0
    if isinstance(realtime_extraction_result, dict):
        realtime_signal_count = int(realtime_extraction_result.get("signal_count") or 0)
        extraction_result["realtime_extraction_enabled"] = bool(
            realtime_extraction_result.get("realtime_extraction_enabled")
        )
        extraction_result["realtime_signal_count"] = realtime_signal_count
        extraction_result["realtime_answer_signal_count"] = int(
            realtime_extraction_result.get("answer_signal_count") or 0
        )
        extraction_result["realtime_answer_ids"] = list(
            realtime_extraction_result.get("realtime_answer_ids") or []
        )[:200]

    if realtime_signal_count <= 0:
        for answer_record in extraction_result.get("answer_signals", [])[:160]:
            if not isinstance(answer_record, dict):
                continue
            signals = [
                signal
                for signal in answer_record.get("signals") or []
                if isinstance(signal, dict)
            ]
            if not signals:
                continue
            stage_result_data = {
                "answer_id": answer_record.get("answer_id"),
                "question_id": answer_record.get("question_id"),
                "question": answer_record.get("question"),
                "platform": answer_record.get("platform"),
                "signal_count": len(signals),
                "is_realtime": False,
                "signals": [
                    {
                        "entity_name": signal.get("entity_name"),
                        "entity_type": signal.get("entity_type"),
                        "matched_text": signal.get("matched_text"),
                        "relation_type": signal.get("relation_type"),
                        "term_origin": signal.get("term_origin"),
                        "evidence_text": signal.get("evidence_text"),
                        "answer_position": signal.get("answer_position"),
                    }
                    for signal in signals[:12]
                ],
            }
            await send_stage_result(
                session_id=session_id,
                stage="EntityExtraction",
                stage_name="实体关系抽取",
                result_type="entity_extraction_signal",
                data=stage_result_data,
            )
            await _persist_a4_stage_result(
                state,
                task_id=str(task_id) if task_id else None,
                stage="EntityExtraction",
                stage_name="实体关系抽取",
                result_type="entity_extraction_signal",
                data=stage_result_data,
            )

    flow_topology = await load_flow_topology(state.get("entity_id"))
    update: dict[str, Any] = {
        "entity_extraction_result": extraction_result,
        "current_step": "EXTRACT",
        "progress": 0.72,
    }
    if projection_chain_enabled(flow_topology):
        update["next_required_action"] = build_next_required_action(
            tool_name="amway_circle_projection",
            authority="authoritative_resume",
            reason="实体抽取已完成，继续执行圈层图谱构建。",
            source_step="amway_extract",
            metadata={
                "signal_count": extraction_result.get("signal_count", 0),
                "realtime_signal_count": realtime_signal_count,
            },
        )
        update["progress_message"] = "实体关系抽取完成，正在构建圈层图谱。"
    else:
        update["next_required_action"] = None
        update["progress_message"] = (
            "画布已断开「实体抽取 → 图谱构建」连线，本次运行止于实体抽取。"
        )
    return Command(update=update)


async def amway_projection_node(state: AgentState) -> Command:
    """Circle projection: entity signals → calibrated association circle.

    Input:  state.fetch_results, state.entity_extraction_result
    Output: state.entity_calibration_result, state.association_circle_projection,
            state.brand_association_report_input
    Chains: → a5_analytics (gated by projection→report canvas edge)
    """
    session_id = str(state.get("session_id") or "")
    task_id = state.get("task_id")
    fetch_results = list(state.get("fetch_results") or [])
    extraction_result = state.get("entity_extraction_result")

    if (
        not _is_association_circle_context(state)
        or not fetch_results
        or not extraction_result
    ):
        logger.info(
            "[AmwayProjection] Skipped: fetch_results=%d has_extraction=%s",
            len(fetch_results),
            bool(extraction_result),
        )
        return Command(
            update={
                "entity_calibration_result": None,
                "association_circle_projection": None,
                "brand_association_report_input": None,
                "next_required_action": None,
                "progress_message": "缺少实体抽取结果，圈层图谱构建未执行。",
            }
        )

    await send_progress_event(
        session_id=session_id,
        step="PROJECTION",
        step_name="圈层图谱构建",
        progress=0.76,
        message="开始按样本量校准实体并构建圈层图谱",
    )

    from app.services.amway_entity_calibration_service import (
        AmwayEntityCalibrationService,
    )
    from app.services.amway_entity_extraction_service import (
        AmwayEntityExtractionService,
    )

    registry = None
    entity_uuid = _uuid_or_none(state.get("entity_id"))
    if entity_uuid is not None:
        try:
            from app.core.database import AsyncSessionLocal
            from app.services.amway_entity_lexicon_service import (
                AmwayEntityLexiconService,
            )

            async with AsyncSessionLocal() as db:
                registry = await AmwayEntityLexiconService(db).registry_for_entity(
                    entity_uuid
                )
        except Exception as exc:
            logger.warning(
                "[AmwayProjection] Failed to load Amway editable lexicon: %s", exc
            )

    extraction_service = AmwayEntityExtractionService(registry=registry)
    calibration_service = AmwayEntityCalibrationService(
        extraction_service=extraction_service
    )
    calibration_result = calibration_service.calibrate(
        fetch_results=fetch_results,
        extraction_result=extraction_result,
        center_terms=_association_center_terms_from_a4_state(state),
    )
    projection = calibration_result.get("association_circle_projection")
    sample_scope = calibration_result.get("sample_scope")
    platform_summary = calibration_result.get("platform_summary")
    calibration_stage_data = {
        "node_count": (
            len(projection.get("nodes") or []) if isinstance(projection, dict) else 0
        ),
        "risk_count": (
            calibration_result.get("risk_map", {}).get("risk_count", 0)
            if isinstance(calibration_result.get("risk_map"), dict)
            else 0
        ),
        "signal_count": extraction_result.get("signal_count", 0),
        "sample_scope": sample_scope if isinstance(sample_scope, dict) else {},
        "platform_summary": (
            platform_summary if isinstance(platform_summary, dict) else {}
        ),
        "generated_from": (
            projection.get("generated_from") if isinstance(projection, dict) else None
        ),
    }
    await send_stage_result(
        session_id=session_id,
        stage="EntityCalibration",
        stage_name="实体校准汇总",
        result_type="entity_calibration_summary",
        data=calibration_stage_data,
    )
    await _persist_a4_stage_result(
        state,
        task_id=str(task_id) if task_id else None,
        stage="EntityCalibration",
        stage_name="实体校准汇总",
        result_type="entity_calibration_summary",
        data=calibration_stage_data,
    )
    await _persist_amway_calibrated_run_snapshot(
        state,
        fetch_results=fetch_results,
        extraction_result=extraction_result,
        calibration_result=calibration_result,
    )

    flow_topology = await load_flow_topology(state.get("entity_id"))
    update: dict[str, Any] = {
        "entity_calibration_result": calibration_result,
        "brand_association_report_input": calibration_result.get("report_input"),
        "association_circle_projection": projection,
        "current_step": "PROJECTION",
        "progress": 0.8,
    }
    if report_chain_enabled(flow_topology):
        report_type = (
            "panorama"
            if str(state.get("analysis_mode") or "").strip().lower() == "baseline"
            else "scenario"
        )
        update["next_required_action"] = build_next_required_action(
            tool_name="analysis_report_skill",
            authority="authoritative_resume",
            reason="圈层图谱构建完成，继续执行 A5 生成分析报告。",
            tool_args={"report_type": report_type},
            source_step="amway_projection",
            metadata={"headless_mode": bool(state.get("headless_mode"))},
        )
        update["progress_message"] = "圈层图谱构建完成，正在生成分析报告。"
    else:
        update["next_required_action"] = None
        update["progress_message"] = (
            "画布已断开「图谱构建 → 报告」连线，本次运行止于图谱构建。"
        )
    return Command(update=update)
