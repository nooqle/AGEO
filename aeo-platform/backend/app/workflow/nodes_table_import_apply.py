"""Apply confirmed table imports by producing artifacts first, then resuming flow."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from langgraph.types import Command

from app.core.database import AsyncSessionLocal
from app.workflow.events import (
    save_and_send_artifact,
    send_error_event,
    send_progress_event,
    send_stage_result,
)
from app.workflow.state import AgentState

logger = logging.getLogger(__name__)


def _uuid_or_none(value: object):
    try:
        from uuid import UUID

        return UUID(str(value)) if value else None
    except (TypeError, ValueError):
        return None


async def _record_table_import_apply_action(
    state: AgentState,
    *,
    table_kind: str,
    intake_result: dict[str, Any],
    output_payload: dict[str, Any],
) -> None:
    entity_uuid = _uuid_or_none(state.get("entity_id"))
    if entity_uuid is None:
        return
    try:
        from app.services.brand_action_service import BrandActionService

        async with AsyncSessionLocal() as db:
            action_service = BrandActionService(db)
            await action_service.record_applied_action(
                entity_id=entity_uuid,
                session_id=_uuid_or_none(state.get("session_id")),
                user_id=_uuid_or_none(state.get("user_id")),
                parent_action_record_id=_uuid_or_none(
                    state.get("latest_user_action_record_id")
                ),
                action_type="apply_table_import",
                actor_type="system",
                origin_surface="workflow_node",
                origin_event_id=str(state.get("run_id") or "") or None,
                input_payload=_table_import_action_input_payload(
                    state=state,
                    table_kind=table_kind,
                    intake_result=intake_result,
                ),
                output_payload=output_payload,
            )
            await db.commit()
    except Exception as exc:
        logger.warning("[TableImportApply] Failed to record ontology action: %s", exc)


def _table_import_action_input_payload(
    *,
    state: AgentState,
    table_kind: str,
    intake_result: dict[str, Any],
) -> dict[str, Any]:
    normalized_payload = dict(intake_result.get("normalized_payload") or {})
    detected_columns = dict(intake_result.get("detected_columns") or {})
    rows = (
        normalized_payload.get("rows")
        or normalized_payload.get("competitors")
        or normalized_payload.get("questions")
        or normalized_payload.get("links")
        or []
    )
    mapping = detected_columns or {"table_kind": table_kind}
    return {
        "actor_id": str(state.get("user_id") or "") or None,
        "mapping": mapping,
        "rows": rows,
        "table_kind": table_kind,
        "source": "confirmed_table_import",
    }


async def table_import_apply_node(state: AgentState) -> Command:
    session_id = state["session_id"]
    action = dict(state.get("confirmed_import_action") or {})
    result = dict(state.get("table_intake_result") or {})
    table_kind = action.get("table_kind") or result.get("table_kind")

    if not table_kind:
        message = "当前没有待应用的表格导入动作。"
        await send_error_event(session_id, "TABLE_IMPORT_APPLY", message, recoverable=True)
        return Command(
            update={
                "error_info": {
                    "step": "TABLE_IMPORT_APPLY",
                    "error": message,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            }
        )

    try:
        if table_kind == "brand_competitor_info":
            return await _apply_brand_competitor_import(state, result)
        if table_kind == "link_list":
            return await _apply_link_list_import(state, result)
        return Command(update={"confirmed_import_action": None})
    except Exception as exc:
        logger.exception("[TableImportApply] Failed for %s: %s", table_kind, exc)
        await send_error_event(session_id, "TABLE_IMPORT_APPLY", str(exc), recoverable=True)
        return Command(
            update={
                "error_info": {
                    "step": "TABLE_IMPORT_APPLY",
                    "error": str(exc),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            }
        )


async def _apply_brand_competitor_import(
    state: AgentState,
    result: dict[str, Any],
) -> Command:
    session_id = state["session_id"]
    normalized = dict(result.get("normalized_payload") or {})
    brand_profile_patch = dict(normalized.get("brand_profile_patch") or {})
    imported_competitors = list(normalized.get("competitors") or [])

    current_brand_profile = dict(state.get("brand_profile") or {})
    merged_brand_profile = {**current_brand_profile, **brand_profile_patch}
    merged_competitors = imported_competitors or list(state.get("competitors") or [])

    await send_progress_event(
        session_id=session_id,
        step="table_import_apply",
        step_name="应用品牌表格导入",
        progress=0.7,
        message="正在更新品牌/竞品交付物...",
    )

    await save_and_send_artifact(
        session_id=session_id,
        output_type="workflow",
        title="品牌档案",
        data={
            "artifact_kind": "brand_competitor_import",
            "brandProfile": merged_brand_profile,
            "brand_profile": merged_brand_profile,
            "competitors": merged_competitors,
            "competitive_landscape": state.get("competitive_landscape"),
            "currentStep": "A1",
            "executionStatus": "completed",
            "completedSteps": ["A1"],
            "description": "已根据上传表格更新品牌/竞品信息。",
        },
    )

    await send_stage_result(
        session_id,
        "A1",
        "品牌信息导入",
        result_type="brand_profile",
        data={
            "brand_name": merged_brand_profile.get("brand_name", ""),
            "industry": merged_brand_profile.get("industry", ""),
            "competitors": [c.get("name", "") for c in merged_competitors[:5]],
            "source": "uploaded_table",
        },
    )

    try:
        if state.get("entity_id"):
            from app.services.knowledge_workspace_service import (
                KnowledgeWorkspaceService,
            )

            async with AsyncSessionLocal() as db:
                knowledge_service = KnowledgeWorkspaceService(db)
                await knowledge_service.ingest_a1_facts(
                    entity_id=state.get("entity_id"),
                    session_id=session_id,
                    task_id=state.get("task_id"),
                    run_id=state.get("run_id"),
                    brand_profile=merged_brand_profile,
                    competitors=merged_competitors,
                )
    except Exception as knowledge_err:
        logger.warning(
            "[TableImportApply] Failed to write imported A1 facts to knowledge workspace: %s",
            knowledge_err,
        )

    user_decisions = dict(state.get("user_decisions", {}))
    user_decisions["table_import_confirmed"] = False
    user_decisions.pop("confirmed_table_kind", None)

    await send_progress_event(
        session_id=session_id,
        step="table_import_apply",
        step_name="应用品牌表格导入",
        progress=1.0,
        message="品牌/竞品交付物已更新",
        status="completed",
    )
    await _record_table_import_apply_action(
        state,
        table_kind="brand_competitor_info",
        intake_result=result,
        output_payload={
            "brand_profile_fields": sorted(brand_profile_patch.keys()),
            "competitor_count": len(merged_competitors),
        },
    )

    return Command(
        update={
            "brand_profile": merged_brand_profile,
            "competitors": merged_competitors,
            "brand_name": merged_brand_profile.get("brand_name") or state.get("brand_name"),
            "official_website": merged_brand_profile.get("official_website")
            or state.get("official_website"),
            "industry_hint": merged_brand_profile.get("industry")
            or state.get("industry_hint"),
            "current_step": "A1",
            "confirmed_import_action": None,
            "error_info": None,
            "user_decisions": user_decisions,
        }
    )


async def _apply_link_list_import(
    state: AgentState,
    result: dict[str, Any],
) -> Command:
    session_id = state["session_id"]
    normalized = dict(result.get("normalized_payload") or {})
    links = list(normalized.get("links") or [])

    await send_progress_event(
        session_id=session_id,
        step="table_import_apply",
        step_name="应用链接清单导入",
        progress=0.7,
        message="正在生成链接清单交付物...",
    )

    rows = [
        {
            "id": item.get("id"),
            "url": item.get("url"),
            "label": item.get("label") or "",
        }
        for item in links
    ]
    await save_and_send_artifact(
        session_id=session_id,
        output_type="dataTable",
        title="链接清单",
        data={
            "artifact_kind": "source_link_list",
            "export_title": "链接清单",
            "description": "已根据上传表格整理来源/链接清单。",
            "columns": [
                {"key": "url", "label": "链接"},
                {"key": "label", "label": "备注"},
            ],
            "rows": rows,
        },
    )

    await send_stage_result(
        session_id,
        "A7",
        "链接清单导入",
        result_type="link_list",
        data={
            "count": len(rows),
            "examples": [row.get("url", "") for row in rows[:3]],
            "source": "uploaded_table",
        },
    )

    import_source_metadata = dict(state.get("import_source_metadata") or {})
    import_source_metadata["imported_link_list_count"] = len(rows)
    import_source_metadata["imported_links"] = rows
    import_source_metadata.pop("requested_tool_mode", None)
    next_required_action = None

    user_decisions = dict(state.get("user_decisions", {}))
    user_decisions["table_import_confirmed"] = False
    user_decisions.pop("confirmed_table_kind", None)

    await send_progress_event(
        session_id=session_id,
        step="table_import_apply",
        step_name="应用链接清单导入",
        progress=1.0,
        message=f"链接清单交付物已更新，共 {len(rows)} 条",
        status="completed",
    )
    await _record_table_import_apply_action(
        state,
        table_kind="link_list",
        intake_result=result,
        output_payload={"link_count": len(rows)},
    )

    return Command(
        update={
            "import_source_metadata": import_source_metadata,
            "current_step": "A7",
            "confirmed_import_action": None,
            "error_info": None,
            "next_required_action": next_required_action,
            "selected_tool_mode": None,
            "user_decisions": user_decisions,
        }
    )
