"""Node-level wiring tests for the topology gates (3b-1.3).

These prove the resolver is actually consulted by the A3/A4 chain — without
triggering any real fetch — by monkeypatching ``load_flow_topology`` at the
node modules' import sites.
"""

from types import SimpleNamespace

import pytest

from app.workflow.node_contracts import FlowTopology
from app.workflow import nodes_a3, nodes_a4


def _topology(*removed: str) -> FlowTopology:
    return FlowTopology.from_dict({"removedEdgeIds": list(removed)})


@pytest.mark.asyncio
async def test_a4_all_platforms_disconnected_short_circuits_fetch(monkeypatch):
    topology = _topology(
        "e-fetch-deepseek", "e-fetch-kimi", "e-fetch-doubao", "e-fetch-hunyuan"
    )

    async def fake_load(entity_id):
        return topology

    monkeypatch.setattr(nodes_a4, "load_flow_topology", fake_load)

    command = await nodes_a4.a4_fetch_node(
        {
            "session_id": "s-1",
            "entity_id": "8dc281a9-a270-42dd-83da-77b553399d18",
            "questions": [{"id": "q1", "text": "安利中国怎么样？"}],
            "fetch_mode": "fast",
        }
    )
    assert command.update["fetch_results"] == []
    assert "跳过答案抓取" in command.update["progress_message"]


@pytest.mark.asyncio
async def test_a4_partial_disconnect_gates_platform_filter(monkeypatch):
    topology = _topology("e-fetch-doubao")

    async def fake_load(entity_id):
        return topology

    captured: dict = {}

    def fake_build_request(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            auth_context=SimpleNamespace(context_key="auth"),
            run_context=SimpleNamespace(context_key="run"),
            platforms=(),
        )

    monkeypatch.setattr(nodes_a4, "load_flow_topology", fake_load)
    monkeypatch.setattr(
        nodes_a4._AIO_ANSWER_FETCH_TOOL, "build_request", fake_build_request
    )

    command = await nodes_a4.a4_fetch_node(
        {
            "session_id": "s-1",
            "entity_id": "8dc281a9-a270-42dd-83da-77b553399d18",
            "questions": [],  # early-return right after build_request
            "fetch_mode": "fast",
        }
    )
    assert captured["platform_filter"] == ["deepseek", "kimi", "hunyuan"]
    assert command.update["fetch_results"] == []


@pytest.mark.asyncio
async def test_a4_no_topology_record_keeps_legacy_passthrough(monkeypatch):
    async def fake_load(entity_id):
        return FlowTopology()  # missing row → all edges active

    captured: dict = {}

    def fake_build_request(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            auth_context=SimpleNamespace(context_key="auth"),
            run_context=SimpleNamespace(context_key="run"),
            platforms=(),
        )

    monkeypatch.setattr(nodes_a4, "load_flow_topology", fake_load)
    monkeypatch.setattr(
        nodes_a4._AIO_ANSWER_FETCH_TOOL, "build_request", fake_build_request
    )

    await nodes_a4.a4_fetch_node(
        {
            "session_id": "s-1",
            "entity_id": "8dc281a9-a270-42dd-83da-77b553399d18",
            "questions": [],
            "fetch_mode": "fast",
        }
    )
    # None keeps the legacy "all platforms" meaning downstream
    assert captured["platform_filter"] is None


@pytest.mark.asyncio
async def test_a3_fetch_chain_gate_blocks_chaining_into_a4(monkeypatch):
    topology = _topology("e-questions-fetch")

    async def fake_load(entity_id):
        return topology

    monkeypatch.setattr(nodes_a3, "load_flow_topology", fake_load)

    update = await nodes_a3._question_set_confirmation_update(
        {"entity_id": "8dc281a9-a270-42dd-83da-77b553399d18", "fetch_mode": "fast"},
        question_set_id="qs-1",
        monitor_mode="scenario",
        question_count=8,
    )
    assert update["next_required_action"] is None
    assert update["execution_status"] == "completed"
    assert "画布已断开" in update["progress_message"]


@pytest.mark.asyncio
async def test_a3_fetch_chain_gate_open_chains_into_a4(monkeypatch):
    async def fake_load(entity_id):
        return FlowTopology()

    monkeypatch.setattr(nodes_a3, "load_flow_topology", fake_load)

    update = await nodes_a3._question_set_confirmation_update(
        {"entity_id": "8dc281a9-a270-42dd-83da-77b553399d18", "fetch_mode": "fast"},
        question_set_id="qs-1",
        monitor_mode="scenario",
        question_count=8,
    )
    action = update["next_required_action"]
    assert action is not None
    assert action["tool_name"] == "answer_fetch"
