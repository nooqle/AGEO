"""Analytics API endpoints for Dashboard."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.services.analytics_service import AnalyticsService
from app.services.entity_service import EntityService

router = APIRouter(prefix="/analytics", tags=["analytics"])


async def _ensure_brand_access(
    brand_id: str | None,
    *,
    db: AsyncSession,
    current_user,
) -> None:
    if not brand_id:
        return
    entity = await EntityService(db).get_entity_model(
        brand_id,
        current_user,
        allow_internal_admin_bypass=False,
    )
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")


@router.get("/overview")
async def get_overview(
    brand_id: str | None = Query(None),
    date_range: str = Query("month"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get KPI overview: visibility, mention rate, SOV."""
    await _ensure_brand_access(brand_id, db=db, current_user=current_user)
    service = AnalyticsService(
        db,
        viewer=current_user,
        allow_internal_admin_bypass=False,
    )
    return await service.get_overview(brand_id, date_range)


@router.get("/visibility")
async def get_visibility(
    brand_id: str | None = Query(None),
    date_range: str = Query("month"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get visibility trend data."""
    await _ensure_brand_access(brand_id, db=db, current_user=current_user)
    service = AnalyticsService(
        db,
        viewer=current_user,
        allow_internal_admin_bypass=False,
    )
    return await service.get_visibility_data(brand_id, date_range)


@router.get("/platforms")
async def get_platforms(
    brand_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get platform comparison data."""
    await _ensure_brand_access(brand_id, db=db, current_user=current_user)
    service = AnalyticsService(
        db,
        viewer=current_user,
        allow_internal_admin_bypass=False,
    )
    return await service.get_platform_data(brand_id)


@router.get("/sources")
async def get_sources(
    brand_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get source distribution data."""
    await _ensure_brand_access(brand_id, db=db, current_user=current_user)
    service = AnalyticsService(
        db,
        viewer=current_user,
        allow_internal_admin_bypass=False,
    )
    return await service.get_source_data(brand_id)


@router.get("/aeo")
async def get_aeo_metrics(
    brand_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get AEO performance metrics."""
    await _ensure_brand_access(brand_id, db=db, current_user=current_user)
    service = AnalyticsService(
        db,
        viewer=current_user,
        allow_internal_admin_bypass=False,
    )
    return await service.get_aeo_metrics(brand_id)


@router.get("/sentiment")
async def get_sentiment(
    brand_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get sentiment analysis data."""
    await _ensure_brand_access(brand_id, db=db, current_user=current_user)
    service = AnalyticsService(
        db,
        viewer=current_user,
        allow_internal_admin_bypass=False,
    )
    return await service.get_sentiment_data(brand_id)


@router.get("/competitors")
async def get_competitors(
    brand_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get competitor comparison data."""
    await _ensure_brand_access(brand_id, db=db, current_user=current_user)
    service = AnalyticsService(
        db,
        viewer=current_user,
        allow_internal_admin_bypass=False,
    )
    return await service.get_competitor_data(brand_id)


@router.get("/v2/overview")
async def get_overview_v2(
    brand_id: str | None = Query(None),
    date_range: str = Query("month"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get Dashboard V2 overview data."""
    await _ensure_brand_access(brand_id, db=db, current_user=current_user)
    service = AnalyticsService(
        db,
        viewer=current_user,
        allow_internal_admin_bypass=False,
    )
    return await service.get_overview_v2(brand_id, date_range)


@router.get("/v2/scenarios")
async def get_scenarios_v2(
    brand_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get Dashboard V2 scenario table data."""
    await _ensure_brand_access(brand_id, db=db, current_user=current_user)
    service = AnalyticsService(
        db,
        viewer=current_user,
        allow_internal_admin_bypass=False,
    )
    return await service.get_scenarios_v2(brand_id)


@router.get("/v2/competitor-battles")
async def get_competitor_battles_v2(
    brand_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get Dashboard V2 competitor battle data."""
    await _ensure_brand_access(brand_id, db=db, current_user=current_user)
    service = AnalyticsService(
        db,
        viewer=current_user,
        allow_internal_admin_bypass=False,
    )
    return await service.get_competitor_battles_v2(brand_id)


@router.get("/v2/sources")
async def get_sources_v2(
    brand_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get Dashboard V2 source overview."""
    await _ensure_brand_access(brand_id, db=db, current_user=current_user)
    service = AnalyticsService(
        db,
        viewer=current_user,
        allow_internal_admin_bypass=False,
    )
    return await service.get_sources_v2(brand_id)



@router.get("/v2/dashboard-home")
async def get_dashboard_home_v2(
    brand_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get Dashboard homepage three-board aggregate data."""
    await _ensure_brand_access(brand_id, db=db, current_user=current_user)
    service = AnalyticsService(
        db,
        viewer=current_user,
        allow_internal_admin_bypass=False,
    )
    return await service.get_dashboard_home_v2(brand_id)


@router.get("/v2/risks-actions")
async def get_risks_actions_v2(
    brand_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get Dashboard V2 risks and actions."""
    await _ensure_brand_access(brand_id, db=db, current_user=current_user)
    service = AnalyticsService(
        db,
        viewer=current_user,
        allow_internal_admin_bypass=False,
    )
    return await service.get_risks_actions_v2(brand_id)


# =========================================================================
# Trend Endpoints (Cycle 4)
# =========================================================================


@router.get("/trend")
async def get_trend(
    brand_id: str = Query(..., description="Entity ID"),
    metric: str = Query("mention_rate", description="Metric name"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get trend time series for a specific metric."""
    from app.services.trend_engine import TrendEngine

    await _ensure_brand_access(brand_id, db=db, current_user=current_user)
    engine = TrendEngine(db)
    data_points = await engine.get_trend_data_points(
        UUID(brand_id), metric_name=metric, limit=limit
    )
    return {"trend": data_points, "metric": metric}


@router.get("/trend/summary")
async def get_trend_summary(
    brand_id: str = Query(..., description="Entity ID"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get trend summary for all core metrics."""
    from app.services.trend_engine import TrendEngine

    await _ensure_brand_access(brand_id, db=db, current_user=current_user)
    engine = TrendEngine(db)
    summaries = await engine.get_entity_trend_summary(UUID(brand_id))
    return {
        "summaries": {
            name: {
                "metric_name": s.metric_name,
                "current_value": s.current_value,
                "direction": s.trend_direction.value,
                "period_delta": {
                    "absolute": s.period_delta.absolute_change,
                    "percentage": s.period_delta.percentage_change,
                    "is_significant": s.period_delta.is_significant,
                    "direction": s.period_delta.direction,
                } if s.period_delta else None,
                "data_points": s.data_points,
                "time_range_days": s.time_range_days,
                "moving_average": s.moving_average,
                "min_value": s.min_value,
                "max_value": s.max_value,
            }
            for name, s in summaries.items()
        }
    }


