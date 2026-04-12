"""Doubao (ByteDance) browser handler."""

import asyncio
import logging
from typing import AsyncGenerator

from app.core.fetchers.browser.base_handler import BaseBrowserHandler
from app.core.fetchers.browser.parsers.base import BaseResponseParser
from app.core.fetchers.browser.parsers.sse import DoubaoSSEParser
from app.schemas.fetch import (
    BrowserState,
    Platform,
    SearchReference,
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

    _DEFAULTS: dict = {
        "input": "textarea.semi-input-textarea, textarea",
        "input_ready": "textarea.semi-input-textarea, textarea",
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

            chat_ready = await self._wait_for_doubao_chat_ready(timeout=6)
            if chat_ready:
                logger.info("[Doubao] Chat page already ready after open, skipping manual prompts")
            else:
                detected_modal = await self._detect_blocking_modal()
                if detected_modal:
                    logger.info("[Doubao] Blocking modal detected before login check: %s", detected_modal)
                    waiting_message = "检测到豆包页面弹窗需要确认，请在浏览器窗口中操作"
                    action_hint = "请在弹出的浏览器窗口中关闭弹窗或同意协议，完成后点击“我已完成”"
                    events, request_id = await self._begin_modal_takeover_gate(
                        message=waiting_message,
                        action_hint=action_hint,
                        progress=0.25,
                        url=self.URL,
                        open_error_message="打开豆包浏览器窗口失败，请重试",
                    )
                    for event in events:
                        yield event
                    if not request_id:
                        return
                    return

            # Step 3: Check login status
            yield self._create_event(BrowserState.CHECKING_LOGIN, "检查登录状态...", progress=0.3)

            login_needed = not chat_ready
            if self.client.page is not None:
                try:
                    # Multi-signal login check: textarea alone is NOT enough
                    # (landing page also has textarea when not logged in)
                    logged_in = await self.client.page.evaluate("""() => {
                        const textarea = document.querySelector('textarea.semi-input-textarea, textarea');
                        if (!textarea) return false;
                        // Signal 1: URL must contain /chat/ (logged-in chat page)
                        if (!location.pathname.includes('/chat')) return false;
                        // Signal 2: No visible login button
                        const loginBtn = document.querySelector('[data-testid="to_login_button"], [class*="login-btn"]');
                        if (loginBtn && loginBtn.offsetParent !== null) return false;
                        return true;
                    }""")
                    login_needed = not logged_in
                    logger.info("[Doubao] Login check: logged_in=%s (URL+textarea+no_login_btn)", logged_in)
                except Exception as e:
                    logger.debug("[Doubao] Login check failed: %s", e)

            if login_needed:
                waiting_message = "检测到需要登录，请在浏览器窗口中完成登录"
                action_hint = "请在弹出的浏览器窗口中完成豆包登录，完成后点击“我已完成”"
                events, request_id = await self._begin_login_takeover_gate(
                    message=waiting_message,
                    action_hint=action_hint,
                    progress=0.35,
                    url=self.URL,
                    open_error_message="打开豆包浏览器窗口失败，请重试",
                )
                for event in events:
                    yield event
                if not request_id:
                    return
                return

                detected_modal = ""
                if not await self._wait_for_doubao_chat_ready(timeout=6):
                    detected_modal = await self._detect_blocking_modal()
                if detected_modal:
                    logger.info("[Doubao] Blocking modal detected after login: %s", detected_modal)
                    waiting_message = "检测到豆包页面弹窗需要确认，请在浏览器窗口中操作"
                    action_hint = "请在弹出的浏览器窗口中关闭弹窗或同意协议，完成后点击“我已完成”"
                    events, request_id = await self._begin_modal_takeover_gate(
                        message=waiting_message,
                        action_hint=action_hint,
                        progress=0.4,
                        url=self.URL,
                        open_error_message="打开豆包浏览器窗口失败，请重试",
                    )
                    for event in events:
                        yield event
                    if not request_id:
                        return
                    return

            # Step 4: Enable web search
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

            # Step 5b: Submit question
            submitted = False
            if self.client.page is not None:
                try:
                    textarea = self.client.page.locator(self._sel("input")).first
                    if await textarea.count() > 0:
                        await textarea.fill(question)
                        await asyncio.sleep(0.3)
                        await self.client.page.keyboard.press("Enter")
                        submitted = True
                        logger.info("[Doubao] Question submitted via textarea + Enter")
                except Exception as e:
                    logger.debug("[Doubao] Direct submit failed: %s", e)

            if not submitted:
                await self.client.find_and_fill("发消息", question)
                await self.client.press("Enter")
                logger.info("[Doubao] Question submitted via find_and_fill fallback")

            # Step 6: Wait for response (network interception first, fallback to DOM)
            yield self._create_event(BrowserState.WAITING_RESPONSE, "等待 AI 回复...", progress=0.7)
            answer_text = ""
            search_refs: list[SearchReference] = []
            source = "dom"

            if intercept_task:
                parsed = await intercept_task
                if parsed and parsed.parse_ok and len(parsed.answer_text.strip()) >= 10:
                    answer_text = parsed.answer_text
                    search_refs = parsed.references
                    source = "network"
                    logger.info("[Doubao] Using network-intercepted data (%d chars, %d refs)",
                                len(answer_text), len(search_refs))
                elif parsed and parsed.error_type:
                    # SSE error detected — skip DOM fallback, report specific error
                    logger.warning("[Doubao] SSE error: %s (type=%s)", parsed.error, parsed.error_type)
                    events, handled = await self._handle_browser_agent_parser_error(
                        parsed_error=parsed.error,
                        error_type=parsed.error_type,
                        progress=0.68,
                        fallback_url=self.URL,
                        message_overrides={
                            "rate_limit": "豆包触发平台限流，请稍后重试，或降低并发后再采集。",
                            "verify": "豆包触发安全验证，请在浏览器窗口完成验证后重新采集。",
                        },
                    )
                    for event in events:
                        yield event
                    if handled:
                        return
                    return

            # DOM fallback
            if not answer_text:
                logger.info("[Doubao] Falling back to DOM extraction")
                prev_len, waited, blocker_decision = await self._wait_for_content_with_browser_agent(
                    max_wait=60, poll_interval=3, min_content_len=80,
                    target_url=self.URL,
                )
                events, handled = await self._handle_browser_agent_wait_blocker(
                    blocker_decision,
                    progress=0.72,
                    fallback_url=self.URL,
                )
                for event in events:
                    yield event
                if handled:
                    return
                if prev_len == 0:
                    await self._dump_page_debug(waited)

                yield self._create_event(BrowserState.EXTRACTING, "提取回答内容...", progress=0.9)
                answer_text = await self._extract_answer_dom()
                search_refs = await self._extract_references_dom()

            events, handled = await self._handle_browser_agent_empty_answer(
                answer_text,
                progress=0.92,
                fallback_url=self.URL,
            )
            for event in events:
                yield event
            if handled:
                return

            # Step 7: Build result
            yield self._create_event(BrowserState.EXTRACTING, "提取回答内容...", progress=0.9)
            fetch_result = await self._build_success_result(
                question=question,
                answer_text=answer_text,
                search_references=search_refs,
                source=source,
            )

            yield self._create_event(BrowserState.COMPLETED, "抓取完成", progress=1.0, data=fetch_result)

        except Exception as e:
            yield self._create_event(BrowserState.ERROR, f"抓取失败: {str(e)}", progress=0)

    # ------------------------------------------------------------------ Doubao-specific helpers

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
        elapsed = 0.0
        while elapsed < timeout:
            if self.client.page is not None:
                try:
                    ready = await self.client.page.evaluate("""() => {
                        if (!location.pathname.includes('/chat')) return false;
                        const textarea = document.querySelector('textarea.semi-input-textarea, textarea');
                        if (!textarea) return false;
                        const loginBtn = document.querySelector('[data-testid="to_login_button"], [class*="login-btn"]');
                        if (loginBtn && loginBtn.offsetParent !== null) return false;
                        const verifyText = document.body?.innerText || '';
                        if (verifyText.includes('验证') || verifyText.toLowerCase().includes('verify')) return false;
                        return true;
                    }""")
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

