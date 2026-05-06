"""Follow-up analysis nodes for multi-turn dialogue (Cycle 3, Module 2).

Two follow-up nodes operate on existing session data without re-running
the full A1-A5 pipeline:

- drill_down_node: Focused analysis on a specific dimension of existing results
- compare_snapshots_node: Compare current analysis with a previous snapshot
"""

import json
import logging
from typing import Any

from langgraph.types import Command

from app.services.tool_capability_matrix import validate_tool_capability_access
from app.workflow.harness_validation import build_harness_decision
from app.workflow.a5.metrics import analyze_sentiment
from app.workflow.state import AgentState
from app.workflow.skill_fact_snapshot import build_skill_fact_snapshot
from app.workflow.nodes_streaming import call_llm_streaming
from app.workflow.skill_state import (
    apply_skill_prompt_context,
    build_harness_decision_update,
    build_skill_result_update,
)
from app.core.llm.task_routing import get_long_text_llm_model

logger = logging.getLogger(__name__)


_SENTIMENT_ALIASES = {
    "negative": {"negative", "负向", "负面", "消极"},
    "positive": {"positive", "正向", "正面", "积极"},
    "neutral": {"neutral", "中性"},
}


def _resolve_metric_payload(payload: dict[str, Any]) -> dict[str, Any]:
    metric_bundle = payload.get("metric_bundle")
    if isinstance(metric_bundle, dict):
        merged = dict(metric_bundle)
        if "platform_breakdown" not in merged and isinstance(payload.get("metrics"), dict):
            merged["platform_breakdown"] = payload["metrics"].get("platform_breakdown", {})
        if "summary_metrics" not in merged:
            merged["summary_metrics"] = payload.get("summary_metrics") or merged
        if "mention_sentiment_analysis" not in merged and payload.get("mention_sentiment_analysis"):
            merged["mention_sentiment_analysis"] = payload.get("mention_sentiment_analysis")
        return merged
    metrics = payload.get("metrics")
    return metrics if isinstance(metrics, dict) else payload


def _normalize_sentiment_focus(value: str) -> str:
    text = str(value or "").strip().lower()
    for canonical, aliases in _SENTIMENT_ALIASES.items():
        if text in aliases:
            return canonical
    return text


# =============================================================================
# drill_down_node
# =============================================================================


async def drill_down_node(state: AgentState) -> Command:
    """Generate focused drill-down analysis from existing data.

    Reads: fetch_results, metrics, report, brand_profile, simulated_questions.
    Does NOT invoke any Agent pipeline.
    Uses LLM to generate targeted analysis based on focus_dimension/focus_value.
    Returns the generated analysis to the orchestrator as an observation.
    """
    session_id = state["session_id"]
    tool_args = state.get("tool_call_args") or {}
    focus_dimension = tool_args.get("focus_dimension", "platform")
    focus_value = tool_args.get("focus_value", "")

    facts = build_skill_fact_snapshot(state)
    fetch_results = facts.fetch_results
    metrics = _resolve_metric_payload(facts.metrics)
    report = facts.report
    brand_profile = facts.brand_profile
    simulated_questions = state.get("simulated_questions") or {}

    # Precondition check (Review T5)
    if not fetch_results:
        error_msg = (
            "当前会话中没有分析数据，请先完成一次完整的品牌分析后再进行深入分析。"
        )
        return Command(
            update={
                "orchestrator_reply": error_msg,
                "execution_status": "completed",
                **build_skill_result_update(
                    state,
                    skill_key=state.get("current_skill"),
                    tool_name="post_analysis_skill",
                    status="completed",
                    summary=error_msg,
                    executor_ref="post_analysis_executor",
                    metadata={
                        "analysis_mode": "drill_down",
                        "blocked_by": "analysis_context_missing",
                    },
                ),
            }
        )

    # Filter data based on focus dimension (Review T4: includes simulated_questions)
    filtered_data = _filter_by_dimension(
        fetch_results,
        metrics,
        report,
        simulated_questions,
        focus_dimension,
        focus_value,
    )

    # Generate focused analysis via LLM
    analysis = await _generate_drill_down(
        state,
        session_id,
        brand_profile,
        filtered_data,
        focus_dimension,
        focus_value,
        skill_key=state.get("current_skill"),
    )

    return Command(
        update={
            "orchestrator_reply": analysis,
            "execution_status": "completed",
            **build_skill_result_update(
                state,
                skill_key=state.get("current_skill"),
                tool_name="post_analysis_skill",
                status="completed",
                summary=f"后续分析已完成，本次执行为 drill_down（{focus_dimension}:{focus_value or '全部'}）。",
                executor_ref="post_analysis_executor",
                metadata={
                    "analysis_mode": "drill_down",
                    "focus_dimension": focus_dimension,
                    "focus_value": focus_value,
                },
            ),
        }
    )


