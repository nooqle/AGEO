"""WebSocket event handling for LangGraph workflow.

This module handles sending events to the frontend during workflow execution.
New event system: reply_delta, plan_update, action_log, thought_delta, inline_confirmation.
Legacy events (send_output_ready, send_execution_complete, send_error_event) are preserved.
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.services.session_event_publisher import session_event_publisher

logger = logging.getLogger(__name__)

_USER_VISIBLE_TEXT_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("site_confidence_assessment_skill", "官网 AI 友好度"),
    ("site_confidence_assessment_executor", "官网 AI 友好度"),
    ("官网置信度评估", "官网 AI 友好度"),
    ("官网置信度报告", "官网 AI 友好度报告"),
)


# =============================================================================
# Session-level Layer Accumulator
# =============================================================================
# WARNING: _session_layers is an in-memory dict that requires single-process deployment.
# For multi-worker deployment (e.g. gunicorn --workers N), migrate to Redis or similar.
# Lifecycle: reset (on message start) -> accumulate (during workflow) -> pop (on message save)
# TTL cleanup handles orphaned entries from crashed sessions.

_session_layers: dict[str, dict[str, Any]] = {}

_SESSION_LAYER_TTL_SECONDS = 1800  # 30 minutes


def _sanitize_user_visible_text(value: str | None) -> str:
    text = str(value or "")
    for raw, display in _USER_VISIBLE_TEXT_REPLACEMENTS:
        text = text.replace(raw, display)
    return text


def _sanitize_confirmation_options(
    options: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for option in options or []:
        item = dict(option or {})
        if "label" in item:
            item["label"] = _sanitize_user_visible_text(item.get("label"))
        if "description" in item:
            item["description"] = _sanitize_user_visible_text(item.get("description"))
        sanitized.append(item)
    return sanitized


def _get_layers(session_id: str) -> dict[str, Any]:
    """Get or create the layer accumulator for a session.

    Also performs TTL cleanup: purges entries older than 30 minutes on each call.
    """
    now = time.monotonic()

    # TTL cleanup: purge entries older than 30 minutes
    stale = [
        sid
        for sid, data in _session_layers.items()
        if now - data.get("_created_at", 0) > _SESSION_LAYER_TTL_SECONDS
    ]
    for sid in stale:
        logger.info("[Layers] TTL expired, purging orphaned session %s", sid[:8])
        _session_layers.pop(sid, None)

    if session_id not in _session_layers:
        # NOTE: Field names use camelCase intentionally — they are stored in
        # message.metadata.layers and consumed by the frontend as-is.
        _session_layers[session_id] = {
            "_created_at": now,
            "replyText": "",
            "thought": "",
            "planText": "",
            "actionLogs": [],
            "stageResults": [],
        }
    return _session_layers[session_id]


def reset_session_layers(session_id: str) -> None:
    """Reset accumulated layers for a new execution round."""
    _session_layers.pop(session_id, None)


def pop_accumulated_layers(session_id: str) -> dict[str, Any]:
    """Pop and return accumulated layers for persistence, then clear."""
    data = _session_layers.pop(session_id, {})
    data.pop("_created_at", None)  # Do not expose internal bookkeeping field
    if data:
        logger.info(
            "[Layers] Popped layers for session %s: thought=%d, plans=%d, logs=%d, results=%d",
            session_id[:8],
            len(data.get("thought", "")),
            len(data.get("planText", "")),
            len(data.get("actionLogs", [])),
            len(data.get("stageResults", [])),
        )
    return data


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

    content = _sanitize_user_visible_text(content)

    if not is_complete:
        layers = _get_layers(session_id)
        if is_new_round or not is_delta:
            layers["replyText"] = content
        else:
            layers["replyText"] += content

    await session_event_publisher.emit_to_session(
        session_id,
        "reply_delta",
        {
            "content": content,
            "is_delta": is_delta,
            "is_complete": is_complete,
            "is_new_round": is_new_round,
        },
    )


async def send_plan_event(
    session_id: str,
    plan_text: str,
    steps: list[dict[str, Any]] | None = None,
) -> None:
    """Layer 2: Send plan update."""
    # Headless sessions: skip both accumulation and WS send
    if _is_headless(session_id):
        return

    # Accumulate for persistence (plan is replaced, not appended)
    layers = _get_layers(session_id)
    layers["planText"] = plan_text

    await session_event_publisher.emit_to_session(
        session_id,
        "plan_update",
        {
            "text": plan_text,
            "steps": steps,
        },
    )


async def send_action_log_event(
    session_id: str,
    action_type: str,
    message: str,
    step: str = "",
    is_complete: bool = False,
) -> None:
    """Layer 3: Send action log entry."""
    # Headless sessions: skip both accumulation and WS send
    if _is_headless(session_id):
        return

    ts = datetime.now(timezone.utc).isoformat()
    # Accumulate for persistence
    layers = _get_layers(session_id)
    layers["actionLogs"].append(
        {
            "action_type": action_type,
            "message": message,
            "step": step,
            "is_complete": is_complete,
            "timestamp": ts,
        }
    )

    await session_event_publisher.emit_to_session(
        session_id,
        "action_log",
        {
            "action_type": action_type,
            "message": message,
            "step": step,
            "is_complete": is_complete,
            "timestamp": ts,
        },
    )


async def send_thought_event(
    session_id: str,
    content: str,
    is_delta: bool = True,
    is_complete: bool = False,
) -> None:
    """Send thinking/reasoning content (collapsible)."""
    # Headless sessions: skip both accumulation and WS send
    if _is_headless(session_id):
        return

    # Accumulate for persistence
    layers = _get_layers(session_id)
    if is_delta:
        layers["thought"] += content
    else:
        layers["thought"] = content

    await session_event_publisher.emit_to_session(
        session_id,
        "thought_delta",
        {
            "content": content,
            "is_delta": is_delta,
            "is_complete": is_complete,
        },
    )


async def send_inline_confirmation(
    session_id: str,
    message: str,
    options: list[dict[str, Any]],
) -> None:
    """Layer 4: Send inline confirmation request."""
    if _is_headless(session_id):
        return
    message = _sanitize_user_visible_text(message)
    options = _sanitize_confirmation_options(options)
    await session_event_publisher.emit_to_session(
        session_id,
        "inline_confirmation",
        {
            "message": message,
            "options": options,
        },
    )


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
    step_name = _sanitize_user_visible_text(step_name)
    message = _sanitize_user_visible_text(message)
    payload: dict[str, Any] = {
        "stage": step,
        "stage_name": step_name,
        "progress": progress,
        "message": message,
        "status": status,
    }
    if steps is not None:
        payload["steps"] = steps
    await session_event_publisher.emit_to_session(
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
    sequence: int | None = None,
    category: str | None = None,
    scenario_label: str | None = None,
) -> None:
    """Send output ready event for Canvas artifacts."""
    if _is_headless(session_id):
        return
    title = _sanitize_user_visible_text(title or "分析结果")
    payload: dict[str, Any] = {
        "output_id": output_id,
        "type": output_type,
        "title": title,
        "data": data,
        "auto_open_canvas": True,
        "related_message_id": related_message_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if linked_message_id:
        payload["linked_message_id"] = linked_message_id
    if sequence is not None:
        payload["sequence"] = sequence
    if category:
        payload["category"] = category
    if scenario_label:
        payload["scenario_label"] = scenario_label
    await session_event_publisher.emit_to_session(session_id, "output_ready", payload)


async def save_and_send_artifact(
    session_id: str,
    output_type: str,
    title: str,
    data: dict,
    related_message_id: str | None = None,
    category: str | None = None,
    scenario_label: str | None = None,
    artifact_key: str | None = None,
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
    title = _sanitize_user_visible_text(title)
    if isinstance(data, dict):
        data = dict(data)
        for key in ("headline", "description", "preview_description", "subtitle"):
            if key in data:
                data[key] = _sanitize_user_visible_text(data.get(key))
        status = data.get("status")
        if isinstance(status, dict) and "message" in status:
            data["status"] = {
                **status,
                "message": _sanitize_user_visible_text(status.get("message")),
            }

    # Headless mode: skip Message save, rely on Snapshot only
    if session_id.startswith("headless-"):
        logger.info(
            "[Artifact] Headless mode, skipping Message save: %s (type=%s)",
            title,
            output_type,
        )
        return ""

    from app.services.message_service import MessageService
    from app.core.database import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as db:
            service = MessageService(db)
            resolved_artifact_id = artifact_key or f"{session_id}_{output_type}"
            msg = await service.save_message(
                session_id=UUID(session_id),
                role="agent",
                content=title,
                metadata={
                    "output_id": resolved_artifact_id,
                    "artifact_kind": data.get("artifact_kind"),
                    "report_kind": data.get("report_kind"),
                    "triggered_by": data.get("triggered_by"),
                },
                message_type="OUTPUT",
                output_type=output_type,
                output_data=json.dumps(data, ensure_ascii=False),
            )
            db_message_id = msg["id"]
            db_sequence = msg.get("sequence")

        artifact_id = resolved_artifact_id

        await send_output_ready(
            session_id=session_id,
            output_type=output_type,
            data=data,
            title=title,
            output_id=artifact_id,
            related_message_id=related_message_id,
            linked_message_id=db_message_id,
            sequence=db_sequence if isinstance(db_sequence, int) else None,
            category=category,
            scenario_label=scenario_label,
        )
        logger.info(
            f"[Artifact] Saved and sent: {title} (type={output_type}, artifact={artifact_id}, msg={db_message_id})"
        )
        return db_message_id
    except Exception as e:
        logger.error(f"[Artifact] Failed to save/send artifact: {e}", exc_info=True)
        return ""


async def send_artifact_patch(
    session_id: str,
    artifact_id: str,
    patch: dict[str, Any],
    patch_type: str = "merge",
    status: str | None = None,
    message: str | None = None,
) -> None:
    """Send incremental patch update for an existing artifact."""
    if _is_headless(session_id):
        return
    payload: dict[str, Any] = {
        "artifact_id": artifact_id,
        "patch_type": patch_type,
        "patch": patch,
    }
    if status:
        payload["status"] = status
    if message:
        payload["message"] = message
    await session_event_publisher.emit_to_session(session_id, "artifact_patch", payload)


async def send_execution_complete(session_id: str, message: str = "分析完成") -> None:
    """Send execution complete event."""
    if _is_headless(session_id):
        return
    message = _sanitize_user_visible_text(message)
    await session_event_publisher.emit_to_session(
        session_id, "execution_complete", {"message": message}
    )


async def send_error_event(
    session_id: str, step: str, error: str, recoverable: bool = False
) -> None:
    """Send error event."""
    if _is_headless(session_id):
        return
    # Guard: never send empty error string to frontend
    if not error or not error.strip():
        error = f"未知错误 ({step})"
        logger.warning(
            "[Events] send_error_event called with empty error for step %s", step
        )
    step = _sanitize_user_visible_text(step)
    error = _sanitize_user_visible_text(error)
    await session_event_publisher.emit_to_session(
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
        await send_action_log_event(
            session_id, "generic", content, is_complete=is_complete
        )


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

    await session_event_publisher.emit_to_session(session_id, "system_notice", payload)


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
    # Headless sessions: skip both accumulation and WS send
    if _is_headless(session_id):
        return

    ts = datetime.now(timezone.utc).isoformat()
    # Accumulate for persistence
    layers = _get_layers(session_id)
    layers["stageResults"].append(
        {
            "stage": stage,
            "stage_name": stage_name,
            "result_type": result_type,
            "data": data,
            "timestamp": ts,
        }
    )

    await session_event_publisher.emit_to_session(
        session_id,
        "stage_result",
        {
            "stage": stage,
            "stage_name": stage_name,
            "result_type": result_type,
            "data": data,
            "timestamp": ts,
        },
    )


async def send_browser_state_event(
    session_id: str,
    platform: str,
    state: str,
    message: str,
    progress: float = 0.0,
    requires_action: bool = False,
    action_hint: str | None = None,
    request_id: str | None = None,
    related_message_id: str | None = None,
    reason_code: str | None = None,
    blocking_url: str | None = None,
    blocking_fingerprint: str | None = None,
    takeover: dict[str, Any] | None = None,
) -> None:
    """Send browser state event to frontend.

    Used to notify frontend about browser login requirements and state changes.

    Args:
        session_id: WebSocket session id.
        platform: Platform name (e.g. 'kimi', 'deepseek').
        state: Browser state string (e.g. 'waiting_for_login').
        message: Human-readable status message.
        progress: Progress value (0-1).
        requires_action: Whether user action is required.
        action_hint: Hint for what the user should do.
    """
    if _is_headless(session_id):
        return
    payload: dict[str, Any] = {
        "platform": platform,
        "state": state,
        "message": message,
        "progress": progress,
        "requires_action": requires_action,
    }
    if action_hint:
        payload["action_hint"] = action_hint
    if request_id:
        payload["request_id"] = request_id
    if related_message_id:
        payload["related_message_id"] = related_message_id
    if reason_code:
        payload["reason_code"] = reason_code
    if blocking_url:
        payload["blocking_url"] = blocking_url
    if blocking_fingerprint:
        payload["blocking_fingerprint"] = blocking_fingerprint
    if takeover:
        payload["takeover"] = takeover
    await session_event_publisher.emit_to_session(session_id, "browser_state", payload)


async def send_browser_user_action_event(
    session_id: str,
    platform: str,
    state: str,
    action_type: str,
    message: str,
    progress: float = 0.0,
    action_hint: str | None = None,
    request_id: str | None = None,
    related_message_id: str | None = None,
    reason_code: str | None = None,
    blocking_url: str | None = None,
    blocking_fingerprint: str | None = None,
    takeover: dict[str, Any] | None = None,
) -> None:
    """Send a normalized browser user-action event to frontend.

    This is the action-oriented companion to ``browser_state`` and is used for
    cases where the UI should clearly distinguish login, verification, and
    modal-confirmation flows.
    """
    if _is_headless(session_id):
        return
    payload: dict[str, Any] = {
        "platform": platform,
        "state": state,
        "action_type": action_type,
        "message": message,
        "progress": progress,
        "requires_action": True,
    }
    if action_hint:
        payload["action_hint"] = action_hint
    if request_id:
        payload["request_id"] = request_id
    if related_message_id:
        payload["related_message_id"] = related_message_id
    if reason_code:
        payload["reason_code"] = reason_code
    if blocking_url:
        payload["blocking_url"] = blocking_url
    if blocking_fingerprint:
        payload["blocking_fingerprint"] = blocking_fingerprint
    if takeover:
        payload["takeover"] = takeover
    await session_event_publisher.emit_to_session(
        session_id, "browser_user_action", payload
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
