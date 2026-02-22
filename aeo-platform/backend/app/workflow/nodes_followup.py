"""Follow-up analysis nodes for multi-turn dialogue (Cycle 3, Module 2).

Three follow-up nodes that operate on existing session data without re-running
the full A1-A5 pipeline:

- drill_down_node: Focused analysis on a specific dimension of existing results
- compare_snapshots_node: Compare current analysis with a previous snapshot
- selective_refetch_node: Re-fetch from specific platforms only, merge & re-analyze
"""

import json
import logging
from typing import Any

from langgraph.types import Command

from app.workflow.state import AgentState
from app.workflow.events import send_reply_event
from app.workflow.nodes_streaming import call_llm_streaming
from app.core.llm import get_llm_model

logger = logging.getLogger(__name__)


# =============================================================================
# drill_down_node
# =============================================================================


async def drill_down_node(state: AgentState) -> Command:
    """Generate focused drill-down analysis from existing data.

    Reads: fetch_results, metrics, report, brand_profile, simulated_questions.
    Does NOT invoke any Agent pipeline.
    Uses LLM to generate targeted analysis based on focus_dimension/focus_value.
    Sends result via reply_delta (chat response, not a full report).
    """
    session_id = state["session_id"]
    tool_args = state.get("tool_call_args") or {}
    focus_dimension = tool_args.get("focus_dimension", "platform")
    focus_value = tool_args.get("focus_value", "")

    fetch_results = state.get("fetch_results") or []
    metrics = state.get("metrics") or {}
    brand_profile = state.get("brand_profile") or {}
    simulated_questions = state.get("simulated_questions") or {}

    # Precondition check (Review T5)
    if not fetch_results:
        error_msg = (
            "当前会话中没有分析数据，请先完成一次完整的品牌分析后再进行深入分析。"
        )
        await send_reply_event(
            session_id, error_msg, is_delta=False, is_complete=True
        )
        return Command(
            update={
                "orchestrator_reply": error_msg,
                "execution_status": "completed",
            }
        )

    # Filter data based on focus dimension (Review T4: includes simulated_questions)
    filtered_data = _filter_by_dimension(
        fetch_results, metrics, simulated_questions, focus_dimension, focus_value
    )

    # Generate focused analysis via LLM
    analysis = await _generate_drill_down(
        session_id, brand_profile, filtered_data, focus_dimension, focus_value
    )

    # Send as chat reply (not Canvas artifact)
    await send_reply_event(
        session_id, analysis, is_delta=False, is_complete=True
    )

    return Command(
        update={
            "orchestrator_reply": analysis,
            "execution_status": "completed",
        }
    )


def _filter_by_dimension(
    fetch_results: list,
    metrics: dict,
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
                pr for pr in fr.get("platform_results", [])
                if not focus_lower or pr.get("platform", "").lower() == focus_lower
            ]
            if platform_results:
                filtered["results"].append({
                    "question_text": fr.get("question_text", ""),
                    "platform_results": platform_results,
                })
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
                    q_text = var_data.get("question", "") if isinstance(var_data, dict) else ""
                    if q_text:
                        matching_question_ids.add(q_text)
                core_q = sq.get("core_question", "")
                if core_q:
                    matching_question_ids.add(core_q)
                filtered["question_context"].append({
                    "category": sq.get("category", ""),
                    "subcategory": sq.get("subcategory", ""),
                    "core_question": core_q,
                })

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
                content = answer.get("content", "") if isinstance(answer, dict) else str(answer)
                if focus_lower and focus_lower in content.lower():
                    relevant_results.append(pr)
            if relevant_results:
                filtered["results"].append({
                    "question_text": fr.get("question_text", ""),
                    "platform_results": relevant_results,
                })

    elif focus_dimension == "sentiment":
        # Filter by sentiment (positive/negative/neutral)
        from app.workflow.nodes_a5 import _analyze_sentiment

        for fr in fetch_results:
            relevant_results = []
            for pr in fr.get("platform_results", []):
                if not pr.get("success"):
                    continue
                answer = pr.get("answer", {})
                content = answer.get("content", "") if isinstance(answer, dict) else str(answer)
                sentiment = _analyze_sentiment(content)
                if not focus_lower or sentiment == focus_lower:
                    relevant_results.append({**pr, "_sentiment": sentiment})
            if relevant_results:
                filtered["results"].append({
                    "question_text": fr.get("question_text", ""),
                    "platform_results": relevant_results,
                })

    else:
        # Fallback: include all results
        filtered["results"] = fetch_results

    filtered["total_filtered"] = len(filtered["results"])
    return filtered


