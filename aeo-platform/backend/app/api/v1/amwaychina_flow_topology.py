"""Amwaychina flow topology APIs (3b/3c): plan, persist, patch, compile-nl."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.v1.amwaychina_common import iso, require_amway_entity
from app.models.flow_topology import FlowTopologyRecord

router = APIRouter(tags=["amwaychina"])

EMPTY_TOPOLOGY: dict[str, Any] = {
    "version": 1,
    "customNodes": [],
    "customEdges": [],
    "removedEdgeIds": [],
}


class FlowTopologyPayload(BaseModel):
    topology: dict[str, Any] = Field(default_factory=dict)
    # Optional optimistic-lock token: client's last seen row.version
    expected_version: int | None = None


def normalize_topology(raw: Any) -> dict[str, Any]:
    """Validate/normalize topology for persistence (P0-1).

    Drops garbage via FlowTopology parser, then enforces endpoint existence,
    no self-loops, DAG, and edge-count limits. Raises ValueError on invalid
    documents (callers map to HTTP 400).
    """
    from app.workflow.topology_resolver import validate_topology_document

    return validate_topology_document(raw if isinstance(raw, dict) else None)


@router.get("/entities/{entity_id}/flow-plan")
async def get_flow_plan(
    entity_id: str,
    platforms: str | None = Query(
        None,
        description="Comma-separated enabled platform ids; default = all canvas platforms",
    ),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """3b-2.1: project the deterministic execution plan from current topology."""
    entity = await require_amway_entity(db, current_user, entity_id)
    row = (
        await db.execute(
            select(FlowTopologyRecord).where(FlowTopologyRecord.entity_id == entity.id)
        )
    ).scalar_one_or_none()
    from app.workflow.node_contracts import FlowTopology
    from app.workflow.topology_resolver import (
        CANVAS_PLATFORM_IDS,
        build_execution_plan_summary,
    )

    topology = FlowTopology.from_dict(
        row.topology if row is not None and isinstance(row.topology, dict) else None
    )
    enabled = None
    if platforms:
        wanted = {p.strip() for p in platforms.split(",") if p.strip()}
        if not wanted:
            raise HTTPException(status_code=400, detail="platforms 参数不能为空")
        enabled = [p for p in CANVAS_PLATFORM_IDS if p in wanted]
        unknown = sorted(wanted - set(CANVAS_PLATFORM_IDS))
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"无效平台参数：{', '.join(unknown)}",
            )
        if not enabled:
            raise HTTPException(status_code=400, detail="无有效平台参数")
    plan = build_execution_plan_summary(topology, enabled_platforms=enabled)
    return {
        "plan": plan,
        "topology": normalize_topology(
            row.topology if row is not None and isinstance(row.topology, dict) else {}
        ),
    }


@router.get("/entities/{entity_id}/flow-topology")
async def get_flow_topology(
    entity_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entity = await require_amway_entity(db, current_user, entity_id)
    row = (
        await db.execute(
            select(FlowTopologyRecord).where(FlowTopologyRecord.entity_id == entity.id)
        )
    ).scalar_one_or_none()
    if row is None:
        return {"topology": dict(EMPTY_TOPOLOGY), "updated_at": None, "version": 0}
    try:
        topology = normalize_topology(row.topology)
    except ValueError:
        topology = dict(EMPTY_TOPOLOGY)
    return {
        "topology": topology,
        "updated_at": iso(row.updated_at),
        "version": int(row.version or 1),
    }


@router.put("/entities/{entity_id}/flow-topology")
async def put_flow_topology(
    entity_id: str,
    body: FlowTopologyPayload,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entity = await require_amway_entity(db, current_user, entity_id, manage=True)
    try:
        normalized = normalize_topology(body.topology)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    row = (
        await db.execute(
            select(FlowTopologyRecord).where(FlowTopologyRecord.entity_id == entity.id)
        )
    ).scalar_one_or_none()
    if row is None:
        if body.expected_version is not None and int(body.expected_version) != 0:
            raise HTTPException(
                status_code=409,
                detail="拓扑版本冲突：记录不存在或已被删除，请重新加载。",
            )
        try:
            row = FlowTopologyRecord(entity_id=entity.id, topology=normalized)
            db.add(row)
            await db.commit()
        except Exception as exc:
            await db.rollback()
            # Unique index race on concurrent first write
            logger = __import__("logging").getLogger(__name__)
            logger.warning("[flow-topology] concurrent create race: %s", exc)
            raise HTTPException(
                status_code=409,
                detail="拓扑正在被其他请求创建，请重试。",
            ) from exc
    else:
        if body.expected_version is not None and int(body.expected_version) != int(
            row.version or 1
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"拓扑版本冲突：期望 version={body.expected_version}，"
                    f"当前 version={row.version}。请重新加载后再保存。"
                ),
            )
        row.topology = normalized
        row.version = int(row.version or 1) + 1
        await db.commit()
    await db.refresh(row)
    return {
        "topology": normalized,
        "updated_at": iso(row.updated_at),
        "version": int(row.version or 1),
    }


class FlowTopologyPatchRequest(BaseModel):
    """3c-B: deterministic topology ops (intent_id XOR ops)."""

    intent_id: str | None = None
    ops: list[dict[str, Any]] | None = None
    # Client's last seen row.version; preview also rejects mismatch (stale base).
    expected_version: int | None = None


class FlowTopologyCompileNlRequest(BaseModel):
    """3c-C1/C2: natural language → ops (rule-first, optional LLM; no write)."""

    text: str = Field(..., min_length=1, max_length=500)
    expected_version: int | None = None
    # C2: when True, miss on rules falls through to stable-prompt LLM compile
    allow_llm: bool = True


def load_topology_row(db_result_row: Any) -> tuple[dict[str, Any], int]:
    """Return (topology_dict, version). Missing row → empty / version 0."""
    if db_result_row is None:
        return dict(EMPTY_TOPOLOGY), 0
    try:
        topology = normalize_topology(db_result_row.topology)
    except ValueError:
        topology = dict(EMPTY_TOPOLOGY)
    return topology, int(db_result_row.version or 1)


def build_patch_result(
    *,
    base_topology: dict[str, Any],
    base_version: int,
    body: FlowTopologyPatchRequest,
) -> dict[str, Any]:
    from app.workflow.node_contracts import FlowTopology
    from app.workflow.topology_patch import resolve_ops_payload, apply_topology_ops
    from app.workflow.topology_resolver import build_execution_plan_summary

    try:
        ops = resolve_ops_payload(
            intent_id=body.intent_id,
            ops=body.ops,
            base=base_topology,
        )
        proposed_raw, summary = apply_topology_ops(base_topology, ops)
        proposed = normalize_topology(proposed_raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    plan = build_execution_plan_summary(FlowTopology.from_dict(proposed))
    return {
        "base": {"topology": base_topology, "version": base_version},
        "proposed": {"topology": proposed},
        "ops": ops,
        "summary": summary,
        "plan": plan,
    }


@router.post("/entities/{entity_id}/flow-topology/preview-patch")
async def preview_flow_topology_patch(
    entity_id: str,
    body: FlowTopologyPatchRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """3c-B: dry-run topology ops; no write. Rejects stale expected_version."""
    entity = await require_amway_entity(db, current_user, entity_id)
    row = (
        await db.execute(
            select(FlowTopologyRecord).where(FlowTopologyRecord.entity_id == entity.id)
        )
    ).scalar_one_or_none()
    base_topology, base_version = load_topology_row(row)
    if body.expected_version is not None and int(body.expected_version) != base_version:
        raise HTTPException(
            status_code=409,
            detail=(
                f"拓扑版本冲突：期望 version={body.expected_version}，"
                f"当前 version={base_version}。请重新加载后再预览。"
            ),
        )
    return build_patch_result(
        base_topology=base_topology, base_version=base_version, body=body
    )


@router.post("/entities/{entity_id}/flow-topology/compile-nl")
async def compile_flow_topology_nl(
    entity_id: str,
    body: FlowTopologyCompileNlRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """3c-C1/C2: NL → ops → preview shape (no write).

    Rule compiler first; optional LLM with stable ``topology_ops_compiler`` prompt.
    """
    from app.workflow.topology_nl_llm import compile_nl_auto

    entity = await require_amway_entity(db, current_user, entity_id)
    row = (
        await db.execute(
            select(FlowTopologyRecord).where(FlowTopologyRecord.entity_id == entity.id)
        )
    ).scalar_one_or_none()
    base_topology, base_version = load_topology_row(row)
    if body.expected_version is not None and int(body.expected_version) != base_version:
        raise HTTPException(
            status_code=409,
            detail=(
                f"拓扑版本冲突：期望 version={body.expected_version}，"
                f"当前 version={base_version}。请重新加载后再编译。"
            ),
        )
    try:
        compiled = await compile_nl_auto(
            body.text,
            base_topology,
            allow_llm=bool(body.allow_llm),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = build_patch_result(
        base_topology=base_topology,
        base_version=base_version,
        body=FlowTopologyPatchRequest(ops=list(compiled.ops)),
    )
    return {
        **result,
        "compile": {
            "mode": compiled.mode,
            "matched": compiled.matched,
            "intent_id": compiled.intent_id,
            "confidence": compiled.confidence,
        },
    }


@router.post("/entities/{entity_id}/flow-topology/apply-patch")
async def apply_flow_topology_patch(
    entity_id: str,
    body: FlowTopologyPatchRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """3c-B: apply topology ops with optimistic lock, then persist."""
    entity = await require_amway_entity(db, current_user, entity_id, manage=True)
    if body.expected_version is None:
        raise HTTPException(
            status_code=400,
            detail="apply-patch 必须提供 expected_version",
        )
    row = (
        await db.execute(
            select(FlowTopologyRecord).where(FlowTopologyRecord.entity_id == entity.id)
        )
    ).scalar_one_or_none()
    base_topology, base_version = load_topology_row(row)
    if int(body.expected_version) != base_version:
        raise HTTPException(
            status_code=409,
            detail=(
                f"拓扑版本冲突：期望 version={body.expected_version}，"
                f"当前 version={base_version}。请重新加载后再应用。"
            ),
        )
    result = build_patch_result(
        base_topology=base_topology, base_version=base_version, body=body
    )
    normalized = result["proposed"]["topology"]

    if row is None:
        try:
            row = FlowTopologyRecord(entity_id=entity.id, topology=normalized)
            db.add(row)
            await db.commit()
        except Exception as exc:
            await db.rollback()
            raise HTTPException(
                status_code=409,
                detail="拓扑正在被其他请求创建，请重试。",
            ) from exc
    else:
        row.topology = normalized
        row.version = int(row.version or 1) + 1
        await db.commit()
    await db.refresh(row)
    return {
        **result,
        "topology": normalized,
        "version": int(row.version or 1),
        "updated_at": iso(row.updated_at),
    }


