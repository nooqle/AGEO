from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_internal_admin_user, get_db
from app.schemas.account_admin import (
    AdminUserResponse,
    ControlPlaneCustomerDetail,
    ControlPlaneCustomerSummary,
    ControlPlaneEntitySummary,
    ControlPlaneTaskSummary,
    OrganizationResponse,
)
from app.schemas.user import UserResponse
from app.services.control_plane_service import ControlPlaneService

router = APIRouter(prefix="/control-plane", tags=["control-plane"])


def _serialize_org(organization) -> OrganizationResponse:
    users = sorted(organization.users, key=lambda item: item.created_at)
    primary_account = None
    if users:
        primary_account = users[0].email or users[0].phone
    return OrganizationResponse.model_validate(
        {
            **organization.__dict__,
            "primary_account": primary_account,
            "member_count": len(organization.users),
            "entity_count": len(organization.entities),
        }
    )


def _serialize_user(user) -> AdminUserResponse:
    return AdminUserResponse.model_validate(
        {
            **user.__dict__,
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
                    "last_analyzed": entity.last_analyzed,
                    "updated_at": entity.updated_at,
                }
            )
            for entity in payload["entities"]
        ],
        recent_tasks=[
            ControlPlaneTaskSummary(
                task_id=task.id,
                brand_name=task.brand_name,
                session_id=task.session_id,
                entity_id=task.entity_id,
                status=task.status.value,
                llm_total_tokens=task.llm_total_tokens,
                llm_estimated_cost=task.llm_estimated_cost,
                llm_total_latency_ms=task.llm_total_latency_ms,
                updated_at=task.updated_at,
            )
            for task in payload["recent_tasks"]
        ],
    )
