import os
from datetime import datetime, timezone
from pathlib import Path
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{Path(__file__).resolve().parent / 'test_service.db'}",
)

from app.core.database import Base
from app.models.registration_application import RegistrationApplication
from app.models.user import User, UserRole, UserStatus
from app.services.registration_application_service import (
    RegistrationApplicationService,
)


@pytest.mark.asyncio
async def test_issue_invite_creates_new_organization_when_none_selected(tmp_path):
    db_path = tmp_path / "invite-service.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        reviewer = User(
            id=uuid.uuid4(),
            email="admin@example.com",
            is_active=True,
            status=UserStatus.ACTIVE,
            role=UserRole.INTERNAL_ADMIN,
        )
        application = RegistrationApplication(
            id=uuid.uuid4(),
            email="pending@example.com",
            organization_name="钛行测试",
            job_title="体验申请",
            created_at=datetime.now(timezone.utc),
        )
        session.add_all([reviewer, application])
        await session.commit()

        service = RegistrationApplicationService(session)

        async def fake_send_code(**_: object) -> dict[str, object]:
            return {
                "challenge_id": str(uuid.uuid4()),
                "expires_in_seconds": 604800,
                "debug_code": None,
            }

        service.verification.send_code = fake_send_code  # type: ignore[method-assign]

        updated = await service.issue_invite_code(
            application_id=application.id,
            reviewer_user_id=reviewer.id,
            organization_id=None,
        )

        assert updated.assigned_organization_id is not None
        assert updated.assigned_organization is not None
        assert updated.assigned_organization.legal_name == "钛行测试"
        assert updated.invite_code_sent_at is not None

    await engine.dispose()
