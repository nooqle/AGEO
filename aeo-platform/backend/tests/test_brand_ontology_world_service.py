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
    f"sqlite+aiosqlite:///{Path(__file__).resolve().parent / 'test_ontology_world.db'}",
)

from app.core.database import Base
from app.models.brand_intelligence import BrandIntelligenceFinding, BrandReportVersion
from app.models.entity import Entity, EntityStatus
from app.models.message import Message, MessageRole, MessageType
from app.models.session import Session, SessionStatus
from app.models.user import User, UserRole, UserStatus
from app.services.brand_action_service import BrandActionService
from app.services.brand_evidence_denoising_service import (
    BrandEvidenceDenoisingService,
    CitationEvidenceRow,
)
from app.services.brand_intelligence_projection_service import (
    BrandIntelligenceProjectionService,
)
from app.services.brand_ontology_action_planner_service import (
    BrandOntologyActionPlannerService,
)
from app.services.brand_ontology_world_service import (
    BrandOntologyWorldService,
    _object_label,
)
from app.services.brand_knowledge_graph_projection_service import (
    _distribution_target_name,
    _is_distribution_domain,
    _looks_like_internal_id,
    _platform_label,
    _preview,
)
from app.workflow.orchestrator_context_packets import (
    build_ontology_action_plan_packet,
    build_ontology_world_packet,
    render_ontology_action_plan_packet,
    render_ontology_world_packet,
)
from app.workflow.orchestrator_node import build_orchestrator_prompt_assembly
from sqlalchemy import select


def test_dashboard_preview_repairs_legacy_mojibake():
    mojibake = "理想汽车正在被提及".encode("utf-8").decode("latin1")
    assert _preview(mojibake, 80) == "理想汽车正在被提及"


def test_recommendation_distribution_domain_filters_technical_hosts():
    assert _is_distribution_domain("dongchedi.com") is True
    assert _is_distribution_domain("ichgcp.net") is False
    assert _is_distribution_domain("static.example-cdn.com") is False
    assert _distribution_target_name("dongchedi.com") == "懂车帝"
    assert _distribution_target_name("iesdouyin.com") == "抖音"
    assert _platform_label("yuanbao") == "腾讯元宝"


def test_dashboard_projection_hides_internal_question_ids():
    assert _looks_like_internal_id("q001") is True
    assert _looks_like_internal_id("q_001") is True
    assert _looks_like_internal_id("question_001") is True
    assert _looks_like_internal_id("家庭用户会如何选择 Li Auto？") is False


async def _build_session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'world.db'}")
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, session_factory


def _active_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="ontology-world-owner@example.com",
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


def test_evidence_cluster_topic_does_not_expose_internal_question_ids():
    service = BrandEvidenceDenoisingService(db=None)  # type: ignore[arg-type]
    row = CitationEvidenceRow(
        citation_id="citation-1",
        answer_id="answer-1",
        question_id="q_001",
        question_text="",
        category="",
        platform="kimi",
        url="https://www.autohome.com.cn/review/li-auto-noa",
        domain="autohome.com.cn",
        title="理想汽车智能驾驶安全评测",
        snippet="NOA 辅助驾驶和主动安全体验。",
        confidence=0.88,
        created_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
        payload={
            "url_intelligence": {
                "site_name": "汽车之家",
                "category": "汽车垂直媒体",
            }
        },
    )

    clusters = service._evidence_clusters(rows=[row], official_domains=[])

    assert clusters[0]["topic_label"] == "智能驾驶与安全"
    rendered = json.dumps(clusters, ensure_ascii=False)
    assert "q_001" not in clusters[0]["title"]
    assert "q_001" not in clusters[0]["topic_key"]
    assert "question_id" not in clusters[0]["samples"][0]
    assert "问题 q_" not in rendered


def test_world_summary_evidence_cluster_sample_label_hides_internal_ids():
    label = _object_label(
        {
            "object_id": "q-001:other",
            "properties": {
                "title": "问题 q_001 · 其他来源",
                "topic_label": "问题 q_001",
                "source_role_label": "其他来源",
            },
        },
        object_type="evidence_cluster",
    )

    assert label == "综合证据主题 · 其他来源"
    assert "q_001" not in label
    assert "问题 q_" not in label


