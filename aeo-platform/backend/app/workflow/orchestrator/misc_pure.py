"""Small pure helpers (P2 knife 4, cautious)."""

from __future__ import annotations

from typing import Any, Mapping

from app.services.skill_registry_service import build_builtin_skill_tool_definitions
from app.workflow.orchestrator.run_context import _get_latest_user_message
from app.workflow.orchestrator.text_normalize import _compact_text

def _normalize_sentiment_followup_value(text: str) -> str | None:
    raw = str(text or "").lower()
    if any(keyword in raw for keyword in ["负向", "负面", "消极", "negative"]):
        return "negative"
    if any(keyword in raw for keyword in ["正向", "正面", "积极", "positive"]):
        return "positive"
    if any(keyword in raw for keyword in ["中性", "neutral"]):
        return "neutral"
    return None

def _format_tool_args_for_suggestion(tool_args: dict[str, Any]) -> str:
    if not tool_args:
        return ""
    args = ", ".join(
        f"{key}={value!r}"
        for key, value in tool_args.items()
        if value is not None and value != ""
    )
    return f"({args})" if args else ""

def _infer_current_import_query(state: Mapping[str, Any]) -> str | None:
    current_import_artifact = state.get("current_import_artifact") or {}
    if not str(current_import_artifact.get("artifact_id") or "").strip():
        return None

    latest_user_message = _get_latest_user_message(state)
    if not latest_user_message:
        return None

    upload_keywords = ("上传", "导入", "附件", "表格", "问题列表", "问题内容", "问题")
    history_keywords = ("历史", "过往", "以前", "之前", "历次")
    if any(keyword in latest_user_message for keyword in upload_keywords) and not any(
        keyword in latest_user_message for keyword in history_keywords
    ):
        return latest_user_message
    return None

def _build_static_public_skill_index() -> str:
    lines: list[str] = []
    for definition in build_builtin_skill_tool_definitions():
        name = str(definition.get("name") or "")
        description = _compact_text(definition.get("description"), 64)
        lines.append(f"- {name}: {description}")
        if len(lines) >= 6:
            break
    return "\n".join(lines)

