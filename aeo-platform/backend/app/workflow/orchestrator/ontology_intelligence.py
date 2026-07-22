"""Ontology intelligence explanation replies (P2 knife 3)."""

from __future__ import annotations

import re
from typing import Any, Mapping

from app.workflow.orchestrator.ontology_format import (
    _action_readiness_label,
    _ontology_brand_label,
    _ontology_float,
    _ontology_int,
    _ontology_object_summaries,
    _ontology_status_label,
    _relationship_is_core,
    _source_domain_sort_key,
)
from app.workflow.orchestrator.run_context import _get_latest_user_message

CORE_RELATIONSHIP_TYPES: frozenset[str] = frozenset(
    {
        "brand_has_intelligence_finding",
        "question_answered_by",
        "platform_answer_cites_source",
        "evidence_set_contains_answer",
        "intelligence_finding_uses_evidence_set",
        "report_contains_intelligence_finding",
        "report_uses_evidence_set",
    }
)

def _is_ontology_intelligence_explanation_request(state: Mapping[str, Any]) -> bool:
    latest = str(state.get("latest_user_input") or _get_latest_user_message(state))
    if not latest.strip():
        return False
    normalized = re.sub(r"\s+", "", latest)
    explanation_markers = (
        "为什么",
        "哪些",
        "哪个",
        "谁",
        "什么",
        "如何",
        "怎么",
        "是否",
        "能不能",
        "要不要",
        "需要",
        "解释",
        "说明",
        "支撑",
        "影响",
        "风险",
    )
    ontology_markers = (
        "官网",
        "引用",
        "来源",
        "外部来源",
        "证据",
        "证据主题",
        "证据包",
        "对象",
        "关系",
        "辅助关联",
        "弱关系",
        "其他关联",
        "隐藏关系",
        "情报",
        "结论",
        "转化率",
        "替代",
        "叙事",
        "动作",
        "监测",
        "监测计划",
        "确认",
    )
    action_boundary_markers = (
        "跳过确认",
        "直接执行",
        "自动执行",
        "需要确认",
        "人确认",
        "人工确认",
        "先确认",
        "下一步",
    )
    action_markers = ("创建", "生成", "执行", "抓取", "采集", "导入", "修改", "更新")
    if not any(marker in normalized for marker in explanation_markers):
        return False
    if not any(marker in normalized for marker in ontology_markers):
        return False
    if (
        any(marker in normalized for marker in action_markers)
        and "不要重新抓取" not in normalized
        and not any(marker in normalized for marker in action_boundary_markers)
    ):
        return False
    dashboard_context = state.get("dashboard_context") or {}
    if isinstance(dashboard_context, dict) and (
        dashboard_context.get("entity_id") or dashboard_context.get("brand")
    ):
        return True
    return "对象" in normalized or "情报" in normalized

def _format_source_domains_for_reply(ontology_world: dict[str, Any]) -> str:
    domains = ontology_world.get("source_domain_summary") or []
    if not isinstance(domains, list) or not domains:
        return "暂无可用来源域名摘要。"
    lines: list[str] = []
    for item in domains[:5]:
        if not isinstance(item, dict):
            continue
        domain = str(item.get("domain") or "").strip() or "unknown"
        role = str(
            item.get("source_role_label") or item.get("source_role") or ""
        ).strip()
        citations = int(item.get("citation_count") or 0)
        answers = int(item.get("answer_count") or 0)
        detail = f"{domain}：{citations} 个引用"
        if answers:
            detail += f"，覆盖 {answers} 条回答"
        if role:
            detail += f"，类型是{role}"
        lines.append(detail)
    return "\n".join(f"- {line}" for line in lines) or "暂无可用来源域名摘要。"

