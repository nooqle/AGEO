"""Agent tool-result summary builders (P2 knife 8, cautious)."""

from __future__ import annotations

from typing import Any, Mapping

from app.workflow.orchestrator.history_query import (
    _has_authoritative_history_refresh_result,
    _is_latest_run_history_stats_query,
)
from app.workflow.orchestrator.knowledge_fallback import (
    _infer_knowledge_fallback_tool,  # noqa: F401  # may be used by extended paths
)
from app.workflow.orchestrator.knowledge_format import (
    _format_knowledge_comparison,
    _format_knowledge_group,
    _format_knowledge_lookup_match,
)
from app.workflow.orchestrator.run_context import _get_latest_user_message
from app.workflow.orchestrator.text_normalize import (
    _extract_exact_datetime_scope_text,
    _normalize_public_knowledge_text,
)

DIRECTIVE_A1_HAS_BASELINE = (
    "建议先用 3-5 句话向用户汇报品牌分析结果，并带出至少 1 个具体洞察。"
    "如果用户还没有明确下一步，可继续引导其在引用内容置信度评估、用户画像与场景细化、"
    "重新运行品牌全景分析或直接追问之间做选择；只有在确实需要明确选择时，再调用 ask_user。"
)

DIRECTIVE_A1_NO_BASELINE = (
    "当前仅完成了品牌分析，还没有建立品牌全景分析结果。"
    "建议先向用户说明品牌全景分析会用行业通用问题建立各 AI 平台上的整体认知参考，"
    "后续画像和场景分析都会基于它做对比；如果用户尚未明确是否继续，可再调用 ask_user 请求确认。"
)

DIRECTIVE_A2_ASK_PATH = (
    "画像已生成并展示在界面结果区中。"
    "建议先提醒用户勾选希望重点分析的画像；"
    "如果用户还没有明确是否继续或是否跳过，可调用 ask_user 请求确认。"
)

DIRECTIVE_A3_NEXT_FETCH = (
    "建议先用 2-3 句话说明问题已生成，且问题列表已在界面结果区中展示。"
    "通常下一步是让用户在快速采集、完整采集或重新调整问题之间做选择；"
    "如果用户尚未明确采集模式，可调用 ask_user 请求确认。不要逐条复述 UI 中已经展示的问题内容。"
)

DIRECTIVE_A5_BASELINE_NEXT = (
    "建议先用 3-5 句话向用户汇报品牌全景分析结果，并至少包含 1 个具体指标或风险发现。"
    "如果用户还没有明确下一步，可继续引导其选择引用内容置信度评估、用户画像与场景细化、"
    "重新运行品牌全景分析或直接追问；需要明确确认时再调用 ask_user。"
)

DIRECTIVE_A5_PERSONA_NEXT = (
    "建议先用 3-5 句话向用户汇报场景分析报告结果，并至少包含 1 个具体指标或风险发现。"
    "如果用户还没有明确下一步，可继续引导其选择引用内容置信度评估、深入分析当前报告或直接追问；"
    "需要明确确认时再调用 ask_user。"
)

