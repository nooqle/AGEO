"""A4 Node: Answer Fetching from AI Platforms.

This module contains the A4 node implementation for fetching answers
from various AI platforms (Doubao, Hunyuan, Kimi, DeepSeek, etc.)

Optimizations:
- API-first strategy: Doubao/Hunyuan (API) execute first, Kimi/DeepSeek (Browser) second
- API platforms retry up to 2 times on failure (exponential backoff)
- Browser platforms have a 90s per-question timeout (from PlatformConstants), no retries
- Browser failures do not block the overall flow
- Minimum 2 platforms with data required to proceed (adjusted for selective_refetch)
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

from langgraph.types import Command

from app.workflow.state import AgentState
from app.workflow.events import (
    send_progress_event,
    send_reply_event,
    send_error_event,
    send_stage_result,
    send_browser_state_event,
)

logger = logging.getLogger(__name__)

# Platform configurations
PLATFORMS = {
    "doubao": {"name": "豆包", "method": "api"},
    "hunyuan": {"name": "混元", "method": "api"},
    "kimi": {"name": "Kimi", "method": "browser"},
    "deepseek": {"name": "DeepSeek", "method": "browser"},
}

# API platforms: full retry support
MAX_RETRIES = 2
RETRY_BACKOFF_BASE = 2.0  # seconds

# Browser platforms: per-platform timeout from constants, 1 retry
BROWSER_MAX_RETRIES = 1

from app.core.constants import PlatformConstants


def _get_browser_timeout(platform: str) -> float:
    """Get per-platform browser timeout from constants."""
    return float(PlatformConstants.PLATFORM_TIMEOUTS.get(platform, 200))

# Minimum number of platforms with successful data to proceed
MIN_PLATFORMS_REQUIRED = 2

# Concurrency limiter for API calls
API_CONCURRENCY_LIMIT = 5
_api_semaphore = asyncio.Semaphore(API_CONCURRENCY_LIMIT)


async def _throttled_retry_fetch(
    fetch_fn: Callable[..., Coroutine[Any, Any, dict[str, Any]]],
    *args: Any,
    platform: str,
    method: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Semaphore-wrapped version of _retry_fetch for concurrency control."""
    async with _api_semaphore:
        return await _retry_fetch(fetch_fn, *args, platform=platform, method=method, **kwargs)