async def _generate_drill_down(
    session_id: str,
    brand_profile: dict,
    filtered_data: dict,
    focus_dimension: str,
    focus_value: str,
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
    for r in filtered_data.get("results", [])[:10]:
        q_text = r.get("question_text", "")[:80]
        pr_summary = []
        for pr in r.get("platform_results", [])[:4]:
            answer = pr.get("answer", {})
            content = answer.get("content", "") if isinstance(answer, dict) else str(answer)
            pr_summary.append({
                "platform": pr.get("platform", ""),
                "has_mention": answer.get("has_brand_mention", False) if isinstance(answer, dict) else False,
                "excerpt": content[:200],
                "sentiment": pr.get("_sentiment", ""),
            })
        results_summary.append({"question": q_text, "results": pr_summary})

    system_prompt = f"""你是 Specta AI 的数据分析专家。用户正在深入分析品牌「{brand_name}」在AI搜索中的表现。
请基于过滤后的数据，对「{dim_label}: {focus_value or '全部'}」维度进行针对性分析。

输出要求：
1. 使用 Markdown 格式
2. 包含核心发现（3-5条）
3. 包含具体数据支撑
4. 给出针对性优化建议（2-3条）
5. 总字数 300-500 字
6. 语言简洁、有洞察力"""

    user_content = f"""## 分析维度
- 维度: {dim_label}
- 具体值: {focus_value or '全部'}
- 匹配结果数: {filtered_data.get('total_filtered', 0)}

## 品牌信息
- 品牌: {brand_name}
- 行业: {brand_profile.get('industry', '')}

## 过滤后的数据
{json.dumps(results_summary, ensure_ascii=False, indent=2)[:4000]}

## 问题上下文
{json.dumps(filtered_data.get('question_context', [])[:5], ensure_ascii=False)[:1000]}

请生成针对「{dim_label}: {focus_value or '全部'}」的深入分析报告。"""

    try:
        model = get_llm_model()
        response = await call_llm_streaming(
            session_id=session_id,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            step="drill_down",
            step_name="深入分析",
            progress_start=0.0,
            progress_end=1.0,
            max_tokens=4096,
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
        await send_reply_event(
            session_id, msg, is_delta=False, is_complete=True
        )
        return Command(update={"execution_status": "completed"})

    from app.core.database import AsyncSessionLocal
    from app.services.snapshot_service import SnapshotService

    # Single DB session for listing + loading snapshots (N-1: merged from two sessions)
    async with AsyncSessionLocal() as db:
        service = SnapshotService(db)
        snapshot_list = await service.list_snapshots(entity_id, page=1, page_size=2)

        snapshots = snapshot_list.get("snapshots", [])
        if len(snapshots) < 2:
            msg = "目前只有一次分析记录，至少需要两次分析才能进行对比。请再次运行分析后重试。"
            await send_reply_event(
                session_id, msg, is_delta=False, is_complete=True
            )
            return Command(update={"execution_status": "completed"})

        # Load full snapshot data (Review T6: use get_snapshot for raw_data)
        snapshot_new = await service.get_snapshot(snapshots[0]["id"])
        snapshot_old = await service.get_snapshot(snapshots[1]["id"])

    if not snapshot_new or not snapshot_old:
        msg = "无法加载快照数据，请稍后重试。"
        await send_reply_event(
            session_id, msg, is_delta=False, is_complete=True
        )
        return Command(update={"execution_status": "completed"})

    # Generate comparison via LLM
    comparison = await _generate_comparison(
        session_id,
        snapshot_old.raw_data or {},
        snapshot_new.raw_data or {},
        state.get("brand_profile") or {},
        old_meta=snapshots[1],
        new_meta=snapshots[0],
    )

    await send_reply_event(
        session_id, comparison, is_delta=False, is_complete=True
    )

    return Command(
        update={
            "orchestrator_reply": comparison,
            "execution_status": "completed",
        }
    )


async def _generate_comparison(
    session_id: str,
    old_data: dict,
    new_data: dict,
    brand_profile: dict,
    old_meta: dict | None = None,
    new_meta: dict | None = None,
) -> str:
    """Use LLM to generate a snapshot comparison analysis."""
    brand_name = brand_profile.get("brand_name", "品牌")

    old_metrics = old_data.get("metrics", {})
    new_metrics = new_data.get("metrics", {})

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

    old_date = old_meta.get("created_at", "N/A")[:10] if old_meta else "N/A"
    new_date = new_meta.get("created_at", "N/A")[:10] if new_meta else "N/A"

    user_content = f"""## 对比概要
- 品牌: {brand_name}
- 旧快照日期: {old_date}
- 新快照日期: {new_date}

## 指标变化
- BWVS指数: {_safe_delta('bwvs_index')}
- 提及率: {_safe_delta('mention_rate')}
- 总问题数: {old_metrics.get('total_questions', 0)} → {new_metrics.get('total_questions', 0)}
- 总提及数: {old_metrics.get('total_mentions', 0)} → {new_metrics.get('total_mentions', 0)}

## 旧快照 BWVS 分解
{json.dumps(old_metrics.get('bwvs_breakdown', {}), ensure_ascii=False, indent=2)[:800]}

## 新快照 BWVS 分解
{json.dumps(new_metrics.get('bwvs_breakdown', {}), ensure_ascii=False, indent=2)[:800]}

## 旧快照平台分布
{json.dumps(old_metrics.get('platform_breakdown', {}), ensure_ascii=False, indent=2)[:500]}

## 新快照平台分布
{json.dumps(new_metrics.get('platform_breakdown', {}), ensure_ascii=False, indent=2)[:500]}

请生成两次分析的对比报告。"""

    try:
        model = get_llm_model()
        response = await call_llm_streaming(
            session_id=session_id,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            step="compare",
            step_name="快照对比",
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
            f"- BWVS指数: {_safe_delta('bwvs_index')}\n"
            f"- 提及率: {_safe_delta('mention_rate')}\n\n"
            f"*详细对比生成失败: {e}*"
        )


# =============================================================================
# selective_refetch_node
# =============================================================================


async def selective_refetch_node(state: AgentState) -> Command:
    """Re-fetch from selected platforms and regenerate report.

    V1 SIMPLIFIED APPROACH (Review C5/T3):
    Instead of a complex merge node, we use a platform filter pattern:
    1. Read the LATEST Snapshot.raw_data for the entity to get baseline data
       (existing fetch_results from unselected platforms) -- Review C3
    2. Set state["platform_filter"] = requested platforms
    3. Route to A4 which reads platform_filter and only fetches those platforms
    4. After A4, merge: replace selected-platform results, keep unselected from baseline
    5. Route to A5 to regenerate report from merged data
    6. Create a new Snapshot with merged results (Review C5)

    Precondition: simulated_questions must exist in state (from prior full analysis).
    """
    session_id = state["session_id"]
    tool_args = state.get("tool_call_args") or {}
    platforms = tool_args.get("platforms", [])

    # Precondition check (Review T5)
    simulated_questions = state.get("simulated_questions")
    if not simulated_questions:
        error_msg = (
            "当前会话中没有分析数据，请先完成一次完整的品牌分析后再进行选择性重新抓取。"
        )
        await send_reply_event(
            session_id, error_msg, is_delta=False, is_complete=True
        )
        return Command(
            update={
                "orchestrator_reply": error_msg,
                "execution_status": "completed",
            }
        )

    # V1: Use current state fetch_results as baseline.
    # Snapshot raw_data only contains summaries, not full platform results,
    # so DB lookup is unnecessary here. If entity-level baseline is needed
    # in the future, implement proper raw_data storage first.
    entity_id = state.get("entity_id")
    current_fetch = state.get("fetch_results") or []
    platforms_lower = [p.lower() for p in platforms]

    # Keep results from unselected platforms
    unselected_results = []
    for fr in current_fetch:
        kept_pr = [
            pr for pr in fr.get("platform_results", [])
            if pr.get("platform", "").lower() not in platforms_lower
        ]
        if kept_pr:
            unselected_results.append({
                "question_id": fr.get("question_id", ""),
                "question_text": fr.get("question_text", ""),
                "platform_results": kept_pr,
            })

    await send_reply_event(
        session_id,
        f"正在重新抓取以下平台的数据: {', '.join(platforms)}...",
        is_delta=False,
        is_complete=True,
    )

    return Command(
        update={
            "platform_filter": platforms_lower,
            "preserved_fetch_results": unselected_results,
            "execution_status": "running",
        },
        goto="a4_fetch",
    )
