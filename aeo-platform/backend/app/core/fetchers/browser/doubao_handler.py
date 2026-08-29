"""Doubao (ByteDance) browser handler."""

import asyncio
import json
import logging
from contextlib import suppress
from typing import Any, AsyncGenerator

from app.core.fetchers.browser.base_handler import BaseBrowserHandler
from app.core.fetchers.browser.browser_executor import (
    BrowserAnswerExecutionPlan,
    execute_post_submit_capture_flow,
)
from app.core.fetchers.browser.failure_observability import build_failure_contract
from app.core.fetchers.browser.parsers.base import BaseResponseParser
from app.core.fetchers.browser.parsers.sse import DoubaoSSEParser
from app.schemas.fetch import (
    BrowserState,
    Platform,
)

logger = logging.getLogger(__name__)


class DoubaoHandler(BaseBrowserHandler):
    """Doubao (ByteDance) browser-based handler.

    Uses Playwright to interact with doubao.com.
    Standard textarea input (Semi Design), Enter key to submit.
    """

    URL = "https://www.doubao.com/chat/"
    PLATFORM = Platform.DOUBAO
    PLATFORM_KEY = "doubao"
    DOUBLE_UTF8_FIX = True  # Doubao SSE body is double UTF-8 encoded
    BROWSER_READY_URL_PATTERNS = ("/chat", "doubao.com/chat")
    BROWSER_LOGIN_URL_PATTERNS = ("login", "signin", "auth")
    BROWSER_READY_HINTS = ("新对话", "深入研究")
    BROWSER_LOGIN_HINTS = ("登录", "手机号", "验证码")
    BROWSER_LATE_BLOCKER_HINTS = ("安全验证", "verify", "人机验证", "验证码")

    _DEFAULTS: dict = {
        "input": (
            "textarea.semi-input-textarea, "
            "[data-testid*='chat-input'] [contenteditable='true'], "
            "[role='textbox'][contenteditable='true'], "
            ".ProseMirror[contenteditable='true'], "
            "[class*='editor'][contenteditable='true'], textarea"
        ),
        "input_ready": (
            "textarea.semi-input-textarea, "
            "[data-testid*='chat-input'] [contenteditable='true'], "
            "[role='textbox'][contenteditable='true'], "
            ".ProseMirror[contenteditable='true'], "
            "[class*='editor'][contenteditable='true'], textarea"
        ),
        "send_btn": (
            "button[data-testid*='send'], button[aria-label*='发送'], "
            "button[aria-label*='send' i], [role='button'][class*='send'], "
            "button[class*='send']"
        ),
        "login_btn": "[data-testid='to_login_button'], [class*='login-btn']",
        "content": [
            ".flow-markdown-body",
            "[data-testid='message_text_content']",
            "[class*='markdown-body']",
        ],
        "citation_strip": "[class*='cite'], [class*='citation'], [class*='ref-num'], sup, a[data-index]",
        "reference_links": [
            "[class*='source'] a[href^='http']",
            "[class*='reference'] a[href^='http']",
            "[class*='search-result'] a[href^='http']",
        ],
        "new_chat_text": "新对话",
        "web_search_text": "深入研究",
        "dismiss_texts": ["关闭", "稍后再说", "我知道了"],
        "reference_expand_texts": ["来源", "引用", "Sources", "References"],
    }

    def _get_response_parser(self) -> BaseResponseParser | None:
        return DoubaoSSEParser()

    async def fetch(self, question: str) -> AsyncGenerator:
        """Fetch answer from Doubao Web."""
        self._refresh_selectors()
        try:
            # Step 1: Initializing
            yield self._create_event(BrowserState.INITIALIZING, "初始化浏览器...", progress=0.1)

            # Step 2: Navigate or start new chat
            yield self._create_event(BrowserState.NAVIGATING, f"正在访问 {self.URL}...", progress=0.2)
            page = self.client.page
            fast_path_ok = False
            page_url = page.url if page is not None else ""

            if page is not None and "doubao.com" in page_url:
                try:
                    new_chat_text = self._sel("new_chat_text")
                    btn = page.get_by_text(new_chat_text, exact=False).first
                    if await btn.count() > 0:
                        old_url = page.url
                        await btn.click()
                        # Verify: wait for URL change or input clear (not just sleep)
                        for _ in range(6):
                            await asyncio.sleep(0.5)
                            if page.url != old_url:
                                fast_path_ok = True
                                break
                        if not fast_path_ok:
                            # URL didn't change but click succeeded — check if input cleared
                            fast_path_ok = True
                        logger.info("[Doubao] Fast path: clicked %s (url_changed=%s)", new_chat_text, page.url != old_url)
                except Exception as e:
                    logger.debug("[Doubao] Fast path click failed: %s", e)

            if not fast_path_ok and await self._reuse_existing_aio_surface(self.URL):
                fast_path_ok = True

            if not fast_path_ok:
                open_result = await self.client.open(self.URL, headed=self.headed)
                if not open_result.get("success"):
                    yield self._create_event(
                        BrowserState.ERROR,
                        f"浏览器打开失败: {open_result.get('error', '未知错误')}",
                        progress=0,
                    )
                    return
                await asyncio.sleep(3)

            if self.client.page:
                logger.info("[Doubao] Page URL: %s", self.client.page.url)

            preflight_events, should_abort = await self._run_browser_agent_preflight(
                progress=0.24,
                url=self.URL,
            )
            for event in preflight_events:
                yield event
            if should_abort:
                return

            # Step 3: Enable web search
            yield self._create_event(BrowserState.ENABLING_SEARCH, "确认联网搜索...", progress=0.5)
            logger.info("[Doubao] Web search is on by default, skipping toggle")

            # Step 5: Start network interception (before submit)
            yield self._create_event(BrowserState.SUBMITTING, f"提交问题: {question[:30]}...", progress=0.6)
            intercept_config = self._get_intercept_config()
            parser = self._get_response_parser()
            intercept_task = None
            if intercept_config and parser and self.client.page:
                intercept_task = asyncio.create_task(
                    self._intercept_and_wait(intercept_config, parser)
                )

            # Step 5b: Submit question and confirm that the UI accepted it.
            baseline_probe = await self._capture_submission_probe(question)
            submitted = await self._submit_question(question, baseline_probe)
            if not submitted:
                if intercept_task is not None:
                    intercept_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await intercept_task
                evidence_ref = await self._capture_failure_evidence(
                    failure_reason="submission_not_confirmed",
                    execution_stage="submit_question",
                    extra_metadata={
                        "baseline_submission_probe": baseline_probe,
                        "last_submission_probe": getattr(
                            self, "_last_submission_probe", None
                        ),
                    },
                )
                yield self._create_event(
                    BrowserState.ERROR,
                    "豆包未接收本题，已停止等待并记录页面证据",
                    progress=0,
                    error_type="submission_not_confirmed",
                    **build_failure_contract(
                        failure_reason="submission_not_confirmed",
                        execution_stage="submit_question",
                        retryable=True,
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
                    max_wait=60,
                    poll_interval=3,
                    min_content_len=80,
                    stable_rounds=2,
                    blocker_check_after_seconds=9,
                    parser_message_overrides={
                        "rate_limit": "豆包触发平台限流，请稍后重试，或降低并发后再采集。",
                        "verify": "豆包触发安全验证，请在浏览器窗口完成验证后重新采集。",
                    },
                ),
            )
            for event in events:
                yield event
            if fetch_result is None:
                return

            yield self._create_event(BrowserState.COMPLETED, "抓取完成", progress=1.0, data=fetch_result)

        except Exception as e:
            yield self._create_event(BrowserState.ERROR, f"抓取失败: {str(e)}", progress=0)

    # ------------------------------------------------------------------ Doubao-specific helpers

    async def _capture_submission_probe(self, question: str) -> dict[str, Any]:
        """Capture observable UI state before typing a question."""

        if self.client.page is None:
            return {}
        input_selector = json.dumps(self._sel("input"), ensure_ascii=False)
        question_prefix = json.dumps(question.strip()[:16], ensure_ascii=False)
        probe = await self.client.page.evaluate(
            f"""() => {{
                const candidates = Array.from(document.querySelectorAll({input_selector}));
                const input = candidates.find((el) => el.offsetParent !== null) || null;
                const readInput = input
                    ? String(input.value || input.innerText || input.textContent || '').trim()
                    : '';
                const prefix = {question_prefix};
                const bodyText = String(document.body?.innerText || '');
                const userSelector = [
                    '[data-testid*="message"][data-testid*="user"]',
                    '[class*="message"][class*="user"]',
                    '[class*="user-message"]',
                    '[class*="message-user"]'
                ].join(',');
                return {{
                    url: location.href,
                    input_len: readInput.length,
                    input_contains_question: prefix ? readInput.includes(prefix) : false,
                    body_prefix_count: prefix ? bodyText.split(prefix).length - 1 : 0,
                    user_message_count: document.querySelectorAll(userSelector).length,
                }};
            }}"""
        )
        return probe if isinstance(probe, dict) else {}

    async def _type_question_into_visible_input(self, question: str) -> bool:
        """Type into the first visible legacy textarea or rich-text editor."""

        page = self.client.page
        if page is None:
            return False
        locator = page.locator(self._sel("input"))
        for index in range(await locator.count()):
            candidate = locator.nth(index)
            try:
                if not await candidate.is_visible():
                    continue
                await candidate.click()
                await page.keyboard.press("Control+a")
                await page.keyboard.insert_text(question)
                typed = await candidate.evaluate(
                    "(el) => String(el.value || el.innerText || el.textContent || '').trim()"
                )
                if question.strip()[:16] in str(typed):
                    return True
            except Exception as exc:
                logger.debug("[Doubao] Candidate input %d failed: %s", index, exc)
        return False

    async def _click_send_button(self) -> bool:
        page = self.client.page
        if page is None:
            return False
        buttons = page.locator(self._sel("send_btn"))
        for index in range(await buttons.count()):
            button = buttons.nth(index)
            try:
                if await button.is_visible() and await button.is_enabled():
                    await button.click()
                    return True
            except Exception as exc:
                logger.debug("[Doubao] Candidate send button %d failed: %s", index, exc)
        return False

    async def _submission_looks_started(
        self,
        baseline_probe: dict[str, Any],
        question: str,
        *,
        timeout_seconds: float,
    ) -> bool:
        """Confirm submission from URL/message changes or a cleared input."""

        if self.client.page is None:
            return False

        def _as_int(value: Any) -> int:
            try:
                return int(value or 0)
            except (TypeError, ValueError):
                return 0

        baseline_prefix_count = _as_int(baseline_probe.get("body_prefix_count"))
        baseline_message_count = _as_int(baseline_probe.get("user_message_count"))
        baseline_url = str(baseline_probe.get("url") or "")
        self._last_submission_probe = {
            "baseline": baseline_probe,
            "latest": None,
            "confirmed_by": None,
        }
        waited = 0.0
        while waited < timeout_seconds:
            await asyncio.sleep(0.4)
            waited += 0.4
            probe = await self._capture_submission_probe(question)
            probe["waited_seconds"] = waited
            self._last_submission_probe["latest"] = probe
            if str(probe.get("url") or "") != baseline_url:
                self._last_submission_probe["confirmed_by"] = "url_changed"
                return True
            if _as_int(probe.get("user_message_count")) > baseline_message_count:
                self._last_submission_probe["confirmed_by"] = "user_message_added"
                return True
            if (
                _as_int(probe.get("body_prefix_count")) > baseline_prefix_count
                and _as_int(probe.get("input_len")) == 0
            ):
                self._last_submission_probe["confirmed_by"] = (
                    "question_rendered_and_input_cleared"
                )
                return True
        return False

    async def _submit_question(
        self,
        question: str,
        baseline_probe: dict[str, Any],
    ) -> bool:
        if not await self._type_question_into_visible_input(question):
            logger.warning("[Doubao] No visible input accepted the question")
            return False
        await self.client.page.keyboard.press("Enter")
        if await self._submission_looks_started(
            baseline_probe, question, timeout_seconds=2.0
        ):
            logger.info("[Doubao] Question submission confirmed after Enter")
            return True
        latest_probe = getattr(self, "_last_submission_probe", {}).get("latest") or {}
        if not bool(latest_probe.get("input_contains_question")):
            if await self._submission_looks_started(
                baseline_probe, question, timeout_seconds=4.0
            ):
                logger.info(
                    "[Doubao] Question submission confirmed after input cleared"
                )
                return True
            logger.warning(
                "[Doubao] Question left the input after Enter but submission was not confirmed"
            )
            return False
        if await self._click_send_button() and await self._submission_looks_started(
            baseline_probe, question, timeout_seconds=4.0
        ):
            logger.info("[Doubao] Question submission confirmed after send-button click")
            return True
        logger.warning("[Doubao] Submission was not confirmed after Enter/button paths")
        return False

    async def recover_after_rate_limit(self, cooldown_seconds: int = 35) -> bool:
        """Cooldown and reopen chat page after Doubao rate limiting."""
        logger.info("[Doubao] Cooling down for %ss before retry", cooldown_seconds)
        await asyncio.sleep(cooldown_seconds)
        if getattr(self.client, "aio_session_id", None):
            open_result = await self.client.open(self.URL, headed=False)
        else:
            await self.client.close()
            open_result = await self.client.open(self.URL, headed=self.headed)
        if not open_result.get("success"):
            logger.warning("[Doubao] Failed to reopen after rate limit: %s", open_result.get("error"))
            return False
        await asyncio.sleep(3)
        return await self._wait_for_doubao_chat_ready(timeout=45)

    async def recover_after_verify(self, timeout: int = 300, prepare_window: bool = True) -> bool:
        """Wait until Doubao returns to a usable chat state after manual verify."""
        if prepare_window:
            logger.info("[Doubao] Opening headed browser for verify recovery")
            opened = await self._open_headed_for_user_action(self.URL)
            if not opened:
                logger.warning("[Doubao] Failed to open headed browser for verify")
                return False
        return await self._wait_for_doubao_chat_ready(timeout=timeout)

    async def _wait_for_doubao_chat_ready(self, timeout: int = 300) -> bool:
        """Wait until Doubao returns to a usable chat state."""
        input_selector = json.dumps(self._sel("input_ready"), ensure_ascii=False)
        elapsed = 0.0
        while elapsed < timeout:
            if self.client.page is not None:
                try:
                    ready = await self.client.page.evaluate(f"""() => {{
                        if (!location.pathname.includes('/chat')) return false;
                        const inputs = Array.from(document.querySelectorAll({input_selector}));
                        if (!inputs.some((el) => el.offsetParent !== null)) return false;
                        const loginBtn = document.querySelector('[data-testid="to_login_button"], [class*="login-btn"]');
                        if (loginBtn && loginBtn.offsetParent !== null) return false;
                        const verifyText = document.body?.innerText || '';
                        if (verifyText.includes('验证') || verifyText.toLowerCase().includes('verify')) return false;
                        return true;
                    }}""")
                    if ready:
                        logger.info("[Doubao] Chat page ready after recovery")
                        return True
                except Exception:
                    pass
            await asyncio.sleep(2)
            elapsed += 2
        logger.warning("[Doubao] Chat page was not ready within %ss", timeout)
        return False

    def _browser_agent_stage_note(
        self,
        *,
        stage: str,
        action_type: str | None = None,
    ) -> str | None:
        note = super()._browser_agent_stage_note(stage=stage, action_type=action_type)
        if stage == "resume_probe" and action_type == "login":
            return (
                f"{note} 豆包的就绪信号通常是已经进入 /chat 对话页，可见聊天输入区，"
                "且页面上不再出现登录按钮、验证提示或安全校验文案。"
            )
        if stage == "wait_gate":
            return (
                f"{note} 如果豆包已经转入安全验证、限流或登录阻塞，不要继续等待空答案。"
            )
        return note

    async def probe_takeover_ready(self, action_type: str) -> bool:
        if action_type == "login":
            return False
        return await super().probe_takeover_ready(action_type)

