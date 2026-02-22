"""API router."""

from fastapi import APIRouter

from app.api.v1 import (
    alerts,
    analytics,
    auth,
    entities,
    files,
    messages,
    monitoring,
    outputs,
    sessions,
    snapshots,
    tasks,
    touchpoints,
)
from app.api.v1.tasks import global_tasks_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(sessions.router)
api_router.include_router(messages.router)
api_router.include_router(outputs.router)
api_router.include_router(auth.router)
api_router.include_router(analytics.router)
api_router.include_router(entities.router)
api_router.include_router(touchpoints.router)
api_router.include_router(files.router)
api_router.include_router(snapshots.router)
api_router.include_router(tasks.router)
api_router.include_router(global_tasks_router)
api_router.include_router(monitoring.router)
api_router.include_router(alerts.router)
