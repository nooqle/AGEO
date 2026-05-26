from __future__ import annotations

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
    f"sqlite+aiosqlite:///{Path(__file__).resolve().parent / 'test_entity_delete.db'}",
)

from app.core.database import Base
from app.models.brand_intelligence import BrandActionRecord, BrandUserDecision
from app.models.brand_intelligence_run import BrandIntelligenceRun
from app.models.entity import Entity, EntityStatus
from app.models.user import User, UserRole, UserStatus
from app.services.entity_service import EntityService


async def _build_session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'entity.db'}")
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, session_factory


@pytest.mark.asyncio
async def test_delete_entity_removes_brand_intelligence_dependents(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = User(
            id=uuid.uuid4(),
            email="delete-entity-owner@example.com",
            is_active=True,
            status=UserStatus.ACTIVE,
            role=UserRole.CUSTOMER_USER,
        )
        entity = Entity(
            id=uuid.uuid4(),
            name="删除测试品牌",
            domain="delete.example.com",
            industry="测试",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        action = BrandActionRecord(
            id=uuid.uuid4(),
            entity_id=entity.id,
            user_id=owner.id,
            actor_type="user",
            origin_surface="test",
            origin_event_id="delete-test",
            action_type="record_user_feedback",
            status="applied",
            input_payload={},
            output_payload={},
        )
        decision = BrandUserDecision(
            id=uuid.uuid4(),
            entity_id=entity.id,
            action_record_id=action.id,
            user_id=owner.id,
            decision_type="recommendation_task",
            decision_key="recommendation:delete-test",
            status="submitted",
            input_payload={},
            output_payload={},
        )
        run = BrandIntelligenceRun(
            id=uuid.uuid4(),
            entity_id=entity.id,
            created_by_user_id=owner.id,
            origin_surface="test",
            status="planning_questions",
            stage="planning_questions",
            progress=0.1,
            message="test",
            run_goal="test",
            analysis_mode="panorama",
            input_scope={},
            output_refs={},
        )
        session.add_all([owner, entity, action, decision, run])
        await session.commit()

        deleted = await EntityService(session).delete_entity(str(entity.id), owner)

        assert deleted is True
        assert await session.get(Entity, entity.id) is None
        assert (
            await session.execute(
                select(BrandActionRecord).where(
                    BrandActionRecord.entity_id == entity.id
                )
            )
        ).scalar_one_or_none() is None
        assert (
            await session.execute(
                select(BrandUserDecision).where(
                    BrandUserDecision.entity_id == entity.id
                )
            )
        ).scalar_one_or_none() is None
        assert (
            await session.execute(
                select(BrandIntelligenceRun).where(
                    BrandIntelligenceRun.entity_id == entity.id
                )
            )
        ).scalar_one_or_none() is None

    await engine.dispose()
