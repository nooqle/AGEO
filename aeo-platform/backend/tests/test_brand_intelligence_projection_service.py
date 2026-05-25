from __future__ import annotations

import uuid
import os
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{Path(__file__).resolve().parent / 'test_brand_intel.db'}",
)

from app.core.database import Base
from app.models.brand_intelligence import (
    BrandAudiencePersona,
    BrandCitationSource,
    BrandCompetitorEntity,
    BrandEvidenceSet,
    BrandIntelligenceFinding,
    BrandIntelligenceQuestion,
    BrandMetricSnapshot,
    BrandMention,
    BrandObjectLink,
    BrandPlatformAnswer,
    BrandReportVersion,
    BrandUsageScenario,
)
from app.models.entity import Entity, EntityStatus
from app.services.brand_intelligence_projection_service import (
    BrandIntelligenceProjectionService,
)


def test_normalize_questions_from_a3_payload():
    payload = {
        "simulated_questions": [
            {
                "question_id": "q-1",
                "core_question": "AI 会如何推荐品牌情报工具？",
                "category": "购买决策",
                "subcategory": "工具选择",
                "user_intent": "寻找替代方案",
                "decision_stage": "comparison",
            }
        ]
    }

    questions = BrandIntelligenceProjectionService.normalize_questions(payload)

    assert len(questions) == 1
    assert questions[0].question_id == "q-1"
    assert questions[0].question_text == "AI 会如何推荐品牌情报工具？"
    assert questions[0].category == "购买决策"


def test_normalize_fetch_results_builds_answer_and_citation_chain():
    bundle = BrandIntelligenceProjectionService.normalize_fetch_results(
        [
            {
                "question_id": "q-1",
                "question_text": "AI 会如何推荐品牌情报工具？",
                "platform_results": [
                    {
                        "platform": "hunyuan",
                        "fetch_method": "api",
                        "success": True,
                        "answer": {
                            "content": "Specta 适合做 AI 品牌情报监测。",
                            "has_brand_mention": True,
                            "citations": [
                                {
                                    "url": "https://example.com/report",
                                    "title": "行业报告",
                                    "confidence": 0.8,
                                }
                            ],
                        },
                    }
                ],
            }
        ]
    )

    assert len(bundle.questions) == 1
    assert len(bundle.answers) == 1
    assert len(bundle.citations) == 1
    assert bundle.answers[0].platform == "yuanbao"
    assert bundle.answers[0].brand_mentioned is True
    assert bundle.citations[0].domain == "example.com"


def test_normalize_personas_builds_scenario_chain():
    personas = BrandIntelligenceProjectionService.normalize_personas(
        {
            "user_personas": [
                {
                    "persona_id": "p1",
                    "persona_name": "市场负责人",
                    "persona_description": "负责品牌增长和监测。",
                    "usage_scenarios": [
                        {
                            "scenario_key": "s1",
                            "scenario_name": "竞品对比",
                            "scenario_description": "判断品牌是否被 AI 推荐。",
                        }
                    ],
                }
            ]
        }
    )

    assert len(personas) == 1
    assert personas[0].persona_id == "p1"
    assert len(personas[0].scenarios) == 1
    assert personas[0].scenarios[0].scenario_key == "s1"


async def _build_session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'brand-intel.db'}")
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, session_factory


@pytest.mark.asyncio
async def test_persist_fetch_results_writes_question_answer_and_citation(tmp_path):
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

        service = BrandIntelligenceProjectionService(session)
        counts = await service.persist_fetch_results(
            entity_id=entity.id,
            session_id=None,
            fetch_results=[
                {
                    "question_id": "q-1",
                    "question_text": "AI 会如何推荐品牌情报工具？",
                    "platform_results": [
                        {
                            "platform": "kimi",
                            "fetch_method": "browser",
                            "success": True,
                            "answer": "Specta 是一个品牌情报工作台。",
                            "citations": ["https://example.com/a"],
                        }
                    ],
                }
            ],
        )
        await session.commit()

        question_rows = (
            (await session.execute(select(BrandIntelligenceQuestion))).scalars().all()
        )
        answer_rows = (
            (await session.execute(select(BrandPlatformAnswer))).scalars().all()
        )
        citation_rows = (
            (await session.execute(select(BrandCitationSource))).scalars().all()
        )

        assert counts == {"questions": 1, "answers": 1, "citations": 1, "links": 2}
        assert question_rows[0].question_id == "q-1"
        assert answer_rows[0].question_object_id == question_rows[0].id
        assert citation_rows[0].answer_id == answer_rows[0].id
        assert citation_rows[0].domain == "example.com"
    await engine.dispose()


