from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from fastapi import BackgroundTasks
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{Path(__file__).resolve().parent / 'test_brand_space_api.db'}",
)

from app.api.v1.brand_space import (
    create_board_run,
    decide_graph_patch,
    generate_graph_update_report,
    get_artifact_access,
    get_board_run_assets,
    get_board_run_events,
    get_artifact_detail,
    download_artifact,
    get_brand_graph,
    get_brand_reports,
    get_brand_review_items,
    get_brand_space,
    get_report_version,
    pause_board_run,
    publish_report_version,
    resume_board_run,
    stop_board_run,
)
from app.core.database import Base
from app.models import *  # noqa: F401, F403
from app.models.entity import Entity, EntityStatus
from app.models.user import User, UserRole, UserStatus
from app.schemas.brand_space import BoardRunCreate, GraphPatchDecision, GraphUpdateReportCreate


async def _build_session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'brand-space-api.db'}")
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
async def test_brand_space_api_run_controls_patch_decision_and_report(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("brand-space-api-owner@example.com")
        other_user = _user("brand-space-api-other@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="安利",
            domain="amway.com.cn",
            industry="营养健康",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        session.add_all([owner, other_user, entity])
        await session.commit()

        created = await create_board_run(
            entity_id=str(entity.id),
            payload=BoardRunCreate(),
            background_tasks=BackgroundTasks(),
            db=session,
            current_user=owner,
        )
        run_id = created["run"]["id"]
        assert created["run"]["status"] == "running"
        assert created["run"]["is_scaffold"] is True

        graph = await get_brand_graph(
            entity_id=str(entity.id),
            db=session,
            current_user=owner,
        )
        assert graph["graph_update"]["id"] == created["graph_update"]["id"]
        assert any(item["label"] == "安利" for item in graph["graph"]["entities"])

        events = await get_board_run_events(
            run_id=run_id,
            db=session,
            current_user=owner,
        )
        assert any(event["type"] == "scaffold_data_loaded" for event in events["events"])
        cursor_events = await get_board_run_events(
            run_id=run_id,
            after_sequence=0,
            db=session,
            current_user=owner,
        )
        assert cursor_events["pagination"]["total"] is None
        assert cursor_events["cursor"]["next_sequence"] >= 1
        assert all(event["sequence"] > 0 for event in cursor_events["events"])

        assets = await get_board_run_assets(
            run_id=run_id,
            db=session,
            current_user=owner,
        )
        assert len(assets["artifacts"]) == 8
        assert assets["pagination"]["total"] == 8

        graph_assets = await get_board_run_assets(
            run_id=run_id,
            artifact_type="graph_update",
            limit=1,
            db=session,
            current_user=owner,
        )
        assert graph_assets["summary"]["total"] == 1
        assert graph_assets["artifacts"][0]["type"] == "graph_update"
        graph_asset_detail = await get_artifact_detail(
            artifact_id=graph_assets["artifacts"][0]["artifactId"],
            db=session,
            current_user=owner,
        )
        assert graph_asset_detail["preview"]["kind"] == "json"
        graph_asset_access = await get_artifact_access(
            artifact_id=graph_assets["artifacts"][0]["artifactId"],
            db=session,
            current_user=owner,
        )
        assert graph_asset_access["access"]["mode"] == "object_storage"
        with pytest.raises(HTTPException) as access_exc:
            await get_artifact_access(
                artifact_id=graph_assets["artifacts"][0]["artifactId"],
                db=session,
                current_user=other_user,
            )
        assert access_exc.value.status_code == 404
        with pytest.raises(HTTPException) as download_exc:
            await download_artifact(
                artifact_id=graph_assets["artifacts"][0]["artifactId"],
                db=session,
                current_user=other_user,
            )
        assert download_exc.value.status_code == 404
        assert any(
            link["kind"] == "graph_update"
            for link in graph_asset_detail["trace"]["links"]
        )

        review_items = await get_brand_review_items(
            entity_id=str(entity.id),
            db=session,
            current_user=owner,
        )
        assert review_items["summary"]["total"] == 3
        assert {item["category"] for item in review_items["review_items"]} >= {
            "risk",
            "competitor",
            "new_entity",
        }

        competitor_items = await get_brand_review_items(
            entity_id=str(entity.id),
            category="competitor",
            db=session,
            current_user=owner,
        )
        assert len(competitor_items["review_items"]) == 1
        assert competitor_items["review_items"][0]["category"] == "competitor"

        paused = await pause_board_run(run_id=run_id, db=session, current_user=owner)
        assert paused["run"]["status"] == "paused"

        resumed = await resume_board_run(
            run_id=run_id,
            background_tasks=BackgroundTasks(),
            db=session,
            current_user=owner,
        )
        assert resumed["run"]["status"] == "running"

        patch = next(
            item for item in resumed["patches"] if item["patchType"] == "add_competitor_relation"
        )
        decided = await decide_graph_patch(
            patch_id=patch["id"],
            payload=GraphPatchDecision(status="accepted", reason="证据可用"),
            db=session,
            current_user=owner,
        )
        decided_patch = next(item for item in decided["patches"] if item["id"] == patch["id"])
        assert decided_patch["status"] == "accepted"

        duplicate_decision = await decide_graph_patch(
            patch_id=patch["id"],
            payload=GraphPatchDecision(status="accepted", reason="重复提交不应新增事件"),
            db=session,
            current_user=owner,
        )
        duplicate_patch = next(
            item for item in duplicate_decision["patches"] if item["id"] == patch["id"]
        )
        assert duplicate_patch["status"] == "accepted"

        events_after_duplicate = await get_board_run_events(
            run_id=run_id,
            db=session,
            current_user=owner,
        )
        assert [
            event["type"] for event in events_after_duplicate["events"]
        ].count("graph_patch_accepted") == 1

        with pytest.raises(HTTPException) as terminal_exc:
            await decide_graph_patch(
                patch_id=patch["id"],
                payload=GraphPatchDecision(status="needs_review", reason="不允许反转终态"),
                db=session,
                current_user=owner,
            )
        assert terminal_exc.value.status_code == 400

        report = await generate_graph_update_report(
            graph_update_id=resumed["graph_update"]["id"],
            payload=GraphUpdateReportCreate(),
            db=session,
            current_user=owner,
        )
        assert report["report"]["title"] == "安利品牌 AI 认知图景"
        report_assets = await get_board_run_assets(
            run_id=run_id,
            artifact_type="report",
            db=session,
            current_user=owner,
        )
        assert report_assets["pagination"]["total"] == 1
        report_asset_detail = await get_artifact_detail(
            artifact_id=report_assets["artifacts"][0]["artifactId"],
            db=session,
            current_user=owner,
        )
        assert report_asset_detail["trace"]["report"]["id"] == report["report"]["id"]
        assert report_asset_detail["access"]["available"] is True
        reports = await get_brand_reports(
            entity_id=str(entity.id),
            db=session,
            current_user=owner,
        )
        assert reports["summary"]["graph_update"] == 1
        report_detail = await get_report_version(
            report_version_id=report["report"]["id"],
            db=session,
            current_user=owner,
        )
        assert report_detail["report"]["id"] == report["report"]["id"]

        accepted_again = await decide_graph_patch(
            patch_id=patch["id"],
            payload=GraphPatchDecision(status="accepted", reason="证据已补足"),
            db=session,
            current_user=owner,
        )
        assert next(
            item for item in accepted_again["patches"] if item["id"] == patch["id"]
        )["status"] == "accepted"

        publishable_report = await generate_graph_update_report(
            graph_update_id=resumed["graph_update"]["id"],
            payload=GraphUpdateReportCreate(publish_requested=True),
            db=session,
            current_user=owner,
        )
        assert publishable_report["report"]["payload"]["publication_status"] == "publishable"
        published_report = await publish_report_version(
            report_version_id=publishable_report["report"]["id"],
            db=session,
            current_user=owner,
        )
        assert published_report["report"]["payload"]["publication_status"] == "published"

        stopped = await stop_board_run(run_id=run_id, db=session, current_user=owner)
        assert stopped["run"]["status"] == "stopped"

        fetched = await get_brand_space(
            entity_id=str(entity.id),
            db=session,
            current_user=owner,
        )
        assert fetched["run"]["id"] == run_id

    await engine.dispose()


@pytest.mark.asyncio
async def test_brand_space_api_blocks_other_user(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("brand-space-api-owner-2@example.com")
        other = _user("brand-space-api-other@example.com")
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

        created = await create_board_run(
            entity_id=str(entity.id),
            payload=BoardRunCreate(),
            background_tasks=BackgroundTasks(),
            db=session,
            current_user=owner,
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_brand_space(
                entity_id=str(entity.id),
                db=session,
                current_user=other,
            )
        assert exc_info.value.status_code == 404

        with pytest.raises(HTTPException) as review_exc:
            await get_brand_review_items(
                entity_id=str(entity.id),
                db=session,
                current_user=other,
            )
        assert review_exc.value.status_code == 404

        with pytest.raises(HTTPException) as artifact_exc:
            await get_artifact_detail(
                artifact_id=created["artifacts"][0]["artifactId"],
                db=session,
                current_user=other,
            )
        assert artifact_exc.value.status_code == 404

    await engine.dispose()


@pytest.mark.asyncio
async def test_brand_space_api_real_run_submits_background_dispatch(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("brand-space-api-real-owner@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="安利",
            domain="amway.com.cn",
            industry="营养健康",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        session.add_all([owner, entity])
        await session.commit()

        background_tasks = BackgroundTasks()
        created = await create_board_run(
            entity_id=str(entity.id),
            payload=BoardRunCreate(execution_mode="real", request_id="rerun-click-1"),
            background_tasks=background_tasks,
            db=session,
            current_user=owner,
        )

        assert created["run"]["is_scaffold"] is False
        assert created["run"]["analysis_task_id"]
        assert created["graph_update"] is None
        assert any(
            event["type"] == "runtime_dispatch_requested"
            for event in created["events"]
        )
        assert len(background_tasks.tasks) == 1

        duplicate_tasks = BackgroundTasks()
        duplicate = await create_board_run(
            entity_id=str(entity.id),
            payload=BoardRunCreate(execution_mode="real", request_id="rerun-click-1"),
            background_tasks=duplicate_tasks,
            db=session,
            current_user=owner,
        )
        assert duplicate["run"]["id"] == created["run"]["id"]
        assert len(duplicate_tasks.tasks) == 0

        first_resume_tasks = BackgroundTasks()
        await resume_board_run(
            run_id=created["run"]["id"],
            background_tasks=first_resume_tasks,
            db=session,
            current_user=owner,
        )
        assert len(first_resume_tasks.tasks) == 0

        second_resume_tasks = BackgroundTasks()
        await resume_board_run(
            run_id=created["run"]["id"],
            background_tasks=second_resume_tasks,
            db=session,
            current_user=owner,
        )
        assert len(second_resume_tasks.tasks) == 0

    await engine.dispose()
