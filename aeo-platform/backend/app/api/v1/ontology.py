"""Ontology object graph API endpoints."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.brand_intelligence import BrandActionRecord, BrandIntelligenceFinding
from app.services.brand_action_service import BrandActionService
from app.services.brand_ontology_object_service import BrandOntologyObjectService
from app.services.brand_ontology_world_service import BrandOntologyWorldService
from app.services.entity_service import EntityService

router = APIRouter(prefix="/ontology", tags=["ontology"])


class IntelligenceFindingFeedbackRequest(BaseModel):
    feedback_type: Literal["validate", "dismiss", "correct"]
    feedback_text: str | None = Field(default=None, max_length=1000)
    origin_event_id: str | None = Field(default=None, max_length=120)


class OntologyActionFeedbackRequest(BaseModel):
    feedback_type: Literal["confirm", "defer", "provide_input"]
    feedback_text: str | None = Field(default=None, max_length=1000)
    provided_inputs: dict[str, Any] | None = Field(default=None)
    origin_event_id: str | None = Field(default=None, max_length=120)


class RecommendationTaskRequest(BaseModel):
    task_status: Literal[
        "not_started",
        "in_progress",
        "completed",
        "review_pending",
    ]
    owner_label: str | None = Field(default=None, max_length=80)
    due_at: str | None = Field(default=None, max_length=40)
    review_at: str | None = Field(default=None, max_length=40)
    feedback_text: str | None = Field(default=None, max_length=1000)
    origin_event_id: str | None = Field(default=None, max_length=120)


def _parse_uuid(value: str, field_name: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid UUID for {field_name}: {value}",
        )


async def _require_accessible_entity(
    *,
    db: AsyncSession,
    entity_id: str,
    current_user,
) -> UUID:
    entity_uuid = _parse_uuid(entity_id, "entity_id")
    entity = await EntityService(db).get_entity_model(
        str(entity_uuid),
        current_user,
        allow_internal_admin_bypass=False,
    )
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found",
        )
    return entity_uuid


@router.get("/entities/{entity_id}/world")
async def get_ontology_world(
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get the Dashboard-facing brand object world summary."""

    entity_uuid = await _require_accessible_entity(
        db=db,
        entity_id=entity_id,
        current_user=current_user,
    )
    world_service = BrandOntologyWorldService(db)
    entity_model = await EntityService(db).get_entity_model(
        str(entity_uuid),
        current_user,
        allow_internal_admin_bypass=False,
    )
    if entity_model is not None:
        fast_payload = await world_service.build_association_circle_dashboard_summary(
            entity_id=entity_uuid,
            entity_name=getattr(entity_model, "name", None),
            entity_domain=getattr(entity_model, "domain", None),
            entity_aliases=getattr(entity_model, "aliases", None),
        )
        if fast_payload is not None:
            return fast_payload

    backfill_result = await world_service.ensure_legacy_backfill(entity_id=entity_uuid)
    if isinstance(backfill_result, dict) and backfill_result.get("changed"):
        BrandOntologyWorldService.invalidate_cache(entity_uuid)
    payload = await world_service.build_dashboard_summary(
        entity_id=entity_uuid,
        actor_id=current_user.id,
    )
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brand world not found",
        )
    return payload


