"""Deterministic action planning from the durable ontology world."""

from __future__ import annotations

from typing import Any

from app.ontology import OntologyRegistry, load_default_ontology
from app.ontology.schemas import ActionTypeDefinition

ACTION_INPUT_DEFAULTS: dict[str, dict[str, str]] = {
    "generate_question_set": {
        "question_count": "orchestrator_policy",
        "generation_mode": "orchestrator_policy",
    },
    "run_answer_fetch": {
        "platforms": "platform_policy",
    },
    "generate_report": {
        "report_kind": "orchestrator_policy",
    },
    "export_evidence_set": {
        "format": "user_or_default_export_policy",
    },
    "generate_official_website_evidence_plan": {
        "improvement_scope": "official_website_evidence_policy",
    },
}


ACTION_OBJECT_PREREQUISITES: dict[str, tuple[tuple[str, int], ...]] = {
    "generate_brand_context": (("brand_entity", 1),),
    "generate_persona_map": (("brand_entity", 1),),
    "generate_question_set": (("brand_entity", 1),),
    "update_brand_profile": (("brand_entity", 1),),
    "confirm_question_set": (("simulated_question", 1),),
    "record_user_feedback": (("brand_entity", 1),),
    "run_answer_fetch": (("simulated_question", 1),),
    "generate_report": (("platform_answer", 1),),
    "generate_official_website_evidence_plan": (("official_website_asset", 1),),
    "create_monitoring_plan": (("simulated_question", 1),),
    "update_monitoring_plan": (("monitoring_plan", 1),),
    "apply_table_import": (("brand_entity", 1),),
    "compare_snapshots": (("metric_snapshot", 2),),
    "export_evidence_set": (("evidence_set", 1),),
}


STATE_INPUT_ALIASES: dict[str, tuple[str, ...]] = {
    "actor_id": ("actor_id", "user_id"),
    "feedback_type": ("feedback_type",),
    "question_count": ("question_count",),
    "generation_mode": ("generation_mode", "analysis_mode"),
    "question_ids": ("question_ids", "selected_question_ids"),
    "platforms": ("platforms", "platform_filter", "selected_platforms"),
    "report_kind": ("report_kind", "report_type"),
    "cadence": ("cadence", "frequency"),
    "change_type": ("change_type", "monitoring_plan_change_type"),
    "mapping": ("mapping",),
    "rows": ("rows",),
    "baseline_snapshot_id": ("baseline_snapshot_id",),
    "current_snapshot_id": ("current_snapshot_id",),
    "evidence_set_id": ("evidence_set_id",),
    "official_domain": ("official_domain", "official_website", "domain"),
    "improvement_scope": ("improvement_scope",),
    "format": ("format", "export_format"),
}


ACTION_REASON_BY_KEY: dict[str, str] = {
    "generate_brand_context": "品牌对象存在，但竞品和品牌上下文还没有沉淀成对象。",
    "generate_persona_map": "已有品牌上下文，可以继续沉淀人群和场景对象。",
    "generate_question_set": "还没有可执行的问题对象，需要先生成或导入问题组。",
    "confirm_question_set": "问题对象已经存在，但还缺少人的确认，不能直接进入抓取。",
    "run_answer_fetch": "已有可用问题对象，但还没有平台回答证据。",
    "generate_report": "已有平台回答证据，可以生成报告和指标对象。",
    "generate_official_website_evidence_plan": (
        "官网资产已经暴露出引用或内容承载缺口，需要在人确认后生成可执行的官网证据页优化建议。"
    ),
    "create_monitoring_plan": "已有分析结果，可以让用户确认是否进入持续监测。",
    "update_monitoring_plan": "监测计划已经存在，后续启用、暂停、归档和配置调整都应作为受控动作记录。",
    "compare_snapshots": "已有多个指标快照，可以做变化对比。",
    "export_evidence_set": "已有证据集合，可以导出供复核或分享。",
    "record_user_feedback": "用户反馈应记录为可审计动作，再驱动后续编排。",
}

