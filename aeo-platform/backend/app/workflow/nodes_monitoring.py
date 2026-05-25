"""Monitoring schedule management node for LangGraph workflow.

Handles chat-triggered monitoring schedule operations. The node keeps the
legacy create_monitoring_schedule path working, while also supporting the new
monitoring-plan workflow where an existing plan/schedule should be queried or
updated instead of forcing users to delete and recreate it manually.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from langgraph.types import Command
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.monitoring_plan import MonitoringPlanStatus
from app.models.monitoring_plan import MonitoringQuestionSet, QuestionSetStatus
from app.models.monitoring_schedule import (
    MonitoringSchedule,
    ScheduleFrequency,
    ScheduleStatus,
)
from app.models.session import Session
from app.services.brand_action_service import BrandActionService
from app.services.monitoring_plan_service import MonitoringPlanService
from app.services.monitoring_service import MonitoringService
from app.workflow.events import send_action_log_event, send_reply_event
from app.workflow.state import AgentState

logger = logging.getLogger(__name__)

FREQ_LABELS = {
    "daily": "每天",
    "weekly": "每周",
    "biweekly": "每两周",
    "monthly": "每月",
}

STATUS_LABELS = {
    "active": "运行中",
    "paused": "已暂停",
    "error": "异常",
    "completed": "已完成",
}

MONITOR_MODE_LABELS = {
    "panorama": "全景监测",
    "scenario": "用户场景监测",
}

PLATFORM_LABELS = {
    "doubao": "豆包",
    "yuanbao": "元宝",
    "hunyuan": "元宝",
    "kimi": "Kimi",
    "deepseek": "DeepSeek",
    "doubao_api": "豆包API",
    "yuanbao_api": "元宝API",
    "kimi_api": "Kimi API",
    "deepseek_browser": "DeepSeek",
}

ACTION_ALIASES = {
    "read": "get",
    "show": "get",
    "query": "get",
    "view": "get",
    "create": "upsert",
    "set": "upsert",
    "save": "upsert",
    "enable": "upsert",
    "adjust": "upsert",
    "modify": "update",
    "change": "update",
    "edit": "update",
    "disable": "pause",
    "stop": "pause",
    "restart": "resume",
}

SUPPORTED_ACTIONS = {"get", "upsert", "update", "pause", "resume", "delete"}

MONITOR_MODE_ALIASES = {
    "panorama": "panorama",
    "panorama_monitoring": "panorama",
    "baseline": "panorama",
    "baseline_monitoring": "panorama",
    "scenario": "scenario",
    "scenario_monitoring": "scenario",
    "persona": "scenario",
    "persona_monitoring": "scenario",
}


async def create_monitoring_node(state: AgentState) -> Command:
    """Manage a monitoring schedule via chat command."""

    session_id = state["session_id"]
    tool_args = dict(state.get("tool_call_args") or {})
    dashboard_context = _dashboard_context(state)
    if not dashboard_context.get("question_set_ids"):
        dashboard_context["question_set_ids"] = _first_value(
            tool_args.get("question_set_ids"),
            state.get("question_set_ids"),
        )
    if not dashboard_context.get("endpoint_ids"):
        dashboard_context["endpoint_ids"] = _first_value(
            tool_args.get("endpoint_ids"),
            state.get("endpoint_ids"),
        )
    entity_id = _first_text(
        tool_args.get("entity_id"),
        dashboard_context.get("entity_id"),
        state.get("entity_id"),
    )

    if not entity_id:
        msg = (
            "需要先完成至少一次品牌分析，才能设置周期监测。"
            "请先告诉我您要分析的品牌名称。"
        )
        await send_reply_event(session_id, msg, is_delta=False)
        return Command(update={"orchestrator_reply": msg})

    entity_uuid = _parse_uuid(entity_id)
    if entity_uuid is None:
        msg = "当前品牌实体信息无效，请回到 Dashboard 重新进入该品牌后再试。"
        await send_reply_event(session_id, msg, is_delta=False)
        return Command(update={"orchestrator_reply": msg})

    action = _normalize_action(tool_args.get("action"))
    monitor_mode = _resolve_monitor_mode(state, tool_args, dashboard_context)
    brand_name = _first_text(
        tool_args.get("brand_name"),
        dashboard_context.get("brand"),
        state.get("brand_name"),
        "该品牌",
    )
    frequency = _normalize_frequency(tool_args.get("frequency"))
    preferred_hour = _normalize_preferred_hour(tool_args.get("preferred_hour"))
    alert_threshold = _normalize_alert_threshold(
        _first_value(tool_args.get("alert_threshold"), tool_args.get("alert_threshold_bwvs"))
    )
    timezone_str = _first_text(tool_args.get("timezone"), "Asia/Shanghai")

    await send_action_log_event(
        session_id,
        "monitoring",
        _build_action_log_message(action, frequency, preferred_hour),
        step="create_monitoring",
        is_complete=False,
    )

    try:
        async with AsyncSessionLocal() as db:
            user_id = await _resolve_user_id(db, session_id)
            if user_id is None:
                msg = "无法确定当前用户，请重新登录后重试。"
                await send_reply_event(session_id, msg, is_delta=False)
                return Command(update={"orchestrator_reply": msg})

            monitoring_service = MonitoringService(db)
            plan_service = MonitoringPlanService(db)

            plan_id = _parse_uuid(
                _first_text(
                    tool_args.get("monitoring_plan_id"),
                    dashboard_context.get("monitoring_plan_id"),
                    state.get("monitoring_plan_id"),
                    state.get("latest_monitoring_plan_id"),
                )
            )
            plan = (
                await plan_service.get_plan(plan_id, user_id=user_id)
                if plan_id is not None
                else await plan_service.get_entity_plan(
                    user_id=user_id,
                    entity_id=entity_uuid,
                    monitor_mode=monitor_mode,
                )
            )

            schedule = await _find_schedule(
                monitoring_service,
                user_id=user_id,
                entity_id=entity_uuid,
                monitor_mode=monitor_mode,
                schedule_id=_parse_uuid(tool_args.get("schedule_id")),
                monitoring_plan_id=plan.id if plan is not None else plan_id,
            )

            if action == "get":
                msg = await _build_current_plan_reply(
                    brand_name=brand_name,
                    monitor_mode=monitor_mode,
                    plan_service=plan_service,
                    plan=plan,
                    schedule=schedule,
                )
                return Command(update=_build_state_update(msg, plan=plan, schedule=schedule))

            if action in {"pause", "resume", "delete"} and plan is None and schedule is None:
                msg = f"当前没有找到 {brand_name} 的{MONITOR_MODE_LABELS[monitor_mode]}。"
                return Command(update={"orchestrator_reply": msg})

            if action == "pause":
                action_service = BrandActionService(db)
                monitoring_action_record = await _start_monitoring_plan_action(
                    db=db,
                    action_service=action_service,
                    state=state,
                    tool_args=tool_args,
                    dashboard_context=dashboard_context,
                    user_id=user_id,
                    entity_id=entity_uuid,
                    monitor_mode=monitor_mode,
                    action=action,
                    plan=plan,
                    schedule=schedule,
                    frequency=frequency,
                )
                try:
                    plan, schedule = await _pause_existing_monitoring(
                        plan_service,
                        monitoring_service,
                        user_id=user_id,
                        plan=plan,
                        schedule=schedule,
                    )
                except Exception as exc:
                    await _fail_monitoring_action(
                        db=db,
                        action_service=action_service,
                        record=monitoring_action_record,
                        error_message=str(exc),
                    )
                    raise
                if plan is not None:
                    schedule = await _find_schedule(
                        monitoring_service,
                        user_id=user_id,
                        entity_id=entity_uuid,
                        monitor_mode=monitor_mode,
                        monitoring_plan_id=plan.id,
                    )
                await _complete_monitoring_action(
                    db=db,
                    action_service=action_service,
                    record=monitoring_action_record,
                    plan=plan,
                    schedule=schedule,
                    monitor_mode=monitor_mode,
                )
                msg = _build_schedule_reply(
                    prefix="监测计划已暂停。",
                    brand_name=brand_name,
                    monitor_mode=monitor_mode,
                    plan=plan,
                    schedule=schedule,
                )
                return Command(update=_build_state_update(msg, plan=plan, schedule=schedule))

            if action == "resume":
                action_service = BrandActionService(db)
                monitoring_action_record = await _start_monitoring_plan_action(
                    db=db,
                    action_service=action_service,
                    state=state,
                    tool_args=tool_args,
                    dashboard_context=dashboard_context,
                    user_id=user_id,
                    entity_id=entity_uuid,
                    monitor_mode=monitor_mode,
                    action=action,
                    plan=plan,
                    schedule=schedule,
                    frequency=frequency,
                )
                try:
                    plan, schedule = await _resume_existing_monitoring(
                        plan_service,
                        monitoring_service,
                        user_id=user_id,
                        plan=plan,
                        schedule=schedule,
                    )
                except Exception as exc:
                    await _fail_monitoring_action(
                        db=db,
                        action_service=action_service,
                        record=monitoring_action_record,
                        error_message=str(exc),
                    )
                    raise
                if plan is not None:
                    schedule = await _find_schedule(
                        monitoring_service,
                        user_id=user_id,
                        entity_id=entity_uuid,
                        monitor_mode=monitor_mode,
                        monitoring_plan_id=plan.id,
                    )
                await _complete_monitoring_action(
                    db=db,
                    action_service=action_service,
                    record=monitoring_action_record,
                    plan=plan,
                    schedule=schedule,
                    monitor_mode=monitor_mode,
                )
                msg = _build_schedule_reply(
                    prefix="监测计划已恢复。",
                    brand_name=brand_name,
                    monitor_mode=monitor_mode,
                    plan=plan,
                    schedule=schedule,
                )
                return Command(update=_build_state_update(msg, plan=plan, schedule=schedule))

            if action == "delete":
                action_service = BrandActionService(db)
                monitoring_action_record = await _start_monitoring_plan_action(
                    db=db,
                    action_service=action_service,
                    state=state,
                    tool_args=tool_args,
                    dashboard_context=dashboard_context,
                    user_id=user_id,
                    entity_id=entity_uuid,
                    monitor_mode=monitor_mode,
                    action=action,
                    plan=plan,
                    schedule=schedule,
                    frequency=frequency,
                )
                try:
                    archived = False
                    deleted = await _delete_existing_schedule(
                        monitoring_service,
                        schedule=schedule,
                    )
                    if plan is not None:
                        plan = await plan_service.archive_plan(
                            plan_id=plan.id,
                            user_id=user_id,
                            commit=False,
                        )
                        archived = True
                except Exception as exc:
                    await _fail_monitoring_action(
                        db=db,
                        action_service=action_service,
                        record=monitoring_action_record,
                        error_message=str(exc),
                    )
                    raise
                await _complete_monitoring_action(
                    db=db,
                    action_service=action_service,
                    record=monitoring_action_record,
                    plan=plan,
                    schedule=None,
                    monitor_mode=monitor_mode,
                )
                msg = (
                    "监测计划已删除。"
                    if deleted or archived
                    else "当前没有找到可删除的监测计划。"
                )
                return Command(update=_build_state_update(msg, plan=plan, schedule=None))

            if action == "update" and plan is None and schedule is None:
                msg = (
                    f"当前没有找到 {brand_name} 的{MONITOR_MODE_LABELS[monitor_mode]}。"
                    "如果要新建，请告诉我监测频率、执行时间和告警阈值。"
                )
                return Command(update={"orchestrator_reply": msg})

            action_service = BrandActionService(db)
            monitoring_action_record = await _start_monitoring_plan_action(
                db=db,
                action_service=action_service,
                state=state,
                tool_args=tool_args,
                dashboard_context=dashboard_context,
                user_id=user_id,
                entity_id=entity_uuid,
                monitor_mode=monitor_mode,
                action=action,
                plan=plan,
                schedule=schedule,
                frequency=frequency,
            )
            try:
                plan, schedule = await _upsert_monitoring(
                    plan_service,
                    monitoring_service,
                    user_id=user_id,
                    entity_id=entity_uuid,
                    monitor_mode=monitor_mode,
                    dashboard_context=dashboard_context,
                    plan=plan,
                    schedule=schedule,
                    frequency=frequency,
                    preferred_hour=preferred_hour,
                    timezone_str=timezone_str,
                    alert_threshold=alert_threshold,
                )
            except Exception as exc:
                await _fail_monitoring_action(
                    db=db,
                    action_service=action_service,
                    record=monitoring_action_record,
                    error_message=str(exc),
                )
                raise
            if monitoring_action_record is not None:
                await _complete_monitoring_action(
                    db=db,
                    action_service=action_service,
                    record=monitoring_action_record,
                    plan=plan,
                    schedule=schedule,
                    monitor_mode=monitor_mode,
                )
            else:
                await db.commit()

        prefix = "监测计划已更新。" if schedule is not None else "监测计划已设置。"
        msg = _build_schedule_reply(
            prefix=prefix,
            brand_name=brand_name,
            monitor_mode=monitor_mode,
            plan=plan,
            schedule=schedule,
        )

        await send_action_log_event(
            session_id,
            "monitoring",
            "监测计划设置完成",
            step="create_monitoring",
            is_complete=True,
        )

        logger.info(
            "[MonitoringNode] Managed schedule for entity %s (action=%s, mode=%s)",
            entity_id,
            action,
            monitor_mode,
        )

        return Command(update=_build_state_update(msg, plan=plan, schedule=schedule))

    except ValueError as e:
        error_msg = f"监测计划处理失败：{str(e)}"
        await send_reply_event(session_id, error_msg, is_delta=False)
        logger.warning("[MonitoringNode] Validation error: %s", e)
        return Command(update={"orchestrator_reply": error_msg})
    except Exception as e:
        error_msg = f"处理监测计划时出现错误：{str(e)}"
        await send_reply_event(session_id, error_msg, is_delta=False)
        logger.error("[MonitoringNode] Error: %s", e, exc_info=True)
        return Command(
            update={
                "orchestrator_reply": error_msg,
                "error_info": {
                    "step": "create_monitoring",
                    "error": str(e),
                },
            }
        )


def _dashboard_context(state: AgentState) -> dict[str, Any]:
    value = state.get("dashboard_context")
    return dict(value) if isinstance(value, dict) else {}


def _first_value(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _first_text(*values: Any) -> str | None:
    value = _first_value(*values)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_uuid(value: Any) -> UUID | None:
    text = _first_text(value)
    if not text:
        return None
    try:
        return UUID(text)
    except (TypeError, ValueError):
        return None


def _normalize_action(value: Any) -> str:
    raw = str(value or "upsert").strip().lower()
    action = ACTION_ALIASES.get(raw, raw)
    return action if action in SUPPORTED_ACTIONS else "upsert"


def _normalize_frequency(value: Any) -> ScheduleFrequency | None:
    text = _first_text(value)
    if not text:
        return None
    try:
        return ScheduleFrequency(text)
    except ValueError:
        return None


def _normalize_preferred_hour(value: Any) -> int | None:
    if value is None:
        return None
    try:
        hour = int(value)
    except (TypeError, ValueError):
        return None
    return hour if 0 <= hour <= 23 else None


def _normalize_alert_threshold(value: Any) -> float | None:
    if value is None:
        return None
    try:
        threshold = float(value)
    except (TypeError, ValueError):
        return None
    return threshold if 0 < threshold <= 100 else None


def _resolve_monitor_mode(
    state: AgentState,
    tool_args: dict[str, Any],
    dashboard_context: dict[str, Any],
) -> str:
    raw = _first_text(
        tool_args.get("monitor_mode"),
        dashboard_context.get("monitor_mode"),
        (state.get("monitoring_plan") or {}).get("monitor_mode")
        if isinstance(state.get("monitoring_plan"), dict)
        else None,
        "panorama",
    )
    return MONITOR_MODE_ALIASES.get(str(raw or "").strip().lower(), "panorama")


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = value.split(",")
    elif isinstance(value, list):
        raw_items = value
    else:
        return []
    result: list[str] = []
    for item in raw_items:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _endpoint_ids_to_platforms(endpoint_ids: list[str]) -> list[str] | None:
    platforms = MonitoringPlanService.endpoint_ids_to_platforms(endpoint_ids)
    return platforms or None


async def _find_schedule(
    service: MonitoringService,
    *,
    user_id: UUID,
    entity_id: UUID,
    monitor_mode: str,
    schedule_id: UUID | None = None,
    monitoring_plan_id: UUID | None = None,
) -> MonitoringSchedule | None:
    if schedule_id is not None:
        schedule = await service.get_schedule(schedule_id)
        if schedule is not None and schedule.user_id == user_id:
            return schedule

    schedules, _ = await service.list_schedules(
        user_id,
        entity_id=entity_id,
        monitor_mode=monitor_mode,
        limit=20,
    )
    if monitoring_plan_id is not None:
        for schedule in schedules:
            if schedule.monitoring_plan_id == monitoring_plan_id:
                return schedule

    active = [item for item in schedules if item.status == ScheduleStatus.ACTIVE]
    paused = [item for item in schedules if item.status == ScheduleStatus.PAUSED]
    return (active or paused or schedules or [None])[0]


async def _build_current_plan_reply(
    *,
    brand_name: str,
    monitor_mode: str,
    plan_service: MonitoringPlanService,
    plan: Any | None,
    schedule: MonitoringSchedule | None,
) -> str:
    if plan is None and schedule is None:
        return f"当前没有找到 {brand_name} 的{MONITOR_MODE_LABELS[monitor_mode]}。"

    if plan is not None:
        plan_payload = await plan_service.plan_to_dict(plan)
        plan_line = (
            f"- 分析计划：{plan_payload.get('question_count', 0)} 个问题 · "
            f"{'、'.join(plan_payload.get('endpoint_labels') or []) or '平台来源待确认'} · "
            f"{_plan_status_label(plan_payload.get('status'))}"
        )
    else:
        plan_line = "- 分析计划：当前为旧版 schedule，未绑定新监测计划。"

    return _build_schedule_reply(
        prefix="这是当前监测计划：",
        brand_name=brand_name,
        monitor_mode=monitor_mode,
        plan=plan,
        schedule=schedule,
        extra_lines=[plan_line],
    )


async def _pause_existing_monitoring(
    plan_service: MonitoringPlanService,
    monitoring_service: MonitoringService,
    *,
    user_id: UUID,
    plan: Any | None,
    schedule: MonitoringSchedule | None,
) -> tuple[Any | None, MonitoringSchedule | None]:
    if plan is not None:
        plan = await plan_service.pause_plan(
            plan_id=plan.id,
            user_id=user_id,
            commit=False,
        )
    elif schedule is not None and schedule.status == ScheduleStatus.ACTIVE:
        schedule = await monitoring_service.pause_schedule(schedule.id)
    return plan, schedule


async def _resume_existing_monitoring(
    plan_service: MonitoringPlanService,
    monitoring_service: MonitoringService,
    *,
    user_id: UUID,
    plan: Any | None,
    schedule: MonitoringSchedule | None,
) -> tuple[Any | None, MonitoringSchedule | None]:
    if plan is not None:
        plan = await plan_service.update_plan(
            plan_id=plan.id,
            user_id=user_id,
            status=MonitoringPlanStatus.ACTIVE.value,
            commit=False,
        )
    elif schedule is not None and schedule.status in {ScheduleStatus.PAUSED, ScheduleStatus.ERROR}:
        schedule = await monitoring_service.resume_schedule(schedule.id)
    return plan, schedule


async def _delete_existing_schedule(
    monitoring_service: MonitoringService,
    *,
    schedule: MonitoringSchedule | None,
) -> bool:
    if schedule is None:
        return False
    return await monitoring_service.delete_schedule(schedule.id)


async def _start_monitoring_plan_action(
    *,
    db: AsyncSession,
    action_service: BrandActionService,
    state: AgentState,
    tool_args: dict[str, Any],
    dashboard_context: dict[str, Any],
    user_id: UUID,
    entity_id: UUID,
    monitor_mode: str,
    action: str,
    plan: Any | None,
    schedule: MonitoringSchedule | None,
    frequency: ScheduleFrequency | None,
) -> Any | None:
    parent_action_record_id = _parse_uuid(state.get("latest_user_action_record_id"))
    actor_type = "agent" if parent_action_record_id is not None else "user"
    origin_surface = (
        "workflow_monitoring_node"
        if parent_action_record_id is not None
        else "workflow_monitoring_user_command"
    )

    cadence = _monitoring_action_cadence(
        frequency=frequency,
        plan=plan,
        schedule=schedule,
    )
    ontology_action_type = _monitoring_ontology_action_type(
        action=action,
        plan=plan,
    )
    if ontology_action_type == "update_monitoring_plan" and plan is None:
        logger.info(
            "[MonitoringNode] Skipping monitoring plan lifecycle action because "
            "no monitoring_plan object exists yet."
        )
        return None
    question_ids = await _resolve_monitoring_action_question_ids(
        db=db,
        user_id=user_id,
        entity_id=entity_id,
        monitor_mode=monitor_mode,
        plan=plan,
        tool_args=tool_args,
        dashboard_context=dashboard_context,
        state=state,
    )
    if ontology_action_type == "create_monitoring_plan" and not question_ids:
        if parent_action_record_id is not None:
            raise ValueError(
                "Confirmed monitoring plan action requires question_ids"
            )
        logger.info(
            "[MonitoringNode] Skipping monitoring plan create action because "
            "legacy schedule input has no confirmed question ids."
        )
        return None
    if ontology_action_type == "update_monitoring_plan":
        input_payload = _build_monitoring_update_action_input_payload(
            entity_id=entity_id,
            change_type=_monitoring_change_type(action),
            cadence=cadence,
            monitor_mode=monitor_mode,
            plan=plan,
            schedule=schedule,
            dashboard_context=dashboard_context,
        )
    else:
        input_payload = _build_monitoring_action_input_payload(
            entity_id=entity_id,
            question_ids=question_ids,
            cadence=cadence,
            monitor_mode=monitor_mode,
            plan=plan,
            schedule=schedule,
            dashboard_context=dashboard_context,
        )
    return await action_service.start_action(
        entity_id=entity_id,
        session_id=_parse_uuid(state.get("session_id")),
        user_id=user_id,
        parent_action_record_id=parent_action_record_id,
        actor_type=actor_type,
        origin_surface=origin_surface,
        origin_event_id=_monitoring_action_origin_event_id(
            state=state,
            entity_id=entity_id,
            monitor_mode=monitor_mode,
            action=action,
            cadence=cadence,
        ),
        action_type=ontology_action_type,
        input_payload=input_payload,
    )


async def _complete_monitoring_action(
    *,
    db: AsyncSession,
    action_service: BrandActionService,
    record: Any | None,
    plan: Any | None,
    schedule: MonitoringSchedule | None,
    monitor_mode: str,
) -> None:
    if record is None:
        return
    await action_service.complete_action(
        record,
        output_payload=_build_monitoring_action_output_payload(
            plan=plan,
            schedule=schedule,
            monitor_mode=monitor_mode,
        ),
    )
    if plan is not None:
        await action_service.links.ensure_link(
            entity_id=record.entity_id,
            link_type="action_record_handles_monitoring_plan",
            from_object_type="action_record",
            from_object_id=str(record.id),
            to_object_type="monitoring_plan",
            to_object_id=str(plan.id),
            source_action_record_id=record.id,
            extra_metadata={"action_type": record.action_type},
        )
    await db.commit()


async def _fail_monitoring_action(
    *,
    db: AsyncSession,
    action_service: BrandActionService,
    record: Any | None,
    error_message: str,
) -> None:
    if record is None:
        await db.rollback()
        return
    failure_context = {
        "entity_id": record.entity_id,
        "session_id": record.session_id,
        "user_id": record.user_id,
        "parent_action_record_id": record.parent_action_record_id,
        "actor_type": record.actor_type,
        "origin_surface": record.origin_surface,
        "origin_event_id": record.origin_event_id,
        "action_type": record.action_type,
        "input_payload": (
            dict(record.input_payload)
            if isinstance(record.input_payload, dict)
            else {}
        ),
    }
    await db.rollback()
    try:
        failed_record = await action_service.start_action(
            entity_id=failure_context["entity_id"],
            session_id=failure_context["session_id"],
            user_id=failure_context["user_id"],
            parent_action_record_id=failure_context["parent_action_record_id"],
            actor_type=failure_context["actor_type"],
            origin_surface=failure_context["origin_surface"],
            origin_event_id=failure_context["origin_event_id"],
            action_type=failure_context["action_type"],
            input_payload=failure_context["input_payload"],
            strict_input_validation=False,
        )
        await action_service.fail_action(
            failed_record,
            error_message=error_message,
        )
        await db.commit()
    except Exception as fail_exc:
        await db.rollback()
        logger.warning(
            "[MonitoringNode] Failed to persist monitoring action failure: %s",
            fail_exc,
        )


def _monitoring_action_origin_event_id(
    *,
    state: AgentState,
    entity_id: UUID,
    monitor_mode: str,
    action: str,
    cadence: str,
) -> str:
    run_id = str(state.get("run_id") or "").strip() or "manual"
    return f"monitoring-plan:{run_id}:{entity_id}:{monitor_mode}:{action}:{cadence}"


def _monitoring_ontology_action_type(*, action: str, plan: Any | None) -> str:
    if action in {"pause", "resume", "delete", "update"}:
        return "update_monitoring_plan"
    if action == "upsert" and plan is not None:
        return "update_monitoring_plan"
    return "create_monitoring_plan"


def _monitoring_change_type(action: str) -> str:
    if action == "resume":
        return "activate"
    if action == "delete":
        return "archive"
    if action == "upsert":
        return "update"
    return action


def _monitoring_action_cadence(
    *,
    frequency: ScheduleFrequency | None,
    plan: Any | None,
    schedule: MonitoringSchedule | None,
) -> str:
    if frequency is not None:
        return frequency.value
    plan_frequency = str(getattr(plan, "frequency", "") or "").strip()
    if plan_frequency:
        return plan_frequency
    schedule_frequency = getattr(schedule, "frequency", None)
    if isinstance(schedule_frequency, ScheduleFrequency):
        return schedule_frequency.value
    schedule_frequency_text = str(schedule_frequency or "").strip()
    return schedule_frequency_text or ScheduleFrequency.WEEKLY.value


async def _resolve_monitoring_action_question_ids(
    *,
    db: AsyncSession,
    user_id: UUID,
    entity_id: UUID,
    monitor_mode: str,
    plan: Any | None,
    tool_args: dict[str, Any],
    dashboard_context: dict[str, Any],
    state: AgentState,
) -> list[str]:
    explicit_question_ids = _normalize_string_list(
        _first_value(
            tool_args.get("question_ids"),
            dashboard_context.get("question_ids"),
            state.get("question_ids"),
            state.get("selected_question_ids"),
        )
    )
    if explicit_question_ids:
        return explicit_question_ids

    question_set_ids = [
        parsed
        for parsed in (
            _parse_uuid(item)
            for item in _normalize_string_list(
                _first_value(
                    tool_args.get("question_set_ids"),
                    dashboard_context.get("question_set_ids"),
                    state.get("question_set_ids"),
                    getattr(plan, "question_set_ids", None),
                )
            )
        )
        if parsed is not None
    ]
    question_sets = await _load_monitoring_action_question_sets(
        db=db,
        user_id=user_id,
        entity_id=entity_id,
        monitor_mode=monitor_mode,
        question_set_ids=question_set_ids,
    )
    return _question_ids_from_question_sets(question_sets)


async def _load_monitoring_action_question_sets(
    *,
    db: AsyncSession,
    user_id: UUID,
    entity_id: UUID,
    monitor_mode: str,
    question_set_ids: list[UUID],
) -> list[MonitoringQuestionSet]:
    conditions = [
        MonitoringQuestionSet.user_id == user_id,
        MonitoringQuestionSet.entity_id == entity_id,
        MonitoringQuestionSet.monitor_mode == monitor_mode,
        MonitoringQuestionSet.status == QuestionSetStatus.CONFIRMED.value,
    ]
    if question_set_ids:
        conditions.append(MonitoringQuestionSet.id.in_(question_set_ids))
    statement = select(MonitoringQuestionSet).where(*conditions).order_by(
        desc(MonitoringQuestionSet.updated_at)
    )
    if not question_set_ids:
        statement = statement.limit(1)
    result = await db.execute(statement)
    rows = list(result.scalars().all())
    if question_set_ids:
        by_id = {item.id: item for item in rows}
        return [by_id[item] for item in question_set_ids if item in by_id]
    return rows


def _question_ids_from_question_sets(
    question_sets: list[MonitoringQuestionSet],
) -> list[str]:
    question_ids: list[str] = []
    for question_set in question_sets:
        for question in MonitoringPlanService.normalize_questions(
            question_set.questions or []
        ):
            question_id = str(question.get("question_id") or "").strip()
            if question_id and question_id not in question_ids:
                question_ids.append(question_id)
    return question_ids


def _build_monitoring_action_input_payload(
    *,
    entity_id: UUID,
    question_ids: list[str],
    cadence: str,
    monitor_mode: str,
    plan: Any | None,
    schedule: MonitoringSchedule | None,
    dashboard_context: dict[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "brand_entity_id": str(entity_id),
        "question_ids": question_ids,
        "cadence": cadence,
        "monitor_mode": monitor_mode,
    }
    question_set_ids = _normalize_string_list(
        _first_value(
            dashboard_context.get("question_set_ids"),
            getattr(plan, "question_set_ids", None),
            getattr(schedule, "question_set_ids", None),
        )
    )
    if question_set_ids:
        payload["question_set_ids"] = question_set_ids
    endpoint_ids = _normalize_string_list(
        _first_value(
            dashboard_context.get("endpoint_ids"),
            getattr(plan, "endpoint_ids", None),
            getattr(schedule, "endpoint_ids", None),
        )
    )
    if endpoint_ids:
        payload["endpoint_ids"] = endpoint_ids
    if plan is not None:
        payload["monitoring_plan_id"] = str(plan.id)
    if schedule is not None:
        payload["schedule_id"] = str(schedule.id)
    return payload


def _build_monitoring_update_action_input_payload(
    *,
    entity_id: UUID,
    change_type: str,
    cadence: str,
    monitor_mode: str,
    plan: Any | None,
    schedule: MonitoringSchedule | None,
    dashboard_context: dict[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "brand_entity_id": str(entity_id),
        "monitoring_plan_id": str(plan.id) if plan is not None else "",
        "change_type": change_type,
        "monitor_mode": monitor_mode,
        "cadence": cadence,
    }
    question_set_ids = _normalize_string_list(
        _first_value(
            dashboard_context.get("question_set_ids"),
            getattr(plan, "question_set_ids", None),
            getattr(schedule, "question_set_ids", None),
        )
    )
    if question_set_ids:
        payload["question_set_ids"] = question_set_ids
    endpoint_ids = _normalize_string_list(
        _first_value(
            dashboard_context.get("endpoint_ids"),
            getattr(plan, "endpoint_ids", None),
            getattr(schedule, "endpoint_ids", None),
        )
    )
    if endpoint_ids:
        payload["endpoint_ids"] = endpoint_ids
    if schedule is not None:
        payload["schedule_id"] = str(schedule.id)
    return payload


def _build_monitoring_action_output_payload(
    *,
    plan: Any | None,
    schedule: MonitoringSchedule | None,
    monitor_mode: str,
) -> dict[str, Any]:
    return {
        "monitoring_plan_id": str(plan.id) if plan is not None else None,
        "schedule_id": str(schedule.id) if schedule is not None else None,
        "monitor_mode": monitor_mode,
        "status": (
            str(getattr(plan, "status", "") or getattr(schedule, "status", "") or "")
            or None
        ),
    }


async def _upsert_monitoring(
    plan_service: MonitoringPlanService,
    monitoring_service: MonitoringService,
    *,
    user_id: UUID,
    entity_id: UUID,
    monitor_mode: str,
    dashboard_context: dict[str, Any],
    plan: Any | None,
    schedule: MonitoringSchedule | None,
    frequency: ScheduleFrequency | None,
    preferred_hour: int | None,
    timezone_str: str,
    alert_threshold: float | None,
) -> tuple[Any | None, MonitoringSchedule | None]:
    question_set_ids = [
        parsed
        for parsed in (
            _parse_uuid(item)
            for item in _normalize_string_list(dashboard_context.get("question_set_ids"))
        )
        if parsed is not None
    ]
    endpoint_ids = _normalize_string_list(dashboard_context.get("endpoint_ids"))

    if plan is not None:
        plan = await plan_service.update_plan(
            plan_id=plan.id,
            user_id=user_id,
            status=MonitoringPlanStatus.ACTIVE.value,
            frequency=(frequency.value if frequency is not None else None),
            preferred_hour=preferred_hour,
            timezone_str=timezone_str,
            commit=False,
        )
        schedule = await _find_schedule(
            monitoring_service,
            user_id=user_id,
            entity_id=entity_id,
            monitor_mode=monitor_mode,
            monitoring_plan_id=plan.id,
        )
        if alert_threshold is not None and schedule is not None:
            schedule = await monitoring_service.update_schedule(
                schedule.id,
                alert_threshold_bwvs=alert_threshold,
            )
        return plan, schedule

    if schedule is not None:
        update_kwargs: dict[str, Any] = {"status": ScheduleStatus.ACTIVE}
        if frequency is not None:
            update_kwargs["frequency"] = frequency
        if preferred_hour is not None:
            update_kwargs["preferred_hour"] = preferred_hour
        if timezone_str:
            update_kwargs["timezone"] = timezone_str
        if alert_threshold is not None:
            update_kwargs["alert_threshold_bwvs"] = alert_threshold
        if endpoint_ids:
            update_kwargs["endpoint_ids"] = endpoint_ids
            update_kwargs["platforms"] = _endpoint_ids_to_platforms(endpoint_ids)
        schedule = await monitoring_service.update_schedule(schedule.id, **update_kwargs)
        return None, schedule

    if question_set_ids:
        plan = await plan_service.create_plan(
            user_id=user_id,
            entity_id=entity_id,
            monitor_mode=monitor_mode,
            question_set_ids=question_set_ids,
            endpoint_ids=endpoint_ids or None,
            run_policy="quick",
            status=MonitoringPlanStatus.ACTIVE.value,
            frequency=(frequency.value if frequency is not None else "weekly"),
            preferred_hour=preferred_hour if preferred_hour is not None else 11,
            timezone_str=timezone_str,
            commit=False,
        )
        schedule = await _find_schedule(
            monitoring_service,
            user_id=user_id,
            entity_id=entity_id,
            monitor_mode=monitor_mode,
            monitoring_plan_id=plan.id,
        )
        if alert_threshold is not None and schedule is not None:
            schedule = await monitoring_service.update_schedule(
                schedule.id,
                alert_threshold_bwvs=alert_threshold,
            )
        return plan, schedule

    schedule = await monitoring_service.create_schedule(
        user_id=user_id,
        entity_id=entity_id,
        frequency=frequency or ScheduleFrequency.WEEKLY,
        preferred_hour=preferred_hour if preferred_hour is not None else 11,
        timezone_str=timezone_str,
        alert_threshold_bwvs=alert_threshold if alert_threshold is not None else 10.0,
        status=ScheduleStatus.ACTIVE,
        monitor_mode=monitor_mode,
        endpoint_ids=endpoint_ids or None,
        platforms=_endpoint_ids_to_platforms(endpoint_ids) if endpoint_ids else None,
        run_policy="quick",
    )
    return None, schedule


def _build_action_log_message(
    action: str,
    frequency: ScheduleFrequency | None,
    preferred_hour: int | None,
) -> str:
    if action == "get":
        return "正在查询当前监测计划..."
    if action == "pause":
        return "正在暂停监测计划..."
    if action == "resume":
        return "正在恢复监测计划..."
    if action == "delete":
        return "正在删除监测计划..."
    pieces = ["正在设置监测计划"]
    if frequency is not None:
        pieces.append(FREQ_LABELS.get(frequency.value, frequency.value))
    if preferred_hour is not None:
        pieces.append(f"{preferred_hour:02d}:00")
    return " · ".join(pieces) + "..."


def _build_schedule_reply(
    *,
    prefix: str,
    brand_name: str,
    monitor_mode: str,
    plan: Any | None,
    schedule: MonitoringSchedule | None,
    extra_lines: list[str] | None = None,
) -> str:
    lines = [
        prefix,
        f"- 品牌：{brand_name}",
        f"- 监测类型：{MONITOR_MODE_LABELS[monitor_mode]}",
    ]
    if extra_lines:
        lines.extend(extra_lines)
    if schedule is None:
        lines.append("- 运行设置：当前还没有生成可执行的周期任务。")
        lines.append("可以在看板的持续监测页继续补齐问题集、平台来源和执行时间。")
        return "\n".join(lines)

    lines.extend(
        [
            f"- 状态：{_schedule_status_label(schedule.status)}",
            f"- 执行频率：{FREQ_LABELS.get(schedule.frequency.value, schedule.frequency.value)}",
            f"- 执行时间：{schedule.timezone} {schedule.preferred_hour:02d}:00",
            f"- 下次执行：{_format_next_run(schedule)}",
            f"- 告警阈值：{schedule.alert_threshold_bwvs:g}",
            f"- 平台来源：{_format_platforms(schedule)}",
        ]
    )
    if plan is not None:
        lines.append("- 已绑定新版监测计划，可在看板的持续监测页继续调整。")
    else:
        lines.append("- 当前为旧版周期任务，可在看板的持续监测页继续调整。")
    return "\n".join(lines)


def _build_state_update(
    reply: str,
    *,
    plan: Any | None,
    schedule: MonitoringSchedule | None,
) -> dict[str, Any]:
    update: dict[str, Any] = {"orchestrator_reply": reply}
    if schedule is not None:
        update["monitoring_schedule_id"] = str(schedule.id)
        update["question_set_ids"] = schedule.question_set_ids or None
        update["endpoint_ids"] = schedule.endpoint_ids or None
        update["run_policy"] = schedule.run_policy
    if plan is not None:
        update["monitoring_plan_id"] = str(plan.id)
        update["latest_monitoring_plan_id"] = str(plan.id)
    return update


def _schedule_status_label(status: ScheduleStatus | str | None) -> str:
    value = status.value if isinstance(status, ScheduleStatus) else str(status or "")
    return STATUS_LABELS.get(value, value or "未知")


def _plan_status_label(status: Any) -> str:
    value = str(status or "")
    return {
        "active": "已启用",
        "paused": "已暂停",
        "draft": "草稿",
        "archived": "已归档",
    }.get(value, value or "未知")


def _format_next_run(schedule: MonitoringSchedule) -> str:
    if schedule.next_run_at is None:
        return "未安排"
    return schedule.next_run_at.strftime("%Y-%m-%d %H:%M UTC")


def _format_platforms(schedule: MonitoringSchedule) -> str:
    values = schedule.endpoint_ids or schedule.platforms or []
    if not values:
        return "按默认来源"
    return "、".join(PLATFORM_LABELS.get(str(item), str(item)) for item in values)


async def _resolve_user_id(db: AsyncSession, session_id: str) -> UUID | None:
    """Resolve user_id from the session record."""

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
