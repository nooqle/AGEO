"""Wave O: visible flow lesson synthesis (DB-free)."""

from __future__ import annotations

from app.api.v1.amwaychina_flow_topology import EMPTY_TOPOLOGY
from app.services.flow_run_lesson_service import (
    build_lessons_payload,
    lessons_from_run,
    lessons_from_topology,
)


def test_lessons_from_topology_skip_doubao():
    topo = {**EMPTY_TOPOLOGY, "removedEdgeIds": ["e-fetch-doubao"]}
    items = lessons_from_topology(topo)
    node_ids = {i["node_id"] for i in items}
    assert "platform-doubao" in node_ids
    assert "fetch" in node_ids
    assert any("豆包" in i["headline"] for i in items)
    # annotation v0: never auto-applied (payload contract via merge/build)
    payload = build_lessons_payload(topology=topo, events=[], run=None)
    assert payload["auto_applied"] is False
    assert all(i.get("auto_applied") is False for i in payload["lessons"])
    assert any(i["node_id"] == "platform-doubao" for i in payload["lessons"])


def test_lessons_from_run_planned_platforms():
    run = {
        "id": "r1",
        "status": "completed",
        "input_scope": {
            "recipe_name": "三平台",
            "flow_plan": {
                "planned_platforms": ["deepseek", "kimi", "hunyuan"],
                "steps": [
                    {
                        "node_id": "platform-doubao",
                        "status": "skipped",
                        "label": "豆包",
                        "skip_reason": "拓扑未连接",
                    }
                ],
            },
        },
    }
    items = lessons_from_run(run)
    assert any(i["node_id"] == "platform-doubao" for i in items)
    assert any("三平台" in i["headline"] for i in items)


def test_build_payload_empty_safe():
    payload = build_lessons_payload(topology={}, events=[], run=None)
    assert payload["engine"] == "visible_v0"
    assert payload["auto_applied"] is False
    assert payload["lessons"] == []