def test_evidence_cluster_topic_summarizes_long_question_as_business_topic():
    service = BrandEvidenceDenoisingService(db=None)  # type: ignore[arg-type]
    row = CitationEvidenceRow(
        citation_id="citation-2",
        answer_id="answer-2",
        question_id="bl_001",
        question_text=(
            "看现在很多新出的家用SUV都在强调冰箱彩电大沙发，"
            "这种配置真的是未来的主流趋势吗？"
        ),
        category="",
        platform="deepseek",
        url="https://www.dongchedi.com/article/li-auto-family-suv",
        domain="dongchedi.com",
        title="家用 SUV 舒适体验评测",
        snippet="空间、座椅、家庭出行和舒适体验。",
        confidence=0.7,
        created_at=datetime(2026, 5, 21, tzinfo=timezone.utc),
        payload={
            "url_intelligence": {
                "site_name": "懂车帝",
                "category": "汽车垂直媒体",
            }
        },
    )

    clusters = service._evidence_clusters(rows=[row], official_domains=[])

    assert clusters[0]["topic_label"] == "家庭用车体验"
    assert "看现在很多新出的家用SUV" not in clusters[0]["title"]


@pytest.mark.asyncio
async def test_ontology_world_snapshot_summarizes_objects_links_and_actions(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _active_user()
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
        action = await action_service.record_applied_action(
            entity_id=entity.id,
            action_type="record_user_feedback",
            user_id=owner.id,
            actor_type="user",
            input_payload={
                "feedback_type": "runtime_smoke",
                "secret": "do-not-expose",
            },
            output_payload={"internal": "do-not-expose"},
            feedback_text="private feedback",
        )
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
            source_action_record_id=action.id,
        )
        await projection_service.persist_fetch_results(
            entity_id=entity.id,
            session_id=None,
            fetch_results=[
                {
                    "question_id": "q1",
                    "question_text": "AI 会如何推荐 Specta？",
                    "platform_results": [
                        {
                            "platform": "kimi",
                            "fetch_method": "api",
                            "success": True,
                            "status": "success",
                            "answer": {
                                "content": "Specta 是品牌情报工作台。",
                                "citations": [{"url": "https://example.com/a"}],
                            },
                        }
                    ],
                }
            ],
            source_action_record_id=action.id,
        )
        await projection_service.persist_report_artifact(
            entity_id=entity.id,
            session_id=None,
            report_kind="panorama",
            title="品牌全景分析报告",
            artifact_id="artifact-1",
            payload={
                "report_id": "report-1",
                "key_findings": [
                    {
                        "fact": "Specta 在样本回答中已经形成品牌情报认知。",
                        "detail": "Kimi 回答把 Specta 描述为品牌情报工作台。",
                        "type": "recommendation_advantage",
                    }
                ],
            },
            source_action_record_id=action.id,
        )
        finding = (
            await session.execute(
                select(BrandIntelligenceFinding).where(
                    BrandIntelligenceFinding.entity_id == entity.id
                )
            )
        ).scalar_one()
        await action_service.record_intelligence_finding_feedback(
            entity_id=entity.id,
            finding_id=finding.id,
            user_id=owner.id,
            feedback_type="correct",
            feedback_text="",
        )
        await session.commit()

        world_service = BrandOntologyWorldService(session)
        world = await world_service.build_snapshot(entity_id=entity.id)
        assert world is not None
        dashboard_world = await world_service.build_dashboard_summary(
            entity_id=entity.id,
            actor_id=owner.id,
        )
        assert dashboard_world is not None

        summaries = {item["object_type"]: item for item in world["object_summaries"]}
        assert world["brand"]["label"] == "Specta"
        assert world["entity"]["label"] == "Specta"
        assert summaries["competitor_entity"]["total"] == 1
        assert summaries["simulated_question"]["lifecycle_counts"] == {"fetched": 1}
        assert summaries["simulated_question"]["sample_lifecycle_counts"] == {
            "fetched": 1
        }
        assert summaries["intelligence_finding"]["total"] == 1
        assert world["finding_feedback_summary"]["total"] == 1
        assert world["finding_feedback_summary"]["correction_count"] == 1
        assert world["finding_feedback_summary"]["correction_without_text_count"] == 1
        assert world["finding_feedback_summary"]["latest"][0]["finding_id"] == str(
            finding.id
        )
        assert "feedback_text" not in world["finding_feedback_summary"]["latest"][0]
        assert world["relationship_counts"]["brand_has_competitor"] == 1
        assert world["relationship_counts"]["brand_has_intelligence_finding"] == 1
        assert world["relationship_counts"]["question_answered_by"] == 1
        assert world["relationship_counts"]["platform_answer_cites_source"] == 1
        assert world["relationship_counts"]["evidence_set_contains_answer"] == 1
        assert world["governance_report"]["status"] == "healthy"
        assert any(
            action["key"] == "confirm_question_set"
            for action in world["available_actions"]
        )
        assert not any(
            item["link_type"] == "brand_has_competitor"
            for item in dashboard_world["relationship_summary"]
        )
        assert any(
            item["link_type"] == "brand_has_competitor"
            for item in dashboard_world["supporting_relationship_summary"]
        )
        assert any(
            item["link_type"] == "question_answered_by"
            for item in dashboard_world["relationship_summary"]
        )
        competitor_relationship = next(
            item
            for item in dashboard_world["supporting_relationship_summary"]
            if item["link_type"] == "brand_has_competitor"
        )
        question_relationship = next(
            item
            for item in dashboard_world["relationship_summary"]
            if item["link_type"] == "question_answered_by"
        )
        assert competitor_relationship["visibility"] == "supporting"
        assert competitor_relationship["default_visible"] is False
        assert question_relationship["visibility"] == "core"
        assert question_relationship["default_visible"] is True
        assert "action_queue" in dashboard_world
        assert dashboard_world["task_flow"]["title"] in {
            "转入持续监测",
            "持续运营品牌情报",
        }
        assert dashboard_world["task_flow"]["owner_label"] in {
            "需要人反馈",
            "人可调整，系统执行",
            "系统可执行",
            "等待前置信息",
        }
        assert any(
            step["key"] == "findings" and step["status"] == "complete"
            for step in dashboard_world["task_flow"]["steps"]
        )
        assert "do-not-expose" not in dashboard_world["task_flow"]["action_prompt"]
        feedback_queue_items = [
            item
            for item in dashboard_world["action_queue"]
            if item.get("source") == "finding_feedback"
        ]
        assert feedback_queue_items
        assert feedback_queue_items[0]["target_object_id"] == str(finding.id)
        assert feedback_queue_items[0]["missing_inputs"] == ["feedback_text"]
        assert dashboard_world["intelligence_findings"][0]["title"].startswith("Specta")
        assert dashboard_world["world_phase"] in {
            "evidence_ready",
            "report_ready",
            "operating_world",
        }

        rendered = render_ontology_world_packet(
            build_ontology_world_packet({"ontology_world": world})
        )
        assert "当前品牌情报状态" in rendered
        assert "统一行动入口" in rendered
        assert "Brandwatch" in rendered
        assert "Specta 在样本回答中" in rendered
        assert "情报治理状态：healthy" in rendered
        assert "do-not-expose" not in rendered
        assert "private feedback" not in rendered

        action_plan = BrandOntologyActionPlannerService().build_plan(
            ontology_world=world,
            state={"user_id": str(owner.id), "report_kind": "panorama"},
        )
        assert action_plan is not None
        action_plan_rendered = render_ontology_action_plan_packet(
            build_ontology_action_plan_packet({"ontology_action_plan": action_plan})
        )
        assert "当前品牌情报计算的行动建议" in action_plan_rendered
        assert "来源=情报判断反馈" in action_plan_rendered
        assert "缺信息=feedback_text" in action_plan_rendered
        assert "创建监测计划" in action_plan_rendered
        assert "do-not-expose" not in action_plan_rendered

        assembly = build_orchestrator_prompt_assembly(
            {
                "session_id": str(uuid.uuid4()),
                "entity_id": str(entity.id),
                "brand_name": "Specta",
                "official_website": "https://imspecta.com",
                "ontology_world": world,
                "ontology_action_plan": action_plan,
            }
        )
        ontology_sections = [
            section
            for section in assembly.runtime_context_sections
            if section.key == "ontology_world"
        ]
        action_plan_sections = [
            section
            for section in assembly.runtime_context_sections
            if section.key == "ontology_action_plan"
        ]
        assert len(ontology_sections) == 1
        assert len(action_plan_sections) == 1
        assert "品牌情报状态" in ontology_sections[0].title
        assert "当前品牌情报状态" in ontology_sections[0].body
        assert "行动建议" in action_plan_sections[0].title
        assert "当前品牌情报计算的行动建议" in action_plan_sections[0].body
    await engine.dispose()