def _filter_by_dimension(
    fetch_results: list,
    metrics: dict,
    report: dict,
    simulated_questions: dict | list,
    focus_dimension: str,
    focus_value: str,
) -> dict[str, Any]:
    """Filter fetch_results and related data by the specified dimension."""
    filtered: dict[str, Any] = {
        "dimension": focus_dimension,
        "value": focus_value,
        "results": [],
        "question_context": [],
    }

    # Normalize simulated_questions: it can be a dict with "simulated_questions" key or a list
    sq_list = []
    if isinstance(simulated_questions, dict):
        sq_list = simulated_questions.get("simulated_questions", [])
    elif isinstance(simulated_questions, list):
        sq_list = simulated_questions

    focus_lower = focus_value.lower() if focus_value else ""

    if focus_dimension == "platform":
        # Filter platform_results to only the specified platform
        for fr in fetch_results:
            platform_results = [
                pr
                for pr in fr.get("platform_results", [])
                if not focus_lower or pr.get("platform", "").lower() == focus_lower
            ]
            if platform_results:
                filtered["results"].append(
                    {
                        "question_text": fr.get("question_text", ""),
                        "platform_results": platform_results,
                    }
                )
        # Platform-level metrics
        pb = metrics.get("platform_breakdown", {})
        if focus_lower and focus_lower in pb:
            filtered["platform_metrics"] = pb[focus_lower]

    elif focus_dimension == "question_category":
        # Filter by question category from simulated_questions (Review T4)
        matching_question_ids = set()
        for sq in sq_list:
            cat = sq.get("category", "").lower()
            subcat = sq.get("subcategory", "").lower()
            if focus_lower in cat or focus_lower in subcat:
                # Match question variants
                variants = sq.get("question_variants", {})
                for var_key, var_data in variants.items():
                    q_text = (
                        var_data.get("question", "")
                        if isinstance(var_data, dict)
                        else ""
                    )
                    if q_text:
                        matching_question_ids.add(q_text)
                core_q = sq.get("core_question", "")
                if core_q:
                    matching_question_ids.add(core_q)
                filtered["question_context"].append(
                    {
                        "category": sq.get("category", ""),
                        "subcategory": sq.get("subcategory", ""),
                        "core_question": core_q,
                    }
                )

        for fr in fetch_results:
            q_text = fr.get("question_text", "")
            # Match if question text is in our matching set or contains the focus value
            if q_text in matching_question_ids or focus_lower in q_text.lower():
                filtered["results"].append(fr)

    elif focus_dimension == "competitor":
        # Filter results mentioning the specified competitor
        for fr in fetch_results:
            relevant_results = []
            for pr in fr.get("platform_results", []):
                if not pr.get("success"):
                    continue
                answer = pr.get("answer", {})
                content = (
                    answer.get("content", "")
                    if isinstance(answer, dict)
                    else str(answer)
                )
                if focus_lower and focus_lower in content.lower():
                    relevant_results.append(pr)
            if relevant_results:
                filtered["results"].append(
                    {
                        "question_text": fr.get("question_text", ""),
                        "platform_results": relevant_results,
                    }
                )

    elif focus_dimension == "sentiment":
        normalized_focus = _normalize_sentiment_focus(focus_value)
        mention_analysis = {}
        if isinstance(report, dict):
            mention_analysis = (
                report.get("mention_sentiment_analysis")
                or report.get("skill_outputs", {})
                .get("sentiment_risk_analyzer", {})
                .get("summary", {})
            ) or {}
        if not mention_analysis and isinstance(metrics, dict):
            mention_analysis = metrics.get("mention_sentiment_analysis") or {}

        brand_analysis = (
            mention_analysis.get("brand", {})
            if isinstance(mention_analysis, dict)
            else {}
        )
        brand_items = (
            brand_analysis.get("items", []) if isinstance(brand_analysis, dict) else []
        )
        if brand_items:
            filtered["sentiment_summary"] = (
                brand_analysis.get("summary", {})
                if isinstance(brand_analysis, dict)
                else {}
            )
            sentiment_items = [
                item
                for item in brand_items
                if not normalized_focus
                or str(item.get("sentiment", "")).lower() == normalized_focus
            ]
            filtered["sentiment_items"] = sentiment_items
            for item in sentiment_items:
                filtered["results"].append(
                    {
                        "question_text": item.get("scenario_label", ""),
                        "platform_results": [
                            {
                                "platform": item.get("platform", ""),
                                "success": True,
                                "answer": {
                                    "content": item.get("evidence", ""),
                                    "has_brand_mention": True,
                                },
                                "_sentiment": item.get("sentiment", ""),
                                "_citation_domains": item.get("citation_domains", []),
                                "_citation_titles": item.get("citation_titles", []),
                                "_citation_urls": item.get("citation_urls", []),
                            }
                        ],
                    }
                )
            filtered["total_filtered"] = len(filtered["results"])
            return filtered

        for fr in fetch_results:
            relevant_results = []
            for pr in fr.get("platform_results", []):
                if not pr.get("success"):
                    continue
                answer = pr.get("answer", {})
                content = (
                    answer.get("content", "")
                    if isinstance(answer, dict)
                    else str(answer)
                )
                sentiment = analyze_sentiment(content)
                if not normalized_focus or sentiment == normalized_focus:
                    relevant_results.append({**pr, "_sentiment": sentiment})
            if relevant_results:
                filtered["results"].append(
                    {
                        "question_text": fr.get("question_text", ""),
                        "platform_results": relevant_results,
                    }
                )

    else:
        # Fallback: include all results
        filtered["results"] = fetch_results

    filtered["total_filtered"] = len(filtered["results"])
    return filtered


