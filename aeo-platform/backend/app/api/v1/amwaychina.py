"""Amway China dedicated console asset APIs."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.models.brand_intelligence_run import BrandIntelligenceRun
from app.models.entity import Entity
from app.models.monitoring_plan import MonitoringQuestionSet, QuestionSetStatus
from app.services.access_scope_service import AccessScopeService
from app.services.amway_entity_lexicon_service import AmwayEntityLexiconService
from app.services.monitoring_plan_service import MonitoringPlanService
from app.services.organization_feature_service import (
    FEATURE_AMWAYCHINA_CONSOLE,
    feature_enabled_for_account,
)

router = APIRouter(prefix="/amwaychina", tags=["amwaychina"])


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


def _parse_uuid(value: str, field_name: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UUID for {field_name}: {value}",
        ) from exc


async def _require_amway_entity(
    db: AsyncSession,
    current_user: Any,
    entity_id: str,
    *,
    manage: bool = False,
) -> Entity:
    entity_uuid = _parse_uuid(entity_id, "entity_id")
    result = await db.execute(
        select(Entity)
        .options(selectinload(Entity.organization), selectinload(Entity.sessions))
        .where(Entity.id == entity_uuid)
    )
    entity = result.scalar_one_or_none()
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    if not AccessScopeService.can_access_entity(entity, current_user):
        raise HTTPException(status_code=403, detail="无权访问该安利实体")
    if manage and not AccessScopeService.can_manage_entity(entity, current_user):
        raise HTTPException(status_code=403, detail="无权管理该安利实体")
    if not feature_enabled_for_account(
        user_flags=getattr(current_user, "feature_flags", None),
        organization_flags=getattr(entity.organization, "feature_flags", None),
        feature_key=FEATURE_AMWAYCHINA_CONSOLE,
    ):
        raise HTTPException(status_code=403, detail="当前账号未开通安利专项权限")
    return entity


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
                .where(MonitoringQuestionSet.entity_id == entity.id)
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
        input_scope = run.input_scope if isinstance(run.input_scope, dict) else {}
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


def _question_set_row_to_record(row: MonitoringQuestionSet) -> dict[str, Any]:
    metadata = row.extra_metadata if isinstance(row.extra_metadata, dict) else {}
    questions = MonitoringPlanService.normalize_questions(row.questions or [])
    return {
        "id": str(row.id),
        "source_type": "question_set",
        "title": row.title,
        "source": row.source,
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


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None
