"""A4 Node: Answer Fetching from AI Platforms.

This module contains the A4 node implementation for fetching answers
from various AI platforms (Doubao, Yuanbao, Kimi, DeepSeek, etc.)

Optimizations:
- API-first strategy: Doubao/Yuanbao (API) execute first, Kimi/DeepSeek (Browser) second
- API platforms retry up to 2 times on failure (exponential backoff)
- Browser platforms have a 90s per-question timeout (from PlatformConstants), no retries
- Browser failures do not block the overall flow
- Minimum 2 platforms with data required to proceed (adjusted for scoped platform fetch)
"""

import asyncio
import logging
import os
import random
import re
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

import httpx
from langgraph.types import Command

from app.core.config import settings
from app.core.constants import PlatformConstants, WorkflowConstants
from app.core.fetchers.browser.failure_observability import (
    BrowserFailureEvidenceService,
    build_failure_contract,
)
from app.core.fetchers.browser.browser_executor import (
    PendingBrowserAction,
    handle_browser_failure,
    resume_browser_action,
)
from app.tools.a4_fetch_agent import (
    AioAnswerFetchTool,
    build_legacy_platform_configs,
    normalize_public_platform_id,
    resolve_platform_display_names,
    to_executor_platform_id,
)
from app.workflow.browser_action_contract import (
    emit_browser_action_handoff,
    wait_for_browser_action_outcome,
)
from app.workflow.state import AgentState
from app.workflow.events import (
    send_progress_event,
    send_reply_event,
    send_error_event,
    send_browser_state_event,
)
from app.workflow.harness_validation import (
    build_harness_decision,
    decide_a4_completion_policy,
    validate_artifact_writeback,
    validate_scoped_fetch_merge,
)
from app.workflow.fetch_recovery import (
    build_fetch_recovery_plan,
    extract_latest_fetch_recovery_plan_from_state,
    normalize_question_targets,
)
from app.workflow.skill_state import (
    build_harness_decision_update,
    build_skill_result_update,
    build_validation_result_update,
)

logger = logging.getLogger(__name__)

# File-based logging — survives uvicorn --reload
# Also capture handler-level logs (browser handlers, parsers, etc.)
_log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
os.makedirs(_log_dir, exist_ok=True)
_a4_fh = logging.FileHandler(os.path.join(_log_dir, "a4.log"), encoding="utf-8")
_a4_fh.setLevel(logging.DEBUG)
_a4_fh.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s")
)

# Add to nodes_a4 logger
if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
    logger.addHandler(_a4_fh)

# Add to browser handler loggers so we see [Doubao]/[Kimi]/etc. in a4.log
for _handler_mod in [
    "app.core.fetchers.browser.base_handler",
    "app.core.fetchers.browser.doubao_handler",
    "app.core.fetchers.browser.kimi_handler",
    "app.core.fetchers.browser.deepseek_handler",
    "app.core.fetchers.browser.yuanbao_handler",
    "app.core.fetchers.browser.parsers.sse",
    "app.core.fetchers.browser.parsers.connect",
    "app.core.fetchers.browser.playwright_client",
    "app.core.playwright_installer",
]:
    _hl = logging.getLogger(_handler_mod)
    if not any(isinstance(h, logging.FileHandler) for h in _hl.handlers):
        _hl.addHandler(_a4_fh)
        _hl.setLevel(logging.DEBUG)

# Platform configurations
_AIO_ANSWER_FETCH_TOOL = AioAnswerFetchTool()

PLATFORMS = build_legacy_platform_configs()

# Aliases from centralized constants
MAX_RETRIES = WorkflowConstants.API_MAX_RETRIES
RETRY_BACKOFF_BASE = WorkflowConstants.API_RETRY_BACKOFF_BASE
BROWSER_MAX_RETRIES = WorkflowConstants.BROWSER_MAX_RETRIES
MIN_PLATFORMS_REQUIRED = WorkflowConstants.MIN_PLATFORMS_REQUIRED


def _canonicalize_platform_id(platform: Any) -> str:
    """Normalize user/orchestrator platform IDs into legacy A4 executor keys."""

    public_platform = normalize_public_platform_id(platform)
    if public_platform is None:
        return str(platform or "").strip().lower()
    return to_executor_platform_id(public_platform)


def _normalize_platform_filter(platform_filter: Any) -> list[str] | None:
    """Return a deduplicated canonical platform filter preserving input order."""

    if not platform_filter:
        return None
    if isinstance(platform_filter, str):
        platform_values = [platform_filter]
    else:
        try:
            platform_values = list(platform_filter)
        except TypeError:
            platform_values = [platform_filter]
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in platform_values:
        canonical = _canonicalize_platform_id(raw)
        if not canonical or canonical in seen:
            continue
        normalized.append(canonical)
        seen.add(canonical)
    return normalized or None


def _should_defer_aio_takeover_open(handler: Any) -> bool:
    client = getattr(handler, "client", None)
    return callable(getattr(client, "_ensure_remote_runtime", None))


def _display_platform_names(platforms: list[str]) -> str:
    """Render canonical platform IDs into user-facing display names."""

    return resolve_platform_display_names(platforms)


def _resolve_fetch_paths(
    fetch_mode: str,
    platforms: list[str],
) -> tuple[list[str], list[str]]:
    """Return the API/browser execution paths for the requested platforms."""

    if fetch_mode == "full":
        return [], list(platforms)

    api_platforms = [p for p in platforms if p in PlatformConstants.API_PLATFORMS]
    browser_platforms = [
        p for p in platforms if p in PlatformConstants.BROWSER_PLATFORMS
    ]
    return api_platforms, browser_platforms


def _build_filtered_fetch_summary(
    fetch_mode: str,
    platforms: list[str],
) -> dict[str, str]:
    """Build precise selective-refetch copy from actual execution paths."""

    api_platforms, browser_platforms = _resolve_fetch_paths(fetch_mode, platforms)
    platform_names = _display_platform_names(platforms)

    if api_platforms and browser_platforms:
        api_names = _display_platform_names(api_platforms)
        browser_names = _display_platform_names(browser_platforms)
        return {
            "mode_label": f"选择性重抓（{api_names} API + {browser_names} 浏览器）",
            "duration_msg": (
                f"开始重新抓取 **{platform_names}** 平台，共 {{question_count}} 个问题。\n\n"
                f"- 采集模式：混合采集（{api_names} API + {browser_names} 浏览器）\n"
                f"- API 平台（{api_names}）：约 2-3 分钟\n"
                f"- 浏览器平台（{browser_names}）：约 3-5 分钟\n"
                f"- 预计总耗时约 5-10 分钟\n\n"
                "请保持页面打开，完成后将自动继续。"
            ),
        }

    if browser_platforms:
        browser_names = _display_platform_names(browser_platforms)
        return {
            "mode_label": f"选择性重抓（{browser_names} 浏览器）",
            "duration_msg": (
                f"开始重新抓取 **{platform_names}** 平台，共 {{question_count}} 个问题。\n\n"
                f"- 采集模式：浏览器采集（{browser_names}）\n"
                f"- 预计耗时约 3-10 分钟\n\n"
                "请保持页面打开，完成后将自动继续。"
            ),
        }

    api_names = _display_platform_names(api_platforms or platforms)
    return {
        "mode_label": f"选择性重抓（{api_names} API）",
        "duration_msg": (
            f"开始重新抓取 **{platform_names}** 平台，共 {{question_count}} 个问题。\n\n"
            f"- 采集模式：API 采集（{api_names}）\n"
            f"- 预计耗时约 2-3 分钟\n\n"
            "请保持页面打开，完成后将自动继续。"
        ),
    }


def _build_a4_followup_options(*, retry_failed_only: bool) -> list[dict[str, str]]:
    supplemental_label = (
        "继续补采剩余失败项（浏览器）" if retry_failed_only else "补采失败项（浏览器）"
    )
    supplemental_description = (
        "只重跑本轮补采后仍失败的平台和问题，并和已成功结果继续合并"
        if retry_failed_only
        else "只重跑上一轮失败的平台和问题，并和已成功结果合并"
    )
    return [
        {
            "id": "run_supplemental_fetch",
            "label": supplemental_label,
            "description": supplemental_description,
        },
        {
            "id": "run_analysis_report",
            "label": "先用当前结果继续分析",
            "description": "跳过继续补采，直接基于当前成功样本生成新报告",
        },
    ]


def _build_a4_completion_observation(
    *,
    projected_fetch_results: list[dict[str, Any]],
    completion_decision: Any,
    artifact_validation: Any,
    retry_failed_only: bool,
    scoped_merge_active: bool,
    question_targets: list[dict[str, Any]],
    successful_fetches: int,
    total_fetches: int,
    fail_count: int,
    platform_statuses: dict[str, Any],
) -> dict[str, Any]:
    recovery_plan = build_fetch_recovery_plan(projected_fetch_results)
    requires_user_decision = bool(
        artifact_validation.passed
        and completion_decision.decision_type == "degraded_continue"
        and recovery_plan
        and int(recovery_plan.get("failure_count") or 0) > 0
    )
    return {
        "summary": (
            "答案抓取已完成，当前仍有失败项，需要由 Orchestrator 先请求用户确认下一步。"
            if requires_user_decision
            else "答案抓取已完成，结果已写回到当前官方样本。"
        ),
        "requires_user_decision": requires_user_decision,
        "followup_options": (
            _build_a4_followup_options(retry_failed_only=retry_failed_only)
            if requires_user_decision
            else []
        ),
        "failed_question_count": int(
            (recovery_plan or {}).get("failed_question_count") or 0
        ),
        "failed_platform_count": int(
            (recovery_plan or {}).get("failed_platform_count") or fail_count
        ),
        "failure_count": int((recovery_plan or {}).get("failure_count") or 0),
        "success_count": int(
            (recovery_plan or {}).get("success_count") or successful_fetches
        ),
        "total_count": int((recovery_plan or {}).get("total_count") or total_fetches),
        "successful_fetches": successful_fetches,
        "total_fetches": total_fetches,
        "artifact_write_validated": bool(artifact_validation.passed),
        "completion_decision": completion_decision.to_state_payload(),
        "retry_failed_only": bool(retry_failed_only),
        "scoped_merge_active": bool(scoped_merge_active),
        "question_target_count": len(question_targets),
        "platform_statuses": dict(platform_statuses or {}),
        "recovery_plan": recovery_plan,
    }


def _build_a4_completion_response(
    *,
    total_fetches: int,
    successful_fetches: int,
    platform_summary: list[str],
    observation: dict[str, Any],
) -> str:
    success_rate = (
        (successful_fetches / total_fetches * 100) if total_fetches > 0 else 0
    )
    if not bool(observation.get("artifact_write_validated", True)):
        next_step_message = (
            "抓取结果已经生成，但官方结果写回失败。"
            "我会先处理这次写回异常，当前不会直接继续生成分析报告。"
        )
    elif observation.get("requires_user_decision"):
        next_step_message = (
            "抓取已完成，但当前仍有失败项。"
            "我会先请您确认是继续补采剩余失败项，还是直接基于当前成功结果生成分析报告。"
        )
    else:
        next_step_message = "抓取已完成。我会基于当前抓取结果继续生成分析报告。"

    return f"""✅ **答案抓取完成**

本轮问题已经完成抓取，抓取结果和平台成功/失败统计都已汇总完成。

**📊 抓取概览**
- 总抓取次数：{total_fetches} 次
- 成功抓取：{successful_fetches} 次
- 成功率：{success_rate:.0f}%

**🌐 平台分布**
{chr(10).join(platform_summary) if platform_summary else "- 暂无平台数据"}

**📋 输出内容**
- 完整抓取结果
- 平台答案对照与引用列表

**⏭️ 下一步**
{next_step_message}"""


def _build_a4_canonical_result(
    *,
    projected_fetch_results: list[dict[str, Any]],
    authoritative_projection: dict[str, Any] | None,
    artifact_message_id: str,
    artifact_key: str,
    artifact_validation: Any,
    completion_decision: Any,
    observation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "version": "a4_fetch_result_v1",
        "fetch_results": projected_fetch_results,
        "platform_status": (
            (authoritative_projection or {}).get("platform_status") or {}
        ),
        "timing_summary": (
            (authoritative_projection or {}).get("timing_summary") or {}
        ),
        "artifact": {
            "message_id": artifact_message_id,
            "artifact_key": artifact_key,
            "output_type": "fetchResults",
        },
        "validation": artifact_validation.to_state_payload(),
        "completion_decision": completion_decision.to_state_payload(),
        "recovery_plan": dict(observation.get("recovery_plan") or {}),
        "observation": observation,
    }


