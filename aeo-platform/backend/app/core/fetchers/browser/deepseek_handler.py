"""DeepSeek browser handler."""

import asyncio
import json
import logging
import re
from typing import AsyncGenerator

logger = logging.getLogger(__name__)


def _is_junk_title(title: str) -> bool:
    """Return True if the title is just numbers, dashes, or punctuation."""
    return bool(re.fullmatch(r'[-\d\s.\[\]()]+', title))

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

    Uses Playwright to interact with DeepSeek Web UI.
    """

    URL = "https://chat.deepseek.com/"
    PLATFORM = Platform.DEEPSEEK

    # Selectors for DeepSeek Web UI
    TEXTAREA_SELECTOR = "textarea"
    ANSWER_SELECTOR = "div.ds-markdown"

    # JS wrapped in arrow function to avoid bare-return SyntaxError
    CONTENT_CHECK_JS = """() => {
        const msgs = document.querySelectorAll('div.ds-markdown');
        const last = msgs[msgs.length - 1];
        return last ? String(last.textContent.length) : '0';
    }"""

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
            yield self._create_event(
                BrowserState.NAVIGATING,
                f"正在访问 {self.URL}...",
                progress=0.2,
            )
            page = self.client.page
            fast_path_ok = False
            if page is not None and "chat.deepseek.com" in (page.url or ""):
                try:
                    new_chat = page.get_by_text("新对话", exact=False).first
                    if await new_chat.count() > 0:
                        await new_chat.click()
                        await asyncio.sleep(1.5)
                        fast_path_ok = True
                        logger.info("[DeepSeek] Fast path: clicked 新对话")
                except Exception as e:
                    logger.debug("[DeepSeek] 新对话 click failed (%s), falling back to navigate", e)

            if not fast_path_ok:
                open_result = await self.client.open(self.URL, headed=False)
                if not open_result.get("success"):
                    yield self._create_event(
                        BrowserState.ERROR,
                        f"浏览器打开失败: {open_result.get('error', '未知错误')}",
                        progress=0,
                        requires_action=False,
                    )
                    return
                await asyncio.sleep(3)  # Wait for SPA to render

            if self.client.page:
                logger.info("[DeepSeek] Page URL: %s", self.client.page.url)

            # Step 3: Check login
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
                open_headed = await self.client.open(self.URL, headed=True)
                if not open_headed.get("success"):
                    yield self._create_event(
                        BrowserState.ERROR,
                        f"无法打开登录浏览器: {open_headed.get('error', '未知错误')}",
                        progress=0,
                        requires_action=False,
                    )
                    return
                login_success = await self._wait_for_login(INPUT_READY_SELECTOR, timeout=120)
                if not login_success:
                    yield self._create_event(
                        BrowserState.ERROR,
                        "登录超时，请重试",
                        progress=0,
                        requires_action=False,
                    )
                    return

            # Step 4: Ensure web search (联网搜索) is ON.
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
            submitted = False
            snapshot = await self.client.snapshot(interactive_only=True)
            textarea_ref = self._find_textarea_ref(snapshot)
            if textarea_ref:
                await self.client.fill(textarea_ref, question)
                await asyncio.sleep(0.5)
                await self.client.press("Enter")
                submitted = True
                logger.info("[DeepSeek] Question submitted via snapshot ref %s", textarea_ref)
            else:
                await self.client.find_and_fill("发送消息", question)
                await self.client.press("Enter")
                submitted = True
                logger.info("[DeepSeek] Question submitted via find_and_fill fallback")

            # Step 6: Wait for response via content-stability detection.
            # Budget: 90s external timeout − ~15s navigation/submit − ~10s extraction
            #       = ~65s available. Use max_wait=50 for safety margin.
            yield self._create_event(
                BrowserState.WAITING_RESPONSE,
                "等待 AI 回复...",
                progress=0.7,
            )
            await asyncio.sleep(3)
            max_wait = 50
            waited = 3
            prev_len = 0
            stable_count = 0

            while waited < max_wait:
                await asyncio.sleep(3)
                waited += 3
                length_result = await self.client.eval(self.CONTENT_CHECK_JS)
                if "error" in length_result:
                    logger.warning("[DeepSeek] eval error at %ds: %s", waited, length_result["error"])
                cur_len = int(length_result.get("output", "0") or "0")
                logger.info("[DeepSeek] Poll %ds: content_len=%d (prev=%d, stable=%d)",
                            waited, cur_len, prev_len, stable_count)
                if cur_len > 0 and cur_len == prev_len:
                    stable_count += 1
                    if stable_count >= 2:
                        logger.info("[DeepSeek] Content stable at %d chars after %ds", cur_len, waited)
                        break
                else:
                    stable_count = 0
                prev_len = cur_len

            if prev_len == 0:
                logger.warning("[DeepSeek] No content detected after %ds — dumping page structure", waited)
                try:
                    dump = await self.client.page.evaluate("""() => {
                        const bodyText = (document.body?.innerText || '').slice(0, 500);
                        const allCls = new Set();
                        document.querySelectorAll('*').forEach(el => {
                            const cn = typeof el.className === 'string' ? el.className : (el.className?.baseVal || '');
                            cn.split(' ').forEach(c => { if (c.trim()) allCls.add(c.trim()); });
                        });
                        const mdLike = [...allCls].filter(c =>
                            c.includes('markdown') || c.includes('message') ||
                            c.includes('chat') || c.includes('answer') ||
                            c.includes('content') || c.includes('reply') ||
                            c.includes('ds-')
                        ).slice(0, 40);
                        return { bodyText, mdLike };
                    }""")
                    logger.warning("[DeepSeek] Page text: %s", str(dump.get("bodyText", ""))[:300])
                    logger.warning("[DeepSeek] Relevant classes: %s", dump.get("mdLike", []))
                except Exception as e:
                    logger.warning("[DeepSeek] Could not dump page: %s", e)

            # Step 7: Extract answer
            yield self._create_event(
                BrowserState.EXTRACTING,
                "提取回答内容...",
                progress=0.9,
            )
            answer_text = await self._extract_answer()

            # Validate answer before reporting success
            if not answer_text or len(answer_text.strip()) < 10:
                logger.warning("[DeepSeek] Answer too short or empty (%d chars), reporting error",
                               len(answer_text) if answer_text else 0)
                yield self._create_event(
                    BrowserState.ERROR,
                    "未能提取到有效回答",
                    progress=0,
                    requires_action=False,
                )
                return

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
        1. Find the textarea, walk up the DOM to locate the input toolbar.
        2. Among toolbar buttons, find the WebSearch toggle specifically
           (by text or index), not just the first pressed=false button.
        3. If it's off, click to enable.
        """
        try:
            info = await self.client.page.evaluate("""() => {
                const INTERACTIVE = 'button, [role="button"], [role="switch"], [aria-pressed], [aria-checked]';
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

            if not toolbar:
                if not all_toggles:
                    logger.warning("[DeepSeek] No toolbar or toggle elements found near textarea")
                # Fallback: try direct text-based click via Playwright
                await self._try_text_based_search_toggle()
                return

            # Find the WebSearch toggle specifically.
            # Layout is typically [DeepThink, Search, upload_icon, ...].
            # We identify Search by: text contains "search"/"联网", or it's a
            # toggle-button at index 1 (when DeepThink is at index 0).
            search_idx = self._find_web_search_index(toolbar)
            if search_idx is None:
                logger.warning("[DeepSeek] Could not identify WebSearch toggle in toolbar, trying text fallback")
                await self._try_text_based_search_toggle()
                return

            btn = toolbar[search_idx]
            pressed = btn.get("pressed", "")
            cls = btn.get("cls", "")

            # Check state via aria-pressed first, then class-based fallback
            if pressed == "true":
                logger.info("[DeepSeek] Web search already ON (toolbar[%d], pressed=true)", search_idx)
                return
            if pressed == "false":
                await self._click_toolbar_button(search_idx)
                logger.info("[DeepSeek] Enabled web search toolbar[%d] (pressed false→true)", search_idx)
                return

            # No aria-pressed: use class-based detection
            if "--selected" in cls:
                logger.info("[DeepSeek] Web search already ON (toolbar[%d], --selected)", search_idx)
            else:
                await self._click_toolbar_button(search_idx)
                logger.info("[DeepSeek] Enabled web search toolbar[%d] (was OFF, cls=%s)", search_idx, cls[:60])

        except Exception as e:
            logger.warning("[DeepSeek] _ensure_web_search_on failed: %s", e)

    def _find_web_search_index(self, toolbar: list[dict]) -> int | None:
        """Find the index of the WebSearch toggle button in the toolbar."""
        # Pass 1: Look for any button with Search/联网 text (text match is most reliable)
        for i, btn in enumerate(toolbar):
            txt = btn.get("txt", "").lower()
            if "search" in txt or "联网" in txt:
                return i

        # Pass 2: Look for toggle-button class (may have changed to toggle, switch, etc.)
        toggle_keywords = ("toggle", "switch", "ds-toggle")
        toggle_indices = []
        for i, btn in enumerate(toolbar):
            cls = btn.get("cls", "").lower()
            if any(kw in cls for kw in toggle_keywords):
                toggle_indices.append(i)

        # If 2+ toggle buttons found, second is typically Search (first is DeepThink)
        if len(toggle_indices) >= 2:
            return toggle_indices[1]

        # Pass 3: Look for aria-pressed or role="switch" buttons
        for i, btn in enumerate(toolbar):
            if btn.get("pressed") in ("true", "false"):
                txt = btn.get("txt", "").lower()
                # Skip DeepThink
                if "think" in txt or "深度" in txt or "思考" in txt:
                    continue
                return i

        if toggle_indices:
            # Only one toggle found — could be Search if DeepThink is hidden
            return toggle_indices[0]

        logger.warning("[DeepSeek] _find_web_search_index: no toggle found in toolbar with %d items", len(toolbar))
        return None

    async def _click_toolbar_button(self, index: int) -> None:
        """Click a toolbar button by index (re-locating from textarea)."""
        await self.client.page.evaluate(f"""() => {{
            const INTERACTIVE = 'button, [role="button"], [role="switch"], [aria-pressed], [aria-checked]';
            const textarea = document.querySelector('textarea');
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
        """Fallback: try to enable web search by clicking element containing '联网' text."""
        if not self.client.page:
            return
        try:
            # Try Playwright's text locator — more resilient to DOM changes
            locator = self.client.page.get_by_text("联网搜索", exact=False).first
            if await locator.count() > 0:
                await locator.click()
                await asyncio.sleep(0.5)
                logger.info("[DeepSeek] Enabled web search via text-based fallback ('联网搜索')")
                return
            # Try shorter text
            locator2 = self.client.page.get_by_text("联网", exact=False).first
            if await locator2.count() > 0:
                await locator2.click()
                await asyncio.sleep(0.5)
                logger.info("[DeepSeek] Enabled web search via text-based fallback ('联网')")
                return
            logger.warning("[DeepSeek] Text-based search toggle fallback: no matching element found")
        except Exception as e:
            logger.warning("[DeepSeek] Text-based search toggle fallback failed: %s", e)

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
        """Extract answer text from page.

        Clones the DOM node and strips inline citation markers before
        extracting innerText so that superscript reference numbers
        (e.g. [4], [7]) do not pollute the answer text.
        """
        try:
            result = await self.client.eval("""() => {
                const messages = document.querySelectorAll('div.ds-markdown');
                const lastMessage = messages[messages.length - 1];
                if (!lastMessage) return '';
                const clone = lastMessage.cloneNode(true);
                // Remove inline citation markers (superscript numbers / cite links)
                clone.querySelectorAll(
                    '[class*="cite"], [class*="citation"], [class*="ref-num"], ' +
                    'sup, a.ds-markdown-cite, a[data-index]'
                ).forEach(el => el.remove());
                return clone.innerText;
            }""")
            text = result.get("output", "")
            if text:
                logger.info("[DeepSeek] Extracted answer (%d chars)", len(text))
            else:
                logger.warning("[DeepSeek] Answer extraction returned empty string")
            return text
        except Exception:
            return ""

    async def _extract_references(self) -> list[SearchReference]:
        """Extract search references from page.

        Strategy:
        1. Use a dedicated JS snippet that extracts citation links from
           the last answer, reading the title attribute or parent tooltip
           to get meaningful titles (not just the superscript number).
        2. Fallback to generic selectors if step 1 yields nothing.
        3. Attempt to expand the reference panel and re-check.
        """
        # Phase 1: Extract citation links with smart title resolution
        refs = await self._extract_citation_links()
        if refs:
            logger.info("[DeepSeek] Extracted %d references via citation links", len(refs))
            return refs

        # Phase 2: Generic selectors (reference panel elements)
        panel_selectors = [
            "[class*='reference'] a[href^='http']",
            ".search-result a[href^='http']",
        ]
        for selector in panel_selectors:
            refs = await self._try_ref_selector(selector)
            if refs:
                logger.info("[DeepSeek] Extracted %d references via selector: %s", len(refs), selector)
                return refs

        # Phase 3: Try to expand the reference panel, then re-check
        for btn_text in ["引用", "来源", "References", "Sources"]:
            try:
                result = await self.client.find_and_click(btn_text)
                if result.get("success"):
                    await asyncio.sleep(2)
                    break
            except Exception:
                continue

        for selector in panel_selectors:
            refs = await self._try_ref_selector(selector)
            if refs:
                logger.info("[DeepSeek] Extracted %d references (after expand) via: %s", len(refs), selector)
                return refs

        # Diagnostic: dump sample http links
        try:
            diag = await self.client.eval("""() => {
                const links = Array.from(document.querySelectorAll('a[href^="http"]'));
                return JSON.stringify(links.slice(0, 20).map(a => ({
                    url: a.href.slice(0, 80),
                    txt: (a.textContent || '').trim().slice(0, 40),
                    cls: (a.className || '').slice(0, 60),
                    pCls: (a.parentElement?.className || '').slice(0, 60),
                })));
            }""")
            link_data = json.loads(diag.get("output", "[]") or "[]")
            logger.warning("[DeepSeek] No references found. Sample http links (%d): %s",
                           len(link_data), link_data[:5])
        except Exception:
            logger.warning("[DeepSeek] No references found after trying all selectors")

        return refs

    async def _extract_citation_links(self) -> list[SearchReference]:
        """Extract citation links from the last answer with smart title resolution.

        DeepSeek renders inline citation markers as <a> tags whose textContent
        is just a number (e.g. "4").  This method extracts the href (real URL)
        and attempts to read a meaningful title from the element's title
        attribute, aria-label, or a nearby tooltip / parent container.
        If no title is available, falls back to the URL domain.
        """
        try:
            result = await self.client.eval("""() => {
                const messages = document.querySelectorAll('div.ds-markdown');
                const lastMsg = messages[messages.length - 1];
                if (!lastMsg) return '[]';

                // Collect all <a> tags with external http links inside the answer
                const links = Array.from(lastMsg.querySelectorAll('a[href^="http"]'));
                const seen = new Set();
                const refs = [];

                for (const a of links) {
                    const url = a.href;
                    if (!url || seen.has(url)) continue;
                    seen.add(url);

                    // Try to get a meaningful title from multiple sources
                    let title = (a.getAttribute('title') || '').trim();
                    if (!title) title = (a.getAttribute('aria-label') || '').trim();
                    if (!title) {
                        // Check data attributes
                        title = (a.getAttribute('data-title') || '').trim();
                    }
                    if (!title) {
                        // Look at parent tooltip or wrapper text (skip if it's just a number)
                        const parent = a.closest('[class*="tooltip"], [class*="popup"], [class*="citation-content"]');
                        if (parent) {
                            const pText = (parent.textContent || '').trim();
                            if (pText.length > 5) title = pText.slice(0, 200);
                        }
                    }
                    if (!title || /^[-\\d\\s.]+$/.test(title)) {
                        // Title is empty or just numbers/dashes — use URL domain
                        try {
                            title = new URL(url).hostname.replace(/^www\\./, '');
                        } catch {
                            title = url.slice(0, 60);
                        }
                    }

                    refs.push({ index: refs.length + 1, title, url });
                }
                return JSON.stringify(refs);
            }""")
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

    async def _try_ref_selector(self, selector: str) -> list[SearchReference]:
        """Try a single CSS selector to extract references.

        If the extracted title looks like a bare number or dash-number,
        falls back to using the URL domain as the title.
        """
        try:
            js_selector = json.dumps(selector)
            result = await self.client.eval(
                f"""() => {{
                    const items = document.querySelectorAll({js_selector});
                    return JSON.stringify([...items].map((el, idx) => ({{
                        index: idx + 1,
                        title: (el.getAttribute('title') || el.textContent || '').trim().slice(0, 200),
                        url: el.href || el.getAttribute('href') || '',
                    }})));
                }}"""
            )
            data = json.loads(result.get("output", "[]") or "[]")
            if not data:
                return []
            cleaned = []
            for item in data:
                url = item.get("url", "")
                if url and not url.startswith(("javascript:", "#", "/")):
                    title = item.get("title", "")
                    # If title is empty or just numbers/dashes, use URL domain
                    if not title or _is_junk_title(title):
                        try:
                            from urllib.parse import urlparse
                            title = urlparse(url).hostname or url[:60]
                            title = title.removeprefix("www.")
                        except Exception:
                            title = url[:60]
                    cleaned.append(SearchReference(
                        index=len(cleaned) + 1,
                        title=title,
                        url=url,
                        snippet=None,
                        site_name=None,
                        is_official=False,
                    ))
            return cleaned
        except Exception as e:
            logger.debug("[DeepSeek] Selector '%s' failed: %s", selector, e)
            return []
