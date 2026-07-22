"""Wave C1: deterministic recipe recommendation ranking (DB-free)."""

from __future__ import annotations

from app.api.v1.amwaychina_flow_topology import EMPTY_TOPOLOGY
from app.services.flow_topology_recipe_recommend import (
    build_recommendation_payload,
    rank_recommendations,
    structure_similarity_score,
    topology_structure_signature,
)


def _recipe(
    rid: str,
    name: str,
    *,
    entity: bool = True,
    removed: list[str] | None = None,
    description: str | None = None,
) -> dict:
    topo = {
        **EMPTY_TOPOLOGY,
        "removedEdgeIds": list(removed or []),
    }
    return {
        "id": rid,
        "name": name,
        "description": description,
        "entity_id": "e1" if entity else None,
        "scope": "entity" if entity else "organization",
        "topology": topo,
        "version": 1,
    }


def test_structure_signature_platforms():
    sig_all = topology_structure_signature(EMPTY_TOPOLOGY)
    assert len(sig_all["enabled_platforms"]) == 4

    sig_3 = topology_structure_signature(
        {**EMPTY_TOPOLOGY, "removedEdgeIds": ["e-fetch-doubao"]}
    )
    assert "doubao" not in sig_3["enabled_platforms"]
    assert len(sig_3["enabled_platforms"]) == 3


def test_structure_similarity_full_match():
    a = topology_structure_signature(EMPTY_TOPOLOGY)
    pts, reason = structure_similarity_score(a, a)
    assert pts > 0
    assert reason is not None
    assert "一致" in reason or "平台" in reason


def test_rank_prefers_entity_and_intent():
    recipes = [
        _recipe("org1", "组织默认", entity=False),
        _recipe("ent1", "三平台监测", entity=True, removed=["e-fetch-doubao"], description="跳过豆包"),
        _recipe("ent2", "全平台日常", entity=True),
    ]
    current = {**EMPTY_TOPOLOGY, "removedEdgeIds": ["e-fetch-doubao"]}
    ranked = rank_recommendations(
        recipes=recipes,
        current_topology=current,
        events=[],
        intent="三平台",
        active_recipe_id=None,
        limit=3,
    )
    assert ranked
    assert ranked[0]["recipe_id"] == "ent1"
    assert any("意图" in r or "匹配" in r for r in ranked[0]["reasons"])
    assert all(item["reasons"] for item in ranked)


def test_rank_uses_apply_events_and_excludes_active():
    recipes = [
        _recipe("a", "配方A"),
        _recipe("b", "配方B"),
        _recipe("c", "配方C"),
    ]
    events = [
        {
            "event_type": "apply_recipe",
            "payload": {"recipe_id": "b", "recipe_name": "配方B"},
        },
        {
            "event_type": "apply_recipe",
            "payload": {"recipe_id": "b", "recipe_name": "配方B"},
        },
        {
            "event_type": "apply_recipe",
            "payload": {"recipe_id": "a", "recipe_name": "配方A"},
        },
    ]
    ranked = rank_recommendations(
        recipes=recipes,
        current_topology=EMPTY_TOPOLOGY,
        events=events,
        active_recipe_id="a",
        limit=3,
    )
    ids = [x["recipe_id"] for x in ranked]
    assert "a" not in ids
    assert ids[0] == "b"
    assert any("套用" in r for r in ranked[0]["reasons"])


def test_payload_never_auto_applied():
    payload = build_recommendation_payload([])
    assert payload["auto_applied"] is False
    assert payload["engine"] == "deterministic_v0"
    assert payload["recommendations"] == []
