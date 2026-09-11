"""A4/AIO answer-fetch tool contract.

This module is the stable tool-facing seam for answer fetching. The current
executor still runs in the backend and attaches to AIO through CDP; future AIO
runtime workers should replace only this tool's executor internals, not A4's
public contract.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Awaitable, Literal, cast

from app.core.config import settings
from app.schemas.platform_fetch_methods import resolve_platform_fetch_methods

logger = logging.getLogger(__name__)

AioPublicPlatform = Literal["doubao", "yuanbao", "kimi", "deepseek"]
AioExecutorPlatform = Literal["doubao", "hunyuan", "kimi", "deepseek"]
AioFetchMode = Literal["fast", "full"]
AioFetchMethod = Literal["api", "browser"]
AioPlatformStatus = Literal["result", "takeover_required", "skipped", "failed"]

PUBLIC_PLATFORM_IDS: tuple[AioPublicPlatform, ...] = (
    "doubao",
    "yuanbao",
    "kimi",
    "deepseek",
)

_PUBLIC_PLATFORM_DISPLAY_NAMES: dict[str, str] = {
    "doubao": "豆包",
    "yuanbao": "元宝",
    "hunyuan": "元宝",
    "kimi": "Kimi",
    "deepseek": "DeepSeek",
}

_PLATFORM_ALIASES: dict[str, AioPublicPlatform] = {
    "doubao": "doubao",
    "豆包": "doubao",
    "doubao_api": "doubao",
    "doubao_browser": "doubao",
    "yuanbao": "yuanbao",
    "hunyuan": "yuanbao",
    "元宝": "yuanbao",
    "yuanbao_api": "yuanbao",
    "yuanbao_browser": "yuanbao",
    "hunyuan_api": "yuanbao",
    "hunyuan_browser": "yuanbao",
    "kimi": "kimi",
    "kimi_api": "kimi",
    "kimi_browser": "kimi",
    "deepseek": "deepseek",
    "deep_seek": "deepseek",
    "deep seek": "deepseek",
    "deepseek_browser": "deepseek",
    "deepseek_api": "deepseek",
    "deepseek_web": "deepseek",
}

_PUBLIC_TO_EXECUTOR_PLATFORM: dict[AioPublicPlatform, AioExecutorPlatform] = {
    "doubao": "doubao",
    "yuanbao": "hunyuan",
    "kimi": "kimi",
    "deepseek": "deepseek",
}

_EXECUTOR_TO_PUBLIC_PLATFORM: dict[str, AioPublicPlatform] = {
    "doubao": "doubao",
    "hunyuan": "yuanbao",
    "yuanbao": "yuanbao",
    "kimi": "kimi",
    "deepseek": "deepseek",
}

_API_PUBLIC_PLATFORMS: set[AioPublicPlatform] = {"doubao", "yuanbao", "kimi"}
_FAST_BROWSER_PUBLIC_PLATFORMS: set[AioPublicPlatform] = {"deepseek"}


@dataclass(frozen=True, slots=True)
class AioAuthContext:
    """Long-lived auth identity for AIO browser state."""

    specta_user_id: str
    environment: str

    @property
    def context_key(self) -> str:
        return f"{self.environment}/{self.specta_user_id}"


@dataclass(frozen=True, slots=True)
class AioRunContext:
    """Per-analysis run identity for AIO extracted artifacts."""

    entity_id: str
    task_id: str
    run_id: str | None = None

    @property
    def context_key(self) -> str:
        return f"{self.entity_id}/{self.task_id}"


@dataclass(frozen=True, slots=True)
class AioAnswerFetchRequest:
    """Tool-level answer-fetch request."""

    session_id: str
    specta_user_id: str
    entity_id: str
    task_id: str
    run_id: str | None
    questions: list[dict[str, Any]]
    mode: AioFetchMode
    platforms: tuple[AioPublicPlatform, ...]
    auth_context: AioAuthContext
    run_context: AioRunContext
    raw_platform_filter: list[str] | None = None
    platform_fetch_methods: dict[str, str] | None = None


@dataclass(frozen=True, slots=True)
class AioPlatformFetchJob:
    """One platform job after mode/path routing."""

    public_platform: AioPublicPlatform
    executor_platform: AioExecutorPlatform
    browser_platform: AioPublicPlatform
    display_name: str
    method: AioFetchMethod
    question_count: int


@dataclass(frozen=True, slots=True)
class AioTakeoverRequiredPacket:
    """Tool output when one platform needs human takeover."""

    takeover_id: str
    platform: AioPublicPlatform
    reason_code: str
    surface_url: str | None
    target_url: str | None
    expires_at: str | None
    resume_policy: str = "manual_resume_gate"


@dataclass(frozen=True, slots=True)
class AioPlatformFetchResult:
    """Tool-level platform result packet."""

    platform: AioPublicPlatform
    status: AioPlatformStatus
    questions: list[dict[str, Any]] = field(default_factory=list)
    answers: list[dict[str, Any]] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    auth_state_updated: bool = False
    provenance: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    takeover: AioTakeoverRequiredPacket | None = None


BrowserTask = Awaitable[Any]


def normalize_public_platform_id(platform: Any) -> AioPublicPlatform | None:
    """Normalize user/API aliases into the public AIO platform ID."""

    value = str(platform or "").strip()
    if not value:
        return None
    return _PLATFORM_ALIASES.get(value.lower())


def normalize_public_platforms(platforms: Any) -> tuple[AioPublicPlatform, ...]:
    """Return a deduplicated public-platform tuple preserving input order."""

    if not platforms:
        return PUBLIC_PLATFORM_IDS
    if isinstance(platforms, str):
        platform_values = [platforms]
    else:
        try:
            platform_values = list(platforms)
        except TypeError:
            platform_values = [platforms]
    normalized: list[AioPublicPlatform] = []
    seen: set[str] = set()
    for raw in platform_values:
        public_platform = normalize_public_platform_id(raw)
        if not public_platform or public_platform in seen:
            continue
        normalized.append(public_platform)
        seen.add(public_platform)
    return tuple(normalized) or PUBLIC_PLATFORM_IDS


def to_executor_platform_id(platform: Any) -> AioExecutorPlatform:
    public_platform = normalize_public_platform_id(platform)
    if public_platform is None:
        value = str(platform or "").strip().lower()
        if value in _EXECUTOR_TO_PUBLIC_PLATFORM:
            return cast(AioExecutorPlatform, value)
        raise ValueError(f"Unsupported AIO platform: {platform!r}")
    return _PUBLIC_TO_EXECUTOR_PLATFORM[public_platform]


def to_public_platform_id(platform: Any) -> AioPublicPlatform:
    value = str(platform or "").strip().lower()
    public_platform = _EXECUTOR_TO_PUBLIC_PLATFORM.get(value)
    if public_platform is None:
        normalized = normalize_public_platform_id(value)
        if normalized is None:
            raise ValueError(f"Unsupported AIO platform: {platform!r}")
        public_platform = normalized
    return public_platform


def display_platform_name(platform: Any) -> str:
    value = str(platform or "").strip().lower()
    return _PUBLIC_PLATFORM_DISPLAY_NAMES.get(value, str(platform or ""))


class AioAnswerFetchTool:
    """AIO-backed answer-fetch tool facade used by the A4 executor."""

    def build_auth_context(self, state: dict[str, Any]) -> AioAuthContext:
        user_id = str(state.get("user_id") or state.get("session_id") or "anonymous")
        return AioAuthContext(
            specta_user_id=user_id,
            environment=settings.AIO_AUTH_ENV_SCOPE,
        )

    def build_run_context(self, state: dict[str, Any]) -> AioRunContext:
        return AioRunContext(
            entity_id=str(
                state.get("entity_id") or state.get("session_id") or "anonymous"
            ),
            task_id=str(state.get("task_id") or state.get("session_id") or "unknown"),
            run_id=str(state.get("run_id")) if state.get("run_id") else None,
        )

    def build_request(
        self,
        *,
        state: dict[str, Any],
        questions: list[dict[str, Any]],
        mode: str,
        platform_filter: Any = None,
    ) -> AioAnswerFetchRequest:
        auth_context = self.build_auth_context(state)
        run_context = self.build_run_context(state)
        normalized_mode: AioFetchMode = "full" if mode == "full" else "fast"
        platforms = normalize_public_platforms(platform_filter)
        if isinstance(platform_filter, str):
            raw_platform_filter = [platform_filter]
        elif platform_filter:
            try:
                raw_platform_filter = list(platform_filter)
            except TypeError:
                raw_platform_filter = [platform_filter]
        else:
            raw_platform_filter = None
        return AioAnswerFetchRequest(
            session_id=str(state.get("session_id") or ""),
            specta_user_id=auth_context.specta_user_id,
            entity_id=run_context.entity_id,
            task_id=run_context.task_id,
            run_id=run_context.run_id,
            questions=questions,
            mode=normalized_mode,
            platforms=platforms,
            auth_context=auth_context,
            run_context=run_context,
            raw_platform_filter=raw_platform_filter,
            platform_fetch_methods=(
                resolve_platform_fetch_methods(
                    state["platform_fetch_methods"], platforms=platforms,
                    fetch_mode=normalized_mode, explicit=True,
                ) if "platform_fetch_methods" in state and state["platform_fetch_methods"] is not None else None
            ),
        )

    def to_executor_platforms(
        self,
        platforms: Any,
    ) -> list[AioExecutorPlatform]:
        normalized = normalize_public_platforms(platforms)
        return [_PUBLIC_TO_EXECUTOR_PLATFORM[platform] for platform in normalized]

    def resolve_execution_paths(
        self,
        request: AioAnswerFetchRequest,
    ) -> tuple[list[AioPlatformFetchJob], list[AioPlatformFetchJob]]:
        api_jobs: list[AioPlatformFetchJob] = []
        browser_jobs: list[AioPlatformFetchJob] = []

        from app.core.fetchers.api.hunyuan_client import HunyuanClient
        legacy_yuanbao_browser = HunyuanClient.has_legacy_configuration(
            configured_url=settings.HUNYUAN_BASE_URL,
            configured_model=settings.HUNYUAN_FAST_MODEL or settings.HUNYUAN_MODEL,
        )
        methods = resolve_platform_fetch_methods(
            request.platform_fetch_methods, platforms=request.platforms,
            fetch_mode=request.mode, explicit=request.platform_fetch_methods is not None,
            legacy_yuanbao_browser=legacy_yuanbao_browser,
        )
        for public_platform in request.platforms:
            executor_platform = _PUBLIC_TO_EXECUTOR_PLATFORM[public_platform]
            if methods[public_platform] == "api":
                api_jobs.append(
                    self._build_job(request, public_platform, executor_platform, "api")
                )
            if methods[public_platform] == "browser":
                browser_jobs.append(
                    self._build_job(
                        request,
                        public_platform,
                        executor_platform,
                        "browser",
                    )
                )
        return api_jobs, browser_jobs

    def _build_job(
        self,
        request: AioAnswerFetchRequest,
        public_platform: AioPublicPlatform,
        executor_platform: AioExecutorPlatform,
        method: AioFetchMethod,
    ) -> AioPlatformFetchJob:
        return AioPlatformFetchJob(
            public_platform=public_platform,
            executor_platform=executor_platform,
            browser_platform=public_platform,
            display_name=display_platform_name(public_platform),
            method=method,
            question_count=len(request.questions),
        )

    def create_browser_client(
        self,
        *,
        platform: Any,
        state: dict[str, Any],
    ) -> Any:
        """Create the browser client selected by current runtime mode."""

        public_platform = to_public_platform_id(platform)
        session_name = public_platform
        if settings.AIO_ENABLED and settings.AIO_BASE_URL:
            from app.core.fetchers.browser.aio_connected_client import (
                AioConnectedBrowserClient,
            )

            auth_context = self.build_auth_context(state)
            run_context = self.build_run_context(state)
            return AioConnectedBrowserClient(
                session_name=session_name,
                workspace_id=auth_context.specta_user_id,
                task_id=run_context.task_id,
                platform=public_platform,
                purpose="a4_browser",
                auth_scope_id=auth_context.specta_user_id,
                run_scope_id=run_context.entity_id,
            )

        from app.core.fetchers.browser.playwright_client import PlaywrightBrowserClient

        run_context = self.build_run_context(state)
        return PlaywrightBrowserClient(
            session_name=session_name,
            task_id=run_context.task_id,
        )

    def create_browser_handler(
        self,
        *,
        platform: Any,
        browser_client: Any,
        session_id: str,
        run_id: str | None = None,
    ) -> Any:
        public_platform = to_public_platform_id(platform)
        if public_platform == "deepseek":
            from app.core.fetchers.browser.deepseek_handler import DeepSeekHandler

            return DeepSeekHandler(browser_client, session_id=session_id, run_id=run_id)
        if public_platform == "kimi":
            from app.core.fetchers.browser.kimi_handler import KimiHandler

            return KimiHandler(browser_client, session_id=session_id, run_id=run_id)
        if public_platform == "yuanbao":
            from app.core.fetchers.browser.yuanbao_handler import YuanbaoHandler

            return YuanbaoHandler(browser_client, session_id=session_id, run_id=run_id)
        if public_platform == "doubao":
            from app.core.fetchers.browser.doubao_handler import DoubaoHandler

            return DoubaoHandler(browser_client, session_id=session_id, run_id=run_id)
        raise ValueError(f"Unsupported AIO browser platform: {platform!r}")

    async def gather_browser_tasks(
        self,
        browser_tasks: list[BrowserTask],
        *,
        timeout_seconds: float | None = None,
    ) -> list[Any]:
        """Run browser platform jobs with the configured AIO concurrency cap."""

        if not browser_tasks:
            return []

        semaphore: asyncio.Semaphore | None = None
        if settings.AIO_ENABLED and settings.AIO_BASE_URL:
            max_parallel = max(1, settings.AIO_MAX_PARALLEL_BROWSER_SESSIONS)
            semaphore = asyncio.Semaphore(max_parallel)

        async def _bounded(task: BrowserTask) -> Any:
            if semaphore is None:
                return await task
            async with semaphore:
                return await task

        scheduled = [asyncio.create_task(_bounded(task)) for task in browser_tasks]
        pending: set[asyncio.Task[Any]] = set()

        try:
            if timeout_seconds is None:
                return await asyncio.gather(*scheduled, return_exceptions=True)

            done, pending = await asyncio.wait(scheduled, timeout=timeout_seconds)
            if pending:
                logger.warning(
                    "[A4] Browser task batch hit hard timeout (%.0fs); forcing %d pending task(s) to timeout",
                    timeout_seconds,
                    len(pending),
                )

            results: list[Any] = []
            for task in scheduled:
                if task in done:
                    try:
                        results.append(task.result())
                    except BaseException as exc:  # surfaced as gather-style result
                        results.append(exc)
                else:
                    task.cancel()
                    results.append(
                        asyncio.TimeoutError(
                            f"browser task batch exceeded {timeout_seconds:.0f}s hard timeout"
                        )
                    )
            return results
        finally:
            for task in scheduled:
                if not task.done():
                    task.cancel()
            # Drain every scheduled task, including cancellation that interrupts
            # asyncio.wait before its pending-set assignment completes.
            await asyncio.gather(*scheduled, return_exceptions=True)

    def build_result_packet(
        self,
        *,
        platform: Any,
        status: AioPlatformStatus,
        questions: list[dict[str, Any]] | None = None,
        answers: list[dict[str, Any]] | None = None,
        citations: list[dict[str, Any]] | None = None,
        evidence: list[dict[str, Any]] | None = None,
        auth_state_updated: bool = False,
        provenance: dict[str, Any] | None = None,
        errors: list[dict[str, Any]] | None = None,
        takeover: AioTakeoverRequiredPacket | None = None,
    ) -> AioPlatformFetchResult:
        return AioPlatformFetchResult(
            platform=to_public_platform_id(platform),
            status=status,
            questions=questions or [],
            answers=answers or [],
            citations=citations or [],
            evidence=evidence or [],
            auth_state_updated=auth_state_updated,
            provenance=provenance or {},
            errors=errors or [],
            takeover=takeover,
        )

    def classify_legacy_result_status(
        self,
        result: dict[str, Any],
    ) -> AioPlatformStatus:
        """Classify a legacy A4 platform result into the AIO packet status."""

        if result.get("success"):
            return "result"
        error_type = str(result.get("error_type") or "").strip().lower()
        if (
            result.get("skipped_by_user")
            or result.get("skipped_by_breaker")
            or error_type == "user_skipped"
        ):
            return "skipped"
        if (
            error_type == "takeover_required"
            or result.get("takeover_id")
            or result.get("surface_url")
        ):
            return "takeover_required"
        return "failed"

    def build_result_packet_from_legacy(
        self,
        *,
        result: dict[str, Any],
        question: dict[str, Any] | None = None,
        auth_context: AioAuthContext | None = None,
        run_context: AioRunContext | None = None,
    ) -> AioPlatformFetchResult:
        """Adapt the current A4 result dict into the new tool packet contract."""

        platform = result.get("platform")
        status = self.classify_legacy_result_status(result)
        answer = result.get("answer")
        answers = [answer] if isinstance(answer, dict) and result.get("success") else []
        citations = (
            result.get("citations") if isinstance(result.get("citations"), list) else []
        )
        evidence_ref = (
            result.get("evidence_ref")
            if isinstance(result.get("evidence_ref"), dict)
            else None
        )
        error = str(result.get("error") or "").strip()
        error_type = str(result.get("error_type") or "").strip()
        errors: list[dict[str, Any]] = []
        if status in {"failed", "skipped", "takeover_required"} and (
            error or error_type
        ):
            errors.append(
                {
                    "message": error,
                    "error_type": error_type or None,
                    "reason_code": result.get("reason_code") or error_type or None,
                    "target_url": result.get("target_url"),
                    "final_url": result.get("final_url"),
                    "probe_result": result.get("probe_result"),
                    "stop_platform": bool(result.get("stop_platform")),
                    "skipped_by_user": bool(result.get("skipped_by_user")),
                    "skipped_by_breaker": bool(result.get("skipped_by_breaker")),
                    "failure_layer": result.get("failure_layer"),
                    "failure_reason": result.get("failure_reason"),
                    "execution_stage": result.get("execution_stage"),
                    "retryable": result.get("retryable"),
                    "needs_handoff": result.get("needs_handoff"),
                    "evidence_ref": evidence_ref,
                }
            )
        takeover: AioTakeoverRequiredPacket | None = None
        if status == "takeover_required":
            takeover_platform = to_public_platform_id(platform)
            takeover = AioTakeoverRequiredPacket(
                takeover_id=str(
                    result.get("takeover_id")
                    or result.get("request_id")
                    or f"legacy:{takeover_platform}:unknown"
                ),
                platform=takeover_platform,
                reason_code=str(
                    result.get("reason_code") or error_type or "takeover_required"
                ),
                surface_url=(
                    str(result.get("surface_url"))
                    if result.get("surface_url") is not None
                    else None
                ),
                target_url=(
                    str(result.get("target_url"))
                    if result.get("target_url") is not None
                    else None
                ),
                expires_at=(
                    str(result.get("expires_at"))
                    if result.get("expires_at") is not None
                    else None
                ),
                resume_policy=str(result.get("resume_policy") or "manual_resume_gate"),
            )

        return self.build_result_packet(
            platform=platform,
            status=status,
            questions=[question] if question else [],
            answers=answers,
            citations=citations,
            evidence=[evidence_ref] if evidence_ref else [],
            auth_state_updated=bool(result.get("auth_state_updated")),
            provenance={
                "source": "aio_answer_fetch",
                "source_type": result.get("fetch_method") or "unknown",
                "requested_platform": result.get("requested_platform"),
                "requested_method": result.get("requested_method"),
                "actual_provider": result.get("actual_provider"),
                "provider_model": result.get("provider_model"),
                "web_search_supported": result.get("web_search_supported"),
                "web_search_executed": result.get("web_search_executed"),
                "reference_scope": result.get("reference_scope"),
                "protocol": result.get("protocol"),
                "platform_legacy_id": str(platform or ""),
                "duration": result.get("duration"),
                "auth_context": auth_context.context_key if auth_context else None,
                "run_context": run_context.context_key if run_context else None,
                "request_id": result.get("request_id"),
                "takeover_id": result.get("takeover_id"),
                "reason_code": result.get("reason_code") or error_type or None,
                "target_url": result.get("target_url"),
                "final_url": result.get("final_url"),
                "probe_result": result.get("probe_result"),
                "failure_layer": result.get("failure_layer"),
                "failure_reason": result.get("failure_reason"),
                "execution_stage": result.get("execution_stage"),
                "retryable": result.get("retryable"),
                "needs_handoff": result.get("needs_handoff"),
                "evidence_ref": evidence_ref,
            },
            errors=errors,
            takeover=takeover,
        )

    def attach_result_packet_to_legacy(
        self,
        *,
        result: dict[str, Any],
        question: dict[str, Any] | None = None,
        auth_context: AioAuthContext | None = None,
        run_context: AioRunContext | None = None,
    ) -> dict[str, Any]:
        """Return a legacy A4 result with the AIO packet attached."""

        enriched = dict(result)
        try:
            packet = self.build_result_packet_from_legacy(
                result=result,
                question=question,
                auth_context=auth_context,
                run_context=run_context,
            )
        except ValueError:
            return enriched
        enriched["aio_packet"] = asdict(packet)
        return enriched


def build_legacy_platform_configs() -> dict[str, dict[str, str]]:
    """Legacy A4 platform config map kept for existing downstream code."""

    return {
        "doubao": {"name": display_platform_name("doubao"), "method": "api"},
        "hunyuan": {"name": display_platform_name("yuanbao"), "method": "api"},
        "kimi": {"name": display_platform_name("kimi"), "method": "api"},
        "deepseek": {"name": display_platform_name("deepseek"), "method": "browser"},
    }


def resolve_platform_display_names(platforms: list[str]) -> str:
    return "、".join(display_platform_name(platform) for platform in platforms)


async def fetch_answers(
    questions: list,
    platforms: list[str] | None = None,
) -> list[dict]:
    """Backward-compatible async wrapper for legacy callers.

    The executable A4 route is still the LangGraph node. This wrapper now
    exposes the normalized tool contract instead of pretending to fetch directly.
    """

    tool = AioAnswerFetchTool()
    request = tool.build_request(
        state={"session_id": "legacy_direct_tool_call"},
        questions=[dict(q) for q in questions],
        mode="fast",
        platform_filter=platforms,
    )
    api_jobs, browser_jobs = tool.resolve_execution_paths(request)
    raise NotImplementedError(
        "Use the answer-fetch workflow node for execution; "
        f"aio_answer_fetch contract resolved {len(api_jobs)} api job(s) "
        f"and {len(browser_jobs)} browser job(s)."
    )


# Backward compatibility
FetchAgentTool = fetch_answers
