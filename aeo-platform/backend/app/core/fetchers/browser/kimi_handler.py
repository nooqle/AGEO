"""Kimi browser handler.

NOTE: This module uses Playwright's page.evaluate() API to run JavaScript
in the browser context for DOM interaction — this is the standard Playwright
pattern for web scraping, not Python's built-in eval().
"""

import asyncio
import json
import logging
from typing import AsyncGenerator

from app.core.fetchers.browser.base_handler import BaseBrowserHandler
from app.core.fetchers.browser.parsers.base import BaseResponseParser
from app.core.fetchers.browser.parsers.connect import KimiConnectParser
from app.schemas.fetch import (
    BrowserState,
    FetchMethod,
    FetchResult,
    Platform,
    SearchReference,
)

logger = logging.getLogger(__name__)


class KimiHandler(BaseBrowserHandler):
    """Kimi browser-based handler.

    Uses Playwright to interact with Kimi Web UI.
    """

    URL = "https://kimi.com/"
    PLATFORM = Platform.KIMI
    PLATFORM_KEY = "kimi"

    _DEFAULTS: dict = {
        "input": ".chat-input-editor, [class*='chat-input'], [contenteditable='true']",
        "new_chat": ".new-chat-btn, [class*='new-chat']",
        "not_logged_in": ".not-login-container",
        "content": [
            ".chat-content-item-assistant .markdown",
            ".segment-assistant .markdown",
            ".segment-assistant .segment-content",
            ".markdown-container",
            ".message-list .markdown-body",
            "[class*='message'] .markdown-body",
            "[class*='markdown-body']",
        ],
        "login_modal": [
            ".login-modal-content", ".wechat-login", ".phone-login-mobile-number",
            '[placeholder="请输入手机号"]',
            "[class*='login-modal']", "[class*='login-dialog']", "[class*='auth-modal']",
        ],
        "citation_strip": "[class*='cite'], [class*='citation'], [class*='ref-num'], sup, a[data-index]",
        "reference_links": [
            ".source-item a", "[class*='source'] a[href^='http']",
            "[class*='reference'] a[href^='http']", "[data-testid*='source'] a",
            ".message-content a[href^='http']",
        ],
        "popup_close_icons": "[class*='activity'] img[class*='close'], [class*='banner'] img[class*='close']",
        "dismiss_texts": ["稍后再说", "关闭", "取消", "暂不升级", "我知道了"],
        "new_chat_text": "新建对话",
        "reference_expand_texts": ["来源", "Sources", "References", "引用来源"],
    }

    def _get_response_parser(self) -> BaseResponseParser | None:
        return KimiConnectParser()

    def _dismiss_popups_js(self) -> str:
        """Build popup dismissal JS for Kimi."""
        texts = json.dumps(self._sel("dismiss_texts"), ensure_ascii=False)
        icons_sel = json.dumps(self._sel("popup_close_icons"), ensure_ascii=False)
        return f"""() => {{
            let dismissed = 0;
            const dismissTexts = {texts};
            for (const txt of dismissTexts) {{
                const btns = [...document.querySelectorAll('button')];
                for (const btn of btns) {{
                    if ((btn.textContent || '').trim() === txt && btn.offsetParent !== null) {{
                        btn.click();
                        dismissed++;
                    }}
                }}
            }}
            const bannerClose = document.querySelectorAll({icons_sel});
            bannerClose.forEach(el => {{ el.click(); dismissed++; }});
            document.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Escape', bubbles: true}}));
            return dismissed;
        }}"""

    async def fetch(self, question: str) -> AsyncGenerator:
        """Fetch answer from Kimi Web."""
        self._refresh_selectors()
        try:
            # Step 1: Initializing
            yield self._create_event(BrowserState.INITIALIZING, "初始化浏览器...", progress=0.1)

            # Step 2: Navigate or start new chat
            yield self._create_event(BrowserState.NAVIGATING, f"正在访问 {self.URL}...", progress=0.2)
            page = self.client.page
            fast_path_ok = False
            page_url = page.url if page is not None else ""
            on_kimi = "kimi.moonshot.cn" in page_url or "kimi.com" in page_url

            if page is not None and on_kimi:
                # Dismiss popups BEFORE attempting new-chat click
                try:
                    dismissed = await page.evaluate(self._dismiss_popups_js())
                    if dismissed:
                        logger.info("[Kimi] Pre-navigation: dismissed %d popup(s)", dismissed)
                        await asyncio.sleep(0.5)
                except Exception:
                    pass

                # Attempt 1: CSS selector with scrollIntoView
                try:
                    new_chat = page.locator(self._sel("new_chat")).first
                    if await new_chat.count() > 0:
                        old_url = page.url
                        await new_chat.scroll_into_view_if_needed()
                        await new_chat.click(timeout=5000)
                        # Verify URL change instead of blind sleep
                        for _ in range(4):
                            await asyncio.sleep(0.5)
                            if page.url != old_url:
                                break
                        fast_path_ok = True
                        logger.info("[Kimi] Fast path: clicked 新建对话 (url_changed=%s)", page.url != old_url)
                except Exception as e:
                    logger.debug("[Kimi] Fast path CSS click failed: %s", e)

                # Attempt 2: text-based fallback
                if not fast_path_ok:
                    try:
                        btn = page.get_by_text(self._sel("new_chat_text"), exact=False).first
                        if await btn.count() > 0:
                            await btn.scroll_into_view_if_needed()
                            await btn.click(timeout=5000)
                            await asyncio.sleep(1.0)
                            fast_path_ok = True
                            logger.info("[Kimi] Fast path: clicked 新建对话 (text)")
                    except Exception as e:
                        logger.debug("[Kimi] Fast path text click failed: %s", e)

                # Attempt 3: retry after popup dismissal
                if not fast_path_ok:
                    try:
                        await page.evaluate(self._dismiss_popups_js())
                        await asyncio.sleep(1)
                        new_chat = page.locator(self._sel("new_chat")).first
                        if await new_chat.count() > 0:
                            await new_chat.click(force=True)
                            await asyncio.sleep(1.0)
                            fast_path_ok = True
                            logger.info("[Kimi] Fast path: clicked 新建对话 (retry)")
                    except Exception as e:
                        logger.debug("[Kimi] Fast path retry failed (%s), falling back", e)

            if not fast_path_ok:
                open_result = await self.client.open(self.URL, headed=self.headed)
                if not open_result.get("success"):
                    yield self._create_event(
                        BrowserState.ERROR,
                        f"浏览器打开失败: {open_result.get('error', '未知错误')}",
                        progress=0,
                    )
                    return
                await asyncio.sleep(4)

            if self.client.page:
                logger.info("[Kimi] Page URL: %s", self.client.page.url)

            # Step 3: Check login status (Kimi-specific multi-step detection)
            yield self._create_event(BrowserState.CHECKING_LOGIN, "检查登录状态...", progress=0.3)
            login_detected = await self._detect_login_needed()

            if login_detected:
                INPUT_READY_SELECTOR = ".chat-input-editor, [class*='chat-input']"
                waiting_message = "检测到需要登录，请在浏览器窗口中完成登录"
                action_hint = "请在弹出的浏览器窗口中完成 Kimi 登录，完成后点击“我已完成”"
                request_id = await self._prepare_user_action_request(
                    action_type="login",
                    message=waiting_message,
                    action_hint=action_hint,
                    progress=0.35,
                    url=self.URL,
                )
                if not request_id:
                    yield self._create_event(BrowserState.ERROR, "打开 Kimi 浏览器窗口失败，请重试", progress=0)
                    return
                yield self._create_event(
                    BrowserState.WAITING_FOR_LOGIN,
                    waiting_message,
                    progress=0.35,
                    requires_action=True,
                    action_type="login",
                    action_hint=action_hint,
                    request_id=request_id,
                )
                login_success = await self._wait_for_user_action_completion(
                    request_id=request_id,
                    ready_check=lambda ready_timeout: self._wait_for_login(
                        INPUT_READY_SELECTOR,
                        timeout=ready_timeout,
                    ),
                    timeout=300,
                    ready_timeout=120,
                )
                if not login_success:
                    yield self._create_event(BrowserState.ERROR, "登录超时，请重试", progress=0)
                    return

            # Step 3.5: Dismiss popups before interacting
            if self.client.page is not None:
                try:
                    dismissed = await self.client.page.evaluate(self._dismiss_popups_js())
                    if dismissed:
                        logger.info("[Kimi] Dismissed %d popup(s)", dismissed)
                        await asyncio.sleep(1)
                except Exception as e:
                    logger.debug("[Kimi] Popup dismissal failed: %s", e)

            # Step 4: Confirm input is ready
            yield self._create_event(BrowserState.ENABLING_SEARCH, "确认输入框可用...", progress=0.5)

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
                    editor = self.client.page.locator(self._sel("input")).first
                    if await editor.count() > 0:
                        await editor.click()
                        await asyncio.sleep(0.2)
                        await self.client.page.keyboard.press("Control+a")
                        await self.client.page.keyboard.type(question)
                        await asyncio.sleep(0.3)
                        await self.client.page.keyboard.press("Enter")
                        submitted = True
                        logger.info("[Kimi] Question submitted via .chat-input-editor keyboard")
                except Exception as e:
                    logger.debug("[Kimi] Direct locator submit failed: %s", e)

            if not submitted:
                snapshot = await self.client.snapshot(interactive_only=True)
                textarea_ref = self._find_textarea_ref(snapshot)
                if textarea_ref:
                    await self.client.fill(textarea_ref, question)
                    await asyncio.sleep(0.3)
                    await self.client.press("Enter")
                    submitted = True
                    logger.info("[Kimi] Question submitted via snapshot ref %s", textarea_ref)

            if not submitted:
                await self.client.find_and_fill("发送消息", question)
                await self.client.press("Enter")
                logger.info("[Kimi] Question submitted via find_and_fill fallback")

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
                    logger.info("[Kimi] Using network-intercepted data (%d chars, %d refs)",
                                len(answer_text), len(search_refs))
                elif parsed and parsed.error_type:
                    logger.warning("[Kimi] SSE error: %s (type=%s)", parsed.error, parsed.error_type)
                    yield self._create_event(
                        BrowserState.ERROR,
                        f"Kimi 返回错误: {parsed.error}",
                        progress=0,
                        error_type=parsed.error_type,
                    )
                    return

            # DOM fallback (with Kimi's late login detection)
            if not answer_text:
                logger.info("[Kimi] Falling back to DOM extraction")
                prev_len, waited, late_login_detected = await self._wait_for_content_with_login_check(
                    max_wait=60,
                    detect_late_login=True,
                )

                if late_login_detected:
                    waiting_message = "检测到 Kimi 在回复过程中要求重新登录，请在浏览器窗口中完成登录"
                    action_hint = "请在弹出的浏览器窗口中完成 Kimi 登录，完成后点击“我已完成”"
                    request_id = await self._prepare_user_action_request(
                        action_type="login",
                        message=waiting_message,
                        action_hint=action_hint,
                        progress=0.72,
                        url=self.URL,
                    )
                    if not request_id:
                        yield self._create_event(BrowserState.ERROR, "打开 Kimi 浏览器窗口失败，请重试", progress=0)
                        return
                    yield self._create_event(
                        BrowserState.WAITING_FOR_LOGIN,
                        waiting_message,
                        progress=0.72,
                        requires_action=True,
                        action_type="login",
                        action_hint=action_hint,
                        request_id=request_id,
                    )
                    login_success = await self._wait_for_user_action_completion(
                        request_id=request_id,
                        ready_check=lambda ready_timeout: self._wait_for_login(
                            INPUT_READY_SELECTOR,
                            timeout=ready_timeout,
                        ),
                        timeout=300,
                        ready_timeout=120,
                    )
                    if not login_success:
                        yield self._create_event(BrowserState.ERROR, "重新登录超时，请重试", progress=0)
                        return

                    await self._resubmit_question(question)
                    prev_len, waited, _ = await self._wait_for_content_with_login_check(
                        max_wait=60,
                        detect_late_login=False,
                    )

                if prev_len == 0:
                    await self._dump_page_debug(waited, extra_keywords=[
                        'segment', 'bubble', 'text', 'response',
                    ])

                yield self._create_event(BrowserState.EXTRACTING, "提取回答内容...", progress=0.9)
                answer_text = await self._extract_answer_dom()
                search_refs = await self._extract_references_dom()

            if not answer_text or len(answer_text.strip()) < 10:
                logger.warning("[Kimi] Answer too short or empty (%d chars)",
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

    # ------------------------------------------------------------------ Kimi-specific helpers

    async def _detect_login_needed(self) -> bool:
        """Detect if Kimi requires login (multi-step check).

        Uses Playwright page.evaluate() to run JS in the browser context.
        """
        if self.client.page is None:
            return False
        try:
            login_check = await self.client.page.evaluate("""() => {
                const selectors = [
                    '.login-modal-content', '.wechat-login',
                    '.phone-login-mobile-number', '[placeholder="请输入手机号"]',
                    '[class*="login-modal"]', '[class*="login-dialog"]', '[class*="auth-modal"]',
                ];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    // Must check visibility — hidden login DOM shouldn't trigger login flow
                    if (el && el.offsetParent !== null) return sel;
                }
                const notLogin = document.querySelector('.not-login-container');
                if (notLogin && (notLogin.textContent || '').includes('登录')) {
                    return '__need_login__';
                }
                const input = document.querySelector('.chat-input-editor');
                if (input) return '__input_ready__';
                return '__no_input__';
            }""")
            result_str = login_check if isinstance(login_check, str) else str(login_check)

            if result_str == '__input_ready__':
                logger.info("[Kimi] Input ready, no login required")
                return False
            elif result_str == '__need_login__':
                logger.info("[Kimi] Not logged in (.not-login-container detected)")
                return True
            elif result_str == '__no_input__':
                logger.info("[Kimi] No input found yet, waiting for SPA to finish loading...")
                for _wait_round in range(4):
                    await asyncio.sleep(2)
                    retry_check = await self.client.page.evaluate("""() => {
                        const input = document.querySelector('.chat-input-editor')
                            || document.querySelector('[class*="chat-input"]')
                            || document.querySelector('[contenteditable="true"]');
                        if (input && input.offsetParent !== null) return '__input_ready__';
                        const loginSels = ['.login-modal-content', '.wechat-login',
                            '[class*="login-modal"]', '[class*="login-dialog"]'];
                        for (const sel of loginSels) {
                            const el = document.querySelector(sel);
                            if (el && el.offsetParent !== null) return sel;
                        }
                        return '__no_input__';
                    }""")
                    retry_str = retry_check if isinstance(retry_check, str) else str(retry_check)
                    if retry_str == '__input_ready__':
                        logger.info("[Kimi] Input became ready after extra wait")
                        return False
                    if retry_str != '__no_input__':
                        logger.info("[Kimi] Login modal appeared after wait: %s", retry_str)
                        return True
                logger.warning("[Kimi] Input still unavailable after extended wait, assuming login required")
                return True
            else:
                logger.info("[Kimi] Login modal detected via: %s", result_str)
                return True
        except Exception as e:
            logger.debug("[Kimi] Login detection check failed: %s", e)
            return False

    async def _wait_for_content_with_login_check(
        self,
        max_wait: float = 60,
        detect_late_login: bool = True,
    ) -> tuple[int, float, bool]:
        """Wait for content stability with late login modal detection.

        Returns (final_content_len, waited_seconds, late_login_detected).
        """
        await asyncio.sleep(3)
        waited = 3.0
        prev_len = 0
        stable_count = 0

        _LOGIN_CHECK_JS = """() => {
            const sels = ['.login-modal-content', '.wechat-login',
                          '[class*="login-modal"]', '[class*="login-dialog"]'];
            for (const s of sels) {
                const el = document.querySelector(s);
                if (el && el.offsetParent !== null) return true;
            }
            return false;
        }"""

        while waited < max_wait:
            await asyncio.sleep(3)
            waited += 3
            result = await self.client.eval(self._content_check_js())
            if "error" in result:
                logger.warning("[Kimi] eval error at %ds: %s", waited, result["error"])
            cur_len = int(result.get("output", "0") or "0")
            logger.info("[Kimi] Poll %ds: content_len=%d (prev=%d, stable=%d)",
                        waited, cur_len, prev_len, stable_count)

            # Detect late login modal
            if detect_late_login and cur_len == 0 and waited >= 12 and self.client.page is not None:
                try:
                    has_login = await self.client.page.evaluate(_LOGIN_CHECK_JS)
                    if has_login:
                        logger.warning("[Kimi] Late login modal detected at %ds", waited)
                        return prev_len, waited, True
                except Exception as e:
                    logger.debug("[Kimi] Late login check failed: %s", e)

            MIN_CONTENT_LEN = 100
            if cur_len > 0 and cur_len == prev_len:
                stable_count += 1
                if stable_count >= 2 and cur_len >= MIN_CONTENT_LEN:
                    logger.info("[Kimi] Content stable at %d chars after %ds", cur_len, waited)
                    break
            else:
                stable_count = 0
            prev_len = cur_len

        return prev_len, waited, False

    async def _resubmit_question(self, question: str) -> None:
        """Re-submit the question after manual login recovery."""
        await asyncio.sleep(1.5)
        if self.client.page is not None:
            try:
                await self.client.page.evaluate(self._dismiss_popups_js())
                await asyncio.sleep(1)
            except Exception:
                pass

        if self.client.page is not None:
            try:
                editor = self.client.page.locator(self._sel("input")).first
                if await editor.count() > 0:
                    await editor.click()
                    await asyncio.sleep(0.2)
                    await self.client.page.keyboard.press("Control+a")
                    await self.client.page.keyboard.type(question)
                    await asyncio.sleep(0.3)
                    await self.client.page.keyboard.press("Enter")
                    logger.info("[Kimi] Re-submitted question after login")
            except Exception as e:
                logger.warning("[Kimi] Re-submit after login failed: %s", e)