@router.get("/entities/{entity_id}/objects/{object_type}")
async def list_ontology_objects(
    entity_id: str,
    object_type: str,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    created_after: Annotated[datetime | None, Query()] = None,
    created_before: Annotated[datetime | None, Query()] = None,
    sort: Annotated[str, Query()] = "created_at_desc",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List ontology objects of one type within an accessible brand entity."""

    entity_uuid = await _require_accessible_entity(
        db=db,
        entity_id=entity_id,
        current_user=current_user,
    )
    service = BrandOntologyObjectService(db)
    try:
        return await service.list_objects(
            entity_id=entity_uuid,
            object_type=object_type,
            status=status_filter,
            created_after=created_after,
            created_before=created_before,
            sort=sort,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("/entities/{entity_id}/objects/{object_type}/{object_id}")
async def get_ontology_object(
    entity_id: str,
    object_type: str,
    object_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get one ontology object within an accessible brand entity."""

    entity_uuid = await _require_accessible_entity(
        db=db,
        entity_id=entity_id,
        current_user=current_user,
    )
    service = BrandOntologyObjectService(db)
    try:
        payload = await service.get_object(
            entity_id=entity_uuid,
            object_type=object_type,
            object_id=object_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Object not found",
        )
    return payload


@router.get("/entities/{entity_id}/objects/{object_type}/{object_id}/links")
async def list_ontology_object_links(
    entity_id: str,
    object_type: str,
    object_id: str,
    direction: str = Query("both", pattern="^(in|out|both)$"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """List relationships around one ontology object."""

    entity_uuid = await _require_accessible_entity(
        db=db,
        entity_id=entity_id,
        current_user=current_user,
    )
    service = BrandOntologyObjectService(db)
    try:
        links = await service.list_links(
            entity_id=entity_uuid,
            object_type=object_type,
            object_id=object_id,
            direction=direction,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if links is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Object not found",
        )
    return {"links": links, "total": len(links)}


@router.post("/entities/{entity_id}/findings/{finding_id}/feedback")
async def submit_intelligence_finding_feedback(
    entity_id: str,
    finding_id: str,
    body: IntelligenceFindingFeedbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Record user feedback against one durable intelligence finding."""

    entity_uuid = await _require_accessible_entity(
        db=db,
        entity_id=entity_id,
        current_user=current_user,
    )
    finding_uuid = _parse_uuid(finding_id, "finding_id")
    try:
        record, finding = await BrandActionService(
            db,
        ).record_intelligence_finding_feedback(
            entity_id=entity_uuid,
            finding_id=finding_uuid,
            user_id=current_user.id,
            feedback_type=body.feedback_type,
            feedback_text=body.feedback_text,
            origin_event_id=body.origin_event_id,
        )
        await db.commit()
        BrandOntologyWorldService.invalidate_cache(entity_uuid)
    except PermissionError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        await db.rollback()
        status_code = (
            status.HTTP_404_NOT_FOUND
            if "not found" in str(exc).lower()
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    world = await BrandOntologyWorldService(db).build_dashboard_summary(
        entity_id=entity_uuid,
        actor_id=current_user.id,
        force_refresh=True,
    )
    return {
        "action_record": _public_action_record(record),
        "finding": _public_intelligence_finding(finding),
        "world": world,
    }


@router.post("/entities/{entity_id}/actions/{action_key}/feedback")
async def submit_ontology_action_feedback(
    entity_id: str,
    action_key: str,
    body: OntologyActionFeedbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Record user feedback against one recommended ontology action."""

    entity_uuid = await _require_accessible_entity(
        db=db,
        entity_id=entity_id,
        current_user=current_user,
    )
    action_service = BrandActionService(db)
    world_service = BrandOntologyWorldService(db)
    try:
        action_definition = action_service.registry.require_action_type(action_key)
        current_world = await world_service.build_dashboard_summary(
            entity_id=entity_uuid,
            actor_id=current_user.id,
            force_refresh=True,
        )
        queue_item = _find_action_queue_item(current_world, action_key)
        if queue_item is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Action is not in the current ontology action queue",
            )
        _validate_action_feedback_request(queue_item, body.feedback_type)
        provided_inputs = _build_action_feedback_provided_inputs(
            queue_item=queue_item,
            body=body,
        )
        origin_event_id = (
            body.origin_event_id
            or _action_feedback_origin_event_id(
                entity_id=entity_uuid,
                action_key=action_key,
                feedback_type=body.feedback_type,
                user_id=current_user.id,
                feedback_text=body.feedback_text,
                provided_inputs=provided_inputs,
            )
        )
        record = await action_service.record_applied_action(
            entity_id=entity_uuid,
            user_id=current_user.id,
            actor_type="user",
            origin_surface="dashboard_action_queue",
            origin_event_id=origin_event_id,
            action_type="record_user_feedback",
            input_payload={
                "actor_id": str(current_user.id),
                "feedback_type": f"action_queue_{body.feedback_type}",
                "target_action_key": action_key,
                "target_action_display_name": action_definition.display_name,
                "feedback_text": body.feedback_text,
                **(
                    {"provided_inputs": provided_inputs}
                    if provided_inputs
                    else {}
                ),
            },
            output_payload={
                "target_action_key": action_key,
                "feedback_type": body.feedback_type,
                "provided_input_keys": sorted(provided_inputs.keys()),
            },
            decision_type="ontology_action_queue_feedback",
            decision_key=f"{action_key}:{body.feedback_type}",
            target_object_type="brand_entity",
            target_object_id=str(entity_uuid),
            feedback_text=body.feedback_text or action_definition.display_name,
        )
        await db.commit()
        BrandOntologyWorldService.invalidate_cache(entity_uuid)
    except PermissionError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    world = await world_service.build_dashboard_summary(
        entity_id=entity_uuid,
        actor_id=current_user.id,
        force_refresh=True,
    )
    return {
        "action_record": _public_action_record(record),
        "world": world,
    }


@router.post("/entities/{entity_id}/recommendations/{recommendation_id}/task")
async def submit_recommendation_task_feedback(
    entity_id: str,
    recommendation_id: str,
    body: RecommendationTaskRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Record a follow-up task state for one recommendation."""

    entity_uuid = await _require_accessible_entity(
        db=db,
        entity_id=entity_id,
        current_user=current_user,
    )
    world_service = BrandOntologyWorldService(db)
    action_service = BrandActionService(db)
    try:
        current_world = await world_service.build_dashboard_summary(
            entity_id=entity_uuid,
            actor_id=current_user.id,
            force_refresh=True,
        )
        recommendation = _find_recommendation_item(
            current_world,
            recommendation_id,
        )
        if recommendation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recommendation not found",
            )
        origin_event_id = body.origin_event_id or _recommendation_task_origin_event_id(
            entity_id=entity_uuid,
            recommendation_id=recommendation_id,
            user_id=current_user.id,
            task_status=body.task_status,
            owner_label=body.owner_label,
            due_at=body.due_at,
            review_at=body.review_at,
            feedback_text=body.feedback_text,
        )
        input_payload = {
            "actor_id": str(current_user.id),
            "feedback_type": "recommendation_task_update",
            "recommendation_id": recommendation_id,
            "recommendation_title": recommendation.get("title"),
            "task_status": body.task_status,
            "owner_label": body.owner_label or "",
            "due_at": body.due_at or "",
            "review_at": body.review_at or "",
            "feedback_text": body.feedback_text or "",
        }
        record = await action_service.record_applied_action(
            entity_id=entity_uuid,
            user_id=current_user.id,
            actor_type="user",
            origin_surface="dashboard_recommendation_task",
            origin_event_id=origin_event_id,
            action_type="record_user_feedback",
            input_payload=input_payload,
            output_payload={
                "recommendation_id": recommendation_id,
                "task_state": body.task_status,
                "target_metric": recommendation.get("target_metric"),
            },
            decision_type="recommendation_task",
            decision_key=f"recommendation:{recommendation_id}",
            target_object_type="brand_entity",
            target_object_id=str(entity_uuid),
            feedback_text=body.feedback_text or str(recommendation.get("title") or ""),
            strict_input_validation=True,
        )
        await db.commit()
        BrandOntologyWorldService.invalidate_cache(entity_uuid)
    except PermissionError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    world = await world_service.build_dashboard_summary(
        entity_id=entity_uuid,
        actor_id=current_user.id,
        force_refresh=True,
    )
    return {
        "action_record": _public_action_record(record),
        "recommendation": _find_recommendation_item(world, recommendation_id),
        "world": world,
    }


@router.get("/entities/{entity_id}/views/{view_key}/{object_type}/{object_id}")
async def get_ontology_object_view(
    entity_id: str,
    view_key: str,
    object_type: str,
    object_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get an ontology object with its registered view and relationships."""

    entity_uuid = await _require_accessible_entity(
        db=db,
        entity_id=entity_id,
        current_user=current_user,
    )
    service = BrandOntologyObjectService(db)
    try:
        payload = await service.get_object_view(
            entity_id=entity_uuid,
            object_type=object_type,
            object_id=object_id,
            view_key=view_key,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Object view not found",
        )
    return payload


def _public_action_record(record: BrandActionRecord) -> dict[str, object]:
    return {
        "id": str(record.id),
        "entity_id": str(record.entity_id),
        "user_id": str(record.user_id) if record.user_id else None,
        "actor_type": record.actor_type,
        "action_type": record.action_type,
        "status": record.status,
        "requires_confirmation": record.requires_confirmation,
        "permission_scope": record.permission_scope,
        "origin_surface": record.origin_surface,
        "origin_event_id": record.origin_event_id,
        "submitted_at": record.submitted_at.isoformat(),
        "completed_at": record.completed_at.isoformat()
        if record.completed_at
        else None,
    }


def _public_intelligence_finding(
    finding: BrandIntelligenceFinding,
) -> dict[str, object]:
    return {
        "object_id": str(finding.id),
        "title": finding.title,
        "summary": finding.summary,
        "finding_type": finding.finding_type,
        "severity": finding.severity,
        "confidence": finding.confidence,
        "status": finding.status,
        "evidence_summary": finding.evidence_summary,
        "supporting_question_count": finding.supporting_question_count,
        "supporting_answer_count": finding.supporting_answer_count,
        "supporting_citation_count": finding.supporting_citation_count,
        "suggested_action_type": finding.suggested_action_type,
        "updated_at": finding.updated_at.isoformat(),
    }


def _action_feedback_origin_event_id(
    *,
    entity_id: UUID,
    action_key: str,
    feedback_type: str,
    user_id: UUID,
    feedback_text: str | None,
    provided_inputs: dict[str, Any] | None = None,
) -> str:
    canonical = json.dumps(
        {
            "entity_id": str(entity_id),
            "action_key": action_key,
            "feedback_type": feedback_type,
            "user_id": str(user_id),
            "feedback_text": feedback_text or "",
            "provided_inputs": provided_inputs or {},
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:16]
    return f"action-feedback:{action_key}:{feedback_type}:{digest}"


def _find_action_queue_item(
    world: dict[str, Any],
    action_key: str,
) -> dict[str, Any] | None:
    normalized_action_key = str(action_key or "").strip()
    for raw_item in world.get("action_queue") or []:
        if not isinstance(raw_item, dict):
            continue
        if str(raw_item.get("action_key") or "").strip() == normalized_action_key:
            return raw_item
    return None


def _find_recommendation_item(
    world: dict[str, Any] | None,
    recommendation_id: str,
) -> dict[str, Any] | None:
    normalized_id = str(recommendation_id or "").strip()
    if not normalized_id or not isinstance(world, dict):
        return None
    projection = world.get("recommendation_projection") or {}
    if not isinstance(projection, dict):
        return None
    for raw_item in projection.get("recommendations") or []:
        if not isinstance(raw_item, dict):
            continue
        if str(raw_item.get("id") or "").strip() == normalized_id:
            return raw_item
    return None


def _recommendation_task_origin_event_id(
    *,
    entity_id: UUID,
    recommendation_id: str,
    user_id: UUID,
    task_status: str,
    owner_label: str | None,
    due_at: str | None,
    review_at: str | None,
    feedback_text: str | None,
) -> str:
    canonical = json.dumps(
        {
            "entity_id": str(entity_id),
            "recommendation_id": str(recommendation_id or ""),
            "user_id": str(user_id),
            "task_status": task_status,
            "owner_label": owner_label or "",
            "due_at": due_at or "",
            "review_at": review_at or "",
            "feedback_text": feedback_text or "",
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:16]
    return f"recommendation-task:{recommendation_id}:{task_status}:{digest}"


def _validate_action_feedback_request(
    queue_item: dict[str, Any],
    feedback_type: str,
) -> None:
    readiness = str(queue_item.get("readiness") or "").strip()
    if feedback_type == "confirm" and readiness != "needs_confirmation":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Action is not waiting for confirmation",
        )
    if feedback_type == "provide_input" and readiness not in {
        "needs_input",
        "ready_with_defaults",
    }:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Action is not waiting for additional input",
        )


def _build_action_feedback_provided_inputs(
    *,
    queue_item: dict[str, Any],
    body: OntologyActionFeedbackRequest,
) -> dict[str, Any]:
    if body.feedback_type != "provide_input":
        return {}
    missing_inputs = [
        str(item).strip()
        for item in (queue_item.get("missing_inputs") or [])
        if str(item).strip()
    ]
    defaulted_inputs = [
        str((item or {}).get("input_key") or "").strip()
        for item in (queue_item.get("defaulted_inputs") or [])
        if isinstance(item, dict) and str((item or {}).get("input_key") or "").strip()
    ]
    allowed_inputs = set(missing_inputs + defaulted_inputs)
    raw_inputs = _coerce_provided_inputs(body.provided_inputs, body.feedback_text)
    _validate_provided_inputs_budget(raw_inputs)
    if not raw_inputs and len(missing_inputs) == 1:
        text = str(body.feedback_text or "").strip()
        if text:
            raw_inputs = {missing_inputs[0]: text}
            _validate_provided_inputs_budget(raw_inputs)

    provided_inputs: dict[str, Any] = {}
    for key, value in raw_inputs.items():
        normalized_key = str(key or "").strip()
        if normalized_key not in allowed_inputs:
            continue
        if _payload_has_value(value):
            provided_inputs[normalized_key] = value

    if not provided_inputs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Action input feedback must include at least one missing input",
        )
    return provided_inputs


def _coerce_provided_inputs(
    provided_inputs: dict[str, Any] | None,
    feedback_text: str | None,
) -> dict[str, Any]:
    if isinstance(provided_inputs, dict):
        return dict(provided_inputs)
    text = str(feedback_text or "").strip()
    if not text.startswith("{"):
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _validate_provided_inputs_budget(raw_inputs: dict[str, Any]) -> None:
    if not raw_inputs:
        return
    if len(raw_inputs) > 20:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Action input feedback contains too many fields",
        )
    try:
        encoded = json.dumps(raw_inputs, ensure_ascii=False, sort_keys=True)
    except TypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Action input feedback must be JSON serializable",
        ) from exc
    if len(encoded) > 4000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Action input feedback is too large",
        )


def _payload_has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True
