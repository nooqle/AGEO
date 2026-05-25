from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.monitoring_schedule import ScheduleFrequency, ScheduleStatus
from app.workflow.nodes_monitoring import (
    _build_monitoring_action_input_payload,
    _build_monitoring_update_action_input_payload,
    _build_schedule_reply,
    _monitoring_action_cadence,
    _monitoring_change_type,
    _monitoring_ontology_action_type,
    _find_schedule,
    _normalize_action,
    _resolve_monitor_mode,
)
from app.workflow.orchestrator_node import (
    AGENT_REGISTRY,
    TOOL_TO_NODE,
    _build_context_summary,
)


def _tool_by_name(name: str) -> dict:
    return next(item for item in AGENT_REGISTRY if item["name"] == name)


def test_monitoring_tool_surface_supports_manage_actions() -> None:
    tool = _tool_by_name("manage_monitoring_schedule")

    assert TOOL_TO_NODE["manage_monitoring_schedule"] == "create_monitoring"
    assert TOOL_TO_NODE["create_monitoring_schedule"] == "create_monitoring"
    assert "只支持创建" not in tool["description"]
    assert "不能回答'只能创建、无法修改'" in tool["description"]
    assert tool["parameters"]["properties"]["action"]["enum"] == [
        "get",
        "upsert",
        "update",
        "pause",
        "resume",
        "delete",
    ]


def test_context_summary_advertises_monitoring_manager() -> None:
    summary = _build_context_summary({"entity_id": str(uuid4())})

    assert "manage_monitoring_schedule" in summary
    assert "可查询、创建或调整周期监测计划" in summary
    assert "create_monitoring_schedule (可创建定时监测计划)" not in summary


def test_monitoring_action_and_mode_normalization() -> None:
    assert _normalize_action("adjust") == "upsert"
    assert _normalize_action("modify") == "update"
    assert _normalize_action("query") == "get"
    assert _normalize_action("unknown") == "upsert"
    assert (
        _resolve_monitor_mode(
            {},
            {},
            {"monitor_mode": "scenario_monitoring"},
        )
        == "scenario"
    )


def test_monitoring_action_payload_contains_required_ontology_inputs() -> None:
    entity_id = uuid4()
    plan = SimpleNamespace(
        id=uuid4(),
        question_set_ids=["qs-1"],
        endpoint_ids=["kimi_api"],
    )

    payload = _build_monitoring_action_input_payload(
        entity_id=entity_id,
        question_ids=["q1", "q2"],
        cadence="weekly",
        monitor_mode="panorama",
        plan=plan,
        schedule=None,
        dashboard_context={},
    )

    assert payload["brand_entity_id"] == str(entity_id)
    assert payload["question_ids"] == ["q1", "q2"]
    assert payload["cadence"] == "weekly"
    assert payload["monitor_mode"] == "panorama"
    assert payload["question_set_ids"] == ["qs-1"]
    assert payload["endpoint_ids"] == ["kimi_api"]
    assert payload["monitoring_plan_id"] == str(plan.id)


def test_monitoring_lifecycle_action_payload_targets_existing_plan() -> None:
    entity_id = uuid4()
    plan = SimpleNamespace(
        id=uuid4(),
        question_set_ids=["qs-1"],
        endpoint_ids=["kimi_api"],
    )
    schedule = SimpleNamespace(id=uuid4(), question_set_ids=[], endpoint_ids=[])

    assert _monitoring_ontology_action_type(action="upsert", plan=None) == (
        "create_monitoring_plan"
    )
    assert _monitoring_ontology_action_type(action="pause", plan=plan) == (
        "update_monitoring_plan"
    )
    assert _monitoring_change_type("resume") == "activate"
    assert _monitoring_change_type("delete") == "archive"

    payload = _build_monitoring_update_action_input_payload(
        entity_id=entity_id,
        change_type="pause",
        cadence="weekly",
        monitor_mode="panorama",
        plan=plan,
        schedule=schedule,
        dashboard_context={},
    )

    assert payload["brand_entity_id"] == str(entity_id)
    assert payload["monitoring_plan_id"] == str(plan.id)
    assert payload["change_type"] == "pause"
    assert payload["cadence"] == "weekly"
    assert payload["question_set_ids"] == ["qs-1"]
    assert payload["endpoint_ids"] == ["kimi_api"]
    assert payload["schedule_id"] == str(schedule.id)


def test_monitoring_action_cadence_prefers_explicit_frequency() -> None:
    schedule = SimpleNamespace(frequency=ScheduleFrequency.MONTHLY)
    plan = SimpleNamespace(frequency="weekly")

    assert (
        _monitoring_action_cadence(
            frequency=ScheduleFrequency.DAILY,
            plan=plan,
            schedule=schedule,
        )
        == "daily"
    )
    assert (
        _monitoring_action_cadence(
            frequency=None,
            plan=plan,
            schedule=schedule,
        )
        == "weekly"
    )


@pytest.mark.asyncio
async def test_find_schedule_prefers_plan_match_then_active() -> None:
    user_id = uuid4()
    entity_id = uuid4()
    plan_id = uuid4()
    paused_plan_schedule = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        entity_id=entity_id,
        monitoring_plan_id=plan_id,
        status=ScheduleStatus.PAUSED,
    )
    active_other_schedule = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        entity_id=entity_id,
        monitoring_plan_id=uuid4(),
        status=ScheduleStatus.ACTIVE,
    )

    class FakeService:
        async def get_schedule(self, schedule_id):
            return None

        async def list_schedules(self, *args, **kwargs):
            return [active_other_schedule, paused_plan_schedule], 2

    assert (
        await _find_schedule(
            FakeService(),
            user_id=user_id,
            entity_id=entity_id,
            monitor_mode="panorama",
            monitoring_plan_id=plan_id,
        )
        is paused_plan_schedule
    )
    assert (
        await _find_schedule(
            FakeService(),
            user_id=user_id,
            entity_id=entity_id,
            monitor_mode="panorama",
        )
        is active_other_schedule
    )


def test_schedule_reply_uses_supported_frequency_and_hour_only() -> None:
    schedule = SimpleNamespace(
        id=uuid4(),
        frequency=ScheduleFrequency.MONTHLY,
        status=ScheduleStatus.ACTIVE,
        preferred_hour=11,
        timezone="Asia/Shanghai",
        next_run_at=None,
        alert_threshold_bwvs=10.0,
        endpoint_ids=["doubao_api", "yuanbao_api"],
        platforms=None,
        question_set_ids=[],
        run_policy="quick",
    )

    reply = _build_schedule_reply(
        prefix="监测计划已更新。",
        brand_name="纽崔莱",
        monitor_mode="panorama",
        plan=SimpleNamespace(id=uuid4()),
        schedule=schedule,
    )

    assert "执行频率：每月" in reply
    assert "执行时间：Asia/Shanghai 11:00" in reply
    assert "每月 1 日" not in reply
    assert "每月1日" not in reply