OFFICIAL_WEBSITE_CITATION_GAP_STATUSES = frozenset({"not_cited", "weak"})
OFFICIAL_WEBSITE_CONTENT_GAP_STATUSES = frozenset(
    {"unreachable", "partially_readable", "thin_content"}
)


class BrandOntologyActionPlannerService:
    """Turns object-world facts into safe action readiness and next-step advice."""

    def __init__(self, *, registry: OntologyRegistry | None = None) -> None:
        self.registry = registry or load_default_ontology()

    def build_plan(
        self,
        *,
        ontology_world: dict[str, Any] | None,
        state: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if not isinstance(ontology_world, dict):
            return None
        entity_id = str(ontology_world.get("entity_id") or "").strip()
        if not entity_id:
            return None

        state_payload = state or {}
        summaries = _summaries_by_type(ontology_world)
        official_website_signal = _official_website_signal(
            ontology_world=ontology_world,
            summaries=summaries,
        )
        available_inputs, inferred_inputs = _collect_available_inputs(
            entity_id=entity_id,
            summaries=summaries,
            state=state_payload,
            official_website_signal=official_website_signal,
        )
        governance_status = _governance_status(ontology_world)
        action_readiness = [
            self._build_action_readiness(
                action=action,
                summaries=summaries,
                available_inputs=available_inputs,
            )
            for action in self.registry.action_types
        ]
        readiness_by_key = {item["action_key"]: item for item in action_readiness}
        feedback_summary = _feedback_summary(ontology_world)
        recommended_items = (
            _recommend_action_items(
                summaries=summaries,
                feedback_summary=feedback_summary,
                official_website_signal=official_website_signal,
            )
            if governance_status != "blocked"
            else []
        )
        recommendations = [
            _merge_recommended_action(
                readiness=readiness_by_key[item["action_key"]],
                item=item,
            )
            for item in recommended_items
            if item["action_key"] in readiness_by_key
        ]

        return {
            "entity_id": entity_id,
            "world_phase": _world_phase(summaries),
            "governance_status": governance_status,
            "available_inputs": sorted(available_inputs),
            "inferred_inputs": inferred_inputs,
            "gaps": [
                *_governance_gaps(governance_status),
                *_build_gaps(
                    summaries,
                    official_website_signal=official_website_signal,
                ),
            ],
            "recommended_actions": recommendations,
            "action_readiness": action_readiness,
            "blocked_actions": [
                item for item in action_readiness if item["readiness"] == "blocked"
            ],
            "needs_human_confirmation": [
                item
                for item in recommendations
                if item["requires_confirmation"]
                or item["readiness"] in {"needs_input", "needs_confirmation"}
            ],
            "guardrails": [
                "payload_missing_inputs_must_not_call_action_service",
                "requires_confirmation_must_ask_human_first",
                "llm_may_recommend_but_must_not_mutate_objects_directly",
                *(
                    ["ontology_governance_status_must_be_respected"]
                    if governance_status in {"blocked", "degraded"}
                    else []
                ),
            ],
        }

    def _build_action_readiness(
        self,
        *,
        action: ActionTypeDefinition,
        summaries: dict[str, dict[str, Any]],
        available_inputs: set[str],
    ) -> dict[str, Any]:
        missing_objects = [
            {"object_type": object_type, "required_min": required_min}
            for object_type, required_min in ACTION_OBJECT_PREREQUISITES.get(
                action.key, ()
            )
            if _total(summaries, object_type) < required_min
        ]
        if (
            action.key in {"run_answer_fetch", "create_monitoring_plan"}
            and _total(summaries, "simulated_question") > 0
            and _confirmed_or_fetched_questions(summaries) <= 0
        ):
            missing_objects.append(
                {
                    "object_type": "simulated_question",
                    "required_status": "confirmed",
                }
            )
        defaultable_inputs = ACTION_INPUT_DEFAULTS.get(action.key, {})
        missing_inputs = [
            input_key
            for input_key in action.required_inputs
            if input_key not in available_inputs and input_key not in defaultable_inputs
        ]
        defaulted_inputs = [
            {
                "input_key": input_key,
                "source": defaultable_inputs[input_key],
            }
            for input_key in action.required_inputs
            if input_key not in available_inputs and input_key in defaultable_inputs
        ]
        if missing_objects:
            readiness = "blocked"
        elif missing_inputs:
            readiness = "needs_input"
        elif action.requires_confirmation:
            readiness = "needs_confirmation"
        elif defaulted_inputs:
            readiness = "ready_with_defaults"
        else:
            readiness = "ready"

        return {
            "action_key": action.key,
            "display_name": action.display_name,
            "readiness": readiness,
            "permission_scope": action.permission_scope,
            "requires_confirmation": action.requires_confirmation,
            "missing_inputs": missing_inputs,
            "defaulted_inputs": defaulted_inputs,
            "missing_objects": missing_objects,
            "writes": list(action.writes),
            "creates_links": list(action.creates_links),
        }


def _summaries_by_type(ontology_world: dict[str, Any]) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    for raw_summary in ontology_world.get("object_summaries") or []:
        if not isinstance(raw_summary, dict):
            continue
        object_type = str(raw_summary.get("object_type") or "").strip()
        if object_type:
            summaries[object_type] = raw_summary
    return summaries


def _collect_available_inputs(
    *,
    entity_id: str,
    summaries: dict[str, dict[str, Any]],
    state: dict[str, Any],
    official_website_signal: dict[str, Any],
) -> tuple[set[str], dict[str, str]]:
    available = {"brand_entity_id"}
    inferred = {"brand_entity_id": "ontology_world.entity_id"}

    for input_key, aliases in STATE_INPUT_ALIASES.items():
        if _state_has_any_value(state, aliases):
            available.add(input_key)
            inferred[input_key] = "runtime_state"

    if _total(summaries, "simulated_question") > 0:
        available.add("question_ids")
        inferred.setdefault("question_ids", "ontology_world.simulated_question")
    if _total(summaries, "question_set") > 0:
        available.add("question_set_id")
        available.add("question_set_ids")
        inferred.setdefault("question_set_ids", "ontology_world.question_set")
    if _total(summaries, "monitoring_plan") > 0:
        available.add("monitoring_plan_id")
        inferred.setdefault("monitoring_plan_id", "ontology_world.monitoring_plan")
    if _total(summaries, "report_artifact") > 0:
        available.add("report_id")
        inferred.setdefault("report_id", "ontology_world.report_artifact")
    if _total(summaries, "metric_snapshot") >= 2:
        available.add("baseline_snapshot_id")
        available.add("current_snapshot_id")
        inferred.setdefault("baseline_snapshot_id", "ontology_world.metric_snapshot")
        inferred.setdefault("current_snapshot_id", "ontology_world.metric_snapshot")
    if _total(summaries, "evidence_set") > 0:
        available.add("evidence_set_id")
        inferred.setdefault("evidence_set_id", "ontology_world.evidence_set")

    official_domain = str(official_website_signal.get("domain") or "").strip()
    if official_domain:
        available.add("official_domain")
        inferred.setdefault("official_domain", "ontology_world.official_website_asset")

    table_intake = state.get("table_intake_result") or {}
    if isinstance(table_intake, dict):
        if table_intake.get("mapping"):
            available.add("mapping")
            inferred.setdefault("mapping", "runtime_state.table_intake_result")
        if table_intake.get("rows"):
            available.add("rows")
            inferred.setdefault("rows", "runtime_state.table_intake_result")

    return available, inferred


def _state_has_any_value(state: dict[str, Any], aliases: tuple[str, ...]) -> bool:
    for alias in aliases:
        if _has_value(state.get(alias)):
            return True
    fetch_config = state.get("fetch_config")
    if isinstance(fetch_config, dict):
        for alias in aliases:
            if _has_value(fetch_config.get(alias)):
                return True
    user_decisions = state.get("user_decisions")
    if isinstance(user_decisions, dict):
        for alias in aliases:
            if _has_value(user_decisions.get(alias)):
                return True
    return False


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _recommend_action_items(
    *,
    summaries: dict[str, dict[str, Any]],
    feedback_summary: dict[str, Any],
    official_website_signal: dict[str, Any],
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []

    def append(
        action_key: str,
        *,
        reason: str | None = None,
        source: str = "ontology_world",
        target_object_type: str | None = None,
        target_object_id: str | None = None,
        feedback_type: str | None = None,
        missing_inputs: list[str] | None = None,
    ) -> None:
        recommendations.append(
            {
                "action_key": action_key,
                "reason": reason,
                "source": source,
                "target_object_type": target_object_type,
                "target_object_id": target_object_id,
                "feedback_type": feedback_type,
                "missing_inputs": missing_inputs or [],
            }
        )

    if _total(summaries, "competitor_entity") <= 0:
        append("generate_brand_context")
    if (
        _total(summaries, "competitor_entity") > 0
        and _total(summaries, "audience_persona") <= 0
        and _total(summaries, "usage_scenario") <= 0
    ):
        append("generate_persona_map")

    question_total = _total(summaries, "simulated_question")
    confirmed_or_fetched_questions = _confirmed_or_fetched_questions(summaries)
    if question_total <= 0:
        append("generate_question_set")
    elif confirmed_or_fetched_questions <= 0:
        append("confirm_question_set")
    elif _total(summaries, "platform_answer") <= 0:
        append("run_answer_fetch")
    elif _total(summaries, "report_artifact") <= 0:
        append("generate_report")
    elif _total(summaries, "monitoring_plan") <= 0:
        append("create_monitoring_plan")
    else:
        append(
            "update_monitoring_plan",
            reason=(
                "监测计划已经进入对象世界，启用、暂停、归档或调整配置都应继续通过受控动作处理。"
            ),
        )

    official_website_item = _official_website_action_item(official_website_signal)
    if official_website_item:
        append(**official_website_item)

    correction_without_text_count = _int_value(
        feedback_summary.get("correction_without_text_count")
    )
    correction_count = _int_value(feedback_summary.get("correction_count"))
    dismissed_count = _int_value(feedback_summary.get("dismissed_count"))
    if correction_without_text_count > 0:
        latest = _latest_feedback_for_type(feedback_summary, "correct")
        append(
            "record_user_feedback",
            reason="有情报判断被标记为修正，但还缺少明确修正说明，需要先向用户补问。",
            source="finding_feedback",
            target_object_type="intelligence_finding",
            target_object_id=latest.get("finding_id"),
            feedback_type="correct",
            missing_inputs=["feedback_text"],
        )
    elif (
        correction_count > 0
        and _total(summaries, "platform_answer") > 0
        and _total(summaries, "report_artifact") > 0
    ):
        latest = _latest_feedback_for_type(feedback_summary, "correct")
        append(
            "generate_report",
            reason="用户已经对情报判断提出修正，需要基于现有回答证据重新整理报告和判断。",
            source="finding_feedback",
            target_object_type="intelligence_finding",
            target_object_id=latest.get("finding_id"),
            feedback_type="correct",
        )
    if (
        dismissed_count > 0
        and _total(summaries, "platform_answer") > 0
        and _total(summaries, "report_artifact") > 0
    ):
        latest = _latest_feedback_for_type(feedback_summary, "dismiss")
        append(
            "generate_report",
            reason="用户暂不采纳部分情报判断，需要复核报告结论并重新沉淀判断。",
            source="finding_feedback",
            target_object_type="intelligence_finding",
            target_object_id=latest.get("finding_id"),
            feedback_type="dismiss",
        )

    if _total(summaries, "metric_snapshot") >= 2:
        append("compare_snapshots")
    if _total(summaries, "evidence_set") > 0:
        append("export_evidence_set")
    return _unique_action_items(recommendations)[:5]


def _official_website_action_item(
    official_website_signal: dict[str, Any],
) -> dict[str, Any] | None:
    domain = str(official_website_signal.get("domain") or "").strip()
    if not domain:
        return None

    citation_status = str(official_website_signal.get("status") or "").strip()
    content_status = str(official_website_signal.get("content_status") or "").strip()
    citation_gap = citation_status in OFFICIAL_WEBSITE_CITATION_GAP_STATUSES
    content_gap = content_status in OFFICIAL_WEBSITE_CONTENT_GAP_STATUSES
    if not citation_gap and not content_gap:
        return None

    gap_labels: list[str] = []
    if citation_gap:
        gap_labels.append(_official_citation_gap_label(citation_status))
    if content_gap:
        gap_labels.append(_official_content_gap_label(content_status))
    gap_text = "；".join(item for item in gap_labels if item)
    reason = (
        f"官网资产 {domain} 的观测结果显示：{gap_text}。"
        "这不是自动改官网，而是先生成一份可复核的官网证据页优化建议。"
    )
    return {
        "action_key": "generate_official_website_evidence_plan",
        "reason": reason,
        "source": "official_website_asset",
        "target_object_type": "official_website_asset",
        "target_object_id": domain,
    }


def _merge_recommended_action(
    *,
    readiness: dict[str, Any],
    item: dict[str, Any],
) -> dict[str, Any]:
    merged = {
        **readiness,
        "reason": item.get("reason")
        or ACTION_REASON_BY_KEY.get(str(item.get("action_key") or ""), ""),
        "source": item.get("source") or "ontology_world",
        "target_object_type": item.get("target_object_type"),
        "target_object_id": item.get("target_object_id"),
        "feedback_type": item.get("feedback_type"),
    }
    missing_inputs = [
        str(input_key)
        for input_key in readiness.get("missing_inputs") or []
        if str(input_key).strip()
    ]
    missing_inputs.extend(
        str(input_key)
        for input_key in item.get("missing_inputs") or []
        if str(input_key).strip()
    )
    if item.get("feedback_type"):
        missing_inputs = [
            input_key for input_key in missing_inputs if input_key != "feedback_type"
        ]
    if missing_inputs:
        merged["readiness"] = "needs_input"
        merged["missing_inputs"] = _unique_strings(missing_inputs)
    return merged


def _official_website_signal(
    *,
    ontology_world: dict[str, Any],
    summaries: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    raw_observation = ontology_world.get("official_website_observation")
    if isinstance(raw_observation, dict):
        content_audit = raw_observation.get("content_audit") or {}
        if not isinstance(content_audit, dict):
            content_audit = {}
        return {
            "status": str(raw_observation.get("status") or "").strip(),
            "domain": str(raw_observation.get("domain") or "").strip(),
            "citation_count": _int_value(raw_observation.get("citation_count")),
            "value_score": _int_value(raw_observation.get("value_score")),
            "content_status": str(content_audit.get("status") or "").strip(),
            "content_score": _int_value(content_audit.get("value_score")),
            "gaps": list(raw_observation.get("gaps") or []),
            "content_gaps": list(content_audit.get("gaps") or []),
        }

    summary = summaries.get("official_website_asset") or {}
    if _int_value(summary.get("total")) <= 0:
        return {}

    samples = summary.get("samples") if isinstance(summary.get("samples"), list) else []
    first_sample = next((item for item in samples if isinstance(item, dict)), {})
    domain = str(first_sample.get("object_id") or "").strip()
    if domain == "official-website":
        domain = ""
    status = str(first_sample.get("lifecycle") or "").strip()
    if not status:
        status = _first_count_key(summary.get("lifecycle_counts") or {})
    if not status:
        status = _first_count_key(summary.get("sample_lifecycle_counts") or {})
    return {
        "status": status,
        "domain": domain,
        "citation_count": 0,
        "value_score": 0,
        "content_status": "",
        "content_score": 0,
        "gaps": [],
        "content_gaps": [],
    }


def _official_website_gaps(
    official_website_signal: dict[str, Any],
) -> list[dict[str, Any]]:
    status = str(official_website_signal.get("status") or "").strip()
    domain = str(official_website_signal.get("domain") or "").strip()
    content_status = str(official_website_signal.get("content_status") or "").strip()
    gaps: list[dict[str, Any]] = []
    if status == "missing_domain" or (official_website_signal and not domain):
        gaps.append(
            {
                "key": "official_website_domain_missing",
                "severity": "optional",
                "object_type": "official_website_asset",
                "message": "品牌对象缺少官网域名，无法判断官网是否承担品牌自有证据价值。",
            }
        )
        return gaps
    if status in OFFICIAL_WEBSITE_CITATION_GAP_STATUSES:
        gaps.append(
            {
                "key": "official_website_citation_gap",
                "severity": "optional",
                "object_type": "official_website_asset",
                "message": _official_citation_gap_label(status),
            }
        )
    if content_status in OFFICIAL_WEBSITE_CONTENT_GAP_STATUSES:
        gaps.append(
            {
                "key": "official_website_content_gap",
                "severity": "optional",
                "object_type": "official_website_asset",
                "message": _official_content_gap_label(content_status),
            }
        )
    return gaps


def _official_citation_gap_label(status: str) -> str:
    return {
        "not_cited": "AI 回答引用了大量外部来源，但没有引用官网",
        "weak": "官网已经被引用，但覆盖的问题或平台偏少",
    }.get(status, "官网引用价值偏弱")


def _official_content_gap_label(status: str) -> str:
    return {
        "unreachable": "官网首页当前不可读，难以成为稳定证据入口",
        "partially_readable": "官网首页可读，但标题、描述、正文或结构化信息仍偏弱",
        "thin_content": "官网首页可读内容偏薄，承载品牌事实的能力不足",
    }.get(status, "官网内容承载能力偏弱")


def _first_count_key(counts: Any) -> str:
    if not isinstance(counts, dict):
        return ""
    for key, value in counts.items():
        if str(key).strip() and _int_value(value) > 0:
            return str(key).strip()
    return ""


def _feedback_summary(ontology_world: dict[str, Any]) -> dict[str, Any]:
    raw_summary = ontology_world.get("finding_feedback_summary") or {}
    if isinstance(raw_summary, dict):
        return raw_summary
    return {}


def _governance_status(ontology_world: dict[str, Any]) -> str:
    raw_report = ontology_world.get("governance_report") or {}
    if not isinstance(raw_report, dict):
        return "unknown"
    status = str(raw_report.get("status") or "").strip().lower()
    return status or "unknown"


def _governance_gaps(governance_status: str) -> list[dict[str, Any]]:
    if governance_status != "blocked":
        return []
    return [
        {
            "key": "ontology_governance_blocked",
            "severity": "blocking",
            "object_type": "ontology_world",
            "message": "对象世界治理状态为 blocked，不能继续执行推荐动作。",
        }
    ]


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _latest_feedback_for_type(
    feedback_summary: dict[str, Any],
    feedback_type: str,
) -> dict[str, Any]:
    latest_items = feedback_summary.get("latest") or []
    if not isinstance(latest_items, list):
        return {}
    for item in latest_items:
        if not isinstance(item, dict):
            continue
        if str(item.get("feedback_type") or "") == feedback_type:
            return item
    return {}


def _unique_action_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        action_key = str(item.get("action_key") or "").strip()
        if not action_key or action_key in seen:
            continue
        seen.add(action_key)
        result.append(item)
    return result


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _confirmed_or_fetched_questions(
    summaries: dict[str, dict[str, Any]],
) -> int:
    return _lifecycle(summaries, "simulated_question", "confirmed") + _lifecycle(
        summaries,
        "simulated_question",
        "fetched",
    )


def _world_phase(summaries: dict[str, dict[str, Any]]) -> str:
    if _total(summaries, "brand_entity") <= 0:
        return "missing_brand"
    if (
        _total(summaries, "report_artifact") > 0
        and _total(summaries, "monitoring_plan") > 0
    ):
        return "operating_world"
    if _total(summaries, "report_artifact") > 0:
        return "report_ready"
    if _total(summaries, "platform_answer") > 0:
        return "evidence_ready"
    if (
        _lifecycle(summaries, "simulated_question", "confirmed")
        + _lifecycle(summaries, "simulated_question", "fetched")
        > 0
    ):
        return "questions_confirmed"
    if _total(summaries, "simulated_question") > 0:
        return "questions_generated"
    if (
        _total(summaries, "audience_persona") > 0
        or _total(summaries, "usage_scenario") > 0
    ):
        return "persona_ready"
    if _total(summaries, "competitor_entity") > 0:
        return "brand_context_ready"
    return "brand_ready"


def _build_gaps(
    summaries: dict[str, dict[str, Any]],
    *,
    official_website_signal: dict[str, Any],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    official_website_gaps = _official_website_gaps(official_website_signal)
    if _total(summaries, "competitor_entity") <= 0:
        gaps.append(
            {
                "key": "brand_context_missing",
                "severity": "blocking",
                "object_type": "competitor_entity",
                "message": "缺少竞品和品牌上下文对象。",
            }
        )
    if _total(summaries, "simulated_question") <= 0:
        gaps.append(
            {
                "key": "question_set_missing",
                "severity": "blocking",
                "object_type": "simulated_question",
                "message": "缺少可执行的问题对象。",
            }
        )
        gaps.extend(official_website_gaps)
        return gaps

    confirmed_or_fetched_questions = _lifecycle(
        summaries, "simulated_question", "confirmed"
    ) + _lifecycle(summaries, "simulated_question", "fetched")
    if confirmed_or_fetched_questions <= 0:
        gaps.append(
            {
                "key": "question_confirmation_needed",
                "severity": "blocking",
                "object_type": "simulated_question",
                "message": "问题对象尚未确认，不能直接抓取平台回答。",
            }
        )
        gaps.extend(official_website_gaps)
        return gaps

    if _total(summaries, "platform_answer") <= 0:
        gaps.append(
            {
                "key": "answer_fetch_missing",
                "severity": "blocking",
                "object_type": "platform_answer",
                "message": "缺少平台回答证据对象。",
            }
        )
        gaps.extend(official_website_gaps)
        return gaps
    if _total(summaries, "report_artifact") <= 0:
        gaps.append(
            {
                "key": "report_missing",
                "severity": "blocking",
                "object_type": "report_artifact",
                "message": "已有回答证据，但还没有报告对象。",
            }
        )
    if _total(summaries, "monitoring_plan") <= 0:
        gaps.append(
            {
                "key": "monitoring_plan_missing",
                "severity": "optional",
                "object_type": "monitoring_plan",
                "message": "还没有持续监测计划对象。",
            }
        )
    gaps.extend(official_website_gaps)
    return gaps


def _total(summaries: dict[str, dict[str, Any]], object_type: str) -> int:
    try:
        return int((summaries.get(object_type) or {}).get("total") or 0)
    except (TypeError, ValueError):
        return 0


def _lifecycle(
    summaries: dict[str, dict[str, Any]],
    object_type: str,
    status: str,
) -> int:
    summary = summaries.get(object_type) or {}
    counts = summary.get("lifecycle_counts") or summary.get("sample_lifecycle_counts")
    if not isinstance(counts, dict):
        return 0
    try:
        return int(counts.get(status) or 0)
    except (TypeError, ValueError):
        return 0
