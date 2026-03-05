"""Yuanbao (Tencent) browser handler."""

import asyncio
import json
import logging
from typing import AsyncGenerator

from app.core.fetchers.browser.base_handler import BaseBrowserHandler
from app.core.fetchers.browser.parsers.base import BaseResponseParser
from app.core.fetchers.browser.parsers.sse import YuanbaoSSEParser
from app.schemas.fetch import (
    BrowserState,
    FetchMethod,
    FetchResult,
    Platform,
    SearchReference,
)

logger = logging.getLogger(__name__)


class YuanbaoHandler(BaseBrowserHandler):
    """Yuanbao (Tencent Hunyuan) browser-based handler.

    Uses Playwright to interact with yuanbao.tencent.com.
    Ensures the Hunyuan model is selected (not DeepSeek).
    """

    URL = "https://yuanbao.tencent.com/"
    PLATFORM = Platform.HUNYUAN
    PLATFORM_KEY = "yuanbao"
    DOUBLE_UTF8_FIX = True  # Yuanbao SSE body is double UTF-8 encoded

    _DEFAULTS: dict = {
        "input": ".ql-editor",
        "input_ready": ".ql-editor",
        "new_chat": ".icon-yb-ic_newchat_20",
        "send_btn": "a[class*='send-btn']:not([class*='disabled'])",
        "model_selector": ".ybc-model-select-button",
        "target_model": "Hunyuan",
        "not_logged_in": ".nologin",
        "login_btn": "button.agent-dialogue__tool__login",
        "content": [
            ".agent-dialogue__content--common__content",
            "[class*='hyc-content-markdown']",
            "[class*='hyc-markdown']",
            "[class*='agent-dialogue'] [class*='content']",
            "[class*='markdown-body']",
            "[class*='markdown']",
        ],
        "web_search_btn": ".yb-internet-search-btn",
        "citation_strip": "[class*='cite'], [class*='citation'], [class*='ref-num'], sup, a[data-index]",
        "reference_links": [
            "[class*='source'] a[href^='http']",
            "[class*='reference'] a[href^='http']",
            "[class*='search-result'] a[href^='http']",
            "a[href^='http'][class*='link']",
        ],
        "popup_close_icons": "[class*='close-icon'], [class*='banner'] [class*='close']",
        "dismiss_texts": ["关闭", "稍后再说", "我知道了"],
        "reference_expand_texts": ["来源", "引用", "Sources", "References"],
    }

    def _get_response_parser(self) -> BaseResponseParser | None:
        return YuanbaoSSEParser()

    def _dismiss_popups_js(self) -> str:
        """Build popup dismissal JS for Yuanbao."""
        texts = json.dumps(self._sel("dismiss_texts"), ensure_ascii=False)
        icons_sel = json.dumps(self._sel("popup_close_icons"), ensure_ascii=False)
        return f"""() => {{
            let dismissed = 0;
            const dismissTexts = {texts};
            for (const txt of dismissTexts) {{
                const btns = [...document.querySelectorAll('button, a, [role="button"]')];
                for (const btn of btns) {{
                    if ((btn.textContent || '').trim() === txt && btn.offsetParent !== null) {{
                        btn.click();
                        dismissed++;
                    }}
                }}
            }}
            const closeIcons = document.querySelectorAll({icons_sel});
            closeIcons.forEach(el => {{ el.click(); dismissed++; }});
            document.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Escape', bubbles: true}}));
            return dismissed;
        }}"""

    async def fetch(self, question: str) -> AsyncGenerator:
        """Fetch answer from Yuanbao Web."""
        self._refresh_selectors()
        try:
            # Step 1: Initializing
            yield self._create_event(BrowserState.INITIALIZING, "初始化浏览器...", progress=0.1)

            # Step 2: Navigate or start new chat
            yield self._create_event(BrowserState.NAVIGATING, f"正在访问 {self.URL}...", progress=0.2)
            page = self.client.page
            fast_path_ok = False
            page_url = page.url if page is not None else ""

            if page is not None and "yuanbao.tencent.com" in page_url:
                try:
                    dismissed = await page.evaluate(self._dismiss_popups_js())
                    if dismissed:
                        logger.info("[Yuanbao] Pre-navigation: dismissed %d popup(s)", dismissed)
                        await asyncio.sleep(0.5)
                except Exception:
                    pass

                try:
                    new_chat = page.locator(self._sel("new_chat")).first
                    if await new_chat.count() > 0:
                        await new_chat.click(timeout=5000)
                        await asyncio.sleep(1.5)
                        fast_path_ok = True
                        logger.info("[Yuanbao] Fast path: clicked new chat icon")
                except Exception as e:
                    logger.debug("[Yuanbao] Fast path click failed: %s", e)

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
                logger.info("[Yuanbao] Page URL: %s", self.client.page.url)

            # Step 3: Check login status
            yield self._create_event(BrowserState.CHECKING_LOGIN, "检查登录状态...", progress=0.3)
            login_needed = False
            if self.client.page is not None:
                try:
                    login_needed = await self.client.page.evaluate(f"""() => {{
                        const nologin = document.querySelector('{self._sel("not_logged_in")}');
                        if (nologin && nologin.offsetParent !== null) return true;
                        const loginBtn = document.querySelector('{self._sel("login_btn")}');
                        if (loginBtn && loginBtn.offsetParent !== null) return true;
                        const editor = document.querySelector('{self._sel("input")}');
                        if (editor) {{
                            const ph = editor.getAttribute('data-placeholder') || '';
                            if (ph.includes('登录')) return true;
                        }}
                        return false;
                    }}""")
                except Exception as e:
                    logger.debug("[Yuanbao] Login check failed: %s", e)

            if login_needed:
                yield self._create_event(
                    BrowserState.WAITING_FOR_LOGIN,
                    "检测到需要登录，请在浏览器窗口中完成登录",
                    progress=0.35, requires_action=True,
                    action_hint="请在弹出的浏览器窗口中完成元宝登录（支持微信/QQ扫码）",
                )
                await self.client.close()
                await self.client.open(self.URL, headed=True)
                login_success = await self._wait_for_login_ready(timeout=300)
                if not login_success:
                    yield self._create_event(BrowserState.ERROR, "登录超时，请重试", progress=0)
                    return

            # Step 3.5: Dismiss popups after navigation / login
            if self.client.page is not None:
                try:
                    dismissed = await self.client.page.evaluate(self._dismiss_popups_js())
                    if dismissed:
                        logger.info("[Yuanbao] Dismissed %d popup(s)", dismissed)
                        await asyncio.sleep(0.5)
                except Exception:
                    pass

            # Step 4: Ensure Hunyuan model is selected
            yield self._create_event(BrowserState.ENABLING_SEARCH, "确认模型和联网搜索...", progress=0.45)
            if self.client.page is not None:
                await self._ensure_hunyuan_model()
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
            if self.client.page is not None:
                try:
                    editor = self.client.page.locator(self._sel("input")).first
                    if await editor.count() > 0:
                        await editor.click()
                        await asyncio.sleep(0.2)
                        await self.client.page.keyboard.press("Control+a")
                        await self.client.page.keyboard.type(question)
                        await asyncio.sleep(0.5)

                        send_btn = self.client.page.locator(self._sel("send_btn")).first
                        if await send_btn.count() > 0:
                            await send_btn.click()
                            submitted = True
                            logger.info("[Yuanbao] Question submitted via send button")
                        else:
                            await self.client.page.keyboard.press("Enter")
                            submitted = True
                            logger.info("[Yuanbao] Question submitted via Enter key")
                except Exception as e:
                    logger.debug("[Yuanbao] Direct submit failed: %s", e)

            if not submitted:
                await self.client.find_and_fill("输入内容", question)
                await self.client.press("Enter")
                logger.info("[Yuanbao] Question submitted via find_and_fill fallback")

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
                    logger.info("[Yuanbao] Using network-intercepted data (%d chars, %d refs)",
                                len(answer_text), len(search_refs))
                elif parsed and parsed.error_type:
                    logger.warning("[Yuanbao] SSE error: %s (type=%s)", parsed.error, parsed.error_type)
                    yield self._create_event(
                        BrowserState.ERROR,
                        f"元宝返回错误: {parsed.error}",
                        progress=0,
                        error_type=parsed.error_type,
                    )
                    return

            # DOM fallback
            if not answer_text:
                logger.info("[Yuanbao] Falling back to DOM extraction")
                prev_len, waited = await self._wait_for_content_stable(
                    max_wait=60, poll_interval=3, min_content_len=100,
                )
                if prev_len == 0:
                    await self._dump_page_debug(waited, extra_keywords=['agent-dialogue'])

                # Expand collapsed content
                if self.client.page is not None:
                    try:
                        expand_clicked = await self.client.page.evaluate("""() => {
                            const sels = [
                                '[class*="expand"]', '[class*="fold"] [class*="arrow"]',
                                '[class*="collapse"]', 'svg[class*="arrow"]',
                            ];
                            let clicked = 0;
                            for (const sel of sels) {
                                const els = document.querySelectorAll(sel);
                                els.forEach(el => { el.click(); clicked++; });
                            }
                            const btns = Array.from(document.querySelectorAll('button, a, [role="button"], span'));
                            for (const btn of btns) {
                                const txt = (btn.textContent || '').trim();
                                if (txt === '展开' || txt === '展开全部' || txt === '查看完整回答') {
                                    btn.click(); clicked++;
                                }
                            }
                            return clicked;
                        }""")
                        if expand_clicked:
                            logger.info("[Yuanbao] Clicked %d expand elements, waiting 1s", expand_clicked)
                            await asyncio.sleep(1)
                    except Exception as e:
                        logger.debug("[Yuanbao] Expand attempt failed: %s", e)

                yield self._create_event(BrowserState.EXTRACTING, "提取回答内容...", progress=0.9)
                answer_text = await self._extract_answer_dom()
                search_refs = await self._extract_references_dom()

            if not answer_text or len(answer_text.strip()) < 10:
                logger.warning("[Yuanbao] Answer too short or empty (%d chars)",
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

    # ------------------------------------------------------------------ platform-specific helpers

    async def _wait_for_login_ready(self, timeout: int = 300) -> bool:
        """Wait until user logs in and input becomes available."""
        elapsed = 0.0
        while elapsed < timeout:
            if self.client.page is not None:
                try:
                    ready = await self.client.page.evaluate(f"""() => {{
                        const editor = document.querySelector('{self._sel("input")}');
                        if (!editor) return false;
                        const ph = editor.getAttribute('data-placeholder') || '';
                        return !ph.includes('登录');
                    }}""")
                    if ready:
                        return True
                except Exception:
                    pass
            await asyncio.sleep(2)
            elapsed += 2
        return False

    async def _ensure_hunyuan_model(self) -> None:
        """Ensure the Hunyuan model is selected (not DeepSeek)."""
        page = self.client.page
        if page is None:
            return
        try:
            model_sel = self._sel("model_selector")
            target = self._sel("target_model")

            model_btn = page.locator(model_sel).first
            if await model_btn.count() == 0:
                logger.debug("[Yuanbao] Model selector not found")
                return

            current_text = await model_btn.text_content()
            if current_text and target.lower() in current_text.lower():
                logger.info("[Yuanbao] Model already set to %s", target)
                return

            await model_btn.click()
            await asyncio.sleep(0.5)
            option = page.get_by_text(target, exact=False).first
            if await option.count() > 0:
                await option.click()
                await asyncio.sleep(0.5)
                logger.info("[Yuanbao] Switched model to %s", target)
            else:
                await page.keyboard.press("Escape")
                logger.warning("[Yuanbao] Model '%s' not found in selector", target)
        except Exception as e:
            logger.warning("[Yuanbao] _ensure_hunyuan_model failed: %s", e)

    async def _ensure_web_search_on(self) -> None:
        """Ensure web search is enabled."""
        page = self.client.page
        if page is None:
            return
        try:
            search_btn = page.locator(self._sel("web_search_btn")).first
            if await search_btn.count() == 0:
                logger.debug("[Yuanbao] Web search button not found")
                return

            is_active = await search_btn.evaluate("""el => {
                return el.classList.contains('active') ||
                       el.classList.contains('selected') ||
                       el.getAttribute('aria-pressed') === 'true' ||
                       (el.className || '').includes('active') ||
                       (el.className || '').includes('selected');
            }""")

            if is_active:
                logger.info("[Yuanbao] Web search already ON")
            else:
                await search_btn.click()
                await asyncio.sleep(0.3)
                logger.info("[Yuanbao] Enabled web search")
        except Exception as e:
            logger.warning("[Yuanbao] _ensure_web_search_on failed: %s", e)
