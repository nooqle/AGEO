"""Workflow-side confirmation resolution helpers.

This module keeps business selection semantics close to workflow concerns
instead of expanding transport handlers with more branching.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from app.workflow.runtime_policy_executor import build_next_required_action


logger = logging.getLogger(__name__)

_KNOWN_CONFIRMATION_LABELS: dict[str, str] = {
    "panorama_fast": "品牌全景分析（快速模式）",
    "panorama_full": "品牌全景分析（完整模式）",
    "panorama": "品牌全景分析",
    "scenario": "场景细化分析",
    "website": "官网 AI 友好度评估",
    "ask": "直接提问",
    "persona_first": "先做用户画像分析",
    "custom_questions": "我自定义问题",
    "view_questions": "先查看问题内容",
    "still_empty": "问题列表仍未显示",
    "table_import_question_list": "确认导入问题列表",
    "table_import_question_list_merge": "整合导入",
    "table_import_question_list_replace": "替换导入",
    "table_import_brand_info": "更新品牌/竞品信息",
    "table_import_link_list": "作为链接清单继续",
    "table_import_cancel": "暂不导入",
    "run_answer_fetch": "先执行答案抓取",
    "run_supplemental_fetch": "补采上一轮失败项",
    "run_analysis_report": "重新生成分析报告",
    "confirm_question_set_enable_quick": "确认并启用快速监测",
    "append_question_set_questions": "继续补充问题",
    "decline_question_set_enable": "暂不启用",
}

TABLE_IMPORT_QUESTION_LIST_ARTIFACT_KIND = "table_import_question_list"


@dataclass
class ConfirmationResolution:
    """Resolved workflow intent from a user confirmation payload."""

    user_content: str
    user_decisions: dict[str, Any]
    state_updates: dict[str, Any]


def resolve_known_confirmation_label(option_id: str | None) -> str | None:
    normalized = str(option_id or "").strip()
    if not normalized:
        return None
    return _KNOWN_CONFIRMATION_LABELS.get(normalized)


def _build_uploaded_question_items(result: dict[str, Any]) -> list[dict[str, str]]:
    payload = result.get("normalized_payload") or {}
    questions = payload.get("questions") or []
    items: list[dict[str, str]] = []
    for index, item in enumerate(questions, start=1):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        items.append(
            {
                "id": str(item.get("id") or index),
                "text": text,
                "category": str(item.get("category") or "上传问题").strip() or "上传问题",
                "intent": str(item.get("intent") or "").strip(),
                "stage": str(item.get("stage") or "").strip(),
            }
        )
    return items


def build_table_import_question_list_artifact_id(session_id: str) -> str:
    normalized = str(session_id or "").strip()
    return f"{normalized}_tableImportQuestionList"


def resolve_table_import_question_list_artifact_ref(
    *,
    session_id: str,
    result: dict[str, Any] | None = None,
    state_values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifact_ref = None
    if isinstance(result, dict):
        artifact_ref = result.get("artifact_ref")
    if not isinstance(artifact_ref, dict) and isinstance(state_values, dict):
        artifact_ref = (
            (state_values.get("import_source_metadata") or {}).get("current_import_artifact")
            or (state_values.get("table_intake_result") or {}).get("artifact_ref")
        )
    if isinstance(artifact_ref, dict):
        artifact_id = str(artifact_ref.get("artifact_id") or "").strip()
        if artifact_id:
            return {
                "artifact_id": artifact_id,
                "artifact_kind": str(
                    artifact_ref.get("artifact_kind")
                    or TABLE_IMPORT_QUESTION_LIST_ARTIFACT_KIND
                ).strip()
                or TABLE_IMPORT_QUESTION_LIST_ARTIFACT_KIND,
                "output_type": str(artifact_ref.get("output_type") or "questionList"),
                "title": str(artifact_ref.get("title") or "上传问题列表").strip() or "上传问题列表",
                "item_count": int(artifact_ref.get("item_count") or 0),
            }

    return {
        "artifact_id": build_table_import_question_list_artifact_id(session_id),
        "artifact_kind": TABLE_IMPORT_QUESTION_LIST_ARTIFACT_KIND,
        "output_type": "questionList",
        "title": "上传问题列表",
        "item_count": len(_build_uploaded_question_items(result or {})),
    }


def build_table_import_preview(result: dict[str, Any], *, limit: int = 3) -> str:
    source_file = result.get("source_file") or {}
    source_name = str(source_file.get("name") or "当前表格").strip() or "当前表格"
    questions = _build_uploaded_question_items(result)
    if not questions:
        return source_name

    preview_lines = [
        f"{index}. {item['text']}" for index, item in enumerate(questions[:limit], start=1)
    ]
    remaining = len(questions) - len(preview_lines)
    if remaining > 0:
        preview_lines.append(f"...另外还有 {remaining} 条问题")

    return f"{source_name}，共识别到 {len(questions)} 条有效问题：\n" + "\n".join(
        preview_lines
    )


def build_table_import_question_list_artifact(
    result: dict[str, Any],
    *,
    session_id: str,
) -> tuple[str, dict[str, Any]]:
    questions = _build_uploaded_question_items(result)
    source_file = result.get("source_file") or {}
    item_count = len(questions)
    artifact_ref = resolve_table_import_question_list_artifact_ref(
        session_id=session_id,
        result=result,
    )
    return (
        "上传问题列表",
        {
            "artifact_kind": TABLE_IMPORT_QUESTION_LIST_ARTIFACT_KIND,
            "artifact_id": artifact_ref["artifact_id"],
            "questions": questions,
            "generationMode": "上传问题预览",
            "sourceFile": source_file or None,
            "preview_description": f"本次上传共识别到 {item_count} 条问题，请先确认问题内容是否正确。",
            "itemCount": item_count,
            "source_scope": {
                "scope_type": "uploaded_table_question_list",
                "source_file_id": str((source_file or {}).get("file_id") or "").strip() or None,
                "source_file_name": str((source_file or {}).get("name") or "").strip() or None,
                "item_count": item_count,
            },
        },
    )


def build_table_import_confirmation_payload(
    result: dict[str, Any],
    *,
    include_view_option: bool = True,
) -> tuple[str, list[dict[str, str]], str]:
    table_kind = result.get("table_kind")
    if table_kind == "question_list":
        import_intent = (result.get("import_intent") or {}).get("mode")
        preview = build_table_import_preview(result)
        view_option = (
            [
                {
                    "id": "view_questions",
                    "label": "先查看问题内容",
                    "description": "先打开右侧问题列表，确认识别出的上传问题",
                }
            ]
            if include_view_option
            else []
        )
        if import_intent == "unspecified":
            return (
                f"{preview}\n\n当前会话里已经有一版上传问题。请确认这次是整合到上一版，还是替换上一版。",
                [
                    *view_option,
                    {
                        "id": "table_import_question_list_merge",
                        "label": "整合导入",
                        "description": "保留上一版上传问题，并追加本次新问题",
                    },
                    {
                        "id": "table_import_question_list_replace",
                        "label": "替换导入",
                        "description": "放弃上一版上传问题，只保留本次新问题",
                    },
                    {
                        "id": "table_import_cancel",
                        "label": "暂不导入",
                        "description": "保留当前结果，不执行本次导入",
                    },
                ],
                "确认问题列表导入",
            )
        return (
            f"{preview}\n\n是否将这些问题作为 A3 问题列表导入？确认后我会先更新问题列表，再继续后续流程。",
            [
                *view_option,
                {
                    "id": "table_import_question_list",
                    "label": "确认导入问题列表",
                    "description": "先更新 A3 交付物，再继续后续抓取流程",
                },
                {
                    "id": "table_import_cancel",
                    "label": "暂不导入",
                    "description": "保留当前结果，不执行本次导入",
                },
            ],
            "确认问题列表导入",
        )
    if table_kind == "brand_competitor_info":
        return (
            "我已识别到这是一份品牌/竞品信息表。确认后会先更新当前 A1 上下文，再继续后续流程。",
            [
                {
                    "id": "table_import_brand_info",
                    "label": "更新品牌/竞品信息",
                    "description": "先更新 A1 交付物，再回到后续流程",
                },
                {
                    "id": "table_import_cancel",
                    "label": "暂不更新",
                    "description": "保留当前上下文，不执行本次导入",
                },
            ],
            "确认品牌信息导入",
        )
    return (
        "我已识别到这是一份链接清单。确认后会先整理为链接交付物，再继续后续来源分析。",
        [
            {
                "id": "table_import_link_list",
                "label": "作为链接清单继续",
                "description": "先生成链接清单交付物，再继续后续分析",
            },
            {
                "id": "table_import_cancel",
                "label": "暂不继续",
                "description": "保留当前流程，不执行本次导入",
            },
        ],
        "确认链接清单导入",
    )


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
            or import_source_metadata.get("current_import_artifact")
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
        elif opt_id == "panorama_fast":
            clear_question_import_state()
            resolved_user_content = "先做品牌全景分析，并使用快速采集。"
            decisions["a3_mode"] = "baseline_dynamic"
            decisions["fetch_mode_pending"] = False
            decisions["fetch_mode_confirmed"] = True
            state_updates["analysis_mode"] = "baseline"
            state_updates["fetch_mode"] = "fast"
            state_updates["next_required_action"] = build_next_required_action(
                tool_name="question_simulation",
                authority="user_confirmation",
                tool_args={"mode": "baseline_dynamic"},
                reason="用户选择品牌全景分析快速模式。",
                reply_text="好的，我会按品牌全景分析路径继续，并使用快速采集模式。",
                source_step="confirmation",
            )
            logger.info("[LangGraph] Inline confirmation: panorama_fast mode")
        elif opt_id == "panorama_full":
            clear_question_import_state()
            resolved_user_content = "先做品牌全景分析，并使用完整采集。"
            decisions["a3_mode"] = "baseline_dynamic"
            decisions["fetch_mode_pending"] = False
            decisions["fetch_mode_confirmed"] = True
            state_updates["analysis_mode"] = "baseline"
            state_updates["fetch_mode"] = "full"
            state_updates["next_required_action"] = build_next_required_action(
                tool_name="question_simulation",
                authority="user_confirmation",
                tool_args={"mode": "baseline_dynamic"},
                reason="用户选择品牌全景分析完整模式。",
                reply_text="好的，我会按品牌全景分析路径继续，并使用完整采集模式。",
                source_step="confirmation",
            )
            logger.info("[LangGraph] Inline confirmation: panorama_full mode")
        elif opt_id in {"persona_first", "scenario"}:
            clear_question_import_state()
            resolved_user_content = "先做用户画像分析。"
            decisions["a3_mode"] = "persona"
            state_updates["analysis_mode"] = "persona"
            state_updates["next_required_action"] = build_next_required_action(
                tool_name="persona_generation",
                authority="user_confirmation",
                reason="用户选择先做用户画像分析。",
                reply_text="好的，我先生成用户画像，再基于画像继续设计问题。",
                source_step="confirmation",
            )
            logger.info("[LangGraph] Inline confirmation: persona/scenario mode")
        elif opt_id == "custom_questions":
            clear_question_import_state()
            resolved_user_content = "我会自定义问题。"
            logger.info("[LangGraph] Inline confirmation: custom_questions mode")
        elif opt_id in {"brand_panorama", "panorama"}:
            clear_question_import_state()
            resolved_user_content = "先做品牌全景分析吧。"
            decisions["a3_mode"] = "baseline_dynamic"
            state_updates["analysis_mode"] = "baseline"
            state_updates["next_required_action"] = build_next_required_action(
                tool_name="question_simulation",
                authority="user_confirmation",
                tool_args={"mode": "baseline_dynamic"},
                reason="用户选择品牌全景分析。",
                reply_text="好的，我会继续生成品牌全景分析问题。",
                source_step="confirmation",
            )
            logger.info("[LangGraph] Inline confirmation: brand panorama mode")
        elif opt_id == "website":
            clear_question_import_state()
            resolved_user_content = "请评估官网 AI 友好度。"
            state_updates["next_required_action"] = build_next_required_action(
                tool_name="site_confidence_assessment_skill",
                authority="user_confirmation",
                reason="用户选择官网 AI 友好度评估。",
                reply_text="好的，我会继续评估官网在 AI 引用与理解中的友好度。",
                source_step="confirmation",
            )
            logger.info("[LangGraph] Inline confirmation: website assessment mode")
        elif opt_id == "ask":
            clear_question_import_state()
            resolved_user_content = "我想直接提问。"
            logger.info("[LangGraph] Inline confirmation: direct ask mode")
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
            resolved_user_content = str(
                selection.get("label")
                or resolve_known_confirmation_label(opt_id)
                or opt_id
            )
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
        artifact_ref = resolve_table_import_question_list_artifact_ref(
            session_id=str(state_values.get("session_id") or ""),
            result=table_intake_result,
            state_values=state_values,
        )
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
            "artifact_ref": artifact_ref if decisions.get("confirmed_table_kind") == "question_list" else None,
        }
    elif cleared_question_import_state:
        state_updates["confirmed_import_action"] = None

    return ConfirmationResolution(
        user_content=resolved_user_content,
        user_decisions=decisions,
        state_updates=state_updates,
    )
