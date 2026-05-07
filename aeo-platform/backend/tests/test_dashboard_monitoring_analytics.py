import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{Path(__file__).resolve().parent / 'test_dashboard_monitoring.db'}",
)

from app.core.database import Base
from app.models.entity import Entity, EntityStatus
from app.models.monitoring_plan import (
    MonitoringEvidenceRecord,
    MonitoringRun,
    MonitoringRunPolicy,
    MonitoringRunStatus,
)
from app.models.snapshot import AnalysisSnapshot, SnapshotStatus
from app.models.user import User, UserRole, UserStatus
from app.services.analytics_service import AnalyticsService
from app.services.monitoring_plan_service import MonitoringPlanService
from app.services.monitoring_service import MonitoringService


async def _build_session(tmp_path):
    db_path = tmp_path / "dashboard-monitoring.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, session_factory


async def _seed_user_entity(session: AsyncSession):
    user = User(
        id=uuid.uuid4(),
        email=f"{uuid.uuid4()}@example.com",
        is_active=True,
        status=UserStatus.ACTIVE,
        role=UserRole.CUSTOMER_USER,
    )
    entity = Entity(
        id=uuid.uuid4(),
        name="Specta",
        domain="example.com",
        industry="brand intelligence",
        description="test brand",
        status=EntityStatus.ACTIVE,
        owner_user_id=user.id,
    )
    session.add_all([user, entity])
    await session.commit()
    return user, entity


def _snapshot(
    entity_id,
    *,
    mode: str,
    mention_rate: float,
    created_at: datetime,
    with_report: bool = False,
    session_id: uuid.UUID | None = None,
) -> AnalysisSnapshot:
    raw_data = {
        "report_kind": mode,
        "metric_bundle": {
            "mention_rate": mention_rate,
            "content_citation_rate": 0.2,
        },
    }
    if with_report:
        report_metric_bundle = {
            "mention_rate": mention_rate,
            "brand_visibility": mention_rate,
            "content_citation_rate": 0.2,
            "successful_answers": 1,
            "total_answers": 1,
            "source_summary": {
                "official_conversion_rate": 0.2,
                "source_type_breakdown": {},
                "top_domains": [],
            },
        }
        raw_data["metric_bundle"] = report_metric_bundle
        raw_data["report_data"] = {
            "title": "A5 完整分析报告",
            "executive_summary": "本轮分析已完成。",
            "brand_name": "Specta",
            "dashboard_projection": {"report_kind": mode},
            "metric_bundle": report_metric_bundle,
            "input_bundle": {
                "questions": [
                    {
                        "question_id": "q1",
                        "question_text": "How is Specta mentioned?",
                        "scene": "basic",
                    }
                ],
                "answers": [
                    {
                        "status": "ok",
                        "platform": "doubao",
                        "fetch_method": "api",
                        "mentioned_monitor_brand": True,
                        "sentiment": "positive",
                    }
                ],
            },
        }
    return AnalysisSnapshot(
        id=uuid.uuid4(),
        entity_id=entity_id,
        session_id=session_id,
        status=SnapshotStatus.COMPLETED,
        bwvs_index=mention_rate * 100,
        mention_rate=mention_rate,
        sentiment_score=0.5,
        coverage_score=0.75,
        citation_score=0.2,
        platforms_total=4,
        platforms_success=4,
        total_questions=10,
        total_mentions=int(mention_rate * 10),
        snapshot_type=mode,
        triggered_by="scheduled",
        raw_data=raw_data,
        created_at=created_at,
        completed_at=created_at,
    )


