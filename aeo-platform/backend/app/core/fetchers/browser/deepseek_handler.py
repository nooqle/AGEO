"""DeepSeek browser handler.

NOTE: All eval() calls in this module are Playwright's page.evaluate() API,
which executes JavaScript in the browser context for DOM interaction.
This is the standard Playwright pattern, not Python's built-in eval().
"""

import asyncio
import json
import logging
from typing import Any, AsyncGenerator
from urllib.parse import urlparse, urlunparse

from app.core.config import settings
from app.core.fetchers.browser.base_handler import BaseBrowserHandler
from app.core.fetchers.browser.browser_executor import (
    BrowserAnswerExecutionPlan,
    execute_post_submit_capture_flow,
)
from app.core.fetchers.browser.failure_observability import (
    build_failure_contract,
    is_browser_context_closed_error,
)
from app.core.fetchers.browser.parsers.base import BaseResponseParser
from app.core.fetchers.browser.parsers.sse import DeepSeekSSEParser
from app.schemas.fetch import (
    BrowserEvent,
    BrowserState,
    Platform,
    SearchReference,
)

logger = logging.getLogger(__name__)


class DeepSeekHandler(BaseBrowserHandler):
    """DeepSeek browser-based handler.

    Uses Playwright to interact with DeepSeek Web UI.
    """

    URL = "https://chat.deepseek.com/"
    PLATFORM = Platform.DEEPSEEK
    PLATFORM_KEY = "deepseek"
    BROWSER_READY_URL_PATTERNS = ("chat.deepseek.com",)
    BROWSER_LOGIN_URL_PATTERNS = ("sign_in", "login", "auth")
    BROWSER_READY_HINTS = ("联网搜索", "new chat", "textarea")
    BROWSER_LOGIN_HINTS = (
        "scan with wechat to login",
        "send code",
        "phone number",
        "verification code",
        "二维码",
        "手机号",
    )
    BROWSER_LATE_BLOCKER_HINTS = (
        "scan with wechat to login",
        "verification",
        "人机验证",
        "安全验证",
    )
    RISK_CONTROL_MARKERS = (
        "请检查网络后重试",
        "浏览器运行环境异常",
        "当前浏览器运行环境异常",
        "运行环境",
        "switch execution environments and try again",
    )
    PAGE_RUNTIME_RISK_FAILURE_REASON = "page_runtime_retry_or_risk_control"
    REFERENCE_TARGET_COUNT = 15
    REFERENCE_EXTRACTION_LIMIT = 20

    _DEFAULTS: dict = {
        "input": "textarea",
        "input_ready": "textarea, [contenteditable='true']",
        "answer": "div.ds-markdown",
        "reference_links": [
            "[class*='reference'] a[href^='http']",
            "[class*='citation'] a[href^='http']",
            "[class*='source'] a[href^='http']",
            ".search-result a[href^='http']",
            "[class*='result'] a[href^='http']",
            "[class*='web'] a[href^='http']",
        ],
        "citation_strip": "[class*='cite'], [class*='citation'], [class*='ref-num'], sup, a.ds-markdown-cite, a[data-index]",
        "new_chat_text": "新对话",
        "web_search_texts": ["联网搜索", "联网"],
        "reference_expand_texts": ["引用", "来源", "References", "Sources"],
    }

    def _resolve_interaction_mode(self) -> str:
        raw_mode = str(settings.DEEPSEEK_AIO_INTERACTION_MODE or "").strip().lower()
        aliases = {
            "gui": "gui_actions",
            "visual": "gui_actions",
            "vnc": "gui_actions",
            "cdp": "cdp_dom",
            "dom": "cdp_dom",
            "playwright": "cdp_dom",
        }
        return aliases.get(raw_mode, raw_mode or "cdp_dom")

    def _should_use_aio_gui_actions(self) -> bool:
        return (
            self._resolve_interaction_mode() == "gui_actions"
            and bool(getattr(self.client, "aio_session_id", None))
        )

    def _interaction_metadata(self) -> dict[str, Any]:
        configured_mode = self._resolve_interaction_mode()
        return {
            "interaction_mode": (
                "gui_actions" if self._should_use_aio_gui_actions() else "cdp_dom"
            ),
            "configured_interaction_mode": configured_mode,
            "aio_gui_actions_available": bool(
                getattr(self.client, "aio_session_id", None)
            ),
        }

    def _build_runtime_diagnostics_metadata(self) -> dict[str, Any]:
        metadata = super()._build_runtime_diagnostics_metadata()
        metadata.update(self._interaction_metadata())
        return metadata

    def _get_response_parser(self) -> BaseResponseParser | None:
        return DeepSeekSSEParser()

    # DeepSeek uses a single selector for answer, override content_check_js
    def _content_check_js(self) -> str:
        """DeepSeek uses single 'answer' selector (div.ds-markdown)."""
        answer_sel = json.dumps(self._sel("answer"), ensure_ascii=False)
        return f"""() => {{
            const msgs = document.querySelectorAll({answer_sel});
            const last = msgs[msgs.length - 1];
            return last ? String(last.textContent.length) : '0';
        }}"""

    async def fetch(self, question: str) -> AsyncGenerator:
        """Fetch answer from DeepSeek Web."""
        self._refresh_selectors()
        try:
            # Step 1: Initializing
            yield self._create_event(BrowserState.INITIALIZING, "初始化浏览器...", progress=0.1)

            # Step 2: Navigate or start new chat
            yield self._create_event(BrowserState.NAVIGATING, f"正在访问 {self.URL}...", progress=0.2)
            page = self.client.page
            fast_path_ok = False
            if page is not None and "chat.deepseek.com" in (page.url or ""):
                try:
                    new_chat_text = self._sel("new_chat_text")
                    new_chat = page.get_by_text(new_chat_text, exact=False).first
                    if await new_chat.count() > 0:
                        old_url = page.url
                        await new_chat.click()
                        # Verify URL change instead of blind sleep
                        for _ in range(4):
                            await asyncio.sleep(0.5)
                            if page.url != old_url:
                                break
                        fast_path_ok = True
                        logger.info("[DeepSeek] Fast path: clicked %s (url_changed=%s)", new_chat_text, page.url != old_url)
                except Exception as e:
                    logger.debug("[DeepSeek] %s click failed (%s), falling back to navigate",
                                 self._sel("new_chat_text"), e)

            if not fast_path_ok and await self._reuse_existing_aio_surface(self.URL):
                fast_path_ok = True

            if not fast_path_ok:
                open_result = await self.client.open(self.URL, headed=False)
                if not open_result.get("success"):
                    yield self._create_event(
                        BrowserState.ERROR,
                        f"浏览器打开失败: {open_result.get('error', '未知错误')}",
                        progress=0,
                    )
                    return
                await asyncio.sleep(3)

            if self.client.page:
                logger.info("[DeepSeek] Page URL: %s", self.client.page.url)

            preflight_events, should_abort = await self._run_browser_agent_preflight(
                progress=0.28,
                url=self.URL,
            )
            for event in preflight_events:
                yield event
            if should_abort:
                return

            # Step 3: Ensure web search is ON
            yield self._create_event(BrowserState.ENABLING_SEARCH, "确认联网搜索已开启...", progress=0.5)
            if self.client.page is not None:
                if self._should_use_aio_gui_actions():
                    await self._ensure_web_search_on_via_aio_gui_actions()
                else:
                    await self._ensure_web_search_on()

            # Step 5: Start network interception (before submit)
            yield self._create_event(BrowserState.SUBMITTING, f"提交问题: {question[:30]}...", progress=0.6)
            intercept_config = self._get_intercept_config()
            parser = self._get_response_parser()
            intercept_task = None
            if intercept_config and parser and self.client.page:
                intercept_task = asyncio.create_task(
                    self._intercept_and_wait(intercept_config, parser)
                )

            # Step 5b: Submit question
            submitted = False
            baseline_probe = await self._capture_submission_probe(question)
            using_gui_actions = self._should_use_aio_gui_actions()
            if using_gui_actions:
                submitted = await self._submit_question_via_aio_gui_actions(
                    question,
                    baseline_probe,
                )

            if not submitted:
                if using_gui_actions:
                    logger.info(
                        "[DeepSeek] AIO GUI submission not confirmed; trying CDP DOM fallback"
                    )
                submitted = await self._submit_question_via_cdp_dom(
                    question,
                    baseline_probe,
                )

            if not submitted:
                logger.warning(
                    "[DeepSeek] Submission could not be confirmed; skipping DOM wait for this question"
                )
                evidence_ref = await self._capture_failure_evidence(
                    failure_reason="submission_not_confirmed",
                    execution_stage="submit_question",
                    extra_metadata={
                        "answer_length": 0,
                        "baseline_submission_probe": baseline_probe,
                        "last_submission_probe": getattr(
                            self, "_last_submission_probe", None
                        ),
                        **self._interaction_metadata(),
                    },
                )
                yield self._create_event(
                    BrowserState.ERROR,
                    "提交后页面未进入回答状态，本题已跳过",
                    progress=0,
                    error_type="submission_not_confirmed",
                    **build_failure_contract(
                        failure_reason="submission_not_confirmed",
                        execution_stage="submit_question",
                        retryable=False,
                        needs_handoff=False,
                        failure_layer="adapter",
                        evidence_ref=evidence_ref,
                    ),
                )
                return

            yield self._create_event(BrowserState.WAITING_RESPONSE, "等待 AI 回复...", progress=0.7)
            fetch_result, events = await execute_post_submit_capture_flow(
                self,
                BrowserAnswerExecutionPlan(
                    question=question,
                    intercept_task=intercept_task,
                    fallback_url=self.URL,
                    max_wait=50,
                    poll_interval=3,
                    min_content_len=0,
                    stable_rounds=2,
                    blocker_check_after_seconds=9,
                    dump_keywords=["ds-"],
                    extract_references=self._extract_references,
                ),
            )
            for event in events:
                yield event
            if fetch_result is None:
                return

            yield self._create_event(BrowserState.COMPLETED, "抓取完成", progress=1.0, data=fetch_result)

        except Exception as e:
            if is_browser_context_closed_error(e):
                evidence_ref = await self._capture_failure_evidence(
                    failure_reason="browser_context_closed",
                    execution_stage="fetch_loop",
                    extra_metadata={
                        "exception_type": e.__class__.__name__,
                        "exception_message": str(e),
                        **self._interaction_metadata(),
                    },
                )
                yield self._create_event(
                    BrowserState.ERROR,
                    "DeepSeek 浏览器页面已关闭，正在重建页面后重试。",
                    progress=0,
                    error_type="browser_context_closed",
                    **build_failure_contract(
                        failure_reason="browser_context_closed",
                        execution_stage="fetch_loop",
                        retryable=True,
                        needs_handoff=False,
                        failure_layer="client",
                        evidence_ref=evidence_ref,
                    ),
                )
                return
            yield self._create_event(BrowserState.ERROR, f"抓取失败: {str(e)}", progress=0)

    # ------------------------------------------------------------------ DeepSeek-specific

    async def _detect_risk_control_marker(self) -> tuple[str | None, str | None]:
        text_snapshot = await self._browser_agent_text_snapshot_provider()
        normalized_text = " ".join(str(text_snapshot or "").split())
        if not normalized_text:
            return None, None
        lower_text = normalized_text.lower()
        for marker in self.RISK_CONTROL_MARKERS:
            if marker.lower() in lower_text:
                return marker, normalized_text[:600]
        return None, None

    async def _handle_browser_agent_empty_answer(
        self,
        answer_text: str | None,
        *,
        progress: float,
        fallback_url: str | None = None,
    ) -> tuple[list[BrowserEvent], bool]:
        if answer_text and len(answer_text.strip()) >= 10:
            return [], False

        risk_control_marker, page_excerpt = await self._detect_risk_control_marker()
        if not risk_control_marker:
            return await super()._handle_browser_agent_empty_answer(
                answer_text,
                progress=progress,
                fallback_url=fallback_url,
            )

        evidence_ref = await self._capture_failure_evidence(
            failure_reason=self.PAGE_RUNTIME_RISK_FAILURE_REASON,
            execution_stage="extract_answer",
            extra_metadata={
                "answer_length": len(answer_text or ""),
                "risk_control_marker": risk_control_marker,
                "page_excerpt": page_excerpt,
                **self._interaction_metadata(),
            },
        )
        return [
            self._create_event(
                BrowserState.ERROR,
                "DeepSeek 页面返回运行环境/重试提示，当前运行时未获得有效回答",
                progress=0,
                error_type=self.PAGE_RUNTIME_RISK_FAILURE_REASON,
                **build_failure_contract(
                    failure_reason=self.PAGE_RUNTIME_RISK_FAILURE_REASON,
                    execution_stage="extract_answer",
                    retryable=False,
                    needs_handoff=False,
                    failure_layer="adapter",
                    evidence_ref=evidence_ref,
                ),
            )
        ], True

    async def _capture_submission_probe(self, question: str | None = None) -> dict[str, Any]:
        if self.client.page is None:
            return {"message_count": 0, "answer_count": 0, "input_len": 0}
        input_sel = json.dumps(self._sel("input"), ensure_ascii=False)
        question_prefix = (question or "").strip()[:16]
        question_prefix_js = json.dumps(question_prefix, ensure_ascii=False)
        probe = await self.client.page.evaluate(
            f"""() => {{
                const textarea = document.querySelector({input_sel});
                const readValue = textarea
                    ? String(textarea.value || textarea.textContent || '').trim()
                    : '';
                const questionPrefix = {question_prefix_js};
                const bodyText = String(document.body?.innerText || '');
                const bodyPrefixCount = questionPrefix
                    ? bodyText.split(questionPrefix).length - 1
                    : 0;
                return {{
                    message_count: document.querySelectorAll('.ds-message').length,
                    answer_count: document.querySelectorAll('div.ds-markdown').length,
                    input_len: readValue.length,
                    body_prefix_count: bodyPrefixCount,
                }};
            }}"""
        )
        return probe if isinstance(probe, dict) else {}

    async def _submission_looks_started(
        self,
        baseline_probe: dict[str, Any],
        question: str,
        *,
        timeout_seconds: float = 4.0,
    ) -> bool:
        if self.client.page is None:
            return False
        input_sel = json.dumps(self._sel("input"), ensure_ascii=False)
        question_prefix = question.strip()[:16]
        question_prefix_js = json.dumps(question_prefix, ensure_ascii=False)

        def _as_int(value: Any) -> int:
            try:
                return int(value or 0)
            except (TypeError, ValueError):
                return 0

        baseline_message_count = _as_int(baseline_probe.get("message_count"))
        baseline_answer_count = _as_int(baseline_probe.get("answer_count"))
        baseline_prefix_count = _as_int(baseline_probe.get("body_prefix_count"))
        self._last_submission_probe = {
            "baseline": baseline_probe,
            "latest": None,
            "confirmed_by": None,
        }
        waited = 0.0
        while waited <= timeout_seconds:
            await asyncio.sleep(0.5)
            waited += 0.5
            probe = await self.client.page.evaluate(
                f"""() => {{
                    const textarea = document.querySelector({input_sel});
                    const readValue = textarea
                        ? String(textarea.value || textarea.textContent || '').trim()
                        : '';
                    const questionPrefix = {question_prefix_js};
                    const bodyText = String(document.body?.innerText || '');
                    const bodyPrefixCount = questionPrefix
                        ? bodyText.split(questionPrefix).length - 1
                        : 0;
                    return {{
                        message_count: document.querySelectorAll('.ds-message').length,
                        answer_count: document.querySelectorAll('div.ds-markdown').length,
                        input_len: readValue.length,
                        body_prefix_count: bodyPrefixCount,
                        body_has_prefix: bodyPrefixCount > 0,
                    }};
                }}"""
            )
            if not isinstance(probe, dict):
                continue
            latest_probe = dict(probe)
            latest_probe["waited_seconds"] = waited
            self._last_submission_probe = {
                "baseline": baseline_probe,
                "latest": latest_probe,
                "confirmed_by": None,
            }
            if _as_int(probe.get("message_count")) > baseline_message_count:
                self._last_submission_probe["confirmed_by"] = "message_count"
                return True
            if _as_int(probe.get("answer_count")) > baseline_answer_count:
                self._last_submission_probe["confirmed_by"] = "answer_count"
                return True
            current_prefix_count = _as_int(probe.get("body_prefix_count"))
            if (
                current_prefix_count > baseline_prefix_count
                and bool(probe.get("body_has_prefix"))
                and _as_int(probe.get("input_len")) == 0
            ):
                self._last_submission_probe["confirmed_by"] = (
                    "body_prefix_added_and_input_cleared"
                )
                return True
        return False

    async def _click_send_button_near_input(self) -> bool:
        if self.client.page is None:
            return False
        input_sel = json.dumps(self._sel("input"), ensure_ascii=False)
        clicked = await self.client.page.evaluate(
            f"""() => {{
                const textarea = document.querySelector({input_sel});
                if (!textarea) return false;
                const interactive = [
                    "button",
                    "[role='button']",
                    "div[class*='icon-button']",
                ].join(", ");
                let container = textarea.parentElement;
                while (container && container !== document.body) {{
                    const candidates = Array.from(container.querySelectorAll(interactive));
                    const enabled = candidates.filter((el) => {{
                        const cls = String(el.className || '').toLowerCase();
                        const aria = String(el.getAttribute('aria-label') || '').toLowerCase();
                        const title = String(el.getAttribute('title') || '').toLowerCase();
                        const text = String(el.textContent || '').trim().toLowerCase();
                        const disabled = el.hasAttribute('disabled')
                            || el.getAttribute('aria-disabled') === 'true'
                            || cls.includes('disabled');
                        if (disabled) return false;
                        return (
                            aria.includes('send')
                            || aria.includes('发送')
                            || title.includes('send')
                            || title.includes('发送')
                            || text.includes('send')
                            || text.includes('发送')
                            || cls.includes('send')
                            || cls.includes('submit')
                            || cls.includes('icon-button')
                        );
                    }});
                    if (enabled.length > 0) {{
                        enabled[enabled.length - 1].click();
                        return true;
                    }}
                    container = container.parentElement;
                }}
                return false;
            }}"""
        )
        return bool(clicked)

    async def _submit_question_via_cdp_dom(
        self,
        question: str,
        baseline_probe: dict[str, Any],
    ) -> bool:
        submitted = False
        if self.client.page is not None:
            try:
                editor = self.client.page.locator(self._sel("input")).last
                if await editor.count() > 0:
                    await editor.click()
                    await asyncio.sleep(0.2)
                    await editor.fill(question)
                    await asyncio.sleep(0.2)
                    await editor.press("Enter")
                    submitted = await self._submission_looks_started(
                        baseline_probe, question
                    )
                    logger.info(
                        "[DeepSeek] Question submitted via locator Enter (confirmed=%s)",
                        submitted,
                    )
            except Exception as e:
                logger.debug("[DeepSeek] Direct locator submit failed: %s", e)

        if not submitted:
            snapshot = await self.client.snapshot(interactive_only=True)
            textarea_ref = self._find_textarea_ref(snapshot)
            if textarea_ref:
                await self.client.fill(textarea_ref, question)
                await asyncio.sleep(0.3)
                await self.client.press("Enter")
                submitted = await self._submission_looks_started(
                    baseline_probe, question
                )
                logger.info(
                    "[DeepSeek] Question submitted via snapshot ref %s (confirmed=%s)",
                    textarea_ref,
                    submitted,
                )

        if not submitted and await self._click_send_button_near_input():
            submitted = await self._submission_looks_started(
                baseline_probe, question
            )
            logger.info(
                "[DeepSeek] Question submitted via send-button fallback (confirmed=%s)",
                submitted,
            )

        return submitted

    async def _execute_aio_gui_action(self, action_payload: dict[str, Any]) -> bool:
        try:
            result = await self._aio_backend.execute_action(
                action_payload=action_payload
            )
        except Exception as exc:
            logger.warning("[DeepSeek] AIO GUI action failed: %s", exc)
            return False

        detail = result.get("detail") if isinstance(result, dict) else None
        if isinstance(detail, dict) and detail.get("success") is False:
            logger.warning("[DeepSeek] AIO GUI action rejected: %s", detail)
            return False

        status = str(
            (result.get("status") if isinstance(result, dict) else "") or ""
        ).lower()
        if status in {"error", "failed", "failure"}:
            logger.warning("[DeepSeek] AIO GUI action returned status=%s", status)
            return False
        return True

    async def _aio_gui_click_rect(self, rect: dict[str, Any]) -> bool:
        try:
            x = int(round(float(rect["gui_x"])))
            y = int(round(float(rect["gui_y"])))
        except (KeyError, TypeError, ValueError):
            return False

        moved = await self._execute_aio_gui_action(
            {"action_type": "MOVE_TO", "x": x, "y": y}
        )
        clicked = await self._execute_aio_gui_action(
            {"action_type": "CLICK", "x": x, "y": y}
        )
        return moved and clicked

    async def _deepseek_input_rect_for_gui_actions(self) -> dict[str, Any] | None:
        if self.client.page is None:
            return None
        input_sel = json.dumps(self._sel("input"), ensure_ascii=False)
        result = await self.client.page.evaluate(
            f"""() => {{
                const elements = Array.from(document.querySelectorAll({input_sel}));
                const el = elements.reverse().find((candidate) => {{
                    const rect = candidate.getBoundingClientRect();
                    return rect.width > 20 && rect.height > 10;
                }});
                if (!el) return null;
                const rect = el.getBoundingClientRect();
                const chromeOffsetX = Math.max(0, Math.round((window.outerWidth - window.innerWidth) / 2));
                const chromeOffsetY = Math.max(0, Math.round(window.outerHeight - window.innerHeight));
                return {{
                    page_x: rect.left + rect.width / 2,
                    page_y: rect.top + rect.height / 2,
                    gui_x: rect.left + rect.width / 2 + chromeOffsetX,
                    gui_y: rect.top + rect.height / 2 + chromeOffsetY,
                    width: rect.width,
                    height: rect.height,
                    chrome_offset_x: chromeOffsetX,
                    chrome_offset_y: chromeOffsetY,
                }};
            }}"""
        )
        return result if isinstance(result, dict) else None

    async def _deepseek_send_button_rect_for_gui_actions(
        self,
    ) -> dict[str, Any] | None:
        if self.client.page is None:
            return None
        input_sel = json.dumps(self._sel("input"), ensure_ascii=False)
        result = await self.client.page.evaluate(
            f"""() => {{
                const textarea = document.querySelector({input_sel});
                if (!textarea) return null;
                const inputRect = textarea.getBoundingClientRect();
                const chromeOffsetX = Math.max(0, Math.round((window.outerWidth - window.innerWidth) / 2));
                const chromeOffsetY = Math.max(0, Math.round(window.outerHeight - window.innerHeight));
                const interactive = [
                    "button",
                    "[role='button']",
                    "div[class*='icon-button']",
                    "div[class*='send']",
                    "[class*='submit']",
                ].join(", ");
                const labelOf = (el) => [
                    el.getAttribute('aria-label') || '',
                    el.getAttribute('title') || '',
                    el.getAttribute('data-testid') || '',
                    el.getAttribute('class') || '',
                    el.innerText || el.textContent || '',
                ].join(' ').trim().toLowerCase();
                const isDisabled = (el) => {{
                    const cls = String(el.getAttribute('class') || '').toLowerCase();
                    return el.hasAttribute('disabled')
                        || el.getAttribute('aria-disabled') === 'true'
                        || cls.includes('disabled');
                }};
                const isToggle = (el, label) => {{
                    return el.hasAttribute('aria-pressed')
                        || el.hasAttribute('aria-checked')
                        || el.getAttribute('role') === 'switch'
                        || label.includes('deepthink')
                        || label.includes('联网')
                        || label.includes('search')
                        || label.includes('attach')
                        || label.includes('upload')
                        || label.includes('file')
                        || label.includes('附件')
                        || label.includes('上传');
                }};
                const describeRect = (rect) => ({{
                    page_x: rect.left + rect.width / 2,
                    page_y: rect.top + rect.height / 2,
                    gui_x: rect.left + rect.width / 2 + chromeOffsetX,
                    gui_y: rect.top + rect.height / 2 + chromeOffsetY,
                    width: rect.width,
                    height: rect.height,
                    chrome_offset_x: chromeOffsetX,
                    chrome_offset_y: chromeOffsetY,
                }});
                let container = textarea.parentElement;
                let depth = 0;
                let best = null;
                while (container && container !== document.body && depth < 8) {{
                    for (const el of Array.from(container.querySelectorAll(interactive))) {{
                        if (el === textarea || isDisabled(el)) continue;
                        const rect = el.getBoundingClientRect();
                        if (rect.width < 12 || rect.height < 12) continue;
                        const label = labelOf(el);
                        if (isToggle(el, label)) continue;
                        const cx = rect.left + rect.width / 2;
                        const cy = rect.top + rect.height / 2;
                        const rightSide = cx >= inputRect.left + inputRect.width * 0.55;
                        const nearInputY = cy >= inputRect.top - 80 && cy <= inputRect.bottom + 90;
                        let score = 0;
                        if (/(send|submit|arrow|up|发送)/.test(label)) score += 8;
                        if (rightSide) score += 3;
                        if (nearInputY) score += 3;
                        if (rect.width <= 90 && rect.height <= 90) score += 2;
                        if (String(el.tagName || '').toLowerCase() === 'button') score += 1;
                        if (
                            !best
                            || score > best.candidate_score
                            || (
                                score === best.candidate_score
                                && cx > best.page_x
                            )
                        ) {{
                            best = {{
                                ...describeRect(rect),
                                candidate_score: score,
                                candidate_label: label.slice(0, 120),
                                candidate_tag: el.tagName,
                            }};
                        }}
                    }}
                    container = container.parentElement;
                    depth += 1;
                }}
                return best && best.candidate_score >= 5 ? best : null;
            }}"""
        )
        return result if isinstance(result, dict) else None

    async def _submit_question_via_aio_gui_actions(
        self,
        question: str,
        baseline_probe: dict[str, Any],
    ) -> bool:
        rect = await self._deepseek_input_rect_for_gui_actions()
        if not rect:
            logger.warning("[DeepSeek] AIO GUI submit failed: input rect unavailable")
            return False

        if not await self._aio_gui_click_rect(rect):
            return False
        await asyncio.sleep(0.2)

        await self._execute_aio_gui_action(
            {"action_type": "HOTKEY", "keys": ["ctrl", "a"]}
        )
        await asyncio.sleep(0.1)
        typed = await self._execute_aio_gui_action(
            {
                "action_type": "TYPING",
                "text": question,
                "use_clipboard": True,
            }
        )
        if not typed:
            return False
        await asyncio.sleep(0.2)

        pressed = await self._execute_aio_gui_action(
            {"action_type": "PRESS", "key": "Enter"}
        )
        if not pressed:
            return False

        submitted = await self._submission_looks_started(baseline_probe, question)
        logger.info(
            "[DeepSeek] Question submitted via AIO GUI Enter (confirmed=%s)",
            submitted,
        )
        if submitted:
            return True

        send_rect = await self._deepseek_send_button_rect_for_gui_actions()
        if not send_rect:
            logger.warning("[DeepSeek] AIO GUI send-button fallback unavailable")
            return False
        if not await self._aio_gui_click_rect(send_rect):
            logger.warning(
                "[DeepSeek] AIO GUI send-button fallback click failed: %s",
                send_rect,
            )
            return False
        submitted = await self._submission_looks_started(
            baseline_probe,
            question,
            timeout_seconds=6.0,
        )
        logger.info(
            "[DeepSeek] Question submitted via AIO GUI send button "
            "(confirmed=%s, score=%s, label=%s)",
            submitted,
            send_rect.get("candidate_score"),
            send_rect.get("candidate_label"),
        )
        return submitted

    async def _ensure_web_search_on_via_aio_gui_actions(self) -> None:
        if self.client.page is None:
            return
        try:
            input_sel = json.dumps(self._sel("input"), ensure_ascii=False)
            info = await self.client.page.evaluate(
                f"""() => {{
                    const INTERACTIVE = 'button, [role="button"], [role="switch"], [aria-pressed], [aria-checked]';
                    const textarea = document.querySelector({input_sel});
                    const chromeOffsetX = Math.max(0, Math.round((window.outerWidth - window.innerWidth) / 2));
                    const chromeOffsetY = Math.max(0, Math.round(window.outerHeight - window.innerHeight));
                    const descEl = (el) => {{
                        const rect = el.getBoundingClientRect();
                        return {{
                            tag: el.tagName,
                            pressed: el.getAttribute('aria-pressed') || '',
                            checked: el.getAttribute('aria-checked') || '',
                            state: el.getAttribute('data-state') || '',
                            label: el.getAttribute('aria-label') || '',
                            title: el.getAttribute('title') || '',
                            cls: (el.className || '').slice(0, 80),
                            txt: (el.innerText || el.textContent || '').trim().slice(0, 40),
                            rect: {{
                                page_x: rect.left + rect.width / 2,
                                page_y: rect.top + rect.height / 2,
                                gui_x: rect.left + rect.width / 2 + chromeOffsetX,
                                gui_y: rect.top + rect.height / 2 + chromeOffsetY,
                                width: rect.width,
                                height: rect.height,
                                chrome_offset_x: chromeOffsetX,
                                chrome_offset_y: chromeOffsetY,
                            }},
                        }};
                    }};
                    let toolbarEls = null;
                    if (textarea) {{
                        let c = textarea.parentElement;
                        while (c && c !== document.body) {{
                            const els = Array.from(c.querySelectorAll(INTERACTIVE));
                            if (els.length >= 1 && els.length <= 8) {{
                                toolbarEls = els;
                                break;
                            }}
                            c = c.parentElement;
                        }}
                    }}
                    return {{
                        toolbarBtns: toolbarEls ? toolbarEls.map(descEl) : [],
                    }};
                }}"""
            )

            toolbar = info.get("toolbarBtns") if isinstance(info, dict) else []
            if not isinstance(toolbar, list) or not toolbar:
                logger.warning("[DeepSeek] AIO GUI search toggle: no toolbar found")
                return

            search_idx = self._find_web_search_index(toolbar)
            if search_idx is None or search_idx >= len(toolbar):
                logger.warning("[DeepSeek] AIO GUI search toggle not identified")
                return

            button = toolbar[search_idx]
            pressed = button.get("pressed", "")
            cls = button.get("cls", "")
            if pressed == "true" or "--selected" in cls:
                logger.info("[DeepSeek] Web search already ON via GUI probe")
                return

            rect = button.get("rect")
            if isinstance(rect, dict) and await self._aio_gui_click_rect(rect):
                logger.info("[DeepSeek] Enabled web search via AIO GUI actions")
                await asyncio.sleep(0.5)
        except Exception as exc:
            logger.warning(
                "[DeepSeek] _ensure_web_search_on_via_aio_gui_actions failed: %s",
                exc,
            )

    async def _ensure_web_search_on(self) -> None:
        """Ensure the web search toggle is ON in the input toolbar.

        DeepSeek renders toolbar toggles as pure SVG icon-buttons with no
        visible text or aria-label.
        """
        try:
            input_sel = json.dumps(self._sel("input"), ensure_ascii=False)
            # Playwright page.evaluate() — runs JS in browser context
            info = await self.client.page.evaluate(f"""() => {{
                const INTERACTIVE = 'button, [role="button"], [role="switch"], [aria-pressed], [aria-checked]';
                const textarea = document.querySelector({input_sel});
                let toolbarEls = null;
                let toolbarContainerCls = '';
                if (textarea) {{
                    let c = textarea.parentElement;
                    while (c && c !== document.body) {{
                        const els = Array.from(c.querySelectorAll(INTERACTIVE));
                        if (els.length >= 1 && els.length <= 8) {{
                            toolbarEls = els;
                            toolbarContainerCls = (c.className || '').slice(0, 80);
                            break;
                        }}
                        c = c.parentElement;
                    }}
                }}
                const descEl = el => ({{
                    tag: el.tagName,
                    pressed: el.getAttribute('aria-pressed') || '',
                    checked: el.getAttribute('aria-checked') || '',
                    state:   el.getAttribute('data-state')   || '',
                    label:   el.getAttribute('aria-label')   || '',
                    title:   el.getAttribute('title')        || '',
                    cls:    (el.className || '').slice(0, 80),
                    txt:    (el.innerText || el.textContent || '').trim().slice(0, 40),
                }});
                const allToggles = Array.from(
                    document.querySelectorAll('[aria-pressed], [aria-checked], [role="switch"]')
                ).map(descEl);
                return {{
                    toolbarBtns: toolbarEls ? toolbarEls.map(descEl) : null,
                    toolbarContainerCls,
                    allToggles,
                }};
            }}""")

            toolbar = info.get("toolbarBtns") or []
            all_toggles = info.get("allToggles") or []
            logger.info("[DeepSeek] Toolbar buttons (%d): %s | All toggles (%d): %s",
                        len(toolbar), toolbar, len(all_toggles), all_toggles)

            if not toolbar:
                if not all_toggles:
                    logger.warning("[DeepSeek] No toolbar or toggle elements found near textarea")
                await self._try_text_based_search_toggle()
                return

            search_idx = self._find_web_search_index(toolbar)
            if search_idx is None:
                logger.warning("[DeepSeek] Could not identify WebSearch toggle in toolbar")
                await self._try_text_based_search_toggle()
                return

            btn = toolbar[search_idx]
            pressed = btn.get("pressed", "")
            cls = btn.get("cls", "")

            if pressed == "true":
                logger.info("[DeepSeek] Web search already ON (toolbar[%d], pressed=true)", search_idx)
                return
            if pressed == "false":
                await self._click_toolbar_button(search_idx)
                logger.info("[DeepSeek] Enabled web search toolbar[%d] (pressed false→true)", search_idx)
                return

            if "--selected" in cls:
                logger.info("[DeepSeek] Web search already ON (toolbar[%d], --selected)", search_idx)
            else:
                await self._click_toolbar_button(search_idx)
                logger.info("[DeepSeek] Enabled web search toolbar[%d] (was OFF)", search_idx)

        except Exception as e:
            logger.warning("[DeepSeek] _ensure_web_search_on failed: %s", e)

    def _browser_agent_stage_note(
        self,
        *,
        stage: str,
        action_type: str | None = None,
    ) -> str | None:
        note = super()._browser_agent_stage_note(stage=stage, action_type=action_type)
        if stage == "resume_probe" and action_type == "login":
            return (
                f"{note} DeepSeek 的就绪信号通常是已经进入聊天页，可见输入区和工具栏；"
                "如果仍停留在 sign_in/login 页面、手机号/验证码表单、二维码登录或安全验证页面，则不要放行。"
            )
        if stage == "wait_gate":
            return (
                f"{note} DeepSeek 可能在提交后转入登录页或验证页；如果 URL 或页面文案显示 sign_in/login/验证码，应及时识别为 blocker。"
            )
        return note

    def _find_web_search_index(self, toolbar: list[dict]) -> int | None:
        """Find the index of the WebSearch toggle button in the toolbar."""
        for i, btn in enumerate(toolbar):
            txt = btn.get("txt", "").lower()
            if "search" in txt or "联网" in txt:
                return i

        toggle_keywords = ("toggle", "switch", "ds-toggle")
        toggle_indices = []
        for i, btn in enumerate(toolbar):
            cls = btn.get("cls", "").lower()
            if any(kw in cls for kw in toggle_keywords):
                toggle_indices.append(i)

        if len(toggle_indices) >= 2:
            return toggle_indices[1]

        for i, btn in enumerate(toolbar):
            if btn.get("pressed") in ("true", "false"):
                txt = btn.get("txt", "").lower()
                if "think" in txt or "深度" in txt or "思考" in txt:
                    continue
                return i

        if toggle_indices:
            return toggle_indices[0]

        logger.warning("[DeepSeek] _find_web_search_index: no toggle found")
        return None

    async def _click_toolbar_button(self, index: int) -> None:
        """Click a toolbar button by index (re-locating from textarea)."""
        input_sel = json.dumps(self._sel("input"), ensure_ascii=False)
        # Playwright page.evaluate() — runs JS in browser context
        await self.client.page.evaluate(f"""() => {{
            const INTERACTIVE = 'button, [role="button"], [role="switch"], [aria-pressed], [aria-checked]';
            const textarea = document.querySelector({input_sel});
            let c = textarea && textarea.parentElement;
            while (c && c !== document.body) {{
                const els = Array.from(c.querySelectorAll(INTERACTIVE));
                if (els.length >= 1 && els.length <= 8) {{
                    els[{index}] && els[{index}].click();
                    return 'clicked';
                }}
                c = c.parentElement;
            }}
            return 'not found';
        }}""")
        await asyncio.sleep(0.5)

    async def _try_text_based_search_toggle(self) -> None:
        """Fallback: enable web search by clicking element containing '联网' text."""
        if not self.client.page:
            return
        try:
            web_search_texts = self._sel("web_search_texts")
            for text in web_search_texts:
                locator = self.client.page.get_by_text(text, exact=False).first
                if await locator.count() > 0:
                    await locator.click()
                    await asyncio.sleep(0.5)
                    logger.info("[DeepSeek] Enabled web search via text-based fallback ('%s')", text)
                    return
            logger.warning("[DeepSeek] Text-based search toggle fallback: no matching element found")
        except Exception as e:
            logger.warning("[DeepSeek] Text-based search toggle fallback failed: %s", e)

    async def _extract_references(self) -> list[SearchReference]:
        """Extract search references from all DeepSeek surfaces and merge them."""
        citation_refs = await self._extract_citation_links()
        selector_refs = await self._extract_references_dom()
        page_refs = await self._extract_page_reference_links(
            limit=self.REFERENCE_EXTRACTION_LIMIT
        )
        refs = self._merge_references(
            citation_refs,
            selector_refs,
            page_refs,
            limit=self.REFERENCE_EXTRACTION_LIMIT,
        )
        if refs:
            logger.info(
                "[DeepSeek] Extracted %d references "
                "(citation=%d, selector=%d, page=%d, target=%d)",
                len(refs),
                len(citation_refs),
                len(selector_refs),
                len(page_refs),
                self.REFERENCE_TARGET_COUNT,
            )
        return refs

    def _merge_references(
        self,
        *groups: list[SearchReference],
        limit: int | None = None,
    ) -> list[SearchReference]:
        """Merge references from multiple extraction strategies."""
        max_items = limit or self.REFERENCE_EXTRACTION_LIMIT
        merged: list[SearchReference] = []
        seen: set[str] = set()

        for refs in groups:
            for ref in refs:
                url = (getattr(ref, "url", "") or "").strip()
                if not self._is_allowed_reference_url(url):
                    continue

                key = self._normalize_reference_url(url)
                if not key or key in seen:
                    continue
                seen.add(key)

                title = (getattr(ref, "title", "") or "").strip()
                if not title:
                    title = self._title_from_reference_url(url)

                merged.append(
                    SearchReference(
                        index=len(merged) + 1,
                        title=title,
                        url=url,
                        snippet=getattr(ref, "snippet", None),
                        site_name=getattr(ref, "site_name", None),
                        is_official=bool(getattr(ref, "is_official", False)),
                    )
                )
                if len(merged) >= max_items:
                    return merged

        return merged

    @staticmethod
    def _is_allowed_reference_url(url: str) -> bool:
        try:
            parsed = urlparse(url.strip())
        except Exception:
            return False
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        hostname = (parsed.hostname or "").lower()
        return hostname not in {"chat.deepseek.com", "accounts.deepseek.com"}

    @staticmethod
    def _normalize_reference_url(url: str) -> str:
        try:
            parsed = urlparse(url.strip())
        except Exception:
            return ""
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""
        path = parsed.path.rstrip("/")
        return urlunparse(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                path,
                "",
                parsed.query,
                "",
            )
        )

    @staticmethod
    def _title_from_reference_url(url: str) -> str:
        try:
            hostname = urlparse(url).hostname or url[:60]
            return hostname.removeprefix("www.")
        except Exception:
            return url[:60]

    async def _extract_page_reference_links(
        self,
        limit: int | None = None,
    ) -> list[SearchReference]:
        """Extract source links from the latest answer container and source cards."""
        try:
            max_items = limit or self.REFERENCE_EXTRACTION_LIMIT
            scan_limit = max(max_items * 4, self.REFERENCE_TARGET_COUNT)
            script = """
            () => {
                const scopedSelectors = [
                    'a[href^="http"]',
                    '[class*="reference"] a[href^="http"]',
                    '[class*="citation"] a[href^="http"]',
                    '[class*="source"] a[href^="http"]',
                    '[class*="search"] a[href^="http"]',
                    '[class*="result"] a[href^="http"]',
                    '[class*="web"] a[href^="http"]'
                ];
                const globalSelectors = scopedSelectors.slice(1);
                const cardSelector = [
                    '[class*="reference"]',
                    '[class*="citation"]',
                    '[class*="source"]',
                    '[class*="search"]',
                    '[class*="result"]',
                    '[class*="web"]',
                    'article',
                    'li',
                    'section',
                    'div'
                ].join(',');

                const answers = Array.from(
                    document.querySelectorAll('div.ds-markdown')
                );
                const lastAnswer = answers[answers.length - 1];
                const scopedRoots = [];
                let node = lastAnswer;
                for (let depth = 0; node && depth < 6; depth += 1) {
                    scopedRoots.push(node);
                    node = node.parentElement;
                }

                const anchors = [];
                const pushAnchors = (root, selectors) => {
                    if (!root) return;
                    for (const selector of selectors) {
                        for (const anchor of root.querySelectorAll(selector)) {
                            anchors.push(anchor);
                        }
                    }
                };

                for (const root of scopedRoots) {
                    pushAnchors(root, scopedSelectors);
                }
                pushAnchors(document, globalSelectors);

                const seen = new Set();
                const refs = [];
                for (const anchor of anchors) {
                    const url = anchor.href || anchor.getAttribute('href') || '';
                    if (!url || seen.has(url)) continue;
                    seen.add(url);

                    const card = anchor.closest(cardSelector);
                    const cardText = ((card && card.innerText) || '').trim();
                    let title = (
                        anchor.getAttribute('title') ||
                        anchor.getAttribute('aria-label') ||
                        anchor.getAttribute('data-title') ||
                        anchor.innerText ||
                        anchor.textContent ||
                        ''
                    ).trim();
                    if (!title && cardText) {
                        title = cardText.split('\\n').find(Boolean) || '';
                    }
                    if (!title || /^[-\\d\\s.\\[\\]()]+$/.test(title)) {
                        try {
                            title = new URL(url).hostname.replace(/^www\\./, '');
                        } catch {
                            title = url.slice(0, 80);
                        }
                    }

                    let siteName = null;
                    try {
                        siteName = new URL(url).hostname.replace(/^www\\./, '');
                    } catch {
                        siteName = null;
                    }

                    refs.push({
                        index: refs.length + 1,
                        title: title.slice(0, 200),
                        url,
                        snippet: cardText ? cardText.slice(0, 300) : null,
                        site_name: siteName,
                        is_official: false
                    });
                    if (refs.length >= __SCAN_LIMIT__) break;
                }
                return JSON.stringify(refs);
            }
            """.replace("__SCAN_LIMIT__", str(scan_limit))
            result = await self.client.eval(script)
            data = json.loads(result.get("output", "[]") or "[]")
            refs: list[SearchReference] = []
            for item in data:
                url = item.get("url", "")
                if not self._is_allowed_reference_url(url):
                    continue
                refs.append(
                    SearchReference(
                        index=len(refs) + 1,
                        title=item.get("title")
                        or self._title_from_reference_url(url),
                        url=url,
                        snippet=item.get("snippet"),
                        site_name=item.get("site_name"),
                        is_official=bool(item.get("is_official", False)),
                    )
                )
                if len(refs) >= max_items:
                    break
            return refs
        except Exception as e:
            logger.debug("[DeepSeek] _extract_page_reference_links failed: %s", e)
            return []

    async def _extract_citation_links(self) -> list[SearchReference]:
        """Extract citation links from the last answer with smart title resolution.

        DeepSeek renders inline citation markers as <a> tags whose textContent
        is just a number. This extracts the href and resolves a meaningful title.

        Uses Playwright's page.evaluate() — runs JS in browser context, not Python eval().
        """
        try:
            answer_sel = json.dumps(self._sel("answer"), ensure_ascii=False)
            result = await self.client.eval(f"""() => {{
                const messages = document.querySelectorAll({answer_sel});
                const lastMsg = messages[messages.length - 1];
                if (!lastMsg) return '[]';

                const links = Array.from(lastMsg.querySelectorAll('a[href^="http"]'));
                const seen = new Set();
                const refs = [];

                for (const a of links) {{
                    const url = a.href;
                    if (!url || seen.has(url)) continue;
                    seen.add(url);

                    let title = (a.getAttribute('title') || '').trim();
                    if (!title) title = (a.getAttribute('aria-label') || '').trim();
                    if (!title) title = (a.getAttribute('data-title') || '').trim();
                    if (!title) {{
                        const parent = a.closest('[class*="tooltip"], [class*="popup"], [class*="citation-content"]');
                        if (parent) {{
                            const pText = (parent.textContent || '').trim();
                            if (pText.length > 5) title = pText.slice(0, 200);
                        }}
                    }}
                    if (!title || /^[-\\d\\s.]+$/.test(title)) {{
                        try {{
                            title = new URL(url).hostname.replace(/^www\\./, '');
                        }} catch {{
                            title = url.slice(0, 60);
                        }}
                    }}

                    refs.push({{ index: refs.length + 1, title, url }});
                }}
                return JSON.stringify(refs);
            }}""")
            data = json.loads(result.get("output", "[]") or "[]")
            if not data:
                return []
            return [
                SearchReference(
                    index=item["index"],
                    title=item["title"],
                    url=item["url"],
                    snippet=None,
                    site_name=None,
                    is_official=False,
                )
                for item in data
                if item.get("url")
            ]
        except Exception as e:
            logger.debug("[DeepSeek] _extract_citation_links failed: %s", e)
            return []
