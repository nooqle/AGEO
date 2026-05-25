from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{Path(__file__).resolve().parent / 'test_ontology_object.db'}",
)

from app.core.database import Base
from app.models.brand_intelligence import BrandCompetitorEntity
from app.models.entity import Entity, EntityStatus
from app.models.user import User, UserRole, UserStatus
from app.services.brand_action_service import BrandActionService
from app.services.brand_intelligence_projection_service import (
    BrandIntelligenceProjectionService,
)
from app.services.brand_ontology_object_service import BrandOntologyObjectService


async def _build_session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'object.db'}")
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


@pytest.fixture(autouse=True)
def _stub_official_website_content_audit(monkeypatch):
    async def _fake_fetch_page_features(url: str):
        return {
            "crawl_readable": True,
            "http_status": 200,
            "final_url": url,
            "content_type": "text/html; charset=utf-8",
            "fetch_failure_reason": "",
            "fetched_title": "Li Auto 理想汽车官网",
            "meta_description": "理想汽车面向家庭用户提供智能电动车产品与服务。",
            "has_h1": True,
            "h1_texts": ["创造移动的家，创造幸福的家"],
            "h1_count": 1,
            "h2_texts": ["品牌", "产品", "服务"],
            "h2_count": 3,
            "has_main": True,
            "has_article": False,
            "body_text_length": 1200,
            "body_text_excerpt": "理想汽车 Li Auto 家庭智能电动车 产品 服务 官方网站",
            "script_count": 8,
            "has_noscript": False,
            "schema_types": ["Organization", "WebSite"],
            "published_at": "",
        }

    monkeypatch.setattr(
        "app.services.brand_evidence_denoising_service.fetch_page_features",
        _fake_fetch_page_features,
    )


@pytest.mark.asyncio
async def test_object_view_returns_brand_object_and_relationships(tmp_path):
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

        object_service = BrandOntologyObjectService(session)
        view = await object_service.get_object_view(
            entity_id=entity.id,
            object_type="brand_entity",
            object_id=str(entity.id),
            view_key="brand_intelligence_home",
        )

        assert view is not None
        assert view["object"]["object_type"] == "brand_entity"
        assert view["object"]["properties"]["name"] == "Specta"
        assert view["object"]["lifecycle"]["status"] == "active"
        link_types = {link["link_type"] for link in view["links"]}
        assert {"brand_has_competitor", "brand_has_persona"}.issubset(link_types)

        competitors = await object_service.list_objects(
            entity_id=entity.id,
            object_type="competitor_entity",
        )
        assert competitors["total"] == 1
        assert competitors["objects"][0]["lifecycle"]["status"] == "suggested"
    await engine.dispose()


