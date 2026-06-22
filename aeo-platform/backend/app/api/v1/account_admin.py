from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_internal_admin_user, get_db
from app.schemas.account_admin import (
    AccountInvitationCreateRequest,
    AccountInvitationResponse,
    AdminUserResponse,
    AdminUserUpdateRequest,
    OrganizationResponse,
    OrganizationUpdateRequest,
)
from app.schemas.user import UserResponse
from app.services.account_admin_service import AccountAdminService
from app.services.organization_feature_service import (
    normalize_organization_feature_flags,
    normalize_user_feature_flags,
)
from app.services.verification_delivery_service import VerificationDeliveryError
from app.services.verification_service import VerificationThrottleError

router = APIRouter(prefix="/account-admin", tags=["account-admin"])


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


def _serialize_organization(organization) -> OrganizationResponse:
    ordered_users = sorted(organization.users, key=lambda item: item.created_at)
    primary_account = None
    if ordered_users:
        primary_account = ordered_users[0].email or ordered_users[0].phone
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


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    _: UserResponse = Depends(get_current_internal_admin_user),
    db: AsyncSession = Depends(get_db),
):
    service = AccountAdminService(db)
    return [_serialize_user(user) for user in await service.list_users()]


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
async def update_user(
    user_id: UUID,
    payload: AdminUserUpdateRequest,
    _: UserResponse = Depends(get_current_internal_admin_user),
    db: AsyncSession = Depends(get_db),
):
    service = AccountAdminService(db)
    changes = {field: getattr(payload, field) for field in payload.model_fields_set}
    try:
        user = await service.update_user(user_id=user_id, changes=changes)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return _serialize_user(user)


@router.post("/invitations", response_model=AccountInvitationResponse)
async def create_account_invitation(
    payload: AccountInvitationCreateRequest,
    current_user: UserResponse = Depends(get_current_internal_admin_user),
    db: AsyncSession = Depends(get_db),
):
    service = AccountAdminService(db)
    try:
        result = await service.create_invitation(
            email=payload.email,
            organization_id=payload.organization_id,
            reviewer_user_id=current_user.id,
            applicant_name=payload.applicant_name,
            job_title=payload.job_title,
            feature_flags=payload.feature_flags,
        )
    except VerificationThrottleError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    except VerificationDeliveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    user = result.get("user")
    application = result.get("application")
    return AccountInvitationResponse.model_validate(
        {
            "status": result.get("status"),
            "email": result.get("email"),
            "feature_flags": result.get("feature_flags") or {},
            "user": _serialize_user(user) if user is not None else None,
            "application": application,
        }
    )


@router.get("/organizations", response_model=list[OrganizationResponse])
async def list_organizations(
    _: UserResponse = Depends(get_current_internal_admin_user),
    db: AsyncSession = Depends(get_db),
):
    service = AccountAdminService(db)
    return [
        _serialize_organization(organization)
        for organization in await service.list_organizations()
    ]


@router.patch("/organizations/{organization_id}", response_model=OrganizationResponse)
async def update_organization(
    organization_id: UUID,
    payload: OrganizationUpdateRequest,
    _: UserResponse = Depends(get_current_internal_admin_user),
    db: AsyncSession = Depends(get_db),
):
    service = AccountAdminService(db)
    changes = {field: getattr(payload, field) for field in payload.model_fields_set}
    try:
        organization = await service.update_organization(
            organization_id=organization_id,
            changes=changes,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return _serialize_organization(organization)
