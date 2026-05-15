import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{Path(__file__).resolve().parent / 'test_monitoring_plan.db'}",
)

from app.core.database import Base
from app.models.entity import Entity, EntityStatus
from app.models.monitoring_plan import MonitoringPlanStatus, QuestionSetStatus
from app.models.monitoring_schedule import MonitoringSchedule, ScheduleStatus
from app.models.session import Session, SessionStatus
from app.models.user import User, UserRole, UserStatus
from app.services.monitoring_plan_service import (
    QUICK_ENDPOINT_IDS,
    MonitoringPlanService,
)
from app.services.scheduler import resolve_monitoring_chat_session
from app.services.session_service import SessionService


async def _build_session(tmp_path):
    db_path = tmp_path / "monitoring-plan.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, session_factory


@pytest.mark.asyncio
async def test_draft_question_set_cannot_activate_plan(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            email="owner@example.com",
            is_active=True,
            status=UserStatus.ACTIVE,
            role=UserRole.CUSTOMER_USER,
        )
        entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="example.com",
            industry="品牌智能",
            description="测试品牌",
            status=EntityStatus.ACTIVE,
            owner_user_id=user.id,
        )
        session.add_all([user, entity])
        await session.commit()

        service = MonitoringPlanService(session)
        question_set = await service.create_question_set(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            questions=["AI 怎么评价品牌智能平台？"],
        )

        with pytest.raises(ValueError, match="必须先由用户确认"):
            await service.create_plan(
                user_id=user.id,
                entity_id=entity.id,
                monitor_mode="panorama",
                question_set_ids=[question_set.id],
                status=MonitoringPlanStatus.ACTIVE.value,
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_full_browser_bridge_does_not_confirm_draft_question_set(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            email="owner-full@example.com",
            is_active=True,
            status=UserStatus.ACTIVE,
            role=UserRole.CUSTOMER_USER,
        )
        entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="example.com",
            industry="品牌智能",
            description="测试品牌",
            status=EntityStatus.ACTIVE,
            owner_user_id=user.id,
        )
        session.add_all([user, entity])
        await session.commit()

        service = MonitoringPlanService(session)
        question_set = await service.create_question_set(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            questions=["AI 怎么评价品牌智能平台？"],
        )

        with pytest.raises(ValueError, match="v1 自动监测只支持快速监测"):
            await service.create_or_update_active_plan_from_question_set(
                user_id=user.id,
                entity_id=entity.id,
                question_set_id=question_set.id,
                monitor_mode="panorama",
                fetch_mode="full",
            )

        await session.refresh(question_set)
        assert question_set.status == QuestionSetStatus.DRAFT.value
    await engine.dispose()


@pytest.mark.asyncio
async def test_bridge_rejects_cross_entity_question_set_without_confirming(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            email="owner-cross@example.com",
            is_active=True,
            status=UserStatus.ACTIVE,
            role=UserRole.CUSTOMER_USER,
        )
        source_entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="example.com",
            industry="品牌智能",
            description="测试品牌",
            status=EntityStatus.ACTIVE,
            owner_user_id=user.id,
        )
        target_entity = Entity(
            id=uuid.uuid4(),
            name="Another",
            domain="another.example.com",
            industry="品牌智能",
            description="另一个品牌",
            status=EntityStatus.ACTIVE,
            owner_user_id=user.id,
        )
        session.add_all([user, source_entity, target_entity])
        await session.commit()

        service = MonitoringPlanService(session)
        question_set = await service.create_question_set(
            user_id=user.id,
            entity_id=source_entity.id,
            monitor_mode="panorama",
            questions=["AI 怎么评价品牌智能平台？"],
        )

        with pytest.raises(ValueError, match="不属于当前品牌"):
            await service.create_or_update_active_plan_from_question_set(
                user_id=user.id,
                entity_id=target_entity.id,
                question_set_id=question_set.id,
                monitor_mode="panorama",
                fetch_mode="fast",
            )

        await session.refresh(question_set)
        assert question_set.status == QuestionSetStatus.DRAFT.value
    await engine.dispose()