def _format_relationships_for_reply(
    ontology_world: dict[str, Any],
    *,
    include_supporting: bool = False,
    supporting_only: bool = False,
) -> str:
    core_relationships = ontology_world.get("relationship_summary") or []
    supporting_relationships = (
        ontology_world.get("supporting_relationship_summary") or []
    )
    if supporting_only:
        if supporting_relationships:
            relationships = supporting_relationships
        elif isinstance(core_relationships, list):
            relationships = core_relationships
        else:
            relationships = []
    elif include_supporting:
        relationships = list(core_relationships) + list(supporting_relationships)
    else:
        relationships = core_relationships
    if not isinstance(relationships, list) or not relationships:
        counts = ontology_world.get("relationship_counts") or {}
        if not isinstance(counts, dict) or not counts:
            return (
                "暂无可用辅助关联摘要。"
                if supporting_only
                else "暂无可用核心关系摘要。"
            )
        relationships = []
        for key, value in counts.items():
            item = {"link_type": key, "display_name": key, "count": value}
            is_core = key in CORE_RELATIONSHIP_TYPES
            if supporting_only and is_core:
                continue
            if not supporting_only and not include_supporting and not is_core:
                continue
            relationships.append(item)
    priority = {
        "brand_has_intelligence_finding": 1,
        "question_answered_by": 2,
        "platform_answer_cites_source": 3,
        "report_contains_intelligence_finding": 4,
        "intelligence_finding_uses_evidence_set": 5,
        "evidence_set_contains_answer": 6,
    }
    filtered_relationships: list[dict[str, Any]] = []
    for item in relationships:
        if not isinstance(item, dict):
            continue
        count = int(item.get("count") or 0)
        if count <= 0:
            continue
        is_core = _relationship_is_core(item)
        if supporting_only and is_core:
            continue
        if not supporting_only and not include_supporting and not is_core:
            continue
        filtered_relationships.append(item)
    sorted_relationships = sorted(
        filtered_relationships,
        key=lambda item: priority.get(str(item.get("link_type") or ""), 99),
    )
    lines = []
    for item in sorted_relationships[:6]:
        name = str(item.get("display_name") or item.get("link_type") or "").strip()
        count = int(item.get("count") or 0)
        if name and count:
            lines.append(f"- {name}：{count}")
    if lines:
        return "\n".join(lines)
    return "暂无可用辅助关联摘要。" if supporting_only else "暂无可用核心关系摘要。"

def _ontology_object_total(
    ontology_world: dict[str, Any],
    object_type: str,
) -> int:
    item = _ontology_object_summaries(ontology_world).get(object_type) or {}
    total = _ontology_int(item.get("total"))
    if total:
        return total
    if object_type == "source_domain":
        return len(
            [
                item
                for item in list(ontology_world.get("source_domain_summary") or [])
                if isinstance(item, dict)
            ]
        )
    if object_type == "evidence_cluster":
        return len(
            [
                item
                for item in list(ontology_world.get("evidence_clusters") or [])
                if isinstance(item, dict)
            ]
        )
    return 0

def _sorted_source_domains(
    ontology_world: dict[str, Any],
    *,
    prefer_external: bool = False,
) -> list[dict[str, Any]]:
    raw_domains = [
        item
        for item in list(ontology_world.get("source_domain_summary") or [])
        if isinstance(item, dict)
    ]
    if prefer_external:
        external = [item for item in raw_domains if not bool(item.get("is_official"))]
        if external:
            raw_domains = external
    return sorted(raw_domains, key=_source_domain_sort_key, reverse=True)

def _source_domain_reply_line(item: dict[str, Any]) -> str:
    domain = str(item.get("domain") or "").strip() or "unknown"
    role = str(item.get("source_role_label") or item.get("source_role") or "").strip()
    citations = _ontology_int(item.get("citation_count"))
    answers = _ontology_int(item.get("answer_count"))
    platforms = _ontology_int(item.get("platform_count"))
    samples = [
        str(sample).strip()
        for sample in list(item.get("sample_titles") or [])
        if str(sample).strip()
    ]
    detail = f"{domain}：{citations} 个引用"
    if answers:
        detail += f"，覆盖 {answers} 条回答"
    if platforms:
        detail += f"，覆盖 {platforms} 个回答来源"
    if role:
        detail += f"，类型是{role}"
    if samples:
        detail += f"，样本是{samples[0]}"
    return detail

def _evidence_cluster_sort_key(
    item: dict[str, Any],
) -> tuple[int, int, int, int, str]:
    topic_label = str(item.get("topic_label") or item.get("title") or "").strip()
    return (
        1 if topic_label == "综合外部来源" else 0,
        -_ontology_int(item.get("question_count")),
        -_ontology_int(item.get("answer_count")),
        -_ontology_int(item.get("citation_count")),
        str(item.get("title") or ""),
    )