def _build_browser_phase_start_message(
    fetch_mode: str,
    platforms: list[str],
    *,
    api_success_total: int | None = None,
    api_task_count: int | None = None,
) -> str:
    """Build the browser-phase progress copy from actual requested platforms."""

    api_platforms, browser_platforms = _resolve_fetch_paths(fetch_mode, platforms)
    browser_names = (
        _display_platform_names(browser_platforms) if browser_platforms else ""
    )

    if (
        fetch_mode != "full"
        and api_success_total is not None
        and api_task_count is not None
    ):
        if browser_names:
            return (
                f"{_display_platform_names(api_platforms)} API 抓取完成，"
                f"{api_success_total}/{api_task_count} 成功。开始 {browser_names} 浏览器采集。"
            )
        return (
            f"{_display_platform_names(api_platforms)} API 抓取完成，"
            f"{api_success_total}/{api_task_count} 成功。"
        )

    if browser_names:
        return f"启动浏览器采集：{browser_names}。"
    return "启动浏览器采集。"


def _question_id_from_state_question(question: dict[str, Any]) -> str:
    """Resolve the stable question id from workflow question objects."""

    if not isinstance(question, dict):
        return ""
    return str(
        question.get("id") or question.get("question_id") or question.get("qid") or ""
    ).strip()


def _derive_preserved_fetch_results(
    *,
    current_questions: list[dict[str, Any]],
    existing_fetch_results: list[dict[str, Any]] | None,
    selected_platforms: set[str] | None = None,
    question_platform_targets: dict[str, set[str]] | None = None,
) -> list[dict[str, Any]]:
    """Preserve only unselected platform results for the current question set.

    This is used for true scoped reruns only. If the current question set has
    changed (for example, panorama -> scenario), old fetch rows must not leak
    into the new analysis contract.
    """

    current_question_ids = {
        _question_id_from_state_question(question)
        for question in current_questions
        if _question_id_from_state_question(question)
    }
    if not current_question_ids:
        return []

    preserved: list[dict[str, Any]] = []
    for existing_entry in existing_fetch_results or []:
        question_id = str(existing_entry.get("question_id") or "").strip()
        if not question_id or question_id not in current_question_ids:
            continue
        targeted_platforms = (
            question_platform_targets.get(question_id)
            if question_platform_targets and question_id in question_platform_targets
            else selected_platforms
        )
        kept_platform_results = [
            platform_result
            for platform_result in existing_entry.get("platform_results", []) or []
            if not targeted_platforms
            or _canonicalize_platform_id(platform_result.get("platform"))
            not in targeted_platforms
        ]
        if kept_platform_results:
            preserved.append(
                {
                    "question_id": question_id,
                    "question_text": existing_entry.get("question_text", ""),
                    "platform_results": kept_platform_results,
                    "aio_platform_packets": _collect_aio_platform_packets(
                        kept_platform_results
                    ),
                }
            )
    return preserved


def _question_platform_targets_from_questions(
    questions: list[dict[str, Any]],
) -> dict[str, set[str]]:
    targets: dict[str, set[str]] = {}
    for question in questions:
        question_id = _question_id_from_state_question(question)
        if not question_id:
            continue
        platforms: set[str] = set()
        for raw_platform in question.get("platforms") or []:
            platform = _canonicalize_platform_id(raw_platform)
            if platform:
                platforms.add(platform)
        if platforms:
            targets[question_id] = platforms
    return targets


async def _gather_browser_tasks(
    browser_tasks: list[Coroutine[Any, Any, Any]],
    *,
    timeout_seconds: float | None = None,
) -> list[Any]:
    """Run browser platform pipelines with the configured AIO concurrency cap."""

    if settings.AIO_ENABLED and settings.AIO_BASE_URL:
        logger.info(
            "[A4] Phase 2: AIO runtime detected, executing browser pipelines in parallel (max=%d)",
            max(1, settings.AIO_MAX_PARALLEL_BROWSER_SESSIONS),
        )

    return await _AIO_ANSWER_FETCH_TOOL.gather_browser_tasks(
        browser_tasks,
        timeout_seconds=timeout_seconds,
    )


def _get_aio_auth_scope(state: AgentState) -> str:
    """Derive the long-lived AIO auth scope.

    Login state must follow the imspecta account, not one analysis task.
    """

    return _AIO_ANSWER_FETCH_TOOL.build_auth_context(state).specta_user_id


def _get_aio_run_scope(state: AgentState) -> str:
    """Derive the per-analysis AIO run artifact scope."""

    return _AIO_ANSWER_FETCH_TOOL.build_run_context(state).entity_id


def _create_browser_client(platform: str, state: AgentState):
    """Create the browser client selected by current runtime mode."""

    return _AIO_ANSWER_FETCH_TOOL.create_browser_client(
        platform=platform,
        state=state,
    )


def _attach_aio_platform_packet(
    result: dict[str, Any],
    *,
    question: dict[str, Any] | None,
    request: Any,
) -> dict[str, Any]:
    """Attach the new AIO result packet while preserving legacy A4 shape."""

    return _AIO_ANSWER_FETCH_TOOL.attach_result_packet_to_legacy(
        result=result,
        question=question,
        auth_context=getattr(request, "auth_context", None),
        run_context=getattr(request, "run_context", None),
    )


def _collect_aio_platform_packets(
    platform_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        packet
        for packet in (result.get("aio_packet") for result in platform_results)
        if isinstance(packet, dict)
    ]


def _packets_for_fetch_result(fetch_result: dict[str, Any]) -> list[dict[str, Any]]:
    packets = fetch_result.get("aio_platform_packets")
    if isinstance(packets, list):
        return [packet for packet in packets if isinstance(packet, dict)]
    platform_results = fetch_result.get("platform_results", [])
    if isinstance(platform_results, list):
        return _collect_aio_platform_packets(platform_results)
    return []


def _packet_status(packet: dict[str, Any]) -> str:
    return str(packet.get("status") or "").strip().lower()


def _packet_status_is_success(status: str) -> bool:
    return status in {"result", "success"}


def _packet_platform(packet: dict[str, Any]) -> str:
    return str(packet.get("platform") or "unknown").strip().lower() or "unknown"


def _status_priority(status: str) -> int:
    if status == "success":
        return 4
    if status == "skipped":
        return 3
    if status == "takeover_required":
        return 2
    if status == "failed":
        return 1
    return 0


def _fetch_result_has_success(fetch_result: dict[str, Any]) -> bool:
    packets = _packets_for_fetch_result(fetch_result)
    if packets:
        return any(
            _packet_status_is_success(_packet_status(packet)) for packet in packets
        )
    return bool(fetch_result.get("success"))


