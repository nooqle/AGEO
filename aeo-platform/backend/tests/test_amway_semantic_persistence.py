"""Isolated SQLite/route regressions, executed by independent QA only."""
import importlib.util
import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.entity import Entity
from app.models.amway_entity_lexicon import AmwayEntityLexiconOverride
from app.services.amway_entity_lexicon_service import AmwayEntityLexiconService
from app.services.amway_lexicon_repair_service import export_repair_state, repair_lexicon
from tests.test_amway_semantic_repair import repair_fixture, topic_fixture, extract


@pytest.mark.asyncio
async def test_atomic_repair_persists_semantics_and_is_scoped_to_entity(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'lexicon.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    registry, package = repair_fixture()
    async with factory() as db:
        first, other = Entity(name="Amway"), Entity(name="Other tenant")
        db.add_all([first, other])
        await db.commit()
        first_id, other_id = first.id, other.id
        from app.api.v1.amwaychina_common import require_amway_entity
        with pytest.raises(HTTPException) as denied:
            await require_amway_entity(db, SimpleNamespace(id=uuid.uuid4(), organization_id=None), str(first_id), manage=True)
        assert denied.value.status_code == 403
        service = AmwayEntityLexiconService(db, base_registry=registry)
        preview = await repair_lexicon(service, entity=first, user_id=None, package=package)
        assert preview["status"] == "preview"
        assert (await db.execute(select(AmwayEntityLexiconOverride))).scalars().all() == []
        invalid = {**package, "records": [*package["records"], {"entity_id": "bad"}]}
        with pytest.raises(ValueError):
            await repair_lexicon(service, entity=first, user_id=None, package=invalid, apply=True)
        await db.rollback()
        first = await db.get(Entity, first_id)
        applied = await repair_lexicon(service, entity=first, user_id=None, package=package, apply=True)
        assert applied["effective_hash"] == preview["effective_hash"]
        before = await export_repair_state(service, first_id)
        retry = await repair_lexicon(service, entity=first, user_id=None, package=package, apply=True)
        assert retry["status"] == "unchanged"
        assert await export_repair_state(service, first_id) == before
        assert (await export_repair_state(service, other_id))["override_before_images"] == []
    async with factory() as db:
        loaded = await AmwayEntityLexiconService(db, base_registry=registry).registry_for_entity(first_id)
        assert loaded.effective_hash == applied["effective_hash"]
        assert loaded.require_entity("new_identity").semantic_definition.source_refs
    await engine.dispose()


def test_migration_adds_nullable_column_preserving_legacy_rows(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/039_add_amway_lexicon_semantic_definition.py'
    spec = importlib.util.spec_from_file_location("semantic_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE amway_entity_lexicon_overrides (id TEXT PRIMARY KEY, canonical_name TEXT)"))
        connection.execute(text("INSERT INTO amway_entity_lexicon_overrides VALUES ('legacy-id', 'Legacy name')"))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        column = next(c for c in inspect(connection).get_columns("amway_entity_lexicon_overrides") if c["name"] == "semantic_definition")
        assert column["nullable"] is True
        assert connection.execute(text("SELECT id, canonical_name, semantic_definition FROM amway_entity_lexicon_overrides")).one() == ('legacy-id', 'Legacy name', None)
        connection.execute(text("UPDATE amway_entity_lexicon_overrides SET semantic_definition = :value"), {"value": json.dumps({"semantic_type": "concept"})})
        # Application rollback uses its old column list, leaving the new column.
        assert connection.execute(text("SELECT id, canonical_name FROM amway_entity_lexicon_overrides")).one() == ('legacy-id', 'Legacy name')
    engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["export", "preview", "apply"])
