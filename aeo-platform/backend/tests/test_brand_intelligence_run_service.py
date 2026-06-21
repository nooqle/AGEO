from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{Path(__file__).resolve().parent / 'test_brand_intelligence_run.db'}",
)

from app.core.database import Base
from app.models.brand_intelligence_run import (
    BrandIntelligenceRunStatus,
)
from app.models.entity import Entity, EntityStatus
from app.models.snapshot import AnalysisSnapshot, SnapshotStatus
from app.models.task import AnalysisTask, TaskStatus
from app.models.task_run import (
    ExecutorKind,
    TaskRun,
    TaskRunKind,
    TaskRunStatus,
    TaskTriggerSource,
)
from app.models.user import User, UserRole, UserStatus
from app.services.brand_intelligence_run_service import (
    BrandIntelligenceRunService,
    _build_brand_run_initial_state,
)
from app.services.snapshot_service import SnapshotService


async def _build_session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'run.db'}")
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, session_factory


def _user(email: str) -> User:
    return User(
        id=uuid.uuid4(),
        email=email,
        is_active=True,
        status=UserStatus.ACTIVE,
        role=UserRole.CUSTOMER_USER,
    )


@pytest.mark.asyncio
async def test_create_run_reuses_active_run(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("run-owner@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="理想汽车",
            domain="li.auto",
            industry="新能源汽车",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        session.add_all([owner, entity])
        await session.commit()

        service = BrandIntelligenceRunService(session)
        first = await service.create_or_reuse_run(
            entity_id=entity.id,
            current_user=owner,
            run_goal="分析品牌表现",
            analysis_mode="panorama",
            input_scope={"platforms": ["doubao"]},
            origin_event_id="dashboard:start:li",
        )
        second = await service.create_or_reuse_run(
            entity_id=entity.id,
            current_user=owner,
            run_goal="再次开始",
            analysis_mode="panorama",
            input_scope={"question_count": 12},
            origin_event_id="dashboard:start:li-2",
        )

        assert second.id == first.id
        assert second.status == BrandIntelligenceRunStatus.PLANNING_QUESTIONS.value
        assert second.input_scope["platforms"] == ["doubao"]
        assert second.input_scope["question_count"] == 12

    await engine.dispose()


@pytest.mark.asyncio
async def test_cancel_run_cancels_linked_task_run(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("run-cancel-task-owner@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="理想汽车",
            domain="li.auto",
            industry="新能源汽车",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        session.add_all([owner, entity])
        await session.commit()

        service = BrandIntelligenceRunService(session)
        run = await service.create_or_reuse_run(
            entity_id=entity.id,
            current_user=owner,
            run_goal=None,
            analysis_mode="panorama",
        )
        task = AnalysisTask(
            id=uuid.uuid4(),
            user_id=owner.id,
            session_id=None,
            entity_id=entity.id,
            brand_name=entity.name,
            status=TaskStatus.RUNNING,
            current_stage="A4",
            progress=0.55,
            progress_message="running",
        )
        task_run = TaskRun(
            id=uuid.uuid4(),
            task_id=task.id,
            run_kind=TaskRunKind.INITIAL,
            trigger_source=TaskTriggerSource.MESSAGES_API,
            executor_kind=ExecutorKind.LOCAL_WORKFLOW,
            status=TaskRunStatus.RUNNING,
            lease_owner=f"brand-intelligence-run:{run.id}",
            checkpoint_stage="A4",
        )
        session.add_all([task, task_run])
        run.analysis_task_id = task.id
        run.output_refs = {"task_run_id": str(task_run.id)}
        await session.commit()

        cancelled = await service.cancel_run(run_id=run.id, current_user=owner)
        await session.refresh(task)
        await session.refresh(task_run)

        assert cancelled is not None
        assert cancelled.status == BrandIntelligenceRunStatus.CANCELLED.value
        assert task.status == TaskStatus.CANCELLED
        assert task_run.status == TaskRunStatus.CANCELLING
        assert task_run.cancel_requested_at is not None

    await engine.dispose()


@pytest.mark.asyncio
async def test_background_dispatch_state_uses_existing_workflow_chain(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("run-dispatch-owner@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="理想汽车",
            domain="li.auto",
            industry="新能源汽车",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        session.add_all([owner, entity])
        await session.commit()

        service = BrandIntelligenceRunService(session)
        run = await service.create_or_reuse_run(
            entity_id=entity.id,
            current_user=owner,
            run_goal="分析品牌表现",
            analysis_mode="panorama",
            input_scope={"fetch_mode": "fast", "platforms": ["doubao"]},
        )
        state = _build_brand_run_initial_state(
            run=run,
            entity=entity,
            session_uuid=uuid.uuid4(),
            task_id=uuid.uuid4(),
            task_run_uuid=uuid.uuid4(),
        )

        assert state["messages"] == []
        assert state["execution_status"] == "idle"
        assert state["snapshot_id"] is None
        assert state["brand_profile"]["brand_name"] == "理想汽车"
        assert state["fetch_mode"] == "fast"
        assert state["platform_filter"] == ["doubao"]
        action = state["next_required_action"]
        assert action["tool_name"] == "question_simulation"
        assert action["tool_args"] == {"mode": "baseline_dynamic"}
        assert action["authority"] == "authoritative_resume"

    await engine.dispose()


@pytest.mark.asyncio
async def test_resolve_snapshot_id_falls_back_to_latest_session_snapshot(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("run-snapshot-owner@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="理想汽车",
            domain="li.auto",
            industry="新能源汽车",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        snapshot = AnalysisSnapshot(
            id=uuid.uuid4(),
            entity_id=entity.id,
            session_id=uuid.uuid4(),
            status=SnapshotStatus.COMPLETED,
            snapshot_type="panorama",
            triggered_by="manual",
        )
        session.add_all([owner, entity, snapshot])
        await session.commit()

        service = BrandIntelligenceRunService(session)
        resolved = await service._resolve_snapshot_id(
            final_state={"execution_status": "completed", "report": {"ok": True}},
            entity_id=entity.id,
            session_id=snapshot.session_id,
        )

        assert resolved == snapshot.id

    await engine.dispose()


@pytest.mark.asyncio
async def test_snapshot_service_keeps_association_circle_report_kind(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("run-association-snapshot-owner@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="安利",
            domain="amway.com.cn",
            industry="健康生活",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        session.add_all([owner, entity])
        await session.commit()

        snapshot = await SnapshotService(session).create_completed_snapshot(
            entity_id=entity.id,
            session_id=uuid.uuid4(),
            metrics={
                "summary_metrics": [],
                "total_questions": 32,
                "total_mentions": 64,
                "platform_breakdown": {
                    "doubao": {"success": 32},
                    "yuanbao": {"success": 32},
                },
            },
            report_data={
                "artifact_kind": "brand_association_circle",
                "report_kind": "brand_association_circle",
                "dashboard_projection": {
                    "association_circle_projection": {"nodes": [{"term": "营养健康"}]}
                },
            },
            snapshot_type="brand_association_circle",
        )

        assert snapshot.snapshot_type == "brand_association_circle"
        assert snapshot.raw_data["artifact_kind"] == "brand_association_circle"
        assert snapshot.raw_data["report_kind"] == "brand_association_circle"
        assert snapshot.total_questions == 32
        assert snapshot.platforms_success == 2

    await engine.dispose()


@pytest.mark.asyncio
async def test_active_run_syncs_linked_task_progress(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("run-sync-owner@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="理想汽车",
            domain="li.auto",
            industry="新能源汽车",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        session.add_all([owner, entity])
        await session.commit()

        service = BrandIntelligenceRunService(session)
        run = await service.create_or_reuse_run(
            entity_id=entity.id,
            current_user=owner,
            run_goal=None,
            analysis_mode="panorama",
        )
        task = AnalysisTask(
            id=uuid.uuid4(),
            user_id=owner.id,
            session_id=None,
            entity_id=entity.id,
            brand_name=entity.name,
            status=TaskStatus.RUNNING,
            current_stage="A4",
            progress=0.62,
            progress_message="正在采集 AI 回答",
        )
        session.add(task)
        run.analysis_task_id = task.id
        await session.commit()

        synced = await service.get_active_run(entity_id=entity.id, current_user=owner)

        assert synced is not None
        assert synced.status == BrandIntelligenceRunStatus.FETCHING_ANSWERS.value
        assert synced.stage == "fetching_answers"
        assert synced.progress == 0.62
        assert synced.message == "正在采集 AI 回答"

    await engine.dispose()


@pytest.mark.asyncio
async def test_cancelled_run_sync_recovers_completed_task(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("run-completed-repair-owner@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="理想汽车",
            domain="li.auto",
            industry="新能源汽车",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        session.add_all([owner, entity])
        await session.commit()

        service = BrandIntelligenceRunService(session)
        run = await service.create_or_reuse_run(
            entity_id=entity.id,
            current_user=owner,
            run_goal=None,
            analysis_mode="panorama",
        )
        snapshot_id = uuid.uuid4()
        task = AnalysisTask(
            id=uuid.uuid4(),
            user_id=owner.id,
            session_id=None,
            entity_id=entity.id,
            brand_name=entity.name,
            status=TaskStatus.COMPLETED,
            current_stage="A5",
            progress=1.0,
            progress_message="分析完成",
            snapshot_id=snapshot_id,
        )
        session.add(task)
        run.analysis_task_id = task.id
        await service.transition(
            run,
            status=BrandIntelligenceRunStatus.CANCELLED.value,
            stage="cancelled",
            message="已取消",
        )

        repaired = await service.get_run(run_id=run.id, current_user=owner)

        assert repaired is not None
        assert repaired.status == BrandIntelligenceRunStatus.COMPLETED.value
        assert repaired.stage == "completed"
        assert repaired.progress == 1.0
        assert repaired.output_refs["snapshot_id"] == str(snapshot_id)

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_context_run_waits_until_explicit_start(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("run-context-owner@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="理想汽车",
            domain="li.auto",
            industry="新能源汽车",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        session.add_all([owner, entity])
        await session.commit()

        service = BrandIntelligenceRunService(session)
        context_run = await service.create_or_reuse_run(
            entity_id=entity.id,
            current_user=owner,
            run_goal="解释当前品牌情报",
            analysis_mode="panorama",
            origin_surface="dashboard_chat_bubble",
            origin_event_id="dashboard-chat:li",
            start_immediately=False,
        )

        assert context_run.status == BrandIntelligenceRunStatus.NOT_STARTED.value
        assert context_run.progress == 0
        assert context_run.started_at is None
        assert context_run.message == "等待开始分析"

        started = await service.create_or_reuse_run(
            entity_id=entity.id,
            current_user=owner,
            run_goal="分析品牌表现",
            analysis_mode="panorama",
            origin_event_id="dashboard-start:li",
            start_immediately=True,
        )

        assert started.id == context_run.id
        assert started.status == BrandIntelligenceRunStatus.PLANNING_QUESTIONS.value
        assert started.started_at is not None
        assert started.message == "正在生成问题和样本范围"

    await engine.dispose()


@pytest.mark.asyncio
async def test_run_access_is_limited_to_entity_owner(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("run-owner-access@example.com")
        other = _user("run-other@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="imspecta.com",
            industry="AI brand intelligence",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        session.add_all([owner, other, entity])
        await session.commit()

        service = BrandIntelligenceRunService(session)
        run = await service.create_or_reuse_run(
            entity_id=entity.id,
            current_user=owner,
            run_goal=None,
            analysis_mode="panorama",
        )

        assert await service.get_run(run_id=run.id, current_user=owner) is not None
        with pytest.raises(LookupError):
            await service.get_active_run(entity_id=entity.id, current_user=other)
        assert await service.get_run(run_id=run.id, current_user=other) is None

    await engine.dispose()


@pytest.mark.asyncio
async def test_confirm_resume_cancel_and_terminal_guard(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("run-state-owner@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="理想汽车",
            domain="li.auto",
            industry="新能源汽车",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        session.add_all([owner, entity])
        await session.commit()

        service = BrandIntelligenceRunService(session)
        run = await service.create_or_reuse_run(
            entity_id=entity.id,
            current_user=owner,
            run_goal=None,
            analysis_mode="panorama",
        )
        waiting = await service.transition(
            run,
            status=BrandIntelligenceRunStatus.WAITING_USER.value,
            stage="waiting_user",
            progress=0.5,
            message="需要确认",
            requires_user_action=True,
            user_action_type="platform_login",
            blocking_reason="需要接管",
        )
        assert waiting.requires_user_action is True

        confirmed = await service.confirm_run(
            run_id=waiting.id,
            current_user=owner,
            user_action_type="platform_login",
            feedback_text="已确认",
        )
        assert confirmed is not None
        assert confirmed.status == BrandIntelligenceRunStatus.FETCHING_ANSWERS.value
        assert confirmed.requires_user_action is False
        assert confirmed.output_refs["confirmations"][0]["feedback_text"] == "已确认"

        completed = await service.transition(
            confirmed,
            status=BrandIntelligenceRunStatus.COMPLETED.value,
            stage="completed",
            progress=1.0,
            message="完成",
        )
        resumed = await service.resume_run(run_id=completed.id, current_user=owner)
        assert resumed is not None
        assert resumed.status == BrandIntelligenceRunStatus.COMPLETED.value

        cancelled = await service.cancel_run(run_id=completed.id, current_user=owner)
        assert cancelled is not None
        assert cancelled.status == BrandIntelligenceRunStatus.COMPLETED.value

    await engine.dispose()
