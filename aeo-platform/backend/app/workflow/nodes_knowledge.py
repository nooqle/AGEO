"""Knowledge Workspace nodes."""

from __future__ import annotations

import hashlib
import json
import logging

from langgraph.types import Command

from app.core.database import AsyncSessionLocal
from app.services.knowledge_workspace_service import KnowledgeWorkspaceService
from app.services.message_service import MessageService
from app.workflow.events import save_and_send_artifact
from app.workflow.fetch_recovery import normalize_question_targets
from app.workflow.state import AgentState

logger = logging.getLogger(__name__)


def _build_fetch_recovery_plan_from_aggregate_result(
    result: dict[str, object] | None,
) -> dict[str, object] | None:
    fetch_status = (result or {}).get("fetch_status_summary") or {}
    if not isinstance(fetch_status, dict):
        return None

    failure_count = int(fetch_status.get("failure_count") or 0)
    question_targets = normalize_question_targets(
        fetch_status.get("failed_question_targets")
    )
    if failure_count <= 0 or not question_targets:
        return None

    platforms = sorted(
        {
            platform
            for target in question_targets
            for platform in target.get("platforms") or []
        }
    )
    return {
        "question_targets": question_targets,
        "platforms": platforms,
        "success_count": int(fetch_status.get("success_count") or 0),
        "failure_count": failure_count,
        "total_count": int(fetch_status.get("total_count") or 0),
        "success_rate": float(fetch_status.get("success_rate") or 0.0),
        "failed_question_count": int(
            fetch_status.get("failed_question_count") or len(question_targets)
        ),
        "failed_platform_count": int(
            fetch_status.get("failed_platform_count") or len(platforms)
        ),
        "platform_breakdown": list(fetch_status.get("platform_breakdown") or []),
        "task_id": str(fetch_status.get("task_id") or "").strip() or None,
        "analysis_label": str(fetch_status.get("analysis_label") or "").strip() or None,
        "source": "knowledge_aggregate",
    }


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


def _should_use_current_import_scope(
    state: AgentState,
    tool_args: dict[str, object],
    query: str,
) -> bool:
    explicit_scope = str(tool_args.get("source_scope") or "").strip().lower()
    if explicit_scope:
        return explicit_scope == "current_import_artifact"

    current_import_artifact = state.get("current_import_artifact") or {}
    artifact_id = str(current_import_artifact.get("artifact_id") or "").strip()
    if not artifact_id:
        return False

    text = str(query or "").strip().lower()
    if not text:
        return False

    upload_keywords = ("上传", "导入", "附件", "表格", "问题列表", "问题内容", "问题")
    history_keywords = ("历史", "过往", "以前", "之前", "历次")
    return any(keyword in text for keyword in upload_keywords) and not any(
        keyword in text for keyword in history_keywords
    )


async def _build_current_import_export_result(
    state: AgentState,
) -> dict[str, object]:
    current_import_artifact = state.get("current_import_artifact") or {}
    artifact_id = str(current_import_artifact.get("artifact_id") or "").strip()
    if not artifact_id:
        return {
            "status": "miss",
            "reason": "missing_current_import_artifact",
            "rows": [],
            "columns": [],
        }

    async with AsyncSessionLocal() as db:
        message_service = MessageService(db)
        output_message = await message_service.get_latest_output_by_artifact_id(
            session_id=state["session_id"],
            artifact_id=artifact_id,
            compact_output=False,
        )

    output_data = output_message.get("output_data") if isinstance(output_message, dict) else None
    if not isinstance(output_data, dict):
        return {
            "status": "miss",
            "reason": "current_import_artifact_not_found",
            "rows": [],
            "columns": [],
        }

    questions = [
        item
        for item in list(output_data.get("questions") or [])
        if isinstance(item, dict) and str(item.get("text") or "").strip()
    ]
    source_file = output_data.get("sourceFile") if isinstance(output_data.get("sourceFile"), dict) else {}
    rows = [
        {
            "seq": index,
            "question_text": str(item.get("text") or "").strip(),
            "category": str(item.get("category") or "上传问题").strip() or "上传问题",
            "source_scope": "当前导入表格",
        }
        for index, item in enumerate(questions, start=1)
    ]
    columns = [
        {"key": "seq", "label": "序号", "sortable": True},
        {"key": "question_text", "label": "问题内容", "sortable": False},
        {"key": "category", "label": "分类", "sortable": True},
        {"key": "source_scope", "label": "来源范围", "sortable": True},
    ]
    file_name = str(source_file.get("name") or "").strip()
    title = f"当前导入问题表（{file_name}）" if file_name else "当前导入问题表"
    description = f"当前导入问题列表共 {len(rows)} 条，结果仅来自本次上传表格。"
    return {
        "status": "hit",
        "title": title,
        "brand_name": (
            (state.get("brand_profile") or {}).get("brand_name")
            or state.get("brand_name")
            or ""
        ),
        "description": description,
        "columns": columns,
        "rows": rows,
        "item_count": len(rows),
        "truncated": False,
        "has_more_records": False,
        "export_limit": len(rows),
        "source_types": ["uploaded_table_question_list"],
        "platforms": [],
        "analysis_period": "当前导入表格",
        "summary_metrics": {
            "导出条数": len(rows),
            "来源类型": 1,
            "覆盖平台数": 0,
            "结果截断": "否",
        },
        "source_scope": "current_import_artifact",
        "artifact_id": artifact_id,
        "artifact_message_id": output_message.get("id") if isinstance(output_message, dict) else None,
    }