@pytest.mark.asyncio
async def test_persist_fetch_results_writes_brand_mentions_idempotently(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        entity = Entity(
            id=uuid.uuid4(),
            name="理想汽车",
            domain="lixiang.com",
            industry="新能源汽车",
            description="Test brand",
            status=EntityStatus.ACTIVE,
        )
        session.add(entity)
        await session.commit()

        payload = [
            {
                "question_id": "q-mention",
                "question_text": "家庭用车会推荐谁？",
                "platform_results": [
                    {
                        "platform": "yuanbao",
                        "fetch_method": "browser",
                        "success": True,
                        "answer": {
                            "content": "理想汽车适合家庭用户，增程路线清晰。",
                            "has_brand_mention": True,
                            "sentiment": "positive",
                            "mention_quote": "理想汽车适合家庭用户",
                        },
                    }
                ],
            }
        ]
        service = BrandIntelligenceProjectionService(session)
        await service.persist_fetch_results(
            entity_id=entity.id,
            session_id=None,
            fetch_results=payload,
        )
        await service.persist_fetch_results(
            entity_id=entity.id,
            session_id=None,
            fetch_results=payload,
        )
        await session.commit()

        mentions = (await session.execute(select(BrandMention))).scalars().all()
        links = (await session.execute(select(BrandObjectLink))).scalars().all()
        link_types = {link.link_type for link in links}

        assert len(mentions) == 1
        assert mentions[0].mentioned_brand_name == "理想汽车"
        assert mentions[0].sentiment == "positive"
        assert mentions[0].quote == "理想汽车适合家庭用户"
        assert "platform_answer_has_brand_mention" in link_types
        assert "brand_mention_mentions_brand" in link_types
        assert "brand_mention_about_question" in link_types
    await engine.dispose()


@pytest.mark.asyncio
async def test_persist_brand_context_writes_competitors_personas_and_links(tmp_path):
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

        service = BrandIntelligenceProjectionService(session)
        counts = await service.persist_brand_context(
            entity_id=entity.id,
            session_id=None,
            competitors=[
                {
                    "name": "Brandwatch",
                    "website": "https://brandwatch.com",
                    "relevance_score": 8,
                }
            ],
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
        await service.persist_brand_context(
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

        competitor_rows = (
            (await session.execute(select(BrandCompetitorEntity))).scalars().all()
        )
        persona_rows = (
            (await session.execute(select(BrandAudiencePersona))).scalars().all()
        )
        scenario_rows = (
            (await session.execute(select(BrandUsageScenario))).scalars().all()
        )
        links = (await session.execute(select(BrandObjectLink))).scalars().all()
        link_types = {link.link_type for link in links}

        assert counts == {"competitors": 1, "personas": 1, "scenarios": 1}
        assert len(competitor_rows) == 1
        assert len(persona_rows) == 1
        assert len(scenario_rows) == 1
        assert {
            "brand_has_competitor",
            "brand_has_persona",
            "persona_has_scenario",
        }.issubset(link_types)
    await engine.dispose()


@pytest.mark.asyncio
async def test_persist_report_artifact_creates_evidence_set_and_version(tmp_path):
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

        service = BrandIntelligenceProjectionService(session)
        await service.persist_fetch_results(
            entity_id=entity.id,
            session_id=None,
            fetch_results=[
                {
                    "question_id": "q-1",
                    "question_text": "AI 会如何推荐品牌情报工具？",
                    "platform_results": [
                        {
                            "platform": "kimi",
                            "fetch_method": "browser",
                            "success": True,
                            "answer": "Specta 是一个品牌情报工作台。",
                            "citations": ["https://example.com/a"],
                        }
                    ],
                }
            ],
        )
        report_version = await service.persist_report_artifact(
            entity_id=entity.id,
            session_id=None,
            report_kind="panorama",
            title="品牌全景分析报告",
            artifact_id="artifact-1",
            payload={
                "report_id": "report-1",
                "executive_summary": "Specta 在 AI 品牌情报中具备清晰定位。",
                "key_findings": [
                    {
                        "fact": "Specta 已经被 AI 回答识别为品牌情报工作台。",
                        "detail": "Kimi 回答中出现了 Specta，并且引用来源可以继续追溯。",
                        "type": "recommendation_advantage",
                        "confidence": 0.8,
                    }
                ],
                "metrics": {
                    "bwvs_index": 72.5,
                    "mention_rate": 0.6,
                    "total_questions": 10,
                },
            },
        )
        second_version = await service.persist_report_artifact(
            entity_id=entity.id,
            session_id=None,
            report_kind="panorama",
            title="品牌全景分析报告",
            artifact_id="artifact-1",
            payload={"report_id": "report-1", "summary": "第二版。"},
        )
        await session.commit()

        evidence_sets = (
            (await session.execute(select(BrandEvidenceSet))).scalars().all()
        )
        report_versions = (
            (await session.execute(select(BrandReportVersion))).scalars().all()
        )
        metric_snapshots = (
            (await session.execute(select(BrandMetricSnapshot))).scalars().all()
        )
        findings = (
            (await session.execute(select(BrandIntelligenceFinding))).scalars().all()
        )
        links = (await session.execute(select(BrandObjectLink))).scalars().all()
        link_types = [link.link_type for link in links]

        assert report_version.version == 1
        assert second_version.version == 2
        assert len(evidence_sets) == 2
        assert evidence_sets[0].question_count == 1
        assert evidence_sets[0].answer_count == 1
        assert evidence_sets[0].citation_count == 1
        assert len(report_versions) == 2
        assert len(metric_snapshots) == 1
        assert len(findings) == 2
        assert findings[0].title.startswith("Specta")
        assert findings[0].finding_type == "recommendation_advantage"
        assert findings[0].supporting_answer_count == 1
        assert findings[1].finding_type == "summary"
        assert metric_snapshots[0].bwvs_index == 72.5
        assert report_versions[0].summary.startswith("Specta")
        assert link_types.count("evidence_set_contains_answer") == 2
        assert link_types.count("report_uses_evidence_set") == 2
        assert link_types.count("brand_has_intelligence_finding") == 2
        assert link_types.count("report_contains_intelligence_finding") == 2
        assert link_types.count("intelligence_finding_uses_evidence_set") == 2
        assert link_types.count("metric_snapshot_measures_brand") == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_persist_fetch_results_writes_idempotent_object_links(tmp_path):
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

        payload = [
            {
                "question_id": "q-1",
                "question_text": "AI 会如何推荐品牌情报工具？",
                "platform_results": [
                    {
                        "platform": "kimi",
                        "fetch_method": "browser",
                        "success": True,
                        "answer": {
                            "content": "Specta 是一个品牌情报工作台。",
                            "citations": [{"url": "https://example.com/a"}],
                        },
                    }
                ],
            }
        ]
        service = BrandIntelligenceProjectionService(session)
        await service.persist_fetch_results(
            entity_id=entity.id,
            session_id=None,
            fetch_results=payload,
        )
        await service.persist_fetch_results(
            entity_id=entity.id,
            session_id=None,
            fetch_results=payload,
        )
        await session.commit()

        links = (await session.execute(select(BrandObjectLink))).scalars().all()
        link_types = {link.link_type for link in links}

        assert len(links) == 2
        assert link_types == {
            "question_answered_by",
            "platform_answer_cites_source",
        }
    await engine.dispose()


@pytest.mark.asyncio
async def test_persist_fetch_results_scopes_answer_dedupe_across_entities(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        first_entity = Entity(
            id=uuid.uuid4(),
            name="First",
            domain="first.example.com",
            industry="AI brand intelligence",
            description="Test brand",
            status=EntityStatus.ACTIVE,
        )
        second_entity = Entity(
            id=uuid.uuid4(),
            name="Second",
            domain="second.example.com",
            industry="AI brand intelligence",
            description="Test brand",
            status=EntityStatus.ACTIVE,
        )
        session.add_all([first_entity, second_entity])
        await session.commit()

        payload = [
            {
                "question_id": "q-1",
                "question_text": "AI 会如何回答同一个问题？",
                "platform_results": [
                    {
                        "platform": "kimi",
                        "fetch_method": "api",
                        "success": True,
                        "status": "success",
                        "answer": {
                            "content": "同一条回答文本。",
                            "citations": [{"url": "https://example.com/a"}],
                        },
                    }
                ],
            }
        ]
        service = BrandIntelligenceProjectionService(session)
        await service.persist_fetch_results(
            entity_id=first_entity.id,
            session_id=None,
            fetch_results=payload,
        )
        await service.persist_fetch_results(
            entity_id=second_entity.id,
            session_id=None,
            fetch_results=payload,
        )
        await session.commit()

        answers = (await session.execute(select(BrandPlatformAnswer))).scalars().all()
        links = (await session.execute(select(BrandObjectLink))).scalars().all()

        assert {answer.entity_id for answer in answers} == {
            first_entity.id,
            second_entity.id,
        }
        assert len(answers) == 2
        assert len(links) == 4
    await engine.dispose()