async def _generate_drill_down(
    state: AgentState,
    session_id: str,
    brand_profile: dict,
    filtered_data: dict,
    focus_dimension: str,
    focus_value: str,
    *,
    skill_key: str | None = None,
) -> str:
    """Use LLM to generate a focused drill-down analysis."""
    dimension_labels = {
        "platform": "平台",
        "question_category": "问题类别",
        "competitor": "竞品",
        "sentiment": "情感倾向",
    }
    dim_label = dimension_labels.get(focus_dimension, focus_dimension)
    brand_name = brand_profile.get("brand_name", "品牌")

    # Build compact data summary (avoid sending full content to LLM)
    results_summary = []
    if focus_dimension == "sentiment" and filtered_data.get("sentiment_items"):
        for item in filtered_data.get("sentiment_items", [])[:12]:
            results_summary.append(
                {
                    "question": str(item.get("scenario_label", ""))[:80],
                    "platform": item.get("platform", ""),
                    "sentiment": item.get("sentiment", ""),
                    "evidence": str(item.get("evidence", ""))[:220],
                    "citation_domains": item.get("citation_domains", [])[:4],
                }
            )
    else:
        for r in filtered_data.get("results", [])[:10]:
            q_text = r.get("question_text", "")[:80]
            pr_summary = []
            for pr in r.get("platform_results", [])[:4]:
                answer = pr.get("answer", {})
                content = (
                    answer.get("content", "")
                    if isinstance(answer, dict)
                    else str(answer)
                )
                pr_summary.append(
                    {
                        "platform": pr.get("platform", ""),
                        "has_mention": (
                            answer.get("has_brand_mention", False)
                            if isinstance(answer, dict)
                            else False
                        ),
                        "excerpt": content[:200],
                        "sentiment": pr.get("_sentiment", ""),
                        "citation_domains": pr.get("_citation_domains", [])[:4],
                    }
                )
            results_summary.append({"question": q_text, "results": pr_summary})

    system_prompt = f"""你是 Specta AI 的数据分析专家。用户正在深入分析品牌「{brand_name}」在 AI 平台中的表现。
请基于过滤后的数据，对「{dim_label}: {focus_value or '全部'}」维度进行针对性分析。

输出要求：
1. 使用 Markdown 格式
2. 包含核心发现（3-5条）
3. 包含具体数据支撑
4. 给出针对性优化建议（2-3条）
5. 总字数 300-500 字
6. 语言简洁、有洞察力"""
    if focus_dimension == "sentiment":
        system_prompt += (
            "\n7. 如果用户问的是负向/正向提及，优先解释具体是哪几个问题、哪个平台、证据原句是什么。"
            "\n8. 不要泛泛而谈，要直接指出负向提及的具体内容。"
            "\n9. 负向定义：损害品牌声誉、产品硬伤、合规失败或客观负面事件；正向定义：技术优势、权威认证、市场成功或积极社会影响；中性定义：只做机制说明、参数罗列或背景介绍。"
            "\n10. 0% 只能写成“本轮样本未观察到”，不能扩展成长期没有；没有有效分母时写“暂无足够数据支撑”。"
        )
    system_prompt = apply_skill_prompt_context(state, system_prompt)

    user_content = f"""## 分析维度
- 维度: {dim_label}
- 具体值: {focus_value or '全部'}
- 匹配结果数: {filtered_data.get('total_filtered', 0)}

## 品牌信息
- 品牌: {brand_name}
- 行业: {brand_profile.get('industry', '')}

## 过滤后的数据
{json.dumps(results_summary, ensure_ascii=False, indent=2)[:4000]}

## 情感摘要
{json.dumps(filtered_data.get('sentiment_summary', {}), ensure_ascii=False)}

## 问题上下文
{json.dumps(filtered_data.get('question_context', [])[:5], ensure_ascii=False)[:1000]}

请生成针对「{dim_label}: {focus_value or '全部'}」的深入分析报告。"""

    try:
        model = get_long_text_llm_model()
        response = await call_llm_streaming(
            session_id=session_id,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            step="drill_down",
            step_name="深入分析",
            skill_key=skill_key,
            progress_start=0.0,
            progress_end=1.0,
            max_tokens=4096,
            temperature=0.1 if focus_dimension == "sentiment" else None,
        )
        return response.content if hasattr(response, "content") else str(response)
    except Exception as e:
        logger.error("[drill_down] LLM generation failed: %s", e)
        return f"深入分析生成失败: {e}。共找到 {filtered_data.get('total_filtered', 0)} 条相关数据。"


