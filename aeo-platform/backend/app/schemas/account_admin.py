from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.organization import OrganizationStatus
from app.models.user import UserRole, UserStatus
from app.schemas.auth import RegistrationApplicationResponse


class AdminUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr | None
    phone: str | None
    is_active: bool
    status: UserStatus
    role: UserRole
    job_title: str | None
    feature_flags: dict[str, bool] = Field(default_factory=dict)
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
    feature_flags: dict[str, bool] | None = None


class AccountInvitationCreateRequest(BaseModel):
    email: EmailStr
    organization_id: UUID
    applicant_name: str | None = Field(default=None, max_length=255)
    job_title: str | None = Field(default="团队成员", max_length=255)
    feature_flags: dict[str, bool] = Field(default_factory=dict)


class AccountInvitationResponse(BaseModel):
    status: str
    email: EmailStr
    feature_flags: dict[str, bool] = Field(default_factory=dict)
    user: AdminUserResponse | None = None
    application: RegistrationApplicationResponse | None = None


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    legal_name: str
    status: OrganizationStatus
    feature_flags: dict[str, bool] = Field(default_factory=dict)
    primary_account: str | None = None
    member_count: int = 0
    entity_count: int = 0
    created_at: datetime
    updated_at: datetime


class OrganizationUpdateRequest(BaseModel):
    legal_name: str | None = Field(default=None, min_length=2, max_length=255)
    status: OrganizationStatus | None = None
    feature_flags: dict[str, bool] | None = None


class CurrencyCostSummary(BaseModel):
    currency: str
    total_cost: float
    total_cost_cache_aware: float | None
    estimated_savings: float | None
    priced_call_count: int


class BillingCoverage(BaseModel):
    priced_call_count: int = 0
    unknown_pricing_call_count: int = 0
    pricing_coverage: float = 0.0
    cache_known_call_count: int = 0
    cache_unknown_call_count: int = 0
    cache_coverage: float = 0.0
    cache_known_prompt_tokens: int = 0
    costs_by_currency: list[CurrencyCostSummary] = Field(default_factory=list)


class ControlPlaneCustomerSummary(BillingCoverage):
    organization_id: UUID
    customer_name: str
    primary_account: str | None = None
    member_count: int
    brand_count: int
    organization_brand_count: int = 0
    personal_brand_count: int = 0
    tokens_7d: int
    cost_7d: float | None
    currency: str | None = None
    active_task_count: int
    last_active_at: datetime | None = None


class ControlPlaneTaskSummary(BillingCoverage):
    task_id: UUID
    organization_id: UUID | None = None
    customer_name: str | None = None
    brand_name: str
    session_id: UUID | None
    entity_id: UUID | None
    visibility_scope: str | None = None
    initiator_account: str | None = None
    status: str
    llm_total_tokens: int
    llm_estimated_cost: float | None
    llm_estimated_cost_cache_aware: float | None = None
    currency: str | None = None
    llm_cached_prompt_tokens: int = 0
    llm_billable_prompt_tokens: int = 0
    llm_total_latency_ms: int
    updated_at: datetime


class ControlPlaneEntitySummary(BaseModel):
    id: UUID
    name: str
    visibility_scope: str
    owner_account: str | None = None
    last_analyzed: datetime | None
    updated_at: datetime


class ControlPlaneCustomerDetail(BaseModel):
    organization: OrganizationResponse
    summary: ControlPlaneCustomerSummary
    users: list[AdminUserResponse]
    entities: list[ControlPlaneEntitySummary]
    recent_tasks: list[ControlPlaneTaskSummary]


class ControlPlaneObservabilitySummary(BillingCoverage):
    days: int
    call_count: int
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    cached_prompt_tokens: int
    billable_prompt_tokens: int
    cache_hit_ratio: float | None
    total_cost: float | None
    total_cost_cache_aware: float | None
    estimated_savings: float | None
    currency: str | None = None
    total_latency_ms: int
    avg_latency_ms: float
    unique_models: int
    diagnostic_sample_count: int = 0
    low_cache_call_count: int = 0
    low_cache_call_ratio: float = 0.0
    static_prompt_variant_count: int = 0
    tool_surface_variant_count: int = 0
    model_identity_variant_count: int = 0
    avg_runtime_context_size: int | None = None
    max_runtime_context_size: int | None = None
    runtime_context_known_call_count: int = 0
    first_call_at: datetime | None = None
    last_call_at: datetime | None = None


class ControlPlaneReuseDiagnostic(BaseModel):
    severity: str
    code: str
    title: str
    message: str
    affected_count: int = 0
    ratio: float | None = None


class ControlPlaneCostBreakdown(BillingCoverage):
    organization_id: UUID | None = None
    customer_name: str | None = None
    brand_name: str | None = None
    provider: str | None = None
    model_name: str | None = None
    step: str | None = None
    step_name: str | None = None
    call_count: int
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int = 0
    cached_prompt_tokens: int
    billable_prompt_tokens: int = 0
    cache_hit_ratio: float | None
    total_cost: float | None
    total_cost_cache_aware: float | None
    estimated_savings: float | None
    currency: str | None = None
    total_latency_ms: int
    avg_latency_ms: float


class ControlPlaneRecentCall(BaseModel):
    cost_scope: str = "token_estimate"
    provider_web_search_requests: int | None = None
    search_tool_cost_status: str = "not_reported"
    estimated_search_tool_cost: float | None = None
    search_tool_currency: str | None = None
    usage_time_basis: str = "legacy_unknown"
    cost_is_estimate: bool = True
    pricing_status: str = "legacy_unknown"
    cache_status: str = "legacy_unknown"
    pricing: dict | None = None
    id: UUID
    task_id: UUID | None = None
    session_id: UUID | None = None
    organization_id: UUID | None = None
    customer_name: str | None = None
    brand_name: str
    provider: str
    model_name: str
    step: str | None = None
    step_name: str | None = None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_prompt_tokens: int
    billable_prompt_tokens: int
    cache_hit_ratio: float | None
    latency_ms: int
    estimated_cost: float | None
    estimated_cost_cache_aware: float | None
    estimated_savings: float | None
    currency: str | None = None
    static_prompt_hash: str | None = None
    tool_surface_hash: str | None = None
    model_identity: str | None = None
    runtime_context_size: int | None = None
    runtime_reminder_enabled: bool | None = None
    stable_tool_surface_enabled: bool | None = None
    stable_skill_tool_description_enabled: bool | None = None
    reuse_diagnosis: str | None = None
    created_at: datetime | None = None


class ControlPlaneObservabilitySnapshot(BaseModel):
    summary: ControlPlaneObservabilitySummary
    reuse_diagnostics: list[ControlPlaneReuseDiagnostic] = []
    by_customer_brand: list[ControlPlaneCostBreakdown]
    by_model: list[ControlPlaneCostBreakdown]
    by_step: list[ControlPlaneCostBreakdown]
    recent_calls: list[ControlPlaneRecentCall]
