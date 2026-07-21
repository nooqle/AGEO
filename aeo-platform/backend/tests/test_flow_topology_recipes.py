"""Flow topology recipe normalize + dict shape (DB-free)."""

from __future__ import annotations

from app.api.v1.amwaychina_flow_topology import EMPTY_TOPOLOGY, normalize_topology
from app.services.flow_topology_recipe_service import recipe_to_dict
from types import SimpleNamespace
from uuid import uuid4


def test_normalize_empty_topology_for_recipe():
    doc = normalize_topology(EMPTY_TOPOLOGY)
    assert doc["customNodes"] == []
    assert "removedEdgeIds" in doc


def test_recipe_to_dict_scope():
    org = uuid4()
    row = SimpleNamespace(
        id=uuid4(),
        organization_id=org,
        entity_id=None,
        name="日常监测",
        description="三平台",
        topology={
            **EMPTY_TOPOLOGY,
            "removedEdgeIds": ["e-fetch-doubao"],
        },
        version=1,
        created_by_user_id=None,
        created_at=None,
        updated_at=None,
    )
    d = recipe_to_dict(row)  # type: ignore[arg-type]
    assert d["scope"] == "organization"
    assert d["name"] == "日常监测"
    assert d["entity_id"] is None

    row.entity_id = uuid4()
    d2 = recipe_to_dict(row)  # type: ignore[arg-type]
    assert d2["scope"] == "entity"