# =============================================================================
# compare_snapshots_node
# =============================================================================


async def compare_snapshots_node(state: AgentState) -> Command:
    """Compare current analysis with previous snapshot.

    Design note (Review C7): This node directly accesses the DB layer
    (AsyncSessionLocal + SnapshotService) rather than going through the
    Orchestrator's tool result pattern. This is an intentional design
    difference -- follow-up nodes are "read-only queries" that need DB
    access for historical data, unlike pipeline nodes (A1-A5) that
    operate on in-memory state. This pattern is acceptable but should
    not be extended to pipeline nodes.

    Uses get_snapshot() to retrieve full snapshot data (Review T6),
    not get_trend() which only returns summary/metadata.
    """
    session_id = state["session_id"]
    entity_id = state.get("entity_id")

    if not entity_id:
        msg = "当前会话中没有关联的品牌实体，请先完成一次完整的品牌分析。"
        return Command(
            update={
                "orchestrator_reply": msg,
                "execution_status": "completed",
                **build_skill_result_update(
                    state,
                    skill_key=state.get("current_skill"),
                    tool_name="post_analysis_skill",
                    status="completed",
                    summary=msg,
                    executor_ref="post_analysis_executor",
                    metadata={
                        "analysis_mode": "compare_snapshots",
                        "blocked_by": "analysis_context_missing",
                    },
                ),
            }
        )

    from app.core.database import AsyncSessionLocal
    from app.services.snapshot_service import SnapshotService

    # Single DB session for listing + loading snapshots (N-1: merged from two sessions)
    async with AsyncSessionLocal() as db:
        service = SnapshotService(db)
        snapshot_list = await service.list_snapshots(entity_id, page=1, page_size=2)

        snapshots = snapshot_list.get("snapshots", [])
        if len(snapshots) < 2:
            msg = "目前只有一次分析记录，至少需要两次分析才能进行对比。请再次运行分析后重试。"
            return Command(
                update={
                    "orchestrator_reply": msg,
                    "execution_status": "completed",
                    **build_skill_result_update(
                        state,
                        skill_key=state.get("current_skill"),
                        tool_name="post_analysis_skill",
                        status="completed",
                        summary=msg,
                        executor_ref="post_analysis_executor",
                        metadata={
                            "analysis_mode": "compare_snapshots",
                            "blocked_by": "snapshot_unavailable",
                        },
                    ),
                }
            )

        # Load full snapshot data (Review T6: use get_snapshot for raw_data)
        snapshot_new = await service.get_snapshot(snapshots[0]["id"])
        snapshot_old = await service.get_snapshot(snapshots[1]["id"])

    if not snapshot_new or not snapshot_old:
        msg = "无法加载快照数据，请稍后重试。"
        return Command(
            update={
                "orchestrator_reply": msg,
                "execution_status": "completed",
                **build_skill_result_update(
                    state,
                    skill_key=state.get("current_skill"),
                    tool_name="post_analysis_skill",
                    status="completed",
                    summary=msg,
                    executor_ref="post_analysis_executor",
                    metadata={
                        "analysis_mode": "compare_snapshots",
                        "blocked_by": "snapshot_unavailable",
                    },
                ),
            }
        )

    # Generate comparison via LLM
    comparison = await _generate_comparison(
        state,
        session_id,
        snapshot_old.raw_data or {},
        snapshot_new.raw_data or {},
        state.get("brand_profile") or {},
        old_meta=snapshots[1],
        new_meta=snapshots[0],
        skill_key=state.get("current_skill"),
    )

    return Command(
        update={
            "orchestrator_reply": comparison,
            "execution_status": "completed",
            **build_skill_result_update(
                state,
                skill_key=state.get("current_skill"),
                tool_name="post_analysis_skill",
                status="completed",
                summary="后续分析已完成，本次执行为快照对比。",
                executor_ref="post_analysis_executor",
                metadata={"analysis_mode": "compare_snapshots"},
            ),
        }
    )


