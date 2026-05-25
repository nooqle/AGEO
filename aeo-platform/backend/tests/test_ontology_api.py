from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{Path(__file__).resolve().parent / 'test_ontology_api.db'}",
)

from app.api.v1.ontology import (
    IntelligenceFindingFeedbackRequest,
    OntologyActionFeedbackRequest,
    RecommendationTaskRequest,
    _build_action_feedback_provided_inputs,
    get_ontology_object_view,
    get_ontology_world,
    list_ontology_object_links,
    list_ontology_objects,
    submit_ontology_action_feedback,
    submit_intelligence_finding_feedback,
    submit_recommendation_task_feedback,
)
from app.api.v1.entities import update_entity as update_entity_api
from app.core.database import Base
from app.models.brand_intelligence import (
    BrandActionRecord,
    BrandIntelligenceFinding,
    BrandUserDecision,
)
from app.models.entity import Entity, EntityStatus
from app.models.user import User, UserRole, UserStatus
from app.schemas.entity import EntityUpdate
from app.services.brand_intelligence_projection_service import (
    BrandIntelligenceProjectionService,
)


async def _build_session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'ontology-api.db'}")
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
async def test_ontology_object_view_api_requires_entity_access(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("owner@example.com")
        other = _user("other@example.com")
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

        with pytest.raises(HTTPException) as exc_info:
            await get_ontology_object_view(
                entity_id=str(entity.id),
                view_key="brand_intelligence_home",
                object_type="brand_entity",
                object_id=str(entity.id),
                db=session,
                current_user=other,
            )

        assert exc_info.value.status_code == 404
    await engine.dispose()


@pytest.mark.asyncio
async def test_ontology_object_view_api_returns_accessible_object_graph(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("owner-graph@example.com")
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

        projection_service = BrandIntelligenceProjectionService(session)
        await projection_service.persist_brand_context(
            entity_id=entity.id,
            session_id=None,
            competitors=[{"name": "Brandwatch"}],
            marketing_personas={
                "user_personas": [
                    {
                        "persona_id": "p1",
                        "persona_name": "市场负责人",
                        "usage_scenarios": [
                            {
                                "scenario_key": "s1",
                                "scenario_name": "竞品对比",
                            }
                        ],
                    }
                ]
            },
        )
        await session.commit()

        view = await get_ontology_object_view(
            entity_id=str(entity.id),
            view_key="brand_intelligence_home",
            object_type="brand_entity",
            object_id=str(entity.id),
            db=session,
            current_user=owner,
        )
        world = await get_ontology_world(
            entity_id=str(entity.id),
            db=session,
            current_user=owner,
        )
        links = await list_ontology_object_links(
            entity_id=str(entity.id),
            object_type="brand_entity",
            object_id=str(entity.id),
            direction="out",
            db=session,
            current_user=owner,
        )
        competitors = await list_ontology_objects(
            entity_id=str(entity.id),
            object_type="competitor_entity",
            db=session,
            current_user=owner,
        )

        assert view["object"]["properties"]["name"] == "Specta"
        assert view["view"]["key"] == "brand_intelligence_home"
        assert {link["link_type"] for link in view["links"]}.issuperset(
            {"brand_has_competitor", "brand_has_persona"}
        )
        assert links["total"] == 2
        assert competitors["total"] == 1
        assert competitors["objects"][0]["object_type"] == "competitor_entity"
        assert competitors["objects"][0]["lifecycle"]["status"] == "suggested"
        assert world["entity_id"] == str(entity.id)
        assert world["brand"]["label"] == "Specta"
        assert "action_queue" in world
        assert "relationship_summary" in world
    await engine.dispose()


@pytest.mark.asyncio
async def test_ontology_world_api_returns_public_knowledge_graph_contract(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("owner-world-contract@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="理想汽车",
            domain="li.auto",
            industry="新能源汽车",
            description="Test brand",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        session.add_all([owner, entity])
        await session.commit()

        projection_service = BrandIntelligenceProjectionService(session)
        await projection_service.persist_brand_context(
            entity_id=entity.id,
            session_id=None,
            competitors=[{"name": "小米汽车"}, {"name": "问界"}],
        )
        await projection_service.persist_fetch_results(
            entity_id=entity.id,
            session_id=None,
            fetch_results=[
                {
                    "question_id": "li-auto-family-suv",
                    "question_text": "家庭新能源 SUV 推荐谁？",
                    "platform_results": [
                        {
                            "platform": "yuanbao",
                            "fetch_method": "browser",
                            "success": True,
                            "answer": {
                                "content": "理想汽车适合家庭用户。",
                                "has_brand_mention": True,
                                "sentiment": "positive",
                                "mention_quote": "理想汽车适合家庭用户",
                                "citations": [
                                    {"url": "https://www.lixiang.com/news/family"}
                                ],
                            },
                        },
                        {
                            "platform": "doubao",
                            "fetch_method": "browser",
                            "success": True,
                            "answer": {
                                "content": "小米汽车和问界也适合对比。",
                                "has_brand_mention": False,
                                "competitor_mentions": [
                                    {"name": "小米汽车"},
                                    {"name": "问界"},
                                ],
                                "citations": [
                                    {"url": "https://www.dongchedi.com/article/family"}
                                ],
                            },
                        },
                    ],
                }
            ],
        )
        await session.commit()

        world = await get_ontology_world(
            entity_id=str(entity.id),
            db=session,
            current_user=owner,
        )

        assert world["projection_version"] >= 4
        graph_node_types = {node["type"] for node in world["graph_projection"]["nodes"]}
        assert "official_domain" in graph_node_types
        assert "answer_sample" in graph_node_types
        recommendation = world["recommendation_projection"]["recommendations"][0]
        assert recommendation["execution_steps"]
        assert recommendation["content_generation_brief"]
        assert "task_state" in recommendation
        assert "expected_impact" in recommendation
        assert "review_criteria" in recommendation
        rendered = json.dumps(world, ensure_ascii=False)
        assert "prompt_template" not in rendered
    await engine.dispose()


@pytest.mark.asyncio
async def test_recommendation_task_feedback_persists_and_returns_world_state(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("owner-recommendation-task@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="理想汽车",
            domain="li.auto",
            industry="新能源汽车",
            description="Test brand",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        session.add_all([owner, entity])
        await session.commit()

        projection_service = BrandIntelligenceProjectionService(session)
        await projection_service.persist_fetch_results(
            entity_id=entity.id,
            session_id=None,
            fetch_results=[
                {
                    "question_id": "li-auto-task",
                    "question_text": "家庭新能源 SUV 推荐谁？",
                    "platform_results": [
                        {
                            "platform": "yuanbao",
                            "fetch_method": "browser",
                            "success": True,
                            "answer": {
                                "content": "回答主要比较空间和补能。",
                                "has_brand_mention": False,
                                "citations": [
                                    {"url": "https://www.dongchedi.com/article/task"}
                                ],
                            },
                        }
                    ],
                }
            ],
        )
        await session.commit()

        first = await submit_recommendation_task_feedback(
            entity_id=str(entity.id),
            recommendation_id="mention-rate-content-gap",
            body=RecommendationTaskRequest(
                task_status="in_progress",
                owner_label="内容负责人",
                due_at="2026-06-01",
                review_at="2026-06-15",
                feedback_text="先补家庭场景内容。",
            ),
            db=session,
            current_user=owner,
        )
        second = await submit_recommendation_task_feedback(
            entity_id=str(entity.id),
            recommendation_id="mention-rate-content-gap",
            body=RecommendationTaskRequest(
                task_status="in_progress",
                owner_label="内容负责人",
                due_at="2026-06-01",
                review_at="2026-06-15",
                feedback_text="先补家庭场景内容。",
            ),
            db=session,
            current_user=owner,
        )
        decisions = (
            await session.execute(
                select(BrandUserDecision).where(
                    BrandUserDecision.entity_id == entity.id,
                    BrandUserDecision.decision_type == "recommendation_task",
                )
            )
        ).scalars().all()

        assert first["action_record"]["status"] == "applied"
        assert first["recommendation"]["task_state"] == "in_progress"
        assert first["recommendation"]["owner_label"] == "内容负责人"
        assert second["action_record"]["id"] == first["action_record"]["id"]
        assert len(decisions) == 1
        assert decisions[0].decision_key == "recommendation:mention-rate-content-gap"
        assert decisions[0].input_payload["task_status"] == "in_progress"

        with pytest.raises(HTTPException) as exc_info:
            await submit_recommendation_task_feedback(
                entity_id=str(entity.id),
                recommendation_id="missing-recommendation",
                body=RecommendationTaskRequest(task_status="not_started"),
                db=session,
                current_user=owner,
            )

        assert exc_info.value.status_code == 404
    await engine.dispose()


@pytest.mark.asyncio
async def test_recommendation_task_feedback_rejects_inaccessible_entity_without_write(
    tmp_path,
):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("owner-recommendation-access@example.com")
        other = _user("other-recommendation-access@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="理想汽车",
            domain="li.auto",
            industry="新能源汽车",
            description="Test brand",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        session.add_all([owner, other, entity])
        await session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await submit_recommendation_task_feedback(
                entity_id=str(entity.id),
                recommendation_id="mention-rate-content-gap",
                body=RecommendationTaskRequest(task_status="in_progress"),
                db=session,
                current_user=other,
            )
        action_rows = (
            await session.execute(
                select(BrandActionRecord).where(
                    BrandActionRecord.entity_id == entity.id,
                    BrandActionRecord.action_type == "record_user_feedback",
                )
            )
        ).scalars().all()

        assert exc_info.value.status_code == 404
        assert action_rows == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_intelligence_finding_feedback_api_returns_updated_world(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("owner-finding-api@example.com")
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
            finding_key="risk-1",
            title="AI answer source coverage is thin",
            summary="The current evidence set has few citation sources.",
            finding_type="evidence_gap",
            severity="medium",
            status="observed",
            evidence_summary="1 citation source.",
        )
        session.add_all([owner, entity, finding])
        await session.commit()

        response = await submit_intelligence_finding_feedback(
            entity_id=str(entity.id),
            finding_id=str(finding.id),
            body=IntelligenceFindingFeedbackRequest(
                feedback_type="dismiss",
                feedback_text="Not relevant to this review.",
            ),
            db=session,
            current_user=owner,
        )

        assert response["action_record"]["action_type"] == "record_user_feedback"
        assert response["action_record"]["status"] == "applied"
        assert "input_payload" not in response["action_record"]
        assert response["finding"]["status"] == "dismissed"
        world_findings = response["world"]["intelligence_findings"]
        assert world_findings[0]["object_id"] == str(finding.id)
        assert world_findings[0]["status"] == "dismissed"
    await engine.dispose()


@pytest.mark.asyncio
async def test_ontology_links_api_requires_existing_object(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("owner-missing-object@example.com")
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

        with pytest.raises(HTTPException) as exc_info:
            await list_ontology_object_links(
                entity_id=str(entity.id),
                object_type="brand_entity",
                object_id=str(uuid.uuid4()),
                direction="out",
                db=session,
                current_user=owner,
            )

        assert exc_info.value.status_code == 404
    await engine.dispose()


@pytest.mark.asyncio
async def test_entity_update_records_brand_profile_action(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("owner-update-entity@example.com")
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

        response = await update_entity_api(
            entity_id=str(entity.id),
            data=EntityUpdate(industry="Enterprise intelligence"),
            db=session,
            current_user=owner,
        )

        action = (
            await session.execute(
                select(BrandActionRecord).where(
                    BrandActionRecord.entity_id == entity.id,
                    BrandActionRecord.action_type == "update_brand_profile",
                )
            )
        ).scalar_one()

        assert response["industry"] == "Enterprise intelligence"
        assert action.actor_type == "user"
        assert action.status == "applied"
        assert action.requires_confirmation is True
        assert action.permission_scope == "entity_write"
        assert action.input_payload["profile_patch"]["industry"] == (
            "Enterprise intelligence"
        )
    await engine.dispose()


@pytest.mark.asyncio
async def test_ontology_action_feedback_records_user_decision_and_world(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("owner-action-feedback@example.com")
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

        response = await submit_ontology_action_feedback(
            entity_id=str(entity.id),
            action_key="generate_question_set",
            body=OntologyActionFeedbackRequest(
                feedback_type="defer",
                feedback_text="先不生成问题组。",
            ),
            db=session,
            current_user=owner,
        )
        decision = (
            await session.execute(
                select(BrandUserDecision).where(
                    BrandUserDecision.entity_id == entity.id,
                    BrandUserDecision.decision_type
                    == "ontology_action_queue_feedback",
                )
            )
        ).scalar_one()

        assert response["action_record"]["action_type"] == "record_user_feedback"
        assert response["action_record"]["status"] == "applied"
        assert response["world"]["entity_id"] == str(entity.id)
        queue_item = next(
            item
            for item in response["world"]["action_queue"]
            if item["action_key"] == "generate_question_set"
        )
        assert queue_item["has_user_feedback"] is True
        assert queue_item["latest_feedback_type"] == "defer"
        assert queue_item["user_feedback_state"] == "deferred"
        assert response["world"]["action_feedback_summary"]["total"] == 1
        assert decision.decision_key == "generate_question_set:defer"
        assert decision.target_object_type == "brand_entity"
        assert decision.target_object_id == str(entity.id)
    await engine.dispose()


@pytest.mark.asyncio
async def test_ontology_action_feedback_records_provided_inputs_without_public_values(
    tmp_path,
):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("owner-action-feedback-input@example.com")
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

        response = await submit_ontology_action_feedback(
            entity_id=str(entity.id),
            action_key="generate_question_set",
            body=OntologyActionFeedbackRequest(
                feedback_type="provide_input",
                provided_inputs={"generation_mode": "baseline_dynamic"},
                feedback_text="按品牌全景模式生成。",
            ),
            db=session,
            current_user=owner,
        )
        decision = (
            await session.execute(
                select(BrandUserDecision).where(
                    BrandUserDecision.entity_id == entity.id,
                    BrandUserDecision.decision_type
                    == "ontology_action_queue_feedback",
                )
            )
        ).scalar_one()
        feedback = response["world"]["action_feedback_summary"]["latest_by_action"][
            "generate_question_set"
        ]
        queue_item = next(
            item
            for item in response["world"]["action_queue"]
            if item["action_key"] == "generate_question_set"
        )

        assert decision.input_payload["provided_inputs"] == {
            "generation_mode": "baseline_dynamic"
        }
        assert feedback["provided_input_keys"] == ["generation_mode"]
        assert "provided_inputs" not in feedback
        assert queue_item["provided_input_keys"] == ["generation_mode"]
        assert queue_item["user_feedback_state"] == "input_provided"
    await engine.dispose()


def test_ontology_action_feedback_rejects_large_plain_text_input_fallback():
    with pytest.raises(HTTPException) as exc_info:
        _build_action_feedback_provided_inputs(
            queue_item={
                "missing_inputs": ["operator_note"],
                "defaulted_inputs": [],
            },
            body=OntologyActionFeedbackRequest.model_construct(
                feedback_type="provide_input",
                feedback_text="x" * 5000,
                provided_inputs=None,
                origin_event_id=None,
            ),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Action input feedback is too large"


@pytest.mark.asyncio
async def test_ontology_action_feedback_rejects_action_outside_queue(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("owner-action-feedback-outside-queue@example.com")
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

        with pytest.raises(HTTPException) as exc_info:
            await submit_ontology_action_feedback(
                entity_id=str(entity.id),
                action_key="update_brand_profile",
                body=OntologyActionFeedbackRequest(
                    feedback_type="confirm",
                    feedback_text="不要把非队列动作写入队列反馈。",
                ),
                db=session,
                current_user=owner,
            )

        action_count = (
            await session.execute(
                select(BrandActionRecord).where(
                    BrandActionRecord.entity_id == entity.id,
                    BrandActionRecord.action_type == "record_user_feedback",
                )
            )
        ).scalars().all()

        assert exc_info.value.status_code == 400
        assert action_count == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_ontology_action_feedback_rejects_mismatched_feedback_type(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("owner-action-feedback-mismatch@example.com")
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

        with pytest.raises(HTTPException) as exc_info:
            await submit_ontology_action_feedback(
                entity_id=str(entity.id),
                action_key="generate_question_set",
                body=OntologyActionFeedbackRequest(
                    feedback_type="confirm",
                    feedback_text="这个动作不是等待确认态。",
                ),
                db=session,
                current_user=owner,
            )

        action_count = (
            await session.execute(
                select(BrandActionRecord).where(
                    BrandActionRecord.entity_id == entity.id,
                    BrandActionRecord.action_type == "record_user_feedback",
                )
            )
        ).scalars().all()

        assert exc_info.value.status_code == 400
        assert action_count == []
    await engine.dispose()
