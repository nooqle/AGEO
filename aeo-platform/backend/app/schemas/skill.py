"""Skill registry schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SkillVersionResponse(BaseModel):
    id: str
    skill_id: str
    version: int
    config_payload: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class SkillAssignmentResponse(BaseModel):
    id: str
    skill_id: str
    scope_kind: str
    scope_ref: str | None = None
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SkillResponse(BaseModel):
    id: str
    skill_key: str
    family_skill_key: str
    family_display_name: str
    display_name: str
    description: str
    executor_kind: str
    executor_ref: str
    template_skill_key: str | None = None
    intent_signals: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    artifact_types: list[str] = Field(default_factory=list)
    default_params: dict[str, Any] | None = None
    prompt_overlay: str | None = None
    cost_class: str
    latency_class: str
    confirmation_policy: str
    enabled: bool
    assignment_enabled: bool
    effective_enabled: bool
    is_builtin: bool
    is_profile: bool
    version: int
    package_key: str | None = None
    package_display_name: str | None = None
    package_description: str | None = None
    package_path: str | None = None
    created_at: datetime
    updated_at: datetime
    assignments: list[SkillAssignmentResponse] = Field(default_factory=list)


class SkillListResponse(BaseModel):
    skills: list[SkillResponse]


class SkillCreateRequest(BaseModel):
    template_skill_key: str
    display_name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    default_params: dict[str, Any] | None = None
    prompt_overlay: str | None = Field(default=None, max_length=8000)
    enabled: bool = True
    assignment_scope_kind: str = Field(default="global", max_length=16)
    assignment_scope_ref: str | None = Field(default=None, max_length=120)


class SkillUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    default_params: dict[str, Any] | None = None
    prompt_overlay: str | None = Field(default=None, max_length=8000)
    enabled: bool | None = None
    assignment_scope_kind: str | None = Field(default=None, max_length=16)
    assignment_scope_ref: str | None = Field(default=None, max_length=120)


class SkillPublishResponse(BaseModel):
    skill: SkillResponse
    published_version: SkillVersionResponse
