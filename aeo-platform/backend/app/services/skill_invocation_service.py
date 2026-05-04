"""Unified skill invocation planning for orchestrator and future agent entrypoints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.skill_contracts import SkillContract, build_skill_contract
from app.services.skill_registry_service import SkillRegistryService, SkillScopeContext


SKILL_EXECUTOR_TO_NODE: dict[str, str] = {
    "table_intake_executor": "table_intake",
    "a5_data_analytics": "a5_analytics",
    "site_confidence_assessment_executor": "site_confidence_assessment_executor",
    "post_analysis_executor": "post_analysis_executor",
}

LEGACY_SKILL_TOOL_ALIASES: dict[str, dict[str, Any]] = {
    "data_analytics": {"skill_key": "analysis_report_skill", "extra_args": {}},
    "drill_down_analysis": {
        "skill_key": "post_analysis_skill",
        "extra_args": {"analysis_mode": "drill_down"},
    },
    "compare_snapshots": {
        "skill_key": "post_analysis_skill",
        "extra_args": {"analysis_mode": "compare_snapshots"},
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
    package_description: str | None
    package_path: str | None
    package_body: str | None
    prompt_overlay: str | None
    profiles: tuple[dict[str, str], ...]
    executor_ref: str
    merged_tool_args: dict[str, Any]
    skill_contract: SkillContract


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

        family_skill_key = str(
            resolved_skill.get("family_skill_key") or resolved_skill["skill_key"]
        )
        profiles = await self.registry.list_enabled_profiles_for_template(
            family_skill_key,
            scope_context=scope_context,
        )
        profile_summaries = tuple(
            {
                "skill_key": str(profile.skill_key),
                "display_name": str(profile.display_name),
                "description": str(profile.description or ""),
                "prompt_overlay": str(profile.prompt_overlay or ""),
            }
            for profile in profiles
        )
        merged_tool_args = dict(resolved_skill.get("default_params") or {})
        if alias:
            merged_tool_args.update(alias.get("extra_args") or {})
        merged_tool_args.update(tool_args or {})
        display_name = str(resolved_skill["display_name"])
        skill_contract = build_skill_contract(
            skill_key=str(resolved_skill["skill_key"]),
            family_skill_key=family_skill_key,
            display_name=display_name,
            executor_ref=str(resolved_skill["executor_ref"]),
            prerequisites=list(resolved_skill.get("prerequisites") or []),
            artifact_types=list(resolved_skill.get("artifact_types") or []),
            default_params=dict(resolved_skill.get("default_params") or {}),
            package=resolved_skill.get("package_manifest"),
            prompt_overlay=resolved_skill.get("prompt_overlay"),
        )

        return SkillInvocationPlan(
            requested_tool_name=tool_name,
            effective_tool_name=str(resolved_skill["skill_key"]),
            display_name=display_name,
            node_name=node_name,
            skill_key=str(resolved_skill["skill_key"]),
            family_skill_key=family_skill_key,
            package_key=resolved_skill.get("package_key"),
            package_display_name=resolved_skill.get("package_display_name"),
            package_description=resolved_skill.get("package_description"),
            package_path=resolved_skill.get("package_path"),
            package_body=resolved_skill.get("package_body"),
            prompt_overlay=resolved_skill.get("prompt_overlay"),
            profiles=profile_summaries,
            executor_ref=str(resolved_skill["executor_ref"]),
            merged_tool_args=merged_tool_args,
            skill_contract=skill_contract,
        )