def _build_agent_result_summary(state: Mapping[str, Any], tool_name: str) -> str:
    """Build a concise summary of agent results for the tool_result message."""
    if tool_name == "brand_analysis":
        bp = state.get("brand_profile")
        comps = state.get("competitors", [])
        if bp:
            comp_names = [c.get("name", "?") for c in (comps or [])]
            summary = (
                f"品牌分析完成。品牌：{bp.get('brand_name', '未知')}，"
                f"行业：{bp.get('industry', '未知')}，"
                f"定位：{bp.get('brand_positioning', '未知')}。"
                f"识别出 {len(comps or [])} 个竞品：{', '.join(comp_names[:5])}。"
            )
            has_baseline = bool(state.get("baseline_metrics"))
            summary += (
                DIRECTIVE_A1_HAS_BASELINE if has_baseline else DIRECTIVE_A1_NO_BASELINE
            )
            return summary
        return (
            "品牌分析暂未拿到有效结果。"
            "请先核对品牌名称是否准确，或补充官网/行业线索后让我重试品牌分析。"
        )

    if tool_name == "persona_generation":
        mp = state.get("marketing_personas")
        if mp:
            personas = mp.get("user_personas", [])
            if not personas:
                return (
                    "画像生成暂未拿到有效结果。"
                    "更合适的下一步是先补充品牌信息，或先运行品牌全景分析后再重新生成画像。"
                )
            persona_names = [
                p.get("persona_name", p.get("name", f"画像{i+1}"))
                for i, p in enumerate(personas[:6])
            ]
            names_str = "、".join(persona_names)
            return (
                f"用户画像生成完成，共 {len(personas)} 个画像：{names_str}。"
                f"{DIRECTIVE_A2_ASK_PATH}"
            )
        return (
            "画像生成暂未成功。"
            "请告诉用户可以先补充品牌信息、先运行品牌全景分析，或稍后重新尝试画像生成。"
        )

    if tool_name == "table_intake_skill":
        result = state.get("table_intake_result") or {}
        table_kind = result.get("table_kind", "unknown")
        summary = result.get("summary") or "表格理解完成。"
        if table_kind == "question_list":
            return (
                f"{summary}"
                " 建议先向用户说明这是一份问题列表，适合挂接到 A3；"
                "如果用户尚未确认是否导入，再调用 ask_user 请求确认。"
            )
        if table_kind == "brand_competitor_info":
            return (
                f"{summary}"
                " 建议先说明这份表格更适合作为 A1 的品牌/竞品信息输入；"
                "如果用户尚未确认是否更新上下文，再调用 ask_user。"
            )
        if table_kind == "link_list":
            return (
                f"{summary}"
                " 建议先说明这是一份链接清单，适合作为来源/链接清单继续分析；"
                "如果用户尚未确认是否继续，再调用 ask_user。"
            )
        return (
            f"{summary}"
            " 建议直接告诉用户当前还不能稳定判断这份表格的用途，"
            "并补充可执行方案：重新上传单个 CSV/XLSX、说明希望挂接到哪个步骤、或拆分文件后再试。"
        )

    if tool_name == "question_simulation":
        sq = state.get("simulated_questions")
        if sq:
            qs = sq.get("simulated_questions", [])
            summary = (
                f"问题模拟完成。共生成 {len(qs)} 组模拟问题。{DIRECTIVE_A3_NEXT_FETCH}"
            )
            logger.info(
                "[Orchestrator] A3 tool_result directive (first 300 chars): %s",
                summary[:300],
            )
            return summary
        return (
            "问题模拟暂未生成有效问题。"
            "请直接告知用户当前问题集不足以继续抓取，"
            "并提供两个选项：1) 重新生成问题；2) 换一种方式描述需求或改用上传问题列表。"
            "不要继续调用 answer_fetch，等待用户指示。"
        )

    if tool_name == "answer_fetch":
        fr = state.get("fetch_results")
        a4_observation = state.get("a4_completion_observation") or {}
        requires_user_decision = bool(a4_observation.get("requires_user_decision"))
        if requires_user_decision:
            failed_question_count = int(
                a4_observation.get("failed_question_count") or 0
            )
            failed_platform_count = int(
                a4_observation.get("failed_platform_count") or 0
            )
            option_lines = []
            for option in a4_observation.get("followup_options") or []:
                option_id = str(option.get("id") or "").strip()
                option_label = str(option.get("label") or "").strip()
                option_description = str(option.get("description") or "").strip()
                if not option_id or not option_label:
                    continue
                option_lines.append(
                    f"- {option_label}（id={option_id}）：{option_description}"
                )
            options_text = "\n".join(option_lines)
            return (
                f"AI答案抓取已完成，当前有 {failed_question_count} 个失败问题、"
                f"{failed_platform_count} 个失败平台仍未补齐。"
                "不要直接调用 analysis_report_skill。"
                "请先调用 ask_user，请用户在继续补采剩余失败项和直接基于当前成功样本生成报告之间做选择。"
                f"{chr(10)}可用选项如下：{chr(10)}{options_text}"
            )
        if a4_observation and not bool(
            a4_observation.get("artifact_write_validated", True)
        ):
            return (
                "AI答案抓取已经跑出结果，但官方抓取结果写回失败。"
                "不要继续调用 analysis_report_skill。"
                "请先向用户说明需要重新完成答案抓取结果写回，并提供可执行的重试方案。"
            )
        if fr:
            report_type = (
                "panorama"
                if (state.get("analysis_mode") or "persona") == "baseline"
                else "scenario"
            )
            report_label = (
                "品牌全景分析报告" if report_type == "panorama" else "场景分析报告"
            )
            if bool(a4_observation.get("scoped_merge_active")):
                return (
                    f"AI答案抓取完成。定向补采结果已经并入最新完整样本，共 {len(fr)} 组问题结果。"
                    f"现在可以继续刷新{report_label}。"
                )
            return (
                f"AI答案抓取完成。共抓取 {len(fr)} 组问题结果。"
                f"通常下一步是生成{report_label}；"
                "如果用户当前明确要求补采、换模式、缩小范围或继续确认，优先响应用户当前意图。"
            )
        return (
            "AI答案抓取完成，但未获取到有效数据。"
            "请向用户说明抓取失败，并优先给出这些可执行方案："
            "1) 重新尝试抓取（可换模式，如 fast→full）；"
            "2) 仅抓取指定平台（继续走 answer_fetch，并通过 platforms 指定平台）；"
            "3) 手动提供问题重新抓取。"
            "除非用户明确要求改题，否则不要默认重新调用 question_simulation。"
        )

    if tool_name in {"data_analytics", "analysis_report_skill"}:
        current_mode = state.get("analysis_mode", "persona")
        if current_mode == "baseline":
            metrics = state.get("baseline_metrics") or state.get("metrics")
        else:
            metrics = state.get("metrics")
        if metrics:
            summary_metrics = (
                metrics.get("summary_metrics", {}) if isinstance(metrics, dict) else {}
            )
            mention_rate = (
                float(
                    summary_metrics.get(
                        "brand_mention_rate",
                        (
                            metrics.get("mention_rate", 0)
                            if isinstance(metrics, dict)
                            else 0
                        ),
                    )
                    or 0
                )
                * 100
            )
            official_citation_rate = (
                float(summary_metrics.get("official_citation_rate", 0) or 0) * 100
            )
            high_risk_count = int(
                summary_metrics.get("high_risk_scenario_count", 0) or 0
            )
            mode_label = "品牌全景分析" if current_mode == "baseline" else "场景"
            summary = (
                f"{mode_label}数据分析完成。"
                f"品牌提及率：{mention_rate:.1f}％，"
                f"官网引用率：{official_citation_rate:.1f}％，"
                f"高风险场景：{high_risk_count} 个。"
            )
            if current_mode == "baseline":
                return summary + DIRECTIVE_A5_BASELINE_NEXT
            return summary + DIRECTIVE_A5_PERSONA_NEXT
        return (
            "分析报告暂未生成有效结果。"
            "请结合当前抓取结果说明缺口，并优先给出可执行方案：补抓缺失平台、重试当前模式，或确认是否先基于现有结果继续。"
        )

    if tool_name == "knowledge_lookup":
        latest_history_query = _is_latest_run_history_stats_query(
            _get_latest_user_message(state)
        )
        if latest_history_query and _has_authoritative_history_refresh_result(state):
            return _build_agent_result_summary(state, "knowledge_aggregate")

        result = state.get("knowledge_lookup_result") or {}
        matches = result.get("matches", [])
        if matches:
            top = matches[0]
            evidence_lines = "\n".join(
                _format_knowledge_lookup_match(match) for match in matches[:3]
            )
            query = str(result.get("query") or _get_latest_user_message(state) or "")
            exact_scope = _extract_exact_datetime_scope_text(query)
            platform_label = _normalize_public_knowledge_text(
                top.get("platform") or result.get("platform") or ""
            )
            scope_prefix = ""
            if exact_scope:
                scope_prefix = (
                    f"已按 {exact_scope}"
                    f"{f' 的{platform_label}平台' if platform_label else ''}"
                    f" 命中 {len(matches)} 条记录。"
                    "不要再说无法精确筛选。"
                )
            return (
                f"过往资料检索完成。{scope_prefix}"
                f"{'' if scope_prefix else f'共命中 {len(matches)} 条记录。'}"
                f"最高相关来源类型：{top.get('source_type', 'unknown')}。"
                "\n可直接使用的证据如下：\n"
                f"{evidence_lines}\n"
                "请优先基于这些证据继续回答、分析、导出；"
                "只有当证据仍然不足时，再决定是否调用 brand_analysis / answer_fetch。"
            )
        return (
            "过往资料检索未命中足够记录。"
            "如果用户的问题仍需真实数据，请根据问题类型决定是否调用 brand_analysis 或 answer_fetch；"
            "如果该处理链路较长或模式不明确，再使用 ask_user。"
        )

    if tool_name == "knowledge_aggregate":
        result = state.get("knowledge_aggregate_result") or {}
        groups = result.get("groups", [])
        if groups:
            top = groups[0]
            group_lines = "\n".join(
                _format_knowledge_group(group) for group in groups[:5]
            )
            fetch_status = result.get("fetch_status_summary") or {}
            fetch_prefix = ""
            if int(fetch_status.get("total_count") or 0) > 0:
                fetch_prefix = (
                    f"最近一轮采集共 {int(fetch_status.get('total_count') or 0)} 条，"
                    f"成功 {int(fetch_status.get('success_count') or 0)} 条，"
                    f"失败 {int(fetch_status.get('failure_count') or 0)} 条。"
                )
            fetch_question_hint = ""
            if int(fetch_status.get("failed_question_count") or 0) > 0:
                preview_count = min(len(groups), 5)
                fetch_question_hint = (
                    f"失败问题数以权威统计为准，共 {int(fetch_status.get('failed_question_count') or 0)} 个。"
                    f"如果下面只展示 {preview_count} 个分组，那只是预览，不代表总数。"
                )
            scope_label = str(result.get("analysis_scope_label") or "当前范围")
            filter_label = str(result.get("status_filter_label") or "全部记录")
            return (
                f"{fetch_prefix}"
                f"{fetch_question_hint}"
                f"本次按{scope_label}{filter_label}整理，共统计 {result.get('total_records', 0)} 条记录，"
                f"得到 {len(groups)} 个分组。"
                f"当前最大分组是 {top.get('group_key', 'unknown')}，数量 {top.get('count', 0)}。"
                "\n关键分组如下：\n"
                f"{group_lines}\n"
                "请基于这些分组继续汇总、分析、导出或生成交付结果。"
            )
        return (
            "过往资料整理未得到有效分组。"
            "如果用户仍需要结果，请判断是缩小筛选条件、改用 knowledge_lookup，"
            "还是通过 brand_analysis / answer_fetch 先补齐缺失材料。"
        )

    if tool_name == "knowledge_export":
        result = state.get("knowledge_export_result") or {}
        if result.get("status") == "hit":
            if result.get("source_scope") == "current_import_artifact":
                return (
                    f"当前上传问题表已定位，共整理 {result.get('item_count', 0)} 条记录。"
                    f"交付物标题：{result.get('title', '当前导入问题表')}。"
                    "请向用户说明这次结果只来自当前导入表格，不包含历史资料，并提示现在可以查看或继续导出。"
                )
            return (
                f"过往资料表已生成，共整理 {result.get('item_count', 0)} 条记录。"
                f"交付物标题：{result.get('title', '过往资料表')}。"
                "数据表已经生成，请向用户说明现在可以查看，并可继续导出为 md/pdf，"
                "同时用 1-2 句话概括本次导出的范围。"
            )
        if result.get("source_scope") == "current_import_artifact":
            validation = result.get("validation") or {}
            failure_messages = "；".join(
                str(item.get("message") or "").strip()
                for item in list(validation.get("failures") or [])
                if isinstance(item, dict) and str(item.get("message") or "").strip()
            )
            return (
                "当前上传问题表未生成有效结果。"
                "请不要回退到历史资料表。"
                + (f" 当前阻塞原因：{failure_messages}。" if failure_messages else "")
                + "请判断是重新绑定本次导入交付物，还是提示用户重新上传/重新确认。"
            )
        return (
            "过往资料表未生成有效结果。"
            "请判断是缩小导出范围、先用 knowledge_lookup / knowledge_aggregate 查看材料，"
            "还是先通过 brand_analysis / answer_fetch 补齐缺失材料。"
        )

    if tool_name == "knowledge_compare":
        result = state.get("knowledge_compare_result") or {}
        comparisons = result.get("comparisons", [])
        if comparisons:
            top = comparisons[0]
            comparison_lines = "\n".join(
                _format_knowledge_comparison(item) for item in comparisons[:5]
            )
            return (
                f"过往资料对比完成。"
                f"已比较 {result.get('latest_label', 'latest')} 与 {result.get('previous_label', 'previous')}。"
                f"变化最大项是 {top.get('group_key', 'unknown')}，增量 {top.get('delta', 0)}。"
                "\n关键变化如下：\n"
                f"{comparison_lines}\n"
                "请基于这些变化继续解释趋势、给出分析结论或建议下一步。"
            )
        return (
            "过往资料对比未得到有效变化结果。"
            "如果是因为过往轮次不足，请直接向用户说明；"
            "如果是因为材料不足，请考虑先补齐 brand_analysis 或 answer_fetch。"
        )

    if tool_name == "confidence_analysis_skill":
        return (
            "引用内容置信度评估已完成。"
            "结果已经展示在画布中，您可以继续查看各引用来源的可信度、结构化质量和可核查性差异。"
        )

    if tool_name in {
        "post_analysis_skill",
        "drill_down_analysis",
        "compare_snapshots",
    }:
        last_skill_result = state.get("last_skill_result") or {}
        reply = str(state.get("orchestrator_reply") or "").strip()
        if reply:
            return reply
        if last_skill_result.get("summary"):
            return str(last_skill_result["summary"])
        return "后续分析已完成。"

    if tool_name == "site_confidence_assessment_skill":
        reply = str(
            state.get("site_confidence_report_message")
            or state.get("orchestrator_reply")
            or ""
        ).strip()
        if reply:
            return reply
        last_skill_result = state.get("last_skill_result") or {}
        if last_skill_result.get("summary"):
            return str(last_skill_result["summary"])
        return "官网 AI 友好度评估已完成。"

    current_skill = state.get("current_skill")
    last_skill_result = state.get("last_skill_result") or {}
    if current_skill and tool_name == current_skill:
        summary = str(last_skill_result.get("summary") or "").strip()
        if summary:
            return summary

    if tool_name in {"manage_monitoring_schedule", "create_monitoring_schedule"}:
        reply = state.get("orchestrator_reply", "")
        return f"监测计划处理已完成。{reply[:200]}"

    return f"工具 {tool_name} 执行完成。"

