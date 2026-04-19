"""Monitoring Schedule API endpoints."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.snapshot import AnalysisSnapshot
from app.models.monitoring_schedule import ScheduleFrequency, ScheduleStatus
from app.services.entity_service import EntityService
from app.services.monitoring_service import MonitoringService
from app.services.access_scope_service import AccessScopeService
from app.services.task_service import task_to_dict

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


# =========================================================================
# Request / Response Schemas
# =========================================================================


class CreateScheduleRequest(BaseModel):
    """Request body for creating a monitoring schedule."""

    entity_id: str
    frequency: str = "weekly"
    preferred_hour: int = Field(default=3, ge=0, le=23)
    timezone: str = "Asia/Shanghai"
    status: str = "active"
    platforms: list[str] | None = None
    alert_on_significant_change: bool = True
    alert_threshold_bwvs: float = 10.0
    max_runs: int | None = None


class UpdateScheduleRequest(BaseModel):
    """Request body for updating a monitoring schedule."""

    frequency: str | None = None
    preferred_hour: int | None = Field(default=None, ge=0, le=23)
    timezone: str | None = None
    status: str | None = None
    platforms: list[str] | None = None
    alert_on_significant_change: bool | None = None
    alert_threshold_bwvs: float | None = None


def _parse_uuid(value: str, field_name: str = "id") -> UUID:
    """Parse a string as UUID, raising 400 on invalid format."""
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UUID for {field_name}: {value}",
        )


def _parse_schedule_status(value: str) -> ScheduleStatus:
    try:
        parsed = ScheduleStatus(value)
    except ValueError:
        parsed = None
    if parsed not in {ScheduleStatus.ACTIVE, ScheduleStatus.PAUSED}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status: {value}. Must be one of: active, paused",
        )
    return parsed


def schedule_to_dict(schedule) -> dict[str, Any]:
    """Convert MonitoringSchedule to API-friendly dict.

    Requires entity relationship to be eager-loaded for entity_name.
    """
    # Safely extract entity_name from eager-loaded relationship
    entity_name = None
    try:
        if schedule.entity is not None:
            entity_name = schedule.entity.name
    except Exception:
        pass

    # Baseline summary (don't send full baseline_data in list views)
    baseline = schedule.baseline_data
    has_baseline = baseline is not None and bool(baseline.get("questions"))
    baseline_summary = None
    if has_baseline:
        baseline_summary = {
            "question_count": len(baseline.get("questions", [])),
            "saved_at": baseline.get("saved_at"),
            "source_task_id": baseline.get("source_task_id"),
        }

    normalized_platforms: list[str] = []
    for raw_platform in schedule.platforms or []:
        platform = str(raw_platform).strip().lower()
        platform = MonitoringService.MONITORING_PLATFORM_ALIASES.get(platform, platform)
        if platform in MonitoringService.SUPPORTED_PLATFORM_SET:
            if platform not in normalized_platforms:
                normalized_platforms.append(platform)
            continue
        if platform:
            logger.warning(
                "[MonitoringAPI] Dropping unsupported schedule platform '%s' from response for schedule %s",
                raw_platform,
                schedule.id,
            )

    return {
        "id": str(schedule.id),
        "user_id": str(schedule.user_id),
        "entity_id": str(schedule.entity_id),
        "entity_name": entity_name,
        "frequency": schedule.frequency.value if schedule.frequency else "weekly",
        "status": schedule.status.value if schedule.status else "active",
        "preferred_hour": schedule.preferred_hour,
        "timezone": schedule.timezone,
        "platforms": normalized_platforms or None,
        "alert_on_significant_change": schedule.alert_on_significant_change,
        "alert_threshold_bwvs": schedule.alert_threshold_bwvs,
        "has_baseline": has_baseline,
        "baseline_summary": baseline_summary,
        "next_run_at": (
            schedule.next_run_at.isoformat() if schedule.next_run_at else None
        ),
        "last_run_at": (
            schedule.last_run_at.isoformat() if schedule.last_run_at else None
        ),
        "last_task_id": (str(schedule.last_task_id) if schedule.last_task_id else None),
        "total_runs": schedule.total_runs,
        "consecutive_failures": schedule.consecutive_failures,
        "max_failures": schedule.max_failures,
        "max_runs": schedule.max_runs,
        "end_date": (schedule.end_date.isoformat() if schedule.end_date else None),
        "created_at": (
            schedule.created_at.isoformat() if schedule.created_at else None
        ),
        "updated_at": (
            schedule.updated_at.isoformat() if schedule.updated_at else None
        ),
    }


# =========================================================================
# Endpoints
# =========================================================================


@router.post("/schedules")
async def create_schedule(
    body: CreateScheduleRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new monitoring schedule."""
    entity_id = _parse_uuid(body.entity_id, "entity_id")
    entity_service = EntityService(db)
    entity = await entity_service.get_entity(str(entity_id), current_user)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found",
        )
    entity_model = await entity_service.get_entity_model(str(entity_id), current_user)
    if not AccessScopeService.can_manage_entity(entity_model, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅品牌创建者或内部管理员可创建监测计划",
        )

    try:
        freq = ScheduleFrequency(body.frequency)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid frequency: {body.frequency}. "
            f"Must be one of: daily, weekly, biweekly, monthly",
        )
    sched_status = _parse_schedule_status(body.status)

    service = MonitoringService(db)
    try:
        schedule = await service.create_schedule(
            user_id=current_user.id,
            entity_id=entity_id,
            frequency=freq,
            preferred_hour=body.preferred_hour,
            timezone_str=body.timezone,
            status=sched_status,
            platforms=body.platforms,
            alert_on_significant_change=body.alert_on_significant_change,
            alert_threshold_bwvs=body.alert_threshold_bwvs,
            max_runs=body.max_runs,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return {"schedule": schedule_to_dict(schedule)}


@router.get("/schedules")
async def list_schedules(
    entity_id: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List monitoring schedules for the current user."""
    eid = _parse_uuid(entity_id, "entity_id") if entity_id else None
    sched_status = None
    if status_filter:
        try:
            sched_status = ScheduleStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}",
            )

    service = MonitoringService(db)
    schedules, total = await service.list_schedules_for_viewer(
        viewer=current_user,
        entity_id=eid,
        status=sched_status,
        limit=limit,
        offset=offset,
    )
    return {
        "schedules": [schedule_to_dict(s) for s in schedules],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/schedules/entity/{entity_id}")
async def get_schedules_by_entity(
    entity_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get monitoring schedules for a specific entity.

    Returns all schedules (any status) for the given entity owned by
    the current user. Frontend uses this to display schedule info on
    the entity detail page.
    """
    eid = _parse_uuid(entity_id, "entity_id")
    entity_service = EntityService(db)
    entity = await entity_service.get_entity(str(eid), current_user)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found",
        )
    service = MonitoringService(db)
    schedules, total = await service.list_schedules_for_viewer(
        viewer=current_user,
        entity_id=eid,
        limit=100,
        offset=0,
    )
    return {
        "schedules": [schedule_to_dict(s) for s in schedules],
        "total": total,
    }


@router.get("/schedules/{schedule_id}")
async def get_schedule(
    schedule_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a monitoring schedule by ID."""
    sid = _parse_uuid(schedule_id, "schedule_id")
    service = MonitoringService(db)
    schedule = await service.get_schedule_for_viewer(sid, current_user)
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )
    return {"schedule": schedule_to_dict(schedule)}


@router.put("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: str,
    body: UpdateScheduleRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a monitoring schedule."""
    sid = _parse_uuid(schedule_id, "schedule_id")

    service = MonitoringService(db)
    schedule = await service.get_schedule(sid)
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )
    if not AccessScopeService.can_manage_schedule(schedule, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅计划创建者或内部管理员可修改监测计划",
        )

    update_kwargs: dict[str, Any] = {}
    if body.frequency is not None:
        try:
            update_kwargs["frequency"] = ScheduleFrequency(body.frequency)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid frequency: {body.frequency}",
            )
    if body.preferred_hour is not None:
        update_kwargs["preferred_hour"] = body.preferred_hour
    if body.timezone is not None:
        update_kwargs["timezone"] = body.timezone
    if body.status is not None:
        update_kwargs["status"] = _parse_schedule_status(body.status)
    if body.platforms is not None:
        update_kwargs["platforms"] = body.platforms
    if body.alert_on_significant_change is not None:
        update_kwargs["alert_on_significant_change"] = body.alert_on_significant_change
    if body.alert_threshold_bwvs is not None:
        update_kwargs["alert_threshold_bwvs"] = body.alert_threshold_bwvs

    updated = await service.update_schedule(sid, **update_kwargs)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )
    return {"schedule": schedule_to_dict(updated)}


