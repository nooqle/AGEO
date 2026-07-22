"""Visible run/topology lessons for production-line nodes (Wave O annotation v0).

Synthesizes human-readable, dismissible-by-UI annotations from:
- current topology gates (removed e-fetch-* edges)
- recent orchestration events
- latest run input_scope.flow_plan

No silent topology mutation. No black-box learning.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand_intelligence_run import BrandIntelligenceRun
from app.models.flow_topology import FlowTopologyRecord
from app.services import flow_orchestration_event_service as orch_events
from app.workflow.topology_resolver import CANVAS_PLATFORM_IDS, platform_edge_id

# Canvas node ids (must match frontend AmwayFlowCanvas)
PLATFORM_NODE_PREFIX = "platform-"
NODE_FETCH = "fetch"
NODE_REPORT = "report"

PLATFORM_LABELS: dict[str, str] = {
    "deepseek": "DeepSeek",
    "kimi": "Kimi",
    "doubao": "豆包",
    "hunyuan": "腾讯元宝",
}


def _platform_label(platform: str) -> str:
    return PLATFORM_LABELS.get(platform, platform)


def lessons_from_topology(topology: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Platforms with fetch edge removed → skip lesson on platform node."""
    doc = topology if isinstance(topology, dict) else {}
    removed = {
        str(x)
        for x in (doc.get("removedEdgeIds") or [])
        if isinstance(x, str) and x.strip()
    }
    out: list[dict[str, Any]] = []
    skipped: list[str] = []
    for platform in CANVAS_PLATFORM_IDS:
        edge = platform_edge_id(platform)
        if edge not in removed:
            continue
        skipped.append(platform)
        label = _platform_label(platform)
        out.append(
            {
                "id": f"topology:skip:{platform}",
                "node_id": f"{PLATFORM_NODE_PREFIX}{platform}",
                "kind": "skipped_platform",
                "headline": f"当前生产线未连接{label}，运行将跳过该平台采集。",
                "source": "topology",
                "dismissible": True,
            }
        )
    if skipped:
        names = "、".join(_platform_label(p) for p in skipped)
        out.append(
            {
                "id": f"topology:fetch-skip:{','.join(skipped)}",
                "node_id": NODE_FETCH,
                "kind": "fetch_partial",
                "headline": f"答案采集将跳过：{names}（拓扑门控）。",
                "source": "topology",
                "dismissible": True,
            }
        )
    return out


