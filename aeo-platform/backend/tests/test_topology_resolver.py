"""Tests for the topology-aware orchestration resolver (3b-1.3)."""

import pytest

from app.workflow.node_contracts import FlowTopology
from app.workflow.topology_resolver import (
    BUILTIN_EDGE_IDS,
    CANVAS_PLATFORM_IDS,
    EDGE_PROJECTION_REPORT,
    EDGE_QUESTIONS_FETCH,
    apply_platform_gate,
    build_execution_plan_summary,
    disabled_platform_ids,
    fetch_chain_enabled,
    is_edge_active,
    load_flow_topology,
    report_chain_enabled,
)


def _topology(*removed: str) -> FlowTopology:
    return FlowTopology.from_dict({"removedEdgeIds": list(removed)})


def test_builtin_edge_ids_cover_frontend_defs():
    assert set(BUILTIN_EDGE_IDS) == {
        "e-questions-fetch",
        "e-lexicon-extract",
        "e-fetch-extract",
        "e-extract-projection",
        "e-projection-report",
        "e-fetch-deepseek",
        "e-fetch-kimi",
        "e-fetch-doubao",
        "e-fetch-hunyuan",
    }


def test_empty_topology_keeps_everything_active():
    topology = FlowTopology()
    assert all(is_edge_active(topology, edge) for edge in BUILTIN_EDGE_IDS)
    assert disabled_platform_ids(topology) == frozenset()
    assert fetch_chain_enabled(topology)
    assert report_chain_enabled(topology)


def test_removed_platform_edge_disables_platform():
    topology = _topology("e-fetch-doubao")
    assert disabled_platform_ids(topology) == frozenset({"doubao"})
    assert not is_edge_active(topology, "e-fetch-doubao")
    assert is_edge_active(topology, "e-fetch-kimi")


def test_platform_gate_passthrough_when_nothing_removed():
    topology = FlowTopology()
    assert apply_platform_gate(topology, None) == (None, frozenset())
    assert apply_platform_gate(topology, ["kimi"]) == (["kimi"], frozenset())


def test_platform_gate_none_filter_expands_to_survivors():
    topology = _topology("e-fetch-doubao", "e-fetch-hunyuan")
    gated, disabled = apply_platform_gate(topology, None)
    assert gated == ["deepseek", "kimi"]
    assert disabled == frozenset({"doubao", "hunyuan"})


def test_platform_gate_intersects_explicit_filter():
    topology = _topology("e-fetch-doubao")
    gated, _ = apply_platform_gate(topology, ["doubao", "kimi"])
    assert gated == ["kimi"]


def test_platform_gate_all_disabled_returns_none_sentinel():
    topology = _topology(*(f"e-fetch-{p}" for p in CANVAS_PLATFORM_IDS))
    gated, disabled = apply_platform_gate(topology, None)
    assert gated is None
    assert disabled == frozenset(CANVAS_PLATFORM_IDS)
    # explicit filter fully gated away behaves the same
    gated2, _ = apply_platform_gate(topology, ["kimi", "doubao"])
    assert gated2 is None


def test_fetch_chain_gate():
    assert not fetch_chain_enabled(_topology(EDGE_QUESTIONS_FETCH))
    assert fetch_chain_enabled(_topology("e-fetch-kimi"))


def test_report_chain_gate():
    assert not report_chain_enabled(_topology(EDGE_PROJECTION_REPORT))
    assert report_chain_enabled(FlowTopology())


@pytest.mark.asyncio
async def test_load_flow_topology_degrades_to_empty():
    # blank id and missing row both yield the default (all edges active)
    assert await load_flow_topology(None) == FlowTopology()
    assert await load_flow_topology("") == FlowTopology()
    assert await load_flow_topology("00000000-0000-0000-0000-000000000000") == (
        FlowTopology()
    )


def test_execution_plan_summary_empty_topology_all_platforms():
    plan = build_execution_plan_summary(FlowTopology())
    assert set(plan["planned_platforms"]) == set(CANVAS_PLATFORM_IDS)
    by_id = {s["node_id"]: s for s in plan["steps"]}
    assert by_id["fetch"]["status"] == "pending"
    assert by_id["report"]["status"] == "pending"


def test_execution_plan_summary_skips_disconnected_platform_and_report():
    topology = FlowTopology.from_dict(
        {
            "removedEdgeIds": ["e-fetch-doubao", "e-projection-report"],
            "customNodes": [
                {"id": "a1", "type": "analysis", "position": {}, "config": {}},
                {"id": "c1", "type": "content", "position": {}, "config": {}},
            ],
            "customEdges": [
                {"id": "e1", "source": "projection", "target": "a1"},
                {"id": "e2", "source": "a1", "target": "c1"},
            ],
        }
    )
    plan = build_execution_plan_summary(topology)
    by_id = {s["node_id"]: s for s in plan["steps"]}
    assert by_id["platform-doubao"]["status"] == "skipped"
    assert "doubao" not in plan["planned_platforms"]
    assert by_id["report"]["status"] == "skipped"
    # analysis still planned from projection when report edge is down
    assert by_id["a1"]["status"] == "pending"
    assert by_id["c1"]["status"] == "pending"
    assert "e-fetch-doubao" not in plan["active_edge_ids"]
    assert "e-projection-report" not in plan["active_edge_ids"]
