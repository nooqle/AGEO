"""DeepSeek browser handler.

NOTE: All eval() calls in this module are Playwright's page.evaluate() API,
which executes JavaScript in the browser context for DOM interaction.
This is the standard Playwright pattern, not Python's built-in eval().
"""

import asyncio
import json
import logging
from typing import AsyncGenerator

from app.core.fetchers.browser.base_handler import BaseBrowserHandler
from app.core.fetchers.browser.parsers.base import BaseResponseParser
from app.core.fetchers.browser.parsers.sse import DeepSeekSSEParser
from app.schemas.fetch import (
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

    _DEFAULTS: dict = {
        "input": "textarea",
        "input_ready": "textarea, [contenteditable='true']",
        "answer": "div.ds-markdown",
        "reference_links": [
            "[class*='reference'] a[href^='http']",
            ".search-result a[href^='http']",
        ],
        "citation_strip": "[class*='cite'], [class*='citation'], [class*='ref-num'], sup, a.ds-markdown-cite, a[data-index]",
        "new_chat_text": "新对话",
        "web_search_texts": ["联网搜索", "联网"],
        "reference_expand_texts": ["引用", "来源", "References", "Sources"],
    }

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
            snapshot = await self.client.snapshot(interactive_only=True)
            textarea_ref = self._find_textarea_ref(snapshot)
            if textarea_ref:
                await self.client.fill(textarea_ref, question)
                await asyncio.sleep(0.5)
                await self.client.press("Enter")
                logger.info("[DeepSeek] Question submitted via snapshot ref %s", textarea_ref)
            else:
                await self.client.find_and_fill("发送消息", question)
                await self.client.press("Enter")
                logger.info("[DeepSeek] Question submitted via find_and_fill fallback")

            # Step 6: Wait for response (try network interception first, fallback to DOM)
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
                    logger.info("[DeepSeek] Using network-intercepted data (%d chars, %d refs)",
                                len(answer_text), len(search_refs))
                elif parsed and parsed.error_type:
                    logger.warning("[DeepSeek] SSE error: %s (type=%s)", parsed.error, parsed.error_type)
                    events, handled = await self._handle_browser_agent_parser_error(
                        parsed_error=parsed.error,
                        error_type=parsed.error_type,
                        progress=0.68,
                        fallback_url=self.URL,
                    )
                    for event in events:
                        yield event
                    if handled:
                        return
                    return

            # DOM fallback
            if not answer_text:
                logger.info("[DeepSeek] Falling back to DOM extraction")
                prev_len, waited, blocker_decision = await self._wait_for_content_with_browser_agent(
                    max_wait=50, poll_interval=3, min_content_len=0,
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
                    await self._dump_page_debug(waited, extra_keywords=['ds-'])

                yield self._create_event(BrowserState.EXTRACTING, "提取回答内容...", progress=0.9)
                answer_text = await self._extract_answer_dom()
                search_refs = await self._extract_references()

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
            result = await self._build_success_result(
                question=question,
                answer_text=answer_text,
                search_references=search_refs,
                source=source,
            )

            yield self._create_event(BrowserState.COMPLETED, "抓取完成", progress=1.0, data=result)

        except Exception as e:
            yield self._create_event(BrowserState.ERROR, f"抓取失败: {str(e)}", progress=0)

    # ------------------------------------------------------------------ DeepSeek-specific

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
        """Extract search references with DeepSeek-specific citation link extraction."""
        # Phase 1: DeepSeek-specific citation links
        refs = await self._extract_citation_links()
        if refs:
            logger.info("[DeepSeek] Extracted %d references via citation links", len(refs))
            return refs

        # Phase 2+3: Generic extraction from base
        return await self._extract_references_dom()

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
