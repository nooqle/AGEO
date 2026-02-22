"""Alert API endpoints for monitoring notifications."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.monitoring_alert import AlertSeverity, AlertStatus
from app.services.alert_service import AlertService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitoring/alerts", tags=["monitoring", "alerts"])


def _parse_uuid(value: str, field_name: str = "id") -> UUID:
    """Parse a string as UUID, raising 400 on invalid format."""
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UUID for {field_name}: {value}",
        )


def alert_to_dict(alert) -> dict[str, Any]:
    """Convert MonitoringAlert to API-friendly dict.

    Requires entity relationship to be eager-loaded for entity_name.
    """
    # Safely extract entity_name from eager-loaded relationship
    entity_name = None
    try:
        if alert.entity is not None:
            entity_name = alert.entity.name
    except Exception:
        pass

    return {
        "id": str(alert.id),
        "user_id": str(alert.user_id),
        "entity_id": str(alert.entity_id),
        "entity_name": entity_name,
        "schedule_id": str(alert.schedule_id) if alert.schedule_id else None,
        "snapshot_id": str(alert.snapshot_id) if alert.snapshot_id else None,
        "severity": alert.severity.value if alert.severity else "medium",
        "status": alert.status.value if alert.status else "unread",
        "title": alert.title,
        "summary": alert.summary,
        "metric_name": alert.metric_name,
        "previous_value": alert.previous_value,
        "current_value": alert.current_value,
        "change_absolute": alert.change_absolute,
        "change_percentage": alert.change_percentage,
        "details": alert.details,
        "created_at": (
            alert.created_at.isoformat() if alert.created_at else None
        ),
        "read_at": alert.read_at.isoformat() if alert.read_at else None,
    }


@router.get("")
async def list_alerts(
    entity_id: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    severity: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List alerts for the current user."""
    eid = _parse_uuid(entity_id, "entity_id") if entity_id else None

    alert_status = None
    if status_filter:
        try:
            alert_status = AlertStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}",
            )

    alert_severity = None
    if severity:
        try:
            alert_severity = AlertSeverity(severity)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid severity: {severity}",
            )

    service = AlertService(db)
    alerts, total = await service.get_alerts(
        user_id=current_user.id,
        entity_id=eid,
        status=alert_status,
        severity=alert_severity,
        limit=limit,
        offset=offset,
    )
    return {
        "alerts": [alert_to_dict(a) for a in alerts],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/unread-count")
async def get_unread_count(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get unread alert count for notification badge."""
    service = AlertService(db)
    count = await service.get_unread_count(current_user.id)
    return {"unread_count": count}


@router.get("/{alert_id}")
async def get_alert(
    alert_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single alert by ID."""
    aid = _parse_uuid(alert_id, "alert_id")
    service = AlertService(db)
    alert = await service.get_alert(aid)
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )
    if alert.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    return {"alert": alert_to_dict(alert)}


@router.post("/{alert_id}/read")
async def mark_alert_read(
    alert_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark an alert as read."""
    aid = _parse_uuid(alert_id, "alert_id")
    service = AlertService(db)

    alert = await service.get_alert(aid)
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )
    if alert.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    updated = await service.mark_read(aid)
    return {"alert": alert_to_dict(updated)}


@router.post("/read-all")
async def mark_all_read(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark all unread alerts as read."""
    service = AlertService(db)
    count = await service.mark_all_read(current_user.id)
    return {"updated_count": count}


@router.post("/{alert_id}/dismiss")
async def dismiss_alert(
    alert_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dismiss an alert."""
    aid = _parse_uuid(alert_id, "alert_id")
    service = AlertService(db)

    alert = await service.get_alert(aid)
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )
    if alert.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    updated = await service.dismiss_alert(aid)
    return {"alert": alert_to_dict(updated)}