async def test_repair_routes_require_manage_before_reading_data(monkeypatch, route):
    from app.api.v1 import amwaychina
    guard = AsyncMock(side_effect=HTTPException(403, "denied"))
    monkeypatch.setattr(amwaychina, "_require_amway_entity", guard)
    db, user = AsyncMock(), SimpleNamespace(id=uuid.uuid4())
    with pytest.raises(HTTPException) as error:
        if route == "export":
            await amwaychina.export_entity_lexicon_repair("entity", current_user=user, db=db)
        else:
            await amwaychina.apply_entity_lexicon_repair("entity", {}, apply=route == "apply", current_user=user, db=db)
    assert error.value.status_code == 403
    guard.assert_awaited_once_with(db, user, "entity", manage=True)
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_realtime_registry_loading_failure_propagates(monkeypatch):
    from app.workflow.nodes_a4 import _amway_realtime_extractor
    import app.core.database as database
    context = AsyncMock()
    context.__aenter__.side_effect = RuntimeError("database unavailable")
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: context)
    with pytest.raises(RuntimeError, match="database unavailable"):
        await _amway_realtime_extractor(uuid.uuid4())


@pytest.mark.asyncio
async def test_realtime_snapshot_survives_final_extraction_and_calibration(monkeypatch):
    from app.workflow import nodes_amway
    from app.workflow.node_contracts import FlowTopology
    reg = topic_fixture()
    realtime = extract(reg, "Material Alpha")
    monkeypatch.setattr(nodes_amway, "load_flow_topology", AsyncMock(return_value=FlowTopology()))
    loader = AsyncMock(side_effect=AssertionError("must not reload current lexicon"))
    monkeypatch.setattr(nodes_amway, "_load_editable_lexicon_registry", loader)
    for name in ("send_progress_event", "send_stage_result", "_persist_a4_stage_result", "_persist_amway_calibrated_run_snapshot"):
        monkeypatch.setattr(nodes_amway, name, AsyncMock())
    state = {"session_id": "test", "entity_id": str(uuid.uuid4()), "analysis_mode": "amway_association_circle", "headless_mode": True,
             "fetch_results": [{"question_id": "q1", "question_text": "安利", "platform_results": [{"platform": "Kimi", "answer_text": "Material Alpha"}]}],
             "realtime_entity_extraction_result": realtime}
    extracted = (await nodes_amway.amway_extract_node(state)).update["entity_extraction_result"]
    state["entity_extraction_result"] = extracted
    calibrated = (await nodes_amway.amway_projection_node(state)).update["entity_calibration_result"]
    assert extracted["effective_lexicon_hash"] == calibrated["effective_lexicon_hash"] == reg.effective_hash
    loader.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("incoming_version,incoming_hash", [("new-version", "old-hash"), ("old-version", "new-hash")])
@pytest.mark.parametrize("create_report", [False, True])
async def test_same_run_different_version_is_rejected_without_overwriting(tmp_path, incoming_version, incoming_hash, create_report):
    from app.models.amway_circle_tracking import AmwayCircleRun
    from app.models.brand_intelligence_run import BrandIntelligenceRun
    from app.services.amway_circle_tracking_service import AmwayCircleTrackingService

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'immutable-run.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        entity = Entity(name="Amway")
        db.add(entity)
        await db.flush()
        brand_run = BrandIntelligenceRun(entity_id=entity.id)
        db.add(brand_run)
        await db.flush()
        saved = AmwayCircleRun(entity_id=entity.id, brand_intelligence_run_id=brand_run.id,
                               run_sequence=1, status="completed", run_label="Original run",
                               extraction_version="old-version", lexicon_hash="old-hash",
                               answer_scope={"preserved": True})
        db.add(saved)
        await db.commit()
        before = dict((await db.execute(text("SELECT * FROM amway_circle_runs"))).mappings().one())
        with pytest.raises(ValueError, match="incompatible_version"):
            await AmwayCircleTrackingService(db)._persist_tracking_run(
                brand_run=brand_run,
                state={"entity_extraction_result": {"schema_version": incoming_version, "effective_lexicon_hash": incoming_hash}},
                artifact={}, projection_body={}, create_report=create_report,
            )
        await db.commit()
        after = dict((await db.execute(text("SELECT * FROM amway_circle_runs"))).mappings().one())
        assert before == after
    await engine.dispose()
