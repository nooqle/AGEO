"""Brand Space board runtime API."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.schemas.brand_space import (
    BoardRunCreate,
    GraphPatchDecision,
    GraphUpdateReportCreate,
)
from app.services.brand_intelligence_run_service import dispatch_brand_intelligence_run
from app.services.brand_space_service import (
    BrandSpaceService,
    build_real_graph_update_for_board_run,
)

router = APIRouter(prefix="/brand-space", tags=["brand-space"])


def _parse_uuid(value: str, field_name: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UUID for {field_name}: {value}",
        ) from exc


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@router.get("/brands/{entity_id}/space")
async def get_brand_space(
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    service = BrandSpaceService(db)
    try:
        return await service.get_space(entity_id=entity_id, current_user=current_user)
    except Exception as exc:
        _raise_http(exc)


@router.get("/brands/{entity_id}/graph")
async def get_brand_graph(
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    service = BrandSpaceService(db)
    try:
        return await service.get_graph(entity_id=entity_id, current_user=current_user)
    except Exception as exc:
        _raise_http(exc)


@router.get("/brands/{entity_id}/review-items")
async def get_brand_review_items(
    entity_id: str,
    review_status: str | None = None,
    category: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    service = BrandSpaceService(db)
    try:
        return await service.get_review_items(
            entity_id=entity_id,
            current_user=current_user,
            status=review_status,
            category=category,
            limit=limit,
        )
    except Exception as exc:
        _raise_http(exc)


@router.get("/brands/{entity_id}/reports")
async def get_brand_reports(
    entity_id: str,
    report_kind: str | None = None,
    publication_status: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    service = BrandSpaceService(db)
    try:
        return await service.list_reports(
            entity_id=entity_id,
            current_user=current_user,
            report_kind=report_kind,
            publication_status=publication_status,
            limit=limit,
        )
    except Exception as exc:
        _raise_http(exc)


@router.post("/brands/{entity_id}/board-runs", status_code=201)
async def create_board_run(
    entity_id: str,
    payload: BoardRunCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    service = BrandSpaceService(db)
    try:
        response = await service.create_board_run(
            entity_id=entity_id,
            current_user=current_user,
            board_id=payload.board_id,
            template_id=payload.template_id,
            input_scope=payload.input_scope,
            execution_mode=payload.execution_mode,
        )
        if payload.execution_mode == "real":
            response, intelligence_run_id = await service.submit_board_run_runtime(
                run_id=response["run"]["id"],
                current_user=current_user,
            )
            if intelligence_run_id:
                background_tasks.add_task(dispatch_brand_intelligence_run, intelligence_run_id)
        return response
    except Exception as exc:
        _raise_http(exc)


@router.get("/board-runs/{run_id}")
async def get_board_run(
    run_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _parse_uuid(run_id, "run_id")
    service = BrandSpaceService(db)
    try:
        response = await service.get_board_run(run_id=run_id, current_user=current_user)
        output_refs = (response.get("run") or {}).get("output_refs") or {}
        if output_refs.get("graph_update_build_status") == "pending":
            if await service.claim_graph_update_build(
                run_id=run_id,
                current_user=current_user,
            ):
                background_tasks.add_task(
                    build_real_graph_update_for_board_run,
                    run_id,
                    current_user.id,
                )
        return response
    except Exception as exc:
        _raise_http(exc)


@router.post("/board-runs/{run_id}/pause")
async def pause_board_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _parse_uuid(run_id, "run_id")
    service = BrandSpaceService(db)
    try:
        return await service.update_board_run_status(
            run_id=run_id,
            current_user=current_user,
            status="pause_requested",
        )
    except Exception as exc:
        _raise_http(exc)


@router.post("/board-runs/{run_id}/resume")
async def resume_board_run(
    run_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _parse_uuid(run_id, "run_id")
    service = BrandSpaceService(db)
    try:
        response = await service.update_board_run_status(
            run_id=run_id,
            current_user=current_user,
            status="running",
        )
        if response["run"] and response["run"].get("is_scaffold") is False:
            response, intelligence_run_id = await service.submit_board_run_runtime(
                run_id=run_id,
                current_user=current_user,
            )
            if intelligence_run_id:
                background_tasks.add_task(dispatch_brand_intelligence_run, intelligence_run_id)
        return response
    except Exception as exc:
        _raise_http(exc)


@router.post("/board-runs/{run_id}/stop")
async def stop_board_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _parse_uuid(run_id, "run_id")
    service = BrandSpaceService(db)
    try:
        return await service.update_board_run_status(
            run_id=run_id,
            current_user=current_user,
            status="stopped",
        )
    except Exception as exc:
        _raise_http(exc)


@router.get("/board-runs/{run_id}/events")
async def get_board_run_events(
    run_id: str,
    limit: int = 100,
    offset: int = 0,
    after_sequence: int | None = None,
    sync: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _parse_uuid(run_id, "run_id")
    service = BrandSpaceService(db)
    try:
        return await service.get_events(
            run_id=run_id,
            current_user=current_user,
            limit=limit,
            offset=offset,
            after_sequence=after_sequence,
            sync=sync,
        )
    except Exception as exc:
        _raise_http(exc)


@router.get("/board-runs/{run_id}/assets")
async def get_board_run_assets(
    run_id: str,
    artifact_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
    sync: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _parse_uuid(run_id, "run_id")
    service = BrandSpaceService(db)
    try:
        return await service.get_assets(
            run_id=run_id,
            current_user=current_user,
            artifact_type=artifact_type,
            limit=limit,
            offset=offset,
            sync=sync,
        )
    except Exception as exc:
        _raise_http(exc)


@router.get("/artifacts/{artifact_id}")
async def get_artifact_detail(
    artifact_id: str,
    sync: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    service = BrandSpaceService(db)
    try:
        return await service.get_artifact_detail(
            artifact_id=artifact_id,
            current_user=current_user,
            sync=sync,
        )
    except Exception as exc:
        _raise_http(exc)


@router.get("/artifacts/{artifact_id}/access")
async def get_artifact_access(
    artifact_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    service = BrandSpaceService(db)
    try:
        return await service.get_artifact_access(
            artifact_id=artifact_id,
            current_user=current_user,
        )
    except Exception as exc:
        _raise_http(exc)


@router.get("/artifacts/{artifact_id}/download")
async def download_artifact(
    artifact_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    service = BrandSpaceService(db)
    try:
        download = await service.resolve_artifact_download(
            artifact_id=artifact_id,
            current_user=current_user,
        )
        return FileResponse(
            path=download["path"],
            media_type=download["media_type"],
            filename=download["filename"],
        )
    except Exception as exc:
        _raise_http(exc)


@router.get("/graph-updates/{graph_update_id}")
async def get_graph_update(
    graph_update_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _parse_uuid(graph_update_id, "graph_update_id")
    service = BrandSpaceService(db)
    try:
        return await service.get_graph_update(
            graph_update_id=graph_update_id,
            current_user=current_user,
        )
    except Exception as exc:
        _raise_http(exc)


@router.get("/reports/{report_version_id}")
async def get_report_version(
    report_version_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _parse_uuid(report_version_id, "report_version_id")
    service = BrandSpaceService(db)
    try:
        return await service.get_report(
            report_version_id=report_version_id,
            current_user=current_user,
        )
    except Exception as exc:
        _raise_http(exc)


@router.post("/reports/{report_version_id}/publish")
async def publish_report_version(
    report_version_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _parse_uuid(report_version_id, "report_version_id")
    service = BrandSpaceService(db)
    try:
        return await service.publish_report(
            report_version_id=report_version_id,
            current_user=current_user,
        )
    except Exception as exc:
        _raise_http(exc)


@router.post("/graph-patches/{patch_id}/decision")
async def decide_graph_patch(
    patch_id: str,
    payload: GraphPatchDecision,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _parse_uuid(patch_id, "patch_id")
    service = BrandSpaceService(db)
    try:
        return await service.decide_graph_patch(
            patch_id=patch_id,
            status=payload.status,
            reason=payload.reason,
            current_user=current_user,
        )
    except Exception as exc:
        _raise_http(exc)


@router.post("/graph-updates/{graph_update_id}/reports", status_code=201)
async def generate_graph_update_report(
    graph_update_id: str,
    payload: GraphUpdateReportCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _parse_uuid(graph_update_id, "graph_update_id")
    service = BrandSpaceService(db)
    try:
        return await service.generate_report(
            graph_update_id=graph_update_id,
            current_user=current_user,
            report_kind=payload.report_kind,
            publish_requested=payload.publish_requested,
        )
    except Exception as exc:
        _raise_http(exc)
