from __future__ import annotations

import os
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{Path(__file__).resolve().parent / 'test_brand_space.db'}",
)

from app.core.database import Base
from app.models import *  # noqa: F401, F403
from app.models.brand_intelligence import (
    BrandIntelligenceQuestion,
    BrandPlatformAnswer,
    BrandReportVersion,
)
from app.models.brand_intelligence_run import BrandIntelligenceRun
from app.models.brand_space import BoardRun, GraphPatch, GraphUpdate
from app.models.entity import Entity, EntityStatus
from app.models.task import AnalysisTask, TaskStatus
from app.models.user import User, UserRole, UserStatus
from app.services.brand_space_service import BrandSpaceService, GraphPatchBuilderService


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


async def _build_session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'brand-space.db'}")
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


def _entity(owner: User, name: str = "安利") -> Entity:
    return Entity(
        id=uuid.uuid4(),
        name=name,
        domain="amway.com.cn",
        industry="营养健康",
        status=EntityStatus.ACTIVE,
        owner_user_id=owner.id,
    )


def _answer_stub(platform: str) -> BrandPlatformAnswer:
    return BrandPlatformAnswer(
        entity_id=uuid.uuid4(),
        dedupe_key=f"stub:{uuid.uuid4()}:{platform}",
        platform=platform,
        fetch_method="test",
        status="captured",
        success=True,
        answer_text="",
    )


async def _seed_recorded_answers(
    session: AsyncSession,
    *,
    entity: Entity,
    fixture: dict,
) -> None:
    for index, row in enumerate(fixture["recorded_answers"], start=1):
        question = BrandIntelligenceQuestion(
            entity_id=entity.id,
            question_id=f"fixture-q-{index}",
            question_text=row["question"],
            category=row.get("polarity", ""),
        )
        session.add(question)
        await session.flush()
        session.add(
            BrandPlatformAnswer(
                entity_id=entity.id,
                question_object_id=question.id,
                question_id=question.question_id,
                dedupe_key=f"{entity.id}:fixture:{index}:{row['platform']}",
                platform=row["platform"],
                fetch_method="fixture",
                status="captured",
                success=True,
                answer_text=row["answer_excerpt"],
            )
        )


@pytest.mark.asyncio
async def test_amway_recorded_backtest_fixture_reaches_graph_update_and_report(tmp_path):
    fixture = json.loads((FIXTURE_DIR / "brand_space_amway_backtest.json").read_text(encoding="utf-8"))
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("brand-space-backtest@example.com")
        entity = _entity(owner, fixture["brand"]["name"])
        session.add_all([owner, entity])
        await session.commit()

        service = BrandSpaceService(session)
        payload = await service.create_board_run(
            entity_id=entity.id,
            current_user=owner,
            input_scope={
                "fixture": "brand_space_amway_backtest",
                "lexicon_size": len(fixture["lexicon"]),
                "recorded_answer_count": len(fixture["recorded_answers"]),
                "platforms": ["chatgpt", "deepseek", "kimi", "doubao"],
            },
        )
        assert payload["run"]["input_scope"]["fixture"] == "brand_space_amway_backtest"
        assert payload["graph_update"]["summary"]["needs_review"] == 2
        assert any(entity["label"] == "汤臣倍健" for entity in payload["graph"]["entities"])

        report = await service.generate_report(
            graph_update_id=payload["graph_update"]["id"],
            current_user=owner,
        )
        assert report["report"]["payload"]["graph_update_id"] == payload["graph_update"]["id"]
        assert any(item["severity"] == "block" for item in report["guardrails"])

    await engine.dispose()