@pytest.mark.asyncio
async def test_ontology_world_legacy_backfill_projects_message_outputs(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _active_user()
        entity = Entity(
            id=uuid.uuid4(),
            name="Li Auto",
            domain="lixiang.com",
            industry="EV",
            description="Business brand",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        analysis_session = Session(
            id=uuid.uuid4(),
            user_id=owner.id,
            entity_id=entity.id,
            title="Legacy analysis",
            status=SessionStatus.ACTIVE,
        )
        fetch_message = Message(
            session_id=analysis_session.id,
            role=MessageRole.ASSISTANT,
            type=MessageType.OUTPUT,
            output_type="fetchResults",
            content="AI答案抓取结果",
            sequence=1,
            output_data=json.dumps(
                {
                    "fetchResults": [
                        {
                            "question_id": "q1",
                            "question_text": "AI 会如何推荐 Li Auto？",
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
                                            }
                                        ],
                                    },
                                }
                            ],
                        }
                    ]
                },
                ensure_ascii=False,
            ),
        )
        older_report_message = Message(
            session_id=analysis_session.id,
            role=MessageRole.ASSISTANT,
            type=MessageType.OUTPUT,
            output_type="report",
            content="旧版品牌报告",
            sequence=0,
            created_at=datetime.now(timezone.utc) - timedelta(days=1),
            output_data=json.dumps(
                {
                    "report_id": "legacy-report-old",
                    "report_kind": "panorama",
                    "summary": "旧版报告不应在懒投影里抢占最新入口。",
                    "key_findings": [
                        {
                            "fact": "旧版判断。",
                            "detail": "旧版证据。",
                            "type": "observation",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
        )
        report_message = Message(
            session_id=analysis_session.id,
            role=MessageRole.ASSISTANT,
            type=MessageType.OUTPUT,
            output_type="report",
            content="品牌全景分析报告",
            sequence=2,
            created_at=datetime.now(timezone.utc),
            output_data=json.dumps(
                {
                    "report_id": "legacy-report-1",
                    "report_kind": "panorama",
                    "summary": "Li Auto 在样本回答里有清晰的家庭智能电动车心智。",
                    "key_findings": [
                        {
                            "fact": "Li Auto 的家庭用车定位被智能回答稳定提及。",
                            "detail": "样本回答引用官网并提到家庭智能电动车。",
                            "type": "recommendation_advantage",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
        )
        session.add_all(
            [
                owner,
                entity,
                analysis_session,
                older_report_message,
                fetch_message,
                report_message,
            ]
        )
        await session.commit()

        world_service = BrandOntologyWorldService(session)
        backfill_result = await world_service.ensure_legacy_backfill(
            entity_id=entity.id,
        )
        await session.commit()
        world = await world_service.build_dashboard_summary(
            entity_id=entity.id,
            actor_id=owner.id,
        )

        assert backfill_result["changed"] is True
        assert backfill_result["fetch_bundles"] == 1
        assert backfill_result["reports"] == 1
        assert world is not None
        summaries = {item["object_type"]: item for item in world["object_summaries"]}
        assert summaries["simulated_question"]["total"] == 1
        assert summaries["platform_answer"]["total"] == 1
        assert summaries["citation_source"]["total"] == 1
        assert summaries["report_artifact"]["total"] == 1
        assert summaries["intelligence_finding"]["total"] == 1
        assert world["relationship_counts"]["question_answered_by"] == 1
        assert world["relationship_counts"]["platform_answer_cites_source"] == 1
        assert world["relationship_counts"]["report_uses_evidence_set"] == 1
        assert world["task_flow"]["title"] in {
            "转入持续监测",
            "持续运营品牌情报",
        }

        second_backfill = await world_service.ensure_legacy_backfill(
            entity_id=entity.id,
        )
        await session.commit()
        report_rows = (
            (
                await session.execute(
                    select(BrandReportVersion).where(
                        BrandReportVersion.entity_id == entity.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert second_backfill["reports"] == 0
        assert len(report_rows) == 1
        assert report_rows[0].report_id == "legacy-report-1"
    await engine.dispose()


@pytest.mark.asyncio
async def test_dashboard_world_returns_brand_knowledge_graph_projections(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        entity = Entity(
            id=uuid.uuid4(),
            name="理想汽车",
            domain="li.auto",
            industry="新能源汽车",
            description="Test brand",
            status=EntityStatus.ACTIVE,
        )
        session.add(entity)
        await session.commit()

        projection_service = BrandIntelligenceProjectionService(session)
        await projection_service.persist_brand_context(
            entity_id=entity.id,
            session_id=None,
            competitors=[{"name": "小米汽车"}],
        )
        await projection_service.persist_fetch_results(
            entity_id=entity.id,
            session_id=None,
            fetch_results=[
                {
                    "question_id": "q-ai-brand",
                    "question_text": "家庭新能源车推荐谁？",
                    "platform_results": [
                        {
                            "platform": "yuanbao",
                            "fetch_method": "browser",
                            "success": True,
                            "answer": {
                                "content": (
                                    "debug: internal trace should not be public\n"
                                    "理想汽车适合家庭用户。"
                                ),
                                "has_brand_mention": True,
                                "sentiment": "positive",
                                "mention_quote": (
                                    "websearch 工具调用记录\n"
                                    "理想汽车适合家庭用户"
                                ),
                                "citations": [
                                    {"url": "https://dongchedi.com/article/a"}
                                ],
                            },
                        },
                        {
                            "platform": "doubao",
                            "fetch_method": "browser",
                            "success": True,
                            "answer": {
                                "content": "小米汽车也值得关注。",
                                "has_brand_mention": False,
                                "competitor_mentions": [{"name": "小米汽车"}],
                                "citations": [{"url": "https://lixiang.com/news"}],
                            },
                        },
                        {
                            "platform": "kimi",
                            "fetch_method": "browser",
                            "success": True,
                            "answer": {
                                "content": "",
                                "has_brand_mention": False,
                                "citations": [
                                    {"url": "https://example.com/missing-answer"}
                                ],
                            },
                        },
                    ],
                }
            ],
        )
        await session.commit()

        world = await BrandOntologyWorldService(session).build_dashboard_summary(
            entity_id=entity.id,
            force_refresh=True,
        )

        assert world is not None
        assert world["projection_version"] >= 4
        assert world["summary_projection"]["metrics"]["mention_rate"]["numerator"] == 1
        assert (
            world["summary_projection"]["metrics"]["mention_rate"]["denominator"] == 2
        )
        mention_metric = world["summary_projection"]["metrics"]["mention_rate"]
        assert mention_metric["sample_sufficiency"]["status"] == "formed"
        assert mention_metric["sample_sufficiency"]["sample_count"] == 2
        assert mention_metric["sample_sufficiency"]["evidence_count"] == 1
        assert (
            world["summary_projection"]["sample_scope"][
                "excluded_unreadable_answer_count"
            ]
            == 1
        )
        mention_detail = world["evidence_projection"]["mention_rate_detail"]
        assert mention_detail["platform_rows"]
        assert mention_detail["sample_quality"]["sample_count"] == 2
        assert mention_detail["sample_quality"]["excluded_unreadable_count"] == 1
        rendered_projection = json.dumps(
            world["evidence_projection"],
            ensure_ascii=False,
        )
        assert "debug:" not in rendered_projection
        assert "websearch 工具" not in rendered_projection
        assert "理想汽车适合家庭用户" in rendered_projection
        assert mention_detail["answer_samples"][0]["citation_sources"][0]["url"] == (
            "https://dongchedi.com/article/a"
        )
        unmentioned_samples = world["evidence_projection"]["mention_rate_detail"][
            "unmentioned_answer_samples"
        ]
        assert len(unmentioned_samples) == 1
        assert unmentioned_samples[0]["platform"] == "doubao"
        assert "小米汽车也值得关注" in unmentioned_samples[0]["answer_preview"]
        assert mention_detail["unmentioned_count"] == 1
        assert mention_detail["unmentioned_sample_count"] == 1
        assert mention_detail["unmentioned_unreadable_count"] == 0
        assert mention_detail["excluded_unreadable_answer_count"] == 1
        target_ranking = next(
            row
            for row in world["evidence_projection"]["ranking_detail"]["brands"]
            if row["is_current_brand"]
        )
        assert target_ranking["mention_count"] == 1
        ranking_detail = world["evidence_projection"]["ranking_detail"]
        assert ranking_detail["sample_sufficiency"]["is_comparable"] is False
        assert (
            ranking_detail["sample_sufficiency"]["rank_status"]
            == "insufficient_answer_sample"
        )
        official_detail = world["evidence_projection"]["official_citation_detail"]
        assert official_detail["official_domain"] == "li.auto"
        assert "lixiang.com" in official_detail["official_domains"]
        assert official_detail["official_citation_count"] == 1
        external_domains = {
            row["domain"] for row in official_detail["top_external_domains"]
        }
        assert "lixiang.com" not in external_domains
        assert world["graph_projection"]["default_focus"].startswith("brand:")
        assert any(
            node["label"] == "AI 提及率" for node in world["graph_projection"]["nodes"]
        )
        recommendations = world["recommendation_projection"]["recommendations"]
        mention_recommendation = next(
            item for item in recommendations if item["id"] == "mention-rate-content-gap"
        )
        assert mention_recommendation["title"] == "补齐未提及问题的内容包"
        assert mention_recommendation["content_format"] == "场景问答内容包"
        assert mention_recommendation["content_directions"]
        assert mention_recommendation["distribution_targets"]
        assert mention_recommendation["execution_steps"]
        assert mention_recommendation["content_generation_brief"]
        assert "prompt_template" not in mention_recommendation
        assert any(
            item["title"] in {"对齐高频外部来源", "建立周期复查"}
            for item in recommendations
        )
        graph_nodes = world["graph_projection"]["nodes"]
        assert any(node["type"] == "official_domain" for node in graph_nodes)
        assert any(node["type"] == "answer_sample" for node in graph_nodes)
        assert all("business_meaning" in node for node in graph_nodes)
        assert all("evidence_count" in node for node in graph_nodes)
        metric_node = next(node for node in graph_nodes if node["label"] == "AI 提及率")
        assert metric_node["next_actions"]
        assert all("business_meaning" in edge for edge in world["graph_projection"]["edges"])
        assert "衡量" not in json.dumps(world["graph_projection"], ensure_ascii=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_dashboard_world_forms_ranking_only_with_sufficient_competitor_sample(
    tmp_path,
):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        entity = Entity(
            id=uuid.uuid4(),
            name="理想汽车",
            domain="li.auto",
            industry="新能源汽车",
            description="Test brand",
            status=EntityStatus.ACTIVE,
        )
        session.add(entity)
        await session.commit()

        projection_service = BrandIntelligenceProjectionService(session)
        await projection_service.persist_brand_context(
            entity_id=entity.id,
            session_id=None,
            competitors=[{"name": "小米汽车"}, {"name": "问界"}, {"name": "腾势"}],
        )
        fetch_results = []
        for index in range(24):
            answer: dict[str, object]
            if index < 10:
                answer = {
                    "content": f"理想汽车在家庭场景里被提及 {index}",
                    "has_brand_mention": True,
                    "sentiment": "positive",
                    "mention_quote": "理想汽车适合家庭用户",
                }
            elif index < 15:
                answer = {
                    "content": f"小米汽车在智能座舱里被提及 {index}",
                    "has_brand_mention": False,
                    "competitor_mentions": [{"name": "小米汽车"}],
                }
            elif index < 19:
                answer = {
                    "content": f"问界在智驾场景里被提及 {index}",
                    "has_brand_mention": False,
                    "competitor_mentions": [{"name": "问界"}],
                }
            else:
                answer = {
                    "content": f"这个问题没有稳定提及品牌 {index}",
                    "has_brand_mention": False,
                }
            fetch_results.append(
                {
                    "question_id": f"q-ranking-{index}",
                    "question_text": f"家庭新能源车对比问题 {index}",
                    "platform_results": [
                        {
                            "platform": "yuanbao" if index % 2 == 0 else "doubao",
                            "fetch_method": "browser",
                            "success": True,
                            "answer": answer,
                        }
                    ],
                }
            )

        await projection_service.persist_fetch_results(
            entity_id=entity.id,
            session_id=None,
            fetch_results=fetch_results,
        )
        await session.commit()

        world = await BrandOntologyWorldService(session).build_dashboard_summary(
            entity_id=entity.id,
            force_refresh=True,
        )

        ranking_metric = world["summary_projection"]["metrics"]["mention_ranking"]
        ranking_detail = world["evidence_projection"]["ranking_detail"]
        assert ranking_metric["display_rank"] == 1
        assert ranking_metric["sample_sufficiency"]["is_comparable"] is True
        assert ranking_detail["sample_sufficiency"]["rank_status"] == "formed"
        comparison_sample = ranking_detail["sample_sufficiency"]["comparison_sample"]
        assert comparison_sample["answer_count"] == 24
        assert comparison_sample["competitors_with_mentions"] == 2
        assert comparison_sample["competitor_mention_count"] == 9
    await engine.dispose()


@pytest.mark.asyncio
async def test_dashboard_world_marks_ranking_unformed_when_competitors_have_no_mentions(
    tmp_path,
):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        entity = Entity(
            id=uuid.uuid4(),
            name="理想汽车",
            domain="li.auto",
            industry="新能源汽车",
            description="Test brand",
            status=EntityStatus.ACTIVE,
        )
        session.add(entity)
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
                    "question_id": f"q-no-competitor-{index}",
                    "question_text": f"家庭新能源车推荐谁 {index}",
                    "platform_results": [
                        {
                            "platform": "yuanbao" if index % 2 == 0 else "doubao",
                            "fetch_method": "browser",
                            "success": True,
                            "answer": {
                                "content": (
                                    "理想汽车适合家庭用户。"
                                    if index == 0
                                    else f"家庭用户会关注空间和补能 {index}。"
                                ),
                                "has_brand_mention": index == 0,
                                "sentiment": "positive" if index == 0 else None,
                                "mention_quote": (
                                    "理想汽车适合家庭用户" if index == 0 else None
                                ),
                            },
                        }
                    ],
                }
                for index in range(24)
            ],
        )
        await session.commit()

        world = await BrandOntologyWorldService(session).build_dashboard_summary(
            entity_id=entity.id,
            force_refresh=True,
        )

        ranking_metric = world["summary_projection"]["metrics"]["mention_ranking"]
        ranking_detail = world["evidence_projection"]["ranking_detail"]
        assert ranking_metric["rank"] == 1
        assert ranking_metric["display_rank"] is None
        assert ranking_metric["sample_sufficiency"]["is_comparable"] is False
        assert (
            ranking_detail["sample_sufficiency"]["rank_status"]
            == "insufficient_competitor_sample"
        )
        assert world["summary_projection"]["top_risk"]["title"] == "补竞品同场样本"
        assert any(
            item["id"] == "competitor-sample-gap"
            for item in world["recommendation_projection"]["recommendations"]
        )
    await engine.dispose()


@pytest.mark.asyncio
async def test_dashboard_world_groups_evidence_and_observes_official_website(
    tmp_path,
):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _active_user()
        entity = Entity(
            id=uuid.uuid4(),
            name="Li Auto",
            domain="https://www.lixiang.com",
            industry="EV",
            description="Business brand",
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
                },
                {
                    "question_id": "q2",
                    "question_text": "Li Auto 的品牌优势是什么？",
                    "category": "家庭购车",
                    "platform_results": [
                        {
                            "platform": "doubao",
                            "fetch_method": "api",
                            "success": True,
                            "status": "success",
                            "answer": {
                                "content": "优势集中在家庭场景、空间和智能化。",
                                "has_brand_mention": True,
                                "citations": [
                                    {
                                        "url": "https://www.lixiang.com/news",
                                        "title": "Li Auto 新闻中心",
                                        "snippet": "品牌产品和家庭场景内容。",
                                        "confidence": 0.86,
                                        "url_intelligence": {
                                            "site_name": "Li Auto 官网",
                                            "category": "企业官网",
                                        },
                                    },
                                    {
                                        "url": "https://www.autohome.com.cn/news/b",
                                        "title": "汽车之家导购",
                                        "snippet": "家庭用车导购内容。",
                                        "url_intelligence": {
                                            "site_name": "汽车之家",
                                            "category": "汽车垂直媒体",
                                        },
                                    },
                                    {
                                        "url": "https://www.zhihu.com/question/1",
                                        "title": "知乎讨论",
                                        "snippet": "用户讨论家庭用车体验。",
                                        "url_intelligence": {
                                            "site_name": "知乎",
                                            "category": "社区讨论",
                                        },
                                    },
                                ],
                            },
                        }
                    ],
                },
            ],
        )
        await session.commit()

        world = await BrandOntologyWorldService(session).build_dashboard_summary(
            entity_id=entity.id,
            actor_id=owner.id,
        )

        assert world is not None
        official = world["official_website_observation"]
        assert official["domain"] == "lixiang.com"
        assert official["citation_count"] == 2
        assert official["question_count"] == 2
        assert official["platform_count"] == 2
        assert official["status"] in {"visible", "strong"}
        assert official["value_label"]
        assert official["sampling_policy"]["object_type"] == "official_website_asset"
        assert "lixiang.com" in official["sampling_policy"]["summary"]
        assert official["comparison_domains"][0]["domain"] == "autohome.com.cn"
        assert official["content_audit"]["status"] == "content_ready"
        assert official["content_audit"]["value_score"] >= 70
        assert official["content_audit"]["brand_name_in_body"] is True
        assert len(official["samples"]) <= 4
        assert all(sample["is_official"] for sample in official["samples"])

        domains = world["source_domain_summary"]
        assert domains[0]["domain"] == "lixiang.com"
        assert domains[0]["is_official"] is True
        assert any(item["domain"] == "autohome.com.cn" for item in domains)

        clusters = world["evidence_clusters"]
        assert any(item["source_role"] == "official_website" for item in clusters)
        assert any(item["source_role"] == "industry_vertical" for item in clusters)
        assert all(len(item["samples"]) <= 3 for item in clusters)
        official_cluster = next(
            item for item in clusters if item["source_role"] == "official_website"
        )
        assert official_cluster["topic_label"] == "家庭购车"
        assert official_cluster["official_citation_count"] == 2
        assert "raw_payload" not in json.dumps(clusters, ensure_ascii=False)

        summaries = {item["object_type"]: item for item in world["object_summaries"]}
        assert summaries["official_website_asset"]["total"] == 1
        assert summaries["official_website_asset"]["lifecycle_counts"]
        assert summaries["source_domain"]["total"] >= 3
        assert summaries["evidence_cluster"]["total"] >= 2
    await engine.dispose()


@pytest.mark.asyncio
async def test_ontology_world_marks_action_feedback_consumed_by_child_action(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _active_user()
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
        confirmation = await action_service.record_applied_action(
            entity_id=entity.id,
            action_type="record_user_feedback",
            user_id=owner.id,
            actor_type="user",
            origin_surface="dashboard_action_queue",
            origin_event_id="confirm-create-monitoring-plan",
            input_payload={
                "actor_id": str(owner.id),
                "feedback_type": "action_queue_confirm",
                "target_action_key": "create_monitoring_plan",
            },
            output_payload={
                "target_action_key": "create_monitoring_plan",
                "feedback_type": "confirm",
            },
            decision_type="ontology_action_queue_feedback",
            decision_key="create_monitoring_plan:confirm",
            target_object_type="brand_entity",
            target_object_id=str(entity.id),
            feedback_text="确认创建监测计划",
        )
        child_action = await action_service.start_action(
            entity_id=entity.id,
            session_id=None,
            user_id=owner.id,
            parent_action_record_id=confirmation.id,
            actor_type="agent",
            origin_surface="workflow_node",
            origin_event_id="consume-create-monitoring-plan",
            action_type="create_monitoring_plan",
            input_payload={
                "question_ids": ["q1"],
                "cadence": "weekly",
            },
        )
        await action_service.complete_action(
            child_action,
            output_payload={"monitoring_plan_id": "plan-1"},
        )
        await session.commit()

        world_service = BrandOntologyWorldService(session)
        world = await world_service.build_snapshot(entity_id=entity.id)

        assert world is not None
        latest = world["action_feedback_summary"]["latest_by_action"][
            "create_monitoring_plan"
        ]
        assert latest["feedback_type"] == "confirm"
        assert latest["action_record_id"] == str(confirmation.id)
        assert latest["consumed_by_action_record_id"] == str(child_action.id)
        assert latest["consumed_by_action_type"] == "create_monitoring_plan"
    await engine.dispose()


@pytest.mark.asyncio
async def test_ontology_world_degrades_when_one_object_collection_fails(
    tmp_path,
    monkeypatch,
):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _active_user()
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

        world_service = BrandOntologyWorldService(session)
        original_list_objects = world_service.objects.list_objects

        async def flaky_list_objects(**kwargs):
            if kwargs.get("object_type") == "competitor_entity":
                raise RuntimeError("read failed")
            return await original_list_objects(**kwargs)

        monkeypatch.setattr(
            world_service.objects,
            "list_objects",
            flaky_list_objects,
        )

        world = await world_service.build_snapshot(entity_id=entity.id)

        assert world is not None
        assert world["governance_report"]["status"] == "degraded"
        assert "competitor_entity: read_failed" in world["warnings"]
        assert world["finding_feedback_summary"]["total"] == 0
        assert any(
            item["object_type"] == "brand_entity" for item in world["object_summaries"]
        )
    await engine.dispose()


@pytest.mark.asyncio
async def test_dashboard_world_uses_light_cache_and_can_force_refresh(
    tmp_path,
    monkeypatch,
):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _active_user()
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

        BrandOntologyWorldService.invalidate_cache(entity.id)
        world_service = BrandOntologyWorldService(session)
        call_count = 0
        original_build_snapshot = world_service.build_snapshot

        async def counted_build_snapshot(**kwargs):
            nonlocal call_count
            call_count += 1
            return await original_build_snapshot(**kwargs)

        monkeypatch.setattr(
            world_service,
            "build_snapshot",
            counted_build_snapshot,
        )

        first = await world_service.build_dashboard_summary(
            entity_id=entity.id,
            actor_id=owner.id,
        )
        second = await world_service.build_dashboard_summary(
            entity_id=entity.id,
            actor_id=owner.id,
        )
        refreshed = await world_service.build_dashboard_summary(
            entity_id=entity.id,
            actor_id=owner.id,
            force_refresh=True,
        )

        assert first is not None
        assert second is not None
        assert refreshed is not None
        assert first["brand"]["label"] == "Specta"
        assert second["brand"]["label"] == "Specta"
        assert refreshed["brand"]["label"] == "Specta"
        assert call_count == 2
    await engine.dispose()
