"""Amway China dedicated console asset APIs."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.v1.amwaychina_common import (
    iso as _iso,
    parse_optional_datetime as _parse_optional_datetime,
    parse_optional_uuid as _parse_optional_uuid,
    parse_uuid as _parse_uuid,
    require_amway_entity as _require_amway_entity,
)
from app.api.v1.amwaychina_flow_run import router as flow_run_router
from app.api.v1.amwaychina_flow_topology import (
    EMPTY_TOPOLOGY as _EMPTY_TOPOLOGY,
    normalize_topology as _normalize_topology,
    router as flow_topology_router,
)
from app.core.utils import repair_mojibake
from app.models.brand_intelligence_run import BrandIntelligenceRun
from app.models.entity import Entity
from app.models.monitoring_plan import MonitoringQuestionSet, QuestionSetStatus
from app.services.amway_circle_tracking_service import AmwayCircleTrackingService
from app.services.amway_entity_lexicon_service import AmwayEntityLexiconService
from app.services.monitoring_plan_service import MonitoringPlanService

router = APIRouter(prefix="/amwaychina", tags=["amwaychina"])
router.include_router(flow_topology_router)
router.include_router(flow_run_router)

# Backward-compatible re-exports for tests
__all__ = [
    "router",
    "_EMPTY_TOPOLOGY",
    "_normalize_topology",
    "_require_amway_entity",
    "_iso",
]

class EntityLexiconEntryRequest(BaseModel):
    canonical_name: str | None = None
    entity_type: str | None = None
    aliases: list[str] | str | None = None
    description: str | None = None
    related_terms: list[str] | str | None = None
    graph_policy: dict[str, Any] | None = None
    source_policy: dict[str, Any] | None = None
    review_status: str | None = None


class SaveQuestionSetRequest(BaseModel):
    title: str | None = None
    source_file_name: str | None = None
    center_term: str | None = None
    center_terms: list[str] | None = None
    questions: list[dict[str, Any] | str] = Field(default_factory=list)


class UpdateQuestionSetRequest(BaseModel):
    title: str | None = None
    source_file_name: str | None = None
    center_term: str | None = None
    center_terms: list[str] | None = None
    questions: list[dict[str, Any] | str] | None = None


class CirclePeriodViewResponse(BaseModel):
    period_type: str
    current_period: dict[str, Any]
    previous_period: dict[str, Any] | None = None
    question_set_changed: bool = False
    comparison_notice: str = ""
    change_top5: list[dict[str, Any]] = Field(default_factory=list)
    projection: dict[str, Any] | None = None
    report_input: dict[str, Any] = Field(default_factory=dict)
    report_id: str | None = None


class CirclePeriodReportRequest(BaseModel):
    period_type: str = Field(
        default="last_30_days",
        pattern="^(latest_run|last_7_days|last_14_days|last_30_days|custom)$",
    )
    start_at: datetime | None = None
    end_at: datetime | None = None
    center_term: str = Field(min_length=1)



@router.get("/entities/{entity_id}/circle-runs")
async def list_circle_runs(
    entity_id: str,
    limit: int = Query(30, ge=1, le=100),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entity = await _require_amway_entity(db, current_user, entity_id)
    service = AmwayCircleTrackingService(db)
    return await service.list_runs(entity.id, limit=limit)


@router.get("/entities/{entity_id}/circle-projection")
async def get_circle_projection(
    entity_id: str,
    scope: str = Query("cumulative", pattern="^(run|cumulative|compare)$"),
    run_id: str | None = None,
    base_run_id: str | None = None,
    target_run_id: str | None = None,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entity = await _require_amway_entity(db, current_user, entity_id)
    if scope == "run":
        if not run_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="run 视图需要提供 run_id。",
            )
        if base_run_id or target_run_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="run 视图不能同时提供 compare 参数。",
            )
    elif scope == "cumulative":
        if run_id or base_run_id or target_run_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="cumulative 视图不能提供 run_id 或 compare 参数。",
            )
    elif scope == "compare":
        if run_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="compare 视图不能同时提供 run_id。",
            )
        if bool(base_run_id) != bool(target_run_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="compare 视图需要同时提供 base_run_id 和 target_run_id，或都不提供读取最新对比。",
            )
    service = AmwayCircleTrackingService(db)
    projection = await service.get_projection(
        entity.id,
        scope=scope,
        run_id=_parse_optional_uuid(run_id, "run_id"),
        base_run_id=_parse_optional_uuid(base_run_id, "base_run_id"),
        target_run_id=_parse_optional_uuid(target_run_id, "target_run_id"),
    )
    return {"projection": projection}


@router.get(
    "/entities/{entity_id}/circle-period-view",
    response_model=CirclePeriodViewResponse,
)
async def get_circle_period_view(
    entity_id: str,
    period_type: str = Query(
        "last_30_days",
        pattern="^(latest_run|last_7_days|last_14_days|last_30_days|custom)$",
    ),
    start_at: str | None = None,
    end_at: str | None = None,
    center_term: str | None = None,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entity = await _require_amway_entity(db, current_user, entity_id)
    service = AmwayCircleTrackingService(db)
    try:
        return await service.get_period_view(
            entity.id,
            period_type=period_type,
            start_at=_parse_optional_datetime(start_at, "start_at"),
            end_at=_parse_optional_datetime(end_at, "end_at"),
            center_term=center_term,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/entities/{entity_id}/circle-period-reports",
    response_model=CirclePeriodViewResponse,
)
async def create_circle_period_report(
    entity_id: str,
    body: CirclePeriodReportRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entity = await _require_amway_entity(db, current_user, entity_id)
    try:
        return await AmwayCircleTrackingService(db).create_period_report(
            entity.id,
            period_type=body.period_type,
            start_at=body.start_at,
            end_at=body.end_at,
            center_term=body.center_term,
            created_by_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/entities/{entity_id}/circle-node-insight")
async def get_circle_node_insight(
    entity_id: str,
    projection_id: str,
    node_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entity = await _require_amway_entity(db, current_user, entity_id)
    service = AmwayCircleTrackingService(db)
    insight = await service.get_node_insight(
        entity.id,
        projection_id=_parse_uuid(projection_id, "projection_id"),
        node_id=node_id,
    )
    if insight is None:
        raise HTTPException(status_code=404, detail="节点解读不存在")
    return {"insight": insight}


@router.get("/entities/{entity_id}/entity-lexicon")
async def get_entity_lexicon(
    entity_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entity = await _require_amway_entity(db, current_user, entity_id)
    service = AmwayEntityLexiconService(db)
    payload = await service.payload_for_entity(entity.id)
    payload["entity_id"] = str(entity.id)
    payload["entity_name"] = entity.name
    return payload


@router.post("/entities/{entity_id}/entity-lexicon", status_code=201)
async def create_entity_lexicon_entry(
    entity_id: str,
    body: EntityLexiconEntryRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entity = await _require_amway_entity(db, current_user, entity_id, manage=True)
    service = AmwayEntityLexiconService(db)
    try:
        row = await service.create_entry(
            entity=entity,
            current_user_id=current_user.id,
            payload=body.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"entry_id": row.lexicon_entity_id}


@router.patch("/entities/{entity_id}/entity-lexicon/{lexicon_entity_id}")
async def update_entity_lexicon_entry(
    entity_id: str,
    lexicon_entity_id: str,
    body: EntityLexiconEntryRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entity = await _require_amway_entity(db, current_user, entity_id, manage=True)
    service = AmwayEntityLexiconService(db)
    try:
        row = await service.update_entry(
            entity=entity,
            lexicon_entity_id=lexicon_entity_id,
            current_user_id=current_user.id,
            payload=body.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"entry_id": row.lexicon_entity_id}


@router.delete("/entities/{entity_id}/entity-lexicon/{lexicon_entity_id}")
async def delete_entity_lexicon_entry(
    entity_id: str,
    lexicon_entity_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entity = await _require_amway_entity(db, current_user, entity_id, manage=True)
    service = AmwayEntityLexiconService(db)
    try:
        row = await service.delete_entry(
            entity=entity,
            lexicon_entity_id=lexicon_entity_id,
            current_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"entry_id": row.lexicon_entity_id, "deleted": True}


@router.get("/entities/{entity_id}/question-sets")
async def list_amway_question_sets(
    entity_id: str,
    limit: int = Query(30, ge=1, le=100),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entity = await _require_amway_entity(db, current_user, entity_id)
    records: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()

    question_rows = (
        (
            await db.execute(
                select(MonitoringQuestionSet)
                .where(
                    MonitoringQuestionSet.entity_id == entity.id,
                    MonitoringQuestionSet.source == "amwaychina_upload",
                    MonitoringQuestionSet.status
                    != QuestionSetStatus.ARCHIVED.value,
                )
                .order_by(desc(MonitoringQuestionSet.created_at))
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    for row in question_rows:
        record = _question_set_row_to_record(row)
        signature = _question_signature(record["questions"])
        if signature in seen_hashes:
            continue
        seen_hashes.add(signature)
        records.append(record)

    run_rows = (
        (
            await db.execute(
                select(BrandIntelligenceRun)
                .where(BrandIntelligenceRun.entity_id == entity.id)
                .order_by(desc(BrandIntelligenceRun.created_at))
                .limit(limit * 2)
            )
        )
        .scalars()
        .all()
    )
    for run in run_rows:
        input_scope = repair_mojibake(
            run.input_scope if isinstance(run.input_scope, dict) else {}
        )
        questions = input_scope.get("uploaded_questions")
        if not isinstance(questions, list) or not questions:
            continue
        normalized = MonitoringPlanService.normalize_questions(questions)
        signature = _question_signature(normalized)
        if signature in seen_hashes:
            continue
        seen_hashes.add(signature)
        records.append(
            {
                "id": str(run.id),
                "source_type": "run_input",
                "title": str(
                    input_scope.get("uploaded_question_source")
                    or input_scope.get("question_set_version")
                    or "安利上传题库"
                ),
                "source": str(
                    input_scope.get("uploaded_question_source") or "run_input"
                ),
                "version": input_scope.get("question_set_version"),
                "status": run.status,
                "question_count": len(normalized),
                "questions": normalized,
                "center_terms": input_scope.get("center_terms") or [],
                "created_at": _iso(run.created_at),
                "updated_at": _iso(run.updated_at),
            }
        )

    records.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return {"question_sets": records[:limit], "total": len(records[:limit])}


@router.post("/entities/{entity_id}/question-sets", status_code=201)
async def save_amway_question_set(
    entity_id: str,
    body: SaveQuestionSetRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entity = await _require_amway_entity(db, current_user, entity_id, manage=True)
    normalized = MonitoringPlanService.normalize_questions(body.questions)
    if not normalized:
        raise HTTPException(status_code=400, detail="问题列表不能为空")
    row = MonitoringQuestionSet(
        user_id=current_user.id,
        entity_id=entity.id,
        monitor_mode="panorama",
        status=QuestionSetStatus.CONFIRMED.value,
        source="amwaychina_upload",
        title=body.title or body.source_file_name or "安利上传题库",
        version=1,
        questions=normalized,
        question_count=len(normalized),
        extra_metadata={
            "source_file_name": body.source_file_name,
            "center_term": body.center_term,
            "center_terms": body.center_terms or [],
            "source": "amwaychina_console",
        },
        confirmed_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"question_set": _question_set_row_to_record(row)}


async def _scoped_question_set(
    db: AsyncSession,
    *,
    entity_id: UUID,
    question_set_id: str,
) -> MonitoringQuestionSet:
    question_set_uuid = _parse_uuid(question_set_id, "question_set_id")
    row = (
        await db.execute(
            select(MonitoringQuestionSet).where(
                MonitoringQuestionSet.id == question_set_uuid,
                MonitoringQuestionSet.entity_id == entity_id,
                MonitoringQuestionSet.source == "amwaychina_upload",
            )
        )
    ).scalar_one_or_none()
    if row is None or row.status == QuestionSetStatus.ARCHIVED.value:
        raise HTTPException(status_code=404, detail="题库不存在")
    return row


@router.patch("/entities/{entity_id}/question-sets/{question_set_id}")
async def update_amway_question_set(
    entity_id: str,
    question_set_id: str,
    body: UpdateQuestionSetRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entity = await _require_amway_entity(db, current_user, entity_id, manage=True)
    row = await _scoped_question_set(
        db,
        entity_id=entity.id,
        question_set_id=question_set_id,
    )
    if body.questions is not None:
        normalized = MonitoringPlanService.normalize_questions(body.questions)
        if not normalized:
            raise HTTPException(status_code=400, detail="问题列表不能为空")
        row.questions = normalized
        row.question_count = len(normalized)
    if body.title is not None:
        title = body.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="题库名称不能为空")
        row.title = title
    metadata = dict(row.extra_metadata or {})
    if body.source_file_name is not None:
        metadata["source_file_name"] = body.source_file_name
    if body.center_term is not None:
        metadata["center_term"] = body.center_term
    if body.center_terms is not None:
        metadata["center_terms"] = body.center_terms
    metadata["last_edited_by_user_id"] = str(current_user.id)
    row.extra_metadata = metadata
    row.version = max(int(row.version or 1), 1) + 1
    row.status = QuestionSetStatus.CONFIRMED.value
    row.confirmed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return {"question_set": _question_set_row_to_record(row)}


@router.delete("/entities/{entity_id}/question-sets/{question_set_id}")
async def delete_amway_question_set(
    entity_id: str,
    question_set_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entity = await _require_amway_entity(db, current_user, entity_id, manage=True)
    row = await _scoped_question_set(
        db,
        entity_id=entity.id,
        question_set_id=question_set_id,
    )
    metadata = dict(row.extra_metadata or {})
    metadata.update(
        {
            "archived_by_user_id": str(current_user.id),
            "archived_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    row.extra_metadata = metadata
    row.status = QuestionSetStatus.ARCHIVED.value
    await db.commit()
    return {"question_set_id": str(row.id), "deleted": True}


def _question_set_row_to_record(row: MonitoringQuestionSet) -> dict[str, Any]:
    metadata = row.extra_metadata if isinstance(row.extra_metadata, dict) else {}
    questions = MonitoringPlanService.normalize_questions(row.questions or [])
    return {
        "id": str(row.id),
        "source_type": "question_set",
        "title": row.title,
        "source": row.source,
        "version": max(int(row.version or 1), 1),
        "status": row.status,
        "question_count": row.question_count or len(questions),
        "questions": questions,
        "center_terms": metadata.get("center_terms") or [],
        "source_file_name": metadata.get("source_file_name"),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _question_signature(questions: list[Any]) -> str:
    texts: list[str] = []
    for item in questions:
        if isinstance(item, dict):
            text = str(item.get("question_text") or item.get("text") or "").strip()
        else:
            text = str(item or "").strip()
        if text:
            texts.append(" ".join(text.split()))
    return hashlib.sha256("\n".join(texts).encode("utf-8")).hexdigest()