def _build_aio_packet_fetch_summary(
    fetch_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build A4 downstream status from AIO packets, not legacy booleans."""

    total_fetches = 0
    successful_fetches = 0
    total_answers = 0
    successful_platforms: set[str] = set()
    platform_statuses: dict[str, str] = {}
    platform_fetch_stats: dict[str, dict[str, int]] = {}

    for fetch_result in fetch_results:
        for packet in _packets_for_fetch_result(fetch_result):
            platform = _packet_platform(packet)
            status = _packet_status(packet)
            total_fetches += 1

            if platform not in platform_fetch_stats:
                platform_fetch_stats[platform] = {
                    "completed": 0,
                    "total": 0,
                    "mentions": 0,
                    "skipped": 0,
                    "takeover_required": 0,
                    "failed": 0,
                }
            platform_fetch_stats[platform]["total"] += 1

            next_platform_status = "failed"
            if _packet_status_is_success(status):
                successful_fetches += 1
                total_answers += 1
                successful_platforms.add(platform)
                platform_fetch_stats[platform]["completed"] += 1
                next_platform_status = "success"
            elif status == "skipped":
                platform_fetch_stats[platform]["skipped"] += 1
                next_platform_status = "skipped"
            elif status == "takeover_required":
                platform_fetch_stats[platform]["takeover_required"] += 1
                next_platform_status = "takeover_required"
            else:
                platform_fetch_stats[platform]["failed"] += 1

            previous_status = platform_statuses.get(platform)
            if _status_priority(next_platform_status) >= _status_priority(
                previous_status or ""
            ):
                platform_statuses[platform] = next_platform_status

    return {
        "total_fetches": total_fetches,
        "successful_fetches": successful_fetches,
        "successful_platforms": successful_platforms,
        "platform_fetch_stats": platform_fetch_stats,
        "platform_statuses": platform_statuses,
        "total_answers": total_answers,
    }


def _should_count_browser_failure_for_breaker(result: dict[str, Any]) -> bool:
    """Decide whether a browser failure should trip the platform breaker.

    Browser breaker should only open for platform-availability problems, not for
    softer extraction misses where the page loaded but we failed to collect a
    usable answer on the current question.
    """

    if result.get("success"):
        return False

    error_type = str(result.get("error_type") or "").strip().lower()
    if error_type in {
        "empty_answer",
        "submission_not_confirmed",
        "rate_limit",
        "user_skipped",
        "user_action_timeout",
        "resume_gate_failed",
        "modal_timeout",
    }:
        return False

    if error_type == "verify":
        return True

    error_message = " ".join(str(result.get("error") or "").split()).lower()
    extraction_miss_markers = (
        "未能提取到有效回答",
        "empty answer",
        "empty response",
        "no content",
        "content_len=0",
    )
    if any(marker.lower() in error_message for marker in extraction_miss_markers):
        return False

    return True


class _ProgressTracker:
    """Track per-platform completion during Phase 1 API fetch and emit progress."""

    def __init__(
        self,
        total_questions: int,
        active_platforms: list[str],
        session_id: str,
        task_id: str | None = None,
    ):
        self.total_questions = total_questions
        self.active_platforms = active_platforms
        self.session_id = session_id
        self.task_id = task_id
        self.total_tasks = total_questions * len(active_platforms)
        self.completed = 0
        # Per-platform counters
        self._platform_done: dict[str, int] = {p: 0 for p in active_platforms}

    async def record_completion(self, platform: str) -> None:
        """Record one API task completion and emit progress event."""
        self.completed += 1
        logger.info(
            "[A4] ProgressTracker: %s completed (%d/%d)",
            platform,
            self.completed,
            self.total_tasks,
        )
        self._platform_done[platform] = self._platform_done.get(platform, 0) + 1

        # Progress: linear interpolation 0.57 → 0.72
        ratio = self.completed / self.total_tasks if self.total_tasks > 0 else 1.0
        progress = 0.57 + ratio * 0.15

        # Build per-platform summary
        parts = []
        for p in self.active_platforms:
            name = PLATFORMS.get(p, {}).get("name", p)
            done = self._platform_done.get(p, 0)
            parts.append(f"{name} {done}/{self.total_questions}")

        # Count questions with ALL platforms done
        message = f"API抓取进度: {self.completed}/{self.total_tasks} 完成（{' | '.join(parts)}）"

        await send_progress_event(
            session_id=self.session_id,
            step="A4",
            step_name="AI答案抓取",
            progress=progress,
            message=message,
        )
        await _persist_task_progress(
            self.task_id,
            stage="A4",
            progress=progress,
            message=message,
            context="api_progress",
        )


async def _persist_task_progress(
    task_id: str | None,
    *,
    stage: str,
    progress: float,
    message: str,
    context: str,
) -> None:
    """Mirror live websocket progress into durable task state when available."""

    if not task_id:
        return

    try:
        from uuid import UUID as _UUID

        from app.core.database import AsyncSessionLocal
        from app.services.task_service import TaskService

        async with AsyncSessionLocal() as db:
            ts = TaskService(db)
            await ts.update_progress(
                _UUID(task_id),
                stage=stage,
                progress=progress,
                message=message,
            )
    except Exception as exc:
        logger.warning("[A4] Task progress sync failed (%s): %s", context, exc)


async def _tracked_api_fetch(
    coro: Coroutine[Any, Any, dict[str, Any]],
    platform: str,
    tracker: _ProgressTracker,
) -> dict[str, Any]:
    """Wrap an API fetch coroutine to report completion via tracker."""
    logger.info("[A4] _tracked_api_fetch started for %s", platform)
    try:
        result = await coro
        return result
    finally:
        await tracker.record_completion(platform)


def _get_browser_timeout(platform: str) -> float:
    """Get per-platform browser timeout from constants."""
    return float(PlatformConstants.PLATFORM_TIMEOUTS.get(platform, 200))


_BROWSER_ACTION_WAIT_TIMEOUT_SECONDS = 900.0
_BROWSER_ACTION_RESUME_BUFFER_SECONDS = 120.0


def _is_aio_browser_handler(handler: Any) -> bool:
    client = getattr(handler, "client", None)
    if client is None:
        return False
    if bool(getattr(client, "aio_session_id", None)):
        return True
    return client.__class__.__name__ == "AioConnectedBrowserClient"


def _get_browser_human_action_timeout(platform: str) -> float:
    """Worst-case budget for a browser question that needs human takeover."""

    return (
        _BROWSER_ACTION_WAIT_TIMEOUT_SECONDS
        + _BROWSER_ACTION_RESUME_BUFFER_SECONDS
        + _get_browser_timeout(platform)
    )


def _get_browser_action_wait_timeout(platform: str, question_count: int) -> int:
    """Bound browser handoff waits so multi-question runs cannot stall a platform."""

    if question_count <= 1:
        return int(_BROWSER_ACTION_WAIT_TIMEOUT_SECONDS)

    per_question_timeout = _get_browser_timeout(platform)
    capped_wait = max(180.0, per_question_timeout + 60.0)
    return int(min(_BROWSER_ACTION_WAIT_TIMEOUT_SECONDS, capped_wait))


def _get_browser_pipeline_timeout(platform: str, question_count: int) -> float:
    """Derive a bounded browser pipeline timeout.

    For multi-question runs, keep the platform-level timeout as a real cap so one
    browser does not stall the whole A4 stage for tens of minutes. For a
    single-question run, still allow the longer human-action budget because the
    user may be actively completing a login or verification step for that one
    question.
    """

    configured_timeout = float(PlatformConstants.BROWSER_PIPELINE_TIMEOUT)
    if question_count <= 0:
        return configured_timeout

    if question_count == 1:
        return max(configured_timeout, _get_browser_human_action_timeout(platform))

    first_question_timeout = max(300.0, _get_browser_timeout(platform))
    per_question_timeout = _get_browser_timeout(platform)
    inter_question_delay = float(
        PlatformConstants.PLATFORM_REQUEST_DELAYS.get(platform, 3.0)
    )
    remaining_questions = max(question_count - 1, 0)

    derived_timeout = (
        first_question_timeout
        + remaining_questions * (per_question_timeout + inter_question_delay)
        + 30.0
    )
    return min(configured_timeout, derived_timeout)


_platform_semaphores: dict[str, asyncio.Semaphore] = {}


def _get_platform_semaphore(platform: str) -> asyncio.Semaphore:
    """Get or create a per-platform semaphore (concurrency=1 for serial execution)."""
    return _platform_semaphores.setdefault(platform, asyncio.Semaphore(1))


async def _throttled_retry_fetch(
    fetch_fn: Callable[..., Coroutine[Any, Any, dict[str, Any]]],
    *args: Any,
    platform: str,
    method: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Per-platform serial execution with inter-request delay to avoid 429."""
    sem = _get_platform_semaphore(platform)
    async with sem:
        result = await _retry_fetch(
            fetch_fn, *args, platform=platform, method=method, **kwargs
        )
        # Delay before releasing semaphore so the next request to the same
        # platform doesn't fire immediately (prevents 429 rate limiting).
        delay = PlatformConstants.PLATFORM_REQUEST_DELAYS.get(platform, 3.0)
        await asyncio.sleep(delay)
        return result


# Kimi (OpenAI-compatible): error.type → internal category
_429_ERROR_TYPE_MAP = {
    "rate_limit_reached_error": "rate_limit",
    "engine_overloaded_error": "engine_overloaded",
    "exceeded_current_quota_error": "quota_exceeded",
}

# Doubao / Volcengine: error.code → internal category
# Ref: https://www.volcengine.com/docs/82379/1848593
_429_ERROR_CODE_MAP = {
    "RequestBurstTooFast": "burst",
    "ServerOverloaded": "engine_overloaded",
    "SetLimitExceeded": "quota_exceeded",
}

_RETRY_SECONDS_RE = re.compile(r"try again after (\d+) seconds", re.IGNORECASE)


def _engine_overload_retry_budget(platform: str) -> tuple[int, float]:
    """Return a bounded overload retry budget for one API platform.

    Doubao's responses endpoint is the dominant long-tail blocker in real runs.
    When it repeatedly returns `engine_overloaded`, we prefer partial completion
    over stalling the entire A4 stage for many minutes.
    """

    if platform == "doubao":
        return 1, 2.0
    return (
        WorkflowConstants.ENGINE_OVERLOADED_MAX_RETRIES,
        WorkflowConstants.ENGINE_OVERLOADED_BASE_WAIT,
    )


def _parse_429_error(response: httpx.Response) -> tuple[str, float | None]:
    """Parse 429 response body to extract error type and retry hint.

    Supports two response formats:
      - Kimi (OpenAI-compatible): identifier in error.type
      - Doubao (Volcengine):      identifier in error.code, error.type is generic "TooManyRequests"

    Returns (error_type, retry_seconds):
      error_type: "rate_limit" | "engine_overloaded" | "quota_exceeded" | "burst" | "unknown"
      retry_seconds: extracted from message "try again after N seconds", or None
    """
    try:
        body = response.json()
    except Exception:
        return "unknown", None

    error_obj = body.get("error", {})
    logger.debug("[A4] 429 response body: %s", body)

    # Try Kimi-style error.type first
    raw_type = error_obj.get("type", "")
    error_type = _429_ERROR_TYPE_MAP.get(raw_type)

    # Then try Doubao-style error.code
    if error_type is None:
        raw_code = error_obj.get("code", "")
        error_type = _429_ERROR_CODE_MAP.get(raw_code, "unknown")

    retry_seconds: float | None = None
    message = error_obj.get("message", "")
    match = _RETRY_SECONDS_RE.search(message)
    if match:
        retry_seconds = float(match.group(1))

    return error_type, retry_seconds


async def _retry_fetch(
    fetch_fn: Callable[..., Coroutine[Any, Any, dict[str, Any]]],
    *args: Any,
    platform: str,
    method: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Retry a fetch function up to MAX_RETRIES times with exponential backoff.

    Handles HTTP 429 with classified retry strategies:
      - quota_exceeded: immediately break, no retry
      - engine_overloaded: short backoff + jitter, separate retry budget (does NOT consume main attempt)
      - burst: RequestBurstTooFast — short backoff, consumes main attempt
      - rate_limit / unknown: honour message hint → Retry-After header → default 30s
    Returns the first successful result, or the last failure dict.
    """
    last_result: dict[str, Any] = {
        "platform": platform,
        "fetch_method": method,
        "success": False,
        "error": "no attempt made",
    }

    attempt = 0
    overload_retries = 0
    overload_retry_limit, overload_base_wait = _engine_overload_retry_budget(platform)

    while attempt <= MAX_RETRIES:
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

            # --- Classified 429 handling ---
            is_429 = (
                isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429
            )
            if is_429:
                error_type, hint_seconds = _parse_429_error(e.response)

                if error_type == "quota_exceeded":
                    logger.error(
                        "[A4] %s 429 (quota_exceeded) — skipping retries",
                        platform,
                    )
                    break

                if error_type == "engine_overloaded":
                    overload_retries += 1
                    if overload_retries > overload_retry_limit:
                        logger.warning(
                            "[A4] %s 429 (engine_overloaded) — exhausted %d overload retries",
                            platform,
                            overload_retry_limit,
                        )
                        break
                    wait = (
                        overload_base_wait
                        + overload_retries * 5.0
                        + random.uniform(0, 3)
                    )
                    logger.warning(
                        "[A4] %s 429 (engine_overloaded), waiting %.1fs (overload retry %d/%d)",
                        platform,
                        wait,
                        overload_retries,
                        overload_retry_limit,
                    )
                    await asyncio.sleep(wait)
                    # Don't consume the main attempt budget
                    continue

                if error_type == "burst":
                    # RequestBurstTooFast: slope too steep, pause briefly then retry
                    if attempt < MAX_RETRIES:
                        wait = (
                            WorkflowConstants.BURST_BACKOFF_BASE
                            + attempt * 3.0
                            + random.uniform(0, 2)
                        )
                        logger.warning(
                            "[A4] %s 429 (burst), slowing down — waiting %.1fs before retry %d/%d",
                            platform,
                            wait,
                            attempt + 1,
                            MAX_RETRIES,
                        )
                        await asyncio.sleep(wait)
                        attempt += 1
                        continue

                # rate_limit or unknown
                if attempt < MAX_RETRIES:
                    try:
                        header_val = float(e.response.headers.get("Retry-After", 0))
                    except (ValueError, TypeError):
                        header_val = 0
                    retry_after = (
                        hint_seconds
                        or (header_val or None)
                        or WorkflowConstants.DEFAULT_429_RETRY_SECONDS
                    )
                    logger.warning(
                        "[A4] %s 429 (%s), waiting %.0fs before retry",
                        platform,
                        error_type,
                        retry_after,
                    )
                    await asyncio.sleep(retry_after)
                    attempt += 1
                    continue

        if attempt < MAX_RETRIES:
            wait = RETRY_BACKOFF_BASE**attempt  # 1s, 2s
            logger.info(
                "[A4] %s attempt %d failed (%s), retrying in %.1fs",
                platform,
                attempt + 1,
                last_result.get("error", "unknown"),
                wait,
            )
            await asyncio.sleep(wait)

        attempt += 1

    logger.warning(
        "[A4] %s failed after %d attempts: %s",
        platform,
        MAX_RETRIES + 1,
        last_result.get("error"),
    )
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
    # _fetch_from_browser signature: handler, question, platform, platform_name, browser_state
    platform = args[2] if len(args) > 2 else "unknown"
    platform_name = args[3] if len(args) > 3 else platform
    handler = args[0] if args else None
    question_id = kwargs.get("question_id")
    question_text = args[1] if len(args) > 1 else None

    async def _cleanup_browser_client() -> None:
        client = getattr(handler, "client", None)
        if client is None or not hasattr(client, "close"):
            return
        try:
            await asyncio.wait_for(client.close(), timeout=15)
            logger.info(
                "[A4] Browser %s client cleaned up after failure/timeout", platform
            )
        except Exception as cleanup_error:
            logger.debug(
                "[A4] Browser %s cleanup failed: %s",
                platform,
                cleanup_error,
            )

    try:
        result = await asyncio.wait_for(
            fetch_fn(*args, **kwargs),
            timeout=timeout,
        )
        return result
    except asyncio.TimeoutError:
        logger.warning("[A4] Browser %s timed out after %.0fs", platform, timeout)
        await _cleanup_browser_client()
        evidence_ref = await _capture_browser_failure_evidence(
            handler=handler,
            failure_reason="question_timeout",
            execution_stage="wait_response",
            question_id=question_id,
            question_text=question_text,
            extra_metadata={"timeout_seconds": timeout},
        )

        return _build_browser_failure_result(
            platform=platform,
            platform_name=platform_name,
            error=f"超时（{timeout:.0f}s）",
            error_type="question_timeout",
            duration=timeout,
            failure_reason="question_timeout",
            execution_stage="wait_response",
            retryable=False,
            needs_handoff=False,
            failure_layer="executor",
            evidence_ref=evidence_ref,
        )
    except Exception as e:
        logger.warning("[A4] Browser %s failed: %s", platform, e)
        await _cleanup_browser_client()
        evidence_ref = await _capture_browser_failure_evidence(
            handler=handler,
            failure_reason="parser_error",
            execution_stage="executor_failure",
            question_id=question_id,
            question_text=question_text,
            extra_metadata={"exception": str(e)},
        )

        return _build_browser_failure_result(
            platform=platform,
            platform_name=platform_name,
            error=str(e),
            error_type="parser_error",
            duration=0.0,
            failure_reason="parser_error",
            execution_stage="executor_failure",
            retryable=False,
            needs_handoff=False,
            failure_layer="executor",
            evidence_ref=evidence_ref,
        )


async def _capture_browser_failure_evidence(
    *,
    handler: Any,
    failure_reason: str,
    execution_stage: str,
    question_id: str | None = None,
    question_text: str | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if handler is None:
        return None
    if question_id is not None:
        setattr(handler, "_current_question_id", question_id)
    if question_text is not None:
        setattr(handler, "_current_question_text", question_text)
    capture = getattr(handler, "_capture_failure_evidence", None)
    if not callable(capture):
        return None
    return await capture(
        failure_reason=failure_reason,
        execution_stage=execution_stage,
        extra_metadata=extra_metadata,
    )


def _build_browser_failure_result(
    *,
    platform: str,
    platform_name: str,
    error: str,
    error_type: str,
    duration: float,
    failure_reason: str,
    execution_stage: str,
    retryable: bool,
    needs_handoff: bool,
    failure_layer: str,
    evidence_ref: dict[str, Any] | None = None,
    stop_platform: bool = False,
    skipped_by_user: bool = False,
    **extra_fields: Any,
) -> dict[str, Any]:
    result = {
        "platform": platform,
        "platform_name": platform_name,
        "fetch_method": "browser",
        "success": False,
        "error": error,
        "error_type": error_type,
        "duration": duration,
        "stop_platform": stop_platform,
        "skipped_by_user": skipped_by_user,
        **build_failure_contract(
            failure_reason=failure_reason,
            execution_stage=execution_stage,
            retryable=retryable,
            needs_handoff=needs_handoff,
            failure_layer=failure_layer,
            evidence_ref=evidence_ref,
        ),
    }
    result.update(
        {key: value for key, value in extra_fields.items() if value is not None}
    )
    return result


def _build_duration_msg(fetch_mode: str, question_count: int) -> str:
    """Build user-visible duration message dynamically from PlatformConstants."""
    all_names = "、".join(
        PlatformConstants.PLATFORM_DISPLAY_NAMES[p]
        for p in PlatformConstants.SUPPORTED_PLATFORMS
    )
    platform_count = len(PlatformConstants.SUPPORTED_PLATFORMS)

    if fetch_mode == "full":
        pipelines = " / ".join(
            PlatformConstants.PLATFORM_DISPLAY_NAMES[p]
            for p in PlatformConstants.SUPPORTED_PLATFORMS
        )
        schedule_hint = f"{pipelines} 各平台并行采集"
        return (
            f"开始向{all_names} {platform_count} 个平台提问，共 {question_count} 个问题。\n\n"
            f"- 采集模式：**完整采集**（{platform_count} 平台全浏览器）\n"
            f"- {schedule_hint}\n"
            f"- 预计总耗时约 8-15 分钟\n\n"
            "请保持页面打开，可以切换到其他标签页做别的事，完成后将自动继续。"
        )
    else:
        api_str = "/".join(
            PlatformConstants.PLATFORM_DISPLAY_NAMES[p]
            for p in PlatformConstants.API_PLATFORMS
        )
        browser_str = "/".join(
            PlatformConstants.PLATFORM_DISPLAY_NAMES[p]
            for p in PlatformConstants.BROWSER_PLATFORMS
        )
        return (
            f"开始向{all_names} {platform_count} 个平台提问，共 {question_count} 个问题。\n\n"
            f"- 采集模式：**快速采集**（API + {browser_str} 浏览器）\n"
            f"- API 平台（{api_str}）：各平台串行抓取，约 2-3 分钟\n"
            f"- 浏览器平台（{browser_str}）：约 3-5 分钟\n"
            f"- 预计总耗时约 5-10 分钟\n\n"
            "请保持页面打开，可以切换到其他标签页做别的事，完成后将自动继续。"
        )


async def a4_fetch_node(state: AgentState) -> Command:
    """A4: Fetch answers from AI platforms for all questions.

    Supports two modes (controlled by state['fetch_mode']):
    - fast: API (Doubao/Yuanbao/Kimi) + DeepSeek Browser  (~5-10 min)
    - full: All 4 platforms via Browser only, no API       (~8-15 min)
    """
    session_id = state["session_id"]
    questions = list(state.get("questions", []) or [])
    brand_profile = state.get("brand_profile") or {}
    fetch_mode = state.get("fetch_mode") or "fast"
    tool_args = state.get("tool_call_args") or {}
    retry_failed_only = bool(tool_args.get("retry_failed_only"))
    question_targets = normalize_question_targets(tool_args.get("question_targets"))
    if retry_failed_only and not question_targets:
        recovery_plan = extract_latest_fetch_recovery_plan_from_state(state)
        question_targets = normalize_question_targets(
            (recovery_plan or {}).get("question_targets")
        )
    if question_targets:
        questions = [
            {
                "id": item["question_id"],
                "text": item["question_text"],
                "category": "失败补采",
                "platforms": list(item["platforms"]),
            }
            for item in question_targets
        ]
    requested_platforms = tool_args.get("platforms") or []
    normalized_requested_platforms = _normalize_platform_filter(requested_platforms)
    targeted_platforms = _normalize_platform_filter(
        [
            platform
            for item in question_targets
            for platform in item.get("platforms") or []
        ]
    )
    # 显式 tool_args.platforms 优先于历史 state.platform_filter，避免旧范围覆盖当前用户意图。
    raw_platform_filter = (
        normalized_requested_platforms
        or targeted_platforms
        or state.get("platform_filter")
    )
    platform_filter = _normalize_platform_filter(raw_platform_filter)
    question_platform_targets = _question_platform_targets_from_questions(questions)
    aio_fetch_request = _AIO_ANSWER_FETCH_TOOL.build_request(
        state=state,
        questions=questions,
        mode=fetch_mode,
        platform_filter=raw_platform_filter,
    )
    if platform_filter:
        logger.info(
            "[A4] Platform filter active: raw=%s executor=%s public=%s",
            raw_platform_filter,
            platform_filter,
            list(aio_fetch_request.platforms),
        )

    logger.info(
        "[A4] fetch_mode=%s, questions=%d, auth_context=%s, run_context=%s",
        fetch_mode,
        len(questions),
        aio_fetch_request.auth_context.context_key,
        aio_fetch_request.run_context.context_key,
    )
    try:
        cleaned = BrowserFailureEvidenceService().cleanup_expired()
        if cleaned:
            logger.info(
                "[A4] Cleaned %d expired failure-evidence day folder(s)", cleaned
            )
    except Exception as cleanup_err:
        logger.warning("[A4] Failure-evidence cleanup failed: %s", cleanup_err)

    if not questions:
        return Command(
            update={
                "fetch_results": [],
                "current_step": "A4",
                "progress": 0.6,
            },
        )

    # Send user-visible reply with expected duration based on actual execution path.
    if platform_filter:
        selective_summary = _build_filtered_fetch_summary(fetch_mode, platform_filter)
        duration_msg = selective_summary["duration_msg"].format(
            question_count=len(questions)
        )
        mode_label = selective_summary["mode_label"]
    else:
        duration_msg = _build_duration_msg(fetch_mode, len(questions))
        mode_label = (
            "完整采集（4平台全浏览器）"
            if fetch_mode == "full"
            else "快速采集（豆包、元宝、Kimi API + DeepSeek 浏览器）"
        )
    await send_reply_event(session_id, duration_msg, is_delta=True, is_new_round=True)
    await send_reply_event(session_id, "", is_complete=True)

    await send_progress_event(
        session_id=session_id,
        step="A4",
        step_name="AI答案抓取",
        progress=0.55,
        message=f"开始抓取 {len(questions)} 个问题的答案（{mode_label}）",
    )

    task_id = state.get("task_id")
    await _persist_task_progress(
        task_id,
        stage="A4",
        progress=0.55,
        message=f"开始抓取 {len(questions)} 个问题的答案（{mode_label}）",
        context="start_milestone",
    )

    fetch_results: list[dict[str, Any]] = []

    try:
        # Initialize fetchers based on fetch_mode
        from app.schemas.fetch import BrowserState

        # Cycle 3: If platform_filter is set, only initialize requested platforms
        _pf = set(platform_filter) if platform_filter else None

        # ── API clients (fast mode only) ──
        doubao_client = None
        hunyuan_client = None
        kimi_client = None

        if fetch_mode == "fast":
            from app.core.fetchers.api.doubao_client import DoubaoClient
            from app.core.fetchers.api.hunyuan_client import HunyuanClient

            try:
                if _pf is None or "doubao" in _pf:
                    doubao_client = DoubaoClient()
            except Exception as e:
                logger.warning("[A4] DoubaoClient init failed: %s", e)

            try:
                if _pf is None or "hunyuan" in _pf:
                    hunyuan_client = HunyuanClient()
            except Exception as e:
                logger.warning("[A4] Yuanbao client init failed: %s", e)

            try:
                if _pf is None or "kimi" in _pf:
                    from app.core.fetchers.api.kimi_client import KimiClient

                    kimi_client = KimiClient()
            except Exception as e:
                logger.warning("[A4] KimiClient init failed: %s", e)

        # ── Browser handlers ──
        # fast mode: DeepSeek only
        # full mode: all 4 platforms
        from app.core.playwright_installer import ensure_playwright_ready

        playwright_ok = await ensure_playwright_ready()

        # Reset circuit breakers at start of each A4 run so stale OPEN
        # state from a previous execution doesn't block new requests.
        from app.workflow.resilience import get_circuit_breaker as _get_cb

        for _p in ["deepseek", "kimi", "hunyuan", "doubao"]:
            _get_cb(_p).reset()

        # Track all browser clients for cleanup
        browser_clients: list[Any] = []

        deepseek_handler = None
        deepseek_browser_client = None
        kimi_browser_handler = None
        kimi_browser_client = None
        yuanbao_handler = None
        yuanbao_browser_client = None
        doubao_browser_handler = None
        doubao_browser_client = None

        if playwright_ok:
            # DeepSeek browser: always initialized (both modes)
            try:
                if _pf is None or "deepseek" in _pf:
                    deepseek_browser_client = _create_browser_client("deepseek", state)
                    deepseek_handler = _AIO_ANSWER_FETCH_TOOL.create_browser_handler(
                        platform="deepseek",
                        browser_client=deepseek_browser_client,
                        session_id=session_id,
                        run_id=state.get("run_id"),
                    )
                    browser_clients.append(deepseek_browser_client)
                    logger.info("[A4] DeepSeek browser handler initialized")

            except Exception as e:
                logger.warning("[A4] DeepSeek browser init failed: %s", e)

            # Additional browser handlers (full mode only)
            if fetch_mode == "full":
                try:
                    if _pf is None or "kimi" in _pf:
                        kimi_browser_client = _create_browser_client("kimi", state)
                        kimi_browser_handler = (
                            _AIO_ANSWER_FETCH_TOOL.create_browser_handler(
                                platform="kimi",
                                browser_client=kimi_browser_client,
                                session_id=session_id,
                                run_id=state.get("run_id"),
                            )
                        )
                        browser_clients.append(kimi_browser_client)
                        logger.info("[A4] Kimi browser handler initialized")

                except Exception as e:
                    logger.warning("[A4] Kimi browser init failed: %s", e)

                try:
                    if _pf is None or "hunyuan" in _pf:
                        yuanbao_browser_client = _create_browser_client(
                            "yuanbao", state
                        )
                        yuanbao_handler = _AIO_ANSWER_FETCH_TOOL.create_browser_handler(
                            platform="yuanbao",
                            browser_client=yuanbao_browser_client,
                            session_id=session_id,
                            run_id=state.get("run_id"),
                        )
                        browser_clients.append(yuanbao_browser_client)
                        logger.info("[A4] Yuanbao browser handler initialized")

                except Exception as e:
                    logger.warning("[A4] Yuanbao browser init failed: %s", e)

                try:
                    if _pf is None or "doubao" in _pf:
                        doubao_browser_client = _create_browser_client("doubao", state)
                        doubao_browser_handler = (
                            _AIO_ANSWER_FETCH_TOOL.create_browser_handler(
                                platform="doubao",
                                browser_client=doubao_browser_client,
                                session_id=session_id,
                                run_id=state.get("run_id"),
                            )
                        )
                        browser_clients.append(doubao_browser_client)
                        logger.info("[A4] Doubao browser handler initialized")

                except Exception as e:
                    logger.warning("[A4] Doubao browser init failed: %s", e)

        else:
            logger.warning("[A4] Playwright not ready, all browser handlers skipped")

        total = len(questions)

        try:
            question_results: dict[int, list[dict[str, Any]]] = {
                i: [] for i in range(total)
            }

            # =============================================================
            # Phase 1: API calls (fast mode only)
            # Each platform processes questions one at a time with delay;
            # different platforms run in parallel with each other.
            # =============================================================
            if fetch_mode == "fast":
                await send_progress_event(
                    session_id=session_id,
                    step="A4",
                    step_name="AI答案抓取",
                    progress=0.57,
                    message=f"正在通过 API 抓取：{total} 个问题 × 豆包、元宝、Kimi，批量并行抓取中...",
                )

                api_tasks = []
                api_task_map: list[tuple[int, str]] = []  # (question_idx, platform)
                for idx, question in enumerate(questions):
                    question_id = _question_id_from_state_question(question)
                    allowed_platforms = question_platform_targets.get(question_id)
                    q_text = question.get("text", "")
                    if doubao_client is not None and (
                        not allowed_platforms or "doubao" in allowed_platforms
                    ):
                        api_tasks.append(
                            _throttled_retry_fetch(
                                _fetch_from_doubao,
                                doubao_client,
                                q_text,
                                platform="doubao",
                                method="api",
                            )
                        )
                        api_task_map.append((idx, "doubao"))
                    if hunyuan_client is not None and (
                        not allowed_platforms or "hunyuan" in allowed_platforms
                    ):
                        api_tasks.append(
                            _throttled_retry_fetch(
                                _fetch_from_hunyuan,
                                hunyuan_client,
                                q_text,
                                platform="hunyuan",
                                method="api",
                            )
                        )
                        api_task_map.append((idx, "hunyuan"))
                    if kimi_client is not None and (
                        not allowed_platforms or "kimi" in allowed_platforms
                    ):
                        api_tasks.append(
                            _throttled_retry_fetch(
                                _fetch_from_kimi,
                                kimi_client,
                                q_text,
                                platform="kimi",
                                method="api",
                            )
                        )
                        api_task_map.append((idx, "kimi"))

                # Build active API platforms list and create progress tracker
                active_api_platforms = []
                if doubao_client is not None:
                    active_api_platforms.append("doubao")
                if hunyuan_client is not None:
                    active_api_platforms.append("hunyuan")
                if kimi_client is not None:
                    active_api_platforms.append("kimi")

                tracker = _ProgressTracker(
                    total_questions=total,
                    active_platforms=active_api_platforms,
                    session_id=session_id,
                    task_id=task_id,
                )

                # Wrap each task to report progress on completion
                tracked_tasks = [
                    _tracked_api_fetch(task, platform, tracker)
                    for task, (_q_idx, platform) in zip(api_tasks, api_task_map)
                ]
                api_all_results = await asyncio.gather(
                    *tracked_tasks, return_exceptions=True
                )

                # Organize API results by question index
                api_success_total = 0
                for (q_idx, platform), result in zip(api_task_map, api_all_results):
                    if isinstance(result, BaseException):
                        logger.error(
                            "[A4] API %s Q%d exception: %s", platform, q_idx + 1, result
                        )
                        question_results[q_idx].append(
                            _attach_aio_platform_packet(
                                {
                                    "platform": platform,
                                    "fetch_method": "api",
                                    "success": False,
                                    "error": str(result),
                                },
                                question=questions[q_idx],
                                request=aio_fetch_request,
                            )
                        )
                    else:
                        question_results[q_idx].append(
                            _attach_aio_platform_packet(
                                result,
                                question=questions[q_idx],
                                request=aio_fetch_request,
                            )
                        )
                        if result.get("success"):
                            api_success_total += 1

                logger.info(
                    "[A4] Phase 1 (API) done: %d/%d succeeded",
                    api_success_total,
                    len(api_tasks),
                )

                await send_progress_event(
                    session_id=session_id,
                    step="A4",
                    step_name="AI答案抓取",
                    progress=0.72,
                    message=_build_browser_phase_start_message(
                        fetch_mode,
                        platform_filter or list(PlatformConstants.SUPPORTED_PLATFORMS),
                        api_success_total=api_success_total,
                        api_task_count=len(api_tasks),
                    ),
                )
                await _persist_task_progress(
                    task_id,
                    stage="A4",
                    progress=0.72,
                    message=_build_browser_phase_start_message(
                        fetch_mode,
                        platform_filter or list(PlatformConstants.SUPPORTED_PLATFORMS),
                        api_success_total=api_success_total,
                        api_task_count=len(api_tasks),
                    ),
                    context="browser_phase_start_after_api",
                )
            else:
                # full mode: skip API entirely
                logger.info("[A4] Full mode — skipping Phase 1 (API)")
                await send_progress_event(
                    session_id=session_id,
                    step="A4",
                    step_name="AI答案抓取",
                    progress=0.57,
                    message=_build_browser_phase_start_message(
                        fetch_mode,
                        platform_filter or list(PlatformConstants.SUPPORTED_PLATFORMS),
                    ),
                )
                await _persist_task_progress(
                    task_id,
                    stage="A4",
                    progress=0.57,
                    message=_build_browser_phase_start_message(
                        fetch_mode,
                        platform_filter or list(PlatformConstants.SUPPORTED_PLATFORMS),
                    ),
                    context="browser_phase_start_full_mode",
                )

            # =============================================================
            # Phase 2: Browser platforms
            # Each browser processes questions sequentially (can't parallelize)
            # but different platforms run in parallel with each other.
            #
            # Progress calculation:
            # - Fast mode: browser phase = 0.72..0.95 (API already filled 0.57..0.72)
            # - Full mode: browser phase = 0.57..0.95 (no API phase)
            # A shared counter prevents parallel pipelines from overwriting each other.
            # =============================================================
            _browser_progress_base = 0.57 if fetch_mode == "full" else 0.72
            _browser_progress_range = 0.95 - _browser_progress_base
            _browser_shared_done: dict[str, int] = {}  # platform -> questions done
            # Shared partial results so global timeout can preserve completed work
            _pipeline_partial_results: dict[str, list[tuple[int, dict[str, Any]]]] = {}
            active_browser_pipeline_count = 1

            # =============================================================
            async def _browser_pipeline(
                handler,
                browser_client,
                platform: str,
                platform_name: str,
            ) -> list[tuple[int, dict[str, Any]]]:
                """Process all questions through one browser sequentially.

                Integrates Layer 3 circuit breaker: if breaker is OPEN
                the platform is skipped entirely (no wasted wait time).
                """
                from app.workflow.resilience import get_circuit_breaker

                breaker = get_circuit_breaker(platform)
                logger.info(
                    "[A4] %s browser pipeline started (breaker state: %s)",
                    platform_name,
                    breaker.state.value,
                )
                results: list[tuple[int, dict[str, Any]]] = []
                _pipeline_partial_results[platform] = (
                    results  # share reference for timeout recovery
                )
                for idx, question in enumerate(questions):
                    qid = _question_id_from_state_question(question)
                    allowed_platforms = question_platform_targets.get(qid)
                    q_text = question.get("text", "")
                    if allowed_platforms and platform not in allowed_platforms:
                        _browser_shared_done[platform] = idx + 1
                        continue

                    # Circuit breaker check
                    if not breaker.allow_request():
                        logger.info(
                            "[A4] %s circuit OPEN, skipping Q%d",
                            platform_name,
                            idx + 1,
                        )
                        results.append(
                            (
                                idx,
                                {
                                    "platform": platform,
                                    "platform_name": platform_name,
                                    "fetch_method": "browser",
                                    "success": False,
                                    "error": (
                                        f"平台 {platform_name} 暂时不可用（熔断保护）"
                                    ),
                                    "skipped_by_breaker": True,
                                },
                            )
                        )
                        continue

                    # First question uses extended timeout to allow for login flow
                    question_timeout = (
                        300.0 if idx == 0 else _get_browser_timeout(platform)
                    )
                    r = await _browser_fetch_with_timeout(
                        _fetch_from_browser,
                        handler,
                        q_text,
                        platform,
                        platform_name,
                        BrowserState,
                        question_id=qid,
                        timeout=question_timeout,
                        session_id=session_id,
                        user_id=(
                            str(state.get("user_id")) if state.get("user_id") else None
                        ),
                        run_id=state.get("run_id"),
                        question_count=total,
                        action_wait_timeout=_get_browser_action_wait_timeout(
                            platform, total
                        ),
                    )

                    # Update circuit breaker state — distinguish failure types
                    error_type = r.get("error_type", "")
                    stop_platform = bool(r.get("stop_platform"))
                    if r.get("success"):
                        breaker.record_success()
                    elif error_type in {
                        "user_skipped",
                        "user_action_timeout",
                        "resume_gate_failed",
                    }:
                        logger.info(
                            "[A4] %s stopped by user-action outcome on Q%d (%s)",
                            platform_name,
                            idx + 1,
                            error_type,
                        )
                    elif error_type == "rate_limit":
                        # Rate limit is not a platform fault — don't trip breaker
                        logger.warning(
                            "[A4] %s rate limited on Q%d, adding 30s cooldown",
                            platform_name,
                            idx + 1,
                        )
                        await asyncio.sleep(30)
                    elif error_type == "verify":
                        # CAPTCHA/verify challenge — stop this platform entirely
                        logger.warning(
                            "[A4] %s verify challenge on Q%d, stopping platform",
                            platform_name,
                            idx + 1,
                        )
                        if session_id:
                            await send_browser_state_event(
                                session_id=session_id,
                                platform=platform,
                                state="error",
                                message=f"{platform_name} 再次触发安全验证，本轮已跳过该平台并继续其他平台",
                                progress=0.7,
                                requires_action=False,
                            )
                            await send_reply_event(
                                session_id,
                                (
                                    f"**{platform_name}** 在恢复后再次触发安全验证，"
                                    "本轮无法继续自动抓取该平台。我会继续完成其他平台采集，"
                                    "并在后续报告中基于已成功的平台生成结果。"
                                ),
                                is_delta=True,
                                is_new_round=True,
                            )
                            await send_reply_event(session_id, "", is_complete=True)
                        breaker.record_failure()
                        breaker.record_failure()
                        breaker.record_failure()  # Force OPEN
                    else:
                        if _should_count_browser_failure_for_breaker(r):
                            breaker.record_failure()
                        else:
                            logger.info(
                                "[A4] %s soft browser failure on Q%d won't trip breaker (%s / %s)",
                                platform_name,
                                idx + 1,
                                error_type or "no_error_type",
                                str(r.get("error") or "").strip() or "no_error_message",
                            )

                    results.append((idx, r))

                    if stop_platform:
                        stop_reason = (
                            r.get("error") or f"{platform_name} 已停止本轮采集"
                        )
                        for remaining_idx in range(idx + 1, total):
                            results.append(
                                (
                                    remaining_idx,
                                    {
                                        "platform": platform,
                                        "platform_name": platform_name,
                                        "fetch_method": "browser",
                                        "success": False,
                                        "error": stop_reason,
                                        "error_type": error_type,
                                        "stop_platform": True,
                                        "skipped_by_user": bool(
                                            r.get("skipped_by_user")
                                        ),
                                    },
                                )
                            )
                        _browser_shared_done[platform] = total
                        total_browser_done = sum(_browser_shared_done.values())
                        total_browser_work = total * max(
                            active_browser_pipeline_count, 1
                        )
                        combined_progress = (
                            _browser_progress_base
                            + (total_browser_done / total_browser_work)
                            * _browser_progress_range
                        )
                        await send_progress_event(
                            session_id=session_id,
                            step="A4",
                            step_name="AI答案抓取",
                            progress=combined_progress,
                            message=f"{platform_name} 已停止本轮采集，继续其他平台",
                        )
                        await _persist_task_progress(
                            task_id,
                            stage="A4",
                            progress=combined_progress,
                            message=f"{platform_name} 已停止本轮采集，继续其他平台",
                            context=f"browser_stop_{platform}",
                        )
                        break

                    # Delay between browser questions to avoid rate limiting
                    if idx < len(questions) - 1:
                        browser_delay = PlatformConstants.PLATFORM_REQUEST_DELAYS.get(
                            platform, 3.0
                        )
                        await asyncio.sleep(browser_delay)

                    # Update shared progress counter across all pipelines
                    _browser_shared_done[platform] = idx + 1
                    total_browser_done = sum(_browser_shared_done.values())
                    # Total work = questions × number of active browser pipelines
                    total_browser_work = total * max(active_browser_pipeline_count, 1)
                    combined_progress = (
                        _browser_progress_base
                        + (total_browser_done / total_browser_work)
                        * _browser_progress_range
                    )
                    await send_progress_event(
                        session_id=session_id,
                        step="A4",
                        step_name="AI答案抓取",
                        progress=combined_progress,
                        message=f"{platform_name} {idx + 1}/{total} 完成",
                    )
                    await _persist_task_progress(
                        task_id,
                        stage="A4",
                        progress=combined_progress,
                        message=f"{platform_name} {idx + 1}/{total} 完成",
                        context=f"browser_progress_{platform}",
                    )
                return results

            # Only run browser pipelines for successfully initialized handlers
            # Each pipeline is wrapped with a global timeout to prevent indefinite blocking.
            async def _pipeline_with_global_timeout(
                handler,
                browser_client,
                platform: str,
                platform_name: str,
            ) -> list[tuple[int, dict[str, Any]]]:
                """Run _browser_pipeline capped at BROWSER_PIPELINE_TIMEOUT seconds total."""
                pipeline_timeout = _get_browser_pipeline_timeout(platform, total)
                try:
                    return await asyncio.wait_for(
                        _browser_pipeline(
                            handler, browser_client, platform, platform_name
                        ),
                        timeout=pipeline_timeout,
                    )
                except asyncio.TimeoutError:
                    # Preserve partial results that completed before timeout
                    partial = _pipeline_partial_results.get(platform, [])
                    completed_indices = {idx for idx, _ in partial}
                    completed_ok = sum(1 for _, r in partial if r.get("success"))
                    logger.warning(
                        "[A4] %s pipeline hit global timeout (%.0fs), preserving %d/%d completed (%d success)",
                        platform_name,
                        pipeline_timeout,
                        len(partial),
                        total,
                        completed_ok,
                    )
                    # Add failures only for questions not yet processed
                    for i in range(total):
                        if i not in completed_indices:
                            partial.append(
                                (
                                    i,
                                    {
                                        "platform": platform,
                                        "platform_name": platform_name,
                                        "fetch_method": "browser",
                                        "success": False,
                                        "error": f"平台整体超时（{pipeline_timeout:.0f}s），跳过剩余问题",
                                    },
                                )
                            )
                    return partial

            browser_tasks = []
            browser_task_platforms = []
            requested_browser_platforms: list[str] = []

            # DeepSeek browser: always (both modes)
            deepseek_requested = _pf is None or "deepseek" in _pf
            if deepseek_requested:
                requested_browser_platforms.append("deepseek")

            if deepseek_handler is not None and deepseek_browser_client is not None:
                logger.info("[A4] Phase 2: DeepSeek browser pipeline queued")
                browser_tasks.append(
                    _pipeline_with_global_timeout(
                        deepseek_handler,
                        deepseek_browser_client,
                        "deepseek",
                        "DeepSeek",
                    )
                )
                browser_task_platforms.append("deepseek")
            elif deepseek_requested:
                logger.warning(
                    "[A4] Phase 2: DeepSeek skipped (handler=%s, client=%s)",
                    deepseek_handler,
                    deepseek_browser_client,
                )

            # Additional browsers (full mode only)
            if fetch_mode == "full":
                kimi_requested = _pf is None or "kimi" in _pf
                yuanbao_requested = _pf is None or "hunyuan" in _pf
                doubao_requested = _pf is None or "doubao" in _pf

                if kimi_requested:
                    requested_browser_platforms.append("kimi")
                if kimi_browser_handler is not None and kimi_browser_client is not None:
                    logger.info("[A4] Phase 2: Kimi browser pipeline queued")
                    browser_tasks.append(
                        _pipeline_with_global_timeout(
                            kimi_browser_handler, kimi_browser_client, "kimi", "Kimi"
                        )
                    )
                    browser_task_platforms.append("kimi")
                elif kimi_requested:
                    logger.warning(
                        "[A4] Phase 2: Kimi skipped (handler=%s, client=%s)",
                        kimi_browser_handler,
                        kimi_browser_client,
                    )

                if yuanbao_requested:
                    requested_browser_platforms.append("hunyuan")
                if yuanbao_handler is not None and yuanbao_browser_client is not None:
                    logger.info("[A4] Phase 2: Yuanbao browser pipeline queued")
                    browser_tasks.append(
                        _pipeline_with_global_timeout(
                            yuanbao_handler, yuanbao_browser_client, "hunyuan", "元宝"
                        )
                    )
                    browser_task_platforms.append("hunyuan")
                elif yuanbao_requested:
                    logger.warning(
                        "[A4] Phase 2: Yuanbao skipped (handler=%s, client=%s)",
                        yuanbao_handler,
                        yuanbao_browser_client,
                    )

                if doubao_requested:
                    requested_browser_platforms.append("doubao")
                if (
                    doubao_browser_handler is not None
                    and doubao_browser_client is not None
                ):
                    logger.info("[A4] Phase 2: Doubao browser pipeline queued")
                    browser_tasks.append(
                        _pipeline_with_global_timeout(
                            doubao_browser_handler,
                            doubao_browser_client,
                            "doubao",
                            "豆包",
                        )
                    )
                    browser_task_platforms.append("doubao")
                elif doubao_requested:
                    logger.warning(
                        "[A4] Phase 2: Doubao skipped (handler=%s, client=%s)",
                        doubao_browser_handler,
                        doubao_browser_client,
                    )

            if browser_tasks:
                active_browser_pipeline_count = max(len(browser_task_platforms), 1)
                browser_batch_timeout = (
                    max(
                        _get_browser_pipeline_timeout(platform, total)
                        for platform in browser_task_platforms
                    )
                    + 30.0
                )
                logger.info(
                    "[A4] Phase 2: Starting %d browser pipeline(s) with hard batch timeout %.0fs...",
                    len(browser_tasks),
                    browser_batch_timeout,
                )
                browser_all_results = await _gather_browser_tasks(
                    browser_tasks,
                    timeout_seconds=browser_batch_timeout,
                )

                for i, br in enumerate(browser_all_results):
                    if isinstance(br, BaseException):
                        logger.error(
                            "[A4] Pipeline[%d] %s: %s: %s",
                            i,
                            browser_task_platforms[i],
                            type(br).__name__,
                            br,
                        )
                    else:
                        ok = sum(1 for _, r in br if r.get("success"))
                        logger.info(
                            "[A4] Pipeline[%d] %s: %d/%d success",
                            i,
                            browser_task_platforms[i],
                            ok,
                            len(br),
                        )
            else:
                logger.warning(
                    "[A4] Phase 2: No browser tasks to run (requested=%s)",
                    requested_browser_platforms,
                )

                browser_all_results = []

            # Merge browser results into question_results
            browser_success_total = 0
            for browser_batch, platform in zip(
                browser_all_results, browser_task_platforms
            ):
                if isinstance(browser_batch, BaseException):
                    logger.warning(
                        "[A4] Browser %s pipeline failed: %s", platform, browser_batch
                    )
                    for idx in range(total):
                        question_id = _question_id_from_state_question(questions[idx])
                        allowed_platforms = question_platform_targets.get(question_id)
                        if allowed_platforms and platform not in allowed_platforms:
                            continue
                        question_results[idx].append(
                            _attach_aio_platform_packet(
                                {
                                    "platform": platform,
                                    "fetch_method": "browser",
                                    "success": False,
                                    "error": str(browser_batch),
                                },
                                question=questions[idx],
                                request=aio_fetch_request,
                            )
                        )
                else:
                    for q_idx, r in browser_batch:
                        enriched_result = _attach_aio_platform_packet(
                            r,
                            question=questions[q_idx],
                            request=aio_fetch_request,
                        )
                        question_results[q_idx].append(enriched_result)
                        if _fetch_result_has_success(enriched_result):
                            browser_success_total += 1

            logger.info(
                "[A4] Phase 2 (Browser) done: %d succeeded", browser_success_total
            )

            # Build final fetch_results list
            for idx, question in enumerate(questions):
                question_id = question.get("id", f"Q{idx}")
                question_text = question.get("text", "")
                platform_results = question_results[idx]
                q_success = sum(
                    1
                    for result in platform_results
                    if _fetch_result_has_success(result)
                )
                logger.info(
                    "[A4] Q%d/%d: %d platforms succeeded", idx + 1, total, q_success
                )
                fetch_results.append(
                    {
                        "question_id": question_id,
                        "question_text": question_text,
                        "platform_results": platform_results,
                        "aio_platform_packets": _collect_aio_platform_packets(
                            platform_results
                        ),
                    }
                )

        finally:
            for bc in browser_clients:
                try:
                    await bc.close()
                except BaseException as e:
                    logger.debug("[A4] Browser client close failed: %s", e)

        # When platform_filter is active, only preserve old platform results for
        # the same question set. A fresh scenario run can also use a filtered
        # platform list, but it must not inherit panorama fetch rows.
        final_fetch_results = fetch_results
        baseline = state.get("preserved_fetch_results")
        pair_targeted_merge = bool(question_platform_targets)
        if (
            (platform_filter or pair_targeted_merge)
            and baseline is None
            and state.get("fetch_results")
        ):
            selected_platforms = (
                {str(platform).strip().lower() for platform in platform_filter}
                if platform_filter
                else None
            )
            baseline = _derive_preserved_fetch_results(
                current_questions=questions,
                existing_fetch_results=state.get("fetch_results") or [],
                selected_platforms=selected_platforms,
                question_platform_targets=question_platform_targets or None,
            )
        scoped_merge_active = bool(
            (platform_filter or pair_targeted_merge) and baseline
        )
        if scoped_merge_active:
            baseline_map: dict[str, dict[str, Any]] = {}
            for baseline_entry in baseline:
                question_id = baseline_entry.get("question_id", "")
                if question_id:
                    baseline_map[question_id] = baseline_entry

            merged_results: list[dict[str, Any]] = []
            for fetch_result in fetch_results:
                question_id = fetch_result.get("question_id", "")
                new_platform_results = fetch_result.get("platform_results", []) or []
                if question_id in baseline_map:
                    old_platform_results = (
                        baseline_map.pop(question_id).get("platform_results", []) or []
                    )
                    combined_platform_results = (
                        new_platform_results + old_platform_results
                    )
                    merged_results.append(
                        {
                            "question_id": question_id,
                            "question_text": fetch_result.get("question_text", ""),
                            "platform_results": combined_platform_results,
                            "aio_platform_packets": _collect_aio_platform_packets(
                                combined_platform_results
                            ),
                        }
                    )
                else:
                    merged_results.append(fetch_result)

            for _, baseline_entry in baseline_map.items():
                merged_results.append(baseline_entry)

            final_fetch_results = merged_results
            logger.info(
                "[A4] Merged %d new + %d baseline = %d total results",
                len(fetch_results),
                len(baseline),
                len(final_fetch_results),
            )

        merge_validation = validate_scoped_fetch_merge(
            platform_filter=platform_filter,
            preserved_results=baseline,
            merged_results=final_fetch_results,
        )
        if not merge_validation.passed:
            raise RuntimeError(merge_validation.reason)

        projected_fetch_results = final_fetch_results
        authoritative_projection: dict[str, Any] | None = None
        task_run_id = state.get("run_id")
        entity_id = state.get("entity_id")
        user_id = state.get("user_id")
        if task_id and task_run_id and user_id:
            try:
                from uuid import UUID as _UUID

                from app.core.database import AsyncSessionLocal
                from app.services.fetch_run_platform_state_service import (
                    FetchRunPlatformStateService,
                )

                async with AsyncSessionLocal() as db:
                    state_service = FetchRunPlatformStateService(db)
                    rows = await state_service.sync_fetch_results(
                        task_run_id=_UUID(str(task_run_id)),
                        task_id=_UUID(str(task_id)),
                        session_id=_UUID(str(session_id)) if session_id else None,
                        entity_id=_UUID(str(entity_id)) if entity_id else None,
                        user_id=_UUID(str(user_id)),
                        fetch_results=final_fetch_results,
                    )
                    authoritative_projection = state_service.build_summary_projection(
                        rows
                    )
                    projected_fetch_results = (
                        authoritative_projection.get("fetch_results")
                        or final_fetch_results
                    )
                    await db.commit()
            except Exception as authoritative_err:
                logger.warning(
                    "[A4] Authoritative platform-state sync failed: %s",
                    authoritative_err,
                )

        # Calculate downstream status from the authoritative projection. The legacy
        # platform_results shape remains in artifacts for compatibility only.
        packet_summary = _build_aio_packet_fetch_summary(
            projected_fetch_results,
        )
        total_fetches = int(packet_summary["total_fetches"])
        successful_fetches = int(packet_summary["successful_fetches"])
        successful_platforms = set(packet_summary["successful_platforms"])
        platform_fetch_stats = packet_summary["platform_fetch_stats"]
        platform_statuses = dict(packet_summary["platform_statuses"])
        if authoritative_projection:
            projected_statuses = (
                authoritative_projection.get("platform_status", {}).get(
                    "platform_statuses"
                )
                or {}
            )
            if projected_statuses:
                platform_statuses = dict(projected_statuses)

        # When platform_filter is set, total is the filtered set, not all platforms
        total_platforms = len(aio_fetch_request.platforms)
        fail_count = total_platforms - len(successful_platforms)

        # When platform_filter is active, adjust the minimum
        # threshold to the number of requested platforms (min 1), so that a
        # single-platform scoped fetch doesn't trigger a spurious degradation notice.
        effective_min = (
            min(MIN_PLATFORMS_REQUIRED, total_platforms)
            if platform_filter
            else MIN_PLATFORMS_REQUIRED
        )
        completion_decision = decide_a4_completion_policy(
            success_count=len(successful_platforms),
            fail_count=fail_count,
            effective_min=effective_min,
            platform_filter=platform_filter,
        )

        if len(successful_platforms) < effective_min:
            logger.warning(
                "[A4] Only %d platform(s) succeeded (%s), minimum %d required",
                len(successful_platforms),
                ", ".join(successful_platforms) if successful_platforms else "none",
                effective_min,
            )
            if len(successful_platforms) == 0:
                # Zero platforms -- hard error
                await send_error_event(
                    session_id,
                    "A4",
                    "所有平台数据获取均失败，请检查网络连接后重试",
                    recoverable=True,
                )
            else:
                logger.info(
                    "[A4] %d platform(s) succeeded but below threshold %d; "
                    "skipping chat degradation notice and relying on fetch artifact",
                    len(successful_platforms),
                    effective_min,
                )
        elif fail_count > 0:
            # Partial platform failures are already reflected in the authoritative
            # fetch artifact. Avoid emitting a second coarse-grained chat notice
            # that can conflict with the per-platform success counters users see
            # in the artifact itself.
            logger.info(
                "[A4] Partial platform failures detected (%d success / %d fail); "
                "skipping duplicate chat degradation notice and relying on fetch artifact",
                len(successful_platforms),
                fail_count,
            )

        await send_progress_event(
            session_id=session_id,
            step="A4",
            step_name="AI答案抓取",
            progress=1.0,
            message=f"抓取完成: {successful_fetches}/{total_fetches} 成功（{len(successful_platforms)} 个平台有数据）",
            status="completed",
        )

        platform_summary = []
        for platform, stats in platform_fetch_stats.items():
            success_rate = (
                (stats["completed"] / stats["total"] * 100) if stats["total"] > 0 else 0
            )
            display_name = PlatformConstants.PLATFORM_DISPLAY_NAMES.get(
                platform,
                platform,
            )
            platform_summary.append(
                f"- **{display_name}**: {stats['completed']}/{stats['total']} 成功 ({success_rate:.0f}%)"
            )

        # Save and send artifact to Canvas
        from app.workflow.events import save_and_send_artifact

        artifact_key = f"{session_id}_fetchResults_a4"
        artifact_message_id = await save_and_send_artifact(
            session_id=session_id,
            output_type="fetchResults",
            title="AI答案抓取结果",
            artifact_key=artifact_key,
            data={
                "fetchResults": projected_fetch_results,
                "platformStatus": (
                    authoritative_projection.get("platform_status", {})
                    if authoritative_projection
                    else {}
                ),
                "timingSummary": (
                    authoritative_projection.get("timing_summary", {})
                    if authoritative_projection
                    else {}
                ),
            },
        )
        artifact_validation = validate_artifact_writeback(
            gate_name="artifact_writeback_gate",
            artifact_message_id=artifact_message_id,
            artifact_key=artifact_key,
            artifact_kind="fetch_results",
            metadata={
                "step": "A4",
                "success_count": len(successful_platforms),
                "fail_count": fail_count,
                "retry_failed_only": retry_failed_only,
                "scoped_merge_active": scoped_merge_active,
            },
        )
        observation = _build_a4_completion_observation(
            projected_fetch_results=projected_fetch_results,
            completion_decision=completion_decision,
            artifact_validation=artifact_validation,
            retry_failed_only=retry_failed_only,
            scoped_merge_active=scoped_merge_active,
            question_targets=question_targets,
            successful_fetches=successful_fetches,
            total_fetches=total_fetches,
            fail_count=fail_count,
            platform_statuses=platform_statuses,
        )
        detailed_response = _build_a4_completion_response(
            total_fetches=total_fetches,
            successful_fetches=successful_fetches,
            platform_summary=platform_summary,
            observation=observation,
        )

        from app.workflow.events import send_tpaor_event

        await send_tpaor_event(
            session_id, "response", detailed_response, is_complete=True
        )
        if task_id and task_run_id:
            try:
                from uuid import UUID as _UUID

                from app.core.database import AsyncSessionLocal
                from app.services.fetch_run_platform_state_service import (
                    FetchRunPlatformStateService,
                )

                async with AsyncSessionLocal() as db:
                    state_service = FetchRunPlatformStateService(db)
                    await state_service.mark_artifact_write_status(
                        task_run_id=_UUID(str(task_run_id)),
                        status="written" if artifact_validation.passed else "failed",
                    )
                    await db.commit()
            except Exception as artifact_status_err:
                logger.warning(
                    "[A4] Failed to mark fetch artifact write status: %s",
                    artifact_status_err,
                )

        merge_validation_update = build_validation_result_update(
            state, merge_validation
        )
        artifact_validation_state = {**state, **merge_validation_update}
        artifact_validation_update = build_validation_result_update(
            artifact_validation_state,
            artifact_validation,
        )

        if not artifact_validation.passed:
            artifact_failure_message = (
                "答案抓取结果已生成，但官方结果写回失败，当前不能继续生成分析报告。"
            )
            await send_error_event(
                session_id,
                "A4",
                artifact_failure_message,
                recoverable=True,
            )
            decision_update = build_harness_decision_update(
                {**artifact_validation_state, **artifact_validation_update},
                build_harness_decision(
                    decision_type="retry_step",
                    reason=artifact_validation.reason,
                    recoverable=True,
                    metadata={
                        "step": "A4",
                        "blocker_code": "artifact_writeback_failed",
                        "artifact_key": artifact_key,
                    },
                ),
            )
            return Command(
                update={
                    "a4_completion_observation": observation,
                    "current_step": "A4",
                    "execution_status": "error",
                    "error_info": {
                        "step": "A4",
                        "error": artifact_failure_message,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                    **merge_validation_update,
                    **artifact_validation_update,
                    **decision_update,
                }
            )

        canonical_result = _build_a4_canonical_result(
            projected_fetch_results=projected_fetch_results,
            authoritative_projection=authoritative_projection,
            artifact_message_id=artifact_message_id,
            artifact_key=artifact_key,
            artifact_validation=artifact_validation,
            completion_decision=completion_decision,
            observation=observation,
        )

        # Write A4 materials into Knowledge Workspace for future retrieval.
        try:
            from app.core.database import AsyncSessionLocal
            from app.services.knowledge_workspace_service import (
                KnowledgeWorkspaceService,
            )

            async with AsyncSessionLocal() as db:
                knowledge_service = KnowledgeWorkspaceService(db)
                await knowledge_service.ingest_a4_facts(
                    entity_id=state.get("entity_id"),
                    session_id=session_id,
                    task_id=task_id,
                    run_id=state.get("run_id"),
                    brand_profile=brand_profile,
                    fetch_results=canonical_result["fetch_results"],
                )
        except Exception as knowledge_err:
            logger.warning("[A4] Knowledge write-back failed: %s", knowledge_err)

        # Task milestone: A4 completed (Cycle 3, Module 1)
        if task_id:
            try:
                from app.core.database import AsyncSessionLocal
                from app.services.task_service import TaskService
                from uuid import UUID as _UUID

                async with AsyncSessionLocal() as db:
                    ts = TaskService(db)
                    await ts.update_progress(
                        _UUID(task_id),
                        stage="A4",
                        progress=0.60,
                        message=f"抓取完成: {successful_fetches}/{total_fetches} 成功",
                    )
                    await ts.append_stage_result(
                        _UUID(task_id),
                        {
                            "stage": "A4",
                            "stage_name": "数据抓取",
                            "result_type": "platform_status",
                            "data": {
                                "total_fetches": total_fetches,
                                "successful_fetches": successful_fetches,
                                "platforms": list(successful_platforms),
                                "platform_states": (
                                    authoritative_projection.get(
                                        "platform_status", {}
                                    ).get("platforms", [])
                                    if authoritative_projection
                                    else list(successful_platforms)
                                ),
                            },
                        },
                    )
            except Exception as te:
                logger.warning("[A4] TaskService milestone failed: %s", te)

        update_dict: dict[str, Any] = {
            "a4_canonical_result": canonical_result,
            "a4_completion_observation": observation,
            "fetch_recovery_plan": dict(observation.get("recovery_plan") or {}),
            "fetch_results": canonical_result["fetch_results"],
            "current_step": "A4",
            "progress": 0.6,
        }
        # Clear platform_filter after use; scoped reruns should deterministically
        # reuse the official canonical result instead of stale transient filters.
        if platform_filter or pair_targeted_merge:
            update_dict["platform_filter"] = None
            update_dict["preserved_fetch_results"] = None

        if len(successful_platforms) == 0:
            update_dict["error_info"] = {
                "step": "A4",
                "error": "所有平台数据获取均失败",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        skill_update = build_skill_result_update(
            state,
            skill_key=state.get("current_skill"),
            tool_name="answer_fetch",
            status=(
                "degraded"
                if completion_decision.decision_type == "degraded_continue"
                else "completed"
            ),
            summary=str(observation.get("summary") or "答案抓取已完成。"),
            executor_ref="a4_answer_fetch",
            metadata={
                "artifact_message_id": artifact_message_id,
                "artifact_key": artifact_key,
                "success_count": len(successful_platforms),
                "fail_count": fail_count,
                "requires_user_decision": bool(
                    observation.get("requires_user_decision")
                ),
                "followup_options": list(observation.get("followup_options") or []),
                "retry_failed_only": retry_failed_only,
                "scoped_merge_active": scoped_merge_active,
            },
        )
        update_dict.update(skill_update)
        update_dict.update(merge_validation_update)
        update_dict.update(artifact_validation_update)
        update_dict.update(
            build_harness_decision_update(
                {
                    **artifact_validation_state,
                    **artifact_validation_update,
                    **update_dict,
                },
                completion_decision,
            )
        )

        return Command(update=update_dict)

    except Exception as e:
        logger.exception("[A4] Top-level exception: %s", e)
        await send_error_event(session_id, "A4", str(e), recoverable=True)

        # Task milestone: A4 failed
        task_id = state.get("task_id")
        if task_id:
            try:
                from app.core.database import AsyncSessionLocal
                from app.services.fetch_run_platform_state_service import (
                    FetchRunPlatformStateService,
                )
                from app.services.task_service import TaskService
                from uuid import UUID as _UUID

                async with AsyncSessionLocal() as db:
                    if state.get("run_id"):
                        state_service = FetchRunPlatformStateService(db)
                        await state_service.mark_artifact_write_status(
                            task_run_id=_UUID(str(state.get("run_id"))),
                            status="failed",
                        )
                    task_svc = TaskService(db)
                    await task_svc.fail_task(
                        _UUID(task_id),
                        error_message=str(e),
                        error_stage="A4",
                        run_id=(
                            _UUID(state.get("run_id")) if state.get("run_id") else None
                        ),
                    )
            except Exception as te:
                logger.warning("[A4] TaskService fail_task failed: %s", te)

        return Command(
            update={
                "a4_completion_observation": None,
                "error_info": {
                    "step": "A4",
                    "error": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                "current_step": "A4",
                "execution_status": "error",
                **build_harness_decision_update(
                    state,
                    build_harness_decision(
                        decision_type="retry_step",
                        reason=str(e),
                        recoverable=True,
                        metadata={"step": "A4", "blocker_code": "runtime_exception"},
                    ),
                ),
            },
        )


async def _fetch_from_doubao(client, question: str) -> dict[str, Any]:
    """Fetch answer from Doubao."""
    start_time = datetime.now(timezone.utc)

    try:
        response = await client.ask_with_search(question)
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        answer_text = response.answer_text

        if not answer_text or not answer_text.strip():
            logger.warning(
                "[A4] doubao returned empty answer for question: %s", question[:60]
            )
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
            },
            "citations": [ref.model_dump() for ref in response.search_references],
            "duration": duration,
        }
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            raise  # Let _retry_fetch handle 429 with proper backoff
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.warning(
            "[A4] doubao exception: %s(%s) for question: %s",
            type(e).__name__,
            e,
            question[:60],
        )
        return {
            "platform": "doubao",
            "platform_name": "豆包",
            "fetch_method": "api",
            "success": False,
            "error": f"{type(e).__name__}: {e}" if str(e) else type(e).__name__,
            "duration": duration,
        }
    except Exception as e:
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.warning(
            "[A4] doubao exception: %s(%s) for question: %s",
            type(e).__name__,
            e,
            question[:60],
        )
        return {
            "platform": "doubao",
            "platform_name": "豆包",
            "fetch_method": "api",
            "success": False,
            "error": f"{type(e).__name__}: {e}" if str(e) else type(e).__name__,
            "duration": duration,
        }


async def _fetch_from_hunyuan(client, question: str) -> dict[str, Any]:
    """Fetch answer from Yuanbao."""
    start_time = datetime.now(timezone.utc)

    try:
        response = await client.ask_with_search(question)
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        answer_text = response.answer_text

        if not answer_text or not answer_text.strip():
            logger.warning(
                "[A4] hunyuan returned empty answer for question: %s", question[:60]
            )
            return {
                "platform": "hunyuan",
                "platform_name": "元宝",
                "fetch_method": "api",
                "success": False,
                "error": "empty answer from API",
                "duration": duration,
            }

        return {
            "platform": "hunyuan",
            "platform_name": "元宝",
            "fetch_method": "api",
            "success": True,
            "answer": {
                "content": answer_text,
                "word_count": len(answer_text.split()),
            },
            "citations": [ref.model_dump() for ref in response.search_references],
            "duration": duration,
        }
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            raise
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        return {
            "platform": "hunyuan",
            "platform_name": "元宝",
            "fetch_method": "api",
            "success": False,
            "error": str(e),
            "duration": duration,
        }
    except Exception as e:
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        return {
            "platform": "hunyuan",
            "platform_name": "元宝",
            "fetch_method": "api",
            "success": False,
            "error": str(e),
            "duration": duration,
        }


async def _fetch_from_kimi(client, question: str) -> dict[str, Any]:
    """Fetch answer from Kimi (Moonshot API)."""
    start_time = datetime.now(timezone.utc)

    try:
        response = await client.ask_with_search(question)
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        answer_text = response.answer_text

        if not answer_text or not answer_text.strip():
            logger.warning(
                "[A4] kimi returned empty answer for question: %s", question[:60]
            )
            return {
                "platform": "kimi",
                "platform_name": "Kimi",
                "fetch_method": "api",
                "success": False,
                "error": "empty answer from API",
                "duration": duration,
            }

        return {
            "platform": "kimi",
            "platform_name": "Kimi",
            "fetch_method": "api",
            "success": True,
            "answer": {
                "content": answer_text,
                "word_count": len(answer_text.split()),
            },
            "citations": [ref.model_dump() for ref in response.search_references],
            "duration": duration,
        }
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            raise
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.warning(
            "[A4] kimi exception: %s(%s) for question: %s",
            type(e).__name__,
            e,
            question[:60],
        )
        return {
            "platform": "kimi",
            "platform_name": "Kimi",
            "fetch_method": "api",
            "success": False,
            "error": f"{type(e).__name__}: {e}" if str(e) else type(e).__name__,
            "duration": duration,
        }
    except Exception as e:
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.warning(
            "[A4] kimi exception: %s(%s) for question: %s",
            type(e).__name__,
            e,
            question[:60],
        )
        return {
            "platform": "kimi",
            "platform_name": "Kimi",
            "fetch_method": "api",
            "success": False,
            "error": f"{type(e).__name__}: {e}" if str(e) else type(e).__name__,
            "duration": duration,
        }


def _get_handler_page_url(handler: Any) -> str | None:
    client = getattr(handler, "client", None)
    page = getattr(client, "page", None)
    if page is None:
        return None
    try:
        page_url = getattr(page, "url", None)
    except Exception:
        return None
    return page_url if isinstance(page_url, str) and page_url.strip() else None


async def _fetch_from_browser(
    handler,
    question: str,
    platform: str,
    platform_name: str,
    browser_state,
    question_id: str | None = None,
    session_id: str = "",
    user_id: str | None = None,
    run_id: str | None = None,
    question_count: int = 1,
    action_wait_timeout: int | None = None,
    _is_retry: bool = False,
    _verify_recovery_count: int = 0,
    _auth_state_updated: bool = False,
) -> dict[str, Any]:
    start_time = datetime.now(timezone.utc)
    result_data = None
    error_message = None
    error_type = ""
    failure_layer = None
    failure_reason = None
    execution_stage = None
    retryable = False
    needs_handoff = False
    evidence_ref = None
    max_verify_recoveries = 3
    pending_action: PendingBrowserAction | None = None
    resolved_action_wait_timeout = (
        action_wait_timeout
        or _get_browser_action_wait_timeout(platform, question_count)
    )

    try:
        setattr(handler, "_current_question_id", question_id)
        setattr(handler, "_current_question_text", question)
        async for event in handler.fetch(question):
            if event.state == browser_state.WAITING_FOR_LOGIN and session_id:
                request_id = await emit_browser_action_handoff(
                    session_id=session_id,
                    platform=platform,
                    state=event.state.value,
                    action_type=event.action_type or "login",
                    message=event.message,
                    action_hint=event.action_hint or event.message,
                    progress=event.progress,
                    reply_markdown=(
                        f"**{platform_name}** 需要登录\n\n"
                        "请在浏览器窗口中完成登录。完成后回到聊天卡片点击“我已完成”，我会继续接管抓取。"
                    ),
                    run_id=run_id,
                    handler=handler,
                    user_id=user_id,
                    target_url=getattr(handler, "URL", None),
                )
                pending_action = PendingBrowserAction(
                    request_id=request_id,
                    action_type=event.action_type or "login",
                    success_message=f"{platform_name} 登录已完成，正在继续抓取当前问题",
                    timeout_message=f"{platform_name} 登录未完成或等待超时，本轮将跳过该平台",
                    timeout_error_type="user_action_timeout",
                )
                break

            if event.state == browser_state.WAITING_FOR_MODAL and session_id:
                request_id = await emit_browser_action_handoff(
                    session_id=session_id,
                    platform=platform,
                    state=event.state.value,
                    action_type=event.action_type or "modal",
                    message=event.message,
                    action_hint=event.action_hint or event.message,
                    progress=event.progress,
                    reply_markdown=(
                        f"**{platform_name}** 页面弹窗需要确认\n\n"
                        "请在浏览器中关闭弹窗或同意协议。完成后回到聊天卡片点击“我已完成”，我会继续接管抓取。"
                    ),
                    run_id=run_id,
                    handler=handler,
                    user_id=user_id,
                    target_url=getattr(handler, "URL", None),
                )
                pending_action = PendingBrowserAction(
                    request_id=request_id,
                    action_type=event.action_type or "modal",
                    success_message=f"{platform_name} 弹窗已处理，正在继续抓取当前问题",
                    timeout_message=f"{platform_name} 弹窗未处理完成，本轮将跳过该平台",
                    timeout_error_type="modal_timeout",
                )
                break

            if event.state == browser_state.ERROR:
                error_message = event.message or event.error or "抓取失败"
                if event.error_type:
                    error_type = event.error_type
                if event.failure_layer:
                    failure_layer = event.failure_layer
                if event.failure_reason:
                    failure_reason = event.failure_reason
                if event.execution_stage:
                    execution_stage = event.execution_stage
                if event.retryable is not None:
                    retryable = bool(event.retryable)
                if event.needs_handoff is not None:
                    needs_handoff = bool(event.needs_handoff)
                if isinstance(event.evidence_ref, dict):
                    evidence_ref = event.evidence_ref

            if event.state == browser_state.COMPLETED and event.data:
                result_data = event.data

    except Exception:
        raise

    duration = (datetime.now(timezone.utc) - start_time).total_seconds()

    if (
        result_data
        and result_data.answer_text
        and len(result_data.answer_text.strip()) >= 10
    ):
        answer_text = result_data.answer_text
        return {
            "platform": platform,
            "platform_name": platform_name,
            "fetch_method": "browser",
            "success": True,
            "answer": {
                "content": answer_text,
                "word_count": len(answer_text.split()),
            },
            "citations": [ref.model_dump() for ref in result_data.search_references],
            "auth_state_updated": _auth_state_updated,
            "duration": duration,
        }

    async def _retry_browser_fetch(
        *,
        verify_recovery_increment: bool = False,
        auth_state_updated: bool = False,
    ) -> dict[str, Any]:
        return await _fetch_from_browser(
            handler,
            question,
            platform,
            platform_name,
            browser_state,
            question_id=question_id,
            session_id=session_id,
            user_id=user_id,
            run_id=run_id,
            question_count=question_count,
            action_wait_timeout=resolved_action_wait_timeout,
            _is_retry=True,
            _verify_recovery_count=_verify_recovery_count
            + (1 if verify_recovery_increment else 0),
            _auth_state_updated=_auth_state_updated or auth_state_updated,
        )

    recovery_result = await handle_browser_failure(
        handler=handler,
        platform=platform,
        platform_name=platform_name,
        question=question,
        question_id=question_id,
        session_id=session_id,
        user_id=user_id,
        run_id=run_id,
        pending_action=pending_action,
        error_message=error_message,
        error_type=error_type,
        duration=(datetime.now(timezone.utc) - start_time).total_seconds(),
        question_count=question_count,
        timeout=resolved_action_wait_timeout,
        is_retry=_is_retry,
        verify_recovery_count=_verify_recovery_count,
        max_verify_recoveries=max_verify_recoveries,
        auth_state_updated=_auth_state_updated,
        should_defer_surface_open=_should_defer_aio_takeover_open,
        emit_handoff=emit_browser_action_handoff,
        wait_for_outcome=wait_for_browser_action_outcome,
        resume_action=resume_browser_action,
        send_browser_state=send_browser_state_event,
        send_reply=send_reply_event,
        capture_evidence=_capture_browser_failure_evidence,
        build_failure_result=_build_browser_failure_result,
        retry_fetch=_retry_browser_fetch,
    )
    if recovery_result is not None:
        return recovery_result

    stop_platform = error_type in {
        "user_skipped",
        "user_action_timeout",
        "resume_gate_failed",
        "modal_timeout",
    }
    return _build_browser_failure_result(
        platform=platform,
        platform_name=platform_name,
        error=error_message or "抓取失败",
        error_type=error_type or "parser_error",
        duration=duration,
        failure_reason=failure_reason or error_type or "parser_error",
        execution_stage=execution_stage or "fetch_loop",
        retryable=retryable,
        needs_handoff=needs_handoff,
        failure_layer=failure_layer or "executor",
        evidence_ref=evidence_ref,
        stop_platform=stop_platform,
        skipped_by_user=error_type == "user_skipped",
    )
