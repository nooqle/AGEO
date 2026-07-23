"""Wave P: visible calibration memory pure helpers."""

from __future__ import annotations

from app.services.flow_calibration_memory import (
    build_visible_memory_block,
    lesson_alignment_for_recipe,
    ops_preview,
    platforms_touched_from_ops,
)
from app.api.v1.amwaychina_flow_topology import EMPTY_TOPOLOGY


def test_lesson_alignment_skip_doubao():
    lessons = [
        {
            "node_id": "platform-doubao",
            "kind": "skipped_platform",
            "headline": "当前生产线未连接豆包，运行将跳过该平台采集。",
            "source": "topology",
        }
    ]
    pts, reasons = lesson_alignment_for_recipe(
        recipe_topology={**EMPTY_TOPOLOGY, "removedEdgeIds": ["e-fetch-doubao"]},
        lessons=lessons,
    )
    assert pts > 0
    assert any("豆包" in r for r in reasons)


def test_visible_memory_block_caps():
    events = [{"summary": f"变更{i}"} for i in range(10)]
    lessons = [
        {"headline": f"教训{i}，跳过某平台。", "source": "topology"} for i in range(8)
    ]
    block = build_visible_memory_block(events=events, lessons=lessons)
    assert len(block["recent_changes"]) <= 5
    assert len(block["lessons"]) <= 4
    assert "Hint only" in block["note"]


def test_ops_preview_and_platforms():
    ops = [
        {"op": "disable_platform", "platform": "doubao"},
        {"op": "enable_platform", "platform": "kimi"},
    ]
    assert platforms_touched_from_ops(ops) == ["doubao", "kimi"]
    prev = ops_preview(ops)
    assert prev[0]["op"] == "disable_platform"