def _sorted_evidence_clusters(
    ontology_world: dict[str, Any],
) -> list[dict[str, Any]]:
    clusters = [
        item
        for item in list(ontology_world.get("evidence_clusters") or [])
        if isinstance(item, dict)
    ]
    return sorted(clusters, key=_evidence_cluster_sort_key)

def _evidence_cluster_reply_line(item: dict[str, Any]) -> str:
    title = str(item.get("title") or "未命名证据主题").strip()
    topic = str(item.get("topic_label") or "").strip()
    role = str(item.get("source_role_label") or "").strip()
    citations = _ontology_int(item.get("citation_count"))
    answers = _ontology_int(item.get("answer_count"))
    questions = _ontology_int(item.get("question_count"))
    domains = _ontology_int(item.get("domain_count"))
    official_citations = _ontology_int(item.get("official_citation_count"))
    readout = str(item.get("business_readout") or "").strip()
    domain_items = [
        str(domain).strip()
        for domain in list(item.get("source_domains") or [])
        if str(domain).strip()
    ][:3]

    parts = [f"{title}：{citations} 个引用"]
    if answers:
        parts.append(f"{answers} 条回答")
    if questions:
        parts.append(f"{questions} 个问题")
    if domains:
        parts.append(f"{domains} 个域名")
    if official_citations:
        parts.append(f"官网引用 {official_citations} 个")
    else:
        parts.append("官网引用为 0")
    if topic:
        parts.append(f"主题是{topic}")
    if role:
        parts.append(f"来源类型是{role}")
    if domain_items:
        parts.append(f"代表域名是{'、'.join(domain_items)}")
    line = "，".join(parts)
    if readout:
        line += f"。{readout}"
    return line

def _available_action_items(
    state: Mapping[str, Any] | dict[str, Any],
    ontology_world: dict[str, Any],
) -> list[dict[str, Any]]:
    action_plan = state.get("ontology_action_plan") or {}
    raw_actions = []
    if isinstance(action_plan, dict):
        raw_actions = list(action_plan.get("recommended_actions") or [])
    if not raw_actions:
        raw_actions = list(ontology_world.get("available_actions") or [])
    return [item for item in raw_actions if isinstance(item, dict)]

def _action_reply_line(item: dict[str, Any]) -> str:
    display_name = str(
        item.get("display_name")
        or item.get("action_key")
        or item.get("key")
        or "未命名建议"
    ).strip()
    readiness = _action_readiness_label(item.get("readiness"))
    if bool(item.get("requires_confirmation")):
        readiness = "需要人确认"
    reason = str(item.get("reason") or "").strip()
    line = f"{display_name}：{readiness}"
    if reason:
        line += f"，原因是{reason}"
    return line

def _ontology_intelligence_question_kind(state: Mapping[str, Any] | dict[str, Any]) -> str:
    latest = str(state.get("latest_user_input") or _get_latest_user_message(state))
    normalized = re.sub(r"\s+", "", latest)
    if any(
        marker in normalized
        for marker in (
            "跳过确认",
            "需要确认",
            "人工确认",
            "人确认",
            "直接执行",
            "自动执行",
            "下一步",
            "监测计划",
        )
    ):
        return "action_boundary"
    if "证据簇" in normalized or "证据主题" in normalized or "证据包" in normalized:
        return "evidence_cluster_value"
    if any(marker in normalized for marker in ("替代", "取代", "外部来源")):
        return "source_substitution"
    if any(
        marker in normalized
        for marker in (
            "弱关系",
            "辅助关联",
            "其他关联",
            "隐藏关系",
            "非核心关系",
            "边缘关系",
            "全部关系",
            "所有关系",
        )
    ):
        return "supporting_relationships"
    if "关系" in normalized or "链路" in normalized or "风险" in normalized:
        return "relationship_risk"
    return "official_gap"

