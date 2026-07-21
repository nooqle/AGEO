"""Tests for amwaychina custom analysis/content nodes (blueprint 3b-1.5)."""

from __future__ import annotations

import pytest

from app.services.amway_flow_custom_node_service import (
    build_deterministic_analysis,
    render_content_prompt,
    run_analysis_node,
    run_content_node,
)
from app.workflow import nodes_amway
from app.workflow.node_contracts import FlowTopology, get_contract, is_schedulable
from app.workflow.topology_resolver import (
    analysis_nodes_schedulable,
    content_nodes_schedulable,
)


def _projection() -> dict:
    return {
        "center_terms": ["安利"],
        "sample_scope": {
            "valid_answer_count": 12,
            "valid_platform_names": ["kimi", "deepseek"],
            "requested_platforms": ["kimi", "deepseek", "doubao"],
        },
        "nodes": [
            {
                "node_id": "n1",
                "term": "纽崔莱",
                "track": "core",
                "answer_count": 8,
            },
            {
                "node_id": "n2",
                "term": "监管风险",
                "track": "risk",
                "entity_type": "监管",
                "answer_count": 2,
            },
        ],
        "risk_map": {"risk_count": 1},
    }


def test_analysis_and_content_contracts_are_schedulable():
    assert is_schedulable("analysis")
    assert is_schedulable("content")
    assert get_contract("analysis").tool_name == "amway_secondary_analysis"
    assert get_contract("content").graph_node == "amway_content"


def test_analysis_nodes_schedulable_requires_input_edge():
    bare = FlowTopology.from_dict(
        {
            "customNodes": [
                {"id": "a1", "type": "analysis", "position": {}, "config": {}}
            ],
            "customEdges": [],
        }
    )
    assert analysis_nodes_schedulable(bare) == ()

    wired = FlowTopology.from_dict(
        {
            "customNodes": [
                {"id": "a1", "type": "analysis", "position": {}, "config": {}}
            ],
            "customEdges": [
                {"id": "e1", "source": "projection", "target": "a1"},
            ],
        }
    )
    ready = analysis_nodes_schedulable(wired)
    assert len(ready) == 1
    assert ready[0].id == "a1"


def test_content_nodes_schedulable_from_lexicon_or_analysis():
    topo = FlowTopology.from_dict(
        {
            "customNodes": [
                {"id": "a1", "type": "analysis", "position": {}, "config": {}},
                {"id": "c1", "type": "content", "position": {}, "config": {}},
                {"id": "c2", "type": "content", "position": {}, "config": {}},
            ],
            "customEdges": [
                {"id": "e1", "source": "lexicon", "target": "c1"},
                {"id": "e2", "source": "a1", "target": "c2"},
            ],
        }
    )
    ready_ids = {n.id for n in content_nodes_schedulable(topo)}
    assert ready_ids == {"c1", "c2"}


def test_deterministic_analysis_builds_cards():
    result = build_deterministic_analysis(
        projection=_projection(), dimensions=["platform", "entities", "risk"]
    )
    assert result["mode"] == "deterministic"
    titles = [c["title"] for c in result["cards"]]
    assert "平台覆盖" in titles
    assert "高频实体 Top 10" in titles
    assert "风险信号" in titles
    assert any("纽崔莱" in line for card in result["cards"] for line in card["lines"])


def test_render_content_prompt_substitutes_vars():
    text = render_content_prompt(
        "品牌={{centerTerm}};词库={{entities}};分析={{analysis}}",
        center_term="安利",
        entities_text="纽崔莱",
        analysis_text="风险上升",
    )
    assert text == "品牌=安利;词库=纽崔莱;分析=风险上升"


@pytest.mark.asyncio
async def test_run_analysis_node_falls_back_without_llm(monkeypatch):
    async def _boom(*args, **kwargs):
        raise RuntimeError("no llm")

    class _BrokenModel:
        async def async_call(self, *args, **kwargs):
            return await _boom()

    monkeypatch.setattr(
        "app.core.llm.get_llm_model",
        lambda: _BrokenModel(),
    )
    result = await run_analysis_node(
        projection=_projection(),
        config={"dimensions": ["entities"], "prompt": "focus"},
        use_llm=True,
    )
    assert result["mode"] == "deterministic"
    assert "fallback_reason" in result
    assert result["cards"]


@pytest.mark.asyncio
async def test_run_content_node_template_fallback(monkeypatch):
    class _BrokenModel:
        async def async_call(self, *args, **kwargs):
            raise RuntimeError("no llm")

    monkeypatch.setattr(
        "app.core.llm.get_llm_model",
        lambda: _BrokenModel(),
    )
    result = await run_content_node(
        center_term="安利",
        lexicon_entries=[{"canonical_name": "纽崔莱"}],
        analysis_result={"summary": "核心实体稳定", "cards": []},
        config={"promptTemplate": "写给 {{centerTerm}}：{{entities}} / {{analysis}}"},
        use_llm=True,
    )
    assert result["mode"] == "template"
    assert "安利" in result["draft"]
    assert "纽崔莱" in result["draft"]


@pytest.fixture(autouse=True)
def _quiet_events(monkeypatch):
    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(nodes_amway, "send_progress_event", _noop)
    monkeypatch.setattr(nodes_amway, "send_stage_result", _noop)


@pytest.mark.asyncio
async def test_amway_analysis_node_runs_and_chains_content(monkeypatch):
    topology = FlowTopology.from_dict(
        {
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

    async def _topo(entity_id):
        return topology

    async def _no_persist(*args, **kwargs):
        return None

    monkeypatch.setattr(nodes_amway, "load_flow_topology", _topo)
    monkeypatch.setattr(
        "app.services.amway_flow_custom_node_service.persist_custom_node_results",
        _no_persist,
    )

    async def _analysis(**kwargs):
        return {
            "generatedAt": "2026-07-21T00:00:00Z",
            "dimensions": ["entities"],
            "cards": [{"title": "t", "lines": ["l"]}],
            "mode": "deterministic",
        }

    monkeypatch.setattr(
        "app.services.amway_flow_custom_node_service.run_analysis_node",
        _analysis,
    )

    command = await nodes_amway.amway_analysis_node(
        {
            "session_id": "s1",
            "entity_id": None,
            "association_circle_projection": _projection(),
            "report": None,
        }
    )
    update = command.update
    assert "a1" in (update.get("flow_analysis_results") or {})
    assert update["next_required_action"]["tool_name"] == "amway_content_draft"


@pytest.mark.asyncio
async def test_amway_analysis_skips_when_not_wired(monkeypatch):
    async def _topo(entity_id):
        return FlowTopology.from_dict(
            {
                "customNodes": [
                    {"id": "a1", "type": "analysis", "position": {}, "config": {}}
                ],
                "customEdges": [],
            }
        )

    monkeypatch.setattr(nodes_amway, "load_flow_topology", _topo)
    command = await nodes_amway.amway_analysis_node(
        {
            "session_id": "s1",
            "entity_id": None,
            "association_circle_projection": _projection(),
        }
    )
    assert command.update["next_required_action"] is None
    assert "跳过" in command.update["progress_message"]