def lessons_from_events(events: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Recent orchestration changes as soft lessons (newest first, de-duped)."""
    out: list[dict[str, Any]] = []
    seen_nodes: set[str] = set()
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        et = str(ev.get("event_type") or "")
        summary = str(ev.get("summary") or "").strip()
        if not summary:
            continue
        payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        node_id = NODE_FETCH
        kind = "orchestration"
        # Map common patch intents to nodes when payload carries platform
        platform = str(payload.get("platform") or "").strip()
        if platform in CANVAS_PLATFORM_IDS:
            node_id = f"{PLATFORM_NODE_PREFIX}{platform}"
        elif et in {"apply_recipe", "overwrite_recipe", "save_recipe"}:
            node_id = NODE_FETCH
            kind = "recipe_memory"
        elif et == "apply_patch":
            kind = "topology_change"
        if node_id in seen_nodes and kind == "orchestration":
            continue
        # Cap soft event lessons to avoid noise
        if len(out) >= 4:
            break
        lesson_id = f"event:{ev.get('id') or len(out)}"
        out.append(
            {
                "id": lesson_id,
                "node_id": node_id,
                "kind": kind,
                "headline": summary
                if summary.endswith("。")
                else f"{summary}（编排记录）",
                "source": "event",
                "dismissible": True,
            }
        )
        seen_nodes.add(node_id)
    return out


def lessons_from_run(run: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Latest run flow_plan + status → lessons."""
    if not isinstance(run, dict):
        return []
    out: list[dict[str, Any]] = []
    status = str(run.get("status") or "").lower()
    scope = run.get("input_scope") if isinstance(run.get("input_scope"), dict) else {}
    flow_plan = scope.get("flow_plan") if isinstance(scope.get("flow_plan"), dict) else {}

    planned = [
        str(p)
        for p in (flow_plan.get("planned_platforms") or [])
        if isinstance(p, str) and p.strip()
    ]
    if planned:
        planned_set = set(planned)
        skipped = [p for p in CANVAS_PLATFORM_IDS if p not in planned_set]
        for platform in skipped:
            out.append(
                {
                    "id": f"run:skip:{run.get('id')}:{platform}",
                    "node_id": f"{PLATFORM_NODE_PREFIX}{platform}",
                    "kind": "run_skipped_platform",
                    "headline": (
                        f"最近运行未采集{_platform_label(platform)}"
                        f"（计划平台：{','.join(_platform_label(p) for p in planned)}）。"
                    ),
                    "source": "last_run",
                    "dismissible": True,
                }
            )
        if skipped:
            out.append(
                {
                    "id": f"run:fetch:{run.get('id')}",
                    "node_id": NODE_FETCH,
                    "kind": "run_fetch_partial",
                    "headline": (
                        f"最近运行答案采集跳过："
                        f"{'、'.join(_platform_label(p) for p in skipped)}。"
                    ),
                    "source": "last_run",
                    "dismissible": True,
                }
            )

    # Plan steps with skip reasons
    steps = flow_plan.get("steps") if isinstance(flow_plan.get("steps"), list) else []
    for step in steps:
        if not isinstance(step, dict):
            continue
        if str(step.get("status") or "") != "skipped":
            continue
        node_id = str(step.get("node_id") or step.get("id") or "").strip()
        reason = str(step.get("skip_reason") or step.get("skipReason") or "").strip()
        label = str(step.get("label") or node_id or "步骤").strip()
        if not node_id:
            continue
        text = reason or f"{label} 在最近运行计划中被跳过。"
        out.append(
            {
                "id": f"run:step:{run.get('id')}:{node_id}",
                "node_id": node_id,
                "kind": "run_step_skipped",
                "headline": text if text.endswith("。") else f"{text}。",
                "source": "last_run",
                "dismissible": True,
            }
        )

    if status in {"failed", "error", "cancelled"}:
        out.append(
            {
                "id": f"run:status:{run.get('id')}",
                "node_id": NODE_REPORT,
                "kind": "run_failed",
                "headline": f"最近运行状态为「{status}」，请检查报告/采集结果后再跑。",
                "source": "last_run",
                "dismissible": True,
            }
        )

    recipe_name = str(scope.get("recipe_name") or "").strip()
    if recipe_name and status == "completed":
        out.append(
            {
                "id": f"run:recipe:{run.get('id')}",
                "node_id": NODE_FETCH,
                "kind": "run_recipe",
                "headline": f"最近成功运行基于配方「{recipe_name}」。",
                "source": "last_run",
                "dismissible": True,
            }
        )
    return out


def merge_lessons(*groups: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    """Prefer topology + last_run over soft events; de-dupe by node_id+kind."""
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for group in groups:
        for item in group:
            if not isinstance(item, dict):
                continue
            key = f"{item.get('node_id')}:{item.get('kind')}"
            if key in seen:
                continue
            seen.add(key)
            # Never auto-apply topology mutations from lessons (annotation v0).
            merged.append({**item, "auto_applied": False})
            if len(merged) >= limit:
                return merged
    return merged


def build_lessons_payload(
    *,
    topology: dict[str, Any] | None,
    events: list[dict[str, Any]] | None,
    run: dict[str, Any] | None,
) -> dict[str, Any]:
    lessons = merge_lessons(
        lessons_from_topology(topology),
        lessons_from_run(run),
        lessons_from_events(events),
    )
    return {
        "lessons": lessons,
        "engine": "visible_v0",
        "auto_applied": False,
    }


async def load_lessons_for_entity(
    db: AsyncSession,
    *,
    entity_id: UUID,
) -> dict[str, Any]:
    topo_row = (
        await db.execute(
            select(FlowTopologyRecord).where(FlowTopologyRecord.entity_id == entity_id)
        )
    ).scalar_one_or_none()
    topology = (
        topo_row.topology
        if topo_row is not None and isinstance(topo_row.topology, dict)
        else {}
    )

    event_rows = await orch_events.list_events(db, entity_id=entity_id, limit=15)
    events = [orch_events.event_to_dict(e) for e in event_rows]

    run_row = (
        await db.execute(
            select(BrandIntelligenceRun)
            .where(BrandIntelligenceRun.entity_id == entity_id)
            .order_by(desc(BrandIntelligenceRun.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    run_dict: dict[str, Any] | None = None
    if run_row is not None:
        run_dict = {
            "id": str(run_row.id),
            "status": run_row.status,
            "input_scope": run_row.input_scope
            if isinstance(run_row.input_scope, dict)
            else {},
        }

    return build_lessons_payload(topology=topology, events=events, run=run_dict)
