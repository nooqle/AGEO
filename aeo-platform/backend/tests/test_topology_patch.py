"""3c-B: deterministic topology ops + validate path."""

from __future__ import annotations

import pytest

from app.api.v1.amwaychina import _EMPTY_TOPOLOGY, _normalize_topology
from app.workflow.node_contracts import FlowTopology
from app.workflow.topology_patch import (
    apply_topology_ops,
    expand_intent,
    resolve_ops_payload,
)
from app.workflow.topology_resolver import build_execution_plan_summary


def test_skip_doubao_intent_removes_platform_edge():
    ops = expand_intent("skip_doubao")
    proposed, summary = apply_topology_ops(_EMPTY_TOPOLOGY, ops)
    normalized = _normalize_topology(proposed)
    assert "e-fetch-doubao" in normalized["removedEdgeIds"]
    assert "e-fetch-doubao" in summary["removed_edge_ids_added"]
    plan = build_execution_plan_summary(FlowTopology.from_dict(normalized))
    assert "doubao" not in (plan.get("planned_platforms") or [])


def test_enable_all_platforms_restores_edges():
    base = {
        **_EMPTY_TOPOLOGY,
        "removedEdgeIds": ["e-fetch-doubao", "e-fetch-kimi"],
    }
    ops = expand_intent("enable_all_platforms")
    proposed, summary = apply_topology_ops(base, ops)
    normalized = _normalize_topology(proposed)
    assert "e-fetch-doubao" not in normalized["removedEdgeIds"]
    assert "e-fetch-kimi" not in normalized["removedEdgeIds"]
    assert set(summary["removed_edge_ids_restored"]) >= {
        "e-fetch-doubao",
        "e-fetch-kimi",
    }


def test_add_projection_analysis_wires_custom_node():
    ops = expand_intent("add_projection_analysis", _EMPTY_TOPOLOGY)
    proposed, summary = apply_topology_ops(_EMPTY_TOPOLOGY, ops)
    normalized = _normalize_topology(proposed)
    assert len(normalized["customNodes"]) == 1
    node = normalized["customNodes"][0]
    assert node["type"] == "analysis"
    assert any(
        e["source"] == "projection" and e["target"] == node["id"]
        for e in normalized["customEdges"]
    )
    assert node["id"] in summary["nodes_added"]


def test_add_projection_analysis_second_expand_is_deterministic():
    """F1: same base → same collision id on every expand (preview == apply)."""
    base = {
        **_EMPTY_TOPOLOGY,
        "customNodes": [
            {
                "id": "custom-analysis-3c-preset",
                "type": "analysis",
                "position": {"x": 1, "y": 1},
                "config": {},
            }
        ],
        "customEdges": [
            {
                "id": "e-custom-analysis-3c-preset",
                "source": "projection",
                "target": "custom-analysis-3c-preset",
            }
        ],
    }
    ops_a = expand_intent("add_projection_analysis", base)
    ops_b = expand_intent("add_projection_analysis", base)
    assert ops_a == ops_b
    node_id = ops_a[0]["node"]["id"]
    assert node_id == "custom-analysis-3c-preset-2"
    proposed, _ = apply_topology_ops(base, ops_a)
    assert any(n["id"] == node_id for n in proposed["customNodes"])


def test_add_custom_node_idempotent_upsert():
    ops = [
        {
            "op": "add_custom_node",
            "node": {
                "id": "a1",
                "type": "analysis",
                "position": {"x": 1, "y": 2},
                "config": {"label": "v1"},
            },
        },
        {
            "op": "add_custom_node",
            "node": {
                "id": "a1",
                "type": "analysis",
                "position": {"x": 9, "y": 9},
                "config": {"label": "v2"},
            },
        },
    ]
    proposed, _ = apply_topology_ops(_EMPTY_TOPOLOGY, ops)
    normalized = _normalize_topology(proposed)
    assert len(normalized["customNodes"]) == 1
    assert normalized["customNodes"][0]["config"]["label"] == "v2"
    assert normalized["customNodes"][0]["position"]["x"] == 9


def test_self_loop_edge_rejected_by_validate():
    ops = [
        {
            "op": "add_custom_node",
            "node": {
                "id": "a1",
                "type": "analysis",
                "position": {"x": 0, "y": 0},
                "config": {},
            },
        },
        {
            "op": "add_custom_edge",
            "edge": {"id": "e-loop", "source": "a1", "target": "a1"},
        },
    ]
    proposed, _ = apply_topology_ops(_EMPTY_TOPOLOGY, ops)
    with pytest.raises(ValueError, match="自环"):
        _normalize_topology(proposed)


def test_resolve_ops_xor_intent():
    with pytest.raises(ValueError, match="二选一"):
        resolve_ops_payload(
            intent_id="skip_doubao",
            ops=[{"op": "disable_platform", "platform": "kimi"}],
            base=None,
        )
    with pytest.raises(ValueError, match="必须提供"):
        resolve_ops_payload(intent_id=None, ops=None, base=None)
    ops = resolve_ops_payload(intent_id="skip_doubao", ops=None, base=None)
    assert ops[0]["op"] == "disable_platform"


def test_unknown_op_rejected():
    with pytest.raises(ValueError, match="未知 op"):
        apply_topology_ops(_EMPTY_TOPOLOGY, [{"op": "explode"}])


def test_unknown_intent_rejected():
    with pytest.raises(ValueError, match="未知预设"):
        expand_intent("not-a-real-intent")
