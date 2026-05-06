"""Shared browser execution flow and recovery helpers.

This module centralizes the browser-side answer-capture flow after a platform
handler has completed submission, and the shared recovery/handoff helpers used
by A4 browser execution.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app.core.fetchers.browser.failure_observability import (
    build_failure_contract,
    is_browser_context_closed_error,
)
from app.schemas.fetch import BrowserEvent, BrowserState, FetchResult, SearchReference
from app.workflow.browser_action_contract import wait_for_browser_action_resume

AsyncAnswerExtractor = Callable[[], Awaitable[str]]
AsyncReferenceExtractor = Callable[[], Awaitable[list[SearchReference]]]
AsyncHook = Callable[[], Awaitable[None]]
AsyncSendBrowserState = Callable[..., Awaitable[None]]
AsyncSendReply = Callable[..., Awaitable[None]]
AsyncEmitHandoff = Callable[..., Awaitable[str]]
AsyncWaitForOutcome = Callable[..., Awaitable[str | None]]
AsyncResumeAction = Callable[..., Awaitable[tuple[bool, str | None]]]
BuildFailureResult = Callable[..., dict[str, Any]]
AsyncCaptureEvidence = Callable[..., Awaitable[dict[str, Any] | None]]
BoolPredicate = Callable[[Any], bool]
AsyncRetryFetch = Callable[..., Awaitable[dict[str, Any]]]

logger = logging.getLogger(__name__)

_DEFAULT_STABLE_ROUNDS = 2
_DEFAULT_BLOCKER_CHECK_AFTER_SECONDS = 9


def _coerce_positive_int(value: Any, *, default: int, minimum: int = 1) -> int:
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return default
    if resolved < minimum:
        return default
    return resolved


@dataclass(slots=True)
class BrowserAnswerExecutionPlan:
    question: str
    intercept_task: asyncio.Task | None
    fallback_url: str
    parser_error_progress: float = 0.68
    blocker_progress: float = 0.72
    extract_progress: float = 0.9
    empty_answer_progress: float = 0.92
    max_wait: int = 60
    poll_interval: int = 3
    min_content_len: int = 0
    stable_rounds: int = _DEFAULT_STABLE_ROUNDS
    blocker_check_after_seconds: int = _DEFAULT_BLOCKER_CHECK_AFTER_SECONDS
    dump_keywords: list[str] | None = None
    parser_message_overrides: dict[str, str] | None = None
    before_dom_extract: AsyncHook | None = None
    extract_answer: AsyncAnswerExtractor | None = None
    extract_references: AsyncReferenceExtractor | None = None


@dataclass(slots=True)
class BrowserRecoveryOutcome:
    handled: bool = False
    retry_fetch: bool = False
    verify_recovery_increment: bool = False
    result: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class PendingBrowserAction:
    request_id: str
    action_type: str
    success_message: str
    timeout_message: str
    timeout_error_type: str
    resume_error_type: str = "resume_gate_failed"


async def execute_post_submit_capture_flow(
    handler: Any,
    plan: BrowserAnswerExecutionPlan,
) -> tuple[FetchResult | None, list[BrowserEvent]]:
    """Run the shared browser answer-capture flow after question submission."""

    events: list[BrowserEvent] = []
    answer_text = ""
    search_refs: list[SearchReference] = []
    source = "dom"
    stable_rounds = _coerce_positive_int(
        plan.stable_rounds,
        default=_DEFAULT_STABLE_ROUNDS,
        minimum=1,
    )
    blocker_check_after_seconds = _coerce_positive_int(
        plan.blocker_check_after_seconds,
        default=_DEFAULT_BLOCKER_CHECK_AFTER_SECONDS,
        minimum=1,
    )

    try:
        if plan.intercept_task:
            parsed = await plan.intercept_task
            if parsed and parsed.parse_ok and len(parsed.answer_text.strip()) >= 10:
                answer_text = parsed.answer_text
                search_refs = parsed.references
                source = "network"
                if not search_refs:
                    fallback_refs = await _try_extract_dom_references_after_network(
                        handler,
                        plan,
                    )
                    if fallback_refs:
                        search_refs = fallback_refs
                        source = "network+dom_refs"
            elif parsed and parsed.error_type:
                parser_events, handled = await handler._handle_browser_agent_parser_error(
                    parsed_error=parsed.error,
                    error_type=parsed.error_type,
                    progress=plan.parser_error_progress,
                    fallback_url=plan.fallback_url,
                    message_overrides=plan.parser_message_overrides,
                )
                events.extend(parser_events)
                if handled:
                    return None, events
                return None, events

        if not answer_text:
            prev_len, waited, blocker_decision = await handler._wait_for_content_with_browser_agent(
                max_wait=plan.max_wait,
                poll_interval=plan.poll_interval,
                min_content_len=plan.min_content_len,
                stable_rounds=stable_rounds,
                target_url=plan.fallback_url,
                blocker_check_after_seconds=blocker_check_after_seconds,
            )
            blocker_events, handled = await handler._handle_browser_agent_wait_blocker(
                blocker_decision,
                progress=plan.blocker_progress,
                fallback_url=plan.fallback_url,
            )
            events.extend(blocker_events)
            if handled:
                return None, events

            if prev_len == 0:
                await handler._dump_page_debug(
                    waited,
                    extra_keywords=plan.dump_keywords or [],
                )

            if plan.before_dom_extract:
                await plan.before_dom_extract()

            events.append(
                handler._create_event(
                    BrowserState.EXTRACTING,
                    "提取回答内容...",
                    progress=plan.extract_progress,
                )
            )
            answer_extractor = plan.extract_answer or handler._extract_answer_dom
            reference_extractor = (
                plan.extract_references or handler._extract_references_dom
            )
            answer_text = await answer_extractor()
            search_refs = await reference_extractor()

        empty_events, handled = await handler._handle_browser_agent_empty_answer(
            answer_text,
            progress=plan.empty_answer_progress,
            fallback_url=plan.fallback_url,
        )
        events.extend(empty_events)
        if handled:
            return None, events

        events.append(
            handler._create_event(
                BrowserState.EXTRACTING,
                "提取回答内容...",
                progress=plan.extract_progress,
            )
        )
        fetch_result = await handler._build_success_result(
            question=plan.question,
            answer_text=answer_text,
            search_references=search_refs,
            source=source,
        )
        return fetch_result, events
    except Exception as exc:
        tag = getattr(handler, "PLATFORM_KEY", "browser")
        logger.exception(
            "[%s] Shared post-submit capture flow failed: %s",
            str(tag).capitalize(),
            exc,
        )
        context_closed = is_browser_context_closed_error(exc)
        failure_reason = "browser_context_closed" if context_closed else "parser_error"
        error_type = "browser_context_closed" if context_closed else "fetch_loop_error"
        failure_layer = "client" if context_closed else "executor"
        retryable = context_closed
        evidence_ref = None
        capture_evidence = getattr(handler, "_capture_failure_evidence", None)
        if callable(capture_evidence):
            try:
                evidence_ref = await capture_evidence(
                    failure_reason=failure_reason,
                    execution_stage="fetch_loop",
                    extra_metadata={
                        "exception_type": exc.__class__.__name__,
                        "exception_message": str(exc),
                    },
                )
            except Exception:
                logger.exception(
                    "[%s] Failed to capture executor evidence for fetch-loop error",
                    str(tag).capitalize(),
                )
        display_name = (
            handler._platform_display_name()
            if callable(getattr(handler, "_platform_display_name", None))
            else "当前平台"
        )
        message = (
            f"{display_name}浏览器页面已关闭，正在重建页面后重试。"
            if context_closed
            else f"{display_name}抓取流程异常中断，请稍后重试。"
        )
        events.append(
            handler._create_event(
                BrowserState.ERROR,
                message,
                progress=0,
                error_type=error_type,
                **build_failure_contract(
                    failure_reason=failure_reason,
                    execution_stage="fetch_loop",
                    retryable=retryable,
                    needs_handoff=False,
                    failure_layer=failure_layer,
                    evidence_ref=evidence_ref,
                ),
            )
        )
        return None, events


async def _try_extract_dom_references_after_network(
    handler: Any,
    plan: BrowserAnswerExecutionPlan,
) -> list[SearchReference]:
    """Fallback to DOM reference extraction when network answer has no refs.

    Several web UIs stream answer text and source cards through different
    surfaces. Treating a successful network answer with zero parsed references
    as final loses citations that may already be visible in the DOM.
    """

    tag = getattr(handler, "PLATFORM_KEY", "browser")
    try:
        if plan.before_dom_extract:
            await plan.before_dom_extract()
        reference_extractor = plan.extract_references or handler._extract_references_dom
        refs = await reference_extractor()
        if refs:
            logger.info(
                "[%s] Network response had 0 refs; recovered %d DOM references",
                str(tag).capitalize(),
                len(refs),
            )
        else:
            logger.info(
                "[%s] Network response had 0 refs; DOM fallback also found none",
                str(tag).capitalize(),
            )
        return refs
    except Exception as exc:
        logger.warning(
            "[%s] DOM reference fallback after network response failed: %s",
            str(tag).capitalize(),
            exc,
        )
        return []


def infer_browser_action_requirement(
    *,
    platform_name: str,
    error_message: str | None,
    error_type: str | None,
) -> dict[str, str] | None:
    """Infer a human-solvable browser action from normalized browser failure."""

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


async def resume_browser_action(
    *,
    handler: Any,
    request_id: str,
    action_type: str,
    timeout: int,
) -> tuple[bool, str | None]:
    """Resume one browser handoff action via the shared contract."""

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


async def attempt_rate_limit_recovery(
    *,
    handler: Any,
    platform: str,
    platform_name: str,
    session_id: str | None,
    send_browser_state: AsyncSendBrowserState,
) -> BrowserRecoveryOutcome:
    """Attempt one shared rate-limit recovery for browser platforms."""

    if not hasattr(handler, "recover_after_rate_limit"):
        return BrowserRecoveryOutcome()

    if session_id:
        await send_browser_state(
            session_id=session_id,
            platform=platform,
            state="waiting_response",
            message=f"{platform_name} 触发限流，正在冷却后自动重试",
            progress=0.7,
            requires_action=False,
        )

    recovered = await handler.recover_after_rate_limit()
    if not recovered:
        return BrowserRecoveryOutcome()

    return BrowserRecoveryOutcome(handled=True, retry_fetch=True)


async def attempt_verify_recovery(
    *,
    handler: Any,
    platform: str,
    platform_name: str,
    question_id: str | None,
    question_text: str,
    session_id: str | None,
    user_id: str | None,
    run_id: str | None,
    error_message: str | None,
    duration: float,
    timeout: int,
    verify_recovery_count: int,
    max_verify_recoveries: int,
    should_defer_surface_open: BoolPredicate,
    emit_handoff: AsyncEmitHandoff,
    wait_for_outcome: AsyncWaitForOutcome,
    resume_action: AsyncResumeAction,
    send_browser_state: AsyncSendBrowserState,
    send_reply: AsyncSendReply,
    capture_evidence: AsyncCaptureEvidence,
    build_failure_result: BuildFailureResult,
) -> BrowserRecoveryOutcome:
    """Run shared verify recovery / handoff flow for browser handlers."""

    if not hasattr(handler, "recover_after_verify"):
        return BrowserRecoveryOutcome()

    if verify_recovery_count >= max_verify_recoveries:
        if session_id:
            await send_browser_state(
                session_id=session_id,
                platform=platform,
                state="error",
                message=f"{platform_name} 连续触发安全验证，本轮已跳过该平台并继续其他平台",
                progress=0.7,
                requires_action=False,
            )
            await send_reply(
                session_id,
                (
                    f"**{platform_name}** 连续多次触发安全验证，"
                    "本轮无法继续自动抓取该平台。我会继续完成其他平台采集，"
                    "并在后续报告中基于已成功的平台生成结果。"
                ),
                is_delta=True,
                is_new_round=True,
            )
            await send_reply(session_id, "", is_complete=True)
        return BrowserRecoveryOutcome(
            handled=True,
            result=build_failure_result(
                platform=platform,
                platform_name=platform_name,
                error=error_message or "安全验证未通过",
                error_type="verify",
                duration=duration,
                failure_reason="verify_required",
                execution_stage="resume_gate",
                retryable=False,
                needs_handoff=True,
                failure_layer="adapter",
                stop_platform=True,
            ),
        )

    recovered = False
    if session_id:
        should_open_surface = not should_defer_surface_open(handler)
        if not should_open_surface or await handler._open_headed_for_user_action(
            handler.URL
        ):
            request_id = await emit_handoff(
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
            resolution = await wait_for_outcome(request_id, timeout=timeout)
            if resolution == "completed":
                recovered, _ = await resume_action(
                    handler=handler,
                    request_id=request_id,
                    action_type="verify",
                    timeout=timeout,
                )
        else:
            recovered = False
    else:
        recovered = await handler.recover_after_verify()

    if recovered:
        if session_id:
            await send_browser_state(
                session_id=session_id,
                platform=platform,
                state="waiting_response",
                message=f"{platform_name} 验证已完成，正在继续抓取当前问题",
                progress=0.45,
                requires_action=False,
            )
        return BrowserRecoveryOutcome(
            handled=True,
            retry_fetch=True,
            verify_recovery_increment=True,
        )

    if session_id:
        await send_browser_state(
            session_id=session_id,
            platform=platform,
            state="error",
            message=f"{platform_name} 验证未完成或等待超时，本轮将跳过该平台",
            progress=0.35,
            requires_action=False,
        )
    evidence_ref = await capture_evidence(
        handler=handler,
        failure_reason="verify_required",
        execution_stage="resume_gate",
        question_id=question_id,
        question_text=question_text,
        extra_metadata={"action_type": "verify"},
    )
    return BrowserRecoveryOutcome(
        handled=True,
        result=build_failure_result(
            platform=platform,
            platform_name=platform_name,
            error=error_message or "验证未完成或等待超时",
            error_type="verify",
            duration=duration,
            failure_reason="verify_required",
            execution_stage="resume_gate",
            retryable=False,
            needs_handoff=True,
            failure_layer="executor",
            evidence_ref=evidence_ref,
            stop_platform=True,
        ),
    )


async def attempt_modal_recovery(
    *,
    handler: Any,
    platform: str,
    platform_name: str,
    question_id: str | None,
    question_text: str,
    session_id: str | None,
    user_id: str | None,
    run_id: str | None,
    duration: float,
    should_defer_surface_open: BoolPredicate,
    emit_handoff: AsyncEmitHandoff,
    wait_for_outcome: AsyncWaitForOutcome,
    send_browser_state: AsyncSendBrowserState,
    capture_evidence: AsyncCaptureEvidence,
    build_failure_result: BuildFailureResult,
) -> BrowserRecoveryOutcome:
    """Run shared modal detection / handoff recovery flow."""

    try:
        detected = await handler._detect_blocking_modal()
    except Exception:
        detected = ""

    if not detected:
        return BrowserRecoveryOutcome()

    if should_defer_surface_open(handler):
        opened = True
    else:
        opened = await handler._open_headed_for_user_action(handler.URL)
    if not opened:
        modal_reopen_evidence = await capture_evidence(
            handler=handler,
            failure_reason="modal_blocked",
            execution_stage="modal_gate",
            question_id=question_id,
            question_text=question_text,
            extra_metadata={"detected_modal": detected},
        )
        return BrowserRecoveryOutcome(
            handled=True,
            result=build_failure_result(
                platform=platform,
                platform_name=platform_name,
                error="打开浏览器窗口失败，请稍后重试",
                error_type="modal_reopen_failed",
                duration=duration,
                failure_reason="modal_blocked",
                execution_stage="modal_gate",
                retryable=False,
                needs_handoff=True,
                failure_layer="adapter",
                evidence_ref=modal_reopen_evidence,
            ),
        )

    modal_cleared = False
    if session_id:
        request_id = await emit_handoff(
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
        resolution = await wait_for_outcome(request_id, timeout=45)
        modal_cleared = resolution == "completed" and await handler._wait_for_modal_clear(
            timeout=45
        )
    else:
        modal_cleared = await handler._wait_for_modal_clear(timeout=480)

    if modal_cleared:
        if session_id:
            await send_browser_state(
                session_id=session_id,
                platform=platform,
                state="waiting_response",
                message=f"{platform_name} 弹窗已处理，正在继续抓取当前问题",
                progress=0.45,
                requires_action=False,
            )
        return BrowserRecoveryOutcome(handled=True, retry_fetch=True)

    modal_timeout_evidence = await capture_evidence(
        handler=handler,
        failure_reason="modal_blocked",
        execution_stage="modal_gate",
        question_id=question_id,
        question_text=question_text,
        extra_metadata={"detected_modal": detected},
    )
    return BrowserRecoveryOutcome(
        handled=True,
        result=build_failure_result(
            platform=platform,
            platform_name=platform_name,
            error="弹窗处理超时",
            error_type="modal_timeout",
            duration=duration,
            failure_reason="modal_blocked",
            execution_stage="modal_gate",
            retryable=False,
            needs_handoff=True,
            failure_layer="adapter",
            evidence_ref=modal_timeout_evidence,
            stop_platform=True,
        ),
    )


async def handle_browser_failure(
    *,
    handler: Any,
    platform: str,
    platform_name: str,
    question: str,
    question_id: str | None,
    session_id: str,
    user_id: str | None,
    run_id: str | None,
    pending_action: PendingBrowserAction | None,
    error_message: str | None,
    error_type: str | None,
    duration: float,
    question_count: int,
    timeout: int,
    is_retry: bool,
    verify_recovery_count: int,
    max_verify_recoveries: int,
    auth_state_updated: bool,
    should_defer_surface_open: BoolPredicate,
    emit_handoff: AsyncEmitHandoff,
    wait_for_outcome: AsyncWaitForOutcome,
    resume_action: AsyncResumeAction,
    send_browser_state: AsyncSendBrowserState,
    send_reply: AsyncSendReply,
    capture_evidence: AsyncCaptureEvidence,
    build_failure_result: BuildFailureResult,
    retry_fetch: AsyncRetryFetch,
) -> dict[str, Any] | None:
    """Resolve shared browser failure recovery before final terminal failure."""

    inferred_action = None
    if pending_action is None:
        inferred_action = infer_browser_action_requirement(
            platform_name=platform_name,
            error_message=error_message,
            error_type=error_type,
        )
        if inferred_action and session_id:
            if (
                inferred_action["action_type"] == "verify"
                and verify_recovery_count >= max_verify_recoveries
            ):
                inferred_action = None
            else:
                request_id = await emit_handoff(
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
                action_label = (
                    "验证"
                    if inferred_action["action_type"] == "verify"
                    else "登录"
                    if inferred_action["action_type"] == "login"
                    else "弹窗处理"
                )
                pending_action = PendingBrowserAction(
                    request_id=request_id,
                    action_type=inferred_action["action_type"],
                    success_message=f"{platform_name} {action_label}已完成，正在继续抓取当前问题",
                    timeout_message=f"{platform_name} {action_label}未完成或等待超时，本轮将跳过该平台",
                    timeout_error_type=timeout_error_type,
                )

    if pending_action is not None:
        if (
            pending_action.action_type == "verify"
            and verify_recovery_count >= max_verify_recoveries
        ):
            if session_id:
                await send_browser_state(
                    session_id=session_id,
                    platform=platform,
                    state="error",
                    message=f"{platform_name} 连续触发安全验证，本轮已跳过该平台并继续其他平台",
                    progress=0.7,
                    requires_action=False,
                )
                await send_reply(
                    session_id,
                    (
                        f"**{platform_name}** 连续多次触发安全验证，"
                        "本轮无法继续自动抓取该平台。我会继续完成其他平台采集，"
                        "并在后续报告中基于已成功的平台生成结果。"
                    ),
                    is_delta=True,
                    is_new_round=True,
                )
                await send_reply(session_id, "", is_complete=True)
            return build_failure_result(
                platform=platform,
                platform_name=platform_name,
                error=error_message or "安全验证未通过",
                error_type="verify",
                duration=duration,
                failure_reason="verify_required",
                execution_stage="resume_gate",
                retryable=False,
                needs_handoff=True,
                failure_layer="adapter",
                stop_platform=True,
            )

        resumed, resolution = await resume_action(
            handler=handler,
            request_id=pending_action.request_id,
            action_type=pending_action.action_type,
            timeout=timeout,
        )
        if resumed:
            if session_id:
                await send_browser_state(
                    session_id=session_id,
                    platform=platform,
                    state="waiting_response",
                    message=pending_action.success_message,
                    progress=0.45,
                    requires_action=False,
                )
            return await retry_fetch(
                verify_recovery_increment=pending_action.action_type == "verify",
                auth_state_updated=pending_action.action_type == "login",
            )
        if session_id:
            await send_browser_state(
                session_id=session_id,
                platform=platform,
                state="error",
                message=pending_action.timeout_message,
                progress=0.35,
                requires_action=False,
            )
        failure_error_type = (
            "user_skipped"
            if resolution == "skip"
            else (
                pending_action.resume_error_type
                if resolution == "completed"
                else pending_action.timeout_error_type
            )
        )
        blocker_reason = (
            "modal_blocked"
            if pending_action.action_type == "modal"
            else "auth_required"
            if pending_action.action_type == "login"
            else "verify_required"
            if pending_action.action_type == "verify"
            else "resume_gate_failed"
        )
        pending_evidence_ref = await capture_evidence(
            handler=handler,
            failure_reason=blocker_reason,
            execution_stage="resume_gate",
            question_id=question_id,
            question_text=question,
            extra_metadata={
                "resolution": resolution,
                "action_type": pending_action.action_type,
            },
        )
        return build_failure_result(
            platform=platform,
            platform_name=platform_name,
            error=pending_action.timeout_message,
            error_type=failure_error_type,
            duration=duration,
            failure_reason=blocker_reason,
            execution_stage="resume_gate",
            retryable=False,
            needs_handoff=True,
            failure_layer="executor",
            evidence_ref=pending_evidence_ref,
            reason_code=pending_action.action_type,
            target_url=getattr(handler, "URL", None),
            final_url=getattr(getattr(handler, "page", None), "url", None),
            probe_result=failure_error_type,
            request_id=pending_action.request_id,
            stop_platform=failure_error_type
            in {
                "user_skipped",
                "user_action_timeout",
                "resume_gate_failed",
                "modal_timeout",
            },
            skipped_by_user=failure_error_type == "user_skipped",
        )

    if error_type == "browser_context_closed" and not is_retry:
        if session_id:
            await send_browser_state(
                session_id=session_id,
                platform=platform,
                state="waiting_response",
                message=f"{platform_name} 浏览器页面已关闭，正在重建页面后重试",
                progress=0.45,
                requires_action=False,
            )

        client = getattr(handler, "client", None)
        close_client = getattr(client, "close", None)
        if callable(close_client):
            try:
                await close_client()
            except Exception as exc:
                logger.debug(
                    "[%s] Browser client close before context-closed retry failed: %s",
                    platform,
                    exc,
                )
        return await retry_fetch()

    if error_type == "rate_limit" and not is_retry and platform == "doubao":
        rate_limit_recovery = await attempt_rate_limit_recovery(
            handler=handler,
            platform=platform,
            platform_name=platform_name,
            session_id=session_id,
            send_browser_state=send_browser_state,
        )
        if rate_limit_recovery.result is not None:
            return rate_limit_recovery.result
        if rate_limit_recovery.retry_fetch:
            return await retry_fetch()

    if error_type == "verify" and platform == "doubao":
        verify_recovery = await attempt_verify_recovery(
            handler=handler,
            platform=platform,
            platform_name=platform_name,
            question_id=question_id,
            question_text=question,
            session_id=session_id,
            user_id=user_id,
            run_id=run_id,
            error_message=error_message,
            duration=duration,
            timeout=timeout,
            verify_recovery_count=verify_recovery_count,
            max_verify_recoveries=max_verify_recoveries,
            should_defer_surface_open=should_defer_surface_open,
            emit_handoff=emit_handoff,
            wait_for_outcome=wait_for_outcome,
            resume_action=resume_action,
            send_browser_state=send_browser_state,
            send_reply=send_reply,
            capture_evidence=capture_evidence,
            build_failure_result=build_failure_result,
        )
        if verify_recovery.result is not None:
            return verify_recovery.result
        if verify_recovery.retry_fetch:
            return await retry_fetch(
                verify_recovery_increment=verify_recovery.verify_recovery_increment
            )

    if not is_retry:
        modal_recovery = await attempt_modal_recovery(
            handler=handler,
            platform=platform,
            platform_name=platform_name,
            question_id=question_id,
            question_text=question,
            session_id=session_id,
            user_id=user_id,
            run_id=run_id,
            duration=duration,
            should_defer_surface_open=should_defer_surface_open,
            emit_handoff=emit_handoff,
            wait_for_outcome=wait_for_outcome,
            send_browser_state=send_browser_state,
            capture_evidence=capture_evidence,
            build_failure_result=build_failure_result,
        )
        if modal_recovery.result is not None:
            return modal_recovery.result
        if modal_recovery.retry_fetch:
            return await retry_fetch()

    return None