@pytest.mark.asyncio
async def test_amway_real_fixture_builds_lexicon_backed_graph_update_and_review_items(tmp_path):
    fixture = json.loads((FIXTURE_DIR / "brand_space_amway_backtest.json").read_text(encoding="utf-8"))
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("brand-space-real-fixture@example.com")
        entity = _entity(owner, fixture["brand"]["name"])
        session.add_all([owner, entity])
        await session.commit()

        service = BrandSpaceService(session)
        payload = await service.create_board_run(
            entity_id=entity.id,
            current_user=owner,
            execution_mode="real",
            input_scope={
                "fixture": "brand_space_amway_backtest",
                "entity_lexicon": fixture["lexicon"],
                "platforms": ["chatgpt", "deepseek", "kimi", "doubao"],
            },
        )
        board_run = await session.get(BoardRun, uuid.UUID(payload["run"]["id"]))
        intelligence_run = await session.get(
            BrandIntelligenceRun,
            uuid.UUID(payload["run"]["brand_intelligence_run_id"]),
        )
        assert board_run is not None
        assert intelligence_run is not None
        await _seed_recorded_answers(session, entity=entity, fixture=fixture)
        intelligence_run.status = "completed"
        intelligence_run.stage = "generating_recommendations"
        intelligence_run.progress = 1.0
        intelligence_run.message = "真实 fixture 回测完成"
        board_run.last_synced_at = None
        await session.commit()

        await service._sync_real_board_run(
            board_run=board_run,
            current_user=owner,
            force=True,
        )
        synced = await service.get_board_run(
            run_id=payload["run"]["id"],
            current_user=owner,
        )

        assert synced["graph_update"] is not None
        assert synced["graph_update"]["summary"]["total"] == 5
        patch_by_object = {
            patch["affectedObjectId"]: patch for patch in synced["patches"]
        }
        assert patch_by_object["nutrilite"]["relationType"] == "supports"
        assert patch_by_object["nutrition-supplement"]["relationType"] == "supports"
        assert patch_by_object["active-health"]["relationType"] == "associated_with"
        assert patch_by_object["regulatory"]["relationType"] == "risk_related"
        assert patch_by_object["regulatory"]["status"] == "needs_review"
        assert patch_by_object["by-health"]["relationType"] == "competes_with"
        assert patch_by_object["by-health"]["status"] == "needs_review"
        assert patch_by_object["by-health"]["evidenceRefs"][0]["matched_entity_label"] == "汤臣倍健"
        assert patch_by_object["nutrilite"]["evidenceRefs"][0]["matched_entity_type"] == "SubBrand"

        review_items = await service.get_review_items(
            entity_id=entity.id,
            current_user=owner,
        )
        assert review_items["summary"]["total"] == 2
        assert {item["category"] for item in review_items["review_items"]} == {
            "competitor",
            "risk",
        }
        graph_entity_ids = {
            item["id"] for item in synced["graph"]["entities"]
        }
        assert {"nutrilite", "nutrition-supplement", "active-health", "regulatory", "by-health"} <= graph_entity_ids
        artifact_by_key = {artifact["id"]: artifact for artifact in synced["artifacts"]}
        assert artifact_by_key["artifact-patch-set"]["rowCount"] == 5
        assert artifact_by_key["artifact-review-list"]["rowCount"] == 2

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_board_run_builds_graph_update_assets_and_report_guardrails(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("brand-space-owner@example.com")
        entity = _entity(owner)
        session.add_all([owner, entity])
        await session.commit()

        service = BrandSpaceService(session)
        payload = await service.create_board_run(
            entity_id=entity.id,
            current_user=owner,
            input_scope={"platforms": ["chatgpt", "deepseek", "kimi", "doubao"]},
        )

        assert payload["run"]["status"] == "running"
        assert payload["run"]["is_scaffold"] is True
        assert payload["run"]["brand_intelligence_run_id"]
        assert len(payload["nodes"]) == 8
        assert [platform["platformKey"] for platform in payload["platforms"]] == [
            "chatgpt",
            "deepseek",
            "kimi",
            "doubao",
        ]
        assert len(payload["artifacts"]) == 8
        assets_page = await service.get_assets(
            run_id=payload["run"]["id"],
            current_user=owner,
            artifact_type="graph_patch_set",
            limit=1,
        )
        assert assets_page["pagination"]["total"] == 1
        assert assets_page["summary"]["by_type"]["graph_patch_set"] == 1
        assert assets_page["artifacts"][0]["artifactId"]
        first_assets_page = await service.get_assets(
            run_id=payload["run"]["id"],
            current_user=owner,
            limit=3,
            offset=0,
        )
        second_assets_page = await service.get_assets(
            run_id=payload["run"]["id"],
            current_user=owner,
            limit=3,
            offset=3,
        )
        assert first_assets_page["pagination"]["has_more"] is True
        assert second_assets_page["pagination"]["offset"] == 3
        assert {
            artifact["artifactId"] for artifact in first_assets_page["artifacts"]
        }.isdisjoint({artifact["artifactId"] for artifact in second_assets_page["artifacts"]})
        patch_asset_detail = await service.get_artifact_detail(
            artifact_id=assets_page["artifacts"][0]["artifactId"],
            current_user=owner,
        )
        assert patch_asset_detail["preview"]["kind"] == "table"
        assert patch_asset_detail["preview"]["rowCount"] == 4
        assert any(
            link["kind"] == "graph_update"
            for link in patch_asset_detail["trace"]["links"]
        )
        events_page = await service.get_events(
            run_id=payload["run"]["id"],
            current_user=owner,
            limit=2,
        )
        assert events_page["pagination"]["total"] >= 2
        assert len(events_page["events"]) == 2
        assert payload["graph_update"]["status"] == "needs_review"
        assert payload["graph_update"]["summary"]["blocked"] == 1
        assert len(payload["patches"]) == 4

        events = await service.get_events(run_id=payload["run"]["id"], current_user=owner)
        assert any(event["type"] == "scaffold_data_loaded" for event in events["events"])

        risk_patch = next(
            patch for patch in payload["patches"] if patch["patchType"] == "add_risk_relation"
        )
        assert risk_patch["status"] == "needs_review"
        assert risk_patch["sentimentOrRiskScore"] == 4.2

        report_payload = await service.generate_report(
            graph_update_id=payload["graph_update"]["id"],
            current_user=owner,
        )
        assert report_payload["report"]["payload"]["publication_status"] == "needs_review"
        assert report_payload["report"]["payload"]["claims"]
        assert report_payload["report"]["payload"]["trace_chains"]
        assert report_payload["report"]["payload"]["platform_differences"]
        first_trace = report_payload["report"]["payload"]["trace_chains"][0]
        assert [step["type"] for step in first_trace["steps"]] == [
            "report_claim",
            "graph_patch",
            "entity_relation",
            "answer",
            "question",
            "platform",
        ]
        guardrail_by_key = {item["guardrailKey"]: item for item in report_payload["guardrails"]}
        assert guardrail_by_key["competitor_claim_evidence"]["severity"] == "block"
        assert guardrail_by_key["action_platform_specificity"]["severity"] == "pass"
        assert guardrail_by_key["graph_update_scope"]["severity"] == "pass"
        report_assets = await service.get_assets(
            run_id=payload["run"]["id"],
            current_user=owner,
            artifact_type="report",
        )
        assert report_assets["pagination"]["total"] == 1
        report_asset = report_assets["artifacts"][0]
        assert report_asset["metadata"]["report_version_id"] == report_payload["report"]["id"]
        report_asset_detail = await service.get_artifact_detail(
            artifact_id=report_asset["artifactId"],
            current_user=owner,
        )
        assert report_asset_detail["preview"]["kind"] == "summary"
        assert report_asset_detail["trace"]["report"]["id"] == report_payload["report"]["id"]
        assert any(
            link["kind"] == "report_version"
            and link["id"] == report_payload["report"]["id"]
            for link in report_asset_detail["trace"]["links"]
        )

        risk_result = await session.execute(
            select(GraphPatch).where(
                GraphPatch.graph_update_id == uuid.UUID(payload["graph_update"]["id"]),
                GraphPatch.patch_type == "add_risk_relation",
            )
        )
        risk_patch_model = risk_result.scalar_one()
        risk_patch_model.status = "deferred"
        await session.flush()
        competitor_patch = next(
            patch for patch in payload["patches"] if patch["patchType"] == "add_competitor_relation"
        )
        partial_payload = await service.decide_graph_patch(
            patch_id=competitor_patch["id"],
            current_user=owner,
            status="accepted",
            reason="覆盖未来状态兜底",
        )
        assert partial_payload["graph_update"]["status"] == "partial"
        published_after_review = await service.publish_report(
            report_version_id=report_payload["report"]["id"],
            current_user=owner,
        )
        assert published_after_review["report"]["payload"]["publication_status"] == "published"
        assert published_after_review["report"]["payload"]["blocking_guardrail_keys"] == []
        assert {
            item["guardrailKey"]: item["severity"]
            for item in published_after_review["guardrails"]
        }["competitor_claim_evidence"] == "pass"

    await engine.dispose()


@pytest.mark.asyncio
async def test_mcdonalds_report_versions_publish_and_legacy_mapping(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("brand-space-mcdonalds@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="麦当劳",
            domain="mcdonalds.com.cn",
            industry="餐饮",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        session.add_all([owner, entity])
        await session.commit()

        service = BrandSpaceService(session)
        board_run = BoardRun(
            entity_id=entity.id,
            created_by_user_id=owner.id,
            status="completed",
            is_scaffold=False,
            progress=1.0,
            summary="麦当劳餐饮品牌图谱更新完成",
            active_node_ids=[],
        )
        session.add(board_run)
        await session.flush()
        graph_update = GraphUpdate(
            entity_id=entity.id,
            board_run_id=board_run.id,
            created_by_user_id=owner.id,
            before_graph_version="v1.0.0",
            after_graph_version="v1.1.0",
            status="needs_review",
            summary={"total": 3, "needs_review": 1, "accepted": 1, "auto_applied": 1},
        )
        session.add(graph_update)
        await session.flush()
        session.add_all(
            [
                GraphPatch(
                    graph_update_id=graph_update.id,
                    entity_id=entity.id,
                    patch_type="update_strength",
                    status="auto_applied",
                    title="麦辣鸡腿堡核心产品连接增强",
                    description="多平台回答把麦辣鸡腿堡作为麦当劳核心产品提及。",
                    affected_object_type="menu_item",
                    affected_object_id="spicy-chicken-burger",
                    relation_type="supports",
                    connection_strength=86,
                    confidence=0.88,
                    sentiment_or_risk_score=8.1,
                    after_payload={"zone": "inner", "label": "麦辣鸡腿堡"},
                    evidence_refs=[
                        {
                            "id": "answer:mcd-chatgpt-menu",
                            "answer_id": "mcd-chatgpt-menu",
                            "question_id": "mcd-q-menu",
                            "question": "麦当劳最有代表性的产品是什么？",
                            "platform": "ChatGPT",
                            "excerpt": "麦辣鸡腿堡和巨无霸常被视为麦当劳核心产品。",
                        },
                        {
                            "id": "answer:mcd-kimi-menu",
                            "answer_id": "mcd-kimi-menu",
                            "question_id": "mcd-q-menu",
                            "question": "麦当劳最有代表性的产品是什么？",
                            "platform": "Kimi",
                            "excerpt": "麦辣鸡腿堡在本土菜单中有强识别度。",
                        },
                    ],
                ),
                GraphPatch(
                    graph_update_id=graph_update.id,
                    entity_id=entity.id,
                    patch_type="add_risk_relation",
                    status="needs_review",
                    title="食品安全质疑进入风险层",
                    description="回答中出现食品安全和卫生顾虑，需要审阅。",
                    affected_object_type="risk_signal",
                    affected_object_id="food-safety-concern",
                    relation_type="risk_related",
                    connection_strength=67,
                    confidence=0.72,
                    sentiment_or_risk_score=4.1,
                    after_payload={"zone": "risk", "label": "食品安全质疑"},
                    evidence_refs=[
                        {
                            "id": "answer:mcd-deepseek-risk",
                            "answer_id": "mcd-deepseek-risk",
                            "question_id": "mcd-q-risk",
                            "question": "麦当劳有哪些用户顾虑？",
                            "platform": "DeepSeek",
                            "excerpt": "部分用户会关注食品安全、门店卫生和配料透明度。",
                        }
                    ],
                ),
                GraphPatch(
                    graph_update_id=graph_update.id,
                    entity_id=entity.id,
                    patch_type="add_competitor_relation",
                    status="accepted",
                    title="肯德基竞品关系确认",
                    description="回答包含明确对比语境。",
                    affected_object_type="competitor",
                    affected_object_id="kfc",
                    relation_type="competes_with",
                    connection_strength=74,
                    confidence=0.78,
                    sentiment_or_risk_score=6.2,
                    after_payload={"zone": "middle", "label": "肯德基"},
                    evidence_refs=[
                        {
                            "id": "answer:mcd-doubao-kfc",
                            "answer_id": "mcd-doubao-kfc",
                            "question_id": "mcd-q-competitor",
                            "question": "消费者会把麦当劳和哪些品牌比较？",
                            "platform": "豆包",
                            "excerpt": "消费者常把麦当劳和肯德基进行套餐、价格和门店体验对比。",
                        }
                    ],
                ),
            ]
        )
        legacy_report = BrandReportVersion(
            entity_id=entity.id,
            report_id="legacy-mcdonalds-report",
            version=1,
            report_kind="legacy_brand_report",
            artifact_id="legacy:mcdonalds:1",
            title="麦当劳旧版品牌报告",
            summary="旧报告没有 Graph Update 追溯链。",
            payload={"publication_status": "published"},
        )
        session.add(legacy_report)
        await session.commit()

        report_payload = await service.generate_report(
            graph_update_id=graph_update.id,
            current_user=owner,
        )
        report = report_payload["report"]
        assert report["source_type"] == "graph_update"
        assert report["payload"]["publication_status"] == "draft"
        report_text = json.dumps(report["payload"], ensure_ascii=False)
        assert "麦辣鸡腿堡" in report_text
        assert "食品安全质疑" in report_text
        assert "肯德基" in report_text
        assert "健康管理" not in report_text
        assert "营养补充" not in report_text
        assert any("DeepSeek" in action for action in report["payload"]["recommended_actions"])
        assert report["payload"]["trace_chains"][0]["steps"][-1]["type"] == "platform"

        report_list = await service.list_reports(entity_id=entity.id, current_user=owner)
        assert report_list["summary"]["graph_update"] == 1
        assert report_list["summary"]["pre_graph_update"] == 1
        legacy_filtered = await service.list_reports(
            entity_id=entity.id,
            current_user=owner,
            publication_status="pre_graph_update",
        )
        assert legacy_filtered["summary"]["pre_graph_update"] == 1
        legacy_item = next(item for item in report_list["reports"] if item["id"] == str(legacy_report.id))
        assert legacy_item["source_type"] == "pre_graph_update"

        detail = await service.get_report(
            report_version_id=report["id"],
            current_user=owner,
        )
        assert detail["report"]["id"] == report["id"]
        assert {item["severity"] for item in detail["guardrails"]} <= {"pass", "warn"}

        published = await service.publish_report(
            report_version_id=report["id"],
            current_user=owner,
        )
        assert published["report"]["payload"]["publication_status"] == "published"
        with pytest.raises(ValueError):
            await service.publish_report(
                report_version_id=legacy_report.id,
                current_user=owner,
            )

    await engine.dispose()


@pytest.mark.asyncio
async def test_report_status_filter_scans_beyond_first_page(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("brand-space-report-pagination@example.com")
        entity = _entity(owner)
        session.add_all([owner, entity])
        await session.flush()

        legacy_report = BrandReportVersion(
            entity_id=entity.id,
            report_id="legacy-old-report",
            version=1,
            report_kind="legacy_brand_report",
            artifact_id="legacy:old",
            title="旧报告",
            summary="旧报告没有 GraphUpdate。",
            payload={"publication_status": "published"},
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        session.add(legacy_report)
        base_time = datetime(2026, 6, 20, tzinfo=timezone.utc)
        for index in range(225):
            session.add(
                BrandReportVersion(
                    entity_id=entity.id,
                    report_id=f"graph-report-{index}",
                    version=1,
                    report_kind="graph_update_interpretation",
                    artifact_id=f"graph-report:{index}",
                    title=f"Graph Report {index}",
                    summary="GraphUpdate report",
                    payload={
                        "graph_update_id": str(uuid.uuid4()),
                        "publication_status": "draft",
                    },
                    created_at=base_time + timedelta(minutes=index),
                    updated_at=base_time + timedelta(minutes=index),
                )
            )
        await session.commit()

        service = BrandSpaceService(session)
        legacy_filtered = await service.list_reports(
            entity_id=entity.id,
            current_user=owner,
            publication_status="pre_graph_update",
            limit=1,
        )

        assert legacy_filtered["summary"]["pre_graph_update"] == 1
        assert legacy_filtered["reports"][0]["id"] == str(legacy_report.id)

    await engine.dispose()


@pytest.mark.asyncio
async def test_report_storyline_uses_real_answers_session_scope_and_question_lookup(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("brand-space-report-answers@example.com")
        entity = Entity(
            id=uuid.uuid4(),
            name="麦当劳",
            domain="mcdonalds.com.cn",
            industry="餐饮",
            status=EntityStatus.ACTIVE,
            owner_user_id=owner.id,
        )
        session_a = uuid.uuid4()
        session_b = uuid.uuid4()
        intelligence_run = BrandIntelligenceRun(
            entity_id=entity.id,
            created_by_user_id=owner.id,
            origin_session_id=session_a,
            status="completed",
            stage="generating_recommendations",
            progress=1.0,
            message="完成",
        )
        session.add_all([owner, entity, intelligence_run])
        await session.flush()

        board_run = BoardRun(
            entity_id=entity.id,
            created_by_user_id=owner.id,
            brand_intelligence_run_id=intelligence_run.id,
            status="completed",
            is_scaffold=False,
            progress=1.0,
            summary="麦当劳真实回答报告",
            active_node_ids=[],
            input_scope={
                "entity_lexicon": [
                    {
                        "entity_id": "happy-meal",
                        "label": "开心乐园餐",
                        "type": "MenuItem",
                        "aliases": ["儿童套餐"],
                    }
                ]
            },
        )
        session.add(board_run)
        await session.flush()

        graph_update = GraphUpdate(
            entity_id=entity.id,
            board_run_id=board_run.id,
            created_by_user_id=owner.id,
            before_graph_version="v1.0.0",
            after_graph_version="v1.1.0",
            status="needs_review",
            summary={"total": 1, "needs_review": 0, "auto_applied": 1},
        )
        session.add(graph_update)
        await session.flush()

        open_question = BrandIntelligenceQuestion(
            entity_id=entity.id,
            session_id=session_a,
            question_id="mcd-open-family",
            question_text="有什么适合带小朋友吃饭的快餐？",
            category="scenario",
        )
        risk_question = BrandIntelligenceQuestion(
            entity_id=entity.id,
            session_id=session_a,
            question_id="mcd-risk",
            question_text="麦当劳食品安全有哪些顾虑？",
            category="risk",
        )
        session.add_all([open_question, risk_question])
        await session.flush()

        session.add_all(
            [
                BrandPlatformAnswer(
                    entity_id=entity.id,
                    session_id=session_a,
                    question_object_id=open_question.id,
                    question_id=open_question.question_id,
                    dedupe_key=f"{entity.id}:mcd:open:chatgpt",
                    platform="ChatGPT",
                    fetch_method="test",
                    status="captured",
                    success=True,
                    brand_mentioned=True,
                    answer_text="开心乐园餐适合亲子用餐，门店覆盖也方便。",
                ),
                BrandPlatformAnswer(
                    entity_id=entity.id,
                    session_id=session_a,
                    question_object_id=None,
                    question_id=risk_question.question_id,
                    dedupe_key=f"{entity.id}:mcd:risk:kimi",
                    platform="Kimi",
                    fetch_method="test",
                    status="captured",
                    success=True,
                    brand_mentioned=False,
                    answer_text="部分用户会关注食品安全、后厨卫生和配料透明度。",
                ),
                BrandPlatformAnswer(
                    entity_id=entity.id,
                    session_id=session_b,
                    question_id="other-session",
                    dedupe_key=f"{entity.id}:mcd:other:deepseek",
                    platform="DeepSeek",
                    fetch_method="test",
                    status="captured",
                    success=True,
                    brand_mentioned=True,
                    answer_text="不应进入报告的其他会话回答。",
                ),
            ]
        )
        session.add(
            GraphPatch(
                graph_update_id=graph_update.id,
                entity_id=entity.id,
                patch_type="update_strength",
                status="auto_applied",
                title="开心乐园餐亲子场景增强",
                description="真实回答把开心乐园餐和亲子用餐场景连接起来。",
                affected_object_type="menu_item",
                affected_object_id="happy-meal",
                relation_type="supports",
                connection_strength=82,
                confidence=0.86,
                sentiment_or_risk_score=7.5,
                after_payload={"zone": "inner", "label": "开心乐园餐"},
                evidence_refs=[],
            )
        )
        await session.commit()

        service = BrandSpaceService(session)
        report_payload = await service.generate_report(
            graph_update_id=graph_update.id,
            current_user=owner,
        )
        payload = report_payload["report"]["payload"]
        report_text = json.dumps(payload, ensure_ascii=False)

        assert payload["sample_scope"]["answer_count"] == 2
        assert payload["sample_scope"]["open_brand_mention_count"] == 1
        assert "有什么适合带小朋友吃饭的快餐" in report_text
        assert "麦当劳食品安全有哪些顾虑" in report_text
        assert "不应进入报告" not in report_text

    await engine.dispose()


@pytest.mark.asyncio
async def test_review_items_and_patch_decision_are_idempotent(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("brand-space-review-loop@example.com")
        entity = _entity(owner)
        session.add_all([owner, entity])
        await session.commit()

        service = BrandSpaceService(session)
        payload = await service.create_board_run(entity_id=entity.id, current_user=owner)

        review_items = await service.get_review_items(
            entity_id=entity.id,
            current_user=owner,
        )
        assert review_items["summary"]["total"] == 3
        assert {item["category"] for item in review_items["review_items"]} == {
            "risk",
            "competitor",
            "new_entity",
        }

        competitor_items = await service.get_review_items(
            entity_id=entity.id,
            current_user=owner,
            category="competitor",
        )
        assert len(competitor_items["review_items"]) == 1
        competitor_patch_id = competitor_items["review_items"][0]["id"]

        accepted = await service.decide_graph_patch(
            patch_id=competitor_patch_id,
            current_user=owner,
            status="accepted",
            reason="比较语境明确",
        )
        accepted_patch = next(
            patch for patch in accepted["patches"] if patch["id"] == competitor_patch_id
        )
        assert accepted_patch["status"] == "accepted"
        assert accepted_patch["reviewedAt"]
        assert accepted_patch["reviewReason"] == "比较语境明确"

        duplicate = await service.decide_graph_patch(
            patch_id=competitor_patch_id,
            current_user=owner,
            status="accepted",
            reason="重复提交不改变终态",
        )
        duplicate_patch = next(
            patch for patch in duplicate["patches"] if patch["id"] == competitor_patch_id
        )
        assert duplicate_patch["status"] == "accepted"
        assert duplicate_patch["reviewReason"] == "比较语境明确"

        events = await service.get_events(run_id=payload["run"]["id"], current_user=owner)
        assert [event["type"] for event in events["events"]].count("graph_patch_accepted") == 1

        with pytest.raises(ValueError):
            await service.decide_graph_patch(
                patch_id=competitor_patch_id,
                current_user=owner,
                status="rejected",
                reason="终态不允许反转",
            )

        risk_patch_id = next(item["id"] for item in review_items["review_items"] if item["category"] == "risk")
        applied = await service.decide_graph_patch(
            patch_id=risk_patch_id,
            current_user=owner,
            status="accepted",
            reason="风险证据已确认归档",
        )
        assert applied["graph_update"]["status"] == "applied"
        assert applied["graph_update"]["summary"]["accepted"] == 2
        graph_update = await session.get(GraphUpdate, uuid.UUID(applied["graph_update"]["id"]))
        assert graph_update is not None
        snapshot_entities = graph_update.graph_snapshot["entities"]
        accepted_competitor_entity = next(
            item for item in snapshot_entities if item.get("id") == "by-health"
        )
        assert accepted_competitor_entity["patchId"] == competitor_patch_id
        assert accepted_competitor_entity["patchStatus"] == "accepted"

        remaining_review_items = await service.get_review_items(
            entity_id=entity.id,
            current_user=owner,
        )
        assert all(item["id"] != competitor_patch_id for item in remaining_review_items["review_items"])

        events = await service.get_events(run_id=payload["run"]["id"], current_user=owner)
        event_types = [event["type"] for event in events["events"]]
        assert event_types.count("graph_patch_accepted") == 2
        assert event_types.count("graph_update_applied") == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_review_items_aggregate_runs_and_rejected_patch_is_removed_from_snapshot(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("brand-space-review-multi-run@example.com")
        entity = _entity(owner)
        session.add_all([owner, entity])
        await session.commit()

        service = BrandSpaceService(session)
        first = await service.create_board_run(entity_id=entity.id, current_user=owner)
        await service.create_board_run(entity_id=entity.id, current_user=owner)

        review_items = await service.get_review_items(
            entity_id=entity.id,
            current_user=owner,
        )
        assert review_items["summary"]["total"] == 6
        competitor_items = await service.get_review_items(
            entity_id=entity.id,
            current_user=owner,
            category="competitor",
        )
        assert len(competitor_items["review_items"]) == 2

        first_competitor_patch = next(
            patch for patch in first["patches"] if patch["patchType"] == "add_competitor_relation"
        )
        first_risk_patch = next(
            patch for patch in first["patches"] if patch["patchType"] == "add_risk_relation"
        )
        rejected = await service.decide_graph_patch(
            patch_id=first_competitor_patch["id"],
            current_user=owner,
            status="rejected",
            reason="比较语境不足",
        )
        assert rejected["graph_update"]["status"] == "needs_review"
        applied = await service.decide_graph_patch(
            patch_id=first_risk_patch["id"],
            current_user=owner,
            status="accepted",
            reason="风险层归档",
        )
        assert applied["graph_update"]["status"] == "applied"
        graph_update = await session.get(GraphUpdate, uuid.UUID(first["graph_update"]["id"]))
        assert graph_update is not None
        snapshot_entity_ids = {
            item.get("id") for item in (graph_update.graph_snapshot or {}).get("entities", [])
        }
        assert "by-health" not in snapshot_entity_ids
        assert "workplace-energy" in snapshot_entity_ids

    await engine.dispose()


@pytest.mark.asyncio
async def test_real_board_run_syncs_brand_intelligence_stage_to_canvas(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("brand-space-real-owner@example.com")
        entity = _entity(owner)
        session.add_all([owner, entity])
        await session.commit()

        service = BrandSpaceService(session)
        payload = await service.create_board_run(
            entity_id=entity.id,
            current_user=owner,
            input_scope={"platforms": ["chatgpt", "deepseek", "kimi", "doubao"]},
            execution_mode="real",
        )

        assert payload["run"]["is_scaffold"] is False
        assert payload["graph_update"] is None
        assert payload["graph"]["meta"]["state"] == "runtime_pending"
        assert len(payload["graph"]["entities"]) > 1
        assert any(event["type"] == "runtime_waiting" for event in payload["events"])

        intelligence_run = await session.get(
            BrandIntelligenceRun,
            uuid.UUID(payload["run"]["brand_intelligence_run_id"]),
        )
        assert intelligence_run is not None
        task = AnalysisTask(
            id=uuid.uuid4(),
            user_id=owner.id,
            session_id=None,
            entity_id=entity.id,
            brand_name=entity.name,
            status=TaskStatus.RUNNING,
            current_stage="A4",
            progress=0.62,
            progress_message="正在采集 AI 回答",
        )
        session.add(task)
        session.add_all(
            [
                BrandPlatformAnswer(
                    entity_id=entity.id,
                    question_id=f"q-{index}",
                    dedupe_key=f"{entity.id}:answer:{index}",
                    platform="kimi" if index % 2 else "chatgpt",
                    fetch_method="test",
                    status="captured",
                    success=True,
                    answer_text="测试回答",
                )
                for index in range(5)
            ]
        )
        intelligence_run.analysis_task_id = task.id
        await session.commit()

        synced = await service.get_board_run(
            run_id=payload["run"]["id"],
            current_user=owner,
        )

        assert synced["run"]["status"] == "running"
        assert synced["run"]["progress"] == 0.62
        assert synced["run"]["analysis_task_id"] == str(task.id)
        node_by_id = {node["id"]: node for node in synced["nodes"]}
        assert node_by_id["question-set"]["status"] == "completed"
        assert node_by_id["platform-rack"]["status"] == "running"
        assert sum(platform["answers"] for platform in synced["platforms"]) == 5
        assert any(event["message"] == "正在采集 AI 回答" for event in synced["events"])

    await engine.dispose()


@pytest.mark.asyncio
async def test_real_completed_run_builds_graph_update_from_answers(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("brand-space-real-graph-update@example.com")
        entity = _entity(owner)
        session.add_all([owner, entity])
        await session.commit()

        service = BrandSpaceService(session)
        payload = await service.create_board_run(
            entity_id=entity.id,
            current_user=owner,
            execution_mode="real",
        )
        board_run = await session.get(BoardRun, uuid.UUID(payload["run"]["id"]))
        intelligence_run = await session.get(
            BrandIntelligenceRun,
            uuid.UUID(payload["run"]["brand_intelligence_run_id"]),
        )
        assert board_run is not None
        assert intelligence_run is not None

        health_question = BrandIntelligenceQuestion(
            entity_id=entity.id,
            question_id="q-health",
            question_text="哪些营养品牌适合日常健康管理？",
            category="health",
        )
        risk_question = BrandIntelligenceQuestion(
            entity_id=entity.id,
            question_id="q-risk",
            question_text="直销类营养品牌是否存在用户顾虑？",
            category="risk",
        )
        competitor_question = BrandIntelligenceQuestion(
            entity_id=entity.id,
            question_id="q-competitor",
            question_text="用户购买营养补充品前通常会比较什么？",
            category="competitor",
        )
        session.add_all([health_question, risk_question, competitor_question])
        await session.flush()
        session.add_all(
            [
                BrandPlatformAnswer(
                    entity_id=entity.id,
                    question_object_id=health_question.id,
                    question_id=health_question.question_id,
                    dedupe_key=f"{entity.id}:real:health:kimi",
                    platform="Kimi",
                    fetch_method="test",
                    status="captured",
                    success=True,
                    answer_text="安利和纽崔莱经常在营养补充和健康管理语境中被提及。",
                ),
                BrandPlatformAnswer(
                    entity_id=entity.id,
                    question_object_id=risk_question.id,
                    question_id=risk_question.question_id,
                    dedupe_key=f"{entity.id}:real:risk:deepseek",
                    platform="DeepSeek",
                    fetch_method="test",
                    status="captured",
                    success=True,
                    answer_text="回答提到价格和监管相关疑问，需要更多澄清证据。",
                ),
                BrandPlatformAnswer(
                    entity_id=entity.id,
                    question_object_id=competitor_question.id,
                    question_id=competitor_question.question_id,
                    dedupe_key=f"{entity.id}:real:competitor:chatgpt",
                    platform="ChatGPT",
                    fetch_method="test",
                    status="captured",
                    success=True,
                    answer_text="用户会把安利与汤臣倍健进行对比后再选择。",
                ),
            ]
        )
        intelligence_run.status = "completed"
        intelligence_run.stage = "generating_recommendations"
        intelligence_run.progress = 1.0
        intelligence_run.message = "真实运行已完成"
        board_run.last_synced_at = None
        await session.commit()

        pending = await service.get_board_run(
            run_id=payload["run"]["id"],
            current_user=owner,
        )

        assert pending["run"]["status"] == "completed"
        assert pending["run"]["output_refs"]["graph_update_build_status"] == "pending"
        assert pending["graph_update"] is None
        assert any(event["type"] == "graph_update_build_pending" for event in pending["events"])

        await service._sync_real_board_run(
            board_run=board_run,
            current_user=owner,
            force=True,
        )
        synced = await service.get_board_run(
            run_id=payload["run"]["id"],
            current_user=owner,
        )

        assert synced["run"]["status"] == "completed"
        assert synced["run"]["output_refs"]["graph_update_build_status"] == "ready"
        assert synced["graph_update"] is not None
        assert synced["graph_update"]["summary"]["total"] == 3
        patch_by_type = {patch["patchType"]: patch for patch in synced["patches"]}
        assert patch_by_type["update_strength"]["status"] == "auto_applied"
        assert patch_by_type["add_risk_relation"]["status"] == "needs_review"
        competitor_patch = patch_by_type["add_competitor_relation"]
        assert competitor_patch["status"] == "needs_review"
        assert competitor_patch["affectedObjectId"] == "by-health"
        assert competitor_patch["evidenceRefs"][0]["platform"] == "ChatGPT"
        assert "q-competitor" == competitor_patch["evidenceRefs"][0]["question_id"]
        assert any(event["type"] == "graph_update_created" for event in synced["events"])

        artifact_by_key = {artifact["id"]: artifact for artifact in synced["artifacts"]}
        assert artifact_by_key["artifact-patch-set"]["rowCount"] == 3
        assert artifact_by_key["artifact-review-list"]["rowCount"] == 2
        assert artifact_by_key["artifact-graph-update"]["rowCount"] == 1

        await session.refresh(board_run)
        board_run.last_synced_at = None
        await session.commit()
        await service.get_board_run(run_id=payload["run"]["id"], current_user=owner)
        updates = await session.execute(
            select(GraphUpdate).where(GraphUpdate.board_run_id == board_run.id)
        )
        assert len(list(updates.scalars().all())) == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_confirmed_competitor_patch_becomes_strength_update_on_later_run(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("brand-space-competitor-merge@example.com")
        entity = _entity(owner)
        session.add_all([owner, entity])
        await session.commit()

        service = BrandSpaceService(session)

        async def create_completed_competitor_run(suffix: str) -> dict:
            payload = await service.create_board_run(
                entity_id=entity.id,
                current_user=owner,
                execution_mode="real",
            )
            board_run = await session.get(BoardRun, uuid.UUID(payload["run"]["id"]))
            intelligence_run = await session.get(
                BrandIntelligenceRun,
                uuid.UUID(payload["run"]["brand_intelligence_run_id"]),
            )
            assert board_run is not None
            assert intelligence_run is not None
            question = BrandIntelligenceQuestion(
                entity_id=entity.id,
                question_id=f"q-competitor-{suffix}",
                question_text="用户购买营养补充品前通常会比较什么？",
                category="competitor",
            )
            session.add(question)
            await session.flush()
            session.add(
                BrandPlatformAnswer(
                    entity_id=entity.id,
                    question_object_id=question.id,
                    question_id=question.question_id,
                    dedupe_key=f"{entity.id}:real:competitor:{suffix}",
                    platform="ChatGPT",
                    fetch_method="test",
                    status="captured",
                    success=True,
                    answer_text="相比之下，用户可能更推荐汤臣倍健作为替代选择。",
                )
            )
            intelligence_run.status = "completed"
            intelligence_run.stage = "generating_recommendations"
            intelligence_run.progress = 1.0
            intelligence_run.message = "真实运行已完成"
            board_run.last_synced_at = None
            await session.commit()
            await service._sync_real_board_run(
                board_run=board_run,
                current_user=owner,
                force=True,
            )
            return await service.get_board_run(
                run_id=payload["run"]["id"],
                current_user=owner,
            )

        first = await create_completed_competitor_run("first")
        first_competitor_patch = next(
            patch for patch in first["patches"] if patch["patchType"] == "add_competitor_relation"
        )
        await service.decide_graph_patch(
            patch_id=first_competitor_patch["id"],
            current_user=owner,
            status="accepted",
            reason="确认竞品关系",
        )

        second = await create_completed_competitor_run("second")
        second_competitor_patch = next(
            patch for patch in second["patches"] if patch["affectedObjectId"] == "by-health"
        )
        assert second_competitor_patch["patchType"] == "update_strength"
        assert second_competitor_patch["relationType"] == "competes_with"

    await engine.dispose()


@pytest.mark.asyncio
async def test_real_board_run_sync_is_throttled_for_repeated_reads(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("brand-space-throttle-owner@example.com")
        entity = _entity(owner)
        session.add_all([owner, entity])
        await session.commit()

        service = BrandSpaceService(session)
        payload = await service.create_board_run(
            entity_id=entity.id,
            current_user=owner,
            execution_mode="real",
        )
        first = await service.get_board_run(
            run_id=payload["run"]["id"],
            current_user=owner,
        )
        board_run = await session.get(BoardRun, uuid.UUID(payload["run"]["id"]))
        assert board_run is not None
        first_synced_at = board_run.last_synced_at
        assert first_synced_at is not None

        intelligence_run = await session.get(
            BrandIntelligenceRun,
            uuid.UUID(payload["run"]["brand_intelligence_run_id"]),
        )
        assert intelligence_run is not None
        intelligence_run.message = "不应在 TTL 内同步"
        intelligence_run.progress = 0.99
        await session.commit()

        second = await service.get_board_run(
            run_id=payload["run"]["id"],
            current_user=owner,
        )
        await session.refresh(board_run)

        assert second["run"]["summary"] == first["run"]["summary"]
        assert second["run"]["progress"] == first["run"]["progress"]
        assert board_run.last_synced_at == first_synced_at

    await engine.dispose()


@pytest.mark.asyncio
async def test_real_board_run_marks_missing_intelligence_run_failed(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("brand-space-missing-run-owner@example.com")
        entity = _entity(owner)
        session.add_all([owner, entity])
        await session.commit()

        service = BrandSpaceService(session)
        payload = await service.create_board_run(
            entity_id=entity.id,
            current_user=owner,
            execution_mode="real",
        )
        board_run = await session.get(BoardRun, uuid.UUID(payload["run"]["id"]))
        assert board_run is not None
        board_run.brand_intelligence_run_id = uuid.uuid4()
        board_run.last_synced_at = None
        await session.commit()

        synced = await service.get_board_run(
            run_id=payload["run"]["id"],
            current_user=owner,
        )

        assert synced["run"]["status"] == "failed"
        assert synced["run"]["error_code"] == "intelligence_run_missing"
        assert any(event["type"] == "runtime_missing" for event in synced["events"])

    await engine.dispose()


@pytest.mark.asyncio
async def test_real_board_run_failed_stage_marks_matching_node(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("brand-space-failed-stage-owner@example.com")
        entity = _entity(owner)
        session.add_all([owner, entity])
        await session.commit()

        service = BrandSpaceService(session)
        payload = await service.create_board_run(
            entity_id=entity.id,
            current_user=owner,
            execution_mode="real",
        )
        intelligence_run = await session.get(
            BrandIntelligenceRun,
            uuid.UUID(payload["run"]["brand_intelligence_run_id"]),
        )
        assert intelligence_run is not None
        intelligence_run.status = "failed"
        intelligence_run.stage = "A4"
        intelligence_run.progress = 0.48
        intelligence_run.message = "A4 抓取失败"
        await session.commit()

        synced = await service.get_board_run(
            run_id=payload["run"]["id"],
            current_user=owner,
        )

        node_by_id = {node["id"]: node for node in synced["nodes"]}
        assert node_by_id["platform-rack"]["status"] == "failed"
        assert node_by_id["graph-update"]["status"] == "queued"

    await engine.dispose()


@pytest.mark.asyncio
async def test_brand_space_blocks_cross_user_access(tmp_path):
    engine, session_factory = await _build_session(tmp_path)
    async with session_factory() as session:
        owner = _user("brand-space-owner-2@example.com")
        other = _user("brand-space-other@example.com")
        entity = _entity(owner, "Specta")
        session.add_all([owner, other, entity])
        await session.commit()

        service = BrandSpaceService(session)
        await service.create_board_run(entity_id=entity.id, current_user=owner)

        with pytest.raises(LookupError):
            await service.get_space(entity_id=entity.id, current_user=other)

    await engine.dispose()


def test_circle_allocation_and_competitor_rules_are_guarded():
    threshold_review = BrandSpaceService.allocate_graph_zone(
        connection_strength=90,
        sentiment_or_risk_score=3.0,
        relation_type="associated_with",
        confidence=0.95,
    )
    assert threshold_review["zone"] == "risk"
    assert threshold_review["status"] == "needs_review"

    risk = BrandSpaceService.allocate_graph_zone(
        connection_strength=78,
        sentiment_or_risk_score=4,
        relation_type="associated_with",
        confidence=0.9,
    )
    assert risk["zone"] == "risk"
    assert risk["status"] == "needs_review"

    severe = BrandSpaceService.allocate_graph_zone(
        connection_strength=95,
        sentiment_or_risk_score=2.9,
        relation_type="associated_with",
        confidence=0.95,
    )
    assert severe["zone"] == "risk"
    assert severe["status"] == "blocked"

    positive = BrandSpaceService.allocate_graph_zone(
        connection_strength=82,
        sentiment_or_risk_score=5.0,
        relation_type="associated_with",
        confidence=0.95,
    )
    assert positive["zone"] == "inner"
    assert positive["status"] == "auto_applied"

    exact_competitor_threshold = BrandSpaceService.allocate_graph_zone(
        connection_strength=72,
        sentiment_or_risk_score=6.1,
        relation_type="competes_with",
        confidence=0.7,
    )
    assert exact_competitor_threshold["zone"] == "middle"
    assert exact_competitor_threshold["status"] == "auto_applied"

    co_mention = BrandSpaceService.detect_competitor_context(
        text="安利和汤臣倍健都是营养健康品牌",
        confidence=0.95,
    )
    assert co_mention["is_competitor"] is False

    low_confidence_competitor = BrandSpaceService.detect_competitor_context(
        text="相比之下，用户可能更推荐汤臣倍健作为替代选择",
        confidence=0.62,
    )
    assert low_confidence_competitor["is_competitor"] is True
    assert low_confidence_competitor["status"] == "needs_review"

    exact_confidence_competitor = BrandSpaceService.detect_competitor_context(
        text="相比之下，用户可能更推荐汤臣倍健作为替代选择",
        confidence=0.7,
    )
    assert exact_confidence_competitor["is_competitor"] is True
    assert exact_confidence_competitor["status"] == "auto_applied"


def test_graph_patch_builder_scoring_confidence_and_term_boundaries():
    same_platform_answers = [_answer_stub("ChatGPT") for _ in range(3)]
    diverse_platform_answers = [
        _answer_stub("ChatGPT"),
        _answer_stub("DeepSeek"),
        _answer_stub("Kimi"),
        _answer_stub("ChatGPT"),
        _answer_stub("DeepSeek"),
    ]

    assert (
        GraphPatchBuilderService._competitor_confidence_from_answers(
            same_platform_answers,
            base=0.58,
        )
        < 0.7
    )
    assert (
        GraphPatchBuilderService._competitor_confidence_from_answers(
            diverse_platform_answers,
            base=0.58,
        )
        >= 0.7
    )

    ten_answer_score = GraphPatchBuilderService._score_from_answers(
        [_answer_stub("ChatGPT") for _ in range(10)],
        base=56,
        per_answer=3,
        per_platform=5,
        cap=76,
    )
    twenty_answer_score = GraphPatchBuilderService._score_from_answers(
        [_answer_stub("ChatGPT") for _ in range(20)],
        base=56,
        per_answer=3,
        per_platform=5,
        cap=76,
    )
    assert twenty_answer_score - ten_answer_score <= 3

    assert GraphPatchBuilderService._contains_term("安利和纽崔莱经常一起出现", "安利")
    assert not GraphPatchBuilderService._contains_term("这是一段不健康的表达", "健康")
    assert not GraphPatchBuilderService._contains_term("这个句子里是不安利用法", "安利")


def test_storyline_risk_context_requires_brand_anchor_and_negative_association():
    service = BrandSpaceService.__new__(BrandSpaceService)
    brand_terms = ("安利", "纽崔莱")

    assert (
        service._classify_brand_risk_context(
            question="营养品牌长期健康管理有什么区别？",
            answer_text="Swisse 价格高，部分成分需要谨慎。",
            brand_terms=brand_terms,
            question_has_brand=False,
            answer_has_brand=False,
        )
        == "none"
    )
    assert (
        service._classify_brand_risk_context(
            question="安利是不是传销？",
            answer_text="安利属于正规直销，持有直销经营许可证，回答会提醒区别于传销。",
            brand_terms=brand_terms,
            question_has_brand=True,
            answer_has_brand=True,
        )
        == "clarified"
    )
    assert (
        service._classify_brand_risk_context(
            question="安利的事业机会靠谱吗？",
            answer_text="回答认为安利容易被理解为拉人头，也伴随熟人压力。",
            brand_terms=brand_terms,
            question_has_brand=True,
            answer_has_brand=True,
        )
        == "negative"
    )


def test_report_guardrails_cover_warn_and_block_edges():
    update_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    concentrated_patches = [
        GraphPatch(
            graph_update_id=update_id,
            entity_id=entity_id,
            patch_type="add_entity_relation",
            status="auto_applied",
            evidence_refs=[
                {"question": "安利和免疫力有什么关系？", "platform": "ChatGPT"},
                {"question": "安利和免疫力有什么关系？", "platform": "DeepSeek"},
                {"question": "安利和免疫力有什么关系？", "platform": "Kimi"},
                {"question": "安利和免疫力有什么关系？", "platform": "豆包"},
                {"question": "安利和免疫力有什么关系？", "platform": "Kimi"},
            ],
        )
    ]
    report_payload = {
        "strategic_terms": [
            {"reason": "ChatGPT 中安利与营养健康场景连接增强。"},
            {"reason": "DeepSeek 中安利与家庭健康问题连接增强。"},
        ],
        "competitor_claims": [],
        "recommended_actions": ["在 ChatGPT 补充家庭健康场景。"],
    }
    guardrails = BrandSpaceService.validate_report_payload(report_payload, concentrated_patches)
    guardrail_by_key = {item["guardrail_key"]: item for item in guardrails}
    assert guardrail_by_key["evidence_concentration"]["severity"] == "warn"

    missing_platform_payload = {
        "strategic_terms": [{"reason": "安利与营养健康场景连接增强。"}],
        "competitor_claims": [],
        "recommended_actions": ["补充家庭健康场景。"],
    }
    guardrails = BrandSpaceService.validate_report_payload(
        missing_platform_payload,
        concentrated_patches,
    )
    guardrail_by_key = {item["guardrail_key"]: item for item in guardrails}
    assert guardrail_by_key["action_platform_specificity"]["severity"] == "block"

    out_of_scope_payload = {
        **report_payload,
        "claims": [{"patch_id": str(uuid.uuid4()), "statement": "越界引用"}],
    }
    guardrails = BrandSpaceService.validate_report_payload(
        out_of_scope_payload,
        concentrated_patches,
    )
    guardrail_by_key = {item["guardrail_key"]: item for item in guardrails}
    assert guardrail_by_key["graph_update_scope"]["severity"] == "block"
