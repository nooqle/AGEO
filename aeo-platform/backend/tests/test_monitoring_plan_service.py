import os
from pathlib import Path
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{Path(__file__).resolve().parent / 'test_monitoring_plan.db'}",
)

from app.core.database import Base
import app.api.v1.monitoring as monitoring_api
from app.api.v1.monitoring import _record_monitoring_user_action, archive_monitoring_plan
from app.models.brand_intelligence import (
    BrandActionRecord,
    BrandIntelligenceQuestion,
    BrandObjectLink,
    BrandUserDecision,
)
from app.models.entity import Entity, EntityStatus
from app.models.monitoring_plan import MonitoringPlanStatus, QuestionSetStatus
from app.models.monitoring_schedule import MonitoringSchedule, ScheduleStatus
from app.models.user import User, UserRole, UserStatus
from app.services.monitoring_plan_service import (
    MonitoringPlanService,
    QUICK_ENDPOINT_IDS,
)


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
        link_rows = (await session.execute(select(BrandObjectLink))).scalars().all()
        question_rows = (
            await session.execute(select(BrandIntelligenceQuestion))
        ).scalars().all()
        link_types = {row.link_type for row in link_rows}
        assert len(question_rows) == 1
        assert {
            "monitoring_plan_uses_question_set",
            "question_set_contains_question",
            "monitoring_plan_tracks_question",
        }.issubset(link_types)
        assert any(
            row.link_type == "monitoring_plan_tracks_question"
            and row.from_object_id == str(plan.id)
            and row.to_object_id == str(question_rows[0].id)
            for row in link_rows
        )
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
async def test_updating_active_plan_replaces_monitoring_question_links(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            email="owner-replace-links@example.com",
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
            questions=[{"id": "first", "text": "第一组问题？"}],
        )
        second_question_set = await service.create_question_set(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            questions=[{"id": "second", "text": "第二组问题？"}],
        )
        first_plan = await service.confirm_question_set_and_activate_quick_plan(
            user_id=user.id,
            entity_id=entity.id,
            question_set_id=first_question_set.id,
            monitor_mode="panorama",
        )
        second_plan = await service.confirm_question_set_and_activate_quick_plan(
            user_id=user.id,
            entity_id=entity.id,
            question_set_id=second_question_set.id,
            monitor_mode="panorama",
        )
        replayed_plan = await service.confirm_question_set_and_activate_quick_plan(
            user_id=user.id,
            entity_id=entity.id,
            question_set_id=second_question_set.id,
            monitor_mode="panorama",
        )

        assert second_plan.id == first_plan.id
        assert replayed_plan.id == first_plan.id
        tracking_links = (
            await session.execute(
                select(BrandObjectLink).where(
                    BrandObjectLink.link_type == "monitoring_plan_tracks_question",
                    BrandObjectLink.from_object_id == str(second_plan.id),
                )
            )
        ).scalars().all()
        assert len(tracking_links) == 1
        assert tracking_links[0].extra_metadata["question_set_id"] == str(
            second_question_set.id
        )
        question_rows = (
            await session.execute(select(BrandIntelligenceQuestion))
        ).scalars().all()
        assert len(question_rows) == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_plan_refreshes_monitoring_question_links(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            email="owner-update-plan-links@example.com",
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
            questions=[{"id": "first", "text": "第一组问题？"}],
        )
        second_question_set = await service.create_question_set(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            questions=[{"id": "second", "text": "第二组问题？"}],
        )
        await service.confirm_question_set(
            question_set_id=first_question_set.id,
            user_id=user.id,
        )
        await service.confirm_question_set(
            question_set_id=second_question_set.id,
            user_id=user.id,
        )
        plan = await service.create_plan(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            question_set_ids=[first_question_set.id],
            status=MonitoringPlanStatus.ACTIVE.value,
        )

        updated_plan = await service.update_plan(
            plan_id=plan.id,
            user_id=user.id,
            question_set_ids=[second_question_set.id],
        )
        replayed_plan = await service.update_plan(
            plan_id=plan.id,
            user_id=user.id,
            question_set_ids=[second_question_set.id],
        )

        assert updated_plan.id == plan.id
        assert replayed_plan.id == plan.id
        plan_question_set_links = (
            await session.execute(
                select(BrandObjectLink).where(
                    BrandObjectLink.link_type == "monitoring_plan_uses_question_set",
                    BrandObjectLink.from_object_id == str(plan.id),
                )
            )
        ).scalars().all()
        tracking_links = (
            await session.execute(
                select(BrandObjectLink).where(
                    BrandObjectLink.link_type == "monitoring_plan_tracks_question",
                    BrandObjectLink.from_object_id == str(plan.id),
                )
            )
        ).scalars().all()
        question_rows = (
            await session.execute(select(BrandIntelligenceQuestion))
        ).scalars().all()

        assert len(plan_question_set_links) == 1
        assert plan_question_set_links[0].to_object_id == str(second_question_set.id)
        assert len(tracking_links) == 1
        assert tracking_links[0].extra_metadata["question_set_id"] == str(
            second_question_set.id
        )
        assert len(question_rows) == 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_monitoring_plan_user_action_links_action_to_plan(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            email="owner-action-plan-link@example.com",
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
            questions=[{"id": "first", "text": "第一组问题？"}],
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

        action_id = await _record_monitoring_user_action(
            session,
            current_user=user,
            entity_id=entity.id,
            action_type="update_monitoring_plan",
            origin_event_id=f"{plan.id}:pause-test",
            input_payload={
                "actor_id": str(user.id),
                "monitoring_plan_id": str(plan.id),
                "change_type": "pause",
            },
            output_payload={
                "monitoring_plan_id": str(plan.id),
                "status": MonitoringPlanStatus.PAUSED.value,
                "change_type": "pause",
            },
            target_object_type="monitoring_plan",
            target_object_id=str(plan.id),
        )

        record = await session.get(BrandActionRecord, uuid.UUID(str(action_id)))
        decision = (await session.execute(select(BrandUserDecision))).scalar_one()
        link = (
            await session.execute(
                select(BrandObjectLink).where(
                    BrandObjectLink.link_type
                    == "action_record_handles_monitoring_plan",
                    BrandObjectLink.from_object_id == str(action_id),
                    BrandObjectLink.to_object_id == str(plan.id),
                )
            )
        ).scalar_one()

        assert record is not None
        assert record.action_type == "update_monitoring_plan"
        assert record.input_payload["change_type"] == "pause"
        assert decision.target_object_type == "monitoring_plan"
        assert decision.target_object_id == str(plan.id)
        assert link.source_action_record_id == record.id
    await engine.dispose()


@pytest.mark.asyncio
async def test_archive_plan_moves_lifecycle_and_pauses_schedule(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            email="owner-archive-plan@example.com",
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
            questions=[{"id": "first", "text": "第一组问题？"}],
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

        archived_plan = await service.archive_plan(plan_id=plan.id, user_id=user.id)
        schedule = (
            await session.execute(
                select(MonitoringSchedule).where(
                    MonitoringSchedule.monitoring_plan_id == plan.id
                )
            )
        ).scalar_one()

        assert archived_plan.status == MonitoringPlanStatus.ARCHIVED.value
        assert schedule.status == ScheduleStatus.PAUSED
        assert schedule.next_run_at is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_archive_monitoring_plan_api_records_lifecycle_action(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            email="owner-archive-plan-api@example.com",
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
            questions=[{"id": "first", "text": "第一组问题？"}],
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

        response = await archive_monitoring_plan(
            plan_id=str(plan.id),
            current_user=user,
            db=session,
        )
        record = (
            await session.execute(
                select(BrandActionRecord).where(
                    BrandActionRecord.entity_id == entity.id,
                    BrandActionRecord.action_type == "update_monitoring_plan",
                )
            )
        ).scalar_one()
        link = (
            await session.execute(
                select(BrandObjectLink).where(
                    BrandObjectLink.link_type
                    == "action_record_handles_monitoring_plan",
                    BrandObjectLink.from_object_id == str(record.id),
                    BrandObjectLink.to_object_id == str(plan.id),
                )
            )
        ).scalar_one()

        assert response["plan"]["status"] == MonitoringPlanStatus.ARCHIVED.value
        assert record.input_payload["change_type"] == "archive"
        assert record.output_payload["status"] == MonitoringPlanStatus.ARCHIVED.value
        assert link.source_action_record_id == record.id
    await engine.dispose()


@pytest.mark.asyncio
async def test_archive_monitoring_plan_rolls_back_when_action_record_fails(
    tmp_path,
    monkeypatch,
):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            email="owner-archive-rollback@example.com",
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
            questions=[{"id": "first", "text": "第一组问题？"}],
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
        plan_id = plan.id
        user_id = user.id
        entity_id = entity.id

        class FailingActionService:
            def __init__(self, db):
                self.db = db

            async def record_applied_action(self, **kwargs):
                raise RuntimeError("action ledger unavailable")

        monkeypatch.setattr(
            monitoring_api,
            "BrandActionService",
            FailingActionService,
        )

        with pytest.raises(HTTPException) as exc_info:
            await archive_monitoring_plan(
                plan_id=str(plan_id),
                current_user=user,
                db=session,
            )

        assert exc_info.value.status_code == 500
        refetched_plan = await service.get_plan(plan_id, user_id=user_id)
        assert refetched_plan is not None
        assert refetched_plan.status == MonitoringPlanStatus.ACTIVE.value
        schedule = (
            await session.execute(
                select(MonitoringSchedule).where(
                    MonitoringSchedule.monitoring_plan_id == plan_id,
                )
            )
        ).scalar_one()
        assert schedule.status == ScheduleStatus.ACTIVE
        records = (
            await session.execute(
                select(BrandActionRecord).where(
                    BrandActionRecord.entity_id == entity_id,
                    BrandActionRecord.action_type == "update_monitoring_plan",
                )
            )
        ).scalars().all()
        assert records == []
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
