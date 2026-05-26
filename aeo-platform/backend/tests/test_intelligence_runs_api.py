from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{Path(__file__).resolve().parent / 'test_intelligence_runs_api.db'}",
)

from app.api.v1.intelligence_runs import (
    cancel_intelligence_run,
    confirm_intelligence_run,
    create_intelligence_run,
    get_active_intelligence_run,
    get_intelligence_run,
    resume_intelligence_run,
)
from app.core.database import Base
from app.models.brand_intelligence_run import BrandIntelligenceRunStatus
from app.models.entity import Entity, EntityStatus
from app.models.user import User, UserRole, UserStatus
from app.schemas.intelligence_run import (
    BrandIntelligenceRunConfirm,
    BrandIntelligenceRunCreate,
)


async def _build_session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'run-api.db'}")
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
async def test_intelligence_run_api_create_active_resume_cancel(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("run-api-owner@example.com")
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

        created = await create_intelligence_run(
            entity_id=str(entity.id),
            payload=BrandIntelligenceRunCreate(
                run_goal="分析当前品牌表现",
                analysis_mode="panorama",
                input_scope={"sample": "test"},
                origin_event_id="api-create",
                auto_dispatch=False,
            ),
            background_tasks=BackgroundTasks(),
            db=session,
            current_user=owner,
        )
        run = created["run"]
        assert run["entity_id"] == str(entity.id)
        assert run["status"] == BrandIntelligenceRunStatus.NOT_STARTED.value

        active = await get_active_intelligence_run(
            entity_id=str(entity.id),
            db=session,
            current_user=owner,
        )
        assert active["run"]["id"] == run["id"]

        resumed = await resume_intelligence_run(
            run_id=run["id"],
            background_tasks=BackgroundTasks(),
            db=session,
            current_user=owner,
        )
        assert resumed["run"]["status"] == BrandIntelligenceRunStatus.FETCHING_ANSWERS.value

        cancelled = await cancel_intelligence_run(
            run_id=run["id"],
            db=session,
            current_user=owner,
        )
        assert cancelled["run"]["status"] == BrandIntelligenceRunStatus.CANCELLED.value

        fetched = await get_intelligence_run(
            run_id=run["id"],
            db=session,
            current_user=owner,
        )
        assert fetched["run"]["id"] == run["id"]

    await engine.dispose()


@pytest.mark.asyncio
async def test_intelligence_run_api_blocks_cross_user_access(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("run-api-owner-2@example.com")
        other = _user("run-api-other@example.com")
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

        created = await create_intelligence_run(
            entity_id=str(entity.id),
            payload=BrandIntelligenceRunCreate(auto_dispatch=False),
            background_tasks=BackgroundTasks(),
            db=session,
            current_user=owner,
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_active_intelligence_run(
                entity_id=str(entity.id),
                db=session,
                current_user=other,
            )
        assert exc_info.value.status_code == 404

        with pytest.raises(HTTPException) as exc_info:
            await get_intelligence_run(
                run_id=created["run"]["id"],
                db=session,
                current_user=other,
            )
        assert exc_info.value.status_code == 404

    await engine.dispose()


@pytest.mark.asyncio
async def test_intelligence_run_api_confirm_clears_waiting_state(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("run-api-confirm@example.com")
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

        created = await create_intelligence_run(
            entity_id=str(entity.id),
            payload=BrandIntelligenceRunCreate(auto_dispatch=False),
            background_tasks=BackgroundTasks(),
            db=session,
            current_user=owner,
        )
        confirmed = await confirm_intelligence_run(
            run_id=created["run"]["id"],
            payload=BrandIntelligenceRunConfirm(
                user_action_type="scope",
                feedback_text="确认继续",
            ),
            background_tasks=BackgroundTasks(),
            db=session,
            current_user=owner,
        )
        assert confirmed["run"]["status"] == BrandIntelligenceRunStatus.FETCHING_ANSWERS.value
        assert confirmed["run"]["requires_user_action"] is False
        assert confirmed["run"]["output_refs"]["confirmations"][0]["feedback_text"] == "确认继续"

    await engine.dispose()