@pytest.mark.asyncio
async def test_confirmed_question_set_creates_active_plan_and_schedule(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            email="owner2@example.com",
            is_active=True,
            status=UserStatus.ACTIVE,
            role=UserRole.CUSTOMER_USER,
        )
        entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="example.com",
            industry="品牌智能",
            description="测试品牌",
            status=EntityStatus.ACTIVE,
            owner_user_id=user.id,
        )
        session.add_all([user, entity])
        await session.commit()

        service = MonitoringPlanService(session)
        question_set = await service.create_question_set(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="scenario_monitoring",
            questions=[
                {
                    "id": "s1",
                    "text": "预算有限时怎么选择品牌智能监测工具？",
                    "category": "购买决策",
                }
            ],
        )
        await service.confirm_question_set(
            question_set_id=question_set.id,
            user_id=user.id,
        )
        plan = await service.create_plan(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="persona",
            question_set_ids=[question_set.id],
            endpoint_ids=list(QUICK_ENDPOINT_IDS),
            status=MonitoringPlanStatus.ACTIVE.value,
        )

        plan_payload = await service.plan_to_dict(plan)
        schedule = (
            await session.execute(
                select(MonitoringSchedule).where(
                    MonitoringSchedule.monitoring_plan_id == plan.id
                )
            )
        ).scalar_one()

        assert plan.monitor_mode == "scenario"
        assert plan_payload["endpoint_labels"] == [
            "豆包API",
            "元宝API",
            "Kimi API",
            "DeepSeek网页版",
        ]
        assert schedule.monitor_mode == "scenario"
        assert schedule.baseline_data["questions"][0]["text"] == (
            "预算有限时怎么选择品牌智能监测工具？"
        )
    await engine.dispose()


@pytest.mark.asyncio
async def test_active_plan_carries_source_session_into_schedule_baseline(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            email="owner-source@example.com",
            is_active=True,
            status=UserStatus.ACTIVE,
            role=UserRole.CUSTOMER_USER,
        )
        entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="example.com",
            industry="品牌智能",
            description="测试品牌",
            status=EntityStatus.ACTIVE,
            owner_user_id=user.id,
        )
        source_session = Session(
            id=uuid.uuid4(),
            user_id=user.id,
            entity_id=entity.id,
            title="Specta",
            status=SessionStatus.ACTIVE,
        )
        session.add_all([user, entity, source_session])
        await session.commit()

        service = MonitoringPlanService(session)
        question_set = await service.create_question_set(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            questions=["AI 怎么评价品牌智能平台？"],
            source_session_id=source_session.id,
        )
        await service.confirm_question_set(
            question_set_id=question_set.id,
            user_id=user.id,
        )
        plan = await service.create_plan(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            question_set_ids=[question_set.id],
            status=MonitoringPlanStatus.ACTIVE.value,
        )

        schedule = (
            await session.execute(
                select(MonitoringSchedule).where(
                    MonitoringSchedule.monitoring_plan_id == plan.id
                )
            )
        ).scalar_one()

        assert plan.extra_metadata["source_session_id"] == str(source_session.id)
        assert schedule.baseline_data["source_session_id"] == str(source_session.id)
    await engine.dispose()


@pytest.mark.asyncio
async def test_monitoring_resolves_source_chat_instead_of_monitoring_session(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            email="owner-resolve@example.com",
            is_active=True,
            status=UserStatus.ACTIVE,
            role=UserRole.CUSTOMER_USER,
        )
        entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="example.com",
            industry="品牌智能",
            description="测试品牌",
            status=EntityStatus.ACTIVE,
            owner_user_id=user.id,
        )
        source_session = Session(
            id=uuid.uuid4(),
            user_id=user.id,
            entity_id=entity.id,
            title="Specta",
            status=SessionStatus.ACTIVE,
        )
        old_monitoring_session = Session(
            id=uuid.uuid4(),
            user_id=user.id,
            entity_id=entity.id,
            title="Specta 自动监测",
            status=SessionStatus.ACTIVE,
            extra_metadata='{"source":"monitoring"}',
        )
        session.add_all([user, entity, source_session, old_monitoring_session])
        await session.commit()

        service = MonitoringPlanService(session)
        question_set = await service.create_question_set(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            questions=["AI 怎么评价品牌智能平台？"],
            source_session_id=source_session.id,
        )
        await service.confirm_question_set(
            question_set_id=question_set.id,
            user_id=user.id,
        )
        plan = await service.create_plan(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            question_set_ids=[question_set.id],
            status=MonitoringPlanStatus.ACTIVE.value,
        )
        schedule = (
            await session.execute(
                select(MonitoringSchedule).where(
                    MonitoringSchedule.monitoring_plan_id == plan.id
                )
            )
        ).scalar_one()

        resolved = await resolve_monitoring_chat_session(
            session,
            schedule_id=schedule.id,
            user_id=user.id,
            entity_id=entity.id,
            entity_name=entity.name,
            schedule=schedule,
        )

        assert resolved.id == source_session.id
    await engine.dispose()


