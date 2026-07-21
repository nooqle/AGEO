"""Amway China dedicated console asset APIs."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.core.utils import repair_mojibake
from app.models.brand_intelligence_run import BrandIntelligenceRun
from app.models.entity import Entity
from app.models.flow_topology import FlowTopologyRecord
from app.models.monitoring_plan import MonitoringQuestionSet, QuestionSetStatus
from app.services.access_scope_service import AccessScopeService
from app.services.amway_circle_tracking_service import AmwayCircleTrackingService
from app.services.amway_entity_lexicon_service import AmwayEntityLexiconService
from app.services.brand_association_circle_variant import (
    is_amway_association_entity,
)
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


def _parse_uuid(value: str, field_name: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UUID for {field_name}: {value}",
        ) from exc


def _parse_optional_uuid(value: str | None, field_name: str) -> UUID | None:
    if not value:
        return None
    return _parse_uuid(value, field_name)


def _parse_optional_datetime(value: str | None, field_name: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid datetime for {field_name}: {value}",
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _entity_aliases(entity: Entity) -> list[Any]:
    if not entity.aliases:
        return []
    try:
        value = json.loads(entity.aliases)
    except (TypeError, json.JSONDecodeError):
        return [entity.aliases]
    return value if isinstance(value, list) else [value]


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
    if not is_amway_association_entity(
        name=entity.name,
        domain=entity.domain,
        aliases=_entity_aliases(entity),
    ):
        raise HTTPException(status_code=404, detail="Amway entity not found")
    if not AccessScopeService.can_access_entity(
        entity,
        current_user,
        allow_internal_admin_bypass=False,
    ):
        raise HTTPException(status_code=403, detail="无权访问该安利实体")
    if manage and not AccessScopeService.can_manage_entity(
        entity,
        current_user,
        allow_internal_admin_bypass=False,
    ):
        raise HTTPException(status_code=403, detail="无权管理该安利实体")
    if not feature_enabled_for_account(
        user_flags=getattr(current_user, "feature_flags", None),
        organization_flags=getattr(entity.organization, "feature_flags", None),
        feature_key=FEATURE_AMWAYCHINA_CONSOLE,
    ):
        raise HTTPException(status_code=403, detail="当前账号未开通安利专项权限")
    return entity


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


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None


# ---------------------------------------------------------------------------
# Flow topology persistence (blueprint task 3b-1.4)
# ---------------------------------------------------------------------------

_EMPTY_TOPOLOGY: dict[str, Any] = {
    "version": 1,
    "customNodes": [],
    "customEdges": [],
    "removedEdgeIds": [],
}


class FlowTopologyPayload(BaseModel):
    topology: dict[str, Any] = Field(default_factory=dict)
    # Optional optimistic-lock token: client's last seen row.version
    expected_version: int | None = None


def _normalize_topology(raw: Any) -> dict[str, Any]:
    """Validate/normalize topology for persistence (P0-1).

    Drops garbage via FlowTopology parser, then enforces endpoint existence,
    no self-loops, DAG, and edge-count limits. Raises ValueError on invalid
    documents (callers map to HTTP 400).
    """
    from app.workflow.topology_resolver import validate_topology_document

    return validate_topology_document(raw if isinstance(raw, dict) else None)


@router.get("/entities/{entity_id}/flow-plan")
async def get_flow_plan(
    entity_id: str,
    platforms: str | None = Query(
        None,
        description="Comma-separated enabled platform ids; default = all canvas platforms",
    ),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """3b-2.1: project the deterministic execution plan from current topology."""
    entity = await _require_amway_entity(db, current_user, entity_id)
    row = (
        await db.execute(
            select(FlowTopologyRecord).where(FlowTopologyRecord.entity_id == entity.id)
        )
    ).scalar_one_or_none()
    from app.workflow.node_contracts import FlowTopology
    from app.workflow.topology_resolver import (
        CANVAS_PLATFORM_IDS,
        build_execution_plan_summary,
    )

    topology = FlowTopology.from_dict(
        row.topology if row is not None and isinstance(row.topology, dict) else None
    )
    enabled = None
    if platforms:
        wanted = {p.strip() for p in platforms.split(",") if p.strip()}
        if not wanted:
            raise HTTPException(status_code=400, detail="platforms 参数不能为空")
        enabled = [p for p in CANVAS_PLATFORM_IDS if p in wanted]
        unknown = sorted(wanted - set(CANVAS_PLATFORM_IDS))
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"无效平台参数：{', '.join(unknown)}",
            )
        if not enabled:
            raise HTTPException(status_code=400, detail="无有效平台参数")
    plan = build_execution_plan_summary(topology, enabled_platforms=enabled)
    return {
        "plan": plan,
        "topology": _normalize_topology(
            row.topology if row is not None and isinstance(row.topology, dict) else {}
        ),
    }


@router.get("/entities/{entity_id}/flow-topology")
async def get_flow_topology(
    entity_id: str,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entity = await _require_amway_entity(db, current_user, entity_id)
    row = (
        await db.execute(
            select(FlowTopologyRecord).where(FlowTopologyRecord.entity_id == entity.id)
        )
    ).scalar_one_or_none()
    if row is None:
        return {"topology": dict(_EMPTY_TOPOLOGY), "updated_at": None, "version": 0}
    try:
        topology = _normalize_topology(row.topology)
    except ValueError:
        topology = dict(_EMPTY_TOPOLOGY)
    return {
        "topology": topology,
        "updated_at": _iso(row.updated_at),
        "version": int(row.version or 1),
    }


@router.put("/entities/{entity_id}/flow-topology")
async def put_flow_topology(
    entity_id: str,
    body: FlowTopologyPayload,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entity = await _require_amway_entity(db, current_user, entity_id, manage=True)
    try:
        normalized = _normalize_topology(body.topology)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    row = (
        await db.execute(
            select(FlowTopologyRecord).where(FlowTopologyRecord.entity_id == entity.id)
        )
    ).scalar_one_or_none()
    if row is None:
        if body.expected_version is not None and int(body.expected_version) != 0:
            raise HTTPException(
                status_code=409,
                detail="拓扑版本冲突：记录不存在或已被删除，请重新加载。",
            )
        try:
            row = FlowTopologyRecord(entity_id=entity.id, topology=normalized)
            db.add(row)
            await db.commit()
        except Exception as exc:
            await db.rollback()
            # Unique index race on concurrent first write
            logger = __import__("logging").getLogger(__name__)
            logger.warning("[flow-topology] concurrent create race: %s", exc)
            raise HTTPException(
                status_code=409,
                detail="拓扑正在被其他请求创建，请重试。",
            ) from exc
    else:
        if body.expected_version is not None and int(body.expected_version) != int(
            row.version or 1
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"拓扑版本冲突：期望 version={body.expected_version}，"
                    f"当前 version={row.version}。请重新加载后再保存。"
                ),
            )
        row.topology = normalized
        row.version = int(row.version or 1) + 1
        await db.commit()
    await db.refresh(row)
    return {
        "topology": normalized,
        "updated_at": _iso(row.updated_at),
        "version": int(row.version or 1),
    }


class FlowNodeRunRequest(BaseModel):
    """Optional config overrides for a single custom-node run (3b-1.5)."""

    dimensions: list[str] | None = None
    prompt: str | None = None
    promptTemplate: str | None = None
    use_llm: bool = True
    # 3b-1.6: after this node, also run reachable downstream custom executors
    cascade: bool = False


class FlowBranchRunRequest(BaseModel):
    """Partial topology branch run (blueprint 3b-1.6)."""

    from_node_id: str
    mode: str = "downstream"  # node_only | downstream
    use_llm: bool = True


@router.post("/entities/{entity_id}/flow-nodes/{node_id}/run")
async def run_flow_custom_node(
    entity_id: str,
    node_id: str,
    body: FlowNodeRunRequest | None = None,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """On-demand execution of one analysis/content custom node.

    Loads latest cumulative projection + lexicon + any upstream analysis
    results already stored on the topology. Writes ``config.result`` back to
    the topology document (dual-write with the frontend response).
    """
    entity = await _require_amway_entity(db, current_user, entity_id, manage=True)
    body = body or FlowNodeRunRequest()

    row = (
        await db.execute(
            select(FlowTopologyRecord).where(FlowTopologyRecord.entity_id == entity.id)
        )
    ).scalar_one_or_none()
    topology_raw = (
        row.topology if row is not None and isinstance(row.topology, dict) else {}
    )
    from app.workflow.node_contracts import FlowTopology

    topology = FlowTopology.from_dict(topology_raw)
    target = next((n for n in topology.custom_nodes if n.id == node_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="自定义节点不存在")
    if target.type not in {"analysis", "content"}:
        raise HTTPException(status_code=400, detail="该节点类型不支持独立运行")

    config = dict(target.config or {})
    if body.dimensions is not None:
        config["dimensions"] = body.dimensions
    if body.prompt is not None:
        config["prompt"] = body.prompt
    if body.promptTemplate is not None:
        config["promptTemplate"] = body.promptTemplate

    tracking = AmwayCircleTrackingService(db)
    projection_payload = await tracking.get_projection(entity.id, scope="cumulative")
    projection = _load_projection_body(projection_payload)

    from app.services.amway_flow_custom_node_service import (
        persist_custom_node_results,
        run_analysis_node,
        run_content_node,
        run_custom_branch,
    )

    def _topology_with_patches(patches: dict[str, dict[str, Any]]) -> dict[str, Any]:
        nodes_out = []
        for n in topology.custom_nodes:
            cfg = dict(n.config or {})
            if n.id in patches:
                cfg.update(patches[n.id])
            nodes_out.append(
                {
                    "id": n.id,
                    "type": n.type,
                    "position": n.position,
                    "config": cfg,
                }
            )
        return _normalize_topology(
            {
                "version": topology.version,
                "customNodes": nodes_out,
                "customEdges": [
                    {"id": e.id, "source": e.source, "target": e.target}
                    for e in topology.custom_edges
                ],
                "removedEdgeIds": list(topology.removed_edge_ids),
            }
        )

    if target.type == "analysis" and body.cascade:
        if not projection:
            raise HTTPException(
                status_code=400,
                detail="暂无可用圈层投影，请先完成至少一轮采集。",
            )
        # Apply config overrides onto the start node before branch run
        from dataclasses import replace
        from app.workflow.node_contracts import TopologyNode

        overridden = []
        for n in topology.custom_nodes:
            if n.id == node_id:
                overridden.append(
                    TopologyNode(
                        id=n.id,
                        type=n.type,
                        position=dict(n.position or {}),
                        config=config,
                    )
                )
            else:
                overridden.append(n)
        topology = replace(topology, custom_nodes=tuple(overridden))
        lexicon_payload = await AmwayEntityLexiconService(db).payload_for_entity(
            entity.id
        )
        center_terms = list((projection or {}).get("center_terms") or [])
        center_term = str(
            getattr(entity, "name", None)
            or (center_terms[0] if center_terms else "")
            or "品牌"
        )
        branch_result = await run_custom_branch(
            topology=topology,
            from_node_id=node_id,
            mode="downstream",
            projection=projection,
            report=None,
            lexicon_entries=list(lexicon_payload.get("entries") or []),
            center_term=center_term,
            use_llm=bool(body.use_llm),
        )
        patches = branch_result.get("config_patches") or {}
        if patches:
            await persist_custom_node_results(entity.id, patches)
        if row is not None:
            await db.refresh(row)
            topology_out = _normalize_topology(row.topology)
        else:
            topology_out = _topology_with_patches(patches)
        primary = (branch_result.get("results") or {}).get(node_id) or {}
        return {
            "node_id": node_id,
            "node_type": "analysis",
            "result": primary,
            "ran_node_ids": branch_result.get("ran_node_ids") or [],
            "topology": topology_out,
        }

    if target.type == "analysis":
        if not projection:
            raise HTTPException(
                status_code=400,
                detail="暂无可用圈层投影，请先完成至少一轮采集。",
            )
        result = await run_analysis_node(
            projection=projection,
            report=None,
            config=config,
            use_llm=bool(body.use_llm),
        )
        result_patch = {
            "result": result,
            "dimensions": result.get("dimensions"),
        }
        await persist_custom_node_results(entity.id, {node_id: result_patch})
        if row is not None:
            await db.refresh(row)
            topology_out = _normalize_topology(row.topology)
        else:
            topology_out = _topology_with_patches({node_id: result_patch})
        return {
            "node_id": node_id,
            "node_type": "analysis",
            "result": result,
            "topology": topology_out,
        }

    # content
    lexicon_payload = await AmwayEntityLexiconService(db).payload_for_entity(entity.id)
    lexicon_entries = list(lexicon_payload.get("entries") or [])
    # P2-10: prefer analysis results from wired upstream edges only
    from app.workflow.topology_resolver import custom_incoming_sources

    analysis_result = None
    sources = custom_incoming_sources(topology, node_id)
    analysis_by_id = {
        n.id: (n.config or {}).get("result")
        for n in topology.custom_nodes
        if n.type == "analysis"
    }
    for source in sources:
        stored = analysis_by_id.get(source)
        if isinstance(stored, dict) and stored.get("cards"):
            analysis_result = stored
            break
    if analysis_result is None and "lexicon" in sources:
        # lexicon-only content nodes may still use any analysis as soft context
        for stored in analysis_by_id.values():
            if isinstance(stored, dict) and stored.get("cards"):
                analysis_result = stored
                break
    center_terms = []
    if isinstance(projection, dict):
        center_terms = list(projection.get("center_terms") or [])
    center_term = str(
        getattr(entity, "name", None)
        or (center_terms[0] if center_terms else "")
        or (projection or {}).get("center_term")
        or "品牌"
    )
    result = await run_content_node(
        center_term=center_term,
        lexicon_entries=lexicon_entries,
        analysis_result=analysis_result,
        config=config,
        use_llm=bool(body.use_llm),
    )
    result_patch = {"result": result}
    await persist_custom_node_results(entity.id, {node_id: result_patch})
    if row is not None:
        await db.refresh(row)
        topology_out = _normalize_topology(row.topology)
    else:
        topology_out = _topology_with_patches({node_id: result_patch})
    return {
        "node_id": node_id,
        "node_type": "content",
        "result": result,
        "topology": topology_out,
    }


def _load_projection_body(projection_payload: Any) -> dict[str, Any] | None:
    if not isinstance(projection_payload, dict):
        return None
    nested = projection_payload.get("association_circle_projection")
    if isinstance(nested, dict) and nested:
        return nested
    return None


@router.post("/entities/{entity_id}/flow-branch/run")
async def run_flow_branch(
    entity_id: str,
    body: FlowBranchRunRequest,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run a partial branch of the canvas topology (3b-1.6).

    ``from_node_id`` may be a custom analysis/content node or a builtin seed
    (``projection`` / ``report`` / ``lexicon``). Builtin executors themselves
    are not re-run — only reachable custom analysis/content nodes, using the
    latest cumulative projection + lexicon as inputs.
    """
    entity = await _require_amway_entity(db, current_user, entity_id, manage=True)
    from_node_id = str(body.from_node_id or "").strip()
    if not from_node_id:
        raise HTTPException(status_code=400, detail="from_node_id 不能为空")
    mode = str(body.mode or "downstream").strip().lower()
    if mode not in {"node_only", "downstream"}:
        raise HTTPException(status_code=400, detail="mode 必须是 node_only 或 downstream")

    row = (
        await db.execute(
            select(FlowTopologyRecord).where(FlowTopologyRecord.entity_id == entity.id)
        )
    ).scalar_one_or_none()
    topology_raw = (
        row.topology if row is not None and isinstance(row.topology, dict) else {}
    )
    from app.workflow.node_contracts import FlowTopology
    from app.workflow.topology_resolver import (
        BRANCH_SEED_NODE_IDS,
        branch_custom_executors,
    )

    topology = FlowTopology.from_dict(topology_raw)
    custom_ids = {n.id for n in topology.custom_nodes}
    if from_node_id not in custom_ids and from_node_id not in BRANCH_SEED_NODE_IDS:
        raise HTTPException(
            status_code=404,
            detail="起点节点不存在（需为自定义节点或 projection/report/lexicon）",
        )

    planned = branch_custom_executors(topology, from_node_id, mode=mode)
    if not planned:
        raise HTTPException(
            status_code=400,
            detail="该起点没有可执行的自定义节点分支（请先连线并添加分析/内容节点）",
        )

    # Analysis branch needs projection data.
    needs_projection = any(n.type == "analysis" for n in planned)
    tracking = AmwayCircleTrackingService(db)
    projection_payload = await tracking.get_projection(entity.id, scope="cumulative")
    projection = _load_projection_body(projection_payload)
    if needs_projection and not projection:
        raise HTTPException(
            status_code=400,
            detail="暂无可用圈层投影，请先完成至少一轮采集。",
        )

    lexicon_payload = await AmwayEntityLexiconService(db).payload_for_entity(entity.id)
    lexicon_entries = list(lexicon_payload.get("entries") or [])
    center_terms = list((projection or {}).get("center_terms") or [])
    center_term = str(
        getattr(entity, "name", None)
        or (center_terms[0] if center_terms else "")
        or (projection or {}).get("center_term")
        or "品牌"
    )

    from app.services.amway_flow_custom_node_service import (
        persist_custom_node_results,
        run_custom_branch,
    )

    branch_result = await run_custom_branch(
        topology=topology,
        from_node_id=from_node_id,
        mode=mode,
        projection=projection,
        report=None,
        lexicon_entries=lexicon_entries,
        center_term=center_term,
        use_llm=bool(body.use_llm),
    )
    patches = branch_result.get("config_patches") or {}
    if patches:
        await persist_custom_node_results(entity.id, patches)

    if row is not None:
        await db.refresh(row)
        topology_out = _normalize_topology(row.topology)
    else:
        nodes_out = []
        for n in topology.custom_nodes:
            cfg = dict(n.config or {})
            if n.id in patches:
                cfg.update(patches[n.id])
            nodes_out.append(
                {
                    "id": n.id,
                    "type": n.type,
                    "position": n.position,
                    "config": cfg,
                }
            )
        topology_out = _normalize_topology(
            {
                "version": topology.version,
                "customNodes": nodes_out,
                "customEdges": [
                    {"id": e.id, "source": e.source, "target": e.target}
                    for e in topology.custom_edges
                ],
                "removedEdgeIds": list(topology.removed_edge_ids),
            }
        )

    return {
        "from_node_id": from_node_id,
        "mode": mode,
        "ran_node_ids": branch_result.get("ran_node_ids") or [],
        "results": branch_result.get("results") or {},
        "topology": topology_out,
    }
