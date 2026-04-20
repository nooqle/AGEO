"""Yuanbao (Tencent) browser handler."""

import asyncio
import json
import logging
from typing import AsyncGenerator

from app.core.fetchers.browser.base_handler import BaseBrowserHandler
from app.core.fetchers.browser.browser_executor import (
    BrowserAnswerExecutionPlan,
    execute_post_submit_capture_flow,
)
from app.core.fetchers.browser.parsers.base import BaseResponseParser
from app.core.fetchers.browser.parsers.sse import YuanbaoSSEParser
from app.schemas.fetch import (
    BrowserState,
    Platform,
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
    BROWSER_READY_URL_PATTERNS = ("yuanbao.tencent.com",)
    BROWSER_LOGIN_URL_PATTERNS = ("login", "signin", "auth")
    BROWSER_READY_HINTS = ("hunyuan", "新建对话", "联网搜索")
    BROWSER_LOGIN_HINTS = ("登录", "手机号", "验证码", "扫码", "二维码")
    BROWSER_LATE_BLOCKER_HINTS = ("安全验证", "人机验证", "验证码", "账号选择")

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

    def _login_surface_state_js(self) -> str:
        input_sel = json.dumps(self._sel("input"), ensure_ascii=False)
        send_sel = json.dumps(self._sel("send_btn"), ensure_ascii=False)
        new_chat_sel = json.dumps(self._sel("new_chat"), ensure_ascii=False)
        model_sel = json.dumps(self._sel("model_selector"), ensure_ascii=False)
        search_sel = json.dumps(self._sel("web_search_btn"), ensure_ascii=False)
        not_logged_sel = json.dumps(self._sel("not_logged_in"), ensure_ascii=False)
        login_btn_sel = json.dumps(self._sel("login_btn"), ensure_ascii=False)
        return f"""() => {{
            const isVisible = (el) => Boolean(el && el.offsetParent !== null);
            const editor = document.querySelector({input_sel});
            const editorPlaceholder = editor?.getAttribute('data-placeholder') || '';
            const editorReady = isVisible(editor) && !editorPlaceholder.includes('登录');
            const readySignals = [
              document.querySelector({send_sel}),
              document.querySelector({new_chat_sel}),
              document.querySelector({model_sel}),
              document.querySelector({search_sel}),
            ];
            const actionNodes = [...document.querySelectorAll('button, a, [role="button"], span')];
            const visibleActionTexts = actionNodes
              .filter(isVisible)
              .map((el) => (el.textContent || '').trim())
              .filter(Boolean);
            const explicitLoginCta = visibleActionTexts.some((text) =>
              /(log\\s*in|sign\\s*in|登录|立即登录|微信登录|手机号登录|注册)/i.test(text)
            );
            const loginNeeded =
              isVisible(document.querySelector({not_logged_sel})) ||
              isVisible(document.querySelector({login_btn_sel})) ||
              explicitLoginCta ||
              /(login|signin|auth)/i.test(window.location.href);
            const ready = (editorReady || readySignals.some(isVisible)) && !loginNeeded;
            return {{
              ready,
              loginNeeded,
              editorReady,
            }};
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
                await asyncio.sleep(4)

            if self.client.page:
                logger.info("[Yuanbao] Page URL: %s", self.client.page.url)

            preflight_events, should_abort = await self._run_browser_agent_preflight(
                progress=0.28,
                url=self.URL,
            )
            for event in preflight_events:
                yield event
            if should_abort:
                return

            # Step 3: Dismiss popups after navigation / login
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

            yield self._create_event(BrowserState.WAITING_RESPONSE, "等待 AI 回复...", progress=0.7)
            fetch_result, events = await execute_post_submit_capture_flow(
                self,
                BrowserAnswerExecutionPlan(
                    question=question,
                    intercept_task=intercept_task,
                    fallback_url=self.URL,
                    max_wait=60,
                    poll_interval=3,
                    min_content_len=100,
                    dump_keywords=["agent-dialogue"],
                    before_dom_extract=self._expand_collapsed_answer_sections,
                ),
            )
            for event in events:
                yield event
            if fetch_result is None:
                return

            yield self._create_event(BrowserState.COMPLETED, "抓取完成", progress=1.0, data=fetch_result)

        except Exception as e:
            yield self._create_event(BrowserState.ERROR, f"抓取失败: {str(e)}", progress=0)

    # ------------------------------------------------------------------ platform-specific helpers

    def _browser_agent_stage_note(
        self,
        *,
        stage: str,
        action_type: str | None = None,
    ) -> str | None:
        note = super()._browser_agent_stage_note(stage=stage, action_type=action_type)
        if stage == "resume_probe" and action_type == "login":
            return (
                f"{note} 元宝的就绪信号通常是已经回到对话页面，可见输入区，"
                "且登录抽屉、二维码、短信验证或账号确认控件已经消失。"
            )
        if stage == "wait_gate":
            return (
                f"{note} 如果元宝已经弹出登录抽屉、验证卡片或账号确认，不要继续等待答案，直接识别为 blocker。"
            )
        return note

    async def probe_takeover_ready(self, action_type: str) -> bool:
        if action_type == "login":
            return False
        return await super().probe_takeover_ready(action_type)

    async def _expand_collapsed_answer_sections(self) -> None:
        if self.client.page is None:
            return
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
