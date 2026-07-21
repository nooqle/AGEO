# -*- coding: utf-8 -*-
"""Full verification against docs/review-3b1-3b2-blueprint-2026-07-21.md P0-P1 (+ key P2).

Produces: docs/session-logs/2026-07-21-review-closure-verify.json
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "aeo-platform" / "backend"
sys.path.insert(0, str(BACKEND))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def verify_p0_p1() -> list[dict]:
    from app.workflow.node_contracts import FlowTopology, get_contract, output_type_of
    from app.workflow.topology_resolver import (
        branch_custom_executors,
        build_execution_plan_summary,
        load_flow_topology,
        validate_topology_document,
    )
    from app.workflow import nodes_a4, nodes_amway
    from app.services.brand_intelligence_run_service import _attach_flow_execution_plan
    from app.workflow.orchestrator_context_packets import (
        build_dashboard_context_packet,
        render_dashboard_context_packet,
    )
    from app.workflow.orchestrator_node import TOOL_TO_NODE

    checks: list[dict] = []

    # P0-1 BFS + validate
    topo = FlowTopology.from_dict(
        {
            "customNodes": [
                {"id": "a1", "type": "analysis", "position": {}, "config": {}}
            ],
            "customEdges": [
                {"id": "e1", "source": "projection", "target": "a1"},
                {"id": "eg", "source": "ghost", "target": "ghost"},
            ],
        }
    )
    branch = branch_custom_executors(topo, "projection", mode="downstream")
    checks.append(
        {
            "id": "P0-1-bfs",
            "ok": [n.id for n in branch] == ["a1"],
            "detail": "ghost self-loop does not hang",
        }
    )
    try:
        validate_topology_document(
            {
                "customNodes": [
                    {"id": "a1", "type": "analysis", "position": {}, "config": {}}
                ],
                "customEdges": [{"id": "e", "source": "a1", "target": "a1"}],
            }
        )
        ok_val = False
    except ValueError:
        ok_val = True
    checks.append({"id": "P0-1-validate", "ok": ok_val, "detail": "self-loop rejected"})

    # P0-2 UUID load degrade on invalid
    empty = await load_flow_topology("not-uuid")
    checks.append(
        {
            "id": "P0-2-invalid-uuid",
            "ok": empty.removed_edge_ids == (),
            "detail": "invalid uuid degrades",
        }
    )

    # P0-3 a4 gate to build_request
    captured = {}

    async def _topo(_):
        return FlowTopology.from_dict({"removedEdgeIds": ["e-fetch-doubao"]})

    def _build(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            auth_context=SimpleNamespace(context_key="a"),
            run_context=SimpleNamespace(context_key="r"),
            platforms=tuple(kwargs.get("platform_filter") or ()),
        )

    nodes_a4.load_flow_topology = _topo  # type: ignore
    nodes_a4._AIO_ANSWER_FETCH_TOOL.build_request = _build  # type: ignore
    await nodes_a4.a4_fetch_node(
        {
            "session_id": "s",
            "entity_id": str(uuid4()),
            "questions": [],
            "fetch_mode": "fast",
        }
    )
    pf = captured.get("platform_filter")
    checks.append(
        {
            "id": "P0-3-a4-filter",
            "ok": isinstance(pf, list) and "doubao" not in pf,
            "platform_filter": pf,
        }
    )

    # P1-2 terminal status on all platforms off
    async def _all_off(_):
        return FlowTopology.from_dict(
            {
                "removedEdgeIds": [
                    "e-fetch-deepseek",
                    "e-fetch-kimi",
                    "e-fetch-doubao",
                    "e-fetch-hunyuan",
                ]
            }
        )

    nodes_a4.load_flow_topology = _all_off  # type: ignore
    cmd = await nodes_a4.a4_fetch_node(
        {
            "session_id": "s",
            "entity_id": str(uuid4()),
            "questions": [{"id": "q", "text": "t"}],
            "fetch_mode": "fast",
        }
    )
    checks.append(
        {
            "id": "P1-2-terminal",
            "ok": cmd.update.get("execution_status") == "completed"
            and cmd.update.get("next_required_action") is None,
        }
    )

    # P2-1 port type entity_graph
    checks.append(
        {
            "id": "P2-1-entity_graph",
            "ok": output_type_of("projection") == "entity_graph"
            and get_contract("report").inputs[0].type == "entity_graph",
        }
    )

    # P1-8 registry overlay
    checks.append(
        {
            "id": "P1-8-registry",
            "ok": TOOL_TO_NODE.get("amway_secondary_analysis") == "amway_analysis"
            and TOOL_TO_NODE.get("amway_content_draft") == "amway_content",
        }
    )

    # flow plan in context
    pkt = build_dashboard_context_packet(
        {
            "dashboard_context": {
                "entry_source": "brand_intelligence_run",
                "flow_plan": {
                    "source": "topology_constraint",
                    "summary": "将执行 7 步 · 平台：kimi",
                    "planned_platforms": ["kimi"],
                    "steps": [
                        {
                            "node_id": "platform-doubao",
                            "label": "豆包",
                            "status": "skipped",
                            "skip_reason": "画布已断开该平台连线",
                        }
                    ],
                },
            }
        }
    )
    rendered = render_dashboard_context_packet(pkt)
    checks.append(
        {
            "id": "P2-context-flow-plan",
            "ok": "画布拓扑执行计划" in rendered and "豆包" in rendered,
        }
    )

    # attach plan
    row = SimpleNamespace(
        topology={
            "version": 1,
            "customNodes": [],
            "customEdges": [],
            "removedEdgeIds": ["e-fetch-doubao"],
        }
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    scope = await _attach_flow_execution_plan(
        db,
        entity_id=uuid4(),
        input_scope={"platforms": ["deepseek", "kimi", "doubao", "hunyuan"]},
    )
    fp = scope.get("flow_plan") or {}
    checks.append(
        {
            "id": "attach-flow-plan",
            "ok": "doubao" not in (fp.get("planned_platforms") or []),
        }
    )

    plan = build_execution_plan_summary(
        FlowTopology.from_dict({"removedEdgeIds": ["e-fetch-doubao"]})
    )
    checks.append(
        {
            "id": "plan-no-doubao",
            "ok": "doubao" not in (plan.get("planned_platforms") or []),
        }
    )

    return checks


def run_pytest_suite() -> dict:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "run_3b1_suite.py"),
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    # parse "N passed"
    import re

    m = re.search(r"(\d+) passed", out)
    return {
        "id": "pytest-3b1-suite",
        "ok": proc.returncode == 0,
        "passed": int(m.group(1)) if m else None,
        "returncode": proc.returncode,
        "tail": out[-500:],
    }


async def main() -> int:
    checks = await verify_p0_p1()
    suite = run_pytest_suite()
    checks.append(suite)

    # Static review checklist mapping
    checklist = {
        "P0-1": any(c["id"].startswith("P0-1") and c["ok"] for c in checks),
        "P0-2": any(c["id"].startswith("P0-2") and c["ok"] for c in checks),
        "P0-3": any(c["id"].startswith("P0-3") and c["ok"] for c in checks),
        "P0-4": True,  # this script is the reproducible producer
        "P1-1/2": any(c["id"] == "P1-2-terminal" and c["ok"] for c in checks),
        "P1-8": any(c["id"] == "P1-8-registry" and c["ok"] for c in checks),
        "P2-1": any(c["id"] == "P2-1-entity_graph" and c["ok"] for c in checks),
        "suite": suite["ok"],
    }
    report = {
        "generated_at": _now(),
        "producer": "scripts/review_p0_p1_p2_verify.py",
        "review_doc": "docs/review-3b1-3b2-blueprint-2026-07-21.md",
        "checks": checks,
        "checklist_summary": checklist,
        "all_ok": all(bool(c.get("ok")) for c in checks),
        "verdict": (
            "PASS"
            if all(bool(c.get("ok")) for c in checks)
            else "FAIL"
        ),
    }
    out = ROOT / "docs" / "session-logs" / "2026-07-21-review-closure-verify.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[wrote] {out}")
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
