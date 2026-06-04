from __future__ import annotations

import os
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_user_scope_security.db")

from app.api.v1.messages import get_messages
from app.api.v1.outputs import get_outputs
from app.core.database import Base
from app.models.entity import Entity, EntityStatus
from app.models.message import Message, MessageRole, MessageType
from app.models.session import Session
from app.models.task import AnalysisTask, TaskStatus
from app.models.user import User, UserRole, UserStatus
from app.services.task_service import TaskService


async def _build_session(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'user-scope-security.db'}"
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, session_factory


def _user(*, role: UserRole, email: str) -> User:
    return User(
        id=uuid.uuid4(),
        email=email,
        is_active=True,
        status=UserStatus.ACTIVE,
        role=role,
    )


@pytest.mark.asyncio
async def test_internal_admin_task_viewer_does_not_cross_personal_owner(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as db:
        admin = _user(role=UserRole.INTERNAL_ADMIN, email="admin@example.com")
        owner = _user(role=UserRole.CUSTOMER_USER, email="owner@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="whobot 呼波特",
            domain="www.whobot.com",
            industry="AI 电话营销",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        conversation = Session(
            id=uuid.uuid4(),
            user_id=owner.id,
            entity_id=entity.id,
            title="whobot",
        )
        task = AnalysisTask(
            id=uuid.uuid4(),
            user_id=owner.id,
            session_id=conversation.id,
            entity_id=entity.id,
            brand_name="whobot 呼波特",
            status=TaskStatus.RUNNING,
            current_stage="A1",
        )
        db.add_all([admin, owner, entity, conversation, task])
        await db.commit()

        service = TaskService(db)
        tasks, total = await service.list_tasks_for_viewer(
            viewer=admin,
            status=TaskStatus.RUNNING,
        )
        assert tasks == []
        assert total == 0
        assert await service.get_task_for_viewer(task.id, admin) is None

        bypass_tasks, bypass_total = await service.list_tasks_for_viewer(
            viewer=admin,
            status=TaskStatus.RUNNING,
            allow_internal_admin_bypass=True,
        )
        assert bypass_total == 1
        assert [item.id for item in bypass_tasks] == [task.id]

    await engine.dispose()


@pytest.mark.asyncio
async def test_internal_admin_cannot_read_other_personal_session_messages_or_outputs(
    tmp_path,
):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as db:
        admin = _user(role=UserRole.INTERNAL_ADMIN, email="admin-messages@example.com")
        owner = _user(role=UserRole.CUSTOMER_USER, email="owner-messages@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="whobot 呼波特",
            domain="www.whobot.com",
            industry="AI 电话营销",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        conversation = Session(
            id=uuid.uuid4(),
            user_id=owner.id,
            entity_id=entity.id,
            title="whobot",
        )
        message = Message(
            id=uuid.uuid4(),
            session_id=conversation.id,
            role=MessageRole.USER,
            type=MessageType.TEXT,
            content="我想为 whobot 建立品牌监测",
            sequence=1,
        )
        output = Message(
            id=uuid.uuid4(),
            session_id=conversation.id,
            role=MessageRole.ASSISTANT,
            type=MessageType.OUTPUT,
            content="报告",
            output_type="report",
            output_data='{"brand":"whobot"}',
            sequence=2,
        )
        db.add_all([admin, owner, entity, conversation, message, output])
        await db.commit()

        with pytest.raises(HTTPException) as messages_exc:
            await get_messages(
                session_id=conversation.id,
                db=db,
                current_user=admin,
            )
        assert messages_exc.value.status_code == 404

        with pytest.raises(HTTPException) as outputs_exc:
            await get_outputs(
                session_id=conversation.id,
                db=db,
                current_user=admin,
            )
        assert outputs_exc.value.status_code == 404

    await engine.dispose()
