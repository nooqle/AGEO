"""A4 Node: Answer Fetching from AI Platforms.

This module contains the A4 node implementation for fetching answers
from various AI platforms (Doubao, Yuanbao, Kimi, DeepSeek, etc.)

Optimizations:
- Fast mode resolves API/browser paths from the active configuration; legacy
  Hunyuan configuration routes Yuanbao through the browser path
- API platforms use per-platform pacing, concurrency, and retry budgets
- Browser platforms have a 90s per-question timeout (from PlatformConstants), no retries
- Browser failures do not block the overall flow
- Minimum 2 platforms with data required to proceed (adjusted for scoped platform fetch)
"""

import asyncio
import logging
import os
import random
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Iterator, Literal
from uuid import UUID

import httpx
from langgraph.types import Command

from app.core.config import settings
from app.core.constants import PlatformConstants, WorkflowConstants
from app.core.fetchers.browser.failure_observability import (
    BrowserFailureEvidenceService,
    build_failure_contract,
    is_browser_context_closed_error,
)
from app.core.fetchers.browser.browser_executor import (
    PendingBrowserAction,
    handle_browser_failure,
    resume_browser_action,
)
from app.core.llm import LLMUsage
from app.services.llm_usage_service import record_provider_usage_async
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
    send_stage_result,
)
from app.workflow.harness_validation import (
    build_harness_decision,
    decide_a4_completion_policy,
    validate_artifact_writeback,
    validate_scoped_fetch_merge,
)
from app.workflow.fetch_recovery import (
    build_fetch_recovery_plan,
    extract_base_fetch_results_from_state,
    extract_latest_fetch_recovery_plan_from_state,
    normalize_question_targets,
)
from app.workflow.runtime_policy_executor import build_next_required_action
from app.workflow.skill_state import (
    build_harness_decision_update,
    build_skill_result_update,
    build_validation_result_update,
)
from app.workflow.topology_resolver import (
    apply_platform_gate,
    extract_chain_enabled,
    load_flow_topology,
    report_chain_enabled,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CitationIntelligenceTarget:
    url: str
    canonical_domain: str


@dataclass(frozen=True)
class CitationIntelligenceContext:
    fetch_result: dict[str, Any]
    platform_result: dict[str, Any]
    citation: dict[str, Any]


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


def _int_from_mapping(mapping: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = mapping.get(key)
        if value is None:
            continue
        try:
            return max(int(value), 0)
        except (TypeError, ValueError):
            continue
    return None


def _api_usage_fields(response: Any, *, fallback_model: str) -> dict[str, Any]:
    """Keep only provider-reported usage/model metadata from an A4 API response."""

    raw_response = getattr(response, "raw_response", None)
    if not isinstance(raw_response, dict):
        return {}
    raw_usage = raw_response.get("usage_aggregate") or raw_response.get("usage")
    if not isinstance(raw_usage, dict):
        return {}
    model_name = str(raw_response.get("model") or fallback_model or "unknown").strip()
    return {
        "provider_usage": raw_usage,
        "provider_model": model_name or "unknown",
    }


def _llm_usage_from_provider_payload(raw_usage: dict[str, Any]) -> LLMUsage:
    prompt_details = raw_usage.get("prompt_tokens_details")
    if not isinstance(prompt_details, dict):
        prompt_details = raw_usage.get("input_tokens_details")
    if not isinstance(prompt_details, dict):
        prompt_details = None
    cached_prompt_tokens = None
    if prompt_details:
        cached_prompt_tokens = _int_from_mapping(
            prompt_details,
            "cached_tokens",
            "cache_read_input_tokens",
        )
    if cached_prompt_tokens is None:
        cached_prompt_tokens = _int_from_mapping(
            raw_usage,
            "cached_prompt_tokens",
            "prompt_cache_hit_tokens",
        )
    cache_miss_prompt_tokens = _int_from_mapping(
        raw_usage,
        "cache_miss_prompt_tokens",
        "prompt_cache_miss_tokens",
    )
    return LLMUsage(
        prompt_tokens=_int_from_mapping(
            raw_usage,
            "prompt_tokens",
            "input_tokens",
            "PromptTokens",
            "promptTokens",
        ),
        completion_tokens=_int_from_mapping(
            raw_usage,
            "completion_tokens",
            "output_tokens",
            "CompletionTokens",
            "completionTokens",
        ),
        total_tokens=_int_from_mapping(
            raw_usage,
            "total_tokens",
            "TotalTokens",
            "totalTokens",
        ),
        cached_prompt_tokens=cached_prompt_tokens,
        cache_miss_prompt_tokens=cache_miss_prompt_tokens,
        prompt_tokens_details=prompt_details,
        raw=raw_usage,
    )


async def _record_a4_api_usage(
    *,
    session_id: str | None,
    task_id: str | None,
    question_id: str,
    platform: str,
    result: dict[str, Any],
) -> None:
    raw_usage = result.get("provider_usage")
    if not isinstance(raw_usage, dict):
        return
    provider_by_platform = {
        "doubao": "doubao",
        "hunyuan": "hunyuan",
        "kimi": "moonshot",
    }
    await record_provider_usage_async(
        session_id=session_id,
        task_id=task_id,
        skill_key="answer_fetch",
        step="A4",
        step_name="平台答案抓取",
        provider=provider_by_platform.get(platform, platform),
        model_name=str(result.get("provider_model") or platform),
        usage=_llm_usage_from_provider_payload(raw_usage),
        latency_ms=max(int(float(result.get("duration") or 0) * 1000), 0),
        extra_metadata={
            "platform": platform,
            "question_id": question_id,
            "fetch_method": "api",
            "usage_scope": "a4_platform_fetch",
        },
    )


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


def _uuid_or_none(value: object) -> UUID | None:
    try:
        return UUID(str(value)) if value else None
    except (TypeError, ValueError):
        return None


async def _persist_brand_intelligence_fetch_results(
    state: AgentState,
    *,
    fetch_results: list[dict[str, Any]],
) -> None:
    """Dual-write A4 answers and citations into the durable object layer."""

    entity_uuid = _uuid_or_none(state.get("entity_id"))
    if entity_uuid is None or not fetch_results:
        return
    session_uuid = _uuid_or_none(state.get("session_id"))
    try:
        from app.core.database import AsyncSessionLocal
        from app.services.brand_action_service import BrandActionService
        from app.services.brand_intelligence_projection_service import (
            BrandIntelligenceProjectionService,
        )

        async with AsyncSessionLocal() as db:
            action_service = BrandActionService(db)
            action_record = await action_service.start_action(
                entity_id=entity_uuid,
                session_id=session_uuid,
                user_id=_uuid_or_none(state.get("user_id")),
                parent_action_record_id=_uuid_or_none(
                    state.get("latest_user_action_record_id")
                ),
                actor_type="agent",
                origin_surface="workflow_node",
                origin_event_id=str(state.get("run_id") or "") or None,
                action_type="run_answer_fetch",
                input_payload={
                    "question_ids": _action_question_ids_from_fetch_results(
                        fetch_results
                    ),
                    "platforms": _action_platforms_from_fetch_results(fetch_results),
                    "question_count": len(fetch_results),
                    "run_id": state.get("run_id"),
                    "fetch_mode": state.get("fetch_mode"),
                },
            )
            service = BrandIntelligenceProjectionService(db)
            try:
                counts = await service.persist_fetch_results(
                    entity_id=entity_uuid,
                    session_id=session_uuid,
                    fetch_results=fetch_results,
                    source_action_record_id=action_record.id,
                )
                await action_service.complete_action(
                    action_record,
                    output_payload=counts,
                )
                await db.commit()
            except Exception as inner_exc:
                await action_service.fail_action(
                    action_record,
                    error_message=str(inner_exc),
                )
                await db.commit()
                raise
        logger.info("[A4] Brand intelligence fetch projection: %s", counts)
    except Exception as exc:
        logger.warning("[A4] Brand intelligence fetch projection failed: %s", exc)


_ASSOCIATION_CIRCLE_MODES = {
    "brand_association_circle",
    "association_circle",
    "brand-association-circle",
    "amway_association_circle",
    "amway-brand-association-circle",
}


def _is_association_circle_context(state: AgentState) -> bool:
    candidates: list[Any] = [
        state.get("analysis_mode"),
        state.get("report_kind"),
        state.get("a3_mode"),
    ]
    for container_key in (
        "dashboard_context",
        "input_scope",
        "tool_call_args",
        "user_decisions",
    ):
        container = state.get(container_key)
        if isinstance(container, dict):
            candidates.extend(
                [
                    container.get("analysis_mode"),
                    container.get("report_kind"),
                    container.get("a3_mode"),
                ]
            )
    return any(
        str(candidate or "").strip().lower() in _ASSOCIATION_CIRCLE_MODES
        for candidate in candidates
    )


def _association_center_terms_from_a4_state(state: AgentState) -> list[str] | None:
    for key in ("active_center_term", "center_term"):
        text = str(state.get(key) or "").strip()
        if text:
            return [text]

    for key in ("center_terms", "brand_center_terms"):
        value = state.get(key)
        if isinstance(value, list):
            terms = [str(item).strip() for item in value if str(item).strip()]
            if terms:
                return terms[:1]

    for container_key in ("dashboard_context", "input_scope", "tool_call_args"):
        container = state.get(container_key)
        if not isinstance(container, dict):
            continue
        for key in ("active_center_term", "center_term"):
            text = str(container.get(key) or "").strip()
            if text:
                return [text]
        value = container.get("center_terms")
        if isinstance(value, list):
            terms = [str(item).strip() for item in value if str(item).strip()]
            if terms:
                return terms[:1]
    return None


async def _persist_a4_stage_result(
    state: AgentState,
    *,
    task_id: str | None = None,
    stage: str,
    stage_name: str,
    result_type: str,
    data: dict[str, Any],
) -> None:
    resolved_task_id = (
        task_id
        or state.get("task_id")
        or state.get("analysis_task_id")
        or state.get("active_task_id")
    )
    if not resolved_task_id:
        return
    try:
        from app.core.database import AsyncSessionLocal
        from app.services.task_service import TaskService

        async with AsyncSessionLocal() as db:
            task_service = TaskService(db)
            await task_service.append_stage_result(
                UUID(str(resolved_task_id)),
                {
                    "stage": stage,
                    "stage_name": stage_name,
                    "result_type": result_type,
                    "data": data,
                },
            )
    except Exception as exc:
        logger.warning("[A4] Failed to persist stage_result: %s", exc)


async def _persist_amway_calibrated_run_snapshot(
    state: AgentState,
    *,
    fetch_results: list[dict[str, Any]],
    extraction_result: dict[str, Any],
    calibration_result: dict[str, Any],
) -> None:
    dashboard_context = state.get("dashboard_context")
    if not isinstance(dashboard_context, dict):
        return
    brand_run_id = _uuid_or_none(dashboard_context.get("run_id"))
    if brand_run_id is None:
        return

    from app.core.database import AsyncSessionLocal
    from app.models.brand_intelligence_run import BrandIntelligenceRun
    from app.services.amway_circle_tracking_service import (
        AmwayCircleTrackingService,
    )

    async with AsyncSessionLocal() as db:
        brand_run = await db.get(BrandIntelligenceRun, brand_run_id)
        if brand_run is None:
            raise RuntimeError("Brand intelligence run is missing during calibration")
        circle_run = await AmwayCircleTrackingService(db).persist_calibrated_run(
            brand_run,
            {
                "fetch_results": fetch_results,
                "entity_extraction_result": extraction_result,
                "entity_calibration_result": calibration_result,
                "association_circle_projection": calibration_result.get(
                    "association_circle_projection"
                ),
            },
        )
        if circle_run is None:
            raise RuntimeError(
                "Calibration did not create an Amway circle run snapshot"
            )
        await db.commit()


def _action_question_ids_from_fetch_results(
    fetch_results: list[dict[str, Any]],
) -> list[str]:
    question_ids: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(fetch_results or [], start=1):
        if not isinstance(item, dict):
            continue
        question_id = str(
            item.get("question_id") or item.get("id") or f"q_{index:03d}"
        ).strip()
        if question_id and question_id not in seen:
            question_ids.append(question_id)
            seen.add(question_id)
    return question_ids


def _action_platforms_from_fetch_results(
    fetch_results: list[dict[str, Any]],
) -> list[str]:
    platforms: list[str] = []
    seen: set[str] = set()
    for item in fetch_results or []:
        if not isinstance(item, dict):
            continue
        platform_results = item.get("platform_results")
        if isinstance(platform_results, list):
            for platform_result in platform_results:
                if not isinstance(platform_result, dict):
                    continue
                platform = _canonicalize_platform_id(platform_result.get("platform"))
                if platform and platform not in seen:
                    platforms.append(platform)
                    seen.add(platform)
        aio_packets = item.get("aio_platform_packets")
        if isinstance(aio_packets, list):
            for packet in aio_packets:
                if not isinstance(packet, dict):
                    continue
                platform = _canonicalize_platform_id(packet.get("platform"))
                if platform and platform not in seen:
                    platforms.append(platform)
                    seen.add(platform)
    return platforms


def _should_defer_aio_takeover_open(handler: Any) -> bool:
    client = getattr(handler, "client", None)
    return callable(getattr(client, "_ensure_remote_runtime", None))


def _display_platform_names(platforms: list[str]) -> str:
    """Render canonical platform IDs into user-facing display names."""

    return resolve_platform_display_names(platforms)


def _hunyuan_legacy_configuration_detected() -> bool:
    """Detect the retired Hunyuan API configuration used by fast A4."""

    from app.core.fetchers.api.hunyuan_client import HunyuanClient

    return HunyuanClient.has_legacy_configuration(
        configured_url=settings.HUNYUAN_BASE_URL,
        configured_model=settings.HUNYUAN_FAST_MODEL or settings.HUNYUAN_MODEL,
    )


def _resolve_hunyuan_fetch_method(
    fetch_mode: str,
    *,
    requested: bool,
    legacy_configured: bool,
) -> Literal["api", "browser"] | None:
    """Choose one Hunyuan path without changing other platform routing."""

    if not requested:
        return None
    if fetch_mode == "full" or legacy_configured:
        return "browser"
    return "api"


def _resolve_fetch_paths(
    fetch_mode: str,
    platforms: list[str],
) -> tuple[list[str], list[str]]:
    """Return the API/browser execution paths for the requested platforms."""

    if fetch_mode == "full":
        return [], list(platforms)

    hunyuan_browser_fallback = _hunyuan_legacy_configuration_detected()
    api_platforms = [
        p
        for p in platforms
        if p in PlatformConstants.API_PLATFORMS
        and not (p == "hunyuan" and hunyuan_browser_fallback)
    ]
    browser_platforms = [
        p
        for p in platforms
        if p in PlatformConstants.BROWSER_PLATFORMS
        or (p == "hunyuan" and hunyuan_browser_fallback)
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


def _build_a4_followup_options(
    *,
    retry_failed_only: bool,
    fetch_mode: str,
) -> list[dict[str, str]]:
    mode_label = "快速/API" if fetch_mode == "fast" else "完整/浏览器"
    supplemental_label = (
        f"继续补采剩余失败项（{mode_label}）"
        if retry_failed_only
        else f"补采失败项（{mode_label}）"
    )
    supplemental_description = (
        "沿用上一轮采集模式，只重跑本轮补采后仍失败的平台和问题，并和已成功结果继续合并"
        if retry_failed_only
        else "沿用上一轮采集模式，只重跑上一轮失败的平台和问题，并和已成功结果合并"
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
    headless_mode: bool,
    retry_failed_only: bool,
    scoped_merge_active: bool,
    question_targets: list[dict[str, Any]],
    successful_fetches: int,
    total_fetches: int,
    fail_count: int,
    platform_statuses: dict[str, Any],
    fetch_mode: str,
    merge_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    recovery_plan = build_fetch_recovery_plan(projected_fetch_results)
    if recovery_plan is not None:
        recovery_plan = {**recovery_plan, "fetch_mode": fetch_mode}
    requires_user_decision = bool(
        artifact_validation.passed
        and completion_decision.decision_type == "degraded_continue"
        and recovery_plan
        and int(recovery_plan.get("failure_count") or 0) > 0
        and not headless_mode
    )
    return {
        "summary": (
            "答案抓取已完成，当前仍有失败项，需要由 Orchestrator 先请求用户确认下一步。"
            if requires_user_decision
            else (
                "答案抓取已完成；当前为 headless 定时任务，将直接继续生成分析报告。"
                if headless_mode and artifact_validation.passed
                else "答案抓取已完成，结果已写回到当前官方样本。"
            )
        ),
        "requires_user_decision": requires_user_decision,
        "followup_options": (
            _build_a4_followup_options(
                retry_failed_only=retry_failed_only,
                fetch_mode=fetch_mode,
            )
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
        "merge_metadata": dict(merge_metadata or {}),
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
        "merge_metadata": dict(observation.get("merge_metadata") or {}),
        "observation": observation,
    }


def _count_fetch_pairs(fetch_results: list[dict[str, Any]] | None) -> int:
    count = 0
    for entry in fetch_results or []:
        count += len(entry.get("platform_results") or [])
    return count


def _fetch_results_arg(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _collect_citation_intelligence_targets(
    fetch_results: list[dict[str, Any]],
) -> list[CitationIntelligenceTarget]:
    from app.core.domain_normalization import normalize_domain
    from app.core.utils import extract_domain

    targets: list[CitationIntelligenceTarget] = []
    seen_urls: set[str] = set()
    for context in _iter_citation_intelligence_contexts(fetch_results):
        citation = context.citation
        url = str(citation.get("url") or "").strip()
        raw_domain = str(citation.get("domain") or "").strip()
        domain = normalize_domain(raw_domain or extract_domain(url) or url)
        if not url or not domain or url in seen_urls:
            continue
        targets.append(
            CitationIntelligenceTarget(
                url=url,
                canonical_domain=domain,
            )
        )
        seen_urls.add(url)
    return targets


def _iter_citation_intelligence_contexts(
    fetch_results: list[dict[str, Any]],
) -> Iterator[CitationIntelligenceContext]:
    for fetch_result in fetch_results:
        for platform_result in fetch_result.get("platform_results", []) or []:
            if not isinstance(platform_result, dict):
                continue
            for citation in platform_result.get("citations", []) or []:
                if not isinstance(citation, dict):
                    continue
                yield CitationIntelligenceContext(
                    fetch_result=fetch_result,
                    platform_result=platform_result,
                    citation=citation,
                )
        for packet in fetch_result.get("aio_platform_packets", []) or []:
            if not isinstance(packet, dict):
                continue
            for citation in packet.get("citations", []) or []:
                if not isinstance(citation, dict):
                    continue
                yield CitationIntelligenceContext(
                    fetch_result=fetch_result,
                    platform_result=packet,
                    citation=citation,
                )


async def _build_domain_intelligence_lookup(
    fetch_results: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    targets = _collect_citation_intelligence_targets(fetch_results)
    domains: list[str] = []
    seen_domains: set[str] = set()
    for target in targets:
        if target.canonical_domain in seen_domains:
            continue
        domains.append(target.canonical_domain)
        seen_domains.add(target.canonical_domain)
    if not domains:
        return {}

    from app.services.url_intelligence_skill import URLIntelligenceSkill

    skill = URLIntelligenceSkill()
    results = await skill.analyze_domains(domains)
    return {domain: result.to_payload() for domain, result in results.items()}


def _citation_information_updated_at(
    *,
    citation: dict[str, Any],
    platform_result: dict[str, Any],
    fetch_result: dict[str, Any],
    fallback: str,
) -> tuple[str, str]:
    metadata = (
        citation.get("metadata") if isinstance(citation.get("metadata"), dict) else {}
    )
    candidates = (
        ("citation", citation.get("information_updated_at")),
        ("citation", citation.get("updated_at")),
        ("citation", citation.get("published_at")),
        ("citation", citation.get("date")),
        ("metadata", metadata.get("information_updated_at")),
        ("metadata", metadata.get("updated_at")),
        ("metadata", metadata.get("published_at")),
        ("metadata", metadata.get("date")),
        ("platform_result", platform_result.get("fetched_at")),
        ("platform_result", platform_result.get("updated_at")),
        ("fetch_result", fetch_result.get("fetched_at")),
        ("fetch_result", fetch_result.get("updated_at")),
    )
    for source, value in candidates:
        text = str(value or "").strip()
        if text:
            return text, source
    return fallback, "a4_enrichment"


async def _enrich_fetch_result_citation_domains(
    *,
    fetch_results: list[dict[str, Any]],
    brand_profile: dict[str, Any],
    entity_id: str | None,
) -> None:
    """Attach domain-memory resolution to A4 canonical citation rows."""

    brand_name = str(brand_profile.get("brand_name") or "").strip()
    if not brand_name:
        return

    from app.core.database import AsyncSessionLocal
    from app.core.domain_normalization import normalize_domain
    from app.core.utils import extract_domain
    from app.services.domain_memory_service import DomainMemoryService

    official_domain = normalize_domain(brand_profile.get("official_website"))
    official_domains = [official_domain] if official_domain else []
    domain_intelligence_lookup = await _build_domain_intelligence_lookup(fetch_results)
    enrichment_timestamp = datetime.now(timezone.utc).isoformat()

    async with AsyncSessionLocal() as db:
        domain_memory = DomainMemoryService(db)
        resolution_cache: dict[tuple[str, str], Any] = {}
        for fetch_result in fetch_results:
            question_text = str(fetch_result.get("question_text") or "")
            for context in _iter_citation_intelligence_contexts([fetch_result]):
                platform_result = context.platform_result
                citation = context.citation
                platform = str(platform_result.get("platform") or "")
                url = str(citation.get("url") or "").strip()
                raw_domain = str(citation.get("domain") or "").strip()
                if not raw_domain:
                    raw_domain = extract_domain(url)
                canonical_domain = normalize_domain(raw_domain or url)
                title = str(citation.get("title") or "").strip()
                snippet = str(
                    citation.get("snippet")
                    or citation.get("summary")
                    or question_text
                    or ""
                ).strip()
                site_name = str(
                    citation.get("site_name")
                    or citation.get("source")
                    or citation.get("site_display_name")
                    or ""
                ).strip()
                url_intelligence = domain_intelligence_lookup.get(
                    canonical_domain or ""
                )
                information_updated_at, information_updated_at_source = (
                    _citation_information_updated_at(
                        citation=citation,
                        platform_result=platform_result,
                        fetch_result=fetch_result,
                        fallback=enrichment_timestamp,
                    )
                )
                resolution_key = (canonical_domain or raw_domain or "", url)
                resolution = resolution_cache.get(resolution_key)
                if resolution is None:
                    resolution = await domain_memory.resolve_citation_domain_fast(
                        url=url,
                        raw_domain=raw_domain,
                        title=title,
                        snippet=snippet,
                        site_name=site_name,
                        brand_name=brand_name,
                        entity_id=entity_id,
                        official_domains=official_domains,
                        platform=platform,
                        url_intelligence=url_intelligence,
                    )
                    resolution_cache[resolution_key] = resolution
                resolution_payload = {
                    "canonical_domain": resolution.canonical_domain,
                    "display_name": resolution.display_name,
                    "owner_name": resolution.owner_name,
                    "source_type": resolution.source_type,
                    "site_category": resolution.site_category,
                    "relation_type": resolution.relation_type,
                    "confidence": resolution.confidence,
                    "status": resolution.status,
                    "resolved_by": resolution.resolved_by,
                }
                metadata = dict(citation.get("metadata") or {})
                raw_site_name = citation.get("site_name")
                if raw_site_name:
                    metadata.setdefault("raw_site_name", raw_site_name)
                metadata.update(
                    {
                        "site_display_name": resolution.display_name,
                        "site_category": resolution.site_category,
                        "source_type": resolution.source_type,
                        "canonical_domain": resolution.canonical_domain,
                        "domain_relation_type": resolution.relation_type,
                        "domain_resolution_confidence": resolution.confidence,
                        "domain_resolution_status": resolution.status,
                        "domain_resolved_by": resolution.resolved_by,
                        "is_official": resolution.is_official,
                        "domain_resolution": resolution_payload,
                        "url_intelligence": resolution.url_intelligence,
                        "information_updated_at": information_updated_at,
                        "information_updated_at_source": (
                            information_updated_at_source
                        ),
                    }
                )
                citation.update(
                    {
                        "metadata": metadata,
                        "site_name": resolution.display_name,
                        "site_display_name": resolution.display_name,
                        "site_category": resolution.site_category,
                        "source_type": resolution.source_type,
                        "canonical_domain": resolution.canonical_domain,
                        "domain_relation_type": resolution.relation_type,
                        "domain_resolution_confidence": resolution.confidence,
                        "domain_resolution_status": resolution.status,
                        "domain_resolved_by": resolution.resolved_by,
                        "url_intelligence": resolution.url_intelligence,
                        "information_updated_at": information_updated_at,
                        "information_updated_at_source": (
                            information_updated_at_source
                        ),
                        "is_official": bool(
                            citation.get("is_official") or resolution.is_official
                        ),
                    }
                )
        await db.commit()


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
            if not api_platforms:
                return f"开始 {browser_names} 浏览器采集。"
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


def _build_fast_phase_start_message(
    question_count: int,
    platforms: list[str],
) -> str:
    """Describe fast-mode work from its resolved API/browser paths."""

    api_platforms, browser_platforms = _resolve_fetch_paths("fast", platforms)
    api_names = _display_platform_names(api_platforms)
    browser_names = _display_platform_names(browser_platforms)
    if api_names:
        message = (
            f"正在通过 API 抓取：{question_count} 个问题 × {api_names}，"
            "批量并行抓取中..."
        )
    else:
        message = f"当前无 API 任务，直接通过浏览器采集 {question_count} 个问题。"
    if browser_names:
        message += f" 浏览器平台：{browser_names}。"
    return message


def _build_fast_path_summary(platforms: list[str]) -> str:
    """Render the fast-mode path label from the resolved execution paths."""

    api_platforms, browser_platforms = _resolve_fetch_paths("fast", platforms)
    return _format_fetch_path_summary(api_platforms, browser_platforms)


def _format_fetch_path_summary(
    api_platforms: list[str],
    browser_platforms: list[str],
    *,
    role_first: bool = False,
) -> str:
    """Format resolved platform paths for either a label or detail line."""

    path_parts = []
    if api_platforms:
        api_names = _display_platform_names(api_platforms)
        path_parts.append(f"API（{api_names}）" if role_first else f"{api_names} API")
    if browser_platforms:
        browser_names = _display_platform_names(browser_platforms)
        path_parts.append(
            f"浏览器（{browser_names}）" if role_first else f"{browser_names} 浏览器"
        )
    return " + ".join(path_parts) or "无可用平台"


def _build_fast_mode_label(platforms: list[str]) -> str:
    """Build the fast-mode label without assuming which platform uses API."""

    return f"快速采集（{_build_fast_path_summary(platforms)}）"


def _question_id_from_state_question(question: dict[str, Any]) -> str:
    """Resolve the stable question id from workflow question objects."""

    if not isinstance(question, dict):
        return ""
    return str(
        question.get("id") or question.get("question_id") or question.get("qid") or ""
    ).strip()


_QUESTION_METADATA_KEYS = (
    "category",
    "intent",
    "stage",
    "source",
    "source_persona",
    "audience_segment",
    "core_anxiety",
    "life_scene",
    "opportunity_point",
    "probe_type",
    "mother_theme",
    "question_type",
    "mentions_amway",
    "life_stage",
    "four_have",
    "touchpoint",
    "monitoring_purpose",
    "center_terms",
    "question_set_version",
)


def _question_metadata_for_fetch_result(question: dict[str, Any]) -> dict[str, Any]:
    """Copy analysis metadata from A3 question rows into A4 fetch rows."""

    metadata: dict[str, Any] = {}
    if not isinstance(question, dict):
        return metadata
    for key in _QUESTION_METADATA_KEYS:
        value = question.get(key)
        if value not in (None, ""):
            metadata[key] = value
    if "intent" in metadata and "user_intent" not in metadata:
        metadata["user_intent"] = metadata["intent"]
    if "stage" in metadata and "decision_stage" not in metadata:
        metadata["decision_stage"] = metadata["stage"]
    return metadata


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
        if question_platform_targets:
            targeted_platforms = question_platform_targets.get(question_id)
        else:
            targeted_platforms = selected_platforms
        kept_platform_results = [
            platform_result
            for platform_result in existing_entry.get("platform_results", []) or []
            if not targeted_platforms
            or _canonicalize_platform_id(platform_result.get("platform"))
            not in targeted_platforms
        ]
        if kept_platform_results:
            kept_platforms = {
                _canonicalize_platform_id(platform_result.get("platform"))
                for platform_result in kept_platform_results
                if _canonicalize_platform_id(platform_result.get("platform"))
            }
            preserved.append(
                {
                    "question_id": question_id,
                    "question_text": existing_entry.get("question_text", ""),
                    **_question_metadata_for_fetch_result(
                        next(
                            (
                                question
                                for question in current_questions
                                if _question_id_from_state_question(question)
                                == question_id
                            ),
                            {},
                        )
                    ),
                    "platform_results": kept_platform_results,
                    "aio_platform_packets": _collect_aio_platform_packets_for_platforms(
                        existing_entry,
                        platform_results=kept_platform_results,
                        platforms=kept_platforms,
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
        max_parallel = max(1, settings.AIO_MAX_PARALLEL_BROWSER_SESSIONS)
        schedule_mode = "serially" if max_parallel == 1 else "with bounded parallelism"
        logger.info(
            "[A4] Phase 2: AIO runtime detected, executing browser pipelines %s (max=%d)",
            schedule_mode,
            max_parallel,
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


def _merge_aio_platform_packets(
    *packet_groups: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen_platforms: set[str] = set()
    for packet_group in packet_groups:
        for packet in packet_group or []:
            if not isinstance(packet, dict):
                continue
            platform = _canonicalize_platform_id(packet.get("platform"))
            if not platform or platform in seen_platforms:
                continue
            merged.append(packet)
            seen_platforms.add(platform)
    return merged


def _collect_aio_platform_packets_for_platforms(
    fetch_result: dict[str, Any],
    *,
    platform_results: list[dict[str, Any]],
    platforms: set[str],
) -> list[dict[str, Any]]:
    top_level_packets = [
        packet
        for packet in fetch_result.get("aio_platform_packets", []) or []
        if isinstance(packet, dict)
        and _canonicalize_platform_id(packet.get("platform")) in platforms
    ]
    return _merge_aio_platform_packets(
        top_level_packets,
        _collect_aio_platform_packets(platform_results),
    )


def _legacy_platform_result_to_packet(
    platform_result: dict[str, Any],
) -> dict[str, Any] | None:
    platform = _canonicalize_platform_id(platform_result.get("platform"))
    if not platform:
        return None
    status = platform_result.get("status")
    if status is None:
        status = "success" if platform_result.get("success") else "failed"
    packet: dict[str, Any] = {
        "platform": platform,
        "status": str(status or "failed").strip().lower() or "failed",
    }
    for key in (
        "answer",
        "citations",
        "fetch_method",
        "error",
        "duration",
        "failure_layer",
        "failure_reason",
        "execution_stage",
        "retryable",
        "needs_handoff",
    ):
        value = platform_result.get(key)
        if value is not None:
            packet[key] = value
    return packet


def _packets_for_fetch_result(fetch_result: dict[str, Any]) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    seen_platforms: set[str] = set()

    def add_packet(packet: dict[str, Any] | None) -> None:
        if not isinstance(packet, dict):
            return
        platform = _canonicalize_platform_id(packet.get("platform"))
        if not platform or platform in seen_platforms:
            return
        collected.append(packet)
        seen_platforms.add(platform)

    packets = fetch_result.get("aio_platform_packets")
    if isinstance(packets, list):
        for packet in packets:
            add_packet(packet)

    platform_results = fetch_result.get("platform_results", [])
    if isinstance(platform_results, list):
        for platform_result in platform_results:
            if not isinstance(platform_result, dict):
                continue
            aio_packet = platform_result.get("aio_packet")
            add_packet(aio_packet if isinstance(aio_packet, dict) else None)
            add_packet(_legacy_platform_result_to_packet(platform_result))
    return collected


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
        "risk_control_page",
        "page_runtime_retry_or_risk_control",
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


def _should_stop_browser_platform_after_failure(result: dict[str, Any]) -> bool:
    """Stop the current platform run when repeating the next question is pointless."""

    if result.get("success"):
        return False

    error_type = str(result.get("error_type") or "").strip().lower()
    failure_reason = str(result.get("failure_reason") or "").strip().lower()
    stop_reasons = {
        "page_runtime_retry_or_risk_control",
    }
    return error_type in stop_reasons or failure_reason in stop_reasons


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
    """Persist A4 live progress for control-plane observability."""

    if not task_id:
        return

    try:
        from uuid import UUID

        from app.core.database import AsyncSessionLocal
        from app.models.task import TaskStatus
        from app.services.task_service import TaskService

        task_uuid = UUID(str(task_id))
        safe_progress = max(0.0, min(1.0, float(progress)))
        async with AsyncSessionLocal() as db:
            task_service = TaskService(db)
            task = await task_service.get_task(task_uuid)
            if task is None or task.status in {
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            }:
                return
            await task_service.update_progress(
                task_uuid,
                stage=stage,
                progress=safe_progress,
                message=message[:255],
            )
    except Exception as exc:
        logger.warning(
            "[A4] Failed to persist task progress task=%s context=%s: %s",
            task_id,
            context,
            exc,
        )


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


async def _tracked_api_fetch_with_context(
    q_idx: int,
    platform: str,
    coro: Coroutine[Any, Any, dict[str, Any]],
    tracker: _ProgressTracker,
) -> tuple[int, str, dict[str, Any] | None, Exception | None]:
    """Return question/platform context with each completed API answer."""

    try:
        result = await _tracked_api_fetch(coro, platform, tracker)
    except Exception as exc:
        return q_idx, platform, None, exc
    return q_idx, platform, result, None


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

    configured_timeout = float(
        PlatformConstants.BROWSER_PIPELINE_TIMEOUT_OVERRIDES.get(
            platform,
            PlatformConstants.BROWSER_PIPELINE_TIMEOUT,
        )
    )
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


_platform_semaphores: dict[str, tuple[int, asyncio.Semaphore]] = {}


def _get_platform_semaphore(platform: str) -> asyncio.Semaphore:
    """Get or create a per-platform semaphore with configurable API concurrency."""

    concurrency = _get_api_concurrency(platform)
    existing = _platform_semaphores.get(platform)
    if existing is not None and existing[0] == concurrency:
        return existing[1]

    sem = asyncio.Semaphore(concurrency)
    _platform_semaphores[platform] = (concurrency, sem)
    return sem


def _coerce_non_negative_float(value: Any, default: float) -> float:
    try:
        coerced = float(value)
    except (TypeError, ValueError):
        coerced = default
    return max(0.0, coerced)


def _coerce_int_range(value: Any, default: int, *, minimum: int, maximum: int) -> int:
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        coerced = default
    return max(minimum, min(maximum, coerced))


def _get_api_concurrency(platform: str) -> int:
    """Return bounded fast-mode API concurrency for one platform."""

    override_by_platform = {
        "doubao": settings.A4_DOUBAO_API_CONCURRENCY,
        "hunyuan": settings.A4_HUNYUAN_API_CONCURRENCY,
        "yuanbao": settings.A4_HUNYUAN_API_CONCURRENCY,
        "kimi": settings.A4_KIMI_API_CONCURRENCY,
    }
    return _coerce_int_range(
        override_by_platform.get(platform, 1),
        1,
        minimum=1,
        maximum=8,
    )


def _get_api_max_retries(platform: str) -> int:
    """Return bounded fast-mode API retry budget for one platform."""

    override_by_platform = {
        "doubao": settings.A4_DOUBAO_API_MAX_RETRIES,
        "hunyuan": settings.A4_HUNYUAN_API_MAX_RETRIES,
        "yuanbao": settings.A4_HUNYUAN_API_MAX_RETRIES,
        "kimi": settings.A4_KIMI_API_MAX_RETRIES,
    }
    return _coerce_int_range(
        override_by_platform.get(platform, MAX_RETRIES),
        MAX_RETRIES,
        minimum=0,
        maximum=MAX_RETRIES,
    )


def _get_api_request_delay(platform: str) -> float:
    """Return configurable fast-mode API pacing for one platform."""

    override_by_platform = {
        "doubao": settings.A4_DOUBAO_API_DELAY_SECONDS,
        "hunyuan": settings.A4_HUNYUAN_API_DELAY_SECONDS,
        "yuanbao": settings.A4_HUNYUAN_API_DELAY_SECONDS,
        "kimi": settings.A4_KIMI_API_DELAY_SECONDS,
    }
    return _coerce_non_negative_float(override_by_platform.get(platform, 0.0), 0.0)


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
        delay = (
            _get_api_request_delay(platform)
            if method == "api"
            else PlatformConstants.PLATFORM_REQUEST_DELAYS.get(platform, 3.0)
        )
        if delay > 0:
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


def _provider_429_retry_wait(
    platform: str,
    error_type: str,
    suggested_wait: float | None,
) -> float:
    """Return the actual wait used before retrying a provider-side 429."""

    wait = _coerce_non_negative_float(
        suggested_wait,
        WorkflowConstants.DEFAULT_429_RETRY_SECONDS,
    )
    if platform == "kimi" and error_type in {
        "rate_limit",
        "engine_overloaded",
        "unknown",
    }:
        cooldown = _coerce_non_negative_float(
            getattr(settings, "A4_KIMI_API_429_COOLDOWN_SECONDS", 20.0),
            20.0,
        )
        wait = max(wait, cooldown)
    return wait


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


def _build_api_rate_limit_failure(
    *,
    platform: str,
    method: str,
    error_type: str,
    error_detail: str,
    retry_after_seconds: float | None = None,
) -> dict[str, Any]:
    """Build a user-safe API rate-limit failure payload."""

    platform_name = PlatformConstants.PLATFORM_DISPLAY_NAMES.get(platform, platform)
    if error_type == "quota_exceeded":
        error = f"{platform_name} API 当前配额不足，本题已跳过。"
        retryable = False
    elif error_type == "engine_overloaded":
        error = f"{platform_name} API 当前服务繁忙，本题已跳过，可稍后重试。"
        retryable = True
    else:
        error = f"{platform_name} API 当前请求过于频繁，本题已跳过，可稍后重试。"
        retryable = True

    return {
        "platform": platform,
        "platform_name": platform_name,
        "fetch_method": method,
        "success": False,
        "error": error,
        "error_detail": error_detail,
        "error_type": "api_rate_limited",
        "provider_error_type": error_type,
        "failure_layer": "api_provider",
        "failure_reason": error_type,
        "status_code": 429,
        "retryable": retryable,
        "retry_after_seconds": retry_after_seconds,
    }


async def _retry_fetch(
    fetch_fn: Callable[..., Coroutine[Any, Any, dict[str, Any]]],
    *args: Any,
    platform: str,
    method: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Retry a fetch function with the platform's API retry budget.

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
    retry_usage_totals = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cached_prompt_tokens": 0,
        "cache_miss_prompt_tokens": 0,
    }
    usage_observed = False

    def attach_retry_usage(result: dict[str, Any]) -> dict[str, Any]:
        if not usage_observed:
            return result
        return {**result, "provider_usage": dict(retry_usage_totals)}

    attempt = 0
    overload_retries = 0
    overload_retry_limit, overload_base_wait = _engine_overload_retry_budget(platform)
    max_retries = _get_api_max_retries(platform)

    while attempt <= max_retries:
        try:
            result = await fetch_fn(*args, **kwargs)
            raw_usage = result.get("provider_usage")
            if isinstance(raw_usage, dict):
                parsed_usage = _llm_usage_from_provider_payload(raw_usage)
                prompt_tokens = max(int(parsed_usage.prompt_tokens or 0), 0)
                completion_tokens = max(int(parsed_usage.completion_tokens or 0), 0)
                retry_usage_totals["prompt_tokens"] += prompt_tokens
                retry_usage_totals["completion_tokens"] += completion_tokens
                retry_usage_totals["total_tokens"] += prompt_tokens + completion_tokens
                retry_usage_totals["cached_prompt_tokens"] += max(
                    int(parsed_usage.cached_prompt_tokens or 0), 0
                )
                retry_usage_totals["cache_miss_prompt_tokens"] += max(
                    int(parsed_usage.cache_miss_prompt_tokens or 0), 0
                )
                usage_observed = True
            if result.get("success"):
                if attempt > 0:
                    logger.info("[A4] %s succeeded on retry %d", platform, attempt)
                return attach_retry_usage(result)
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
                try:
                    header_val = float(e.response.headers.get("Retry-After", 0))
                except (ValueError, TypeError):
                    header_val = 0
                retry_after = (
                    hint_seconds
                    or (header_val or None)
                    or WorkflowConstants.DEFAULT_429_RETRY_SECONDS
                )
                retry_wait = _provider_429_retry_wait(
                    platform,
                    error_type,
                    retry_after,
                )
                last_result = _build_api_rate_limit_failure(
                    platform=platform,
                    method=method,
                    error_type=error_type,
                    error_detail=f"HTTP 429: {error_type}",
                    retry_after_seconds=retry_after,
                )

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
                    wait = _provider_429_retry_wait(platform, error_type, wait)
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
                    if attempt < max_retries:
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
                            max_retries,
                        )
                        await asyncio.sleep(wait)
                        attempt += 1
                        continue

                # rate_limit or unknown
                if attempt < max_retries:
                    logger.warning(
                        "[A4] %s 429 (%s), waiting %.0fs before retry",
                        platform,
                        error_type,
                        retry_wait,
                    )
                    await asyncio.sleep(retry_wait)
                    attempt += 1
                    continue

        if attempt < max_retries:
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
        max_retries + 1,
        last_result.get("error"),
    )
    return attach_retry_usage(last_result)


async def _browser_fetch_with_timeout(
    fetch_fn: Callable[..., Coroutine[Any, Any, dict[str, Any]]],
    *args: Any,
    timeout: float = 200.0,
    **kwargs: Any,
) -> dict[str, Any]:
    """Run a browser fetch with a strict timeout and no retries.

    Browser platforms (Yuanbao/Kimi/DeepSeek) are optional — failures are non-blocking.
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
        context_closed = is_browser_context_closed_error(e)
        failure_reason = "browser_context_closed" if context_closed else "parser_error"
        error_type = "browser_context_closed" if context_closed else "parser_error"
        failure_layer = "client" if context_closed else "executor"
        evidence_ref = await _capture_browser_failure_evidence(
            handler=handler,
            failure_reason=failure_reason,
            execution_stage="executor_failure",
            question_id=question_id,
            question_text=question_text,
            extra_metadata={"exception": str(e)},
        )

        return _build_browser_failure_result(
            platform=platform,
            platform_name=platform_name,
            error=str(e),
            error_type=error_type,
            duration=0.0,
            failure_reason=failure_reason,
            execution_stage="executor_failure",
            retryable=context_closed,
            needs_handoff=False,
            failure_layer=failure_layer,
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
        api_platforms, browser_platforms = _resolve_fetch_paths(
            fetch_mode, list(PlatformConstants.SUPPORTED_PLATFORMS)
        )
        api_str = _display_platform_names(api_platforms)
        browser_str = _display_platform_names(browser_platforms)
        path_summary = _format_fetch_path_summary(
            api_platforms, browser_platforms, role_first=True
        )
        detail_lines = [f"- 采集模式：**快速采集**（{path_summary}）"]
        if api_str:
            detail_lines.append(f"- API 平台（{api_str}）：各平台串行抓取，约 2-3 分钟")
        if browser_str:
            detail_lines.append(f"- 浏览器平台（{browser_str}）：约 3-5 分钟")
        return (
            f"开始向{all_names} {platform_count} 个平台提问，共 {question_count} 个问题。\n\n"
            + "\n".join(detail_lines)
            + "\n"
            "- 预计总耗时约 5-10 分钟\n\n"
            "请保持页面打开，可以切换到其他标签页做别的事，完成后将自动继续。"
        )


def _monitor_mode_from_fetch_state(state: AgentState) -> str:
    analysis_mode = str(state.get("analysis_mode") or "").strip().lower()
    if analysis_mode == "persona":
        return "scenario"
    return "panorama"


async def _activate_plan_after_question_confirmation(
    state: AgentState,
    *,
    fetch_mode: str,
) -> dict[str, Any]:
    """Promote the latest draft question set once the user confirms A4 fetch."""
    if state.get("headless_mode"):
        return {}
    question_set_id = str(state.get("latest_question_set_id") or "").strip()
    user_id = str(state.get("user_id") or "").strip()
    entity_id = str(state.get("entity_id") or "").strip()
    if not question_set_id or not user_id or not entity_id:
        return {}
    try:
        from uuid import UUID

        from app.core.database import AsyncSessionLocal
        from app.services.monitoring_plan_service import MonitoringPlanService

        async with AsyncSessionLocal() as db:
            service = MonitoringPlanService(db)
            plan = await service.create_or_update_active_plan_from_question_set(
                user_id=UUID(user_id),
                entity_id=UUID(entity_id),
                question_set_id=UUID(question_set_id),
                monitor_mode=_monitor_mode_from_fetch_state(state),
                fetch_mode=fetch_mode,
            )
            plan_payload = await service.plan_to_dict(plan)
            logger.info(
                "[A4] Activated monitoring plan %s from question set %s",
                plan.id,
                question_set_id,
            )
            return {
                "monitoring_plan_id": str(plan.id),
                "latest_monitoring_plan_id": str(plan.id),
                "question_set_ids": plan_payload.get("question_set_ids") or [],
                "endpoint_ids": plan_payload.get("endpoint_ids") or [],
                "run_policy": plan_payload.get("run_policy") or "quick",
            }
    except Exception as exc:
        logger.warning("[A4] Failed to activate monitoring plan: %s", exc)
        return {}


async def _amway_realtime_extractor(entity_uuid, *, enabled=True):
    from app.core.database import AsyncSessionLocal
    from app.services.amway_entity_lexicon_service import AmwayEntityLexiconService
    from app.services.amway_entity_extraction_service import AmwayEntityExtractionService

    registry = None
    if entity_uuid is not None and enabled:
        async with AsyncSessionLocal() as db:
            registry = await AmwayEntityLexiconService(db).registry_for_entity(entity_uuid)
    return AmwayEntityExtractionService(registry=registry)


async def a4_fetch_node(state: AgentState) -> Command:
    """A4: Fetch answers from AI platforms for all questions.

    Supports two modes (controlled by state['fetch_mode']):
    - fast: API (Doubao/Kimi) + DeepSeek Browser; legacy Hunyuan config uses
      Yuanbao Browser instead (~5-10 min)
    - full: All 4 platforms via Browser only, no API       (~8-15 min)
    """
    session_id = state["session_id"]
    state_questions = list(state.get("questions", []) or [])
    questions = list(state_questions)
    brand_profile = state.get("brand_profile") or {}
    fetch_mode = state.get("fetch_mode") or "fast"
    tool_args = state.get("tool_call_args") or {}
    retry_failed_only = bool(tool_args.get("retry_failed_only"))
    base_fetch_results = _fetch_results_arg(
        tool_args.get("base_fetch_results")
    ) or extract_base_fetch_results_from_state(state)
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
    base_platform_filter = (
        normalized_requested_platforms
        or targeted_platforms
        or state.get("platform_filter")
    )
    # 3b-1.3 拓扑平台门：画布上断开 fetch→platform-X 连线的平台本轮不抓取。
    # 无拓扑记录时 apply_platform_gate 原样透传，行为与硬编码时代一致。
    # P1-1: defense-in-depth — even if LLM dispatches A4 while the canvas
    # questions→fetch edge is removed, refuse to fetch.
    from app.workflow.topology_resolver import fetch_chain_enabled

    flow_topology = await load_flow_topology(state.get("entity_id"))
    if not fetch_chain_enabled(flow_topology):
        logger.info(
            "[A4] Topology fetch-chain gate closed; refusing answer_fetch dispatch."
        )
        return Command(
            update={
                "fetch_results": [],
                "current_step": "A4",
                "progress": 1.0,
                "progress_message": "画布已断开「问题集 → 采集」连线，跳过答案抓取。",
                "execution_status": "completed",
                "next_required_action": None,
                "awaiting_user": False,
                "orchestrator_reply": "画布已断开「问题集 → 采集」连线，跳过答案抓取。",
            },
        )
    gated_platform_filter, topology_disabled_platforms = apply_platform_gate(
        flow_topology, _normalize_platform_filter(base_platform_filter)
    )
    if topology_disabled_platforms and gated_platform_filter is None:
        logger.info(
            "[A4] Topology platform gate disconnected all platforms; skipping fetch."
        )
        return Command(
            update={
                "fetch_results": [],
                "current_step": "A4",
                "progress": 1.0,
                "progress_message": "画布上所有采集平台连线均已断开，本次运行跳过答案抓取。",
                "execution_status": "completed",
                "next_required_action": None,
                "awaiting_user": False,
                "orchestrator_reply": "画布上所有采集平台连线均已断开，本次运行跳过答案抓取。",
            },
        )
    if topology_disabled_platforms:
        logger.info(
            "[A4] Topology platform gate: disabled=%s effective=%s",
            sorted(topology_disabled_platforms),
            gated_platform_filter,
        )
    raw_platform_filter = (
        gated_platform_filter if topology_disabled_platforms else base_platform_filter
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
    monitoring_plan_update = await _activate_plan_after_question_confirmation(
        state,
        fetch_mode=fetch_mode,
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
            else _build_fast_mode_label(list(PlatformConstants.SUPPORTED_PLATFORMS))
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
    realtime_entity_extraction_service: Any | None = None
    realtime_entity_extraction_result: dict[str, Any] | None = None
    if _is_association_circle_context(state):
        try:
            entity_uuid = _uuid_or_none(state.get("entity_id"))
            from app.workflow.topology_resolver import lexicon_chain_enabled
            lexicon_enabled = lexicon_chain_enabled(flow_topology)
            realtime_entity_extraction_service = await _amway_realtime_extractor(entity_uuid, enabled=lexicon_enabled)
            realtime_entity_extraction_result = (
                realtime_entity_extraction_service.extract_from_fetch_results([])
            )
            realtime_entity_extraction_result["realtime_extraction_enabled"] = True
            realtime_entity_extraction_result["lexicon_source"] = "editable" if entity_uuid and lexicon_enabled else "bundled"
            realtime_entity_extraction_result["realtime_answer_ids"] = []
        except Exception as extraction_init_err:
            logger.warning(
                "[A4] Realtime Amway entity extraction init failed: %s",
                extraction_init_err,
            )
            realtime_entity_extraction_service = None
            realtime_entity_extraction_result = None
            raise RuntimeError("Amway effective lexicon initialization failed; collection was not started") from extraction_init_err

    try:
        # Initialize fetchers based on fetch_mode
        from app.schemas.fetch import BrowserState

        # Cycle 3: If platform_filter is set, only initialize requested platforms
        _pf = set(platform_filter) if platform_filter else None

        # ── API clients (fast mode only) ──
        doubao_client = None
        hunyuan_client = None
        kimi_client = None
        hunyuan_requested = _pf is None or "hunyuan" in _pf
        hunyuan_browser_fallback = (
            fetch_mode == "fast" and _hunyuan_legacy_configuration_detected()
        )
        hunyuan_fetch_method = _resolve_hunyuan_fetch_method(
            fetch_mode,
            requested=hunyuan_requested,
            legacy_configured=hunyuan_browser_fallback,
        )

        if fetch_mode == "fast":
            from app.core.fetchers.api.doubao_client import DoubaoClient

            if hunyuan_fetch_method == "browser":
                logger.warning(
                    "[A4] Legacy Hunyuan endpoint/model detected; "
                    "routing Yuanbao through browser and skipping Hunyuan API"
                )

            try:
                if _pf is None or "doubao" in _pf:
                    doubao_client = DoubaoClient(
                        model=settings.DOUBAO_FAST_MODEL or None,
                        use_doubao_app=settings.DOUBAO_FAST_USE_APP_API,
                    )
            except Exception as e:
                logger.warning("[A4] DoubaoClient init failed: %s", e)

            try:
                if hunyuan_fetch_method == "api":
                    from app.core.fetchers.api.hunyuan_client import HunyuanClient

                    hunyuan_client = HunyuanClient(
                        model=settings.HUNYUAN_FAST_MODEL or None
                    )
                elif hunyuan_fetch_method == "browser":
                    logger.info(
                        "[A4] Yuanbao API client skipped; browser fallback active"
                    )
            except Exception as e:
                logger.warning("[A4] Yuanbao client init failed: %s", e)

            try:
                if _pf is None or "kimi" in _pf:
                    from app.core.fetchers.api.kimi_client import KimiClient

                    kimi_client = KimiClient(model=settings.MOONSHOT_FAST_MODEL or None)
            except Exception as e:
                logger.warning("[A4] KimiClient init failed: %s", e)

        # ── Browser handlers ──
        # fast mode: DeepSeek, plus Yuanbao when the legacy API is configured
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

            # Additional browsers run in full mode; legacy Yuanbao also falls
            # back here in fast mode before it can issue retired API requests.
            if fetch_mode == "full" or hunyuan_browser_fallback:
                try:
                    if fetch_mode == "full" and (_pf is None or "kimi" in _pf):
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
                    if hunyuan_fetch_method == "browser":
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
                    if fetch_mode == "full" and (_pf is None or "doubao" in _pf):
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

            def _single_answer_fetch_result(
                q_idx: int,
                enriched_result: dict[str, Any],
            ) -> dict[str, Any]:
                question = questions[q_idx]
                return {
                    "question_id": question.get("id", f"Q{q_idx}"),
                    "question_text": question.get("text", ""),
                    **_question_metadata_for_fetch_result(question),
                    "platform_results": [enriched_result],
                    "aio_platform_packets": _collect_aio_platform_packets(
                        [enriched_result]
                    ),
                }

            async def _extract_incremental_entity_signals(
                fetch_result: dict[str, Any],
                *,
                event_source: str,
            ) -> None:
                if (
                    realtime_entity_extraction_service is None
                    or realtime_entity_extraction_result is None
                ):
                    return
                try:
                    incremental = (
                        realtime_entity_extraction_service.extract_from_fetch_results(
                            [fetch_result]
                        )
                    )
                except Exception as extraction_err:
                    logger.warning(
                        "[A4] Realtime Amway entity extraction failed: %s",
                        extraction_err,
                    )
                    return

                existing_keys = {
                    (
                        str(signal.get("answer_id") or ""),
                        str(signal.get("entity_id") or ""),
                        str(signal.get("matched_text") or ""),
                    )
                    for signal in realtime_entity_extraction_result.get("signals") or []
                    if isinstance(signal, dict)
                }
                answer_signals = realtime_entity_extraction_result.setdefault(
                    "answer_signals", []
                )
                flat_signals = realtime_entity_extraction_result.setdefault(
                    "signals", []
                )
                known_answer_ids = {
                    str(answer_id)
                    for answer_id in realtime_entity_extraction_result.setdefault(
                        "realtime_answer_ids", []
                    )
                }

                for answer_record in incremental.get("answer_signals") or []:
                    if not isinstance(answer_record, dict):
                        continue
                    new_signals: list[dict[str, Any]] = []
                    for signal in answer_record.get("signals") or []:
                        if not isinstance(signal, dict):
                            continue
                        key = (
                            str(signal.get("answer_id") or ""),
                            str(signal.get("entity_id") or ""),
                            str(signal.get("matched_text") or ""),
                        )
                        if key in existing_keys:
                            continue
                        existing_keys.add(key)
                        new_signals.append(signal)
                    if not new_signals:
                        continue

                    answer_id = str(answer_record.get("answer_id") or "")
                    existing_record = next(
                        (
                            record
                            for record in answer_signals
                            if isinstance(record, dict)
                            and str(record.get("answer_id") or "") == answer_id
                        ),
                        None,
                    )
                    if existing_record is None:
                        existing_record = dict(answer_record)
                        existing_record["signals"] = []
                        answer_signals.append(existing_record)
                    existing_record["signals"].extend(new_signals)
                    flat_signals.extend(new_signals)
                    if answer_id and answer_id not in known_answer_ids:
                        known_answer_ids.add(answer_id)
                        realtime_entity_extraction_result["realtime_answer_ids"].append(
                            answer_id
                        )

                    stage_result_data = {
                        "answer_id": answer_id,
                        "question_id": answer_record.get("question_id"),
                        "question": answer_record.get("question"),
                        "platform": answer_record.get("platform"),
                        "event_source": event_source,
                        "signal_count": len(new_signals),
                        "is_realtime": True,
                        "signals": [
                            {
                                "entity_name": signal.get("entity_name"),
                                "entity_type": signal.get("entity_type"),
                                "matched_text": signal.get("matched_text"),
                                "relation_type": signal.get("relation_type"),
                                "term_origin": signal.get("term_origin"),
                                "evidence_text": signal.get("evidence_text"),
                                "answer_position": signal.get("answer_position"),
                            }
                            for signal in new_signals[:12]
                        ],
                    }
                    await send_stage_result(
                        session_id=session_id,
                        stage="EntityExtraction",
                        stage_name="实体关系抽取",
                        result_type="entity_extraction_signal",
                        data=stage_result_data,
                    )
                    await _persist_a4_stage_result(
                        state,
                        task_id=task_id,
                        stage="EntityExtraction",
                        stage_name="实体关系抽取",
                        result_type="entity_extraction_signal",
                        data=stage_result_data,
                    )

                realtime_entity_extraction_result["signal_count"] = len(flat_signals)
                realtime_entity_extraction_result["answer_signal_count"] = sum(
                    1
                    for record in answer_signals
                    if isinstance(record, dict) and record.get("signals")
                )

            async def _persist_incremental_fetch_result(
                q_idx: int,
                enriched_result: dict[str, Any],
                *,
                event_source: str,
            ) -> None:
                """Persist one completed answer before the full A4 batch finishes."""

                task_run_id = state.get("run_id")
                entity_id = state.get("entity_id")
                user_id = state.get("user_id")
                fetch_result = _single_answer_fetch_result(q_idx, enriched_result)
                if not (task_id and task_run_id and user_id):
                    await _extract_incremental_entity_signals(
                        fetch_result,
                        event_source=f"{event_source}_memory_result",
                    )
                    return

                try:
                    from uuid import UUID as _UUID

                    from app.core.database import AsyncSessionLocal
                    from app.services.fetch_run_platform_state_service import (
                        FetchRunPlatformStateService,
                    )

                    async with AsyncSessionLocal() as db:
                        state_service = FetchRunPlatformStateService(db)
                        await state_service.sync_fetch_results(
                            task_run_id=_UUID(str(task_run_id)),
                            task_id=_UUID(str(task_id)),
                            session_id=(_UUID(str(session_id)) if session_id else None),
                            entity_id=(_UUID(str(entity_id)) if entity_id else None),
                            user_id=_UUID(str(user_id)),
                            fetch_results=[fetch_result],
                        )
                        await db.commit()
                    await _extract_incremental_entity_signals(
                        fetch_result,
                        event_source=f"{event_source}_persisted_answer",
                    )
                except Exception as incremental_err:
                    logger.warning(
                        "[A4] Incremental %s result persist failed for Q%d: %s",
                        event_source,
                        q_idx + 1,
                        incremental_err,
                    )
                    await _extract_incremental_entity_signals(
                        fetch_result,
                        event_source=f"{event_source}_memory_result",
                    )

            async def _persist_incremental_browser_result(
                q_idx: int,
                raw_result: dict[str, Any],
            ) -> None:
                """Persist one completed browser answer before the platform finishes."""

                question = questions[q_idx]
                enriched_result = _attach_aio_platform_packet(
                    raw_result,
                    question=question,
                    request=aio_fetch_request,
                )
                await _persist_incremental_fetch_result(
                    q_idx,
                    enriched_result,
                    event_source="browser",
                )

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
                    message=_build_fast_phase_start_message(
                        total,
                        platform_filter or list(PlatformConstants.SUPPORTED_PLATFORMS),
                    ),
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

                api_success_total = 0
                tracked_tasks = [
                    asyncio.create_task(
                        _tracked_api_fetch_with_context(q_idx, platform, task, tracker)
                    )
                    for task, (q_idx, platform) in zip(api_tasks, api_task_map)
                ]

                # Persist and extract each answer as soon as it completes so the
                # console can show a live graph instead of waiting for all APIs.
                for completed_task in asyncio.as_completed(tracked_tasks):
                    q_idx, platform, result, result_err = await completed_task
                    if result_err is not None:
                        logger.error(
                            "[A4] API %s Q%d exception: %s",
                            platform,
                            q_idx + 1,
                            result_err,
                        )
                        enriched_result = _attach_aio_platform_packet(
                            {
                                "platform": platform,
                                "fetch_method": "api",
                                "success": False,
                                "error": str(result_err),
                            },
                            question=questions[q_idx],
                            request=aio_fetch_request,
                        )
                        question_results[q_idx].append(enriched_result)
                        await _persist_incremental_fetch_result(
                            q_idx,
                            enriched_result,
                            event_source="api",
                        )
                        continue

                    if result is None:
                        continue
                    await _record_a4_api_usage(
                        session_id=session_id,
                        task_id=str(task_id) if task_id else None,
                        question_id=_question_id_from_state_question(questions[q_idx]),
                        platform=platform,
                        result=result,
                    )
                    enriched_result = _attach_aio_platform_packet(
                        result,
                        question=questions[q_idx],
                        request=aio_fetch_request,
                    )
                    question_results[q_idx].append(enriched_result)
                    await _persist_incremental_fetch_result(
                        q_idx,
                        enriched_result,
                        event_source="api",
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
                    await _persist_incremental_browser_result(idx, r)

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
                                        "failure_layer": r.get("failure_layer"),
                                        "failure_reason": r.get("failure_reason"),
                                        "execution_stage": r.get("execution_stage"),
                                        "retryable": r.get("retryable"),
                                        "needs_handoff": r.get("needs_handoff"),
                                        "evidence_ref": r.get("evidence_ref"),
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

            # Additional browsers (full mode, plus legacy Yuanbao fallback).
            if fetch_mode == "full" or hunyuan_browser_fallback:
                kimi_requested = fetch_mode == "full" and (_pf is None or "kimi" in _pf)
                yuanbao_requested = hunyuan_fetch_method == "browser"
                doubao_requested = fetch_mode == "full" and (
                    _pf is None or "doubao" in _pf
                )

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
                pipeline_timeouts = [
                    _get_browser_pipeline_timeout(platform, total)
                    for platform in browser_task_platforms
                ]
                # AIO commonly exposes one physical Chromium surface. Its
                # configured semaphore may serialize every platform, so a
                # max(single timeout) batch deadline cancels valid queued work.
                # The sum is a safe upper bound for both serial and parallel
                # execution; each pipeline still keeps its own hard timeout.
                browser_batch_timeout = sum(pipeline_timeouts) + 30.0
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
                        **_question_metadata_for_fetch_result(question),
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
        baseline = _fetch_results_arg(tool_args.get("preserved_fetch_results"))
        if not baseline:
            baseline = state.get("preserved_fetch_results")
        pair_targeted_merge = bool(question_platform_targets)
        if retry_failed_only and not base_fetch_results and not baseline:
            raise RuntimeError(
                "补采缺少上一轮 A4 抓取结果，无法合并生成新的完整抓取 Artifact。"
            )
        if (
            (platform_filter or pair_targeted_merge)
            and baseline is None
            and base_fetch_results
        ):
            selected_platforms = (
                {str(platform).strip().lower() for platform in platform_filter}
                if platform_filter
                else None
            )
            baseline = _derive_preserved_fetch_results(
                current_questions=state_questions if retry_failed_only else questions,
                existing_fetch_results=base_fetch_results,
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
                    baseline_entry = baseline_map.pop(question_id)
                    old_platform_results = (
                        baseline_entry.get("platform_results", []) or []
                    )
                    combined_platform_results = (
                        new_platform_results + old_platform_results
                    )
                    merged_results.append(
                        {
                            "question_id": question_id,
                            "question_text": fetch_result.get("question_text", ""),
                            "platform_results": combined_platform_results,
                            "aio_platform_packets": _merge_aio_platform_packets(
                                _collect_aio_platform_packets(new_platform_results),
                                fetch_result.get("aio_platform_packets", []) or [],
                                baseline_entry.get("aio_platform_packets", []) or [],
                                _collect_aio_platform_packets(old_platform_results),
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

        merge_metadata: dict[str, Any] = {}
        if retry_failed_only or scoped_merge_active:
            merge_metadata = {
                "source": "supplemental_fetch_workflow",
                "merge_key": "question_id+platform",
                "base_pair_count": _count_fetch_pairs(base_fetch_results),
                "preserved_pair_count": _count_fetch_pairs(baseline or []),
                "overlay_pair_count": _count_fetch_pairs(fetch_results),
                "merged_pair_count": _count_fetch_pairs(final_fetch_results),
                "question_target_count": len(question_targets),
                "platforms": list(platform_filter or []),
            }

        merge_validation = validate_scoped_fetch_merge(
            platform_filter=platform_filter,
            preserved_results=baseline,
            merged_results=final_fetch_results,
        )
        if not merge_validation.passed:
            raise RuntimeError(merge_validation.reason)

        try:
            await _enrich_fetch_result_citation_domains(
                fetch_results=final_fetch_results,
                brand_profile=brand_profile,
                entity_id=str(state.get("entity_id") or "") or None,
            )
        except Exception as domain_enrichment_err:
            logger.warning(
                "[A4] Citation domain enrichment failed; continuing with raw citations: %s",
                domain_enrichment_err,
            )

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

        task_run_id = str(state.get("run_id") or "").strip()
        artifact_key = f"{session_id}_fetchResults_a4"
        if task_run_id and (
            state.get("monitoring_schedule_id") or state.get("headless_mode")
        ):
            artifact_key = f"{artifact_key}_{task_run_id}"
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
                "mergeMetadata": merge_metadata,
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
            headless_mode=bool(state.get("headless_mode")),
            retry_failed_only=retry_failed_only,
            scoped_merge_active=scoped_merge_active,
            question_targets=question_targets,
            successful_fetches=successful_fetches,
            total_fetches=total_fetches,
            fail_count=fail_count,
            platform_statuses=platform_statuses,
            fetch_mode=fetch_mode,
            merge_metadata=merge_metadata,
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
            artifact_failure_message = "答案抓取结果已生成，但官方结果写回失败，当前需要先修复写回后再生成分析报告。"
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
                    **monitoring_plan_update,
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

        await _persist_brand_intelligence_fetch_results(
            state,
            fetch_results=canonical_result["fetch_results"],
        )

        # 3b-1.2：实体抽取/圈层图谱已拆为独立节点（nodes_amway），
        # A4 只负责把实时抽取信号写入 state，由 amway_extract 节点消费。
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

        completion_progress_message = (
            "答案抓取完成，等待确认是否补采失败项或继续生成报告。"
            if bool(observation.get("requires_user_decision"))
            else (
                "答案抓取完成，正在准备实体关系抽取。"
                if _is_association_circle_context(state)
                else "答案抓取完成，正在准备生成分析报告。"
            )
        )
        update_dict: dict[str, Any] = {
            "a4_canonical_result": canonical_result,
            "a4_completion_observation": observation,
            "fetch_recovery_plan": dict(observation.get("recovery_plan") or {}),
            "fetch_results": canonical_result["fetch_results"],
            "realtime_entity_extraction_result": realtime_entity_extraction_result,
            "current_step": "A4",
            "progress": 0.6,
            "progress_message": completion_progress_message,
            "awaiting_user": False,
            "pending_confirmation": None,
            "pending_question_set_confirmation": None,
            "execution_status": "running",
        }
        # Clear platform_filter after use; scoped reruns should deterministically
        # reuse the official canonical result instead of stale transient filters.
        if platform_filter or pair_targeted_merge:
            update_dict["platform_filter"] = None
            update_dict["preserved_fetch_results"] = None
        update_dict.update(monitoring_plan_update)

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
        # 3b-1.2/1.3 拓扑链门：amway 圈层上下文链到独立的实体抽取节点
        # （断开「答案采集 → 实体抽取」连线则止于抓取）；其他上下文保持
        # A4 → A5 直链（断开「图谱构建 → 报告」连线则止于抓取）。
        should_chain_forward = artifact_validation.passed and not bool(
            observation.get("requires_user_decision")
        )
        association_circle_context = _is_association_circle_context(state)
        topology_extract_enabled = extract_chain_enabled(flow_topology)
        topology_report_enabled = report_chain_enabled(flow_topology)
        if (
            should_chain_forward
            and association_circle_context
            and not topology_extract_enabled
        ):
            update_dict["next_required_action"] = None
            update_dict["progress_message"] = (
                "画布已断开「答案采集 → 实体抽取」连线，本次运行止于答案抓取。"
            )
        elif (
            should_chain_forward
            and not association_circle_context
            and not topology_report_enabled
        ):
            update_dict["next_required_action"] = None
            update_dict["progress_message"] = (
                "画布已断开「图谱构建 → 报告」连线，本次运行止于图谱构建。"
            )
        if bool(observation.get("requires_user_decision")):
            update_dict["next_required_action"] = build_next_required_action(
                tool_name="ask_user",
                authority="authoritative_resume",
                reason="A4 已完成但存在失败项，需要用户确认补采或继续生成报告。",
                tool_args={
                    "message": (
                        "答案抓取已完成，但仍有部分平台或问题抓取失败。"
                        "请选择是继续补采失败项，还是先用当前成功结果生成报告。"
                    ),
                    "options": list(observation.get("followup_options") or []),
                },
                source_step="a4_answer_fetch",
                metadata={
                    "artifact_write_validated": True,
                    "requires_user_decision": True,
                    "failure_count": int(observation.get("failure_count") or 0),
                },
            )
        elif (
            should_chain_forward
            and association_circle_context
            and topology_extract_enabled
        ):
            update_dict["next_required_action"] = build_next_required_action(
                tool_name="amway_entity_extract",
                authority="authoritative_resume",
                reason="A4 已完成并成功写回结果，继续执行实体关系抽取。",
                source_step="a4_answer_fetch",
                metadata={
                    "headless_mode": bool(state.get("headless_mode")),
                    "artifact_write_validated": True,
                    "requires_user_decision": False,
                },
            )
        elif should_chain_forward and topology_report_enabled:
            report_type = (
                "panorama"
                if str(state.get("analysis_mode") or "").strip().lower() == "baseline"
                else "scenario"
            )
            update_dict["next_required_action"] = build_next_required_action(
                tool_name="analysis_report_skill",
                authority="authoritative_resume",
                reason="A4 已完成并成功写回结果，继续执行 A5 生成分析报告。",
                tool_args={"report_type": report_type},
                source_step="a4_answer_fetch",
                metadata={
                    "headless_mode": bool(state.get("headless_mode")),
                    "artifact_write_validated": True,
                    "requires_user_decision": False,
                },
            )
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
                from uuid import UUID as _UUID

                async with AsyncSessionLocal() as db:
                    if state.get("run_id"):
                        state_service = FetchRunPlatformStateService(db)
                        await state_service.mark_artifact_write_status(
                            task_run_id=_UUID(str(state.get("run_id"))),
                            status="failed",
                        )
            except Exception as te:
                logger.warning("[A4] Failed to mark A4 artifact/run status: %s", te)

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
        usage_fields = _api_usage_fields(
            response,
            fallback_model=str(getattr(client, "model", "") or "doubao"),
        )

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
                **usage_fields,
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
            **usage_fields,
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
        usage_fields = _api_usage_fields(
            response,
            fallback_model=str(getattr(client, "model", "") or "hunyuan"),
        )

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
                **usage_fields,
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
            **usage_fields,
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
        usage_fields = _api_usage_fields(
            response,
            fallback_model=str(getattr(client, "model", "") or "kimi"),
        )

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
                **usage_fields,
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
            **usage_fields,
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
    } or _should_stop_browser_platform_after_failure(
        {
            "success": False,
            "error_type": error_type,
            "failure_reason": failure_reason,
        }
    )
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