async def _retry_fetch(
    fetch_fn: Callable[..., Coroutine[Any, Any, dict[str, Any]]],
    *args: Any,
    platform: str,
    method: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Retry a fetch function up to MAX_RETRIES times with exponential backoff.

    Returns the first successful result, or the last failure dict.
    """
    last_result: dict[str, Any] = {
        "platform": platform,
        "fetch_method": method,
        "success": False,
        "error": "no attempt made",
    }

    for attempt in range(MAX_RETRIES + 1):
        try:
            result = await fetch_fn(*args, **kwargs)
            if result.get("success"):
                if attempt > 0:
                    logger.info("[A4] %s succeeded on retry %d", platform, attempt)
                return result
            last_result = result
        except Exception as e:
            last_result = {
                "platform": platform,
                "fetch_method": method,
                "success": False,
                "error": str(e),
            }

        if attempt < MAX_RETRIES:
            wait = RETRY_BACKOFF_BASE ** attempt  # 1s, 2s
            logger.info(
                "[A4] %s attempt %d failed (%s), retrying in %.1fs",
                platform, attempt + 1, last_result.get("error", "unknown"), wait,
            )
            await asyncio.sleep(wait)

    logger.warning("[A4] %s failed after %d attempts: %s", platform, MAX_RETRIES + 1, last_result.get("error"))
    return last_result


async def _browser_fetch_with_timeout(
    fetch_fn: Callable[..., Coroutine[Any, Any, dict[str, Any]]],
    *args: Any,
    timeout: float = 200.0,
    **kwargs: Any,
) -> dict[str, Any]:
    """Run a browser fetch with a strict timeout and no retries.

    Browser platforms (Kimi/DeepSeek) are optional — failures are non-blocking.
    """
    # Extract platform info from args for error reporting
    # _fetch_from_browser signature: handler, question, brand_profile, platform, platform_name, browser_state
    platform = args[3] if len(args) > 3 else "unknown"
    platform_name = args[4] if len(args) > 4 else platform

    try:
        result = await asyncio.wait_for(
            fetch_fn(*args, **kwargs),
            timeout=timeout,
        )
        return result
    except asyncio.TimeoutError:
        logger.warning("[A4] Browser %s timed out after %.0fs", platform, timeout)
        return {
            "platform": platform,
            "platform_name": platform_name,
            "fetch_method": "browser",
            "success": False,
            "error": f"超时（{timeout:.0f}s）",
            "duration": timeout,
        }
    except Exception as e:
        logger.warning("[A4] Browser %s failed: %s", platform, e)
        return {
            "platform": platform,
            "platform_name": platform_name,
            "fetch_method": "browser",
            "success": False,
            "error": str(e),
        }


async def a4_fetch_node(state: AgentState) -> Command:
    """A4: Fetch answers from AI platforms for all questions.

    Uses API-first strategy:
    - Phase 1: Doubao + Hunyuan (API, fast, with retries) in parallel
    - Phase 2: Kimi + DeepSeek (Browser, 90s per-question timeout, no retries) in parallel
    Browser failures do not block the overall flow.
    """
    session_id = state["session_id"]
    questions = state.get("questions", [])
    brand_profile = state.get("brand_profile") or {}

    # Cycle 3, Module 2: Check for platform_filter (selective_refetch)
    platform_filter = state.get("platform_filter")
    if platform_filter:
        logger.info("[A4] Platform filter active: %s", platform_filter)

    if not questions:
        return Command(
            update={
                "fetch_results": [],
                "current_step": "A4",
                "progress": 0.6,
            },
        )

    # Send user-visible reply with expected duration
    duration_msg = (
        f"开始向豆包、混元、Kimi、DeepSeek 四个平台提问，共 {len(questions)} 个问题。\n\n"
        "- API 平台（豆包/混元）：并行抓取，约 30 秒\n"
        "- 浏览器平台（Kimi/DeepSeek）：各需 3-5 分钟\n"
        "- 预计总耗时约 8-12 分钟\n\n"
        "请保持页面打开，可以切换到其他标签页做别的事，完成后将自动继续。"
    )
    await send_reply_event(session_id, duration_msg, is_delta=True, is_new_round=True)
    await send_reply_event(session_id, "", is_complete=True)

    await send_progress_event(
        session_id=session_id,
        step="A4",
        step_name="AI答案抓取",
        progress=0.55,
        message=f"开始抓取 {len(questions)} 个问题的答案（API优先策略）",
    )

    fetch_results: list[dict[str, Any]] = []

    try:
        # Initialize fetchers
        from app.core.fetchers.api.doubao_client import DoubaoClient
        from app.core.fetchers.api.hunyuan_client import HunyuanClient
        from app.core.fetchers.browser.deepseek_handler import DeepSeekHandler
        from app.core.fetchers.browser.kimi_handler import KimiHandler
        from app.core.fetchers.browser.playwright_client import PlaywrightBrowserClient
        from app.schemas.fetch import BrowserState

        # Each client initialized independently — failure of one does not block others
        # Cycle 3: If platform_filter is set, only initialize requested platforms
        _pf = set(platform_filter) if platform_filter else None

        try:
            if _pf is None or "doubao" in _pf:
                doubao_client = DoubaoClient()
            else:
                doubao_client = None
        except Exception as e:
            logger.warning(f"[A4] DoubaoClient init failed: {e}")
            doubao_client = None

        try:
            if _pf is None or "hunyuan" in _pf:
                hunyuan_client = HunyuanClient()
            else:
                hunyuan_client = None
        except Exception as e:
            logger.warning(f"[A4] HunyuanClient init failed: {e}")
            hunyuan_client = None

        try:
            if _pf is None or "kimi" in _pf:
                kimi_browser_client = PlaywrightBrowserClient(session_name="kimi")
                kimi_handler = KimiHandler(kimi_browser_client)
            else:
                kimi_browser_client = None
                kimi_handler = None
        except Exception as e:
            logger.warning(f"[A4] Kimi browser init failed: {e}")
            kimi_browser_client = None
            kimi_handler = None

        try:
            if _pf is None or "deepseek" in _pf:
                deepseek_browser_client = PlaywrightBrowserClient(session_name="deepseek")
                deepseek_handler = DeepSeekHandler(deepseek_browser_client)
            else:
                deepseek_browser_client = None
                deepseek_handler = None
        except Exception as e:
            logger.warning(f"[A4] DeepSeek browser init failed: {e}")
            deepseek_browser_client = None
            deepseek_handler = None

        total = len(questions)

        try:
            # =============================================================
            # Phase 1: Batch ALL API calls in parallel (Doubao + Hunyuan)
            # 12 questions × 2 platforms = 24 concurrent API calls
            # =============================================================
            await send_progress_event(
                session_id=session_id,
                step="A4",
                step_name="AI答案抓取",
                progress=0.57,
                message=f"Phase 1: {total} 个问题 × API平台，批量并行抓取中...",
            )

            api_tasks = []
            api_task_map: list[tuple[int, str]] = []  # (question_idx, platform)
            for idx, question in enumerate(questions):
                q_text = question.get("text", "")
                if doubao_client is not None:
                    api_tasks.append(
                        _throttled_retry_fetch(
                            _fetch_from_doubao,
                            doubao_client, q_text, brand_profile,
                            platform="doubao", method="api",
                        )
                    )
                    api_task_map.append((idx, "doubao"))
                if hunyuan_client is not None:
                    api_tasks.append(
                        _throttled_retry_fetch(
                            _fetch_from_hunyuan,
                            hunyuan_client, q_text, brand_profile,
                            platform="hunyuan", method="api",
                        )
                    )
                    api_task_map.append((idx, "hunyuan"))

            api_all_results = await asyncio.gather(*api_tasks, return_exceptions=True)

            # Organize API results by question index
            question_results: dict[int, list[dict[str, Any]]] = {i: [] for i in range(total)}
            api_success_total = 0
            for (q_idx, platform), result in zip(api_task_map, api_all_results):
                if isinstance(result, BaseException):
                    logger.error("[A4] API %s Q%d exception: %s", platform, q_idx + 1, result)
                    question_results[q_idx].append({
                        "platform": platform,
                        "fetch_method": "api",
                        "success": False,
                        "error": str(result),
                    })
                else:
                    question_results[q_idx].append(result)
                    if result.get("success"):
                        api_success_total += 1

            logger.info("[A4] Phase 1 (API) done: %d/%d succeeded", api_success_total, len(api_tasks))

            await send_progress_event(
                session_id=session_id,
                step="A4",
                step_name="AI答案抓取",
                progress=0.72,
                message=f"Phase 1 完成: API平台 {api_success_total}/{len(api_tasks)} 成功。开始Browser平台...",
            )

            # =============================================================
            # Phase 2: Browser platforms with per-browser semaphore
            # Each browser processes questions sequentially (can't parallelize)
            # but Kimi and DeepSeek run in parallel with each other
            # =============================================================
            async def _browser_pipeline(
                handler, browser_client, platform: str, platform_name: str,
            ) -> list[tuple[int, dict[str, Any]]]:
                """Process all questions through one browser sequentially.

                Integrates Layer 3 circuit breaker: if breaker is OPEN
                the platform is skipped entirely (no wasted wait time).
                """
                from app.workflow.resilience import get_circuit_breaker

                breaker = get_circuit_breaker(platform)
                results = []
                for idx, question in enumerate(questions):
                    q_text = question.get("text", "")

                    # Circuit breaker check
                    if not breaker.allow_request():
                        logger.info(
                            "[A4] %s circuit OPEN, skipping Q%d",
                            platform_name,
                            idx + 1,
                        )
                        results.append((idx, {
                            "platform": platform,
                            "platform_name": platform_name,
                            "fetch_method": "browser",
                            "success": False,
                            "error": (
                                f"平台 {platform_name} 暂时不可用（熔断保护）"
                            ),
                            "skipped_by_breaker": True,
                        }))
                        continue

                    r = await _browser_fetch_with_timeout(
                        _fetch_from_browser,
                        handler, q_text, brand_profile,
                        platform, platform_name, BrowserState,
                        timeout=_get_browser_timeout(platform),
                        session_id=session_id,
                    )

                    # Update circuit breaker state
                    if r.get("success"):
                        breaker.record_success()
                    else:
                        breaker.record_failure()

                    results.append((idx, r))

                    if (idx + 1) % 4 == 0 or idx == total - 1:
                        browser_done = idx + 1
                        await send_progress_event(
                            session_id=session_id,
                            step="A4",
                            step_name="AI答案抓取",
                            progress=0.72 + (browser_done / total) * 0.23,
                            message=f"Phase 2: {platform_name} {browser_done}/{total} 完成",
                        )
                return results

            # Only run browser pipelines for successfully initialized handlers
            # Each pipeline is wrapped with a global timeout to prevent indefinite blocking.
            pipeline_timeout = float(PlatformConstants.BROWSER_PIPELINE_TIMEOUT)

            async def _pipeline_with_global_timeout(
                handler, browser_client, platform: str, platform_name: str,
            ) -> list[tuple[int, dict[str, Any]]]:
                """Run _browser_pipeline capped at BROWSER_PIPELINE_TIMEOUT seconds total."""
                try:
                    return await asyncio.wait_for(
                        _browser_pipeline(handler, browser_client, platform, platform_name),
                        timeout=pipeline_timeout,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "[A4] %s pipeline hit global timeout (%.0fs), returning partial results",
                        platform_name, pipeline_timeout,
                    )
                    # Return timeout failure for all questions not yet processed
                    return [(i, {
                        "platform": platform,
                        "platform_name": platform_name,
                        "fetch_method": "browser",
                        "success": False,
                        "error": f"平台整体超时（{pipeline_timeout:.0f}s），跳过剩余问题",
                    }) for i in range(total)]

            browser_tasks = []
            browser_task_platforms = []
            if kimi_handler is not None and kimi_browser_client is not None:
                browser_tasks.append(
                    _pipeline_with_global_timeout(kimi_handler, kimi_browser_client, "kimi", "Kimi")
                )
                browser_task_platforms.append("kimi")
            if deepseek_handler is not None and deepseek_browser_client is not None:
                browser_tasks.append(
                    _pipeline_with_global_timeout(deepseek_handler, deepseek_browser_client, "deepseek", "DeepSeek")
                )
                browser_task_platforms.append("deepseek")

            if browser_tasks:
                browser_all_results = await asyncio.gather(*browser_tasks, return_exceptions=True)
            else:
                browser_all_results = []

            # Merge browser results into question_results
            browser_success_total = 0
            for browser_batch, platform in zip(browser_all_results, browser_task_platforms):
                if isinstance(browser_batch, BaseException):
                    logger.warning("[A4] Browser %s pipeline failed: %s", platform, browser_batch)
                    for idx in range(total):
                        question_results[idx].append({
                            "platform": platform,
                            "fetch_method": "browser",
                            "success": False,
                            "error": str(browser_batch),
                        })
                else:
                    for q_idx, r in browser_batch:
                        question_results[q_idx].append(r)
                        if r.get("success"):
                            browser_success_total += 1

            logger.info("[A4] Phase 2 (Browser) done: %d succeeded", browser_success_total)

            # Build final fetch_results list
            for idx, question in enumerate(questions):
                question_id = question.get("id", f"Q{idx}")
                question_text = question.get("text", "")
                platform_results = question_results[idx]
                q_success = sum(1 for r in platform_results if r.get("success"))
                logger.info("[A4] Q%d/%d: %d platforms succeeded", idx + 1, total, q_success)
                fetch_results.append({
                    "question_id": question_id,
                    "question_text": question_text,
                    "platform_results": platform_results,
                })

        finally:
            if kimi_browser_client is not None:
                await kimi_browser_client.close()
            if deepseek_browser_client is not None:
                await deepseek_browser_client.close()

        # Calculate success rate
        total_fetches = sum(len(r["platform_results"]) for r in fetch_results)
        successful_fetches = sum(
            1 for r in fetch_results for p in r["platform_results"] if p.get("success")
        )

        # Check minimum platform threshold: at least MIN_PLATFORMS_REQUIRED platforms
        # must have at least one successful fetch across all questions
        successful_platforms = set()
        for r in fetch_results:
            for p in r["platform_results"]:
                if p.get("success"):
                    successful_platforms.add(p.get("platform"))

        # Stage result: 逐平台推送抓取结果状态
        platform_fetch_stats: dict[str, dict[str, int]] = {}
        for r in fetch_results:
            for p in r["platform_results"]:
                pname = p.get("platform", "unknown")
                if pname not in platform_fetch_stats:
                    platform_fetch_stats[pname] = {"completed": 0, "total": 0, "mentions": 0}
                platform_fetch_stats[pname]["total"] += 1
                if p.get("success"):
                    platform_fetch_stats[pname]["completed"] += 1
                    answer = p.get("answer", {})
                    if isinstance(answer, dict) and answer.get("has_brand_mention"):
                        platform_fetch_stats[pname]["mentions"] += 1

        for pname, pstats in platform_fetch_stats.items():
            p_status = "success" if pstats["completed"] > 0 else "failed"
            await send_stage_result(
                session_id, "A4", "数据抓取",
                result_type="platform_status",
                data={
                    "platforms": [{
                        "platform": pname,
                        "status": p_status,
                        "questions_completed": pstats["completed"],
                        "questions_total": pstats["total"],
                        "mention_count": pstats["mentions"],
                        "error": None if p_status == "success" else f"{pname} 部分抓取失败",
                    }],
                },
            )

        # Layer 2 degradation: send notice based on platform success count
        from app.workflow.resilience import DegradationRegistry

        # When platform_filter is set, total is the filtered set, not all platforms
        total_platforms = len(platform_filter) if platform_filter else len(PLATFORMS)
        fail_count = total_platforms - len(successful_platforms)

        # Build per-platform status from fetch_results for degradation notice
        platform_statuses: dict[str, str] = {}
        for fr in fetch_results:
            for pr in fr.get("platform_results", []):
                pname = pr.get("platform", "unknown")
                if pr.get("skipped_by_breaker"):
                    platform_statuses[pname] = "skipped"
                elif pr.get("success"):
                    platform_statuses[pname] = "success"
                else:
                    platform_statuses[pname] = "failed"

        # When platform_filter is active (selective_refetch), adjust the minimum
        # threshold to the number of requested platforms (min 1), so that a
        # single-platform refetch doesn't trigger a spurious degradation notice.
        effective_min = min(MIN_PLATFORMS_REQUIRED, len(platform_filter)) if platform_filter else MIN_PLATFORMS_REQUIRED

        if len(successful_platforms) < effective_min:
            logger.warning(
                "[A4] Only %d platform(s) succeeded (%s), minimum %d required",
                len(successful_platforms),
                ", ".join(successful_platforms) if successful_platforms else "none",
                effective_min,
            )
            if len(successful_platforms) > 0:
                # Some data available -- send degradation notice, not error
                await DegradationRegistry.send_degradation_notice(
                    session_id,
                    "A4",
                    context={
                        "success_count": len(successful_platforms),
                        "fail_count": fail_count,
                        "platform_statuses": platform_statuses,
                    },
                )
            else:
                # Zero platforms -- hard error
                await send_error_event(
                    session_id,
                    "A4",
                    "所有平台数据获取均失败，请检查网络连接后重试",
                    recoverable=True,
                )
        elif fail_count > 0:
            # Met minimum threshold but some platforms failed -- notify user
            await DegradationRegistry.send_degradation_notice(
                session_id,
                "A4",
                context={
                    "success_count": len(successful_platforms),
                    "fail_count": fail_count,
                    "platform_statuses": platform_statuses,
                },
            )

        await send_progress_event(
            session_id=session_id,
            step="A4",
            step_name="AI答案抓取",
            progress=1.0,
            message=f"抓取完成: {successful_fetches}/{total_fetches} 成功（{len(successful_platforms)} 个平台有数据）",
            status="completed",
        )

        # Send detailed response to user
        brand_name = brand_profile.get("brand_name", "该品牌")

        # Calculate platform stats
        platform_stats: dict[str, dict[str, int]] = {}
        total_answers = 0
        brand_mentions = 0

        for result in fetch_results:
            platform_results = result.get("platform_results", [])
            for pr in platform_results:
                platform = pr.get("platform", "unknown")
                if platform not in platform_stats:
                    platform_stats[platform] = {"total": 0, "success": 0}
                platform_stats[platform]["total"] += 1
                if pr.get("success"):
                    platform_stats[platform]["success"] += 1
                    total_answers += 1
                    answer = pr.get("answer", "")
                    if isinstance(answer, dict):
                        answer = answer.get("content", "")
                    if brand_name in str(answer):
                        brand_mentions += 1

        platform_summary = []
        for platform, stats in platform_stats.items():
            success_rate = (stats["success"] / stats["total"] * 100) if stats["total"] > 0 else 0
            platform_summary.append(f"- **{platform}**: {stats['success']}/{stats['total']} 成功 ({success_rate:.0f}%)")

        detailed_response = f"""✅ **答案抓取完成**

我已针对模拟问题在主流AI搜索平台进行了答案抓取，获取「{brand_name}」在AI搜索中的曝光情况：

**📊 抓取概览**
- 总抓取次数：{total_fetches} 次
- 成功抓取：{successful_fetches} 次
- 成功率：{(successful_fetches/total_fetches*100) if total_fetches > 0 else 0:.0f}%

**🌐 平台分布**
{chr(10).join(platform_summary) if platform_summary else "- 暂无平台数据"}

**📈 品牌曝光**
- 品牌提及次数：{brand_mentions} 次
- 品牌提及率：{(brand_mentions/total_answers*100) if total_answers > 0 else 0:.0f}%

**📋 输出内容**
- 完整抓取结果（左侧 Canvas）
- 平台答案对比分析

**⏸️ 需要您确认**
答案抓取已完成。我已获取各AI平台对您品牌的回答内容，请查看左侧 Canvas 中的抓取结果。如果数据完整，请点击确认开始最终分析报告生成；如果需要补充抓取，请告诉我。"""

        from app.workflow.events import send_tpaor_event
        await send_tpaor_event(
            session_id, "response", detailed_response, is_complete=True
        )

        # Save and send artifact to Canvas
        from app.workflow.events import save_and_send_artifact
        await save_and_send_artifact(
            session_id=session_id,
            output_type="fetchResults",
            title="AI答案抓取结果",
            data={
                "fetchResults": fetch_results,
            },
        )

        # Cycle 3, Module 2: Merge with baseline if selective_refetch
        final_fetch_results = fetch_results
        baseline = state.get("preserved_fetch_results")
        if platform_filter and baseline:
            # Merge: new results (from filtered platforms) + baseline (unselected)
            # Build a map of question_id -> baseline entry for merging
            baseline_map: dict[str, dict] = {}
            for br in baseline:
                qid = br.get("question_id", "")
                if qid:
                    baseline_map[qid] = br

            merged: list[dict[str, Any]] = []
            for fr in fetch_results:
                qid = fr.get("question_id", "")
                new_pr = fr.get("platform_results", [])
                if qid in baseline_map:
                    # Combine: new platform results + baseline platform results
                    old_pr = baseline_map.pop(qid).get("platform_results", [])
                    combined_pr = new_pr + old_pr
                    merged.append({
                        "question_id": qid,
                        "question_text": fr.get("question_text", ""),
                        "platform_results": combined_pr,
                    })
                else:
                    merged.append(fr)

            # Add any remaining baseline entries (questions not in new results)
            for qid, br in baseline_map.items():
                merged.append(br)

            final_fetch_results = merged
            logger.info(
                "[A4] Merged %d new + %d baseline = %d total results",
                len(fetch_results), len(baseline), len(final_fetch_results),
            )

        # Task milestone: A4 completed (Cycle 3, Module 1)
        task_id = state.get("task_id")
        if task_id:
            try:
                from app.core.database import AsyncSessionLocal
                from app.services.task_service import TaskService
                from uuid import UUID as _UUID
                async with AsyncSessionLocal() as db:
                    ts = TaskService(db)
                    await ts.update_progress(
                        _UUID(task_id), stage="A4", progress=0.60,
                        message=f"抓取完成: {successful_fetches}/{total_fetches} 成功",
                    )
                    await ts.append_stage_result(_UUID(task_id), {
                        "stage": "A4",
                        "stage_name": "数据抓取",
                        "result_type": "platform_status",
                        "data": {
                            "total_fetches": total_fetches,
                            "successful_fetches": successful_fetches,
                            "platforms": list(successful_platforms),
                        },
                    })
            except Exception as te:
                logger.warning("[A4] TaskService milestone failed: %s", te)

        update_dict: dict[str, Any] = {
            "fetch_results": final_fetch_results,
            "current_step": "A4",
            "progress": 0.6,
        }
        # Clear platform_filter after use; flag auto A5 trigger for selective_refetch
        if platform_filter:
            update_dict["platform_filter"] = None
            update_dict["preserved_fetch_results"] = None
            update_dict["auto_trigger_a5"] = True

        if len(successful_platforms) == 0:
            update_dict["error_info"] = "所有平台数据获取均失败"

        return Command(update=update_dict)

    except Exception as e:
        await send_error_event(session_id, "A4", str(e), recoverable=True)

        # Task milestone: A4 failed
        task_id = state.get("task_id")
        if task_id:
            try:
                from app.core.database import AsyncSessionLocal
                from app.services.task_service import TaskService
                from uuid import UUID as _UUID
                async with AsyncSessionLocal() as db:
                    task_svc = TaskService(db)
                    await task_svc.fail_task(
                        _UUID(task_id),
                        error_message=str(e),
                        error_stage="A4",
                    )
            except Exception as te:
                logger.warning("[A4] TaskService fail_task failed: %s", te)

        return Command(
            update={
                "fetch_results": fetch_results,
                "error_info": {
                    "step": "A4",
                    "error": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                "current_step": "A4",
            },
        )


async def _fetch_from_doubao(
    client, question: str, brand_profile: dict
) -> dict[str, Any]:
    """Fetch answer from Doubao."""
    start_time = datetime.now(timezone.utc)

    try:
        response = await client.ask_with_search(question)
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        answer_text = response.answer_text

        if not answer_text or not answer_text.strip():
            logger.warning("[A4] doubao returned empty answer for question: %s", question[:60])
            return {
                "platform": "doubao",
                "platform_name": "豆包",
                "fetch_method": "api",
                "success": False,
                "error": "empty answer from API",
                "duration": duration,
            }

        return {
            "platform": "doubao",
            "platform_name": "豆包",
            "fetch_method": "api",
            "success": True,
            "answer": {
                "content": answer_text,
                "word_count": len(answer_text.split()),
                "has_brand_mention": _check_brand_mention(
                    answer_text, brand_profile.get("brand_name", "")
                ),
            },
            "citations": [ref.model_dump() for ref in response.search_references],
            "duration": duration,
        }
    except Exception as e:
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.warning("[A4] doubao exception: %s(%s) for question: %s",
                       type(e).__name__, e, question[:60])
        return {
            "platform": "doubao",
            "platform_name": "豆包",
            "fetch_method": "api",
            "success": False,
            "error": f"{type(e).__name__}: {e}" if str(e) else type(e).__name__,
            "duration": duration,
        }


async def _fetch_from_hunyuan(
    client, question: str, brand_profile: dict
) -> dict[str, Any]:
    """Fetch answer from Hunyuan."""
    start_time = datetime.now(timezone.utc)

    try:
        response = await client.ask_with_search(question)
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        answer_text = response.answer_text

        return {
            "platform": "hunyuan",
            "platform_name": "混元",
            "fetch_method": "api",
            "success": True,
            "answer": {
                "content": answer_text,
                "word_count": len(answer_text.split()),
                "has_brand_mention": _check_brand_mention(
                    answer_text, brand_profile.get("brand_name", "")
                ),
            },
            "citations": [ref.model_dump() for ref in response.search_references],
            "duration": duration,
        }
    except Exception as e:
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        return {
            "platform": "hunyuan",
            "platform_name": "混元",
            "fetch_method": "api",
            "success": False,
            "error": str(e),
            "duration": duration,
        }


async def _fetch_from_browser(
    handler,
    question: str,
    brand_profile: dict,
    platform: str,
    platform_name: str,
    browser_state,
    session_id: str = "",
) -> dict[str, Any]:
    start_time = datetime.now(timezone.utc)
    result_data = None
    error_message = None

    async for event in handler.fetch(question):
        if event.state == browser_state.WAITING_FOR_LOGIN and session_id:
            await send_browser_state_event(
                session_id=session_id,
                platform=platform,
                state=event.state.value,
                message=event.message,
                progress=event.progress,
                requires_action=event.requires_action,
                action_hint=event.action_hint,
            )
        if event.state == browser_state.ERROR:
            error_message = event.message or event.error or "抓取失败"
        if event.state == browser_state.COMPLETED and event.data:
            result_data = event.data

    duration = (datetime.now(timezone.utc) - start_time).total_seconds()

    if result_data and result_data.answer_text and len(result_data.answer_text.strip()) >= 10:
        answer_text = result_data.answer_text
        return {
            "platform": platform,
            "platform_name": platform_name,
            "fetch_method": "browser",
            "success": True,
            "answer": {
                "content": answer_text,
                "word_count": len(answer_text),
                "has_brand_mention": _check_brand_mention(
                    answer_text, brand_profile.get("brand_name", "")
                ),
            },
            "citations": [ref.model_dump() for ref in result_data.search_references],
            "duration": duration,
        }

    return {
        "platform": platform,
        "platform_name": platform_name,
        "fetch_method": "browser",
        "success": False,
        "error": error_message or "抓取失败",
        "duration": duration,
    }


def _check_brand_mention(content: str, brand_name: str) -> bool:
    """Check if brand is mentioned in content."""
    if not brand_name or not content:
        return False
    return brand_name.lower() in content.lower()