@pytest.mark.asyncio
async def test_entity_session_lookup_ignores_legacy_monitoring_session(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            email="owner-session@example.com",
            is_active=True,
            status=UserStatus.ACTIVE,
            role=UserRole.CUSTOMER_USER,
        )
        entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="example.com",
            industry="品牌智能",
            description="测试品牌",
            status=EntityStatus.ACTIVE,
            owner_user_id=user.id,
        )
        old_monitoring_session = Session(
            id=uuid.uuid4(),
            user_id=user.id,
            entity_id=entity.id,
            title="Specta 自动监测",
            status=SessionStatus.ACTIVE,
            extra_metadata='{"source":"monitoring"}',
        )
        session.add_all([user, entity, old_monitoring_session])
        await session.commit()

        resolved = await SessionService(session).get_latest_session_by_entity(
            entity.id,
            user,
            allow_internal_admin_bypass=False,
        )

        assert resolved is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_session_list_excludes_legacy_monitoring_sessions(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            email="owner-list@example.com",
            is_active=True,
            status=UserStatus.ACTIVE,
            role=UserRole.CUSTOMER_USER,
        )
        entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="example.com",
            industry="品牌智能",
            description="测试品牌",
            status=EntityStatus.ACTIVE,
            owner_user_id=user.id,
        )
        normal_session = Session(
            id=uuid.uuid4(),
            user_id=user.id,
            entity_id=entity.id,
            title="Specta",
            status=SessionStatus.ACTIVE,
        )
        old_monitoring_session = Session(
            id=uuid.uuid4(),
            user_id=user.id,
            entity_id=entity.id,
            title="Specta 自动监测",
            status=SessionStatus.ACTIVE,
            extra_metadata='{ "source" :  "monitoring" }',
        )
        session.add_all([user, entity, normal_session, old_monitoring_session])
        await session.commit()

        result = await SessionService(session).list_sessions(
            viewer=user,
            allow_internal_admin_bypass=False,
        )

        assert result["total"] == 1
        assert [item["id"] for item in result["sessions"]] == [str(normal_session.id)]
    await engine.dispose()


@pytest.mark.asyncio
async def test_multiple_active_plans_keep_independent_schedules(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            email="owner-independent@example.com",
            is_active=True,
            status=UserStatus.ACTIVE,
            role=UserRole.CUSTOMER_USER,
        )
        entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="example.com",
            industry="品牌智能",
            description="测试品牌",
            status=EntityStatus.ACTIVE,
            owner_user_id=user.id,
        )
        session.add_all([user, entity])
        await session.commit()

        service = MonitoringPlanService(session)
        first_question_set = await service.create_question_set(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            questions=["AI 怎么评价品牌智能平台？"],
        )
        second_question_set = await service.create_question_set(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            questions=["品牌智能平台适合哪些团队？"],
        )
        await service.confirm_question_set(
            question_set_id=first_question_set.id,
            user_id=user.id,
        )
        await service.confirm_question_set(
            question_set_id=second_question_set.id,
            user_id=user.id,
        )

        first_plan = await service.create_plan(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            question_set_ids=[first_question_set.id],
            status=MonitoringPlanStatus.ACTIVE.value,
            title="全景监测计划 A",
        )
        second_plan = await service.create_plan(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            question_set_ids=[second_question_set.id],
            status=MonitoringPlanStatus.ACTIVE.value,
            title="全景监测计划 B",
        )

        schedules = list(
            (
                await session.execute(
                    select(MonitoringSchedule).where(
                        MonitoringSchedule.entity_id == entity.id,
                        MonitoringSchedule.monitor_mode == "panorama",
                        MonitoringSchedule.status == ScheduleStatus.ACTIVE,
                    )
                )
            ).scalars()
        )

        assert {schedule.monitoring_plan_id for schedule in schedules} == {
            first_plan.id,
            second_plan.id,
        }
        assert len(schedules) == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_entity_plan_prefers_active_plan_over_newer_draft(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            email="owner-active-priority@example.com",
            is_active=True,
            status=UserStatus.ACTIVE,
            role=UserRole.CUSTOMER_USER,
        )
        entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="example.com",
            industry="品牌智能",
            description="测试品牌",
            status=EntityStatus.ACTIVE,
            owner_user_id=user.id,
        )
        session.add_all([user, entity])
        await session.commit()

        service = MonitoringPlanService(session)
        active_question_set = await service.create_question_set(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="scenario",
            questions=["预算有限时怎么选择品牌智能监测工具？"],
        )
        draft_question_set = await service.create_question_set(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="scenario",
            questions=["品牌智能监测适合哪些业务场景？"],
        )
        await service.confirm_question_set(
            question_set_id=active_question_set.id,
            user_id=user.id,
        )

        active_plan = await service.create_plan(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="scenario",
            question_set_ids=[active_question_set.id],
            status=MonitoringPlanStatus.ACTIVE.value,
        )
        await service.create_plan(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="scenario",
            question_set_ids=[draft_question_set.id],
            status=MonitoringPlanStatus.DRAFT.value,
        )

        current_plan = await service.get_entity_plan(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="persona",
        )

        assert current_plan is not None
        assert current_plan.id == active_plan.id
        assert current_plan.status == MonitoringPlanStatus.ACTIVE.value
    await engine.dispose()


