from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
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
    get_board_run_assets,
    get_board_run_events,
    get_brand_graph,
    get_brand_space,
    pause_board_run,
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

        created = await create_board_run(
            entity_id=str(entity.id),
            payload=BoardRunCreate(),
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

        assets = await get_board_run_assets(
            run_id=run_id,
            db=session,
            current_user=owner,
        )
        assert len(assets["artifacts"]) == 8

        paused = await pause_board_run(run_id=run_id, db=session, current_user=owner)
        assert paused["run"]["status"] == "paused"

        resumed = await resume_board_run(run_id=run_id, db=session, current_user=owner)
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
            payload=GraphPatchDecision(status="needs_review", reason="继续观察"),
            db=session,
            current_user=owner,
        )
        duplicate_patch = next(
            item for item in duplicate_decision["patches"] if item["id"] == patch["id"]
        )
        assert duplicate_patch["status"] == "needs_review"

        report = await generate_graph_update_report(
            graph_update_id=resumed["graph_update"]["id"],
            payload=GraphUpdateReportCreate(),
            db=session,
            current_user=owner,
        )
        assert report["report"]["title"] == "安利圈层状态更新"

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

        await create_board_run(
            entity_id=str(entity.id),
            payload=BoardRunCreate(),
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

    await engine.dispose()
