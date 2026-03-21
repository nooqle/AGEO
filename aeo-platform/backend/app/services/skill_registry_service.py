"""Skill registry service and builtin coarse-grained skill definitions."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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


BUILTIN_SKILL_SPECS: tuple[BuiltinSkillSpec, ...] = (
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
        default_params={"report_type": "persona"},
        prompt_overlay=None,
        cost_class=SkillCostClass.HIGH,
        latency_class=SkillLatencyClass.HIGH,
        confirmation_policy=SkillConfirmationPolicy.OPTIONAL,
    ),
    BuiltinSkillSpec(
        skill_key="confidence_signal_skill",
        display_name="引用置信度评估",
        description=(
            "面向引用内容可信度、来源质量与结构化质量评估的公共 Skill。"
            "不会重新抓取，只评估当前已有的引用来源。"
        ),
        executor_kind=SkillExecutorKind.BUILTIN,
        executor_ref="a7_confidence_signal",
        intent_signals=[
            "引用可信度",
            "来源质量",
            "结构化质量",
            "置信度",
            "citation confidence",
        ],
        prerequisites=["fetch_results_required"],
        artifact_types=["confidence_signal"],
        default_params={},
        prompt_overlay=None,
        cost_class=SkillCostClass.MEDIUM,
        latency_class=SkillLatencyClass.MEDIUM,
        confirmation_policy=SkillConfirmationPolicy.NEVER,
    ),
    BuiltinSkillSpec(
        skill_key="post_analysis_skill",
        display_name="后续分析与重抓",
        description=(
            "面向已有分析结果后的继续任务的公共 Skill。"
            "适用于深入分析、历史对比、局部重抓等场景。"
        ),
        executor_kind=SkillExecutorKind.BUILTIN,
        executor_ref="post_analysis_executor",
        intent_signals=["深入分析", "对比", "变化", "趋势", "局部重抓", "只看某个平台"],
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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_config(skill: SkillDefinition) -> dict[str, Any]:
    return {
        "skill_key": skill.skill_key,
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
        "version": int(skill.version or 1),
    }


def _assignment_enabled(skill: SkillDefinition) -> bool:
    assignments = skill.assignments or []
    if not assignments:
        return False
    return any(assignment.enabled for assignment in assignments)


def _serialize_skill(skill: SkillDefinition) -> dict[str, Any]:
    assignment_enabled = _assignment_enabled(skill)
    return {
        "id": str(skill.id),
        "skill_key": skill.skill_key,
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
        "version": int(skill.version or 1),
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


def _build_analysis_report_tool(
    skill: SkillDefinition,
    *,
    profiles: list[SkillDefinition] | None = None,
) -> dict[str, Any]:
    description = skill.description
    if skill.prompt_overlay:
        description = f"{description} 当前策略补充：{skill.prompt_overlay}"
    if profiles:
        description = (
            f"{description} 当前存在 {len(profiles)} 个可选 Skill Profile，"
            "如需使用配置化变体，请填写 skill_profile。"
        )
    properties: dict[str, Any] = {
        "report_focus": {
            "type": "string",
            "description": "报告重点方向（可选）",
        },
        "report_type": {
            "type": "string",
            "enum": ["baseline", "persona"],
            "description": "报告类型：baseline=行业基线报告, persona=场景分析报告（默认）",
        },
    }
    if profiles:
        properties["skill_profile"] = _profile_parameter(profiles)
    return {
        "name": skill.skill_key,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
        },
    }


def _build_confidence_tool(
    skill: SkillDefinition,
    *,
    profiles: list[SkillDefinition] | None = None,
) -> dict[str, Any]:
    description = skill.description
    if skill.prompt_overlay:
        description = f"{description} 当前策略补充：{skill.prompt_overlay}"
    if profiles:
        description = (
            f"{description} 当前存在 {len(profiles)} 个可选 Skill Profile，"
            "如需使用配置化变体，请填写 skill_profile。"
        )
    properties: dict[str, Any] = {}
    if profiles:
        properties["skill_profile"] = _profile_parameter(profiles)
    return {
        "name": skill.skill_key,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
        },
    }


def _build_post_analysis_tool(
    skill: SkillDefinition,
    *,
    profiles: list[SkillDefinition] | None = None,
) -> dict[str, Any]:
    description = skill.description
    if skill.prompt_overlay:
        description = f"{description} 当前策略补充：{skill.prompt_overlay}"
    if profiles:
        description = (
            f"{description} 当前存在 {len(profiles)} 个可选 Skill Profile，"
            "如需使用配置化变体，请填写 skill_profile。"
        )
    properties: dict[str, Any] = {
        "analysis_mode": {
            "type": "string",
            "enum": ["drill_down", "compare_snapshots", "selective_refetch"],
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
        "platforms": {
            "type": "array",
            "items": {"type": "string"},
            "description": "局部重抓的平台列表",
        },
        "fetch_mode": {
            "type": "string",
            "enum": ["fast", "full"],
            "description": "局部重抓时的采集模式（默认 fast）",
        },
    }
    if profiles:
        properties["skill_profile"] = _profile_parameter(profiles)
    return {
        "name": skill.skill_key,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
        },
    }


def build_skill_tool_definition(
    skill: SkillDefinition,
    *,
    profiles: list[SkillDefinition] | None = None,
) -> dict[str, Any]:
    if skill.executor_ref == "a5_data_analytics":
        return _build_analysis_report_tool(skill, profiles=profiles)
    if skill.executor_ref == "a7_confidence_signal":
        return _build_confidence_tool(skill, profiles=profiles)
    if skill.executor_ref == "post_analysis_executor":
        return _build_post_analysis_tool(skill, profiles=profiles)
    raise ValueError(f"Unsupported skill executor_ref: {skill.executor_ref}")


def build_builtin_skill_tool_definitions() -> list[dict[str, Any]]:
    return [build_skill_tool_definition(spec) for spec in BUILTIN_SKILL_SPECS]


class SkillRegistryService:
    def __init__(self, db: AsyncSession):
        self.db = db

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

            if skill_changed:
                skill.updated_at = _utcnow()

        await self.db.commit()

    async def list_skills(self) -> list[dict[str, Any]]:
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
        result = await self.db.execute(stmt)
        skills = result.scalars().all()
        return [_serialize_skill(skill) for skill in skills]

    async def list_enabled_public_skills(self) -> list[SkillDefinition]:
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
        return [
            skill for skill in skills if skill.enabled and _assignment_enabled(skill)
        ]

    async def list_enabled_profiles_for_template(
        self,
        template_skill_key: str,
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
            skill for skill in skills if skill.enabled and _assignment_enabled(skill)
        ]

    async def get_tool_definitions(self) -> list[dict[str, Any]]:
        skills = await self.list_enabled_public_skills()
        tool_definitions: list[dict[str, Any]] = []
        for skill in skills:
            profiles = await self.list_enabled_profiles_for_template(skill.skill_key)
            tool_definitions.append(
                build_skill_tool_definition(skill, profiles=profiles)
            )
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
        created_by_user_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        await self.ensure_builtin_skills()
        template = _BUILTIN_MAP.get(template_skill_key)
        if template is None:
            raise ValueError(f"Unknown template_skill_key: {template_skill_key}")

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
            scope_kind=SkillScopeKind.GLOBAL.value,
            scope_ref=None,
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
    ) -> dict[str, Any] | None:
        skill = await self.get_skill_by_id(skill_id)
        if skill is None:
            return None

        if skill.is_builtin:
            allowed_keys = {"enabled"}
        else:
            allowed_keys = {
                "display_name",
                "description",
                "default_params",
                "prompt_overlay",
                "enabled",
            }

        for key, value in updates.items():
            if key not in allowed_keys:
                continue
            if key == "enabled":
                skill.enabled = bool(value)
                for assignment in skill.assignments or []:
                    if assignment.scope_kind == SkillScopeKind.GLOBAL.value:
                        assignment.enabled = bool(value)
                        assignment.updated_at = _utcnow()
            elif key == "display_name" and value:
                skill.display_name = str(value)
            elif key == "description" and value is not None:
                skill.description = str(value)
            elif key == "default_params":
                skill.default_params = dict(value or {})
            elif key == "prompt_overlay":
                skill.prompt_overlay = str(value).strip() if value else None

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
        requested_profile_key: str | None = None,
    ) -> dict[str, Any] | None:
        await self.ensure_builtin_skills()
        skill = await self.get_skill_by_key(tool_name)
        if (
            skill is None
            or not skill.is_builtin
            or not skill.enabled
            or not _assignment_enabled(skill)
        ):
            return None
        selected_profile: SkillDefinition | None = None
        if requested_profile_key:
            candidate = await self.get_skill_by_key(requested_profile_key)
            if (
                candidate is not None
                and not candidate.is_builtin
                and candidate.template_skill_key == skill.skill_key
                and candidate.enabled
                and _assignment_enabled(candidate)
            ):
                selected_profile = candidate

        profiles = await self.list_enabled_profiles_for_template(skill.skill_key)
        tool_definition = build_skill_tool_definition(skill, profiles=profiles)
        merged_default_params = dict(skill.default_params or {})
        selected_profile_key = None
        selected_profile_display_name = None
        selected_profile_prompt_overlay = None
        if selected_profile is not None:
            merged_default_params.update(selected_profile.default_params or {})
            selected_profile_key = selected_profile.skill_key
            selected_profile_display_name = selected_profile.display_name
            selected_profile_prompt_overlay = selected_profile.prompt_overlay
        return {
            **_serialize_skill(skill),
            "default_params": merged_default_params,
            "selected_profile_key": selected_profile_key,
            "selected_profile_display_name": selected_profile_display_name,
            "selected_profile_prompt_overlay": selected_profile_prompt_overlay,
            "tool_definition": tool_definition,
        }