@pytest.mark.asyncio
async def test_question_set_confirmation_contract_activates_quick_plan(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            email="owner-confirm@example.com",
            is_active=True,
            status=UserStatus.ACTIVE,
            role=UserRole.CUSTOMER_USER,
        )
        entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="example.com",
            industry="品牌智能",
            description="测试品牌",
            status=EntityStatus.ACTIVE,
            owner_user_id=user.id,
        )
        session.add_all([user, entity])
        await session.commit()

        service = MonitoringPlanService(session)
        question_set = await service.create_question_set(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            questions=["AI 怎么评价品牌智能平台？"],
        )

        plan = await service.confirm_question_set_and_activate_quick_plan(
            user_id=user.id,
            entity_id=entity.id,
            question_set_id=question_set.id,
            monitor_mode="panorama_monitoring",
        )
        await session.refresh(question_set)

        assert question_set.status == QuestionSetStatus.CONFIRMED.value
        assert plan.status == MonitoringPlanStatus.ACTIVE.value
        assert plan.endpoint_ids == list(QUICK_ENDPOINT_IDS)
    await engine.dispose()


@pytest.mark.asyncio
async def test_append_questions_blocks_over_thirty_without_mutating_draft(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            email="owner-append@example.com",
            is_active=True,
            status=UserStatus.ACTIVE,
            role=UserRole.CUSTOMER_USER,
        )
        entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="example.com",
            industry="品牌智能",
            description="测试品牌",
            status=EntityStatus.ACTIVE,
            owner_user_id=user.id,
        )
        session.add_all([user, entity])
        await session.commit()

        service = MonitoringPlanService(session)
        question_set = await service.create_question_set(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            questions=[f"问题 {index}" for index in range(29)],
        )

        with pytest.raises(ValueError, match="最多支持 30 个问题"):
            await service.append_questions(
                question_set_id=question_set.id,
                user_id=user.id,
                questions=["新增 1", "新增 2"],
            )

        await session.refresh(question_set)
        assert question_set.question_count == 29
    await engine.dispose()


@pytest.mark.asyncio
async def test_declined_question_set_has_no_active_plan(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            email="owner-decline@example.com",
            is_active=True,
            status=UserStatus.ACTIVE,
            role=UserRole.CUSTOMER_USER,
        )
        entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="example.com",
            industry="品牌智能",
            description="测试品牌",
            status=EntityStatus.ACTIVE,
            owner_user_id=user.id,
        )
        session.add_all([user, entity])
        await session.commit()

        service = MonitoringPlanService(session)
        await service.create_question_set(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            questions=["AI 怎么评价品牌智能平台？"],
        )
        plan = await service.get_entity_plan(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
        )

        assert plan is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_question_limit_blocks_more_than_thirty(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            email="owner3@example.com",
            is_active=True,
            status=UserStatus.ACTIVE,
            role=UserRole.CUSTOMER_USER,
        )
        entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="example.com",
            industry="品牌智能",
            description="测试品牌",
            status=EntityStatus.ACTIVE,
            owner_user_id=user.id,
        )
        session.add_all([user, entity])
        await session.commit()

        service = MonitoringPlanService(session)
        with pytest.raises(ValueError, match="最多支持 30 个问题"):
            await service.create_question_set(
                user_id=user.id,
                entity_id=entity.id,
                monitor_mode="panorama",
                questions=[f"问题 {index}" for index in range(31)],
            )
    await engine.dispose()
