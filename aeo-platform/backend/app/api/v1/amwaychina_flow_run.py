"""Amwaychina custom node / branch run APIs (blueprint 3b-1.5 / 3b-1.6)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.v1.amwaychina_common import (
    load_projection_body,
    require_amway_entity,
)
from app.api.v1.amwaychina_flow_topology import normalize_topology
from app.models.flow_topology import FlowTopologyRecord
from app.services.amway_circle_tracking_service import AmwayCircleTrackingService
from app.services.amway_entity_lexicon_service import AmwayEntityLexiconService

router = APIRouter(tags=["amwaychina"])

class FlowNodeRunRequest(BaseModel):
    """Optional config overrides for a single custom-node run (3b-1.5)."""

    dimensions: list[str] | None = None
    prompt: str | None = None
    promptTemplate: str | None = None
    use_llm: bool = True
    # 3b-1.6: after this node, also run reachable downstream custom executors
    cascade: bool = False


class FlowBranchRunRequest(BaseModel):
    """Partial topology branch run (blueprint 3b-1.6)."""

    from_node_id: str
    mode: str = "downstream"  # node_only | downstream
    use_llm: bool = True


@router.post("/entities/{entity_id}/flow-nodes/{node_id}/run")
async def run_flow_custom_node(
    entity_id: str,
    node_id: str,
    body: FlowNodeRunRequest | None = None,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """On-demand execution of one analysis/content custom node.

    Loads latest cumulative projection + lexicon + any upstream analysis
    results already stored on the topology. Writes ``config.result`` back to
    the topology document (dual-write with the frontend response).
    """
    entity = await require_amway_entity(db, current_user, entity_id, manage=True)
    body = body or FlowNodeRunRequest()

    row = (
        await db.execute(
            select(FlowTopologyRecord).where(FlowTopologyRecord.entity_id == entity.id)
        )
    ).scalar_one_or_none()
    topology_raw = (
        row.topology if row is not None and isinstance(row.topology, dict) else {}
    )
    from app.workflow.node_contracts import FlowTopology

    topology = FlowTopology.from_dict(topology_raw)
    target = next((n for n in topology.custom_nodes if n.id == node_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="自定义节点不存在")
    if target.type not in {"analysis", "content"}:
        raise HTTPException(status_code=400, detail="该节点类型不支持独立运行")

    config = dict(target.config or {})
    if body.dimensions is not None:
        config["dimensions"] = body.dimensions
    if body.prompt is not None:
        config["prompt"] = body.prompt
    if body.promptTemplate is not None:
        config["promptTemplate"] = body.promptTemplate

    tracking = AmwayCircleTrackingService(db)
    projection_payload = await tracking.get_projection(entity.id, scope="cumulative")
    projection = load_projection_body(projection_payload)

    from app.services.amway_flow_custom_node_service import (
        persist_custom_node_results,
        run_analysis_node,
        run_content_node,
        run_custom_branch,
    )

    def _topology_with_patches(patches: dict[str, dict[str, Any]]) -> dict[str, Any]:
        nodes_out = []
        for n in topology.custom_nodes:
            cfg = dict(n.config or {})
            if n.id in patches:
                cfg.update(patches[n.id])
            nodes_out.append(
                {
                    "id": n.id,
                    "type": n.type,
                    "position": n.position,
                    "config": cfg,
                }
            )
        return normalize_topology(
            {
                "version": topology.version,
                "customNodes": nodes_out,
                "customEdges": [
                    {"id": e.id, "source": e.source, "target": e.target}
                    for e in topology.custom_edges
                ],
                "removedEdgeIds": list(topology.removed_edge_ids),
            }
        )

    if target.type == "analysis" and body.cascade:
        if not projection:
            raise HTTPException(
                status_code=400,
                detail="暂无可用圈层投影，请先完成至少一轮采集。",
            )
        # Apply config overrides onto the start node before branch run
        from dataclasses import replace
        from app.workflow.node_contracts import TopologyNode

        overridden = []
        for n in topology.custom_nodes:
            if n.id == node_id:
                overridden.append(
                    TopologyNode(
                        id=n.id,
                        type=n.type,
                        position=dict(n.position or {}),
                        config=config,
                    )
                )
            else:
                overridden.append(n)
        topology = replace(topology, custom_nodes=tuple(overridden))
        lexicon_payload = await AmwayEntityLexiconService(db).payload_for_entity(
            entity.id
        )
        center_terms = list((projection or {}).get("center_terms") or [])
        center_term = str(
            getattr(entity, "name", None)
            or (center_terms[0] if center_terms else "")
            or "品牌"
        )
        branch_result = await run_custom_branch(
            topology=topology,
            from_node_id=node_id,
            mode="downstream",
            projection=projection,
            report=None,
            lexicon_entries=list(lexicon_payload.get("entries") or []),
            center_term=center_term,
            use_llm=bool(body.use_llm),
        )
        patches = branch_result.get("config_patches") or {}
        if patches:
            await persist_custom_node_results(entity.id, patches)
        if row is not None:
            await db.refresh(row)
            topology_out = normalize_topology(row.topology)
        else:
            topology_out = _topology_with_patches(patches)
        primary = (branch_result.get("results") or {}).get(node_id) or {}
        return {
            "node_id": node_id,
            "node_type": "analysis",
            "result": primary,
            "ran_node_ids": branch_result.get("ran_node_ids") or [],
            "topology": topology_out,
        }

    if target.type == "analysis":
        if not projection:
            raise HTTPException(
                status_code=400,
                detail="暂无可用圈层投影，请先完成至少一轮采集。",
            )
        result = await run_analysis_node(
            projection=projection,
            report=None,
            config=config,
            use_llm=bool(body.use_llm),
        )
        result_patch = {
            "result": result,
            "dimensions": result.get("dimensions"),
        }
        await persist_custom_node_results(entity.id, {node_id: result_patch})
        if row is not None:
            await db.refresh(row)
            topology_out = normalize_topology(row.topology)
        else:
            topology_out = _topology_with_patches({node_id: result_patch})
        return {
            "node_id": node_id,
            "node_type": "analysis",
            "result": result,
            "topology": topology_out,
        }

    # content
    lexicon_payload = await AmwayEntityLexiconService(db).payload_for_entity(entity.id)
    lexicon_entries = list(lexicon_payload.get("entries") or [])
    # P2-10: prefer analysis results from wired upstream edges only
    from app.workflow.topology_resolver import custom_incoming_sources

    analysis_result = None
    sources = custom_incoming_sources(topology, node_id)
    analysis_by_id = {
        n.id: (n.config or {}).get("result")
        for n in topology.custom_nodes
        if n.type == "analysis"
    }
    for source in sources:
        stored = analysis_by_id.get(source)
        if isinstance(stored, dict) and stored.get("cards"):
            analysis_result = stored
            break
    if analysis_result is None and "lexicon" in sources:
        # lexicon-only content nodes may still use any analysis as soft context
        for stored in analysis_by_id.values():
            if isinstance(stored, dict) and stored.get("cards"):
                analysis_result = stored
                break
    center_terms = []
    if isinstance(projection, dict):
        center_terms = list(projection.get("center_terms") or [])
    center_term = str(
        getattr(entity, "name", None)
        or (center_terms[0] if center_terms else "")
        or (projection or {}).get("center_term")
        or "品牌"
    )
    result = await run_content_node(
        center_term=center_term,
        lexicon_entries=lexicon_entries,
        analysis_result=analysis_result,
        config=config,
        use_llm=bool(body.use_llm),
    )
    result_patch = {"result": result}
    await persist_custom_node_results(entity.id, {node_id: result_patch})
    if row is not None:
        await db.refresh(row)
        topology_out = normalize_topology(row.topology)
    else:
        topology_out = _topology_with_patches({node_id: result_patch})
    return {
        "node_id": node_id,
        "node_type": "content",
        "result": result,
        "topology": topology_out,
    }

@router.post("/entities/{entity_id}/flow-branch/run")
async def run_flow_branch(
    entity_id: str,
    body: FlowBranchRunRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run a partial branch of the canvas topology (3b-1.6).

    ``from_node_id`` may be a custom analysis/content node or a builtin seed
    (``projection`` / ``report`` / ``lexicon``). Builtin executors themselves
    are not re-run — only reachable custom analysis/content nodes, using the
    latest cumulative projection + lexicon as inputs.
    """
    entity = await require_amway_entity(db, current_user, entity_id, manage=True)
    from_node_id = str(body.from_node_id or "").strip()
    if not from_node_id:
        raise HTTPException(status_code=400, detail="from_node_id 不能为空")
    mode = str(body.mode or "downstream").strip().lower()
    if mode not in {"node_only", "downstream"}:
        raise HTTPException(status_code=400, detail="mode 必须是 node_only 或 downstream")

    row = (
        await db.execute(
            select(FlowTopologyRecord).where(FlowTopologyRecord.entity_id == entity.id)
        )
    ).scalar_one_or_none()
    topology_raw = (
        row.topology if row is not None and isinstance(row.topology, dict) else {}
    )
    from app.workflow.node_contracts import FlowTopology
    from app.workflow.topology_resolver import (
        BRANCH_SEED_NODE_IDS,
        branch_custom_executors,
    )

    topology = FlowTopology.from_dict(topology_raw)
    custom_ids = {n.id for n in topology.custom_nodes}
    if from_node_id not in custom_ids and from_node_id not in BRANCH_SEED_NODE_IDS:
        raise HTTPException(
            status_code=404,
            detail="起点节点不存在（需为自定义节点或 projection/report/lexicon）",
        )

    planned = branch_custom_executors(topology, from_node_id, mode=mode)
    if not planned:
        raise HTTPException(
            status_code=400,
            detail="该起点没有可执行的自定义节点分支（请先连线并添加分析/内容节点）",
        )

    # Analysis branch needs projection data.
    needs_projection = any(n.type == "analysis" for n in planned)
    tracking = AmwayCircleTrackingService(db)
    projection_payload = await tracking.get_projection(entity.id, scope="cumulative")
    projection = load_projection_body(projection_payload)
    if needs_projection and not projection:
        raise HTTPException(
            status_code=400,
            detail="暂无可用圈层投影，请先完成至少一轮采集。",
        )

    lexicon_payload = await AmwayEntityLexiconService(db).payload_for_entity(entity.id)
    lexicon_entries = list(lexicon_payload.get("entries") or [])
    center_terms = list((projection or {}).get("center_terms") or [])
    center_term = str(
        getattr(entity, "name", None)
        or (center_terms[0] if center_terms else "")
        or (projection or {}).get("center_term")
        or "品牌"
    )

    from app.services.amway_flow_custom_node_service import (
        persist_custom_node_results,
        run_custom_branch,
    )

    branch_result = await run_custom_branch(
        topology=topology,
        from_node_id=from_node_id,
        mode=mode,
        projection=projection,
        report=None,
        lexicon_entries=lexicon_entries,
        center_term=center_term,
        use_llm=bool(body.use_llm),
    )
    patches = branch_result.get("config_patches") or {}
    if patches:
        await persist_custom_node_results(entity.id, patches)

    if row is not None:
        await db.refresh(row)
        topology_out = normalize_topology(row.topology)
    else:
        nodes_out = []
        for n in topology.custom_nodes:
            cfg = dict(n.config or {})
            if n.id in patches:
                cfg.update(patches[n.id])
            nodes_out.append(
                {
                    "id": n.id,
                    "type": n.type,
                    "position": n.position,
                    "config": cfg,
                }
            )
        topology_out = normalize_topology(
            {
                "version": topology.version,
                "customNodes": nodes_out,
                "customEdges": [
                    {"id": e.id, "source": e.source, "target": e.target}
                    for e in topology.custom_edges
                ],
                "removedEdgeIds": list(topology.removed_edge_ids),
            }
        )

    return {
        "from_node_id": from_node_id,
        "mode": mode,
        "ran_node_ids": branch_result.get("ran_node_ids") or [],
        "results": branch_result.get("results") or {},
        "topology": topology_out,
    }

