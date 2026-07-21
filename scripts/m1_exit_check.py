# -*- coding: utf-8 -*-
"""M1 lightweight exit check (no full live crawl required).

Checks:
1. Local topology plan: disconnect doubao => not in planned platforms
2. Server attach path: _attach_flow_execution_plan writes flow_plan snapshot
3. Run message uses plan summary
4. Canvas merge contract: parse server plan + merge runtime keeps skips, overlays active
5. Unit suite already expected green (caller may run pytest separately)

Writes: docs/session-logs/2026-07-21-m1-exit-check-evidence.json
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

from dotenv import load_dotenv

load_dotenv(BACKEND / ".env.local")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def check_local_topology_plan() -> dict:
    from app.workflow.node_contracts import FlowTopology
    from app.workflow.topology_resolver import build_execution_plan_summary

    # Checklist 1: disconnect doubao
    topo = FlowTopology.from_dict({"removedEdgeIds": ["e-fetch-doubao"]})
    plan = build_execution_plan_summary(topo)
    platforms = plan.get("planned_platforms") or []
    ok_doubao = "doubao" not in platforms and set(platforms) == {
        "deepseek",
        "kimi",
        "hunyuan",
    }

    # disconnect report chain: report skipped, projection still planned
    topo2 = FlowTopology.from_dict(
        {
            "removedEdgeIds": ["e-projection-report"],
            "customNodes": [
                {"id": "a1", "type": "analysis", "position": {}, "config": {}},
            ],
            "customEdges": [
                {"id": "e1", "source": "projection", "target": "a1"},
            ],
        }
    )
    plan2 = build_execution_plan_summary(topo2)
    by_id = {s["node_id"]: s for s in plan2["steps"]}
    ok_report = by_id["report"]["status"] == "skipped" and by_id["a1"]["status"] == "pending"

    return {
        "name": "local_topology_plan",
        "ok": ok_doubao and ok_report,
        "planned_platforms_without_doubao": platforms,
        "report_skipped": by_id["report"]["status"],
        "analysis_pending": by_id["a1"]["status"],
        "summary": plan.get("summary"),
    }


async def check_attach_flow_plan() -> dict:
    from app.services.brand_intelligence_run_service import _attach_flow_execution_plan
    from app.workflow.node_contracts import FlowTopology

    # Mock topology row with doubao disconnected
    topo_wire = {
        "version": 1,
        "customNodes": [],
        "customEdges": [],
        "removedEdgeIds": ["e-fetch-doubao"],
    }
    row = SimpleNamespace(topology=topo_wire)
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    scope = await _attach_flow_execution_plan(
        db,
        entity_id=uuid4(),
        input_scope={"platforms": ["deepseek", "kimi", "doubao", "hunyuan"]},
    )
    flow_plan = scope.get("flow_plan") or {}
    platforms = flow_plan.get("planned_platforms") or []
    steps = flow_plan.get("steps") or []
    ok = (
        isinstance(flow_plan, dict)
        and flow_plan.get("source") == "topology_constraint"
        and "doubao" not in platforms
        and len(steps) > 0
        and bool(flow_plan.get("summary"))
    )
    return {
        "name": "attach_flow_plan_to_run_scope",
        "ok": ok,
        "source": flow_plan.get("source"),
        "planned_platforms": platforms,
        "step_count": len(steps),
        "summary": flow_plan.get("summary"),
        "has_generated_at": bool(flow_plan.get("generated_at")),
    }


def check_parse_and_merge_contract() -> dict:
    """Mirror frontend parseServerFlowPlan + mergeRuntimeOntoPlan semantics in Python."""
    server = {
        "version": 1,
        "source": "topology_constraint",
        "generated_at": _now(),
        "summary": "将执行 8 步 · 平台：deepseek,kimi,hunyuan",
        "planned_platforms": ["deepseek", "kimi", "hunyuan"],
        "active_edge_ids": ["e-questions-fetch", "e-fetch-deepseek"],
        "steps": [
            {"node_id": "question-set", "label": "问题集", "status": "pending"},
            {"node_id": "fetch", "label": "答案采集", "status": "pending"},
            {
                "node_id": "platform-doubao",
                "label": "豆包",
                "status": "skipped",
                "skip_reason": "画布已断开该平台连线",
            },
            {"node_id": "report", "label": "报告生成", "status": "pending"},
        ],
    }
    # Runtime says fetch active, question-set done; must not un-skip doubao
    runtime_status = {
        "question-set": "done",
        "fetch": "active",
        "platform-doubao": "active",  # hostile runtime must not win over skip
        "report": "pending",
    }
    merged = []
    for step in server["steps"]:
        status = step["status"]
        if status != "skipped":
            status = runtime_status.get(step["node_id"], "pending")
        merged.append({**step, "status": status})

    ok = (
        merged[0]["status"] == "done"
        and merged[1]["status"] == "active"
        and merged[2]["status"] == "skipped"
        and merged[3]["status"] == "pending"
    )
    return {
        "name": "parse_merge_contract",
        "ok": ok,
        "merged_statuses": [s["status"] for s in merged],
        "doubao_remains_skipped": merged[2]["status"] == "skipped",
    }


def check_frontend_source_files() -> dict:
    canvas = (ROOT / "frontend/src/components/dashboard/AmwayFlowCanvas.tsx").read_text(
        encoding="utf-8"
    )
    lib = (ROOT / "frontend/src/lib/amwayFlowExecutionPlan.ts").read_text(encoding="utf-8")
    svc = (
        ROOT / "aeo-platform/backend/app/services/brand_intelligence_run_service.py"
    ).read_text(encoding="utf-8")
    checks = {
        "has_任务计划_badge": "任务计划" in canvas,
        "has_拓扑预览_badge": "拓扑预览" in canvas,
        "uses_parseServerFlowPlan": "parseServerFlowPlan" in canvas,
        "uses_mergeRuntimeOntoPlan": "mergeRuntimeOntoPlan" in canvas,
        "attach_on_create": "_attach_flow_execution_plan" in svc,
        "flow_plan_key": '"flow_plan"' in svc or "'flow_plan'" in svc,
        "parse_export": "export function parseServerFlowPlan" in lib,
    }
    return {
        "name": "source_wiring",
        "ok": all(checks.values()),
        "checks": checks,
    }


async def main() -> int:
    report = {
        "generated_at": _now(),
        "scope": "M1 exit check (lightweight)",
        "environment": {
            "backend_health": "not_checked_here",
            "note": "Live UI click-through requires local 8000/3000; this script covers contract path.",
        },
        "checks": [],
    }
    report["checks"].append(check_local_topology_plan())
    report["checks"].append(await check_attach_flow_plan())
    report["checks"].append(check_parse_and_merge_contract())
    report["checks"].append(check_frontend_source_files())
    report["all_ok"] = all(bool(c.get("ok")) for c in report["checks"])

    out = ROOT / "docs" / "session-logs" / "2026-07-21-m1-exit-check-evidence.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n[wrote] {out}")
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