async def _generate_comparison(
    state: AgentState,
    session_id: str,
    old_data: dict,
    new_data: dict,
    brand_profile: dict,
    old_meta: dict | None = None,
    new_meta: dict | None = None,
    *,
    skill_key: str | None = None,
) -> str:
    """Use LLM to generate a snapshot comparison analysis."""
    brand_name = brand_profile.get("brand_name", "品牌")

    old_metrics = _resolve_metric_payload(old_data)
    new_metrics = _resolve_metric_payload(new_data)

    def _safe_delta(key: str) -> str:
        old_val = old_metrics.get(key, 0) or 0
        new_val = new_metrics.get(key, 0) or 0
        delta = new_val - old_val
        direction = "↑" if delta > 0 else "↓" if delta < 0 else "→"
        return f"{old_val:.2f} → {new_val:.2f} ({direction}{abs(delta):.2f})"

    system_prompt = f"""你是 Specta AI 的数据分析专家。用户要求对比品牌「{brand_name}」的两次分析结果。

输出要求：
1. 使用 Markdown 格式
2. 先给出核心结论（1-2句话）
3. 逐项对比关键指标变化及原因
4. 平台表现变化
5. 给出趋势判断和建议
6. 总字数 300-500 字"""
    system_prompt = apply_skill_prompt_context(state, system_prompt)

    old_date = old_meta.get("created_at", "N/A")[:10] if old_meta else "N/A"
    new_date = new_meta.get("created_at", "N/A")[:10] if new_meta else "N/A"

    user_content = f"""## 对比概要
- 品牌: {brand_name}
- 旧快照日期: {old_date}
- 新快照日期: {new_date}

## 指标变化
- 品牌提及率: {_safe_delta('mention_rate')}
- 官网引用率: {_safe_delta('citation_score')}
- 总问题数: {old_metrics.get('total_questions', 0)} → {new_metrics.get('total_questions', 0)}
- 总提及数: {old_metrics.get('total_mentions', 0)} → {new_metrics.get('total_mentions', 0)}

## 旧快照摘要指标
{json.dumps(old_metrics.get('summary_metrics', {}), ensure_ascii=False, indent=2)[:800]}

## 新快照摘要指标
{json.dumps(new_metrics.get('summary_metrics', {}), ensure_ascii=False, indent=2)[:800]}

## 旧快照平台分布
{json.dumps(old_metrics.get('platform_breakdown', {}), ensure_ascii=False, indent=2)[:500]}

## 新快照平台分布
{json.dumps(new_metrics.get('platform_breakdown', {}), ensure_ascii=False, indent=2)[:500]}

请生成两次分析的对比报告。"""

    try:
        model = get_long_text_llm_model()
        response = await call_llm_streaming(
            session_id=session_id,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            step="compare",
            step_name="快照对比",
            skill_key=skill_key,
            progress_start=0.0,
            progress_end=1.0,
            max_tokens=4096,
        )
        return response.content if hasattr(response, "content") else str(response)
    except Exception as e:
        logger.error("[compare_snapshots] LLM generation failed: %s", e)
        # Fallback: show raw delta
        return (
            f"## {brand_name} 分析对比\n\n"
            f"- 品牌提及率: {_safe_delta('mention_rate')}\n"
            f"- 官网引用率: {_safe_delta('citation_score')}\n\n"
            f"*详细对比生成失败: {e}*"
        )

