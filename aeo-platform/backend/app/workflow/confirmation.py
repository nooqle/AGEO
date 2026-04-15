"""Workflow-side confirmation resolution helpers.

This module keeps business selection semantics close to workflow concerns
instead of expanding transport handlers with more branching.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any


logger = logging.getLogger(__name__)


@dataclass
class ConfirmationResolution:
    """Resolved workflow intent from a user confirmation payload."""

    user_content: str
    user_decisions: dict[str, Any]
    state_updates: dict[str, Any]


def resolve_confirmation_selection(
    *,
    selection: str | dict[str, Any] | None,
    option_id: str,
    user_content: str,
    user_decisions: dict[str, Any],
    state_values: dict[str, Any],
) -> ConfirmationResolution:
    """Map a confirmation payload into workflow-facing state updates.

    The WebSocket transport should only normalize and validate input. The
    workflow semantics of "what does this choice mean" live here.
    """

    decisions = dict(user_decisions)
    state_updates: dict[str, Any] = {}
    resolved_user_content = user_content
    cleared_question_import_state = False

    def clear_question_import_state() -> None:
        nonlocal cleared_question_import_state
        cleared_question_import_state = True
        decisions["table_import_confirmed"] = False
        decisions.pop("confirmed_table_kind", None)
        decisions.pop("question_import_mode", None)
        state_updates["confirmed_import_action"] = None

    def clear_transient_table_import_state() -> None:
        import_source_metadata = dict(state_values.get("import_source_metadata") or {})
        import_source_metadata.pop("attachments", None)
        import_source_metadata.pop("requested_tool_mode", None)
        if import_source_metadata.get("source_type") == "uploaded_table" and not (
            import_source_metadata.get("imported_links")
            or import_source_metadata.get("imported_link_list_count")
        ):
            import_source_metadata.pop("source_type", None)

        state_updates["pending_table_intake"] = None
        state_updates["table_intake_result"] = None
        state_updates["confirmed_import_action"] = None
        state_updates["import_source_metadata"] = import_source_metadata or None
        state_updates["selected_tool_mode"] = None

    if isinstance(selection, dict) and selection.get("type") == "persona_path_selection":
        selected_ids = selection.get("selectedPersonaIds", [])
        selected_names = selection.get("selectedPersonaNames", [])
        clear_question_import_state()
        resolved_user_content = f"我选择了{', '.join(selected_names)}画像，开始出题吧。"
        decisions["a3_mode"] = "persona"
        decisions["selected_persona_ids"] = selected_ids
        decisions["selected_persona_names"] = selected_names
        logger.info(
            "[LangGraph] Persona selection: ids=%s, names=%s",
            selected_ids,
            selected_names,
        )
    elif isinstance(selection, dict) and selection.get("type") == "skip":
        clear_question_import_state()
        resolved_user_content = "跳过画像聚焦，直接生成全景问题吧。"
        decisions["a3_mode"] = "brand"
        logger.info("[LangGraph] User skipped persona selection, using brand mode")
    elif isinstance(selection, dict) and selection.get("optionId"):
        opt_id = str(selection["optionId"])
        if opt_id == "persona_focused":
            clear_question_import_state()
            resolved_user_content = "按我选中的画像开始出题吧。"
            decisions["a3_mode"] = "persona"
            logger.info("[LangGraph] Inline confirmation: persona_focused mode")
        elif opt_id == "brand_panorama":
            clear_question_import_state()
            resolved_user_content = "先做品牌全景分析吧。"
            decisions["a3_mode"] = "brand"
            logger.info("[LangGraph] Inline confirmation: brand_panorama mode")
        elif opt_id == "fast":
            resolved_user_content = "用户选择快速采集"
            decisions["fetch_mode_pending"] = False
            decisions["fetch_mode_confirmed"] = True
            state_updates["fetch_mode"] = "fast"
            logger.info("[LangGraph] Inline confirmation: fast fetch mode")
        elif opt_id == "full":
            resolved_user_content = "用户选择完整采集"
            decisions["fetch_mode_pending"] = False
            decisions["fetch_mode_confirmed"] = True
            state_updates["fetch_mode"] = "full"
            logger.info("[LangGraph] Inline confirmation: full fetch mode")
        elif opt_id == "regenerate":
            resolved_user_content = "用户选择重新生成问题"
            decisions["fetch_mode_pending"] = False
            decisions["fetch_mode_confirmed"] = False
            logger.info("[LangGraph] Inline confirmation: regenerate questions")
        elif opt_id == "table_import_question_list":
            resolved_user_content = "用户确认将表格作为 A3 问题列表导入"
            decisions["table_import_confirmed"] = True
            decisions["confirmed_table_kind"] = "question_list"
            decisions["question_import_mode"] = "replace"
            logger.info("[LangGraph] Inline confirmation: table_import_question_list")
        elif opt_id == "table_import_question_list_merge":
            resolved_user_content = "用户确认将表格整合到上一版 A3 问题列表"
            decisions["table_import_confirmed"] = True
            decisions["confirmed_table_kind"] = "question_list"
            decisions["question_import_mode"] = "merge"
            logger.info(
                "[LangGraph] Inline confirmation: table_import_question_list_merge"
            )
        elif opt_id == "table_import_question_list_replace":
            resolved_user_content = "用户确认用本次表格替换上一版 A3 问题列表"
            decisions["table_import_confirmed"] = True
            decisions["confirmed_table_kind"] = "question_list"
            decisions["question_import_mode"] = "replace"
            logger.info(
                "[LangGraph] Inline confirmation: table_import_question_list_replace"
            )
        elif opt_id == "table_import_brand_info":
            resolved_user_content = "用户确认将表格用于更新品牌/竞品信息"
            decisions["table_import_confirmed"] = True
            decisions["confirmed_table_kind"] = "brand_competitor_info"
            logger.info("[LangGraph] Inline confirmation: table_import_brand_info")
        elif opt_id == "table_import_link_list":
            resolved_user_content = "用户确认将表格作为链接清单继续分析"
            decisions["table_import_confirmed"] = True
            decisions["confirmed_table_kind"] = "link_list"
            logger.info("[LangGraph] Inline confirmation: table_import_link_list")
        elif opt_id == "table_import_cancel":
            clear_question_import_state()
            clear_transient_table_import_state()
            resolved_user_content = "用户选择暂不导入本次表格"
            logger.info("[LangGraph] Inline confirmation: table_import_cancel")
        else:
            resolved_user_content = str(selection.get("label", opt_id))
            logger.info("[LangGraph] Inline confirmation: optionId=%s", opt_id)
    elif isinstance(selection, str) and selection in ("聚焦画像分析", "开始场景细化分析"):
        clear_question_import_state()
        decisions["a3_mode"] = "persona"
        resolved_user_content = "按我选中的画像开始出题吧。"
        logger.info("[LangGraph] Text confirmation mapped to persona mode: %s", selection)
    elif isinstance(selection, str) and selection in ("品牌全景分析",):
        clear_question_import_state()
        decisions["a3_mode"] = "brand"
        resolved_user_content = "先做品牌全景分析吧。"
        logger.info("[LangGraph] Text confirmation mapped to brand mode: %s", selection)
    elif isinstance(selection, str) and selection in ("快速采集（推荐）", "快速采集"):
        decisions["fetch_mode_pending"] = False
        decisions["fetch_mode_confirmed"] = True
        state_updates["fetch_mode"] = "fast"
        resolved_user_content = "用户选择快速采集"
        logger.info("[LangGraph] Text confirmation mapped to fast mode: %s", selection)
    elif isinstance(selection, str) and selection in ("完整采集", "完整采集（全浏览器）"):
        decisions["fetch_mode_pending"] = False
        decisions["fetch_mode_confirmed"] = True
        state_updates["fetch_mode"] = "full"
        resolved_user_content = "用户选择完整采集"
        logger.info("[LangGraph] Text confirmation mapped to full mode: %s", selection)
    elif isinstance(selection, str) and selection in ("重新生成问题",):
        decisions["fetch_mode_pending"] = False
        decisions["fetch_mode_confirmed"] = False
        resolved_user_content = "用户选择重新生成问题"
        logger.info("[LangGraph] Text confirmation mapped to regenerate: %s", selection)
    elif isinstance(selection, str) and selection in ("作为 A3 问题列表导入", "确认导入问题列表"):
        decisions["table_import_confirmed"] = True
        decisions["confirmed_table_kind"] = "question_list"
        decisions["question_import_mode"] = "replace"
        resolved_user_content = "用户确认将表格作为 A3 问题列表导入"
        logger.info(
            "[LangGraph] Text confirmation mapped to question_list import: %s",
            selection,
        )
    elif isinstance(selection, str) and selection in ("整合导入", "整合到上一版", "追加到上一版"):
        decisions["table_import_confirmed"] = True
        decisions["confirmed_table_kind"] = "question_list"
        decisions["question_import_mode"] = "merge"
        resolved_user_content = "用户确认将表格整合到上一版 A3 问题列表"
        logger.info(
            "[LangGraph] Text confirmation mapped to merge question import: %s",
            selection,
        )
    elif isinstance(selection, str) and selection in ("替换导入", "替换上一版", "只保留这次上传"):
        decisions["table_import_confirmed"] = True
        decisions["confirmed_table_kind"] = "question_list"
        decisions["question_import_mode"] = "replace"
        resolved_user_content = "用户确认用本次表格替换上一版 A3 问题列表"
        logger.info(
            "[LangGraph] Text confirmation mapped to replace question import: %s",
            selection,
        )
    elif isinstance(selection, str) and selection in ("更新品牌/竞品信息", "确认更新品牌信息"):
        decisions["table_import_confirmed"] = True
        decisions["confirmed_table_kind"] = "brand_competitor_info"
        resolved_user_content = "用户确认将表格用于更新品牌/竞品信息"
        logger.info(
            "[LangGraph] Text confirmation mapped to brand_competitor_info import: %s",
            selection,
        )
    elif isinstance(selection, str) and selection in ("作为链接清单继续", "确认使用链接清单"):
        decisions["table_import_confirmed"] = True
        decisions["confirmed_table_kind"] = "link_list"
        resolved_user_content = "用户确认将表格作为链接清单继续分析"
        logger.info(
            "[LangGraph] Text confirmation mapped to link_list import: %s",
            selection,
        )
    elif isinstance(selection, str) and selection in ("暂不导入", "取消导入", "先不导入"):
        clear_question_import_state()
        clear_transient_table_import_state()
        resolved_user_content = "用户选择暂不导入本次表格"
        logger.info(
            "[LangGraph] Text confirmation mapped to table_import_cancel: %s",
            selection,
        )

    if decisions.get("table_import_confirmed"):
        table_intake_result = state_values.get("table_intake_result") or {}
        import_intent = table_intake_result.get("import_intent") or {}
        state_updates["confirmed_import_action"] = {
            "table_kind": decisions.get("confirmed_table_kind"),
            "target_step": {
                "question_list": "A3",
                "brand_competitor_info": "A1",
                "link_list": "CONFIDENCE_EVAL",
            }.get(decisions.get("confirmed_table_kind"), "UNKNOWN"),
            "source_file_id": (
                (table_intake_result.get("source_file") or {}).get("file_id")
            ),
            "import_mode": decisions.get("question_import_mode")
            or import_intent.get("mode")
            or "replace",
            "resume_from": {
                "question_list": "A3",
                "brand_competitor_info": "A1",
                "link_list": "CONFIDENCE_EVAL",
            }.get(decisions.get("confirmed_table_kind"), "UNKNOWN"),
            "artifact_type": {
                "question_list": "questionList",
                "brand_competitor_info": "brandProfile",
                "link_list": "linkList",
            }.get(decisions.get("confirmed_table_kind"), "unknown"),
        }
    elif cleared_question_import_state:
        state_updates["confirmed_import_action"] = None

    return ConfirmationResolution(
        user_content=resolved_user_content,
        user_decisions=decisions,
        state_updates=state_updates,
    )