def _validate_export_result(
    *,
    result: dict[str, object],
    expected_scope: str,
    expected_row_scope: str,
    require_artifact_binding: bool,
) -> dict[str, object]:
    failures: list[dict[str, str]] = []
    warnings: list[str] = []

    status = str(result.get("status") or "").strip().lower()
    if status != "hit":
        failures.append(
            {
                "type": "missing_result",
                "message": "当前导出结果未命中有效数据，无法通过交付前校验。",
            }
        )
        return {"passed": False, "failures": failures, "warnings": warnings}

    result_scope = str(result.get("source_scope") or "").strip()
    if result_scope != expected_scope:
        failures.append(
            {
                "type": "scope_mismatch",
                "message": f"导出结果作用域不正确，期望 {expected_scope}，实际为 {result_scope or 'unknown'}。",
            }
        )

    columns = result.get("columns") or []
    rows = result.get("rows") or []
    item_count = int(result.get("item_count") or 0)
    artifact_id = str(result.get("artifact_id") or "").strip()

    if not isinstance(columns, list) or not columns:
        failures.append(
            {
                "type": "missing_columns",
                "message": "导出结果缺少结构化列定义，无法稳定渲染和导出。",
            }
        )
        columns = []

    if not isinstance(rows, list):
        failures.append(
            {
                "type": "invalid_rows",
                "message": "导出结果行数据不是列表结构。",
            }
        )
        rows = []

    column_keys = {
        str(column.get("key") or "").strip()
        for column in columns
        if isinstance(column, dict)
    }
    required_columns = {"source_scope"}
    if expected_scope == "current_import_artifact":
        required_columns.update({"seq", "question_text", "category"})
    else:
        required_columns.update(
            {"question_text", "answer_content", "sentiment", "summary", "tags"}
        )
    missing_columns = sorted(key for key in required_columns if key not in column_keys)
    if missing_columns:
        failures.append(
            {
                "type": "missing_required_columns",
                "message": f"导出结果缺少必要列：{', '.join(missing_columns)}。",
            }
        )

    if item_count != len(rows):
        failures.append(
            {
                "type": "item_count_mismatch",
                "message": f"导出结果条数不一致，声明 {item_count} 条，实际 {len(rows)} 条。",
            }
        )

    if require_artifact_binding and not artifact_id:
        failures.append(
            {
                "type": "missing_artifact_binding",
                "message": "导出结果未绑定到正式 artifact/version，不能作为正式交付。",
            }
        )

    for index, row in enumerate(rows[: min(len(rows), 10)], start=1):
        if not isinstance(row, dict):
            failures.append(
                {
                    "type": "invalid_row_shape",
                    "message": f"第 {index} 行不是结构化对象。",
                }
            )
            continue
        row_scope = str(row.get("source_scope") or "").strip()
        if row_scope != expected_row_scope:
            failures.append(
                {
                    "type": "row_scope_mismatch",
                    "message": f"第 {index} 行来源范围错误，期望 {expected_row_scope}，实际为 {row_scope or 'unknown'}。",
                }
            )
        if expected_scope == "current_import_artifact":
            if not str(row.get("question_text") or "").strip():
                failures.append(
                    {
                        "type": "missing_question_text",
                        "message": f"第 {index} 行缺少问题内容。",
                    }
                )
        else:
            legacy_snippet = str(row.get("snippet") or "").strip()
            if legacy_snippet:
                failures.append(
                    {
                        "type": "legacy_snippet_column",
                        "message": "导出结果仍携带旧 snippet 维度，说明结果类型还没有完全规范化。",
                    }
                )
            for field in ("answer_content", "sentiment", "summary", "tags"):
                if field not in row:
                    failures.append(
                        {
                            "type": "missing_typed_field",
                            "message": f"第 {index} 行缺少字段 {field}。",
                        }
                    )

    return {"passed": not failures, "failures": failures, "warnings": warnings}


def _build_export_artifact_key(
    state: AgentState,
    result: dict[str, object],
    tool_args: dict[str, object],
) -> str:
    source_scope = str(result.get("source_scope") or "knowledge_records").strip()
    if source_scope == "knowledge_records":
        return f"{state['session_id']}_knowledge_export_history"

    scope = {
        "brand_name": result.get("brand_name"),
        "query": str(tool_args.get("query") or "").strip(),
        "analysis_period": result.get("analysis_period"),
        "source_scope": source_scope,
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

    recovery_plan = _build_fetch_recovery_plan_from_aggregate_result(result)

    return Command(
        update={
            "knowledge_aggregate_result": result,
            "fetch_recovery_plan": recovery_plan,
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

    if _should_use_current_import_scope(state, tool_args, query):
        result = await _build_current_import_export_result(state)
    else:
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
        result["query"] = query
        validation = _validate_export_result(
            result=result,
            expected_scope=(
                "current_import_artifact"
                if result.get("source_scope") == "current_import_artifact"
                else "knowledge_records"
            ),
            expected_row_scope=(
                "当前导入表格"
                if result.get("source_scope") == "current_import_artifact"
                else "历史资料库"
            ),
            require_artifact_binding=(
                result.get("source_scope") == "current_import_artifact"
            ),
        )
        result["validation"] = validation
        if not validation.get("passed"):
            result = {
                **result,
                "status": "miss",
                "reason": "export_validation_failed",
                "validation": validation,
            }
            return Command(
                update={
                    "knowledge_export_result": result,
                    "current_step": "KNOWLEDGE",
                }
            )

        artifact_id = str(result.get("artifact_id") or "").strip() or _build_export_artifact_key(
            state,
            result,
            {**tool_args, "query": query},
        )
        artifact_data = {
            "artifact_kind": (
                "current_import_export"
                if result.get("source_scope") == "current_import_artifact"
                else "knowledge_export"
            ),
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
            "source_scope": result.get("source_scope") or "knowledge_records",
        }
        artifact_message_id = result.get("artifact_message_id")
        if not artifact_message_id or result.get("source_scope") != "current_import_artifact":
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
