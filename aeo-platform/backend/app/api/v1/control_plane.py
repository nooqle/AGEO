from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_internal_admin_user, get_db
from app.models.task import TaskStatus
from app.schemas.account_admin import (
    AdminUserResponse,
    ControlPlaneCostBreakdown,
    ControlPlaneCustomerDetail,
    ControlPlaneCustomerSummary,
    ControlPlaneEntitySummary,
    ControlPlaneObservabilitySnapshot,
    ControlPlaneObservabilitySummary,
    ControlPlaneRecentCall,
    ControlPlaneReuseDiagnostic,
    ControlPlaneTaskSummary,
    OrganizationResponse,
)
from app.schemas.user import UserResponse
from app.services.control_plane_service import ControlPlaneService
from app.services.organization_feature_service import (
    normalize_organization_feature_flags,
    normalize_user_feature_flags,
)

router = APIRouter(prefix="/control-plane", tags=["control-plane"])


def _serialize_org(organization) -> OrganizationResponse:
    users = sorted(organization.users, key=lambda item: item.created_at)
    primary_account = None
    if users:
        primary_account = users[0].email or users[0].phone
    return OrganizationResponse.model_validate(
        {
            **organization.__dict__,
            "feature_flags": normalize_organization_feature_flags(
                getattr(organization, "feature_flags", None)
            ),
            "primary_account": primary_account,
            "member_count": len(organization.users),
            "entity_count": len(organization.entities),
        }
    )


def _serialize_user(user) -> AdminUserResponse:
    return AdminUserResponse.model_validate(
        {
            **user.__dict__,
            "feature_flags": normalize_user_feature_flags(
                getattr(user, "feature_flags", None)
            ),
            "organization_name": (
                user.organization.legal_name if user.organization is not None else None
            ),
        }
    )


@router.get("/customers", response_model=list[ControlPlaneCustomerSummary])
async def list_customers(
    days: int = Query(default=7, ge=1, le=90),
    _: UserResponse = Depends(get_current_internal_admin_user),
    db: AsyncSession = Depends(get_db),
):
    service = ControlPlaneService(db)
    return [
        ControlPlaneCustomerSummary.model_validate(item)
        for item in await service.list_customers(days=days)
    ]


@router.get("/tasks", response_model=list[ControlPlaneTaskSummary])
async def list_control_plane_tasks(
    days: int = Query(default=7, ge=1, le=90),
    status_filter: TaskStatus | None = Query(default=None, alias="status"),
    organization_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=300),
    _: UserResponse = Depends(get_current_internal_admin_user),
    db: AsyncSession = Depends(get_db),
):
    service = ControlPlaneService(db)
    tasks = await service.list_tasks(
        days=days,
        status=status_filter,
        organization_id=organization_id,
        limit=limit,
    )
    billing = await service.get_task_billing([task.id for task in tasks])
    return [
        ControlPlaneTaskSummary(
            task_id=task.id,
            organization_id=(
                task.user.organization_id if task.user is not None else None
            ),
            customer_name=(
                task.user.organization.legal_name
                if task.user is not None and task.user.organization is not None
                else None
            ),
            brand_name=task.brand_name,
            session_id=task.session_id,
            entity_id=task.entity_id,
            visibility_scope=(
                task.entity.visibility_scope.value
                if task.entity is not None and task.entity.visibility_scope is not None
                else None
            ),
            initiator_account=(
                (task.user.email or task.user.phone) if task.user is not None else None
            ),
            status=task.status.value,
            llm_total_tokens=task.llm_total_tokens,
            llm_estimated_cost=billing[task.id]["total_cost"],
            llm_estimated_cost_cache_aware=billing[task.id]["total_cost_cache_aware"],
            **billing[task.id],
            llm_cached_prompt_tokens=task.llm_cached_prompt_tokens,
            llm_billable_prompt_tokens=task.llm_billable_prompt_tokens,
            llm_total_latency_ms=task.llm_total_latency_ms,
            updated_at=task.updated_at,
        )
        for task in tasks
    ]


