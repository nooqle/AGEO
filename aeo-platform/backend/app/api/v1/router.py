"""API router."""

from fastapi import APIRouter

from app.api.v1 import (
    aio,
    account_admin,
    alerts,
    analytics,
    auth,
    brand_space,
    control_plane,
    entities,
    favicons,
    feature_entitlements,
    files,
    intelligence_runs,
    messages,
    monitoring,
    ontology,
    outputs,
    sessions,
    skills,
    snapshots,
    tasks,
    touchpoints,
)
from app.api.v1.tasks import global_tasks_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(sessions.router)
api_router.include_router(aio.router)
api_router.include_router(messages.router)
api_router.include_router(outputs.router)
api_router.include_router(auth.router)
api_router.include_router(account_admin.router)
api_router.include_router(analytics.router)
api_router.include_router(entities.router)
api_router.include_router(favicons.router)
api_router.include_router(touchpoints.router)
api_router.include_router(feature_entitlements.router)
api_router.include_router(files.router)
api_router.include_router(intelligence_runs.router)
api_router.include_router(brand_space.router)
api_router.include_router(snapshots.router)
api_router.include_router(tasks.router)
api_router.include_router(global_tasks_router)
api_router.include_router(monitoring.router)
api_router.include_router(ontology.router)
api_router.include_router(alerts.router)
api_router.include_router(skills.router)
api_router.include_router(control_plane.router)
