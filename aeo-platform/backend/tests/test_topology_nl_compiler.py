"""3c-C1: rule-based NL → topology ops."""

from __future__ import annotations

import pytest

from app.api.v1.amwaychina import _EMPTY_TOPOLOGY, _normalize_topology
from app.workflow.node_contracts import FlowTopology
from app.workflow.topology_nl_compiler import compile_nl_to_ops
from app.workflow.topology_patch import apply_topology_ops
from app.workflow.topology_resolver import build_execution_plan_summary


def test_compile_skip_doubao_phrase():
    r = compile_nl_to_ops("这次先别跑豆包")
    assert r.mode == "rule"
    assert r.intent_id == "skip_doubao"
    proposed, _ = apply_topology_ops(_EMPTY_TOPOLOGY, r.ops)
    plan = build_execution_plan_summary(
        FlowTopology.from_dict(_normalize_topology(proposed))
    )
    assert "doubao" not in (plan.get("planned_platforms") or [])


def test_compile_enable_all_platforms():
    base = {**_EMPTY_TOPOLOGY, "removedEdgeIds": ["e-fetch-doubao", "e-fetch-kimi"]}
    r = compile_nl_to_ops("恢复全部平台", base)
    assert r.intent_id == "enable_all_platforms"
    proposed, _ = apply_topology_ops(base, r.ops)
    assert "e-fetch-doubao" not in proposed["removedEdgeIds"]


def test_compile_add_analysis():
    r = compile_nl_to_ops("给图谱加一个分析节点")
    assert r.intent_id == "add_projection_analysis"
    assert any(o.get("op") == "add_custom_node" for o in r.ops)


def test_compile_skip_kimi():
    r = compile_nl_to_ops("跳过 kimi")
    assert r.ops == [{"op": "disable_platform", "platform": "kimi"}]


def test_compile_disable_report():
    r = compile_nl_to_ops("这次不生成报告")
    assert r.ops[0]["op"] == "remove_builtin_edge"
    assert r.ops[0]["edge_id"] == "e-projection-report"


def test_compile_unknown_raises():
    with pytest.raises(ValueError, match="无法识别"):
        compile_nl_to_ops("帮我写一首诗")


def test_compile_empty_raises():
    with pytest.raises(ValueError, match="请输入"):
        compile_nl_to_ops("   ")
