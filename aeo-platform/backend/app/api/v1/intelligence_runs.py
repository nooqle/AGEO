"""Brand intelligence run center API."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.schemas.intelligence_run import (
    BrandIntelligenceRunConfirm,
    BrandIntelligenceRunCreate,
)
from app.services.brand_intelligence_run_service import (
    BrandIntelligenceRunService,
    dispatch_brand_intelligence_run,
)

router = APIRouter(prefix="/intelligence-runs", tags=["intelligence-runs"])


def _envelope(service: BrandIntelligenceRunService, run):
    return {"run": service.to_dict(run)}


def _parse_uuid(value: str, field_name: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UUID for {field_name}: {value}",
        ) from exc


@router.get("/entities/{entity_id}/active")
async def get_active_intelligence_run(
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    service = BrandIntelligenceRunService(db)
    try:
        run = await service.get_active_run(
            entity_id=entity_id,
            current_user=current_user,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _envelope(service, run)


@router.post("/entities/{entity_id}", status_code=201)
async def create_intelligence_run(
    entity_id: str,
    payload: BrandIntelligenceRunCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    service = BrandIntelligenceRunService(db)
    try:
        run = await service.create_or_reuse_run(
            entity_id=entity_id,
            current_user=current_user,
            run_goal=payload.run_goal,
            analysis_mode=payload.analysis_mode,
            input_scope=payload.input_scope,
            origin_surface=payload.origin_surface,
            origin_session_id=payload.origin_session_id,
            origin_event_id=payload.origin_event_id,
            start_immediately=payload.auto_dispatch,
        )
        if payload.auto_dispatch:
            run = await service.ensure_runtime_submitted(
                run=run,
                current_user=current_user,
            )
            background_tasks.add_task(dispatch_brand_intelligence_run, str(run.id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _envelope(service, run)


@router.get("/{run_id}")
async def get_intelligence_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _parse_uuid(run_id, "run_id")
    service = BrandIntelligenceRunService(db)
    try:
        run = await service.get_run(run_id=run_id, current_user=current_user)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return _envelope(service, run)


@router.post("/{run_id}/resume")
async def resume_intelligence_run(
    run_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _parse_uuid(run_id, "run_id")
    service = BrandIntelligenceRunService(db)
    try:
        run = await service.resume_run(run_id=run_id, current_user=current_user)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        run = await service.ensure_runtime_submitted(
            run=run,
            current_user=current_user,
        )
        background_tasks.add_task(dispatch_brand_intelligence_run, str(run.id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _envelope(service, run)


@router.post("/{run_id}/cancel")
async def cancel_intelligence_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _parse_uuid(run_id, "run_id")
    service = BrandIntelligenceRunService(db)
    try:
        run = await service.cancel_run(run_id=run_id, current_user=current_user)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return _envelope(service, run)


@router.post("/{run_id}/confirm")
async def confirm_intelligence_run(
    run_id: str,
    payload: BrandIntelligenceRunConfirm,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _parse_uuid(run_id, "run_id")
    service = BrandIntelligenceRunService(db)
    try:
        run = await service.confirm_run(
            run_id=run_id,
            current_user=current_user,
            user_action_type=payload.user_action_type,
            feedback_text=payload.feedback_text,
            provided_inputs=payload.provided_inputs,
            origin_event_id=payload.origin_event_id,
        )
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        # M3: refresh_flow_plan stays in waiting_scope_confirmation — do not dispatch
        if run.status == "waiting_scope_confirmation" or run.requires_user_action:
            return _envelope(service, run)
        run = await service.ensure_runtime_submitted(
            run=run,
            current_user=current_user,
        )
        background_tasks.add_task(dispatch_brand_intelligence_run, str(run.id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _envelope(service, run)
