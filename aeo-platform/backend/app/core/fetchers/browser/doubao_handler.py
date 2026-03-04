"""Doubao (ByteDance) browser handler."""

import asyncio
import logging
from typing import AsyncGenerator

from app.core.fetchers.browser.base_handler import BaseBrowserHandler
from app.core.fetchers.browser.parsers.base import BaseResponseParser
from app.core.fetchers.browser.parsers.sse import DoubaoSSEParser
from app.schemas.fetch import (
    BrowserState,
    FetchMethod,
    FetchResult,
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
                        await btn.click()
                        await asyncio.sleep(1.5)
                        fast_path_ok = True
                        logger.info("[Doubao] Fast path: clicked %s", new_chat_text)
                except Exception as e:
                    logger.debug("[Doubao] Fast path click failed: %s", e)

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

            # Step 3: Check login status
            yield self._create_event(BrowserState.CHECKING_LOGIN, "检查登录状态...", progress=0.3)

            INPUT_READY_SELECTOR = self._sel("input_ready")
            login_needed = True
            if self.client.page is not None:
                try:
                    el = await self.client.page.query_selector(INPUT_READY_SELECTOR)
                    if el is not None:
                        login_needed = False
                        logger.info("[Doubao] Already logged in (input found)")
                    else:
                        logger.info("[Doubao] Not logged in (no input found)")
                except Exception as e:
                    logger.debug("[Doubao] Login check failed: %s", e)

            if login_needed:
                yield self._create_event(
                    BrowserState.WAITING_FOR_LOGIN,
                    "检测到需要登录，请在浏览器窗口中完成登录",
                    progress=0.35, requires_action=True,
                    action_hint="请在弹出的浏览器窗口中完成豆包登录",
                )
                await self.client.close()
                await self.client.open(self.URL, headed=True)
                login_success = await self._wait_for_login(INPUT_READY_SELECTOR, timeout=300)
                if not login_success:
                    yield self._create_event(BrowserState.ERROR, "登录超时，请重试", progress=0)
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

            # DOM fallback
            if not answer_text:
                logger.info("[Doubao] Falling back to DOM extraction")
                prev_len, waited = await self._wait_for_content_stable(
                    max_wait=60, poll_interval=3, min_content_len=80,
                )
                if prev_len == 0:
                    await self._dump_page_debug(waited)

                yield self._create_event(BrowserState.EXTRACTING, "提取回答内容...", progress=0.9)
                answer_text = await self._extract_answer_dom()
                search_refs = await self._extract_references_dom()

            if not answer_text or len(answer_text.strip()) < 10:
                logger.warning("[Doubao] Answer too short or empty (%d chars)",
                               len(answer_text) if answer_text else 0)
                yield self._create_event(BrowserState.ERROR, "未能提取到有效回答", progress=0)
                return

            # Step 7: Build result
            yield self._create_event(BrowserState.EXTRACTING, "提取回答内容...", progress=0.9)
            fetch_result = FetchResult(
                id=f"{self.PLATFORM.value}_{hash(question)}",
                question_id="",
                question_text=question,
                platform=self.PLATFORM,
                fetch_method=FetchMethod.BROWSER,
                status="success",
                answer_text=answer_text,
                search_references=search_refs,
                raw_response={"source": source},
                error_message=None,
                fetch_duration=None,
            )

            yield self._create_event(BrowserState.COMPLETED, "抓取完成", progress=1.0, data=fetch_result)

        except Exception as e:
            yield self._create_event(BrowserState.ERROR, f"抓取失败: {str(e)}", progress=0)
