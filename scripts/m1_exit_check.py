# -*- coding: utf-8 -*-
"""Reproducible M1/P0 gate checks (no hand-assembled evidence fields).

Only prints JSON produced by this process. Does not claim frontend tsc/pytest
counts it did not run.
"""

from __future__ import annotations

import asyncio
import json
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


async def main() -> int:
    from app.workflow.node_contracts import FlowTopology
    from app.workflow.topology_resolver import (
        branch_custom_executors,
        build_execution_plan_summary,
        validate_topology_document,
    )
    from app.workflow import nodes_a4
    from app.services.brand_intelligence_run_service import _attach_flow_execution_plan

    checks = []

    # 1) plan excludes doubao when edge removed
    plan = build_execution_plan_summary(
        FlowTopology.from_dict({"removedEdgeIds": ["e-fetch-doubao"]})
    )
    checks.append(
        {
            "name": "plan_excludes_doubao",
            "ok": "doubao" not in (plan.get("planned_platforms") or []),
            "planned_platforms": plan.get("planned_platforms"),
        }
    )

    # 2) A4 gate to build_request
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
            "name": "a4_build_request_excludes_doubao",
            "ok": isinstance(pf, list) and "doubao" not in pf,
            "platform_filter": pf,
        }
    )

    # 3) attach flow_plan
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
        db, entity_id=uuid4(), input_scope={"platforms": list(plan["planned_platforms"]) + ["doubao"]}
    )
    fp = scope.get("flow_plan") or {}
    checks.append(
        {
            "name": "attach_flow_plan",
            "ok": fp.get("source") == "topology_constraint"
            and "doubao" not in (fp.get("planned_platforms") or []),
            "summary": fp.get("summary"),
        }
    )

    # 4) ghost loop does not hang
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
            "name": "branch_ghost_loop_safe",
            "ok": [n.id for n in branch] == ["a1"],
        }
    )

    # 5) validate rejects self-loop
    try:
        validate_topology_document(
            {
                "customNodes": [
                    {"id": "a1", "type": "analysis", "position": {}, "config": {}}
                ],
                "customEdges": [{"id": "e", "source": "a1", "target": "a1"}],
            }
        )
        ok = False
    except ValueError:
        ok = True
    checks.append({"name": "validate_rejects_self_loop", "ok": ok})

    report = {
        "generated_at": _now(),
        "producer": "scripts/m1_exit_check.py",
        "checks": checks,
        "all_ok": all(bool(c.get("ok")) for c in checks),
    }
    out = ROOT / "docs" / "session-logs" / "2026-07-21-p0-p1-fix-evidence.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[wrote] {out}")
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
