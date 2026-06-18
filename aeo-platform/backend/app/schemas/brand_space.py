from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


BoardRunStatusLiteral = Literal[
    "idle",
    "running",
    "pause_requested",
    "paused",
    "stopped",
    "completed",
    "failed",
]

GraphPatchDecisionLiteral = Literal["accepted", "rejected", "needs_review"]


class BoardRunCreate(BaseModel):
    board_id: str = Field(default="ai_visibility_monitor", max_length=120)
    template_id: str = Field(default="ai_visibility_monitor:v0.1", max_length=120)
    input_scope: dict[str, Any] | None = Field(default=None)


class GraphPatchDecision(BaseModel):
    status: GraphPatchDecisionLiteral
    reason: str | None = Field(default=None, max_length=1000)


class GraphUpdateReportCreate(BaseModel):
    report_kind: str = Field(default="graph_update_interpretation", max_length=80)
    publish_requested: bool = Field(default=False)
