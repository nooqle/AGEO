from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.entity_service import EntityService


class _FakeScalarResult:
    def all(self):
        return []


class _FakeExecuteResult:
    def scalars(self):
        return _FakeScalarResult()


class _FakeDb:
    def __init__(self):
        self.statements = []
        self.deleted = []
        self.committed = False

    async def execute(self, statement):
        self.statements.append(statement)
        return _FakeExecuteResult()

    async def delete(self, item):
        self.deleted.append(item)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        raise AssertionError("rollback should not be called")


@pytest.mark.asyncio
async def test_delete_entity_cleans_monitoring_dependents_before_entity(monkeypatch):
    db = _FakeDb()
    service = EntityService(db)
    entity_id = uuid4()
    entity = SimpleNamespace(id=entity_id, name="荣耀")

    async def fake_get_entity_model(*_args, **_kwargs):
        return entity

    monkeypatch.setattr(service, "get_entity_model", fake_get_entity_model)

    deleted = await service.delete_entity(str(entity_id))

    assert deleted is True
    assert db.committed is True
    assert entity in db.deleted

    statement_tables = [
        statement.table.name
        for statement in db.statements
        if hasattr(statement, "table")
    ]
    assert "monitoring_alerts" in statement_tables
    assert "monitoring_evidence_records" in statement_tables
    assert "monitoring_runs" in statement_tables
    assert "monitoring_schedules" in statement_tables
    assert "monitoring_plans" in statement_tables
    assert "monitoring_question_sets" in statement_tables
    assert "analysis_snapshots" in statement_tables
    assert "fetch_run_platform_states" in statement_tables
    assert "analysis_tasks" in statement_tables