@pytest.mark.asyncio
async def test_dashboard_home_todo_requires_basic_analysis_when_brand_is_new(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user, entity = await _seed_user_entity(session)

        payload = await AnalyticsService(session, viewer=user).get_dashboard_home_v2(
            str(entity.id),
            monitor_mode="panorama",
            date_range="month",
        )

        assert payload["todoItems"][0]["kind"] == "analysis_setup_incomplete"
        assert payload["todoItems"][0]["action"] == "ai_conversation"
    await engine.dispose()


@pytest.mark.asyncio
async def test_dashboard_home_todo_requires_plan_setup_for_inactive_plan(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user, entity = await _seed_user_entity(session)
        service = MonitoringPlanService(session)
        question_set = await service.create_question_set(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            questions=["How is Specta mentioned?"],
        )
        await service.create_plan(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            question_set_ids=[question_set.id],
            status="draft",
        )

        payload = await AnalyticsService(session, viewer=user).get_dashboard_home_v2(
            str(entity.id),
            monitor_mode="panorama",
            date_range="month",
        )

        assert payload["todoItems"][0]["kind"] == "monitoring_plan_incomplete"
        assert payload["todoItems"][0]["action"] == "setup_plan"
    await engine.dispose()


@pytest.mark.asyncio
async def test_dashboard_home_todo_accepts_active_settings_schedule(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user, entity = await _seed_user_entity(session)
        service = MonitoringPlanService(session)
        question_set = await service.create_question_set(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            questions=["How is Specta mentioned?"],
        )
        await service.create_plan(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            question_set_ids=[question_set.id],
            status="draft",
        )
        session.add(
            _snapshot(
                entity.id,
                mode="panorama",
                mention_rate=0.6,
                created_at=datetime.now(timezone.utc),
                with_report=True,
            )
        )
        await session.commit()
        schedule = await MonitoringService(session).create_schedule(
            user_id=user.id,
            entity_id=entity.id,
            preferred_hour=11,
            platforms=["doubao", "yuanbao", "kimi", "deepseek"],
            monitor_mode="panorama",
        )

        payload = await AnalyticsService(session, viewer=user).get_dashboard_home_v2(
            str(entity.id),
            monitor_mode="panorama",
            date_range="month",
        )

        assert all(
            item["kind"] != "monitoring_plan_incomplete"
            for item in payload["todoItems"]
        )
        assert payload["hasActiveMonitoringSchedule"] is True
        assert payload["monitoringPlan"]["status"] == "active"
        assert payload["monitoringPlan"]["schedule_id"] == str(schedule.id)
        assert payload["monitoringPlan"]["question_count"] == 1
        assert "deepseek_browser" in payload["monitoringPlan"]["endpoint_ids"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_dashboard_home_todo_accepts_active_schedule_from_other_mode(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user, entity = await _seed_user_entity(session)
        service = MonitoringPlanService(session)
        question_set = await service.create_question_set(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            questions=["How is Specta mentioned?"],
        )
        await service.create_plan(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            question_set_ids=[question_set.id],
            status="draft",
        )
        now = datetime.now(timezone.utc)
        session.add_all(
            [
                _snapshot(
                    entity.id,
                    mode="panorama",
                    mention_rate=0.6,
                    created_at=now - timedelta(minutes=5),
                    with_report=True,
                ),
                _snapshot(
                    entity.id,
                    mode="scenario",
                    mention_rate=0.3,
                    created_at=now,
                    with_report=True,
                    session_id=uuid.uuid4(),
                ),
            ]
        )
        await session.commit()
        await MonitoringService(session).create_schedule(
            user_id=user.id,
            entity_id=entity.id,
            preferred_hour=11,
            platforms=["doubao", "yuanbao", "kimi", "deepseek"],
            monitor_mode="panorama",
        )

        payload = await AnalyticsService(session, viewer=user).get_dashboard_home_v2(
            str(entity.id),
            monitor_mode="scenario",
            date_range="month",
        )

        assert all(
            item["kind"] != "monitoring_plan_incomplete"
            for item in payload["todoItems"]
        )
        assert payload["hasActiveMonitoringSchedule"] is True
    await engine.dispose()


@pytest.mark.asyncio
async def test_dashboard_home_todo_active_schedule_survives_stale_plan(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user, entity = await _seed_user_entity(session)
        service = MonitoringPlanService(session)
        question_set = await service.create_question_set(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            questions=["How is Specta mentioned?"],
        )
        plan = await service.create_plan(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            question_set_ids=[question_set.id],
            status="draft",
        )
        plan.question_set_ids = [str(uuid.uuid4())]
        session.add(
            _snapshot(
                entity.id,
                mode="panorama",
                mention_rate=0.6,
                created_at=datetime.now(timezone.utc),
                with_report=True,
            )
        )
        await session.commit()
        schedule = await MonitoringService(session).create_schedule(
            user_id=user.id,
            entity_id=entity.id,
            preferred_hour=11,
            platforms=["doubao", "yuanbao", "kimi", "deepseek"],
            monitor_mode="panorama",
        )

        payload = await AnalyticsService(session, viewer=user).get_dashboard_home_v2(
            str(entity.id),
            monitor_mode="panorama",
            date_range="month",
        )

        assert all(
            item["kind"] != "monitoring_plan_incomplete"
            for item in payload["todoItems"]
        )
        assert payload["monitoringPlan"]["status"] == "active"
        assert payload["monitoringPlan"]["schedule_id"] == str(schedule.id)
    await engine.dispose()


@pytest.mark.asyncio
async def test_dashboard_home_todo_requires_schedule_baseline_questions(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user, entity = await _seed_user_entity(session)
        service = MonitoringPlanService(session)
        question_set = await service.create_question_set(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            questions=["How is Specta mentioned?"],
        )
        await service.create_plan(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            question_set_ids=[question_set.id],
            status="draft",
        )
        session.add(
            _snapshot(
                entity.id,
                mode="panorama",
                mention_rate=0.6,
                created_at=datetime.now(timezone.utc),
                with_report=True,
            )
        )
        await session.commit()
        schedule = await MonitoringService(session).create_schedule(
            user_id=user.id,
            entity_id=entity.id,
            preferred_hour=11,
            platforms=["doubao", "yuanbao", "kimi", "deepseek"],
            monitor_mode="panorama",
        )
        schedule.baseline_data = None
        await session.commit()

        payload = await AnalyticsService(session, viewer=user).get_dashboard_home_v2(
            str(entity.id),
            monitor_mode="panorama",
            date_range="month",
        )

        assert payload["todoItems"][0]["kind"] == "monitoring_plan_incomplete"
        assert payload["monitoringPlan"]["status"] == "draft"
    await engine.dispose()


@pytest.mark.asyncio
async def test_dashboard_home_todo_surfaces_unread_latest_report_for_active_plan(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user, entity = await _seed_user_entity(session)
        service = MonitoringPlanService(session)
        question_set = await service.create_question_set(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            questions=["How is Specta mentioned?"],
        )
        await service.confirm_question_set_and_activate_quick_plan(
            user_id=user.id,
            entity_id=entity.id,
            question_set_id=question_set.id,
            monitor_mode="panorama",
        )
        report_session_id = uuid.uuid4()
        session.add(
            _snapshot(
                entity.id,
                mode="panorama",
                mention_rate=0.6,
                created_at=datetime.now(timezone.utc),
                with_report=True,
                session_id=report_session_id,
            )
        )
        await session.commit()

        payload = await AnalyticsService(session, viewer=user).get_dashboard_home_v2(
            str(entity.id),
            monitor_mode="panorama",
            date_range="month",
        )

        assert payload["todoItems"][0]["kind"] == "unread_latest_report"
        assert payload["todoItems"][0]["action"] == "latest_report"
        assert payload["todoItems"][0]["refId"] == str(report_session_id)
    await engine.dispose()


@pytest.mark.asyncio
async def test_dashboard_home_period_summary_filters_mode_and_date(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user, entity = await _seed_user_entity(session)
        now = datetime.now(timezone.utc)
        session.add_all(
            [
                _snapshot(
                    entity.id,
                    mode="panorama",
                    mention_rate=0.2,
                    created_at=now - timedelta(days=8),
                ),
                _snapshot(
                    entity.id,
                    mode="panorama",
                    mention_rate=0.4,
                    created_at=now - timedelta(days=1),
                ),
                _snapshot(
                    entity.id,
                    mode="scenario",
                    mention_rate=0.9,
                    created_at=now - timedelta(days=1),
                ),
                _snapshot(
                    entity.id,
                    mode="panorama",
                    mention_rate=0.8,
                    created_at=now - timedelta(days=60),
                ),
            ]
        )
        await session.commit()

        payload = await AnalyticsService(session, viewer=user).get_dashboard_home_v2(
            str(entity.id),
            monitor_mode="panorama",
            date_range="month",
        )

        assert payload["periodSummary"]["data_point_count"] == 2
        mention = next(
            item
            for item in payload["periodSummary"]["metrics"]
            if item["metric"] == "mention_rate"
        )
        assert mention["current_value"] == 0.4
        assert mention["average_value"] == pytest.approx(0.3)
    await engine.dispose()


@pytest.mark.asyncio
async def test_endpoint_trends_keep_api_and_browser_sources_separate(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user, entity = await _seed_user_entity(session)
        service = MonitoringPlanService(session)
        question_set = await service.create_question_set(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            questions=["How is Specta mentioned?"],
        )
        plan = await service.confirm_question_set_and_activate_quick_plan(
            user_id=user.id,
            entity_id=entity.id,
            question_set_id=question_set.id,
            monitor_mode="panorama",
        )
        run = MonitoringRun(
            id=uuid.uuid4(),
            user_id=user.id,
            entity_id=entity.id,
            plan_id=plan.id,
            status=MonitoringRunStatus.COMPLETED.value,
            run_policy=MonitoringRunPolicy.QUICK.value,
            monitor_mode="panorama",
            endpoint_ids=["doubao_api", "doubao_browser", "deepseek_browser"],
            question_set_ids=[str(question_set.id)],
            question_count=1,
            completed_at=datetime.now(timezone.utc),
        )
        session.add(run)
        await session.flush()
        session.add_all(
            [
                MonitoringEvidenceRecord(
                    monitoring_run_id=run.id,
                    plan_id=plan.id,
                    entity_id=entity.id,
                    question_id="q1",
                    question_text="How is Specta mentioned?",
                    endpoint_id="doubao_api",
                    endpoint_label="doubao api",
                    platform="doubao",
                    fetch_method="api",
                    answer_status="ok",
                    cited_domains=[],
                    raw_evidence={"mentioned_monitor_brand": True},
                ),
                MonitoringEvidenceRecord(
                    monitoring_run_id=run.id,
                    plan_id=plan.id,
                    entity_id=entity.id,
                    question_id="q1",
                    question_text="How is Specta mentioned?",
                    endpoint_id="doubao_browser",
                    endpoint_label="doubao web",
                    platform="doubao",
                    fetch_method="browser",
                    answer_status="ok",
                    cited_domains=[],
                    raw_evidence={"mentioned_monitor_brand": False},
                ),
                MonitoringEvidenceRecord(
                    monitoring_run_id=run.id,
                    plan_id=plan.id,
                    entity_id=entity.id,
                    question_id="q1",
                    question_text="How is Specta mentioned?",
                    endpoint_id="deepseek_browser",
                    endpoint_label="deepseek web",
                    platform="deepseek",
                    fetch_method="browser",
                    answer_status="ok",
                    cited_domains=["example.com"],
                    raw_evidence={"mentioned_monitor_brand": True},
                ),
            ]
        )
        await session.commit()

        payload = await AnalyticsService(session, viewer=user).get_monitoring_trends_v2(
            brand_id=str(entity.id),
            monitor_mode="panorama",
            metric="mention_rate",
            group_by="endpoint",
        )

        labels = {item["id"]: item["label"] for item in payload["series"]}
        values = {
            item["id"]: item["current_value"]
            for item in payload["series"]
        }
        assert labels["doubao_api"] == "豆包API"
        assert labels["doubao_browser"] == "豆包网页版"
        assert labels["deepseek_browser"] == "DeepSeek网页版"
        assert values["doubao_api"] == 1.0
        assert values["doubao_browser"] == 0.0
    await engine.dispose()


@pytest.mark.asyncio
async def test_question_set_trends_filter_merged_plan_snapshots(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        user, entity = await _seed_user_entity(session)
        service = MonitoringPlanService(session)
        q1 = await service.create_question_set(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            questions=["Question one"],
        )
        q2 = await service.create_question_set(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            questions=["Question two"],
        )
        await service.confirm_question_set(question_set_id=q1.id, user_id=user.id)
        await service.confirm_question_set(question_set_id=q2.id, user_id=user.id)
        plan = await service.create_plan(
            user_id=user.id,
            entity_id=entity.id,
            monitor_mode="panorama",
            question_set_ids=[q1.id, q2.id],
            status="active",
        )
        now = datetime.now(timezone.utc)
        snapshot_one = _snapshot(
            entity.id,
            mode="panorama",
            mention_rate=0.1,
            created_at=now - timedelta(days=2),
        )
        snapshot_two = _snapshot(
            entity.id,
            mode="panorama",
            mention_rate=0.7,
            created_at=now - timedelta(days=1),
        )
        session.add_all([snapshot_one, snapshot_two])
        await session.flush()
        session.add_all(
            [
                MonitoringRun(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    entity_id=entity.id,
                    plan_id=plan.id,
                    snapshot_id=snapshot_one.id,
                    status=MonitoringRunStatus.COMPLETED.value,
                    run_policy=MonitoringRunPolicy.QUICK.value,
                    monitor_mode="panorama",
                    endpoint_ids=["doubao_api"],
                    question_set_ids=[str(q1.id)],
                    question_count=1,
                    completed_at=snapshot_one.created_at,
                    created_at=snapshot_one.created_at,
                ),
                MonitoringRun(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    entity_id=entity.id,
                    plan_id=plan.id,
                    snapshot_id=snapshot_two.id,
                    status=MonitoringRunStatus.COMPLETED.value,
                    run_policy=MonitoringRunPolicy.QUICK.value,
                    monitor_mode="panorama",
                    endpoint_ids=["doubao_api"],
                    question_set_ids=[str(q2.id)],
                    question_count=1,
                    completed_at=snapshot_two.created_at,
                    created_at=snapshot_two.created_at,
                ),
            ]
        )
        await session.commit()

        payload = await AnalyticsService(session, viewer=user).get_monitoring_trends_v2(
            brand_id=str(entity.id),
            monitor_mode="panorama",
            metric="mention_rate",
            group_by="question_set",
            question_set_id=str(q2.id),
        )

        assert len(payload["series"]) == 1
        assert payload["series"][0]["id"] == str(q2.id)
        assert payload["series"][0]["current_value"] == 0.7
    await engine.dispose()
