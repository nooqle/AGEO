"""WebSocket event handling for LangGraph workflow.

This module handles sending events to the frontend during workflow execution.
New event system: reply_delta, plan_update, action_log, thought_delta, inline_confirmation.
Legacy events (send_output_ready, send_execution_complete, send_error_event) are preserved.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.core.websocket_server import manager

logger = logging.getLogger(__name__)


# =============================================================================
# Headless Detection Helper
# =============================================================================

def _is_headless(session_id: str) -> bool:
    """Return True if session_id belongs to a headless (no-WS-client) run."""
    return bool(session_id and session_id.startswith("headless-"))


# =============================================================================
# New Event System (Layer 1-4)
# =============================================================================

async def send_reply_event(
    session_id: str,
    content: str,
    is_delta: bool = True,
    is_complete: bool = False,
    is_new_round: bool = False,
) -> None:
    """Layer 1: Send main reply content (streaming delta).

    Args:
        is_new_round: If True, frontend should replace (not append) the reply content.
    """
    if _is_headless(session_id):
        return
    await manager.emit_to_session(session_id, "reply_delta", {
        "content": content,
        "is_delta": is_delta,
        "is_complete": is_complete,
        "is_new_round": is_new_round,
    })


async def send_plan_event(
    session_id: str,
    plan_text: str,
    steps: list[dict[str, Any]] | None = None,
) -> None:
    """Layer 2: Send plan update."""
    if _is_headless(session_id):
        return
    await manager.emit_to_session(session_id, "plan_update", {
        "text": plan_text,
        "steps": steps,
    })


async def send_action_log_event(
    session_id: str,
    action_type: str,
    message: str,
    step: str = "",
    is_complete: bool = False,
) -> None:
    """Layer 3: Send action log entry."""
    if _is_headless(session_id):
        return
    await manager.emit_to_session(session_id, "action_log", {
        "action_type": action_type,
        "message": message,
        "step": step,
        "is_complete": is_complete,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def send_thought_event(
    session_id: str,
    content: str,
    is_delta: bool = True,
    is_complete: bool = False,
) -> None:
    """Send thinking/reasoning content (collapsible)."""
    if _is_headless(session_id):
        return
    await manager.emit_to_session(session_id, "thought_delta", {
        "content": content,
        "is_delta": is_delta,
        "is_complete": is_complete,
    })


async def send_inline_confirmation(
    session_id: str,
    message: str,
    options: list[dict[str, Any]],
) -> None:
    """Layer 4: Send inline confirmation request."""
    if _is_headless(session_id):
        return
    await manager.emit_to_session(session_id, "inline_confirmation", {
        "message": message,
        "options": options,
    })


# =============================================================================
# Preserved Events (used by agent nodes and websocket handler)
# =============================================================================

async def send_progress_event(
    session_id: str,
    step: str,
    step_name: str,
    progress: float,
    message: str,
    status: str = "running",
    steps: list[dict[str, Any]] | None = None,
) -> None:
    """Send execution progress event to frontend."""
    if _is_headless(session_id):
        return
    payload: dict[str, Any] = {
        "stage": step,
        "stage_name": step_name,
        "progress": progress,
        "message": message,
        "status": status,
    }
    if steps is not None:
        payload["steps"] = steps
    await manager.emit_to_session(
        session_id,
        "execution_progress",
        payload,
    )


async def send_output_ready(
    session_id: str,
    output_type: str,
    data: dict[str, Any],
    title: str | None = None,
    output_id: str | None = None,
    related_message_id: str | None = None,
    linked_message_id: str | None = None,
    category: str | None = None,
    scenario_label: str | None = None,
) -> None:
    """Send output ready event for Canvas artifacts."""
    if _is_headless(session_id):
        return
    payload: dict[str, Any] = {
        "output_id": output_id,
        "type": output_type,
        "title": title or "分析结果",
        "data": data,
        "auto_open_canvas": True,
        "related_message_id": related_message_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if linked_message_id:
        payload["linked_message_id"] = linked_message_id
    if category:
        payload["category"] = category
    if scenario_label:
        payload["scenario_label"] = scenario_label
    await manager.emit_to_session(session_id, "output_ready", payload)


async def save_and_send_artifact(
    session_id: str,
    output_type: str,
    title: str,
    data: dict,
    related_message_id: str | None = None,
    category: str | None = None,
    scenario_label: str | None = None,
) -> str:
    """Save artifact to DB and send to frontend via WebSocket.

    The artifact ID sent to frontend uses a fixed format: ``{session_id}_{output_type}``.
    This ensures same-type artifacts merge into a single Canvas Tab with version history.
    The DB message ID is passed as ``linked_message_id`` for conversation jump-back.

    For headless sessions (session_id starts with "headless-"):
    - Skip Message persistence (no valid session FK)
    - Skip WebSocket send (no connected client)
    - Rely on Snapshot persistence for data durability
    - Return empty string as output_id

    Returns:
        The output message ID (str).
    """
    # Headless mode: skip Message save, rely on Snapshot only
    if session_id.startswith("headless-"):
        logger.info(
            "[Artifact] Headless mode, skipping Message save: %s (type=%s)",
            title, output_type,
        )
        return ""

    from app.services.message_service import MessageService
    from app.core.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            service = MessageService(db)
            msg = await service.save_message(
                session_id=UUID(session_id),
                role="agent",
                content=title,
                message_type="OUTPUT",
                output_type=output_type,
                output_data=json.dumps(data, ensure_ascii=False),
            )
            db_message_id = msg["id"]

        # Fixed artifact ID: same output_type always maps to the same Canvas Tab
        artifact_id = f"{session_id}_{output_type}"

        await send_output_ready(
            session_id=session_id,
            output_type=output_type,
            data=data,
            title=title,
            output_id=artifact_id,
            related_message_id=related_message_id,
            linked_message_id=db_message_id,
            category=category,
            scenario_label=scenario_label,
        )
        logger.info(f"[Artifact] Saved and sent: {title} (type={output_type}, artifact={artifact_id}, msg={db_message_id})")
        return db_message_id
    except Exception as e:
        logger.error(f"[Artifact] Failed to save/send artifact: {e}", exc_info=True)
        return ""


async def send_execution_complete(
    session_id: str, message: str = "分析完成"
) -> None:
    """Send execution complete event."""
    if _is_headless(session_id):
        return
    await manager.emit_to_session(
        session_id, "execution_complete", {"message": message}
    )


async def send_error_event(
    session_id: str, step: str, error: str, recoverable: bool = False
) -> None:
    """Send error event."""
    if _is_headless(session_id):
        return
    await manager.emit_to_session(
        session_id,
        "error",
        {
            "step": step,
            "error": error,
            "recoverable": recoverable,
        },
    )


# =============================================================================
# Backward-Compatible Stubs (used by agent nodes during transition)
# =============================================================================

async def send_tpaor_event(
    session_id: str,
    phase: str,
    content: str,
    is_complete: bool = False,
) -> None:
    """Legacy TPAOR event stub — maps to new event system.

    Phase mapping:
        thought → thought_delta
        plan → plan_update
        action → action_log
        observation → action_log (complete)
        response → reply_delta
    """
    if _is_headless(session_id):
        return
    if phase == "thought":
        await send_thought_event(session_id, content, is_delta=True)
    elif phase == "plan":
        await send_plan_event(session_id, content)
    elif phase == "action":
        await send_action_log_event(session_id, "generic", content, is_complete=False)
    elif phase == "observation":
        await send_action_log_event(session_id, "generic", content, is_complete=True)
    elif phase == "response":
        await send_reply_event(session_id, content, is_delta=False)
    else:
        await send_action_log_event(session_id, "generic", content, is_complete=is_complete)


async def send_system_notice_event(
    session_id: str,
    subtype: str,
    level: str = "info",
    title: str = "",
    description: str = "",
    impact: str = "",
    platforms: list[dict[str, Any]] | None = None,
) -> None:
    """Send a system_notice event via WebSocket.

    Used by the resilience layer to notify the frontend about degradation
    and circuit-breaker events. Falls back to reply_delta if needed.

    Args:
        session_id: WebSocket session id.
        subtype: Notice subtype (e.g. 'degradation', 'platform_status').
        level: Severity level ('info', 'warning', 'error').
        title: Short title.
        description: Detailed description.
        impact: User-facing impact statement.
        platforms: Optional list of platform status dicts.
    """
    if _is_headless(session_id):
        return

    payload: dict[str, Any] = {
        "subtype": subtype,
        "level": level,
        "title": title,
        "description": description,
        "impact": impact,
    }
    if platforms is not None:
        payload["platforms"] = platforms

    await manager.emit_to_session(session_id, "system_notice", payload)


async def send_stage_result(
    session_id: str,
    stage: str,
    stage_name: str,
    result_type: str,
    data: dict[str, Any],
) -> None:
    """发送阶段性结果到前端。

    在每个 Agent 完成关键步骤后调用，让用户在等待期间看到阶段性产出。

    Args:
        session_id: WebSocket session id.
        stage: Agent 阶段标识 (e.g. "A1", "A2", "A3", "A4", "A5").
        stage_name: 阶段中文名称 (e.g. "品牌分析", "用户画像").
        result_type: 结果类型 ("brand_profile" | "personas" | "questions" |
                     "platform_status" | "metrics_preview").
        data: 阶段性结果数据。
    """
    if _is_headless(session_id):
        return
    await manager.emit_to_session(
        session_id,
        "stage_result",
        {
            "stage": stage,
            "stage_name": stage_name,
            "result_type": result_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


async def send_confirmation_request(
    session_id: str,
    step_id: str = "",
    step_name: str = "",
    message: str = "",
    options: list[dict] | None = None,
    **kwargs,
) -> None:
    """Legacy confirmation request stub — maps to inline_confirmation."""
    if _is_headless(session_id):
        return
    await send_inline_confirmation(session_id, message, options or [])