async def post_analysis_executor_node(state: AgentState) -> Command:
    """Route coarse-grained post-analysis skill to existing follow-up nodes."""

    tool_args = state.get("tool_call_args") or {}
    current_capability = state.get("current_tool_capability") or {}
    capability_tool_name = str(current_capability.get("tool_name") or "").strip()
    _, capability_error = validate_tool_capability_access(
        caller="post_analysis_executor",
        tool_name=capability_tool_name,
    )
    if capability_error:
        logger.warning("[post_analysis_skill] Capability access blocked: %s", capability_error)
        return Command(
            update={
                "execution_status": "error",
                "current_step": state.get("current_step") or "post_analysis_executor",
                "orchestrator_reply": "后续分析能力路由被运行时策略阻止，请稍后重试。",
                "error_info": {
                    "step": "post_analysis_executor",
                    "error": capability_error,
                },
                **build_harness_decision_update(
                    state,
                    build_harness_decision(
                        decision_type="fail_step",
                        reason=capability_error,
                        recoverable=False,
                        metadata={
                            "step": "post_analysis_executor",
                            "blocker_code": "capability_policy_blocked",
                            "tool_name": capability_tool_name,
                        },
                    )
                ),
            }
        )
    requested_mode = str(tool_args.get("analysis_mode") or "").strip().lower()
    capability_mode_map = {
        "drill_down_analysis": "drill_down",
        "compare_snapshots": "compare_snapshots",
    }
    if not requested_mode and capability_tool_name in capability_mode_map:
        requested_mode = capability_mode_map[capability_tool_name]
    if (
        tool_args.get("platforms")
        or tool_args.get("fetch_mode")
        or tool_args.get("custom_questions")
    ):
        guidance = (
            "当前请求更像重新抓取新数据。后续分析只读取已有结果，"
            "建议由编排器结合您的当前意图，判断是否改走答案抓取。"
        )
        redirected_fetch_args = {
            key: value
            for key, value in tool_args.items()
            if key in {"platforms", "fetch_mode", "custom_questions"}
            and value not in (None, "", [])
        }
        return Command(
            update={
                "orchestrator_reply": guidance,
                "execution_status": "completed",
                **build_skill_result_update(
                    state,
                    skill_key=state.get("current_skill"),
                    tool_name="post_analysis_skill",
                    status="completed",
                    summary="后续分析判断当前诉求需要新抓取数据，建议改走答案抓取。",
                    executor_ref="post_analysis_executor",
                    metadata={
                        "analysis_mode": "needs_fresh_fetch",
                        "fresh_data_needed": True,
                        "suggested_tool": "answer_fetch",
                        "suggested_tool_args": redirected_fetch_args,
                    },
                ),
            }
        )
    if requested_mode not in {"drill_down", "compare_snapshots"}:
        if tool_args.get("focus_dimension") or tool_args.get("focus_value"):
            requested_mode = "drill_down"
        else:
            requested_mode = "compare_snapshots"

    logger.info(
        "[post_analysis_skill] Routed to %s with capability=%s args=%s",
        requested_mode,
        capability_tool_name or "none",
        tool_args,
    )

    if requested_mode == "drill_down":
        return await drill_down_node(state)
    return await compare_snapshots_node(state)
