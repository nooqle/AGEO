"""Shared fact snapshot builder for skill executors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.workflow.state import AgentState


@dataclass(frozen=True)
class SkillFactSnapshot:
    session_id: str
    entity_id: str | None
    brand_name: str | None
    analysis_mode: str | None
    brand_profile: dict[str, Any]
    competitors: list[Any]
    fetch_results: list[Any]
    confidence_fetch_results: list[Any]
    metrics: dict[str, Any]
    report: dict[str, Any]
    baseline_metrics: dict[str, Any]
    baseline_report: dict[str, Any]
    knowledge_manifest: dict[str, Any]
    knowledge_lookup_result: dict[str, Any]
    knowledge_aggregate_result: dict[str, Any]
    knowledge_compare_result: dict[str, Any]


def build_skill_fact_snapshot(state: AgentState) -> SkillFactSnapshot:
    brand_profile = dict(state.get("brand_profile") or {})
    brand_name = (
        brand_profile.get("brand_name")
        or state.get("brand_name")
        or state.get("official_website")
    )
    return SkillFactSnapshot(
        session_id=str(state.get("session_id") or ""),
        entity_id=state.get("entity_id"),
        brand_name=brand_name,
        analysis_mode=state.get("analysis_mode"),
        brand_profile=brand_profile,
        competitors=list(state.get("competitors") or []),
        fetch_results=list(state.get("fetch_results") or []),
        confidence_fetch_results=list(
            state.get("fetch_results") or state.get("baseline_fetch_results") or []
        ),
        metrics=dict(state.get("metrics") or {}),
        report=dict(state.get("report") or {}),
        baseline_metrics=dict(state.get("baseline_metrics") or {}),
        baseline_report=dict(state.get("baseline_report") or {}),
        knowledge_manifest=dict(state.get("knowledge_manifest") or {}),
        knowledge_lookup_result=dict(state.get("knowledge_lookup_result") or {}),
        knowledge_aggregate_result=dict(state.get("knowledge_aggregate_result") or {}),
        knowledge_compare_result=dict(state.get("knowledge_compare_result") or {}),
    )
