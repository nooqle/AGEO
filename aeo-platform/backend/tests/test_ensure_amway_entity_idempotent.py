"""ensure_amwaychina_console_entity must query Entity table, not poisoned relationships."""

from __future__ import annotations

from app.services import organization_feature_service as ofs


def test_ensure_uses_explicit_entity_query_helpers():
    # Regression guard: helpers exist for DB-table listing (not org.entities only)
    assert hasattr(ofs, "list_organization_entities")
    assert hasattr(ofs, "find_amway_association_entities")
    assert callable(ofs.list_organization_entities)
    assert callable(ofs.find_amway_association_entities)


def test_ensure_source_does_not_rely_on_relationship_iteration_only():
    import inspect

    src = inspect.getsource(ofs.ensure_amwaychina_console_entity)
    # Must call find_amway_association_entities (explicit query path)
    assert "find_amway_association_entities" in src
    # Must not only loop organization.entities as sole discovery path
    assert "for entity in organization.entities" not in src
