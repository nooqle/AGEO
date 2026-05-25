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
    f"sqlite+aiosqlite:///{Path(__file__).resolve().parent / 'test_brand_action.db'}",
)

from app.core.database import Base
from app.models.brand_intelligence import (
    BrandActionRecord,
    BrandCompetitorEntity,
    BrandIntelligenceFinding,
    BrandIntelligenceQuestion,
    BrandObjectLink,
    BrandPlatformAnswer,
    BrandUserDecision,
)
from app.models.entity import Entity, EntityStatus
from app.models.user import User, UserRole, UserStatus
from app.ontology import OntologyRegistryError
from app.services.brand_action_service import BrandActionService
from app.services.brand_object_link_service import BrandObjectLinkService


async def _build_session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'action.db'}")
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, session_factory


def _active_user(email: str) -> User:
    return User(
        id=uuid.uuid4(),
        email=email,
        is_active=True,
        status=UserStatus.ACTIVE,
        role=UserRole.CUSTOMER_USER,
    )


@pytest.mark.asyncio
async def test_record_applied_action_creates_action_record_and_brand_link(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _active_user("owner@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="imspecta.com",
            industry="AI brand intelligence",
            description="Test brand",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        session.add_all([owner, entity])
        await session.commit()

        service = BrandActionService(session)
        record = await service.record_applied_action(
            entity_id=entity.id,
            action_type="generate_question_set",
            user_id=owner.id,
            actor_type="user",
            origin_surface="chat",
            origin_event_id="message-1",
            input_payload={"generation_mode": "test_generation", "question_count": 3},
            output_payload={"questions": 3},
        )
        await session.commit()

        action_rows = (await session.execute(select(BrandActionRecord))).scalars().all()
        link_rows = (await session.execute(select(BrandObjectLink))).scalars().all()
        decision_rows = (
            (await session.execute(select(BrandUserDecision))).scalars().all()
        )

        assert action_rows == [record]
        assert record.status == "applied"
        assert record.permission_scope == "entity_execute"
        assert record.requires_confirmation is False
        assert record.actor_type == "user"
        assert record.origin_surface == "chat"
        assert record.origin_event_id == "message-1"
        assert record.input_payload["brand_entity_id"] == str(entity.id)
        assert record.input_payload["actor_id"]
        assert "_action_validation_warnings" not in record.input_payload
        assert record.output_payload == {"questions": 3}
        assert len(decision_rows) == 1
        assert decision_rows[0].action_record_id == record.id
        assert decision_rows[0].status == "applied"
        assert decision_rows[0].decision_type == "generate_question_set"
        assert decision_rows[0].target_object_type == "brand_entity"
        assert decision_rows[0].target_object_id == str(entity.id)
        link_types = {link.link_type for link in link_rows}
        assert link_types == {
            "action_record_affects_brand",
            "user_decision_confirms_action_record",
        }
        brand_link = next(
            link
            for link in link_rows
            if link.link_type == "action_record_affects_brand"
        )
        decision_link = next(
            link
            for link in link_rows
            if link.link_type == "user_decision_confirms_action_record"
        )
        assert brand_link.from_object_id == str(record.id)
        assert brand_link.to_object_id == str(entity.id)
        assert brand_link.source_action_record_id == record.id
        assert decision_link.from_object_id == str(decision_rows[0].id)
        assert decision_link.to_object_id == str(record.id)
        assert decision_link.source_action_record_id == record.id
    await engine.dispose()


@pytest.mark.asyncio
async def test_intelligence_finding_feedback_updates_status_and_links(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _active_user("owner-finding-feedback@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="imspecta.com",
            industry="AI brand intelligence",
            description="Test brand",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        finding = BrandIntelligenceFinding(
            entity_id=entity.id,
            finding_key="visibility-risk",
            title="AI answer visibility is unstable",
            summary="Visibility differs across platforms.",
            finding_type="risk",
            severity="high",
            status="observed",
            evidence_summary="2 questions, 3 answers.",
        )
        session.add_all([owner, entity, finding])
        await session.commit()

        service = BrandActionService(session)
        record, updated = await service.record_intelligence_finding_feedback(
            entity_id=entity.id,
            finding_id=finding.id,
            user_id=owner.id,
            feedback_type="validate",
            feedback_text="Matches the weekly review.",
        )
        duplicate, _ = await service.record_intelligence_finding_feedback(
            entity_id=entity.id,
            finding_id=finding.id,
            user_id=owner.id,
            feedback_type="validate",
            feedback_text="Matches the weekly review.",
        )
        await session.commit()

        decisions = (await session.execute(select(BrandUserDecision))).scalars().all()
        links = (await session.execute(select(BrandObjectLink))).scalars().all()
        assert record.id == duplicate.id
        assert updated.status == "validated"
        assert record.action_type == "record_user_feedback"
        assert record.status == "applied"
        assert record.input_payload["feedback_type"] == "validate"
        assert record.input_payload["finding_id"] == str(finding.id)
        assert record.output_payload == {
            "feedback_type": "validate",
            "finding_id": str(finding.id),
            "finding_status": "validated",
        }
        assert len(decisions) == 1
        assert decisions[0].target_object_type == "intelligence_finding"
        assert decisions[0].target_object_id == str(finding.id)
        assert decisions[0].decision_type == "validate"
        link_types = {link.link_type for link in links}
        assert link_types == {
            "action_record_affects_brand",
            "action_record_handles_intelligence_finding",
            "user_decision_confirms_action_record",
            "user_decision_updates_intelligence_finding",
        }
        assert len(links) == 4
    await engine.dispose()


@pytest.mark.asyncio
async def test_intelligence_finding_feedback_rejects_wrong_brand(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _active_user("owner-finding-wrong-brand@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="imspecta.com",
            industry="AI brand intelligence",
            description="Test brand",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        other_entity = Entity(
            id=uuid.uuid4(),
            name="Other",
            domain="other.example.com",
            industry="AI brand intelligence",
            description="Other brand",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        finding = BrandIntelligenceFinding(
            entity_id=other_entity.id,
            finding_key="other-risk",
            title="Other risk",
            summary="Other summary.",
            status="observed",
        )
        session.add_all([owner, entity, other_entity, finding])
        await session.commit()

        service = BrandActionService(session)
        with pytest.raises(ValueError, match="finding not found"):
            await service.record_intelligence_finding_feedback(
                entity_id=entity.id,
                finding_id=finding.id,
                user_id=owner.id,
                feedback_type="validate",
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_finding_feedback_idempotency_includes_feedback_type(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _active_user("owner-finding-idempotency@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="imspecta.com",
            industry="AI brand intelligence",
            description="Test brand",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        finding = BrandIntelligenceFinding(
            entity_id=entity.id,
            finding_key="finding-1",
            title="Finding 1",
            summary="Summary.",
            status="observed",
        )
        session.add_all([owner, entity, finding])
        await session.commit()

        service = BrandActionService(session)
        first, _ = await service.record_intelligence_finding_feedback(
            entity_id=entity.id,
            finding_id=finding.id,
            user_id=owner.id,
            feedback_type="validate",
            origin_event_id="same-ui-event",
        )
        second, updated = await service.record_intelligence_finding_feedback(
            entity_id=entity.id,
            finding_id=finding.id,
            user_id=owner.id,
            feedback_type="dismiss",
            origin_event_id="same-ui-event",
        )
        await session.commit()

        records = (await session.execute(select(BrandActionRecord))).scalars().all()
        assert first.id != second.id
        assert len(records) == 2
        assert "validate" in first.origin_event_id
        assert "dismiss" in second.origin_event_id
        assert updated.status == "dismissed"
    await engine.dispose()


@pytest.mark.asyncio
async def test_start_action_rejects_unknown_action_type(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        service = BrandActionService(session)

        with pytest.raises(OntologyRegistryError, match="missing_action"):
            await service.start_action(
                entity_id=uuid.uuid4(),
                action_type="missing_action",
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_start_action_rejects_unknown_actor_type(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        service = BrandActionService(session)

        with pytest.raises(ValueError, match="actor_type"):
            await service.start_action(
                entity_id=uuid.uuid4(),
                action_type="generate_question_set",
                actor_type="browser_button",
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_object_link_preserves_initial_source_action(tmp_path):
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

        action_service = BrandActionService(session)
        first = await action_service.start_action(
            entity_id=entity.id,
            action_type="run_answer_fetch",
            input_payload={
                "question_ids": ["question-1"],
                "platforms": ["deepseek"],
            },
        )
        second = await action_service.start_action(
            entity_id=entity.id,
            action_type="run_answer_fetch",
            input_payload={
                "question_ids": ["question-1"],
                "platforms": ["deepseek"],
            },
        )
        link_service = BrandObjectLinkService(session)
        question = BrandIntelligenceQuestion(
            entity_id=entity.id,
            question_id="question-1",
            question_text="AI 会如何推荐 Specta？",
            status="confirmed",
        )
        answer = BrandPlatformAnswer(
            entity_id=entity.id,
            question_id="question-1",
            question_object_id=question.id,
            dedupe_key=f"{entity.id}:question-1:deepseek",
            platform="deepseek",
            fetch_method="api",
            status="captured",
            success=True,
            answer_text="Specta 是品牌情报工作台。",
        )
        session.add_all([question, answer])
        await session.flush()
        await link_service.ensure_link(
            entity_id=entity.id,
            link_type="question_answered_by",
            from_object_type="simulated_question",
            from_object_id=str(question.id),
            to_object_type="platform_answer",
            to_object_id=str(answer.id),
            source_action_record_id=first.id,
        )
        link = await link_service.ensure_link(
            entity_id=entity.id,
            link_type="question_answered_by",
            from_object_type="simulated_question",
            from_object_id=str(question.id),
            to_object_type="platform_answer",
            to_object_id=str(answer.id),
            source_action_record_id=second.id,
        )
        await session.commit()

        assert link.source_action_record_id == first.id
    await engine.dispose()


@pytest.mark.asyncio
async def test_confirmed_action_cannot_be_executed_by_agent_without_user_parent(
    tmp_path,
):
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

        service = BrandActionService(session)
        with pytest.raises(PermissionError, match="requires a user parent"):
            await service.start_action(
                entity_id=entity.id,
                action_type="create_monitoring_plan",
                actor_type="agent",
                input_payload={
                    "question_ids": ["question-1"],
                    "cadence": "weekly",
                },
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_action_idempotency_and_payload_redaction(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _active_user("owner-redaction@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="imspecta.com",
            industry="AI brand intelligence",
            description="Test brand",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        session.add_all([owner, entity])
        await session.commit()

        service = BrandActionService(session)
        first = await service.record_applied_action(
            entity_id=entity.id,
            action_type="record_user_feedback",
            user_id=owner.id,
            actor_type="user",
            origin_surface="chat",
            origin_event_id="duplicate-event",
            input_payload={
                "feedback_type": "runtime_smoke",
                "api_key": "secret-value",
            },
            output_payload={"answer_text": "raw answer should not be exposed"},
        )
        second = await service.record_applied_action(
            entity_id=entity.id,
            action_type="record_user_feedback",
            user_id=owner.id,
            actor_type="user",
            origin_surface="chat",
            origin_event_id="duplicate-event",
            input_payload={
                "feedback_type": "runtime_smoke",
                "api_key": "secret-value",
            },
            output_payload={"answer_text": "duplicate should not overwrite first"},
        )
        await session.commit()

        rows = (await session.execute(select(BrandActionRecord))).scalars().all()
        assert first.id == second.id
        assert len(rows) == 1
        assert rows[0].input_payload["api_key"] == "[redacted]"
        assert rows[0].output_payload["answer_text"] == "[redacted]"
        assert rows[0].completed_at == first.completed_at
    await engine.dispose()


@pytest.mark.asyncio
async def test_agent_action_can_reference_user_feedback_parent(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _active_user("owner-feedback@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="imspecta.com",
            industry="AI brand intelligence",
            description="Test brand",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        session.add_all([owner, entity])
        await session.commit()

        service = BrandActionService(session)
        user_feedback = await service.record_applied_action(
            entity_id=entity.id,
            action_type="record_user_feedback",
            user_id=owner.id,
            actor_type="user",
            origin_surface="chat_confirmation",
            origin_event_id="request-1",
            input_payload={"feedback_type": "run_answer_fetch"},
        )
        agent_action = await service.record_applied_action(
            entity_id=entity.id,
            action_type="run_answer_fetch",
            parent_action_record_id=user_feedback.id,
            actor_type="agent",
            origin_surface="workflow_node",
            origin_event_id="run-1",
            input_payload={
                "question_ids": ["question-1"],
                "platforms": ["deepseek"],
            },
        )
        await session.commit()

        assert user_feedback.actor_type == "user"
        assert agent_action.actor_type == "agent"
        assert agent_action.parent_action_record_id == user_feedback.id
        decisions = (await session.execute(select(BrandUserDecision))).scalars().all()
        assert len(decisions) == 1
        assert decisions[0].action_record_id == user_feedback.id
        assert decisions[0].decision_type == "run_answer_fetch"
    await engine.dispose()


@pytest.mark.asyncio
async def test_failed_user_action_marks_decision_failed(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _active_user("owner-failed@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="imspecta.com",
            industry="AI brand intelligence",
            description="Test brand",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        session.add_all([owner, entity])
        await session.commit()

        service = BrandActionService(session)
        record = await service.start_action(
            entity_id=entity.id,
            action_type="record_user_feedback",
            user_id=owner.id,
            actor_type="user",
            input_payload={"feedback_type": "bad_request"},
        )
        await service.fail_action(record, error_message="validation failed")
        await session.commit()

        decision = (await session.execute(select(BrandUserDecision))).scalar_one()
        assert record.status == "failed"
        assert decision.status == "failed"
        assert decision.action_record_id == record.id
    await engine.dispose()


@pytest.mark.asyncio
async def test_action_validation_rejects_missing_required_inputs_by_default(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        service = BrandActionService(session)

        with pytest.raises(ValueError, match="generation_mode"):
            await service.start_action(
                entity_id=uuid.uuid4(),
                action_type="generate_question_set",
                actor_type="agent",
                input_payload={"question_count": 3},
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_user_entity_write_action_forces_strict_validation(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _active_user("owner-strict-write@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="imspecta.com",
            industry="AI brand intelligence",
            description="Test brand",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        session.add_all([owner, entity])
        await session.commit()

        service = BrandActionService(session)

        with pytest.raises(ValueError, match="question_ids"):
            await service.start_action(
                entity_id=entity.id,
                action_type="confirm_question_set",
                user_id=owner.id,
                actor_type="user",
                input_payload={},
                strict_input_validation=False,
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_update_monitoring_plan_action_forces_lifecycle_payload(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _active_user("owner-monitoring-action@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="imspecta.com",
            industry="AI brand intelligence",
            description="Test brand",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        session.add_all([owner, entity])
        await session.commit()

        service = BrandActionService(session)

        with pytest.raises(ValueError, match="change_type"):
            await service.start_action(
                entity_id=entity.id,
                action_type="update_monitoring_plan",
                user_id=owner.id,
                actor_type="user",
                input_payload={"monitoring_plan_id": str(uuid.uuid4())},
                strict_input_validation=False,
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_user_action_rejects_non_manager(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _active_user("owner-denied@example.com")
        other = _active_user("other-denied@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="imspecta.com",
            industry="AI brand intelligence",
            description="Test brand",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        session.add_all([owner, other, entity])
        await session.commit()

        service = BrandActionService(session)

        with pytest.raises(PermissionError, match="not allowed"):
            await service.record_applied_action(
                entity_id=entity.id,
                action_type="record_user_feedback",
                user_id=other.id,
                actor_type="user",
                input_payload={"feedback_type": "run_answer_fetch"},
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_agent_action_rejects_missing_entity(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        service = BrandActionService(session)

        with pytest.raises(ValueError, match="Brand entity not found"):
            await service.start_action(
                entity_id=uuid.uuid4(),
                action_type="run_answer_fetch",
                actor_type="agent",
                input_payload={
                    "question_ids": ["question-1"],
                    "platforms": ["deepseek"],
                },
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_user_action_rejects_inactive_user(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        inactive = User(
            id=uuid.uuid4(),
            email="inactive@example.com",
            is_active=False,
            status=UserStatus.DISABLED,
            role=UserRole.CUSTOMER_USER,
        )
        entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="imspecta.com",
            industry="AI brand intelligence",
            description="Test brand",
            status=EntityStatus.ACTIVE,
            owner_user_id=inactive.id,
        )
        session.add_all([inactive, entity])
        await session.commit()

        service = BrandActionService(session)

        with pytest.raises(PermissionError, match="not an active user"):
            await service.record_applied_action(
                entity_id=entity.id,
                action_type="record_user_feedback",
                user_id=inactive.id,
                actor_type="user",
                input_payload={"feedback_type": "run_answer_fetch"},
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_object_link_rejects_unregistered_or_mismatched_contract(tmp_path):
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
        other_entity = Entity(
            id=uuid.uuid4(),
            name="Other",
            domain="other.example.com",
            industry="AI brand intelligence",
            description="Other brand",
            status=EntityStatus.ACTIVE,
        )
        other_competitor = BrandCompetitorEntity(
            entity_id=other_entity.id,
            competitor_key="other",
            normalized_name="Other Competitor",
            status="suggested",
        )
        session.add_all([entity, other_entity, other_competitor])
        await session.commit()

        service = BrandObjectLinkService(session)

        with pytest.raises(OntologyRegistryError, match="missing_link"):
            await service.ensure_link(
                entity_id=uuid.uuid4(),
                link_type="missing_link",
                from_object_type="brand_entity",
                from_object_id="brand-1",
                to_object_type="competitor_entity",
                to_object_id="competitor-1",
            )

        with pytest.raises(ValueError, match="from_object"):
            await service.ensure_link(
                entity_id=uuid.uuid4(),
                link_type="brand_has_competitor",
                from_object_type="competitor_entity",
                from_object_id="competitor-1",
                to_object_type="brand_entity",
                to_object_id="brand-1",
            )

        with pytest.raises(ValueError, match="to_object"):
            await service.ensure_link(
                entity_id=uuid.uuid4(),
                link_type="brand_has_competitor",
                from_object_type="brand_entity",
                from_object_id="brand-1",
                to_object_type="brand_entity",
                to_object_id="brand-1",
            )

        with pytest.raises(ValueError, match="from_object_id"):
            await service.ensure_link(
                entity_id=uuid.uuid4(),
                link_type="brand_has_competitor",
                from_object_type="brand_entity",
                from_object_id="",
                to_object_type="competitor_entity",
                to_object_id="competitor-1",
            )

        with pytest.raises(ValueError, match="source object not found"):
            await service.ensure_link(
                entity_id=entity.id,
                link_type="brand_has_competitor",
                from_object_type="brand_entity",
                from_object_id=str(uuid.uuid4()),
                to_object_type="competitor_entity",
                to_object_id=str(other_competitor.id),
            )

        with pytest.raises(ValueError, match="target object not found"):
            await service.ensure_link(
                entity_id=entity.id,
                link_type="brand_has_competitor",
                from_object_type="brand_entity",
                from_object_id=str(entity.id),
                to_object_type="competitor_entity",
                to_object_id=str(other_competitor.id),
            )
    await engine.dispose()