def _build_official_website_gap_reply(
    state: Mapping[str, Any],
    ontology_world: dict[str, Any],
) -> str:
    brand_label = _ontology_brand_label(state, ontology_world)
    official = ontology_world.get("official_website_observation") or {}
    if not isinstance(official, dict):
        official = {}
    official_domain = str(official.get("domain") or "官网").strip()
    citation_count = _ontology_int(official.get("citation_count"))
    citation_share = _ontology_float(official.get("citation_share"))
    observed_question_count = _ontology_int(official.get("question_count"))
    observed_platform_count = _ontology_int(official.get("platform_count"))
    status = str(official.get("status") or "").strip() or "unknown"
    status_label = _ontology_status_label(status)
    official_readout = str(official.get("business_readout") or "").strip()
    gaps = [
        str(item).strip()
        for item in list(official.get("gaps") or [])
        if str(item).strip()
    ]
    comparison_domains = official.get("comparison_domains") or []
    comparison_lines = []
    if isinstance(comparison_domains, list):
        for item in comparison_domains[:3]:
            if not isinstance(item, dict):
                continue
            domain = str(item.get("domain") or "").strip()
            count = _ontology_int(item.get("citation_count"))
            if domain:
                comparison_lines.append(f"{domain}（{count} 个引用）")

    def total_for(object_type: str) -> int:
        return _ontology_object_total(ontology_world, object_type)

    findings = ontology_world.get("intelligence_findings") or []
    finding_line = ""
    if isinstance(findings, list):
        for item in findings:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if "官网" in title or "引用" in title:
                finding_line = title
                evidence_summary = str(item.get("evidence_summary") or "").strip()
                if evidence_summary:
                    finding_line += f" 证据范围：{evidence_summary}。"
                break

    source_domains_text = _format_source_domains_for_reply(ontology_world)
    relationships_text = _format_relationships_for_reply(ontology_world)
    external_domains = (
        "、".join(comparison_lines) if comparison_lines else "外部汽车媒体和内容平台"
    )
    gap_text = "；".join(gaps) if gaps else "智能回答没有引用官网"

    return (
        f"结论：{brand_label}的官网引用转化率为 0，不是因为系统没有找到品牌证据，"
        f"而是因为当前证据里，官网 {official_domain} 的状态是{status_label}，"
        f"官网引用数为 {citation_count}，引用占比为 {citation_share:.1%}，"
        f"覆盖问题数为 {observed_question_count}，覆盖平台数为 {observed_platform_count}。\n\n"
        "支撑这个判断的证据有四层：\n"
        f"- 品牌：{brand_label}。\n"
        f"- 官网：{official_domain}，当前缺口是{gap_text}。\n"
        f"- 平台回答：{total_for('platform_answer')} 条。\n"
        f"- 引用来源：{total_for('citation_source')} 个，"
        f"被进一步聚合为 {total_for('source_domain')} 个来源域名和 "
        f"{total_for('evidence_cluster')} 个证据主题。\n\n"
        f"最直接的情报判断：{finding_line or official_readout or '官网暂未成为智能回答证据源。'}\n\n"
        "证据关系是：问题产生回答，回答引用来源，来源再聚合成域名和证据主题，"
        "最后支撑情报判断。当前关键关系如下：\n"
        f"{relationships_text}\n\n"
        "外部对照来源显示，品牌叙事主要被这些域名承接：\n"
        f"{source_domains_text}\n\n"
        f"业务影响：智能回答并不是没有谈到{brand_label}，而是更多用 {external_domains} "
        "这类外部来源来支撑判断。官网没有进入证据链，会让官方产品叙事、技术解释、"
        "车型信息和品牌立场更难被 AI 平台直接采用。\n\n"
        "下一步不应该自动改官网，也不应该直接跳过确认。更稳的建议是先生成一份"
        "官网证据页优化建议，明确哪些官网页面、标题、正文、结构化信息需要补强，"
        "再由人确认是否进入执行。"
    )

