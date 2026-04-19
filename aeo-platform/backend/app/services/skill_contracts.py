"""Structured skill contract helpers for public skills."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.skill_package_service import SkillPackageManifest
from app.workflow.prompt_assembly import PromptSection


@dataclass(frozen=True)
class SkillContract:
    """Formal capability contract for a public skill."""

    skill_key: str
    family_skill_key: str
    display_name: str
    executor_ref: str
    intent_scope: str
    preconditions: tuple[str, ...]
    required_inputs: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    expected_outputs: tuple[str, ...]
    artifact_writeback_rules: tuple[str, ...]
    known_blockers: tuple[str, ...]
    postconditions: tuple[str, ...]
    default_params: dict[str, Any]
    prompt_sections: tuple[PromptSection, ...]

    def to_state_payload(self) -> dict[str, Any]:
        return {
            "skill_key": self.skill_key,
            "family_skill_key": self.family_skill_key,
            "display_name": self.display_name,
            "executor_ref": self.executor_ref,
            "intent_scope": self.intent_scope,
            "preconditions": list(self.preconditions),
            "required_inputs": list(self.required_inputs),
            "allowed_tools": list(self.allowed_tools),
            "expected_outputs": list(self.expected_outputs),
            "artifact_writeback_rules": list(self.artifact_writeback_rules),
            "known_blockers": list(self.known_blockers),
            "postconditions": list(self.postconditions),
            "default_params": dict(self.default_params or {}),
            "prompt_sections": [
                section.to_state_payload() for section in self.prompt_sections
            ],
        }


_CONTRACT_BLUEPRINTS: dict[str, dict[str, Any]] = {
    "table_intake_skill": {
        "intent_scope": "理解上传表格的用途，并把结果转成可确认的结构化判断。",
        "required_inputs": ("pending_table_intake",),
        "allowed_tools": ("table_schema_read", "table_normalization"),
        "expected_outputs": ("chat_reply",),
        "artifact_writeback_rules": ("no_business_state_mutation_before_confirmation",),
        "known_blockers": ("attachment_missing", "table_parse_failed"),
        "postconditions": ("table_intake_result_ready",),
    },
    "analysis_report_skill": {
        "intent_scope": "生成完整分析报告、正式结论和面向交付的结构化洞察。",
        "required_inputs": ("brand_profile", "fetch_results", "competitors"),
        "allowed_tools": (
            "fact_snapshot",
            "llm_report_generation",
            "report_artifact_writeback",
        ),
        "expected_outputs": ("report", "dashboard"),
        "artifact_writeback_rules": (
            "must_persist_report_artifact_before_complete",
            "must_record_skill_result_after_artifact_writeback",
        ),
        "known_blockers": (
            "fetch_results_missing",
            "llm_report_incomplete",
            "artifact_writeback_failed",
        ),
        "postconditions": (
            "report_artifact_persisted",
            "metrics_available",
            "skill_result_recorded",
        ),
    },
    "site_confidence_assessment_skill": {
        "intent_scope": "仅针对当前监测品牌自己的官网，自动发现官网页面并生成官网 AI 友好度报告。",
        "required_inputs": (),
        "allowed_tools": (
            "site_page_discovery",
            "site_page_evaluation",
            "report_artifact_writeback",
        ),
        "expected_outputs": ("report",),
        "artifact_writeback_rules": (
            "must_persist_site_confidence_report_before_complete",
            "must_record_skill_result_after_artifact_writeback",
        ),
        "user_facing_report_structure": (
            "结论先行",
            "先解释为什么会得到这个判断",
            "页面级直接证据必须列出扣分项、原因和修复动作",
            "下一步建议必须按 P0 / P1 分组并绑定优先页面",
            "只有边界确实影响本轮判断时才展示边界说明",
        ),
        "known_blockers": (
            "brand_context_missing",
            "official_website_missing",
            "root_url_out_of_scope",
            "root_url_missing",
            "homepage_unreachable",
            "artifact_writeback_failed",
        ),
        "postconditions": (
            "site_confidence_report_persisted",
            "skill_result_recorded",
        ),
    },
    "post_analysis_skill": {
        "intent_scope": "在已有结果基础上做深入分析、历次对比、结论解释和风险提取。该技能只读取已有结果，不重新采集外部数据。",
        "required_inputs": ("fetch_results_or_metrics",),
        "allowed_tools": (
            "drill_down_analysis",
            "compare_snapshots",
        ),
        "expected_outputs": ("chat_reply", "report"),
        "artifact_writeback_rules": ("must_preserve_existing_report_context",),
        "known_blockers": (
            "analysis_context_missing",
            "snapshot_unavailable",
            "evidence_insufficient",
        ),
        "postconditions": ("followup_result_recorded",),
    },
}
_PACKAGE_SECTION_TITLE_LABELS: dict[str, str] = {
    "runtime guidance": "运行时指引",
    "output expectations": "输出要求",
    "guardrails": "边界要求",
    "workflow": "工作流",
}


def _build_contract_summary(
    *,
    intent_scope: str,
    preconditions: tuple[str, ...],
    required_inputs: tuple[str, ...],
    allowed_tools: tuple[str, ...],
    expected_outputs: tuple[str, ...],
    artifact_writeback_rules: tuple[str, ...],
    known_blockers: tuple[str, ...],
    postconditions: tuple[str, ...],
) -> str:
    lines = [
        f"- 意图范围：{intent_scope}",
        f"- 前置条件：{', '.join(preconditions) if preconditions else '无'}",
        f"- 必需输入：{', '.join(required_inputs) if required_inputs else '无'}",
        f"- 允许工具：{', '.join(allowed_tools) if allowed_tools else '无'}",
        f"- 预期输出：{', '.join(expected_outputs) if expected_outputs else '无'}",
        "- 产物写回规则："
        + (", ".join(artifact_writeback_rules) if artifact_writeback_rules else "无"),
        f"- 已知阻塞：{', '.join(known_blockers) if known_blockers else '无'}",
        f"- 完成条件：{', '.join(postconditions) if postconditions else '无'}",
    ]
    return "\n".join(lines)


def _parse_package_sections(
    package: SkillPackageManifest | None,
) -> tuple[PromptSection, ...]:
    if package is None or not package.body.strip():
        return ()

    sections: list[PromptSection] = []
    current_title: str | None = None
    current_lines: list[str] = []

    def _flush() -> None:
        nonlocal current_title, current_lines
        body = "\n".join(current_lines).strip()
        if body:
            display_title = _PACKAGE_SECTION_TITLE_LABELS.get(
                str(current_title or "").strip().lower(),
                current_title or package.display_name,
            )
            key = (
                (current_title or "package_guidance")
                .lower()
                .replace(" ", "_")
                .replace("/", "_")
            )
            sections.append(
                PromptSection(
                    key=f"package_{key}",
                    title=display_title,
                    body=body,
                )
            )
        current_title = None
        current_lines = []

    for raw_line in package.body.splitlines():
        line = raw_line.rstrip()
        if line.startswith("# "):
            _flush()
            current_title = line[2:].strip()
            continue
        if line.startswith("## "):
            _flush()
            current_title = line[3:].strip()
            continue
        current_lines.append(line)
    _flush()
    return tuple(section for section in sections if section.normalized_body())


def build_skill_contract(
    *,
    skill_key: str,
    family_skill_key: str,
    display_name: str,
    executor_ref: str,
    prerequisites: list[str] | tuple[str, ...] | None,
    artifact_types: list[str] | tuple[str, ...] | None,
    default_params: dict[str, Any] | None,
    package: SkillPackageManifest | None,
    prompt_overlay: str | None,
) -> SkillContract:
    blueprint = _CONTRACT_BLUEPRINTS.get(
        family_skill_key, _CONTRACT_BLUEPRINTS.get(skill_key, {})
    )
    preconditions = tuple(prerequisites or ())
    required_inputs = tuple(blueprint.get("required_inputs") or ())
    allowed_tools = tuple(blueprint.get("allowed_tools") or ())
    expected_outputs = tuple(artifact_types or blueprint.get("expected_outputs") or ())
    artifact_writeback_rules = tuple(blueprint.get("artifact_writeback_rules") or ())
    known_blockers = tuple(blueprint.get("known_blockers") or ())
    postconditions = tuple(blueprint.get("postconditions") or ())
    intent_scope = str(
        blueprint.get("intent_scope") or "完成该 public skill 对应的能力合同。"
    )

    sections = [
        PromptSection(
            key="skill_contract",
            title="技能合同",
            body=_build_contract_summary(
                intent_scope=intent_scope,
                preconditions=preconditions,
                required_inputs=required_inputs,
                allowed_tools=allowed_tools,
                expected_outputs=expected_outputs,
                artifact_writeback_rules=artifact_writeback_rules,
                known_blockers=known_blockers,
                postconditions=postconditions,
            ),
        )
    ]
    sections.extend(_parse_package_sections(package))
    if prompt_overlay and str(prompt_overlay).strip():
        sections.append(
            PromptSection(
                key="skill_profile_overlay",
                title="技能补充画像",
                body=str(prompt_overlay).strip(),
            )
        )

    return SkillContract(
        skill_key=skill_key,
        family_skill_key=family_skill_key,
        display_name=display_name,
        executor_ref=executor_ref,
        intent_scope=intent_scope,
        preconditions=preconditions,
        required_inputs=required_inputs,
        allowed_tools=allowed_tools,
        expected_outputs=expected_outputs,
        artifact_writeback_rules=artifact_writeback_rules,
        known_blockers=known_blockers,
        postconditions=postconditions,
        default_params=dict(default_params or {}),
        prompt_sections=tuple(sections),
    )
