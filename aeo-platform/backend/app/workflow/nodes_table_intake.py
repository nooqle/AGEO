"""Table intake node for uploaded CSV/XLSX understanding."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from langgraph.types import Command

from app.core.database import AsyncSessionLocal
from app.services.table_intake_service import TableIntakeService
from app.workflow.events import send_error_event, send_progress_event
from app.workflow.skill_state import build_skill_result_update
from app.workflow.state import AgentState

logger = logging.getLogger(__name__)


def _get_existing_uploaded_questions(state: AgentState) -> list[dict[str, Any]]:
    existing_questions = []
    for item in list(state.get("questions") or []):
        if not isinstance(item, dict):
            continue
        if item.get("source") != "uploaded_table":
            continue
        if not str(item.get("text") or "").strip():
            continue
        existing_questions.append(item)
    return existing_questions


def _infer_question_import_mode(
    user_message: str,
    *,
    existing_question_count: int,
) -> str:
    if existing_question_count <= 0:
        return "create"

    normalized = (user_message or "").strip().lower()
    if not normalized:
        return "unspecified"

    merge_keywords = (
        "加到",
        "追加",
        "整合",
        "合并",
        "一起",
        "并到",
        "merge",
        "combine",
        "append",
    )
    replace_keywords = (
        "替换",
        "覆盖",
        "抛弃",
        "不要上一个",
        "不用上一个",
        "只保留这个",
        "只用这个",
        "replace",
        "overwrite",
    )

    if any(keyword in normalized for keyword in merge_keywords):
        return "merge"
    if any(keyword in normalized for keyword in replace_keywords):
        return "replace"
    return "unspecified"


def _augment_question_list_intent(
    *,
    state: AgentState,
    user_message: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    normalized_payload = dict(result.get("normalized_payload") or {})
    incoming_questions = list(normalized_payload.get("questions") or [])
    existing_questions = _get_existing_uploaded_questions(state)
    existing_count = len(existing_questions)
    import_mode = _infer_question_import_mode(
        user_message,
        existing_question_count=existing_count,
    )

    warnings = list(result.get("warnings") or [])
    summary = str(result.get("summary") or "表格理解完成。")

    if existing_count > 0:
        if import_mode == "merge":
            summary = (
                f"{summary} 检测到会话里已有 {existing_count} 条上传问题，"
                "本次将按整合导入理解。"
            )
        elif import_mode == "replace":
            summary = (
                f"{summary} 检测到会话里已有 {existing_count} 条上传问题，"
                "本次将按替换导入理解。"
            )
        else:
            warning = (
                f"检测到会话里已有 {existing_count} 条上传问题，请确认本次是整合还是替换。"
            )
            if warning not in warnings:
                warnings.append(warning)
            summary = f"{summary} {warning}"

    return {
        **result,
        "warnings": warnings,
        "summary": summary,
        "import_intent": {
            "mode": import_mode,
            "has_existing_uploaded_questions": existing_count > 0,
            "existing_question_count": existing_count,
            "incoming_question_count": len(incoming_questions),
        },
    }


def _build_unknown_result(
    *,
    attachments: list[dict[str, Any]],
    warning: str,
) -> dict[str, Any]:
    attachment = attachments[0] if attachments else {}
    return {
        "table_kind": "unknown",
        "confidence": 0.2,
        "recommended_step": "UNKNOWN",
        "detected_columns": {},
        "normalized_payload": {},
        "warnings": [warning],
        "needs_user_confirmation": True,
        "source_file": {
            "file_id": attachment.get("file_id"),
            "name": attachment.get("name"),
            "mime_type": attachment.get("mime_type"),
            "sheet_name": attachment.get("sheet_hint"),
        },
        "stats": {
            "row_count": 0,
            "valid_row_count": 0,
            "duplicate_row_count": 0,
            "empty_row_count": 0,
        },
        "summary": warning,
    }


async def table_intake_node(state: AgentState) -> Command:
    """Understand a table attachment and return a structured intake result."""

    session_id = state["session_id"]
    intake = dict(state.get("pending_table_intake") or {})
    attachments = list(intake.get("attachments") or [])
    user_message = str(intake.get("user_message") or "")
    import_source_metadata = dict(state.get("import_source_metadata") or {})

    if not attachments:
        message = "当前没有可解析的表格附件。"
        await send_error_event(session_id, "TABLE_INTAKE", message, recoverable=True)
        return Command(
            update={
                "error_info": {
                    "step": "TABLE_INTAKE",
                    "error": message,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            }
        )

    if len(attachments) > 1:
        result = _build_unknown_result(
            attachments=attachments,
            warning="当前一次只支持导入 1 个表格，请保留一个文件后继续。",
        )
        return Command(
            update={
                "table_intake_result": result,
                "error_info": None,
                **build_skill_result_update(
                    state,
                    skill_key=state.get("current_skill"),
                    tool_name="table_intake_skill",
                    status="completed",
                    summary=result["summary"],
                    executor_ref="table_intake_executor",
                    metadata={"table_kind": "unknown", "attachment_count": len(attachments)},
                ),
            }
        )

    try:
        await send_progress_event(
            session_id=session_id,
            step="table_intake_skill",
            step_name="表格导入理解",
            progress=0.15,
            message="正在理解上传的表格内容...",
        )
        async with AsyncSessionLocal() as db:
            service = TableIntakeService(db)
            result = await service.analyze_attachment(
                attachment=attachments[0],
                user_message=user_message,
                brand_context={
                    "brand_name": state.get("brand_name"),
                    "industry": state.get("industry_hint"),
                    "brand_profile": state.get("brand_profile"),
                },
            )
            if result.get("table_kind") == "question_list":
                result = _augment_question_list_intent(
                    state=state,
                    user_message=user_message,
                    result=result,
                )

        await send_progress_event(
            session_id=session_id,
            step="table_intake_skill",
            step_name="表格导入理解",
            progress=1.0,
            message=result.get("summary", "表格理解完成"),
            status="completed",
        )

        import_source_metadata.update(
            {
                "source_type": "uploaded_table",
                "source_file": result.get("source_file"),
                "import_intent": result.get("import_intent"),
            }
        )

        return Command(
            update={
                "table_intake_result": result,
                "import_source_metadata": import_source_metadata,
                "error_info": None,
                **build_skill_result_update(
                    state,
                    skill_key=state.get("current_skill"),
                    tool_name="table_intake_skill",
                    status="completed",
                    summary=result.get("summary", "表格理解完成"),
                    executor_ref="table_intake_executor",
                    metadata={
                        "table_kind": result.get("table_kind"),
                        "recommended_step": result.get("recommended_step"),
                    },
                ),
            }
        )
    except Exception as exc:
        logger.exception("[TableIntake] Failed: %s", exc)
        message = str(exc)
        await send_error_event(session_id, "TABLE_INTAKE", message, recoverable=True)
        return Command(
            update={
                "error_info": {
                    "step": "TABLE_INTAKE",
                    "error": message,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            }
        )
