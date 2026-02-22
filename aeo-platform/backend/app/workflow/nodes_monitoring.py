"""Monitoring schedule creation node for LangGraph workflow.

Handles the create_monitoring_schedule tool call from the orchestrator.
Creates a MonitoringSchedule and returns a confirmation to the orchestrator.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from langgraph.types import Command

from app.core.database import AsyncSessionLocal
from app.models.monitoring_schedule import ScheduleFrequency
from app.models.session import Session
from app.services.monitoring_service import MonitoringService
from app.workflow.events import send_reply_event, send_action_log_event
from app.workflow.state import AgentState

logger = logging.getLogger(__name__)

# Frequency labels for user-facing messages
FREQ_LABELS = {
    "daily": "每天",
    "weekly": "每周",
    "biweekly": "每两周",
    "monthly": "每月",
}


async def create_monitoring_node(state: AgentState) -> Command:
    """Create a monitoring schedule via chat command.

    Reads tool_call_args from the orchestrator and creates a schedule
    using MonitoringService. Returns to orchestrator with the result.
    """
    session_id = state["session_id"]
    entity_id = state.get("entity_id")

    if not entity_id:
        msg = (
            "需要先完成至少一次品牌分析才能创建监测计划。"
            "请先告诉我您要分析的品牌名称。"
        )
        await send_reply_event(session_id, msg, is_delta=False)
        return Command(
            update={
                "orchestrator_reply": msg,
            },
        )

    tool_args = state.get("tool_call_args") or {}
    frequency_str = tool_args.get("frequency", "weekly")
    preferred_hour = tool_args.get("preferred_hour", 11)
    alert_threshold = tool_args.get("alert_threshold", 10.0)

    try:
        frequency = ScheduleFrequency(frequency_str)
    except ValueError:
        frequency = ScheduleFrequency.WEEKLY

    # Validate preferred_hour range
    if not isinstance(preferred_hour, int) or not 0 <= preferred_hour <= 23:
        preferred_hour = 11

    brand_name = state.get("brand_name", "该品牌")

    await send_action_log_event(
        session_id,
        "monitoring",
        f"正在创建{FREQ_LABELS.get(frequency_str, frequency_str)}监测计划...",
        step="create_monitoring",
        is_complete=False,
    )

    try:
        async with AsyncSessionLocal() as db:
            service = MonitoringService(db)

            # Resolve user_id: look up from session in DB
            user_id = await _resolve_user_id(db, session_id)
            if user_id is None:
                msg = "无法确定当前用户，请重新登录后重试。"
                await send_reply_event(session_id, msg, is_delta=False)
                return Command(update={"orchestrator_reply": msg})

            schedule = await service.create_schedule(
                user_id=user_id,
                entity_id=UUID(entity_id),
                frequency=frequency,
                preferred_hour=preferred_hour,
                alert_threshold_bwvs=alert_threshold,
            )

        freq_label = FREQ_LABELS.get(frequency_str, frequency_str)
        next_run_str = (
            schedule.next_run_at.strftime("%Y-%m-%d %H:%M")
            if schedule.next_run_at
            else "待计算"
        )

        msg = (
            f"监测计划已创建。我将{freq_label}自动分析 {brand_name} 的品牌可见度。\n"
            f"- 执行频率：{freq_label}\n"
            f"- 下次执行：{next_run_str} (UTC)\n"
            f"- 告警阈值：BWVS 变化超过 {alert_threshold} 分时通知您\n"
            f"- 监测平台：{', '.join(schedule.platforms or ['doubao', 'hunyuan'])}\n\n"
            f"您可以随时说\"暂停监测\"或\"停止监测\"来管理监测计划。"
        )

        await send_action_log_event(
            session_id,
            "monitoring",
            "监测计划创建成功",
            step="create_monitoring",
            is_complete=True,
        )

        logger.info(
            "[CreateMonitoring] Schedule created for entity %s (freq=%s)",
            entity_id,
            frequency_str,
        )

        return Command(
            update={
                "orchestrator_reply": msg,
            },
        )

    except ValueError as e:
        error_msg = f"创建监测计划失败：{str(e)}"
        await send_reply_event(session_id, error_msg, is_delta=False)
        logger.warning("[CreateMonitoring] Validation error: %s", e)
        return Command(
            update={
                "orchestrator_reply": error_msg,
            },
        )
    except Exception as e:
        error_msg = f"创建监测计划时出现错误：{str(e)}"
        await send_reply_event(session_id, error_msg, is_delta=False)
        logger.error("[CreateMonitoring] Error: %s", e, exc_info=True)
        return Command(
            update={
                "orchestrator_reply": error_msg,
                "error_info": {
                    "step": "create_monitoring",
                    "error": str(e),
                },
            },
        )


async def _resolve_user_id(db: AsyncSession, session_id: str) -> UUID | None:
    """Resolve user_id from the session record.

    For headless sessions (sentinel session_id), this will return None
    since there is no real session. But headless runs don't use this node.
    """
    try:
        session_uuid = UUID(session_id)
    except ValueError:
        return None

    stmt = select(Session).where(Session.id == session_uuid)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if session is not None:
        return session.user_id
    return None
