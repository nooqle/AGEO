from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.organization import OrganizationStatus
from app.models.user import UserRole, UserStatus


class AdminUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr | None
    phone: str | None
    is_active: bool
    status: UserStatus
    role: UserRole
    job_title: str | None
    organization_id: UUID | None
    organization_name: str | None = None
    created_at: datetime
    updated_at: datetime


class AdminUserUpdateRequest(BaseModel):
    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=6, max_length=32)
    job_title: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    status: UserStatus | None = None
    organization_id: UUID | None = None


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    legal_name: str
    status: OrganizationStatus
    primary_account: str | None = None
    member_count: int = 0
    entity_count: int = 0
    created_at: datetime
    updated_at: datetime


class OrganizationUpdateRequest(BaseModel):
    legal_name: str | None = Field(default=None, min_length=2, max_length=255)
    status: OrganizationStatus | None = None


class ControlPlaneCustomerSummary(BaseModel):
    organization_id: UUID
    customer_name: str
    primary_account: str | None = None
    member_count: int
    brand_count: int
    tokens_7d: int
    cost_7d: float
    active_task_count: int
    last_active_at: datetime | None = None


class ControlPlaneTaskSummary(BaseModel):
    task_id: UUID
    brand_name: str
    session_id: UUID | None
    entity_id: UUID | None
    status: str
    llm_total_tokens: int
    llm_estimated_cost: float
    llm_total_latency_ms: int
    updated_at: datetime


class ControlPlaneEntitySummary(BaseModel):
    id: UUID
    name: str
    visibility_scope: str
    last_analyzed: datetime | None
    updated_at: datetime


class ControlPlaneCustomerDetail(BaseModel):
    organization: OrganizationResponse
    summary: ControlPlaneCustomerSummary
    users: list[AdminUserResponse]
    entities: list[ControlPlaneEntitySummary]
    recent_tasks: list[ControlPlaneTaskSummary]