def _build_source_substitution_reply(
    state: Mapping[str, Any],
    ontology_world: dict[str, Any],
) -> str:
    brand_label = _ontology_brand_label(state, ontology_world)
    official = ontology_world.get("official_website_observation") or {}
    if not isinstance(official, dict):
        official = {}
    official_domain = str(official.get("domain") or "官网").strip()
    domains = _sorted_source_domains(ontology_world, prefer_external=True)
    top_lines = [
        f"- {_source_domain_reply_line(item)}"
        for item in domains[:5]
        if isinstance(item, dict)
    ]
    top_domain_names = [
        str(item.get("domain") or "").strip()
        for item in domains[:3]
        if str(item.get("domain") or "").strip()
    ]
    external_summary = "、".join(top_domain_names) or "外部来源"
    source_domain_total = _ontology_object_total(ontology_world, "source_domain")
    citation_total = _ontology_object_total(ontology_world, "citation_source")
    answer_total = _ontology_object_total(ontology_world, "platform_answer")
    cluster_total = _ontology_object_total(ontology_world, "evidence_cluster")
    official_citations = _ontology_int(official.get("citation_count"))

    return (
        f"结论：正在替代 {official_domain} 承接{brand_label}品牌叙事的，"
        f"主要是 {external_summary}。这不是单条引用的问题，而是当前证据里"
        f"来源域名、引用来源和平台回答形成了稳定外部证据链。\n\n"
        "当前最强的外部来源是：\n"
        f"{chr(10).join(top_lines) if top_lines else '- 暂无可用外部来源摘要。'}\n\n"
        "这个判断由四类证据支撑：\n"
        f"- 来源域名：{source_domain_total} 个，用来判断谁在承接叙事。\n"
        f"- 引用来源：{citation_total} 个，用来判断外部来源被采用的强度。\n"
        f"- 平台回答：{answer_total} 条，用来判断这些来源在哪些回答里生效。\n"
        f"- 证据主题：{cluster_total} 个，用来把大量引用压缩成可审阅的主题。\n\n"
        f"官网 {official_domain} 当前引用数是 {official_citations}。"
        "因此风险不是“没有品牌声量”，而是品牌声量的证据入口被外部来源掌握。"
        "企业用户应该优先看这些外部来源讲了什么，再决定官网证据页要补哪类内容。"
    )

def _build_evidence_cluster_value_reply(
    state: Mapping[str, Any],
    ontology_world: dict[str, Any],
) -> str:
    brand_label = _ontology_brand_label(state, ontology_world)
    clusters = _sorted_evidence_clusters(ontology_world)
    cluster_lines = [
        f"- {_evidence_cluster_reply_line(item)}"
        for item in clusters[:4]
        if isinstance(item, dict)
    ]
    citation_total = _ontology_object_total(ontology_world, "citation_source")
    cluster_total = _ontology_object_total(ontology_world, "evidence_cluster")
    source_domain_total = _ontology_object_total(ontology_world, "source_domain")

    return (
        f"证据主题的价值，是把{brand_label}的大量引用降噪成少量可判断主题。"
        f"当前有 {citation_total} 个引用来源、{source_domain_total} 个来源域名，"
        f"聚合成 {cluster_total} 个证据主题。\n\n"
        "优先看的证据主题是：\n"
        f"{chr(10).join(cluster_lines) if cluster_lines else '- 暂无可用证据主题摘要。'}\n\n"
        "它们比原始引用更适合给企业用户看，因为用户不需要逐条读完全部引用；"
        "用户需要先知道哪类主题正在支撑智能回答、这些主题由哪些域名承接、"
        "官网有没有进入这些主题。然后再从每个主题里抽少量样本做深读。"
    )

def _build_relationship_risk_reply(
    state: Mapping[str, Any],
    ontology_world: dict[str, Any],
) -> str:
    brand_label = _ontology_brand_label(state, ontology_world)
    official = ontology_world.get("official_website_observation") or {}
    if not isinstance(official, dict):
        official = {}
    official_domain = str(official.get("domain") or "官网").strip()
    official_citations = _ontology_int(official.get("citation_count"))
    relationships_text = _format_relationships_for_reply(ontology_world)
    domains = _sorted_source_domains(ontology_world, prefer_external=True)
    external_names = [
        str(item.get("domain") or "").strip()
        for item in domains[:3]
        if str(item.get("domain") or "").strip()
    ]
    external_summary = "、".join(external_names) or "外部来源"

    return (
        f"证据关系暴露的核心风险是：智能回答已经形成了关于{brand_label}的证据链，"
        f"但这条证据链绕过了官网 {official_domain}。"
        f"官网当前引用数是 {official_citations}，外部来源则由 {external_summary} "
        "等域名承接。\n\n"
        "当前关键关系是：\n"
        f"{relationships_text}\n\n"
        "这说明用户看到的不是零散数据，而是一条链路：问题先产生回答，回答引用来源，"
        "来源聚合成域名和证据主题，最后支撑情报判断。只要官网不在这条链路里，"
        "官方叙事就很难成为智能回答的默认证据。"
    )

