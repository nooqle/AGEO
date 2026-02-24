"""DeepSeek browser handler."""

import asyncio
import logging
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

from app.core.fetchers.browser.base_handler import BaseBrowserHandler
from app.schemas.fetch import (
    BrowserState,
    FetchMethod,
    FetchResult,
    Platform,
    SearchReference,
)


class DeepSeekHandler(BaseBrowserHandler):
    """DeepSeek browser-based handler.

    Uses agent-browser to interact with DeepSeek Web UI.
    """

    URL = "https://chat.deepseek.com/"
    PLATFORM = Platform.DEEPSEEK

    # Selectors for DeepSeek Web UI
    TEXTAREA_SELECTOR = "textarea"
    ANSWER_SELECTOR = "div.ds-markdown"

    async def fetch(self, question: str) -> AsyncGenerator:
        """Fetch answer from DeepSeek Web.

        Args:
            question: Question to ask

        Yields:
            BrowserEvent objects for progress updates
        """
        try:
            # Step 1: Initializing
            yield self._create_event(
                BrowserState.INITIALIZING,
                "初始化浏览器...",
                progress=0.1,
            )

            # Step 2: Navigate or start new chat.
            # Optimization: if browser is already on chat.deepseek.com, click
            # 新对话 (~1.5s) instead of doing a full page.goto (~3s+).
            yield self._create_event(
                BrowserState.NAVIGATING,
                f"正在访问 {self.URL}...",
                progress=0.2,
            )
            page = self.client.page
            fast_path_ok = False
            if page is not None and "chat.deepseek.com" in (page.url or ""):
                try:
                    # Look for the new-chat button by visible text
                    new_chat = page.get_by_text("新对话", exact=False).first
                    if await new_chat.count() > 0:
                        await new_chat.click()
                        await asyncio.sleep(1.5)
                        fast_path_ok = True
                        logger.info("[DeepSeek] Fast path: clicked 新对话")
                except Exception as e:
                    logger.debug("[DeepSeek] 新对话 click failed (%s), falling back to navigate", e)

            if not fast_path_ok:
                await self.client.open(self.URL, headed=False)
                await asyncio.sleep(3)  # Wait for SPA to render

            if self.client.page:
                logger.info("[DeepSeek] Page URL: %s", self.client.page.url)

            # Step 3: Check login — positive check for the text input being present.
            yield self._create_event(
                BrowserState.CHECKING_LOGIN,
                "检查登录状态...",
                progress=0.3,
            )
            INPUT_READY_SELECTOR = "textarea, [contenteditable='true']"
            input_ready = await self._check_login_status(INPUT_READY_SELECTOR)

            if not input_ready:
                yield self._create_event(
                    BrowserState.WAITING_FOR_LOGIN,
                    "检测到需要登录，请在浏览器窗口中完成登录",
                    progress=0.35,
                    requires_action=True,
                    action_hint="请在弹出的浏览器窗口中完成 DeepSeek 登录",
                )
                await self.client.close()
                await self.client.open(self.URL, headed=True)
                login_success = await self._wait_for_login(INPUT_READY_SELECTOR, timeout=300)
                if not login_success:
                    yield self._create_event(
                        BrowserState.ERROR,
                        "登录超时，请重试",
                        progress=0,
                        requires_action=False,
                    )
                    return

            # Step 4: Ensure web search (联网搜索) is ON.
            # DeepSeek uses pure SVG icon-buttons with no text/aria-label.
            # We locate the input toolbar via the textarea, then inspect
            # aria-pressed / class variants to detect and toggle the state.
            yield self._create_event(
                BrowserState.ENABLING_SEARCH,
                "确认联网搜索已开启...",
                progress=0.5,
            )
            if self.client.page is not None:
                await self._ensure_web_search_on()

            # Step 5: Submit question
            yield self._create_event(
                BrowserState.SUBMITTING,
                f"提交问题: {question[:30]}...",
                progress=0.6,
            )
            snapshot = await self.client.snapshot(interactive_only=True)
            textarea_ref = self._find_textarea_ref(snapshot)
            if textarea_ref:
                await self.client.fill(textarea_ref, question)
                await asyncio.sleep(0.5)
                await self.client.press("Enter")
            else:
                await self.client.find_and_fill("发送消息", question)
                await self.client.press("Enter")

            # Step 6: Wait for response via content-stability detection.
            # Poll div.ds-markdown text length; exit when stable for 2 polls.
            yield self._create_event(
                BrowserState.WAITING_RESPONSE,
                "等待 AI 回复...",
                progress=0.7,
            )
            await asyncio.sleep(4)  # Initial wait for generation to start
            max_wait = 75  # within 90s per-question timeout
            waited = 4
            prev_len = 0
            stable_count = 0
            while waited < max_wait:
                await asyncio.sleep(3)
                waited += 3
                length_result = await self.client.eval(
                    """
                    const msgs = document.querySelectorAll('div.ds-markdown');
                    const last = msgs[msgs.length - 1];
                    return last ? String(last.textContent.length) : '0';
                    """
                )
                cur_len = int(length_result.get("output", "0") or "0")
                if cur_len > 0 and cur_len == prev_len:
                    stable_count += 1
                    if stable_count >= 2:
                        logger.debug("[DeepSeek] Content stable at %d chars", cur_len)
                        break
                else:
                    stable_count = 0
                prev_len = cur_len

            # Step 7: Extract answer
            yield self._create_event(
                BrowserState.EXTRACTING,
                "提取回答内容...",
                progress=0.9,
            )
            answer_text = await self._extract_answer()
            search_refs = await self._extract_references()

            result = FetchResult(
                id=f"{self.PLATFORM.value}_{hash(question)}",
                question_id="",
                question_text=question,
                platform=self.PLATFORM,
                fetch_method=FetchMethod.BROWSER,
                status="success",
                answer_text=answer_text,
                search_references=search_refs,
                raw_response=None,
                error_message=None,
                fetch_duration=None,
            )

            # Step 8: Complete
            yield self._create_event(
                BrowserState.COMPLETED,
                "抓取完成",
                progress=1.0,
                data=result,
            )

        except Exception as e:
            yield self._create_event(
                BrowserState.ERROR,
                f"抓取失败: {str(e)}",
                progress=0,
                requires_action=False,
            )

    async def _ensure_web_search_on(self) -> None:
        """Ensure the web search toggle is ON in the input toolbar.

        DeepSeek renders toolbar toggles as pure SVG icon-buttons with no
        visible text or aria-label.  Strategy:
        1. Find the textarea, walk up the DOM to locate the input toolbar
           (a container with 1-8 interactive elements).
        2. Among those, look for an element with aria-pressed / aria-checked.
        3. If the web-search button (typically index 1: [DeepThink, WebSearch])
           reports pressed=false, click it.
        4. Log everything so we can diagnose DOM changes.
        """
        try:
            info = await self.client.page.evaluate("""() => {
                // Broad query: buttons + anything with aria-pressed/checked/switch
                const INTERACTIVE = 'button, [role="button"], [role="switch"], [aria-pressed], [aria-checked]';

                // --- 1. Find toolbar near textarea ---
                const textarea = document.querySelector('textarea');
                let toolbarEls = null;
                let toolbarContainerCls = '';
                if (textarea) {
                    let c = textarea.parentElement;
                    while (c && c !== document.body) {
                        const els = Array.from(c.querySelectorAll(INTERACTIVE));
                        if (els.length >= 1 && els.length <= 8) {
                            toolbarEls = els;
                            toolbarContainerCls = (c.className || '').slice(0, 80);
                            break;
                        }
                        c = c.parentElement;
                    }
                }

                const descEl = el => ({
                    tag: el.tagName,
                    pressed: el.getAttribute('aria-pressed') || '',
                    checked: el.getAttribute('aria-checked') || '',
                    state:   el.getAttribute('data-state')   || '',
                    label:   el.getAttribute('aria-label')   || '',
                    title:   el.getAttribute('title')        || '',
                    cls:    (el.className || '').slice(0, 80),
                    txt:    (el.innerText || el.textContent || '').trim().slice(0, 40),
                });

                // --- 2. All aria-pressed/checked elements on page ---
                const allToggles = Array.from(
                    document.querySelectorAll('[aria-pressed], [aria-checked], [role="switch"]')
                ).map(descEl);

                return {
                    toolbarBtns: toolbarEls ? toolbarEls.map(descEl) : null,
                    toolbarContainerCls,
                    allToggles,
                };
            }""")

            toolbar = info.get("toolbarBtns") or []
            all_toggles = info.get("allToggles") or []
            logger.info(
                "[DeepSeek] Toolbar buttons (%d): %s | All toggles (%d): %s",
                len(toolbar), toolbar, len(all_toggles), all_toggles,
            )

            # --- Determine which element to click ---
            # Priority 1: any toolbar button that explicitly says pressed=false
            #   (web search is typically the 2nd toggle, after deep-think)
            # Priority 2: fall back to clicking toolbar button at index 1

            clicked = False

            # Check toolbar buttons for a "pressed=false" toggle
            for i, btn in enumerate(toolbar):
                pressed = btn.get("pressed", "")
                if pressed == "false":
                    # This toggle is OFF — click it
                    await self.client.page.evaluate(f"""() => {{
                        const INTERACTIVE = 'button, [role="button"], [role="switch"], [aria-pressed], [aria-checked]';
                        const textarea = document.querySelector('textarea');
                        let c = textarea && textarea.parentElement;
                        while (c && c !== document.body) {{
                            const els = Array.from(c.querySelectorAll(INTERACTIVE));
                            if (els.length >= 1 && els.length <= 8) {{
                                els[{i}] && els[{i}].click();
                                return 'clicked';
                            }}
                            c = c.parentElement;
                        }}
                        return 'not found';
                    }}""")
                    await asyncio.sleep(0.5)
                    logger.info("[DeepSeek] Clicked toolbar[%d] (pressed=false → enabling)", i)
                    clicked = True
                    break
                elif pressed == "true":
                    logger.info("[DeepSeek] Toolbar[%d] already pressed=true, skipping", i)
                    clicked = True  # already on
                    break

            if not clicked and toolbar:
                # No aria-pressed found — use class-based detection.
                # DeepSeek DS system: active toggle = ds-toggle-button--selected,
                # inactive = ds-toggle-button--md (no --selected suffix).
                # Web search is the first button whose cls contains 'toggle-button'
                # (skip plain icon-buttons at the end of the toolbar).
                for i, btn in enumerate(toolbar):
                    cls_i = btn.get("cls", "")
                    if "toggle-button" not in cls_i:
                        continue  # skip non-toggle buttons (file upload, etc.)
                    txt_i = btn.get("txt", "").lower()
                    # Match "Search" or "联网" text; also accept index 1 as fallback
                    # (layout: [DeepThink, Search, ...])
                    if "search" in txt_i or "联网" in txt_i or i == 1:
                        if "--selected" in cls_i:
                            logger.info("[DeepSeek] Web search already ON (toolbar[%d], --selected)", i)
                        else:
                            # OFF — click to enable
                            await self.client.page.evaluate(f"""() => {{
                                const INTERACTIVE = 'button, [role="button"], [role="switch"], [aria-pressed], [aria-checked]';
                                const textarea = document.querySelector('textarea');
                                let c = textarea && textarea.parentElement;
                                while (c && c !== document.body) {{
                                    const els = Array.from(c.querySelectorAll(INTERACTIVE));
                                    if (els.length >= 1 && els.length <= 8) {{
                                        els[{i}] && els[{i}].click();
                                        return 'clicked';
                                    }}
                                    c = c.parentElement;
                                }}
                                return 'not found';
                            }}""")
                            await asyncio.sleep(0.5)
                            logger.info("[DeepSeek] Enabled web search toolbar[%d] (was OFF, cls=%s)", i, cls_i)
                        break

            if not toolbar and not all_toggles:
                logger.warning("[DeepSeek] No toolbar or toggle elements found near textarea")

        except Exception as e:
            logger.debug("[DeepSeek] _ensure_web_search_on failed: %s", e)

    def _find_textarea_ref(self, snapshot: dict) -> str | None:
        """Find textarea reference from snapshot."""
        try:
            refs = snapshot.get("refs", {})
            for ref_id, info in refs.items():
                if info.get("role") == "textbox":
                    return f"@{ref_id}"
            return None
        except Exception:
            return None

    async def _extract_answer(self) -> str:
        """Extract answer text from page."""
        try:
            result = await self.client.eval(
                """
                const messages = document.querySelectorAll('div.ds-markdown');
                const lastMessage = messages[messages.length - 1];
                return lastMessage ? lastMessage.innerText : '';
                """
            )
            return result.get("output", "")
        except Exception:
            return ""

    async def _extract_references(self) -> list[SearchReference]:
        """Extract search references from page.

        Tries multiple selectors with fallback so that UI changes don't cause
        silent failures.
        """
        refs = []

        # Try to expand the reference panel first
        for btn_text in ["引用", "来源", "References", "Sources"]:
            try:
                await self.client.find_and_click(btn_text)
                await asyncio.sleep(2)
                break
            except Exception:
                continue

        selectors_to_try = [
            ".citation-item",
            "[class*='citation']",
            "[class*='reference'] a[href^='http']",
            ".search-result a[href^='http']",
            ".markdown-body a[href^='http']",
            "a[href^='http'][target='_blank']",
        ]

        import json

        for selector in selectors_to_try:
            try:
                result = await self.client.eval(
                    f"""
                    const items = document.querySelectorAll({repr(selector)});
                    return JSON.stringify([...items].map((el, idx) => ({{
                        index: idx + 1,
                        title: (el.textContent || el.title || '').trim().slice(0, 200),
                        url: el.href || el.getAttribute('href') || '',
                    }})));
                    """
                )
                data = json.loads(result.get("output", "[]") or "[]")
                if data:
                    cleaned = []
                    for item in data:
                        url = item.get("url", "")
                        if url and not url.startswith(("javascript:", "#", "/")):
                            cleaned.append(SearchReference(
                                index=len(cleaned) + 1,
                                title=item.get("title", ""),
                                url=url,
                                snippet=None,
                                site_name=None,
                                is_official=False,
                            ))
                    if cleaned:
                        logger.info(
                            "[DeepSeek] Extracted %d references using selector: %s",
                            len(cleaned), selector,
                        )
                        refs = cleaned
                        break
            except Exception as e:
                logger.debug("[DeepSeek] Selector '%s' failed: %s", selector, e)
                continue

        if not refs:
            # Diagnostic: dump all http links on page to find the right selector
            try:
                diag = await self.client.eval("""
                    const links = Array.from(document.querySelectorAll('a[href^="http"]'));
                    return JSON.stringify(links.slice(0, 20).map(a => ({
                        url: a.href.slice(0, 80),
                        txt: (a.textContent || '').trim().slice(0, 40),
                        cls: (a.className || '').slice(0, 60),
                        pCls: (a.parentElement?.className || '').slice(0, 60),
                    })));
                """)
                import json as _json
                link_data = _json.loads(diag.get("output", "[]") or "[]")
                logger.warning("[DeepSeek] No references found. Sample http links (%d): %s",
                               len(link_data), link_data[:5])
            except Exception:
                logger.warning("[DeepSeek] No references found after trying all selectors")

        return refs
