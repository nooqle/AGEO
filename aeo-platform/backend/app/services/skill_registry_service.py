"""Skill registry service and builtin coarse-grained skill definitions."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.skill import (
    BuiltinSkillSpec,
    SkillAssignment,
    SkillConfirmationPolicy,
    SkillCostClass,
    SkillDefinition,
    SkillExecutorKind,
    SkillLatencyClass,
    SkillScopeKind,
    SkillVersion,
)
from app.services.skill_package_service import (
    SkillPackageManifest,
    skill_package_service,
)


_RETIRED_PUBLIC_SKILL_KEYS = {
    "confidence_analysis_skill",
    "confidence_signal_skill",
}


BUILTIN_SKILL_SPECS: tuple[BuiltinSkillSpec, ...] = (
    BuiltinSkillSpec(
        skill_key="table_intake_skill",
        display_name="表格导入理解",
        description=(
            "理解用户上传的 CSV/XLSX 表格用途，输出结构化判断结果。"
            "只做识别和标准化，不直接修改业务状态或推进流程。"
        ),
        executor_kind=SkillExecutorKind.BUILTIN,
        executor_ref="table_intake_executor",
        intent_signals=["上传表格", "问题列表", "竞品表", "链接清单", "导入问题"],
        prerequisites=[],
        artifact_types=["chat_reply"],
        default_params={},
        prompt_overlay=None,
        cost_class=SkillCostClass.LOW,
        latency_class=SkillLatencyClass.LOW,
        confirmation_policy=SkillConfirmationPolicy.REQUIRED,
    ),
    BuiltinSkillSpec(
        skill_key="analysis_report_skill",
        display_name="完整分析报告",
        description=(
            "面向完整分析报告与总结场景的公共 Skill。"
            "适用于要求输出整体分析、正式报告、总结品牌战况、生成完整结论的任务。"
        ),
        executor_kind=SkillExecutorKind.BUILTIN,
        executor_ref="a5_data_analytics",
        intent_signals=["完整报告", "整体分析", "总结", "战况报告", "正式报告"],
        prerequisites=["fetch_results_required"],
        artifact_types=["report", "dashboard"],
        default_params={"report_type": "scenario"},
        prompt_overlay=None,
        cost_class=SkillCostClass.HIGH,
        latency_class=SkillLatencyClass.HIGH,
        confirmation_policy=SkillConfirmationPolicy.OPTIONAL,
    ),
    BuiltinSkillSpec(
        skill_key="site_confidence_assessment_skill",
        display_name="官网 AI 友好度",
        description=(
            "面向当前监测品牌官网的 AI 友好度评估公共 Skill。"
            "只允许扫描当前品牌自己的官网，不面向任意第三方网站。"
            "输入官网根地址后，自动发现官网页面并生成官网 AI 友好度报告。"
        ),
        executor_kind=SkillExecutorKind.BUILTIN,
        executor_ref="site_confidence_assessment_executor",
        intent_signals=["官网 AI 友好度", "官网评估", "brand site confidence"],
        prerequisites=[],
        artifact_types=["report"],
        default_params={"scan_mode": "standard"},
        prompt_overlay=None,
        cost_class=SkillCostClass.MEDIUM,
        latency_class=SkillLatencyClass.MEDIUM,
        confirmation_policy=SkillConfirmationPolicy.NEVER,
    ),
    BuiltinSkillSpec(
        skill_key="post_analysis_skill",
        display_name="后续分析",
        description=(
            "面向已有分析结果后的继续任务的公共 Skill。"
            "适用于深入分析、历次对比、结论解释和风险提取等场景。"
        ),
        executor_kind=SkillExecutorKind.BUILTIN,
        executor_ref="post_analysis_executor",
        intent_signals=["深入分析", "对比", "变化", "趋势", "追问结果", "解释原因"],
        prerequisites=["analysis_results_required"],
        artifact_types=["chat_reply", "report"],
        default_params={"analysis_mode": "compare_snapshots"},
        prompt_overlay=None,
        cost_class=SkillCostClass.MEDIUM,
        latency_class=SkillLatencyClass.MEDIUM,
        confirmation_policy=SkillConfirmationPolicy.OPTIONAL,
    ),
)

BUILTIN_SKILL_KEY_SET = {item.skill_key for item in BUILTIN_SKILL_SPECS}
_BUILTIN_MAP = {item.skill_key: item for item in BUILTIN_SKILL_SPECS}

_SCOPE_PRIORITY = {
    SkillScopeKind.GLOBAL.value: 0,
    SkillScopeKind.WORKSPACE.value: 1,
    SkillScopeKind.ENTITY.value: 2,
}


@dataclass(frozen=True)
class SkillScopeContext:
    workspace_ref: str | None = None
    entity_ref: str | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_config(skill: SkillDefinition) -> dict[str, Any]:
    family_skill_key = _family_key_for_skill(skill)
    package = skill_package_service.resolve_family_package(family_skill_key)
    return {
        "skill_key": skill.skill_key,
        "family_skill_key": family_skill_key,
        "display_name": skill.display_name,
        "description": skill.description,
        "executor_kind": skill.executor_kind,
        "executor_ref": skill.executor_ref,
        "template_skill_key": skill.template_skill_key,
        "intent_signals": list(skill.intent_signals or []),
        "prerequisites": list(skill.prerequisites or []),
        "artifact_types": list(skill.artifact_types or []),
        "default_params": dict(skill.default_params or {}),
        "prompt_overlay": skill.prompt_overlay,
        "cost_class": skill.cost_class,
        "latency_class": skill.latency_class,
        "confirmation_policy": skill.confirmation_policy,
        "enabled": bool(skill.enabled),
        "is_builtin": bool(skill.is_builtin),
        "package_key": package.package_key if package else None,
        "package_display_name": package.display_name if package else None,
        "version": int(skill.version or 1),
    }


def _family_key_for_skill(skill: SkillDefinition) -> str:
    return skill.template_skill_key or skill.skill_key


def _normalize_scope_kind(scope_kind: str | None) -> str:
    value = str(scope_kind or SkillScopeKind.GLOBAL.value).strip().lower()
    if value not in _SCOPE_PRIORITY:
        raise ValueError(f"Unsupported assignment_scope_kind: {scope_kind}")
    return value


def _normalize_scope_ref(scope_kind: str, scope_ref: str | None) -> str | None:
    if scope_kind == SkillScopeKind.GLOBAL.value:
        return None
    normalized = str(scope_ref or "").strip()
    if not normalized:
        raise ValueError(
            f"assignment_scope_ref is required when scope_kind={scope_kind}"
        )
    return normalized


def _matches_scope(
    assignment: SkillAssignment,
    scope_context: SkillScopeContext | None,
) -> bool:
    if assignment.scope_kind == SkillScopeKind.GLOBAL.value:
        return True
    if scope_context is None:
        return False
    if assignment.scope_kind == SkillScopeKind.WORKSPACE.value:
        return bool(
            scope_context.workspace_ref
            and assignment.scope_ref == scope_context.workspace_ref
        )
    if assignment.scope_kind == SkillScopeKind.ENTITY.value:
        return bool(
            scope_context.entity_ref
            and assignment.scope_ref == scope_context.entity_ref
        )
    return False


def _resolve_assignment(
    skill: SkillDefinition,
    scope_context: SkillScopeContext | None,
) -> SkillAssignment | None:
    assignments = skill.assignments or []
    if not assignments:
        return None
    if scope_context is None:
        enabled_assignments = [
            assignment for assignment in assignments if assignment.enabled
        ]
        if not enabled_assignments:
            return None
        return max(
            enabled_assignments,
            key=lambda assignment: (
                _SCOPE_PRIORITY.get(assignment.scope_kind, -1),
                assignment.updated_at or assignment.created_at,
            ),
        )
    matched = [
        assignment
        for assignment in assignments
        if _matches_scope(assignment, scope_context)
    ]
    if not matched:
        return None
    return max(
        matched,
        key=lambda assignment: (
            _SCOPE_PRIORITY.get(assignment.scope_kind, -1),
            assignment.updated_at or assignment.created_at,
        ),
    )


def _assignment_enabled(
    skill: SkillDefinition,
    scope_context: SkillScopeContext | None = None,
) -> bool:
    resolved = _resolve_assignment(skill, scope_context)
    return bool(resolved and resolved.enabled)


def _profile_sort_key(
    skill: SkillDefinition,
    scope_context: SkillScopeContext | None = None,
) -> tuple[int, datetime, str]:
    assignment = _resolve_assignment(skill, scope_context)
    updated_at = skill.updated_at or skill.created_at or _utcnow()
    if assignment is not None:
        updated_at = assignment.updated_at or assignment.created_at or updated_at
    priority = (
        _SCOPE_PRIORITY.get(assignment.scope_kind, -1) if assignment is not None else -1
    )
    return (
        priority,
        updated_at,
        skill.display_name or skill.skill_key,
    )


def _serialize_skill(skill: SkillDefinition) -> dict[str, Any]:
    family_skill_key = _family_key_for_skill(skill)
    family_spec = _BUILTIN_MAP.get(family_skill_key)
    package = skill_package_service.resolve_family_package(family_skill_key)
    assignment_enabled = _assignment_enabled(skill)
    return {
        "id": str(skill.id),
        "skill_key": skill.skill_key,
        "family_skill_key": family_skill_key,
        "family_display_name": (
            family_spec.display_name if family_spec else skill.display_name
        ),
        "display_name": skill.display_name,
        "description": skill.description,
        "executor_kind": skill.executor_kind,
        "executor_ref": skill.executor_ref,
        "template_skill_key": skill.template_skill_key,
        "intent_signals": list(skill.intent_signals or []),
        "prerequisites": list(skill.prerequisites or []),
        "artifact_types": list(skill.artifact_types or []),
        "default_params": dict(skill.default_params or {}),
        "prompt_overlay": skill.prompt_overlay,
        "cost_class": skill.cost_class,
        "latency_class": skill.latency_class,
        "confirmation_policy": skill.confirmation_policy,
        "enabled": bool(skill.enabled),
        "assignment_enabled": assignment_enabled,
        "effective_enabled": bool(skill.enabled and assignment_enabled),
        "is_builtin": bool(skill.is_builtin),
        "is_profile": not bool(skill.is_builtin),
        "version": int(skill.version or 1),
        "package_key": package.package_key if package else None,
        "package_display_name": package.display_name if package else None,
        "package_description": package.description if package else None,
        "package_path": package.skill_md_path if package else None,
        "created_at": skill.created_at,
        "updated_at": skill.updated_at,
        "assignments": [
            {
                "id": str(assignment.id),
                "skill_id": str(skill.id),
                "scope_kind": assignment.scope_kind,
                "scope_ref": assignment.scope_ref,
                "enabled": assignment.enabled,
                "created_at": assignment.created_at,
                "updated_at": assignment.updated_at,
            }
            for assignment in (skill.assignments or [])
        ],
    }


def _profile_parameter(profiles: list[SkillDefinition]) -> dict[str, Any]:
    labels = [f"{profile.display_name}({profile.skill_key})" for profile in profiles]
    description = "可选的 Skill Profile Key。"
    if labels:
        description = f"{description} 当前可用 profile：{', '.join(labels)}"
    return {
        "type": "string",
        "enum": [profile.skill_key for profile in profiles],
        "description": description,
    }


def _with_package_hint(
    description: str,
    package: SkillPackageManifest | None,
) -> str:
    if package is None or not package.tool_hint:
        return description
    return f"{description} 运行时会按需加载 Package：{package.display_name}。{package.tool_hint}"


def _stable_skill_tool_description_enabled() -> bool:
    return bool(getattr(get_settings(), "STABLE_SKILL_TOOL_DESCRIPTION_ENABLED", False))


def _build_skill_tool_description(
    skill: SkillDefinition | BuiltinSkillSpec,
    package: SkillPackageManifest | None,
    *,
    static_suffix: str = "",
) -> str:
    description = str(skill.description or "").strip()
    if not _stable_skill_tool_description_enabled():
        description = _with_package_hint(description, package)
        if skill.prompt_overlay:
            description = f"{description} 当前策略补充：{skill.prompt_overlay}"
    if static_suffix:
        description = f"{description} {static_suffix.strip()}"
    return description


def _build_analysis_report_tool(
    skill: SkillDefinition | BuiltinSkillSpec,
    *,
    profiles: list[SkillDefinition] | None = None,
    package: SkillPackageManifest | None = None,
) -> dict[str, Any]:
    description = _build_skill_tool_description(skill, package)
    properties: dict[str, Any] = {
        "report_focus": {
            "type": "string",
            "description": "报告重点方向（可选）",
        },
        "report_type": {
            "type": "string",
            "enum": ["panorama", "scenario"],
            "description": "报告类型：panorama=品牌全景分析报告, scenario=场景分析报告（默认）",
        },
    }
    return {
        "name": skill.skill_key,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
        },
    }


def _build_table_intake_tool(
    skill: SkillDefinition | BuiltinSkillSpec,
    *,
    profiles: list[SkillDefinition] | None = None,
    package: SkillPackageManifest | None = None,
) -> dict[str, Any]:
    description = _build_skill_tool_description(skill, package)
    return {
        "name": skill.skill_key,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": {},
        },
    }


def _build_confidence_tool(
    skill: SkillDefinition | BuiltinSkillSpec,
    *,
    profiles: list[SkillDefinition] | None = None,
    package: SkillPackageManifest | None = None,
) -> dict[str, Any]:
    description = _build_skill_tool_description(skill, package)
    properties: dict[str, Any] = {
        "source_mode": {
            "type": "string",
            "enum": ["auto", "current_fetch_results", "raw_input", "imported_link_list"],
            "description": (
                "评估材料来源。auto 表示由执行器结合当前状态自动判断；"
                "current_fetch_results 表示评估当前会话已抓取的引用；"
                "raw_input 表示评估本轮用户直接提供的链接或文本；"
                "imported_link_list 表示评估已导入的链接清单。"
            ),
        },
        "raw_input": {
            "type": "string",
            "description": "当 source_mode=raw_input 时，传入用户原始输入的链接列表或文本内容。",
        },
    }
    return {
        "name": skill.skill_key,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
        },
    }


def _build_post_analysis_tool(
    skill: SkillDefinition | BuiltinSkillSpec,
    *,
    profiles: list[SkillDefinition] | None = None,
    package: SkillPackageManifest | None = None,
) -> dict[str, Any]:
    description = _build_skill_tool_description(skill, package)
    properties: dict[str, Any] = {
        "analysis_mode": {
            "type": "string",
            "enum": ["drill_down", "compare_snapshots"],
            "description": "后续分析模式。可以省略，由 Skill 根据参数自动判断。",
        },
        "focus_dimension": {
            "type": "string",
            "description": "深入分析维度：platform/question_category/competitor/sentiment",
        },
        "focus_value": {
            "type": "string",
            "description": "具体值（如 deepseek、华为、positive）",
        },
        "comparison_type": {
            "type": "string",
            "description": "对比方式：vs_previous（默认）或 vs_specific",
        },
    }
    return {
        "name": skill.skill_key,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
        },
    }


def _build_site_confidence_tool(
    skill: SkillDefinition | BuiltinSkillSpec,
    *,
    profiles: list[SkillDefinition] | None = None,
    package: SkillPackageManifest | None = None,
) -> dict[str, Any]:
    description = _build_skill_tool_description(
        skill,
        package,
        static_suffix=(
            "只允许针对当前监测品牌自己的官网。"
            "如果当前品牌官网未绑定，或用户给出的域名不属于当前品牌官网，不能直接执行。"
        ),
    )
    return {
        "name": skill.skill_key,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": {
                "root_url": {
                    "type": "string",
                    "description": "待评估的官网根地址，例如 https://example.com 。",
                },
                "scan_mode": {
                    "type": "string",
                    "enum": ["standard"],
                    "description": "评估模式。当前 Phase 1 仅支持 standard。",
                },
                "max_pages": {
                    "type": "integer",
                    "description": "可选，限制本轮最多评估的页面数。默认扫描首页及最多 7 个核心页面。",
                },
            },
            "required": ["root_url"],
        },
    }


def build_skill_tool_definition(
    skill: SkillDefinition | BuiltinSkillSpec,
    *,
    profiles: list[SkillDefinition] | None = None,
    package: SkillPackageManifest | None = None,
) -> dict[str, Any]:
    if skill.executor_ref == "table_intake_executor":
        return _build_table_intake_tool(skill, profiles=profiles, package=package)
    if skill.executor_ref == "a5_data_analytics":
        return _build_analysis_report_tool(skill, profiles=profiles, package=package)
    if skill.executor_ref == "site_confidence_assessment_executor":
        return _build_site_confidence_tool(skill, profiles=profiles, package=package)
    if skill.executor_ref == "post_analysis_executor":
        return _build_post_analysis_tool(skill, profiles=profiles, package=package)
    raise ValueError(f"Unsupported skill executor_ref: {skill.executor_ref}")


def build_builtin_skill_tool_definitions() -> list[dict[str, Any]]:
    definitions: list[dict[str, Any]] = []
    for spec in BUILTIN_SKILL_SPECS:
        package = skill_package_service.resolve_family_package(spec.skill_key)
        definitions.append(build_skill_tool_definition(spec, package=package))
    return definitions


class SkillRegistryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _replace_assignments(
        self,
        skill: SkillDefinition,
        *,
        scope_kind: str,
        scope_ref: str | None,
        enabled: bool,
    ) -> None:
        assignments = list(skill.assignments or [])
        for assignment in assignments:
            await self.db.delete(assignment)
        replacement = SkillAssignment(
            skill_id=skill.id,
            scope_kind=scope_kind,
            scope_ref=scope_ref,
            enabled=enabled,
        )
        skill.assignments = [replacement]
        self.db.add(replacement)

    async def ensure_builtin_skills(self) -> None:
        for spec in BUILTIN_SKILL_SPECS:
            stmt = (
                select(SkillDefinition)
                .options(
                    selectinload(SkillDefinition.assignments),
                    selectinload(SkillDefinition.versions),
                )
                .where(SkillDefinition.skill_key == spec.skill_key)
            )
            result = await self.db.execute(stmt)
            skill = result.scalar_one_or_none()
            if skill is None:
                skill = SkillDefinition(
                    skill_key=spec.skill_key,
                    display_name=spec.display_name,
                    description=spec.description,
                    executor_kind=spec.executor_kind.value,
                    executor_ref=spec.executor_ref,
                    template_skill_key=spec.skill_key,
                    intent_signals=list(spec.intent_signals),
                    prerequisites=list(spec.prerequisites),
                    artifact_types=list(spec.artifact_types),
                    default_params=dict(spec.default_params),
                    prompt_overlay=spec.prompt_overlay,
                    cost_class=spec.cost_class.value,
                    latency_class=spec.latency_class.value,
                    confirmation_policy=spec.confirmation_policy.value,
                    enabled=spec.enabled,
                    is_builtin=True,
                    version=spec.version,
                )
                self.db.add(skill)
                await self.db.flush()
                self.db.add(
                    SkillVersion(
                        skill_id=skill.id,
                        version=skill.version,
                        config_payload=_serialize_config(skill),
                    )
                )
                self.db.add(
                    SkillAssignment(
                        skill_id=skill.id,
                        scope_kind=SkillScopeKind.GLOBAL.value,
                        scope_ref=None,
                        enabled=spec.enabled,
                    )
                )
                continue

            skill_changed = False

            desired_updates = {
                "display_name": spec.display_name,
                "description": spec.description,
                "executor_kind": spec.executor_kind.value,
                "executor_ref": spec.executor_ref,
                "template_skill_key": spec.skill_key,
                "intent_signals": list(spec.intent_signals),
                "prerequisites": list(spec.prerequisites),
                "artifact_types": list(spec.artifact_types),
                "default_params": dict(spec.default_params),
                "cost_class": spec.cost_class.value,
                "latency_class": spec.latency_class.value,
                "confirmation_policy": spec.confirmation_policy.value,
                "is_builtin": True,
            }
            if skill.is_builtin:
                desired_updates["prompt_overlay"] = spec.prompt_overlay

            for field_name, desired_value in desired_updates.items():
                if getattr(skill, field_name) != desired_value:
                    setattr(skill, field_name, desired_value)
                    skill_changed = True

            if skill.version <= 0:
                skill.version = spec.version
                skill_changed = True

            if not skill.assignments:
                self.db.add(
                    SkillAssignment(
                        skill_id=skill.id,
                        scope_kind=SkillScopeKind.GLOBAL.value,
                        scope_ref=None,
                        enabled=skill.enabled,
                    )
                )

            version_exists = any(
                version.version == skill.version for version in (skill.versions or [])
            )
            if not version_exists:
                self.db.add(
                    SkillVersion(
                        skill_id=skill.id,
                        version=skill.version,
                        config_payload=_serialize_config(skill),
                    )
                )
            elif skill_changed:
                current_version = next(
                    version
                    for version in (skill.versions or [])
                    if version.version == skill.version
                )
                current_version.config_payload = _serialize_config(skill)

            if skill_changed:
                skill.updated_at = _utcnow()

        await self.db.commit()

    async def list_skills(
        self,
        *,
        builtin_only: bool = True,
    ) -> list[dict[str, Any]]:
        await self.ensure_builtin_skills()
        stmt = (
            select(SkillDefinition)
            .options(
                selectinload(SkillDefinition.assignments),
                selectinload(SkillDefinition.versions),
            )
            .order_by(
                SkillDefinition.is_builtin.desc(), SkillDefinition.display_name.asc()
            )
        )
        if builtin_only:
            stmt = stmt.where(
                SkillDefinition.is_builtin.is_(True),
                SkillDefinition.skill_key.notin_(_RETIRED_PUBLIC_SKILL_KEYS),
            )
        result = await self.db.execute(stmt)
        skills = result.scalars().all()
        return [_serialize_skill(skill) for skill in skills]

    async def list_enabled_public_skills(
        self,
        scope_context: SkillScopeContext | None = None,
    ) -> list[SkillDefinition]:
        await self.ensure_builtin_skills()
        stmt = (
            select(SkillDefinition)
            .options(selectinload(SkillDefinition.assignments))
            .where(SkillDefinition.is_builtin.is_(True))
            .order_by(
                SkillDefinition.is_builtin.desc(), SkillDefinition.display_name.asc()
            )
        )
        result = await self.db.execute(stmt)
        skills = result.scalars().all()
        filtered = [
            skill
            for skill in skills
            if skill.skill_key not in _RETIRED_PUBLIC_SKILL_KEYS
            and skill.enabled
            and _assignment_enabled(skill, scope_context)
        ]
        return sorted(
            filtered,
            key=lambda item: _profile_sort_key(item, scope_context),
            reverse=True,
        )

    async def list_enabled_profiles_for_template(
        self,
        template_skill_key: str,
        scope_context: SkillScopeContext | None = None,
    ) -> list[SkillDefinition]:
        stmt = (
            select(SkillDefinition)
            .options(selectinload(SkillDefinition.assignments))
            .where(
                SkillDefinition.is_builtin.is_(False),
                SkillDefinition.template_skill_key == template_skill_key,
            )
            .order_by(SkillDefinition.display_name.asc())
        )
        result = await self.db.execute(stmt)
        skills = result.scalars().all()
        return [
            skill
            for skill in skills
            if skill.enabled and _assignment_enabled(skill, scope_context)
        ]

    async def get_tool_definitions(
        self,
        scope_context: SkillScopeContext | None = None,
    ) -> list[dict[str, Any]]:
        skills = await self.list_enabled_public_skills(scope_context)
        tool_definitions: list[dict[str, Any]] = []
        for skill in skills:
            package = skill_package_service.resolve_family_package(skill.skill_key)
            tool_definitions.append(build_skill_tool_definition(skill, package=package))
        return tool_definitions

    async def get_skill_by_id(self, skill_id: uuid.UUID) -> SkillDefinition | None:
        stmt = (
            select(SkillDefinition)
            .options(
                selectinload(SkillDefinition.assignments),
                selectinload(SkillDefinition.versions),
            )
            .where(SkillDefinition.id == skill_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_skill_by_key(self, skill_key: str) -> SkillDefinition | None:
        stmt = (
            select(SkillDefinition)
            .options(
                selectinload(SkillDefinition.assignments),
                selectinload(SkillDefinition.versions),
            )
            .where(SkillDefinition.skill_key == skill_key)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_versions(self, skill_id: uuid.UUID) -> list[dict[str, Any]]:
        skill = await self.get_skill_by_id(skill_id)
        if skill is None:
            return []
        return [
            {
                "id": str(version.id),
                "skill_id": str(skill.id),
                "version": version.version,
                "config_payload": version.config_payload or {},
                "created_at": version.created_at,
            }
            for version in (skill.versions or [])
        ]

    def _generate_custom_skill_key(self, template_skill_key: str) -> str:
        suffix = uuid.uuid4().hex[:8]
        stem = re.sub(r"[^a-z0-9_]+", "_", template_skill_key.lower()).strip("_")
        if not stem:
            stem = "skill"
        return f"custom_{stem}_{suffix}"

    async def create_skill(
        self,
        *,
        template_skill_key: str,
        display_name: str,
        description: str,
        default_params: dict[str, Any] | None,
        prompt_overlay: str | None,
        enabled: bool,
        assignment_scope_kind: str = SkillScopeKind.GLOBAL.value,
        assignment_scope_ref: str | None = None,
        created_by_user_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        await self.ensure_builtin_skills()
        template = _BUILTIN_MAP.get(template_skill_key)
        if template is None:
            raise ValueError(f"Unknown template_skill_key: {template_skill_key}")
        normalized_scope_kind = _normalize_scope_kind(assignment_scope_kind)
        if (
            normalized_scope_kind == SkillScopeKind.WORKSPACE.value
            and (
                assignment_scope_ref is None
                or assignment_scope_ref == "current-workspace"
            )
            and created_by_user_id is not None
        ):
            assignment_scope_ref = str(created_by_user_id)
        normalized_scope_ref = _normalize_scope_ref(
            normalized_scope_kind,
            assignment_scope_ref,
        )

        skill = SkillDefinition(
            skill_key=self._generate_custom_skill_key(template_skill_key),
            display_name=display_name,
            description=description.strip() or template.description,
            executor_kind=SkillExecutorKind.CONFIGURED_TEMPLATE.value,
            executor_ref=template.executor_ref,
            template_skill_key=template_skill_key,
            intent_signals=list(template.intent_signals),
            prerequisites=list(template.prerequisites),
            artifact_types=list(template.artifact_types),
            default_params=dict(default_params or template.default_params or {}),
            prompt_overlay=prompt_overlay.strip() if prompt_overlay else None,
            cost_class=template.cost_class.value,
            latency_class=template.latency_class.value,
            confirmation_policy=template.confirmation_policy.value,
            enabled=enabled,
            is_builtin=False,
            version=1,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(skill)
        await self.db.flush()
        version = SkillVersion(
            skill_id=skill.id,
            version=1,
            config_payload=_serialize_config(skill),
        )
        assignment = SkillAssignment(
            skill_id=skill.id,
            scope_kind=normalized_scope_kind,
            scope_ref=normalized_scope_ref,
            enabled=enabled,
        )
        self.db.add(version)
        self.db.add(assignment)
        await self.db.commit()
        refreshed = await self.get_skill_by_id(skill.id)
        if refreshed is None:
            raise RuntimeError("Failed to refresh created skill")
        return _serialize_skill(refreshed)

    async def update_skill(
        self,
        *,
        skill_id: uuid.UUID,
        updates: dict[str, Any],
        acting_user_id: uuid.UUID | None = None,
    ) -> dict[str, Any] | None:
        skill = await self.get_skill_by_id(skill_id)
        if skill is None:
            return None

        if skill.is_builtin:
            allowed_keys = {"enabled", "assignment_scope_kind", "assignment_scope_ref"}
        else:
            allowed_keys = {
                "display_name",
                "description",
                "default_params",
                "prompt_overlay",
                "enabled",
                "assignment_scope_kind",
                "assignment_scope_ref",
            }

        normalized_scope_kind: str | None = None
        normalized_scope_ref: str | None = None
        if "assignment_scope_kind" in updates or "assignment_scope_ref" in updates:
            normalized_scope_kind = _normalize_scope_kind(
                updates.get("assignment_scope_kind")
                or (skill.assignments[0].scope_kind if skill.assignments else None)
                or SkillScopeKind.GLOBAL.value
            )
            requested_scope_ref = (
                updates.get("assignment_scope_ref")
                if "assignment_scope_ref" in updates
                else (skill.assignments[0].scope_ref if skill.assignments else None)
            )
            if (
                normalized_scope_kind == SkillScopeKind.WORKSPACE.value
                and (
                    requested_scope_ref is None
                    or requested_scope_ref == "current-workspace"
                )
                and acting_user_id is not None
            ):
                requested_scope_ref = str(acting_user_id)
            normalized_scope_ref = _normalize_scope_ref(
                normalized_scope_kind,
                requested_scope_ref,
            )

        for key, value in updates.items():
            if key not in allowed_keys:
                continue
            if key == "enabled":
                skill.enabled = bool(value)
            elif key == "display_name" and value:
                skill.display_name = str(value)
            elif key == "description" and value is not None:
                skill.description = str(value)
            elif key == "default_params":
                skill.default_params = dict(value or {})
            elif key == "prompt_overlay":
                skill.prompt_overlay = str(value).strip() if value else None

        if normalized_scope_kind is not None:
            await self._replace_assignments(
                skill,
                scope_kind=normalized_scope_kind,
                scope_ref=normalized_scope_ref,
                enabled=bool(skill.enabled),
            )
        elif "enabled" in updates:
            for assignment in skill.assignments or []:
                assignment.enabled = bool(skill.enabled)
                assignment.updated_at = _utcnow()

        skill.updated_at = _utcnow()
        await self.db.commit()
        refreshed = await self.get_skill_by_id(skill_id)
        if refreshed is None:
            return None
        return _serialize_skill(refreshed)

    async def publish_skill(self, *, skill_id: uuid.UUID) -> dict[str, Any] | None:
        skill = await self.get_skill_by_id(skill_id)
        if skill is None:
            return None

        existing_versions = {version.version for version in (skill.versions or [])}
        next_version = int(skill.version or 1)
        if not skill.is_builtin:
            next_version += 1
            skill.version = next_version
        if skill.version not in existing_versions:
            version_record = SkillVersion(
                skill_id=skill.id,
                version=skill.version,
                config_payload=_serialize_config(skill),
            )
            self.db.add(version_record)
        elif not skill.is_builtin:
            version_record = SkillVersion(
                skill_id=skill.id,
                version=skill.version,
                config_payload=_serialize_config(skill),
            )
            self.db.add(version_record)
        else:
            version_record = next(
                version
                for version in (skill.versions or [])
                if version.version == skill.version
            )

        skill.updated_at = _utcnow()
        await self.db.commit()
        refreshed = await self.get_skill_by_id(skill_id)
        if refreshed is None:
            return None
        version_stmt = (
            select(SkillVersion)
            .where(SkillVersion.skill_id == refreshed.id)
            .order_by(SkillVersion.version.desc(), SkillVersion.created_at.desc())
            .limit(1)
        )
        refreshed_version = (await self.db.execute(version_stmt)).scalar_one()
        return {
            "skill": _serialize_skill(refreshed),
            "published_version": {
                "id": str(refreshed_version.id),
                "skill_id": str(refreshed.id),
                "version": refreshed_version.version,
                "config_payload": refreshed_version.config_payload or {},
                "created_at": refreshed_version.created_at,
            },
        }

    async def resolve_tool_to_skill(
        self,
        tool_name: str,
        *,
        scope_context: SkillScopeContext | None = None,
    ) -> dict[str, Any] | None:
        await self.ensure_builtin_skills()
        skill = await self.get_skill_by_key(tool_name)
        if (
            skill is None
            or skill.skill_key in _RETIRED_PUBLIC_SKILL_KEYS
            or not skill.is_builtin
            or not skill.enabled
            or not _assignment_enabled(skill, scope_context)
        ):
            return None
        package = skill_package_service.resolve_family_package(skill.skill_key)
        tool_definition = build_skill_tool_definition(skill, package=package)
        return {
            **_serialize_skill(skill),
            "default_params": dict(skill.default_params or {}),
            "family_skill_key": skill.skill_key,
            "package_key": package.package_key if package else None,
            "package_display_name": package.display_name if package else None,
            "package_description": package.description if package else None,
            "package_path": package.skill_md_path if package else None,
            "package_body": package.body if package else None,
            "package_manifest": package,
            "tool_definition": tool_definition,
        }
