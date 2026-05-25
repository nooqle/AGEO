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
    f"sqlite+aiosqlite:///{Path(__file__).resolve().parent / 'test_ontology_governance.db'}",
)

from app.core.database import Base
from app.models.brand_intelligence import BrandObjectLink
from app.models.entity import Entity, EntityStatus
from app.services.brand_ontology_governance_service import (
    BrandOntologyGovernanceService,
)
from app.services.brand_ontology_world_service import BrandOntologyWorldService


async def _build_session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'governance.db'}")
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, session_factory


@pytest.mark.asyncio
async def test_governance_report_detects_broken_relationships(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="imspecta.com",
            industry="AI brand intelligence",
            description="Test brand",
            status=EntityStatus.ACTIVE,
        )
        broken_link = BrandObjectLink(
            entity_id=entity.id,
            link_type="brand_has_competitor",
            from_object_type="brand_entity",
            from_object_id=str(entity.id),
            to_object_type="competitor_entity",
            to_object_id=str(uuid.uuid4()),
        )
        session.add_all([entity, broken_link])
        await session.commit()

        world = await BrandOntologyWorldService(session).build_dashboard_summary(
            entity_id=entity.id,
        )

        assert world is not None
        governance = world["governance_report"]
        assert governance["status"] == "degraded"
        assert governance["link_audit"]["issue_count"] == 1
        assert governance["link_audit"]["issues"][0]["reason"] == (
            "target_object_missing"
        )
        relationship_check = {
            check["key"]: check for check in governance["checks"]
        }["relationship_integrity"]
        assert relationship_check["status"] == "warning"
    await engine.dispose()


@pytest.mark.asyncio
async def test_governance_report_blocks_unsafe_ready_action_plan(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="imspecta.com",
            industry="AI brand intelligence",
            description="Test brand",
            status=EntityStatus.ACTIVE,
        )
        session.add(entity)
        await session.commit()

        snapshot = await BrandOntologyWorldService(session).build_snapshot(
            entity_id=entity.id,
        )
        assert snapshot is not None
        report = await BrandOntologyGovernanceService(session).build_report(
            entity_id=entity.id,
            snapshot=snapshot,
            action_plan={
                "recommended_actions": [
                    {
                        "action_key": "confirm_question_set",
                        "readiness": "ready",
                        "requires_confirmation": True,
                        "missing_inputs": [],
                        "missing_objects": [],
                    }
                ]
            },
            audit_links=False,
        )

        assert report["status"] == "blocked"
        action_check = {check["key"]: check for check in report["checks"]}[
            "action_plan_safety"
        ]
        assert action_check["status"] == "failed"
        assert action_check["severity"] == "blocking"
    await engine.dispose()
