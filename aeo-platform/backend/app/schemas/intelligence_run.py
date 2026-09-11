from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.platform_fetch_methods import resolve_platform_fetch_methods


BrandIntelligenceRunStatusLiteral = Literal[
    "not_started",
    "planning_questions",
    "waiting_scope_confirmation",
    "fetching_answers",
    "waiting_takeover",
    "analyzing_metrics",
    "building_world",
    "generating_recommendations",
    "waiting_user",
    "completed",
    "failed",
    "cancelled",
]


class BrandIntelligenceRunCreate(BaseModel):
    run_goal: str | None = Field(default=None, max_length=1000)
    analysis_mode: str = Field(default="panorama", max_length=40)
    input_scope: dict[str, Any] | None = Field(default=None)
    origin_surface: str = Field(default="dashboard", max_length=80)
    origin_session_id: str | None = Field(default=None, max_length=80)
    origin_event_id: str | None = Field(default=None, max_length=160)
    auto_dispatch: bool = Field(default=True)


    @field_validator("input_scope")
    @classmethod
    def validate_platform_methods(cls, value):
        if isinstance(value, dict) and "platform_fetch_methods" in value:
            resolve_platform_fetch_methods(
                value["platform_fetch_methods"], platforms=value.get("platforms"),
                fetch_mode=value.get("fetch_mode", "fast"), explicit=True,
            )
        return value


class BrandIntelligenceRunConfirm(BaseModel):
    user_action_type: str | None = Field(default=None, max_length=80)
    feedback_text: str | None = Field(default=None, max_length=1000)
    provided_inputs: dict[str, Any] | None = Field(default=None)
    origin_event_id: str | None = Field(default=None, max_length=160)


class BrandIntelligenceRunResponse(BaseModel):
    id: str
    entity_id: str
    created_by_user_id: str | None = None
    origin_session_id: str | None = None
    analysis_task_id: str | None = None
    origin_surface: str
    origin_event_id: str | None = None
    status: BrandIntelligenceRunStatusLiteral
    stage: str
    progress: float
    message: str
    run_goal: str
    analysis_mode: str
    input_scope: dict[str, Any] | None = None
    sample_scope: dict[str, Any] | None = None
    output_refs: dict[str, Any] | None = None
    requires_user_action: bool
    user_action_type: str | None = None
    blocking_reason: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failed_at: datetime | None = None
    last_activity_at: datetime
    created_at: datetime
    updated_at: datetime


class BrandIntelligenceRunEnvelope(BaseModel):
    run: BrandIntelligenceRunResponse | None
