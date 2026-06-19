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
from app.models.brand_intelligence import BrandIntelligenceQuestion, BrandPlatformAnswer
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
