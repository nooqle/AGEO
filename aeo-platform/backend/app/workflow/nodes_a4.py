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

from langgraph.types import Command

from app.workflow.state import AgentState
from app.workflow.events import (
    send_progress_event,
    send_reply_event,
    send_error_event,
    send_stage_result,
    send_browser_state_event,
)
from app.workflow.harness_validation import (
    build_harness_decision,
    decide_a4_completion_policy,
    validate_scoped_fetch_merge,
)
from app.workflow.runtime_policy_executor import build_next_required_action
from app.workflow.skill_state import (
    build_harness_decision_update,
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
PLATFORMS = {
    "doubao": {"name": "豆包", "method": "api"},
    "hunyuan": {"name": "元宝", "method": "api"},
    "kimi": {"name": "Kimi", "method": "api"},
    "deepseek": {"name": "DeepSeek", "method": "browser"},
}
_PLATFORM_FILTER_ALIASES = {
    "doubao": "doubao",
    "豆包": "doubao",
    "hunyuan": "hunyuan",
    "yuanbao": "hunyuan",
    "元宝": "hunyuan",
    "kimi": "kimi",
    "deepseek": "deepseek",
    "deep_seek": "deepseek",
    "deep seek": "deepseek",
}

import httpx

from app.core.constants import PlatformConstants, WorkflowConstants
from app.core.config import settings
from app.workflow.brand_mentions import content_mentions_brand
from app.workflow.browser_action_contract import (
    emit_browser_action_handoff,
    wait_for_browser_action_outcome,
    wait_for_browser_action_resume,
)

# Aliases from centralized constants
MAX_RETRIES = WorkflowConstants.API_MAX_RETRIES
RETRY_BACKOFF_BASE = WorkflowConstants.API_RETRY_BACKOFF_BASE
BROWSER_MAX_RETRIES = WorkflowConstants.BROWSER_MAX_RETRIES
MIN_PLATFORMS_REQUIRED = WorkflowConstants.MIN_PLATFORMS_REQUIRED


def _canonicalize_platform_id(platform: Any) -> str:
    """Normalize user/orchestrator platform IDs into A4 canonical keys."""

    if platform is None:
        return ""
    value = str(platform).strip()
    if not value:
        return ""
    return _PLATFORM_FILTER_ALIASES.get(value.lower(), value.lower())


def _normalize_platform_filter(platform_filter: Any) -> list[str] | None:
    """Return a deduplicated canonical platform filter preserving input order."""

    if not platform_filter:
        return None
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in platform_filter:
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

    return "、".join(
        PlatformConstants.PLATFORM_DISPLAY_NAMES.get(p, p) for p in platforms
    )


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
                f"Phase 1 完成: {_display_platform_names(api_platforms)} API "
                f"{api_success_total}/{api_task_count} 成功。开始 {browser_names} 浏览器采集..."
            )
        return (
            f"Phase 1 完成: {_display_platform_names(api_platforms)} API "
            f"{api_success_total}/{api_task_count} 成功。"
        )

    if browser_names:
        return f"启动浏览器采集：{browser_names}。"
    return "启动浏览器采集。"


def _get_aio_workspace_scope(state: AgentState) -> str:
    """Derive the workspace-level session reuse scope for AIO.

    Current Specta runtime does not yet expose a dedicated workspace UUID in A4
    state, so V1 uses the authenticated user scope when available, otherwise it
    falls back to the session ID. This keeps the behavior deterministic without
    inventing a second persistence channel.
    """

    return str(state.get("user_id") or state.get("session_id") or "anonymous")


def _create_browser_client(platform: str, state: AgentState):
    """Create the browser client selected by current runtime mode."""

    session_name = platform
    if settings.AIO_ENABLED and settings.AIO_BASE_URL:
        from app.core.fetchers.browser.aio_connected_client import (
            AioConnectedBrowserClient,
        )

        return AioConnectedBrowserClient(
            session_name=session_name,
            workspace_id=_get_aio_workspace_scope(state),
            task_id=str(state.get("task_id") or state.get("session_id") or "unknown"),
            platform=platform,
            purpose="a4_browser",
        )

    from app.core.fetchers.browser.playwright_client import PlaywrightBrowserClient

    return PlaywrightBrowserClient(session_name=session_name)


class _ProgressTracker:
    """Track per-platform completion during Phase 1 API fetch and emit progress."""

    def __init__(
        self,
        total_questions: int,
        active_platforms: list[str],
        session_id: str,
    ):
        self.total_questions = total_questions
        self.active_platforms = active_platforms
        self.session_id = session_id
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
    return bool(getattr(client, "aio_session_id", None))


def _get_browser_human_action_timeout(platform: str) -> float:
    """Worst-case budget for a browser question that needs human takeover."""

    return (
        _BROWSER_ACTION_WAIT_TIMEOUT_SECONDS
        + _BROWSER_ACTION_RESUME_BUFFER_SECONDS
        + _get_browser_timeout(platform)
    )