@router.get(
    "/observability",
    response_model=ControlPlaneObservabilitySnapshot,
)
async def get_control_plane_observability(
    days: int = Query(default=30, ge=1, le=90),
    organization_id: UUID | None = Query(default=None),
    limit: int = Query(default=12, ge=1, le=50),
    _: UserResponse = Depends(get_current_internal_admin_user),
    db: AsyncSession = Depends(get_db),
):
    service = ControlPlaneService(db)
    payload = await service.get_observability_snapshot(
        days=days,
        organization_id=organization_id,
        limit=limit,
    )
    return ControlPlaneObservabilitySnapshot(
        summary=ControlPlaneObservabilitySummary.model_validate(payload["summary"]),
        reuse_diagnostics=[
            ControlPlaneReuseDiagnostic.model_validate(item)
            for item in payload["reuse_diagnostics"]
        ],
        by_customer_brand=[
            ControlPlaneCostBreakdown.model_validate(item)
            for item in payload["by_customer_brand"]
        ],
        by_model=[
            ControlPlaneCostBreakdown.model_validate(item)
            for item in payload["by_model"]
        ],
        by_step=[
            ControlPlaneCostBreakdown.model_validate(item)
            for item in payload["by_step"]
        ],
        recent_calls=[
            ControlPlaneRecentCall.model_validate(item)
            for item in payload["recent_calls"]
        ],
    )


@router.get(
    "/customers/{organization_id}",
    response_model=ControlPlaneCustomerDetail,
)
async def get_customer_detail(
    organization_id: UUID,
    days: int = Query(default=7, ge=1, le=90),
    recent_task_limit: int = Query(default=20, ge=1, le=100),
    _: UserResponse = Depends(get_current_internal_admin_user),
    db: AsyncSession = Depends(get_db),
):
    service = ControlPlaneService(db)
    try:
        payload = await service.get_customer_detail(
            organization_id=organization_id,
            days=days,
            recent_task_limit=recent_task_limit,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    billing = await service.get_task_billing([task.id for task in payload["recent_tasks"]])

    return ControlPlaneCustomerDetail(
        organization=_serialize_org(payload["organization"]),
        summary=ControlPlaneCustomerSummary.model_validate(payload["summary"]),
        users=[_serialize_user(user) for user in payload["users"]],
        entities=[
            ControlPlaneEntitySummary.model_validate(
                {
                    "id": entity.id,
                    "name": entity.name,
                    "visibility_scope": entity.visibility_scope.value,
                    "owner_account": (
                        (entity.owner.email or entity.owner.phone)
                        if entity.owner is not None
                        else None
                    ),
                    "last_analyzed": entity.last_analyzed,
                    "updated_at": entity.updated_at,
                }
            )
            for entity in payload["entities"]
        ],
        recent_tasks=[
            ControlPlaneTaskSummary(
                task_id=task.id,
                organization_id=(
                    task.user.organization_id if task.user is not None else None
                ),
                customer_name=(
                    task.user.organization.legal_name
                    if task.user is not None and task.user.organization is not None
                    else None
                ),
                brand_name=task.brand_name,
                session_id=task.session_id,
                entity_id=task.entity_id,
                visibility_scope=(
                    task.entity.visibility_scope.value
                    if task.entity is not None
                    and task.entity.visibility_scope is not None
                    else None
                ),
                initiator_account=(
                    (task.user.email or task.user.phone)
                    if task.user is not None
                    else None
                ),
                status=task.status.value,
                llm_total_tokens=task.llm_total_tokens,
                llm_estimated_cost=billing[task.id]["total_cost"],
                llm_estimated_cost_cache_aware=billing[task.id]["total_cost_cache_aware"],
                **billing[task.id],
                llm_cached_prompt_tokens=task.llm_cached_prompt_tokens,
                llm_billable_prompt_tokens=task.llm_billable_prompt_tokens,
                llm_total_latency_ms=task.llm_total_latency_ms,
                updated_at=task.updated_at,
            )
            for task in payload["recent_tasks"]
        ],
    )