@pytest.mark.asyncio
async def test_sensitive_action_objects_are_redacted(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _active_user("owner-redacted@example.com")
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

        action_service = BrandActionService(session)
        record = await action_service.record_applied_action(
            entity_id=entity.id,
            action_type="record_user_feedback",
            user_id=owner.id,
            actor_type="user",
            input_payload={"feedback_type": "run_answer_fetch"},
            output_payload={"internal": "value"},
            feedback_text="private feedback",
        )
        await session.commit()

        object_service = BrandOntologyObjectService(session)
        payload = await object_service.get_object(
            entity_id=entity.id,
            object_type="action_record",
            object_id=str(record.id),
        )

        assert payload is not None
        properties = payload["properties"]
        assert properties["action_type"] == "record_user_feedback"
        assert "input_payload" not in properties
        assert "output_payload" not in properties
        assert "error_message" not in properties
        assert "user_id" not in properties

        collection = await object_service.list_objects(
            entity_id=entity.id,
            object_type="action_record",
        )
        collection_properties = collection["objects"][0]["properties"]
        assert collection["total"] == 1
        assert "input_payload" not in collection_properties
        assert "output_payload" not in collection_properties
        assert "user_id" not in collection_properties
    await engine.dispose()


@pytest.mark.asyncio
async def test_answer_objects_expose_preview_not_raw_payload(tmp_path):
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

        projection_service = BrandIntelligenceProjectionService(session)
        await projection_service.persist_fetch_results(
            entity_id=entity.id,
            session_id=None,
            fetch_results=[
                {
                    "question_id": "q-1",
                    "question_text": "AI 会如何推荐 Specta？",
                    "platform_results": [
                        {
                            "platform": "kimi",
                            "fetch_method": "api",
                            "success": True,
                            "status": "success",
                            "answer": {
                                "content": "Specta 是一个面向品牌团队的 AI 情报工作台。",
                                "citations": [{"url": "https://imspecta.com/"}],
                            },
                            "prompt": "internal prompt should stay private",
                        }
                    ],
                }
            ],
        )
        await session.commit()

        object_service = BrandOntologyObjectService(session)
        collection = await object_service.list_objects(
            entity_id=entity.id,
            object_type="platform_answer",
        )
        properties = collection["objects"][0]["properties"]

        assert properties["platform"] == "kimi"
        assert properties["answer_preview"].startswith("Specta 是一个面向品牌团队")
        assert "answer_text" not in properties
        assert "answer_payload" not in properties
        assert "raw_payload" not in properties
        assert "internal prompt" not in str(properties)
    await engine.dispose()


@pytest.mark.asyncio
async def test_object_service_rejects_cross_entity_reads(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        first_entity = Entity(
            id=uuid.uuid4(),
            name="Specta",
            domain="imspecta.com",
            industry="AI brand intelligence",
            description="Test brand",
            status=EntityStatus.ACTIVE,
        )
        second_entity = Entity(
            id=uuid.uuid4(),
            name="Other",
            domain="other.example.com",
            industry="AI brand intelligence",
            description="Other brand",
            status=EntityStatus.ACTIVE,
        )
        session.add_all([first_entity, second_entity])
        await session.commit()

        object_service = BrandOntologyObjectService(session)
        row = await object_service.get_object(
            entity_id=second_entity.id,
            object_type="brand_entity",
            object_id=str(first_entity.id),
        )

        assert row is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_object_service_rejects_invalid_lifecycle_status(tmp_path):
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
        competitor = BrandCompetitorEntity(
            entity_id=entity.id,
            competitor_key="bad-status",
            normalized_name="Bad Status",
            status="stale",
        )
        session.add_all([entity, competitor])
        await session.commit()

        object_service = BrandOntologyObjectService(session)

        with pytest.raises(ValueError, match="invalid lifecycle status"):
            await object_service.get_object(
                entity_id=entity.id,
                object_type="competitor_entity",
                object_id=str(competitor.id),
            )
    await engine.dispose()


@pytest.mark.asyncio
async def test_object_collection_filters_sorts_and_paginates(tmp_path):
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
        now = datetime.now(timezone.utc)
        older = BrandCompetitorEntity(
            entity_id=entity.id,
            competitor_key="older",
            normalized_name="Older Competitor",
            status="suggested",
            created_at=now - timedelta(days=2),
        )
        newer = BrandCompetitorEntity(
            entity_id=entity.id,
            competitor_key="newer",
            normalized_name="Newer Competitor",
            status="confirmed",
            created_at=now - timedelta(hours=1),
        )
        session.add_all([entity, older, newer])
        await session.commit()

        object_service = BrandOntologyObjectService(session)
        confirmed = await object_service.list_objects(
            entity_id=entity.id,
            object_type="competitor_entity",
            status="confirmed",
        )
        ordered = await object_service.list_objects(
            entity_id=entity.id,
            object_type="competitor_entity",
            sort="created_at_asc",
            limit=1,
            offset=1,
        )
        recent = await object_service.list_objects(
            entity_id=entity.id,
            object_type="competitor_entity",
            created_after=now - timedelta(days=1),
        )

        assert confirmed["total"] == 1
        assert confirmed["objects"][0]["properties"]["normalized_name"] == (
            "Newer Competitor"
        )
        assert ordered["total"] == 2
        assert ordered["objects"][0]["properties"]["normalized_name"] == (
            "Newer Competitor"
        )
        assert recent["total"] == 1
        assert recent["objects"][0]["object_id"] == str(newer.id)
    await engine.dispose()


@pytest.mark.asyncio
async def test_derived_evidence_objects_include_official_website_asset(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        entity = Entity(
            id=uuid.uuid4(),
            name="Li Auto",
            domain="https://www.lixiang.com",
            industry="EV",
            description="Business brand",
            status=EntityStatus.ACTIVE,
        )
        session.add(entity)
        await session.commit()

        projection_service = BrandIntelligenceProjectionService(session)
        await projection_service.persist_fetch_results(
            entity_id=entity.id,
            session_id=None,
            fetch_results=[
                {
                    "question_id": "q1",
                    "question_text": "家庭用户会如何选择 Li Auto？",
                    "category": "家庭购车",
                    "platform_results": [
                        {
                            "platform": "kimi",
                            "fetch_method": "api",
                            "success": True,
                            "status": "success",
                            "answer": {
                                "content": "Li Auto 常被描述为家庭智能电动车品牌。",
                                "has_brand_mention": True,
                                "citations": [
                                    {
                                        "url": "https://www.lixiang.com/",
                                        "title": "Li Auto 官网",
                                        "snippet": "家庭智能电动车品牌介绍。",
                                        "confidence": 0.92,
                                        "url_intelligence": {
                                            "site_name": "Li Auto 官网",
                                            "category": "企业官网",
                                        },
                                    },
                                    {
                                        "url": "https://www.autohome.com.cn/news/a",
                                        "title": "汽车之家评测",
                                        "snippet": "家庭SUV评测提到Li Auto。",
                                        "url_intelligence": {
                                            "site_name": "汽车之家",
                                            "category": "汽车垂直媒体",
                                        },
                                    },
                                ],
                            },
                        }
                    ],
                }
            ],
        )
        await session.commit()

        object_service = BrandOntologyObjectService(session)
        official_collection = await object_service.list_objects(
            entity_id=entity.id,
            object_type="official_website_asset",
        )
        source_collection = await object_service.list_objects(
            entity_id=entity.id,
            object_type="source_domain",
        )
        cluster_collection = await object_service.list_objects(
            entity_id=entity.id,
            object_type="evidence_cluster",
        )

        assert official_collection["total"] == 1
        official_object = official_collection["objects"][0]
        assert official_object["object_id"] == "lixiang.com"
        assert official_object["lifecycle"]["status"] in {"visible", "strong"}
        assert official_object["properties"]["sampling_policy"]["object_type"] == (
            "official_website_asset"
        )
        assert official_object["properties"]["content_audit"]["status"] == (
            "content_ready"
        )
        assert (
            official_object["properties"]["content_audit"]["brand_name_in_body"]
            is True
        )
        assert all(
            sample["is_official"]
            for sample in official_object["properties"]["samples"]
        )

        fetched_official = await object_service.get_object(
            entity_id=entity.id,
            object_type="official_website_asset",
            object_id="lixiang.com",
        )
        assert fetched_official == official_object

        source_domains = {
            item["object_id"]: item for item in source_collection["objects"]
        }
        assert {"lixiang.com", "autohome.com.cn"}.issubset(source_domains)
        assert source_domains["lixiang.com"]["lifecycle"]["status"] == "derived"
        assert source_domains["lixiang.com"]["properties"]["is_official"] is True

        assert cluster_collection["total"] >= 2
        assert all(
            item["lifecycle"]["status"] == "derived"
            for item in cluster_collection["objects"]
        )
        assert "raw_payload" not in json.dumps(
            official_collection,
            ensure_ascii=False,
        )

        official_counts = await object_service.count_lifecycle_statuses(
            entity_id=entity.id,
            object_type="official_website_asset",
        )
        assert sum(official_counts.values()) == 1
        source_counts = await object_service.count_lifecycle_statuses(
            entity_id=entity.id,
            object_type="source_domain",
        )
        assert source_counts == {"derived": source_collection["total"]}
    await engine.dispose()
