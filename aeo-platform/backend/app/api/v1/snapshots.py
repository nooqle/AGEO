"""Snapshot API endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import get_current_user
from app.services.snapshot_service import SnapshotService

router = APIRouter(tags=["snapshots"])


@router.get("/entities/{entity_id}/snapshots")
async def list_snapshots(
    entity_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict[str, Any]:
    """获取某品牌的所有快照列表（分页）。"""
    service = SnapshotService(db)
    return await service.list_snapshots(entity_id, page=page, page_size=page_size)


@router.get("/entities/{entity_id}/snapshots/latest")
async def get_latest_snapshot(
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict[str, Any]:
    """获取某品牌的最新快照。"""
    service = SnapshotService(db)
    result = await service.list_snapshots(entity_id, page=1, page_size=1)
    snapshots = result.get("snapshots", [])
    if not snapshots:
        raise HTTPException(status_code=404, detail="No snapshots found")
    return snapshots[0]


@router.get("/snapshots/{snapshot_id}")
async def get_snapshot_detail(
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict[str, Any]:
    """获取快照详情（含 raw_data）。"""
    service = SnapshotService(db)
    snapshot = await service.get_snapshot(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    result = SnapshotService._snapshot_to_dict(snapshot)
    result["raw_data"] = snapshot.raw_data
    return result


@router.get("/entities/{entity_id}/snapshots/compare")
async def compare_snapshots(
    entity_id: str,
    base: str = Query(..., description="基准快照 ID"),
    target: str = Query(..., description="对比目标快照 ID"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict[str, Any]:
    """对比两个快照，delta = target - base。"""
    service = SnapshotService(db)
    result = await service.compare_snapshots(base, target, entity_id=entity_id)
    if not result:
        raise HTTPException(status_code=404, detail="One or both snapshots not found")
    return result


@router.get("/entities/{entity_id}/snapshots/trend")
async def get_snapshot_trend(
    entity_id: str,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict[str, Any]:
    """获取 BWVS 趋势数据（时间序列）。"""
    service = SnapshotService(db)
    trend = await service.get_trend(entity_id, limit=limit)
    return {"trend": trend}
