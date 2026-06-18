from __future__ import annotations

import os
import json
import uuid
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
from app.models.brand_intelligence import BrandPlatformAnswer
from app.models.brand_intelligence_run import BrandIntelligenceRun
from app.models.brand_space import BoardRun, GraphPatch
from app.models.entity import Entity, EntityStatus
from app.models.task import AnalysisTask, TaskStatus
from app.models.user import User, UserRole, UserStatus
from app.services.brand_space_service import BrandSpaceService


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
        guardrail_by_key = {
            item["guardrail_key"]: item for item in report_payload["guardrails"]
        }
        assert guardrail_by_key["competitor_claim_evidence"]["severity"] == "block"
        assert guardrail_by_key["action_platform_specificity"]["severity"] == "pass"

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
