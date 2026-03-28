"""Unified skill invocation planning for orchestrator and future agent entrypoints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.skill_registry_service import SkillRegistryService, SkillScopeContext


SKILL_EXECUTOR_TO_NODE: dict[str, str] = {
    "table_intake_executor": "table_intake",
    "a5_data_analytics": "a5_analytics",
    "confidence_analysis_executor": "confidence_analysis_executor",
    "a7_confidence_signal": "confidence_analysis_executor",
    "post_analysis_executor": "post_analysis_executor",
}

LEGACY_SKILL_TOOL_ALIASES: dict[str, dict[str, Any]] = {
    "data_analytics": {"skill_key": "analysis_report_skill", "extra_args": {}},
    "confidence_signal_skill": {
        "skill_key": "confidence_analysis_skill",
        "extra_args": {},
    },
    "drill_down_analysis": {
        "skill_key": "post_analysis_skill",
        "extra_args": {"analysis_mode": "drill_down"},
    },
    "compare_snapshots": {
        "skill_key": "post_analysis_skill",
        "extra_args": {"analysis_mode": "compare_snapshots"},
    },
    "selective_refetch": {
        "skill_key": "post_analysis_skill",
        "extra_args": {"analysis_mode": "selective_refetch"},
    },
}


@dataclass(frozen=True)
class SkillInvocationPlan:
    requested_tool_name: str
    effective_tool_name: str
    display_name: str
    node_name: str
    skill_key: str
    family_skill_key: str
    package_key: str | None
    package_display_name: str | None
    package_path: str | None
    package_body: str | None
    prompt_overlay: str | None
    executor_ref: str
    merged_tool_args: dict[str, Any]


class SkillInvocationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.registry = SkillRegistryService(db)

    async def resolve_invocation(
        self,
        *,
        tool_name: str,
        tool_args: dict[str, Any] | None,
        scope_context: SkillScopeContext | None = None,
    ) -> SkillInvocationPlan | None:
        resolved_name = tool_name
        alias = LEGACY_SKILL_TOOL_ALIASES.get(tool_name)
        if alias:
            resolved_name = str(alias["skill_key"])

        resolved_skill = await self.registry.resolve_tool_to_skill(
            resolved_name,
            scope_context=scope_context,
        )
        if resolved_skill is None:
            return None

        node_name = SKILL_EXECUTOR_TO_NODE.get(str(resolved_skill["executor_ref"]))
        if not node_name:
            return None

        merged_tool_args = dict(resolved_skill.get("default_params") or {})
        if alias:
            merged_tool_args.update(alias.get("extra_args") or {})
        merged_tool_args.update(tool_args or {})
        display_name = str(resolved_skill["display_name"])

        return SkillInvocationPlan(
            requested_tool_name=tool_name,
            effective_tool_name=str(resolved_skill["skill_key"]),
            display_name=display_name,
            node_name=node_name,
            skill_key=str(resolved_skill["skill_key"]),
            family_skill_key=str(
                resolved_skill.get("family_skill_key") or resolved_skill["skill_key"]
            ),
            package_key=resolved_skill.get("package_key"),
            package_display_name=resolved_skill.get("package_display_name"),
            package_path=resolved_skill.get("package_path"),
            package_body=resolved_skill.get("package_body"),
            prompt_overlay=resolved_skill.get("prompt_overlay"),
            executor_ref=str(resolved_skill["executor_ref"]),
            merged_tool_args=merged_tool_args,
        )
