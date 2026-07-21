"""Tests for the standalone amway extract/projection nodes (3b-1.2)."""

import pytest

from app.workflow import nodes_amway
from app.workflow.node_contracts import FlowTopology


def _fetch_results() -> list[dict]:
    return [
        {
            "question_id": "q1",
            "question_text": "安利中国的纽崔莱怎么样？",
            "platform_results": [
                {
                    "platform": "kimi",
                    "fetch_method": "api",
                    "success": True,
                    "answer": {
                        "content": "安利（中国）日用品有限公司旗下纽崔莱是知名营养保健品牌，"
                        "安利蛋白粉和雅姿也广受关注。",
                        "word_count": 40,
                    },
                    "citations": [],
                }
            ],
        }
    ]


def _amway_state(**overrides):
    state = {
        "session_id": "s-1",
        "entity_id": None,  # 无实体 → 跳过词库/快照持久化，专注纯计算
        "task_id": None,
        "analysis_mode": "amway_association_circle",
        "fetch_results": _fetch_results(),
        "headless_mode": True,
    }
    state.update(overrides)
    return state


@pytest.fixture(autouse=True)
def _quiet_events(monkeypatch):
    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(nodes_amway, "send_progress_event", _noop)
    monkeypatch.setattr(nodes_amway, "send_stage_result", _noop)
    monkeypatch.setattr(nodes_amway, "_persist_a4_stage_result", _noop)
    monkeypatch.setattr(nodes_amway, "_persist_amway_calibrated_run_snapshot", _noop)


@pytest.mark.asyncio
async def test_extract_node_produces_extraction_and_chains_projection(monkeypatch):
    async def _empty_topology(entity_id):
        return FlowTopology()

    monkeypatch.setattr(nodes_amway, "load_flow_topology", _empty_topology)

    command = await nodes_amway.amway_extract_node(_amway_state())
    update = command.update
    result = update["entity_extraction_result"]
    assert isinstance(result, dict)
    assert result.get("signal_count", 0) > 0
    assert update["next_required_action"]["tool_name"] == "amway_circle_projection"


@pytest.mark.asyncio
async def test_extract_node_stops_when_projection_edge_removed(monkeypatch):
    async def _topology(entity_id):
        return FlowTopology.from_dict({"removedEdgeIds": ["e-extract-projection"]})

    monkeypatch.setattr(nodes_amway, "load_flow_topology", _topology)

    command = await nodes_amway.amway_extract_node(_amway_state())
    assert command.update["next_required_action"] is None
    assert "止于实体抽取" in command.update["progress_message"]


@pytest.mark.asyncio
async def test_extract_node_skips_without_fetch_results():
    command = await nodes_amway.amway_extract_node(_amway_state(fetch_results=[]))
    assert command.update["entity_extraction_result"] is None
    assert command.update["next_required_action"] is None


@pytest.mark.asyncio
async def test_projection_node_produces_circle_and_chains_report(monkeypatch):
    async def _empty_topology(entity_id):
        return FlowTopology()

    monkeypatch.setattr(nodes_amway, "load_flow_topology", _empty_topology)

    extract_update = (await nodes_amway.amway_extract_node(_amway_state())).update
    state = _amway_state(
        entity_extraction_result=extract_update["entity_extraction_result"]
    )

    command = await nodes_amway.amway_projection_node(state)
    update = command.update
    assert isinstance(update["association_circle_projection"], dict)
    assert update["association_circle_projection"].get("nodes")
    assert isinstance(update["entity_calibration_result"], dict)
    assert update["brand_association_report_input"] is not None
    action = update["next_required_action"]
    assert action["tool_name"] == "analysis_report_skill"
    assert action["tool_args"]["report_type"] == "scenario"


@pytest.mark.asyncio
async def test_projection_node_stops_when_report_edge_removed(monkeypatch):
    async def _topology(entity_id):
        return FlowTopology.from_dict({"removedEdgeIds": ["e-projection-report"]})

    monkeypatch.setattr(nodes_amway, "load_flow_topology", _topology)

    extract_update = (await nodes_amway.amway_extract_node(_amway_state())).update
    state = _amway_state(
        entity_extraction_result=extract_update["entity_extraction_result"]
    )

    command = await nodes_amway.amway_projection_node(state)
    assert command.update["next_required_action"] is None
    assert "止于图谱构建" in command.update["progress_message"]
    # 图谱产物仍然落进 state——画布断链只影响推进，不影响产物
    assert command.update["association_circle_projection"]


@pytest.mark.asyncio
async def test_projection_node_skips_without_extraction():
    command = await nodes_amway.amway_projection_node(_amway_state())
    assert command.update["association_circle_projection"] is None
    assert command.update["next_required_action"] is None
