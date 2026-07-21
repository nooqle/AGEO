# -*- coding: utf-8 -*-
"""P0 closure verifier for amwaychina 3b-1 (topology gate + real LLM custom nodes).

Does NOT start a full brand-intelligence run. Proves:
1. A4 platform gate: disconnected doubao never reaches build_request.platform_filter
2. Real LLM secondary analysis (use_llm=True) returns mode=llm with cards
3. Real LLM content draft returns mode=llm with non-empty draft
4. branch_custom_executors planning for projection -> analysis -> content

Usage (from aeo-platform/backend):
  python ../../scripts/p0_3b1_closure_verify.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "aeo-platform" / "backend"
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv

load_dotenv(BACKEND / ".env.local")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _projection() -> dict:
    return {
        "center_terms": ["\u5b89\u5229"],
        "sample_scope": {
            "valid_answer_count": 12,
            "valid_platform_names": ["kimi", "deepseek"],
            "requested_platforms": ["kimi", "deepseek", "doubao"],
        },
        "nodes": [
            {
                "node_id": "n1",
                "term": "\u7ebd\u5d14\u83b1",
                "track": "core",
                "answer_count": 8,
            },
            {
                "node_id": "n2",
                "term": "\u76d1\u7ba1\u98ce\u9669",
                "track": "risk",
                "entity_type": "\u76d1\u7ba1",
                "answer_count": 2,
            },
        ],
        "risk_map": {"risk_count": 1},
    }


async def verify_platform_gate() -> dict:
    from app.workflow import nodes_a4
    from app.workflow.node_contracts import FlowTopology

    topology = FlowTopology.from_dict({"removedEdgeIds": ["e-fetch-doubao"]})
    captured: dict = {}

    async def fake_load(entity_id):
        return topology

    def fake_build_request(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            auth_context=SimpleNamespace(context_key="auth"),
            run_context=SimpleNamespace(context_key="run"),
            platforms=(),
        )

    original_load = nodes_a4.load_flow_topology
    original_build = nodes_a4._AIO_ANSWER_FETCH_TOOL.build_request
    nodes_a4.load_flow_topology = fake_load  # type: ignore[assignment]
    nodes_a4._AIO_ANSWER_FETCH_TOOL.build_request = fake_build_request  # type: ignore
    try:
        command = await nodes_a4.a4_fetch_node(
            {
                "session_id": "p0-gate",
                "entity_id": "00000000-0000-0000-0000-000000000001",
                "questions": [],
                "fetch_mode": "fast",
            }
        )
    finally:
        nodes_a4.load_flow_topology = original_load  # type: ignore[assignment]
        nodes_a4._AIO_ANSWER_FETCH_TOOL.build_request = original_build  # type: ignore

    platform_filter = captured.get("platform_filter")
    ok = (
        isinstance(platform_filter, list)
        and "doubao" not in platform_filter
        and set(platform_filter) == {"deepseek", "kimi", "hunyuan"}
        and command.update.get("fetch_results") == []
    )
    return {
        "name": "platform_gate_a4_entry",
        "ok": ok,
        "platform_filter": platform_filter,
        "disabled_expected": ["doubao"],
        "progress_message": command.update.get("progress_message"),
    }


async def verify_real_llm_analysis() -> dict:
    from app.services.amway_flow_custom_node_service import run_analysis_node

    result = await run_analysis_node(
        projection=_projection(),
        report=None,
        config={
            "dimensions": ["platform", "entities", "risk"],
            "prompt": "\u8bf7\u7528\u4e2d\u6587\u7ed9\u51fa\u4e24\u6761\u53ef\u6267\u884c\u5efa\u8bae\uff0c\u4e0d\u7f16\u9020\u6570\u5b57\u3002",
        },
        use_llm=True,
    )
    cards = result.get("cards") or []
    ok = (
        result.get("mode") == "llm"
        and isinstance(cards, list)
        and len(cards) >= 1
        and all(isinstance(c.get("lines"), list) and c.get("lines") for c in cards)
    )
    return {
        "name": "real_llm_analysis",
        "ok": ok,
        "mode": result.get("mode"),
        "card_count": len(cards),
        "card_titles": [c.get("title") for c in cards][:6],
        "summary_preview": str(result.get("summary") or "")[:180],
        "fallback_reason": result.get("fallback_reason"),
    }


async def verify_real_llm_content() -> dict:
    from app.services.amway_flow_custom_node_service import run_content_node

    analysis = {
        "summary": "\u6838\u5fc3\u5b9e\u4f53\u7a33\u5b9a\uff0c\u98ce\u9669\u8f68\u6709\u76d1\u7ba1\u4fe1\u53f7\u3002",
        "cards": [
            {
                "title": "\u9ad8\u9891\u5b9e\u4f53",
                "lines": ["\u7ebd\u5d14\u83b1\u51fa\u73b0\u9891\u6b21\u9ad8"],
            }
        ],
        "mode": "llm",
    }
    result = await run_content_node(
        center_term="\u5b89\u5229",
        lexicon_entries=[
            {"canonical_name": "\u7ebd\u5d14\u83b1"},
            {"canonical_name": "\u96c5\u59ff"},
        ],
        analysis_result=analysis,
        config={
            "promptTemplate": (
                "\u4f60\u662f\u54c1\u724c\u5185\u5bb9\u7b56\u5212\u3002\u57fa\u4e8e {{centerTerm}} / "
                "{{entities}} / {{analysis}}\uff0c\u5199\u4e00\u6bb5 80\u5b57\u4ee5\u5185\u7684\u5408\u89c4\u79cd\u8349\u5fae\u535a\u6587\u6848\u3002"
            )
        },
        use_llm=True,
    )
    draft = str(result.get("draft") or "").strip()
    ok = result.get("mode") == "llm" and len(draft) >= 20
    return {
        "name": "real_llm_content",
        "ok": ok,
        "mode": result.get("mode"),
        "draft_len": len(draft),
        "draft_preview": draft[:200],
        "fallback_reason": result.get("fallback_reason"),
    }


def verify_branch_plan() -> dict:
    from app.workflow.node_contracts import FlowTopology
    from app.workflow.topology_resolver import branch_custom_executors

    topo = FlowTopology.from_dict(
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
    branch = branch_custom_executors(topo, "projection", mode="downstream")
    ids = [n.id for n in branch]
    ok = ids == ["a1", "c1"]
    return {
        "name": "branch_plan_projection_seed",
        "ok": ok,
        "ran_node_ids": ids,
    }


async def main() -> int:
    report: dict = {
        "generated_at": _now(),
        "scope": "P0 closure for blueprint 3b-1 (gate + real LLM custom nodes)",
        "checks": [],
    }
    # Gate (sync path via async)
    try:
        report["checks"].append(await verify_platform_gate())
    except Exception as exc:
        report["checks"].append(
            {
                "name": "platform_gate_a4_entry",
                "ok": False,
                "error": str(exc),
                "trace": traceback.format_exc()[-800:],
            }
        )

    try:
        report["checks"].append(verify_branch_plan())
    except Exception as exc:
        report["checks"].append(
            {
                "name": "branch_plan_projection_seed",
                "ok": False,
                "error": str(exc),
            }
        )

    try:
        report["checks"].append(await verify_real_llm_analysis())
    except Exception as exc:
        report["checks"].append(
            {
                "name": "real_llm_analysis",
                "ok": False,
                "error": str(exc),
                "trace": traceback.format_exc()[-800:],
            }
        )

    try:
        report["checks"].append(await verify_real_llm_content())
    except Exception as exc:
        report["checks"].append(
            {
                "name": "real_llm_content",
                "ok": False,
                "error": str(exc),
                "trace": traceback.format_exc()[-800:],
            }
        )

    report["all_ok"] = all(bool(c.get("ok")) for c in report["checks"])
    out_dir = ROOT / "docs" / "session-logs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "2026-07-21-p0-3b1-closure-evidence.json"
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n[wrote] {out_path}")
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