@router.get("/entities/{entity_id}/panorama-status")
async def get_panorama_status(
    entity_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get latest panorama analysis status for an entity."""
    eid = _parse_uuid(entity_id, "entity_id")
    entity_service = EntityService(db)
    entity = await entity_service.get_entity(str(eid), current_user)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found",
        )

    query = (
        select(AnalysisSnapshot)
        .where(
            AnalysisSnapshot.entity_id == eid,
            AnalysisSnapshot.snapshot_type.in_(["panorama", "baseline"]),
        )
        .order_by(desc(AnalysisSnapshot.created_at))
        .limit(1)
    )
    result = await db.execute(query)
    snapshot = result.scalar_one_or_none()
    if snapshot is None:
        return {
            "panorama_status": {
                "has_report": False,
                "mention_rate": None,
                "brand_rank": None,
                "brand_rank_total": None,
                "brand_rank_label": None,
                "created_at": None,
                "triggered_by": None,
                "session_id": None,
            }
        }

    raw_data = snapshot.raw_data if isinstance(snapshot.raw_data, dict) else {}
    report_data = raw_data.get("report_data", {})
    report_data = report_data if isinstance(report_data, dict) else {}
    metric_bundle = raw_data.get("metric_bundle", {})
    metric_bundle = metric_bundle if isinstance(metric_bundle, dict) else {}
    summary_metrics = raw_data.get("metrics", {})
    summary_metrics = summary_metrics if isinstance(summary_metrics, dict) else {}

    mention_rate = metric_bundle.get("brand_visibility")
    if not isinstance(mention_rate, (int, float)):
        mention_rate = metric_bundle.get("mention_rate")
    if not isinstance(mention_rate, (int, float)):
        mention_rate = snapshot.mention_rate
    if not isinstance(mention_rate, (int, float)):
        mention_rate = summary_metrics.get("mention_rate")

    brand_rank = metric_bundle.get("brand_rank")
    if not isinstance(brand_rank, int):
        brand_rank = (
            summary_metrics.get("brand_rank")
            if isinstance(summary_metrics.get("brand_rank"), int)
            else None
        )

    brand_rank_total = metric_bundle.get("ranked_brand_count")
    if not isinstance(brand_rank_total, int):
        brand_rank_total = (
            report_data.get("metric_bundle", {}).get("ranked_brand_count")
            if isinstance(report_data.get("metric_bundle"), dict)
            and isinstance(report_data.get("metric_bundle", {}).get("ranked_brand_count"), int)
            else None
        )
    if not isinstance(brand_rank_total, int):
        top_brand_ranking = metric_bundle.get("top_brand_ranking")
        if isinstance(top_brand_ranking, list) and top_brand_ranking:
            brand_rank_total = len(top_brand_ranking)
    if not isinstance(brand_rank_total, int):
        dashboard_projection = report_data.get("dashboard_projection", {})
        visibility_board = (
            dashboard_projection.get("boards", {}).get("visibility", {})
            if isinstance(dashboard_projection, dict)
            else {}
        )
        ranking_rows = visibility_board.get("ranking_rows")
        if isinstance(ranking_rows, list) and ranking_rows:
            brand_rank_total = len(ranking_rows)

    brand_rank_label = None
    if isinstance(brand_rank, int):
        brand_rank_label = (
            f"{brand_rank}/{brand_rank_total}"
            if isinstance(brand_rank_total, int) and brand_rank_total > 0
            else f"#{brand_rank}"
        )

    return {
        "panorama_status": {
            "has_report": True,
            "mention_rate": mention_rate if isinstance(mention_rate, (int, float)) else None,
            "brand_rank": brand_rank if isinstance(brand_rank, int) else None,
            "brand_rank_total": brand_rank_total if isinstance(brand_rank_total, int) else None,
            "brand_rank_label": brand_rank_label,
            "created_at": snapshot.created_at.isoformat() if snapshot.created_at else None,
            "triggered_by": snapshot.triggered_by,
            "session_id": str(snapshot.session_id) if snapshot.session_id else None,
        }
    }


@router.patch("/schedules/{schedule_id}")
async def patch_schedule(
    schedule_id: str,
    body: UpdateScheduleRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Partially update a monitoring schedule (PATCH alias for PUT).

    Accepts the same body as PUT. Only non-null fields are applied.
    Added for frontend compatibility (PATCH semantics).
    """
    return await update_schedule(schedule_id, body, current_user, db)


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(
    schedule_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a monitoring schedule."""
    sid = _parse_uuid(schedule_id, "schedule_id")

    service = MonitoringService(db)
    schedule = await service.get_schedule(sid)
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )
    if not AccessScopeService.can_manage_schedule(schedule, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅计划创建者或内部管理员可删除监测计划",
        )

    await service.delete_schedule(sid)
    return {"deleted": True}


@router.post("/schedules/{schedule_id}/pause")
async def pause_schedule(
    schedule_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pause a monitoring schedule."""
    sid = _parse_uuid(schedule_id, "schedule_id")

    service = MonitoringService(db)
    schedule = await service.get_schedule(sid)
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )
    if not AccessScopeService.can_manage_schedule(schedule, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅计划创建者或内部管理员可暂停监测计划",
        )

    try:
        paused = await service.pause_schedule(sid)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return {"schedule": schedule_to_dict(paused)}


@router.post("/schedules/{schedule_id}/resume")
async def resume_schedule(
    schedule_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Resume a paused or errored monitoring schedule."""
    sid = _parse_uuid(schedule_id, "schedule_id")

    service = MonitoringService(db)
    schedule = await service.get_schedule(sid)
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )
    if not AccessScopeService.can_manage_schedule(schedule, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅计划创建者或内部管理员可恢复监测计划",
        )

    try:
        resumed = await service.resume_schedule(sid)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return {"schedule": schedule_to_dict(resumed)}


@router.get("/schedules/{schedule_id}/history")
async def get_schedule_history(
    schedule_id: str,
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get task execution history for a monitoring schedule."""
    sid = _parse_uuid(schedule_id, "schedule_id")

    service = MonitoringService(db)
    schedule = await service.get_schedule_for_viewer(sid, current_user)
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )

    tasks = await service.get_run_history(sid, limit=limit)
    return {
        "tasks": [task_to_dict(t) for t in tasks],
        "schedule_id": str(sid),
    }


# =========================================================================
# Baseline Endpoints
# =========================================================================


@router.get("/schedules/{schedule_id}/baseline")
async def get_baseline(
    schedule_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get baseline data for a monitoring schedule.

    Returns the full baseline including questions, brand_profile, and competitors
    that are reused in subsequent scheduled runs.
    """
    sid = _parse_uuid(schedule_id, "schedule_id")

    service = MonitoringService(db)
    schedule = await service.get_schedule_for_viewer(sid, current_user)
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )

    baseline = schedule.baseline_data
    if baseline is None:
        return {"baseline": None, "has_baseline": False}

    return {
        "baseline": baseline,
        "has_baseline": bool(baseline.get("questions")),
    }


@router.delete("/schedules/{schedule_id}/baseline")
async def clear_baseline(
    schedule_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Clear baseline data for a monitoring schedule.

    The next scheduled run will execute the full A1→A5 pipeline and
    save a fresh baseline upon completion.
    """
    sid = _parse_uuid(schedule_id, "schedule_id")

    service = MonitoringService(db)
    schedule = await service.get_schedule(sid)
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )
    if not AccessScopeService.can_manage_schedule(schedule, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅计划创建者或内部管理员可清除 baseline",
        )

    await service.clear_baseline(sid)
    return {"cleared": True}