def _build_supporting_relationships_reply(
    state: Mapping[str, Any],
    ontology_world: dict[str, Any],
) -> str:
    brand_label = _ontology_brand_label(state, ontology_world)
    supporting_text = _format_relationships_for_reply(
        ontology_world,
        supporting_only=True,
    )
    core_text = _format_relationships_for_reply(ontology_world)

    return (
        f"可以查，但{brand_label}的辅助关联不适合默认放在看板主视图里。"
        "它们通常提供背景、运营线索或历史上下文，不能直接替代证据链本身。\n\n"
        "当前查到的辅助关联是：\n"
        f"{supporting_text}\n\n"
        "我会先把主视图收紧在这些核心关系上：\n"
        f"{core_text}\n\n"
        "什么时候值得继续看辅助关联：当你要追问竞品背景、指标来源、监测任务、"
        "用户反馈或历史操作原因时，再展开它们。否则默认先看问题、回答、引用来源、"
        "证据主题和情报判断之间的链路。"
    )

def _build_action_boundary_reply(
    state: Mapping[str, Any],
    ontology_world: dict[str, Any],
) -> str:
    brand_label = _ontology_brand_label(state, ontology_world)
    actions = _available_action_items(state, ontology_world)
    action_lines = [f"- {_action_reply_line(item)}" for item in actions[:5]]
    guardrail_text = (
        "所有会影响长期记录的操作，都必须记录来源、校验输入、保留处理脉络，"
        "并在需要确认时先交给人。"
    )

    return (
        f"不能直接跳过确认去执行{brand_label}的后续操作。"
        f"{guardrail_text}\n\n"
        "当前可见的操作边界是：\n"
        f"{chr(10).join(action_lines) if action_lines else '- 暂无可用建议。'}\n\n"
        "这一步不是替用户偷偷执行，而是解释情报、说明证据、"
        "把建议理由和风险讲清楚。真正需要修改长期记录、创建计划、生成官网优化建议时，"
        "系统只能发起待确认请求；人确认后，再进入受控执行。"
    )

def _build_ontology_intelligence_explanation_reply(
    state: Mapping[str, Any],
    ontology_world: dict[str, Any],
) -> str:
    kind = _ontology_intelligence_question_kind(state)
    if kind == "source_substitution":
        reply = _build_source_substitution_reply(state, ontology_world)
        return _with_intelligence_reply_closure(reply)
    if kind == "evidence_cluster_value":
        reply = _build_evidence_cluster_value_reply(state, ontology_world)
        return _with_intelligence_reply_closure(reply)
    if kind == "supporting_relationships":
        reply = _build_supporting_relationships_reply(state, ontology_world)
        return _with_intelligence_reply_closure(reply)
    if kind == "relationship_risk":
        reply = _build_relationship_risk_reply(state, ontology_world)
        return _with_intelligence_reply_closure(reply)
    if kind == "action_boundary":
        reply = _build_action_boundary_reply(state, ontology_world)
        return _with_intelligence_reply_closure(reply)
    reply = _build_official_website_gap_reply(state, ontology_world)
    return _with_intelligence_reply_closure(reply)

def _with_intelligence_reply_closure(reply: str) -> str:
    """Ensure fast ontology replies keep a stable business-analysis shape."""

    closure_parts: list[str] = []
    if "结论" not in reply:
        closure_parts.append(
            "结论：这条回答只围绕当前品牌情报里的已沉淀证据做解释，"
            "不把推断当成已经执行的结果。"
        )
    if "证据：" not in reply:
        closure_parts.append(
            "证据：以上判断只使用当前品牌情报里的问题、回答、引用、官网观测、"
            "来源域名、证据主题和待处理事项。"
        )
    if "影响：" not in reply and "业务影响：" not in reply:
        closure_parts.append(
            "影响：如果官网缺席或外部来源主导，品牌叙事会更多被第三方来源塑造，"
            "内容团队需要优先补强可被引用的官方材料。"
        )
    if "需要确认：" not in reply:
        closure_parts.append(
            "需要确认：请先确认是否要把这条判断进入持续监测、官网补证或内容优化；"
            "没有确认时系统只解释，不会修改长期记录。"
        )
    if "下一步建议：" not in reply:
        closure_parts.append(
            "下一步建议：先围绕当前证据追问样本、来源或影响；需要执行时再提交确认。"
        )
    if not closure_parts:
        return reply
    return f"{reply}\n\n" + "\n".join(closure_parts)