def _get_browser_pipeline_timeout(platform: str, question_count: int) -> float:
    """Scale the pipeline timeout to the platform's worst-case question budget."""

    configured_timeout = float(PlatformConstants.BROWSER_PIPELINE_TIMEOUT)
    if question_count <= 0:
        return configured_timeout

    first_question_timeout = max(300.0, _get_browser_human_action_timeout(platform))
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
    return max(configured_timeout, derived_timeout)


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
                    if (
                        overload_retries
                        > WorkflowConstants.ENGINE_OVERLOADED_MAX_RETRIES
                    ):
                        logger.warning(
                            "[A4] %s 429 (engine_overloaded) — exhausted %d overload retries",
                            platform,
                            WorkflowConstants.ENGINE_OVERLOADED_MAX_RETRIES,
                        )
                        break
                    wait = (
                        WorkflowConstants.ENGINE_OVERLOADED_BASE_WAIT
                        + overload_retries * 5.0
                        + random.uniform(0, 3)
                    )
                    logger.warning(
                        "[A4] %s 429 (engine_overloaded), waiting %.1fs (overload retry %d/%d)",
                        platform,
                        wait,
                        overload_retries,
                        WorkflowConstants.ENGINE_OVERLOADED_MAX_RETRIES,
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
    # _fetch_from_browser signature: handler, question, brand_profile, platform, platform_name, browser_state
    platform = args[3] if len(args) > 3 else "unknown"
    platform_name = args[4] if len(args) > 4 else platform
    handler = args[0] if args else None

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
        if _is_aio_browser_handler(handler):
            return await fetch_fn(*args, **kwargs)

        result = await asyncio.wait_for(
            fetch_fn(*args, **kwargs),
            timeout=timeout,
        )
        return result
    except asyncio.TimeoutError:
        logger.warning("[A4] Browser %s timed out after %.0fs", platform, timeout)
        await _cleanup_browser_client()

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
        await _cleanup_browser_client()

        return {
            "platform": platform,
            "platform_name": platform_name,
            "fetch_method": "browser",
            "success": False,
            "error": str(e),
        }


def _build_duration_msg(fetch_mode: str, question_count: int) -> str:
    """Build user-visible duration message dynamically from PlatformConstants."""
    all_names = "、".join(
        PlatformConstants.PLATFORM_DISPLAY_NAMES[p]
        for p in PlatformConstants.SUPPORTED_PLATFORMS
    )
    platform_count = len(PlatformConstants.SUPPORTED_PLATFORMS)

    if fetch_mode == "full":
        if settings.AIO_ENABLED and settings.AIO_BASE_URL:
            pipelines = " / ".join(
                PlatformConstants.PLATFORM_DISPLAY_NAMES[p]
                for p in PlatformConstants.SUPPORTED_PLATFORMS
            )
            schedule_hint = f"{pipelines} 各平台依次采集"
        else:
            pipelines = " / ".join(
                PlatformConstants.PLATFORM_DISPLAY_NAMES[p]
                for p in PlatformConstants.SUPPORTED_PLATFORMS
            )
            schedule_hint = f"{pipelines} 各平台串行采集，{platform_count} 条流水线并行"
        return (
            f"开始向{all_names} {platform_count} 个平台提问，共 {question_count} 个问题。\n\n"
            f"- 采集模式：**完整采集**（{platform_count} 平台全浏览器）\n"
            f"- {schedule_hint}\n"
            f"- 预计总耗时约 10-20 分钟\n\n"
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
    - full: All 4 platforms via Browser only, no API       (~10-20 min)
    """
    session_id = state["session_id"]
    questions = state.get("questions", [])
    brand_profile = state.get("brand_profile") or {}
    fetch_mode = state.get("fetch_mode") or "fast"
    tool_args = state.get("tool_call_args") or {}
    requested_platforms = tool_args.get("platforms") or []
    normalized_requested_platforms = _normalize_platform_filter(requested_platforms)
    # 显式 tool_args.platforms 优先于历史 state.platform_filter，避免旧范围覆盖当前用户意图。
    raw_platform_filter = normalized_requested_platforms or state.get("platform_filter")
    platform_filter = _normalize_platform_filter(raw_platform_filter)
    if platform_filter:
        logger.info(
            "[A4] Platform filter active: raw=%s canonical=%s",
            raw_platform_filter,
            platform_filter,
        )

    logger.info("[A4] fetch_mode=%s, questions=%d", fetch_mode, len(questions))

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
                    progress=0.55,
                    message=f"开始抓取 {len(questions)} 个问题的答案（{mode_label}）",
                )
        except Exception as te:
            logger.warning("[A4] TaskService start milestone failed: %s", te)

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
                    from app.core.fetchers.browser.deepseek_handler import (
                        DeepSeekHandler,
                    )

                    deepseek_browser_client = _create_browser_client("deepseek", state)
                    deepseek_handler = DeepSeekHandler(
                        deepseek_browser_client,
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
                        from app.core.fetchers.browser.kimi_handler import KimiHandler

                        kimi_browser_client = _create_browser_client("kimi", state)
                        kimi_browser_handler = KimiHandler(
                            kimi_browser_client,
                            session_id=session_id,
                            run_id=state.get("run_id"),
                        )
                        browser_clients.append(kimi_browser_client)
                        logger.info("[A4] Kimi browser handler initialized")

                except Exception as e:
                    logger.warning("[A4] Kimi browser init failed: %s", e)

                try:
                    if _pf is None or "hunyuan" in _pf:
                        from app.core.fetchers.browser.yuanbao_handler import (
                            YuanbaoHandler,
                        )

                        yuanbao_browser_client = _create_browser_client(
                            "yuanbao", state
                        )
                        yuanbao_handler = YuanbaoHandler(
                            yuanbao_browser_client,
                            session_id=session_id,
                            run_id=state.get("run_id"),
                        )
                        browser_clients.append(yuanbao_browser_client)
                        logger.info("[A4] Yuanbao browser handler initialized")

                except Exception as e:
                    logger.warning("[A4] Yuanbao browser init failed: %s", e)

                try:
                    if _pf is None or "doubao" in _pf:
                        from app.core.fetchers.browser.doubao_handler import (
                            DoubaoHandler as DoubaoWebHandler,
                        )

                        doubao_browser_client = _create_browser_client("doubao", state)
                        doubao_browser_handler = DoubaoWebHandler(
                            doubao_browser_client,
                            session_id=session_id,
                            run_id=state.get("run_id"),
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
                    message=f"Phase 1: {total} 个问题 × 豆包、元宝、Kimi API，批量并行抓取中...",
                )

                api_tasks = []
                api_task_map: list[tuple[int, str]] = []  # (question_idx, platform)
                for idx, question in enumerate(questions):
                    q_text = question.get("text", "")
                    if doubao_client is not None:
                        api_tasks.append(
                            _throttled_retry_fetch(
                                _fetch_from_doubao,
                                doubao_client,
                                q_text,
                                brand_profile,
                                platform="doubao",
                                method="api",
                            )
                        )
                        api_task_map.append((idx, "doubao"))
                    if hunyuan_client is not None:
                        api_tasks.append(
                            _throttled_retry_fetch(
                                _fetch_from_hunyuan,
                                hunyuan_client,
                                q_text,
                                brand_profile,
                                platform="hunyuan",
                                method="api",
                            )
                        )
                        api_task_map.append((idx, "hunyuan"))
                    if kimi_client is not None:
                        api_tasks.append(
                            _throttled_retry_fetch(
                                _fetch_from_kimi,
                                kimi_client,
                                q_text,
                                brand_profile,
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
                            {
                                "platform": platform,
                                "fetch_method": "api",
                                "success": False,
                                "error": str(result),
                            }
                        )
                    else:
                        question_results[q_idx].append(result)
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
                    q_text = question.get("text", "")

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
                        brand_profile,
                        platform,
                        platform_name,
                        BrowserState,
                        timeout=question_timeout,
                        session_id=session_id,
                        user_id=(
                            str(state.get("user_id")) if state.get("user_id") else None
                        ),
                        run_id=state.get("run_id"),
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
                        breaker.record_failure()

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
            browser_task_clients = []
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
                browser_task_clients.append(deepseek_browser_client)
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
                    browser_task_clients.append(kimi_browser_client)
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
                    browser_task_clients.append(yuanbao_browser_client)
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
                    browser_task_clients.append(doubao_browser_client)
                elif doubao_requested:
                    logger.warning(
                        "[A4] Phase 2: Doubao skipped (handler=%s, client=%s)",
                        doubao_browser_handler,
                        doubao_browser_client,
                    )

            if browser_tasks:
                active_browser_pipeline_count = max(len(browser_task_platforms), 1)
                logger.info(
                    "[A4] Phase 2: Starting %d browser pipeline(s)...",
                    len(browser_tasks),
                )
                if settings.AIO_ENABLED and settings.AIO_BASE_URL:
                    logger.info(
                        "[A4] Phase 2: AIO runtime detected, executing browser pipelines sequentially to avoid shared-browser focus contention"
                    )
                    browser_all_results = []
                    for task, platform, browser_client in zip(
                        browser_tasks,
                        browser_task_platforms,
                        browser_task_clients,
                    ):
                        logger.info(
                            "[A4] Phase 2: Sequential browser pipeline start platform=%s",
                            platform,
                        )
                        try:
                            browser_all_results.append(await task)
                        except BaseException as exc:
                            browser_all_results.append(exc)
                        finally:
                            try:
                                await browser_client.close()
                                logger.info(
                                    "[A4] Phase 2: Sequential browser pipeline closed platform=%s",
                                    platform,
                                )
                            except BaseException as close_exc:
                                logger.debug(
                                    "[A4] Browser client close failed after platform=%s: %s",
                                    platform,
                                    close_exc,
                                )
                else:
                    browser_all_results = await asyncio.gather(
                        *browser_tasks, return_exceptions=True
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
                        question_results[idx].append(
                            {
                                "platform": platform,
                                "fetch_method": "browser",
                                "success": False,
                                "error": str(browser_batch),
                            }
                        )
                else:
                    for q_idx, r in browser_batch:
                        question_results[q_idx].append(r)
                        if r.get("success"):
                            browser_success_total += 1

            logger.info(
                "[A4] Phase 2 (Browser) done: %d succeeded", browser_success_total
            )

            # Build final fetch_results list
            for idx, question in enumerate(questions):
                question_id = question.get("id", f"Q{idx}")
                question_text = question.get("text", "")
                platform_results = question_results[idx]
                q_success = sum(1 for r in platform_results if r.get("success"))
                logger.info(
                    "[A4] Q%d/%d: %d platforms succeeded", idx + 1, total, q_success
                )
                fetch_results.append(
                    {
                        "question_id": question_id,
                        "question_text": question_text,
                        "platform_results": platform_results,
                    }
                )

        finally:
            for bc in browser_clients:
                try:
                    await bc.close()
                except BaseException as e:
                    logger.debug("[A4] Browser client close failed: %s", e)

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
                    platform_fetch_stats[pname] = {
                        "completed": 0,
                        "total": 0,
                        "mentions": 0,
                    }
                platform_fetch_stats[pname]["total"] += 1
                if p.get("success"):
                    platform_fetch_stats[pname]["completed"] += 1
                    answer = p.get("answer", {})
                    if isinstance(answer, dict) and answer.get("has_brand_mention"):
                        platform_fetch_stats[pname]["mentions"] += 1

        for pname, pstats in platform_fetch_stats.items():
            p_status = "success" if pstats["completed"] > 0 else "failed"
            await send_stage_result(
                session_id,
                "A4",
                "数据抓取",
                result_type="platform_status",
                data={
                    "platforms": [
                        {
                            "platform": pname,
                            "status": p_status,
                            "questions_completed": pstats["completed"],
                            "questions_total": pstats["total"],
                            "mention_count": pstats["mentions"],
                            "error": (
                                None
                                if p_status == "success"
                                else f"{pname} 部分抓取失败"
                            ),
                        }
                    ],
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

        # When platform_filter is active, adjust the minimum
        # threshold to the number of requested platforms (min 1), so that a
        # single-platform scoped fetch doesn't trigger a spurious degradation notice.
        effective_min = (
            min(MIN_PLATFORMS_REQUIRED, len(platform_filter))
            if platform_filter
            else MIN_PLATFORMS_REQUIRED
        )

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
            success_rate = (
                (stats["success"] / stats["total"] * 100) if stats["total"] > 0 else 0
            )
            platform_summary.append(
                f"- **{platform}**: {stats['success']}/{stats['total']} 成功 ({success_rate:.0f}%)"
            )

        detailed_response = f"""✅ **答案抓取完成**

我已针对模拟问题在主流 AI 平台进行了答案抓取，获取「{brand_name}」在 AI 平台中的曝光情况：

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

**⏭️ 下一步**
答案抓取已完成。我会基于当前抓取结果立即继续生成分析报告。报告生成后，您可以再决定是否继续做引用内容置信度评估或进入后续画像分析。"""

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

        # When platform_filter is active, merge new platform results with preserved baseline results.
        final_fetch_results = fetch_results
        baseline = state.get("preserved_fetch_results")
        if platform_filter and baseline is None and state.get("fetch_results"):
            baseline = []
            selected_platforms = {str(platform).lower() for platform in platform_filter}
            for existing_entry in state.get("fetch_results") or []:
                kept_platform_results = [
                    platform_result
                    for platform_result in existing_entry.get("platform_results", [])
                    if str(platform_result.get("platform") or "").lower()
                    not in selected_platforms
                ]
                if kept_platform_results:
                    baseline.append(
                        {
                            "question_id": existing_entry.get("question_id", ""),
                            "question_text": existing_entry.get("question_text", ""),
                            "platform_results": kept_platform_results,
                        }
                    )
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
                    merged.append(
                        {
                            "question_id": qid,
                            "question_text": fr.get("question_text", ""),
                            "platform_results": combined_pr,
                        }
                    )
                else:
                    merged.append(fr)

            # Add any remaining baseline entries (questions not in new results)
            for qid, br in baseline_map.items():
                merged.append(br)

            final_fetch_results = merged
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
        completion_decision = decide_a4_completion_policy(
            success_count=len(successful_platforms),
            fail_count=fail_count,
            effective_min=effective_min,
            platform_filter=platform_filter,
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
                    fetch_results=final_fetch_results,
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
                            },
                        },
                    )
            except Exception as te:
                logger.warning("[A4] TaskService milestone failed: %s", te)

        update_dict: dict[str, Any] = {
            "fetch_results": final_fetch_results,
            "current_step": "A4",
            "progress": 0.6,
        }
        # Clear platform_filter after use; scoped reruns should deterministically
        # continue into A5 instead of relying on a dead boolean flag.
        if platform_filter:
            update_dict["platform_filter"] = None
            update_dict["preserved_fetch_results"] = None
            update_dict["next_required_action"] = build_next_required_action(
                tool_name="analysis_report_skill",
                tool_args={"report_type": state.get("analysis_mode") or "persona"},
                reason="答案抓取定向重跑完成后需要刷新分析报告。",
                reply_text="定向重跑已完成，继续刷新分析报告。",
                source_step="A4",
                metadata={
                    "trigger": "scoped_rerun_completed",
                    "platform_filter": list(platform_filter or []),
                },
            )

        if len(successful_platforms) == 0:
            update_dict["error_info"] = {
                "step": "A4",
                "error": "所有平台数据获取均失败",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        update_dict.update(build_validation_result_update(state, merge_validation))
        update_dict.update(
            build_harness_decision_update(
                {**state, **update_dict},
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
                from app.services.task_service import TaskService
                from uuid import UUID as _UUID

                async with AsyncSessionLocal() as db:
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
                "fetch_results": fetch_results,
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
                "has_brand_mention": _check_brand_mention(answer_text, brand_profile),
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


async def _fetch_from_hunyuan(
    client, question: str, brand_profile: dict
) -> dict[str, Any]:
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
                "has_brand_mention": _check_brand_mention(answer_text, brand_profile),
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


async def _fetch_from_kimi(
    client, question: str, brand_profile: dict
) -> dict[str, Any]:
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
                "has_brand_mention": _check_brand_mention(answer_text, brand_profile),
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


def _infer_browser_action_requirement(
    *,
    platform_name: str,
    error_message: str | None,
    error_type: str | None,
) -> dict[str, str] | None:
    """Infer one browser-action requirement from normalized fetch failures."""

    message = (error_message or "").strip()
    lower_message = message.lower()
    normalized_error_type = (error_type or "").strip().lower()

    verify_markers = [
        "verify",
        "captcha",
        "人机验证",
        "安全验证",
        "完成验证",
        "图片验证",
    ]
    if normalized_error_type == "verify" or any(
        marker in lower_message or marker in message for marker in verify_markers
    ):
        return {
            "state": "waiting_for_login",
            "action_type": "verify",
            "message": f"{platform_name} 触发安全验证，请在浏览器窗口完成验证后继续",
            "action_hint": f"请在弹出的浏览器窗口中完成 {platform_name} 验证，完成后点击“我已完成”",
            "reply_markdown": (
                f"**{platform_name}** 触发了安全验证\n\n"
                "请在浏览器窗口中完成验证。完成后回到聊天卡片点击“我已完成”，我会继续接管当前问题。"
            ),
        }

    login_markers = [
        "permission_denied",
        "requirelogin",
        "require login",
        "need login",
        "please login",
        "please log in",
        "sign in",
        "log in",
        "请登录",
        "登录后",
        "未登录",
        "需要登录",
    ]
    login_error_types = {
        "permission_denied",
        "login_required",
        "unauthorized",
        "requirelogin",
        "require_login",
    }
    if normalized_error_type in login_error_types or any(
        marker in lower_message or marker in message for marker in login_markers
    ):
        return {
            "state": "waiting_for_login",
            "action_type": "login",
            "message": f"检测到 {platform_name} 需要登录，请在浏览器窗口中完成登录",
            "action_hint": f"请在弹出的浏览器窗口中完成 {platform_name} 登录，完成后点击“我已完成”",
            "reply_markdown": (
                f"**{platform_name}** 需要登录\n\n"
                "请在浏览器窗口中完成登录。完成后回到聊天卡片点击“我已完成”，我会继续接管抓取。"
            ),
        }

    modal_markers = ["弹窗", "协议", "terms", "privacy", "modal", "dialog"]
    if normalized_error_type == "modal" or any(
        marker in lower_message or marker in message for marker in modal_markers
    ):
        return {
            "state": "waiting_for_modal",
            "action_type": "modal",
            "message": f"检测到 {platform_name} 页面弹窗阻碍了抓取，请在浏览器窗口中操作",
            "action_hint": "请在弹出的浏览器窗口中关闭弹窗或同意协议，完成后点击“我已完成”",
            "reply_markdown": (
                f"**{platform_name}** 页面弹窗阻碍了抓取\n\n"
                "请在浏览器中关闭弹窗或同意协议。完成后回到聊天卡片点击“我已完成”，我会继续接管抓取。"
            ),
        }

    return None


async def _resume_after_browser_action(
    *,
    handler: Any,
    request_id: str,
    action_type: str,
    timeout: int = int(_BROWSER_ACTION_WAIT_TIMEOUT_SECONDS),
) -> tuple[bool, str | None]:
    """Resume one browser action using the unified contract."""

    completion_callback = None
    ready_timeout = 45
    skip_readiness_probe = False

    if action_type == "verify" and hasattr(handler, "recover_after_verify"):

        async def _recover_verify() -> bool:
            return bool(await handler.recover_after_verify(prepare_window=False))

        completion_callback = _recover_verify
        ready_timeout = 300
    elif action_type == "modal":
        ready_timeout = 30

    return await wait_for_browser_action_resume(
        request_id=request_id,
        handler=handler,
        action_type=action_type,
        timeout=timeout,
        ready_timeout=ready_timeout,
        on_completed=completion_callback,
        skip_readiness_probe=skip_readiness_probe,
    )


async def _fetch_from_browser(
    handler,
    question: str,
    brand_profile: dict,
    platform: str,
    platform_name: str,
    browser_state,
    session_id: str = "",
    user_id: str | None = None,
    run_id: str | None = None,
    _is_retry: bool = False,
    _verify_recovery_count: int = 0,
) -> dict[str, Any]:
    start_time = datetime.now(timezone.utc)
    result_data = None
    error_message = None
    error_type = ""
    max_verify_recoveries = 3
    pending_action: dict[str, Any] | None = None

    try:
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
                pending_action = {
                    "request_id": request_id,
                    "action_type": event.action_type or "login",
                    "success_message": f"{platform_name} 登录已完成，正在继续抓取当前问题",
                    "timeout_message": f"{platform_name} 登录未完成或等待超时，本轮将跳过该平台",
                    "timeout_error_type": "user_action_timeout",
                    "resume_error_type": "resume_gate_failed",
                }
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
                pending_action = {
                    "request_id": request_id,
                    "action_type": event.action_type or "modal",
                    "success_message": f"{platform_name} 弹窗已处理，正在继续抓取当前问题",
                    "timeout_message": f"{platform_name} 弹窗未处理完成，本轮将跳过该平台",
                    "timeout_error_type": "modal_timeout",
                    "resume_error_type": "resume_gate_failed",
                }
                break

            if event.state == browser_state.ERROR:
                error_message = event.message or event.error or "抓取失败"
                if event.error_type:
                    error_type = event.error_type

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
                "has_brand_mention": _check_brand_mention(answer_text, brand_profile),
            },
            "citations": [ref.model_dump() for ref in result_data.search_references],
            "duration": duration,
        }

    inferred_action = None
    if pending_action is None:
        inferred_action = _infer_browser_action_requirement(
            platform_name=platform_name,
            error_message=error_message,
            error_type=error_type,
        )
        if inferred_action and session_id:
            if (
                inferred_action["action_type"] == "verify"
                and _verify_recovery_count >= max_verify_recoveries
            ):
                inferred_action = None
            else:
                request_id = await emit_browser_action_handoff(
                    session_id=session_id,
                    platform=platform,
                    state=inferred_action["state"],
                    action_type=inferred_action["action_type"],
                    message=inferred_action["message"],
                    action_hint=inferred_action["action_hint"],
                    progress=0.35,
                    reply_markdown=inferred_action["reply_markdown"],
                    run_id=run_id,
                    handler=handler,
                    user_id=user_id,
                    target_url=getattr(handler, "URL", None),
                )
                timeout_error_type = (
                    "modal_timeout"
                    if inferred_action["action_type"] == "modal"
                    else "user_action_timeout"
                )
                pending_action = {
                    "request_id": request_id,
                    "action_type": inferred_action["action_type"],
                    "success_message": (
                        f"{platform_name} {'验证' if inferred_action['action_type'] == 'verify' else '登录' if inferred_action['action_type'] == 'login' else '弹窗处理'}已完成，正在继续抓取当前问题"
                    ),
                    "timeout_message": (
                        f"{platform_name} {'验证' if inferred_action['action_type'] == 'verify' else '登录' if inferred_action['action_type'] == 'login' else '弹窗处理'}未完成或等待超时，本轮将跳过该平台"
                    ),
                    "timeout_error_type": timeout_error_type,
                    "resume_error_type": "resume_gate_failed",
                }

    if pending_action is not None:
        if (
            pending_action["action_type"] == "verify"
            and _verify_recovery_count >= max_verify_recoveries
        ):
            logger.warning(
                "[A4] %s verify challenge exceeded max recoveries (%d), giving up on current question",
                platform_name,
                max_verify_recoveries,
            )
            if session_id:
                await send_browser_state_event(
                    session_id=session_id,
                    platform=platform,
                    state="error",
                    message=f"{platform_name} 连续触发安全验证，本轮已跳过该平台并继续其他平台",
                    progress=0.7,
                    requires_action=False,
                )
                await send_reply_event(
                    session_id,
                    (
                        f"**{platform_name}** 连续多次触发安全验证，"
                        "本轮无法继续自动抓取该平台。我会继续完成其他平台采集，"
                        "并在后续报告中基于已成功的平台生成结果。"
                    ),
                    is_delta=True,
                    is_new_round=True,
                )
                await send_reply_event(session_id, "", is_complete=True)
            return {
                "platform": platform,
                "platform_name": platform_name,
                "fetch_method": "browser",
                "success": False,
                "error": error_message or "安全验证未通过",
                "error_type": "verify",
                "stop_platform": True,
                "duration": duration,
            }

        resumed, resolution = await _resume_after_browser_action(
            handler=handler,
            request_id=pending_action["request_id"],
            action_type=pending_action["action_type"],
            timeout=int(_BROWSER_ACTION_WAIT_TIMEOUT_SECONDS),
        )
        if resumed:
            if session_id:
                await send_browser_state_event(
                    session_id=session_id,
                    platform=platform,
                    state="waiting_response",
                    message=pending_action["success_message"],
                    progress=0.45,
                    requires_action=False,
                )
            return await _fetch_from_browser(
                handler,
                question,
                brand_profile,
                platform,
                platform_name,
                browser_state,
                session_id=session_id,
                user_id=user_id,
                run_id=run_id,
                _is_retry=True,
                _verify_recovery_count=(
                    _verify_recovery_count + 1
                    if pending_action["action_type"] == "verify"
                    else _verify_recovery_count
                ),
            )
        if session_id:
            await send_browser_state_event(
                session_id=session_id,
                platform=platform,
                state="error",
                message=pending_action["timeout_message"],
                progress=0.35,
                requires_action=False,
            )
        failure_error_type = (
            "user_skipped"
            if resolution == "skip"
            else (
                pending_action["resume_error_type"]
                if resolution == "completed"
                else pending_action["timeout_error_type"]
            )
        )
        return {
            "platform": platform,
            "platform_name": platform_name,
            "fetch_method": "browser",
            "success": False,
            "error": pending_action["timeout_message"],
            "error_type": failure_error_type,
            "stop_platform": failure_error_type
            in {
                "user_skipped",
                "user_action_timeout",
                "resume_gate_failed",
                "modal_timeout",
            },
            "skipped_by_user": failure_error_type == "user_skipped",
            "duration": (datetime.now(timezone.utc) - start_time).total_seconds(),
        }

    # -- Failure path: try platform-specific recovery first --
    if (
        error_type == "rate_limit"
        and not _is_retry
        and platform == "doubao"
        and hasattr(handler, "recover_after_rate_limit")
    ):
        logger.info(
            "[A4] %s rate limited, attempting one automatic recovery", platform_name
        )
        if session_id:
            await send_browser_state_event(
                session_id=session_id,
                platform=platform,
                state="waiting_response",
                message=f"{platform_name} 触发限流，正在冷却后自动重试",
                progress=0.7,
                requires_action=False,
            )
        recovered = await handler.recover_after_rate_limit()
        if recovered:
            return await _fetch_from_browser(
                handler,
                question,
                brand_profile,
                platform,
                platform_name,
                browser_state,
                session_id=session_id,
                user_id=user_id,
                run_id=run_id,
                _is_retry=True,
            )

    if (
        error_type == "verify"
        and platform == "doubao"
        and hasattr(handler, "recover_after_verify")
    ):
        if _verify_recovery_count >= max_verify_recoveries:
            logger.warning(
                "[A4] %s verify challenge exceeded max recoveries (%d), giving up on current question",
                platform_name,
                max_verify_recoveries,
            )
            if session_id:
                await send_browser_state_event(
                    session_id=session_id,
                    platform=platform,
                    state="error",
                    message=f"{platform_name} 连续触发安全验证，本轮已跳过该平台并继续其他平台",
                    progress=0.7,
                    requires_action=False,
                )
                await send_reply_event(
                    session_id,
                    (
                        f"**{platform_name}** 连续多次触发安全验证，"
                        "本轮无法继续自动抓取该平台。我会继续完成其他平台采集，"
                        "并在后续报告中基于已成功的平台生成结果。"
                    ),
                    is_delta=True,
                    is_new_round=True,
                )
                await send_reply_event(session_id, "", is_complete=True)
            return {
                "platform": platform,
                "platform_name": platform_name,
                "fetch_method": "browser",
                "success": False,
                "error": error_message or "安全验证未通过",
                "error_type": error_type,
                "stop_platform": True,
                "duration": duration,
            }

        logger.info(
            "[A4] %s verify challenge detected, waiting for user to clear it (attempt %d/%d)",
            platform_name,
            _verify_recovery_count + 1,
            max_verify_recoveries,
        )
        if session_id:
            recovered = False
            should_open_surface = not _should_defer_aio_takeover_open(handler)
            if not should_open_surface or await handler._open_headed_for_user_action(
                handler.URL
            ):
                request_id = await emit_browser_action_handoff(
                    session_id=session_id,
                    platform=platform,
                    state="waiting_for_login",
                    action_type="verify",
                    message=f"{platform_name} 触发安全验证，请在浏览器窗口完成验证后继续",
                    action_hint=f"请在弹出的浏览器窗口中完成 {platform_name} 验证，完成后点击“我已完成”",
                    progress=0.35,
                    reply_markdown=(
                        f"**{platform_name}** 触发了安全验证\n\n"
                        f"请在浏览器窗口中完成验证。完成后回到聊天卡片点击“我已完成”，我会继续接管当前问题。"
                    ),
                    run_id=run_id,
                    handler=handler,
                    user_id=user_id,
                    target_url=getattr(handler, "URL", None),
                )
                resolution = await wait_for_browser_action_outcome(
                    request_id, timeout=int(_BROWSER_ACTION_WAIT_TIMEOUT_SECONDS)
                )
                if resolution == "completed":
                    recovered = await handler.recover_after_verify(prepare_window=False)
                elif resolution == "skip":
                    recovered = False
            else:
                recovered = False
        else:
            recovered = await handler.recover_after_verify()
        if recovered:
            if session_id:
                await send_browser_state_event(
                    session_id=session_id,
                    platform=platform,
                    state="waiting_response",
                    message=f"{platform_name} 验证已完成，正在继续抓取当前问题",
                    progress=0.45,
                    requires_action=False,
                )
            return await _fetch_from_browser(
                handler,
                question,
                brand_profile,
                platform,
                platform_name,
                browser_state,
                session_id=session_id,
                user_id=user_id,
                run_id=run_id,
                _is_retry=True,
                _verify_recovery_count=_verify_recovery_count + 1,
            )
        if session_id:
            await send_browser_state_event(
                session_id=session_id,
                platform=platform,
                state="error",
                message=f"{platform_name} 验证未完成或等待超时，本轮将跳过该平台",
                progress=0.35,
                requires_action=False,
            )

    # -- Failure path: diagnose if a blocking modal caused the failure --
    if not _is_retry:
        try:
            detected = await handler._detect_blocking_modal()
        except Exception:
            detected = ""

        if detected:
            logger.info(
                "[A4] %s fetch failed, modal detected: %s — alerting user",
                platform_name,
                detected,
            )
            if _should_defer_aio_takeover_open(handler):
                opened = True
            else:
                opened = await handler._open_headed_for_user_action(handler.URL)
            if not opened:
                return {
                    "platform": platform,
                    "platform_name": platform_name,
                    "fetch_method": "browser",
                    "success": False,
                    "error": "打开浏览器窗口失败，请稍后重试",
                    "error_type": "modal_reopen_failed",
                    "duration": (
                        datetime.now(timezone.utc) - start_time
                    ).total_seconds(),
                }

            modal_cleared = False
            if session_id:
                request_id = await emit_browser_action_handoff(
                    session_id=session_id,
                    platform=platform,
                    state="waiting_for_modal",
                    action_type="modal",
                    message=f"检测到 {platform_name} 页面弹窗阻碍了抓取，请在浏览器窗口中操作",
                    action_hint="请在弹出的浏览器窗口中关闭弹窗或同意协议，完成后点击“我已完成”",
                    progress=0.35,
                    reply_markdown=(
                        f"**{platform_name}** 页面弹窗阻碍了抓取\n\n"
                        f"请在浏览器中关闭弹窗或同意协议。完成后回到聊天卡片点击“我已完成”，我会继续接管抓取。"
                    ),
                    run_id=run_id,
                    handler=handler,
                    user_id=user_id,
                    target_url=getattr(handler, "URL", None),
                )
                resolution = await wait_for_browser_action_outcome(
                    request_id, timeout=int(_BROWSER_ACTION_WAIT_TIMEOUT_SECONDS)
                )
                modal_cleared = (
                    resolution == "completed"
                    and await handler._wait_for_modal_clear(timeout=45)
                )
            else:
                modal_cleared = await handler._wait_for_modal_clear(timeout=480)
            if modal_cleared:
                logger.info(
                    "[A4] %s modal cleared by user, retrying fetch", platform_name
                )
                return await _fetch_from_browser(
                    handler,
                    question,
                    brand_profile,
                    platform,
                    platform_name,
                    browser_state,
                    session_id=session_id,
                    user_id=user_id,
                    run_id=run_id,
                    _is_retry=True,
                )
            else:
                return {
                    "platform": platform,
                    "platform_name": platform_name,
                    "fetch_method": "browser",
                    "success": False,
                    "error": "弹窗处理超时",
                    "error_type": "modal_timeout",
                    "stop_platform": True,
                    "duration": (
                        datetime.now(timezone.utc) - start_time
                    ).total_seconds(),
                }

    stop_platform = error_type in {
        "user_skipped",
        "user_action_timeout",
        "resume_gate_failed",
        "modal_timeout",
    }
    return {
        "platform": platform,
        "platform_name": platform_name,
        "fetch_method": "browser",
        "success": False,
        "error": error_message or "抓取失败",
        "error_type": error_type,
        "stop_platform": stop_platform,
        "skipped_by_user": error_type == "user_skipped",
        "duration": duration,
    }


def _check_brand_mention(content: str, brand_profile: dict[str, Any]) -> bool:
    """Check if brand is mentioned in content."""
    return content_mentions_brand(content, brand_profile)
