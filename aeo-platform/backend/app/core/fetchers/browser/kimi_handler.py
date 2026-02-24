"""Kimi browser handler."""

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


class KimiHandler(BaseBrowserHandler):
    """Kimi browser-based handler.

    Uses agent-browser to interact with Kimi Web UI.
    """

    URL = "https://kimi.moonshot.cn/"
    PLATFORM = Platform.KIMI

    # Stable CSS selectors for Kimi Web UI
    INPUT_SELECTOR = ".chat-input-editor"   # contenteditable input area
    NEW_CHAT_SELECTOR = ".new-chat-btn"     # new chat button

    # Content detection: tried in priority order each poll cycle.
    # Multiple fallbacks in case Kimi renames classes across versions.
    CONTENT_SELECTORS = [
        ".message-list .markdown-body",       # original / most specific
        "[class*='message'] .markdown-body",  # partial class match
        ".chat-message [class*='content']",   # alternative structure
        "[class*='markdown-body']",           # last resort: any markdown-body
    ]

    async def fetch(self, question: str) -> AsyncGenerator:
        """Fetch answer from Kimi Web.

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
            # Fast path: if already on kimi.moonshot.cn, click 新建对话 (~1s)
            # instead of full page.goto (~4s+).
            yield self._create_event(
                BrowserState.NAVIGATING,
                f"正在访问 {self.URL}...",
                progress=0.2,
            )
            page = self.client.page
            fast_path_ok = False
            page_url = page.url if page is not None else ""
            on_kimi = "kimi.moonshot.cn" in page_url or "kimi.com" in page_url
            if page is not None and on_kimi:
                try:
                    new_chat = page.locator(self.NEW_CHAT_SELECTOR).first
                    if await new_chat.count() > 0:
                        await new_chat.click()
                        await asyncio.sleep(1.0)
                        fast_path_ok = True
                        logger.info("[Kimi] Fast path: clicked 新建对话")
                    else:
                        # Try text-based fallback
                        btn = page.get_by_text("新建对话", exact=False).first
                        if await btn.count() > 0:
                            await btn.click()
                            await asyncio.sleep(1.0)
                            fast_path_ok = True
                            logger.info("[Kimi] Fast path: clicked 新建对话 (text)")
                except Exception as e:
                    logger.debug("[Kimi] Fast path click failed (%s), falling back to navigate", e)

            if not fast_path_ok:
                await self.client.open(self.URL, headed=False)
                await asyncio.sleep(4)  # SPA takes ~3-4s to render input

            if self.client.page:
                logger.info("[Kimi] Page URL: %s", self.client.page.url)

            # Step 3: Kimi is publicly accessible (no login required).
            yield self._create_event(
                BrowserState.CHECKING_LOGIN,
                "页面加载完成，准备提问...",
                progress=0.3,
            )

            # Step 4: Confirm input is ready.
            yield self._create_event(
                BrowserState.ENABLING_SEARCH,
                "确认输入框可用...",
                progress=0.5,
            )

            # Step 5: Submit question.
            # Primary: direct locator on Kimi's contenteditable input (.chat-input-editor).
            # Fallback 1: snapshot textbox ref.
            # Fallback 2: find_and_fill by placeholder text.
            yield self._create_event(
                BrowserState.SUBMITTING,
                f"提交问题: {question[:30]}...",
                progress=0.6,
            )

            submitted = False
            if self.client.page is not None:
                try:
                    editor = self.client.page.locator(self.INPUT_SELECTOR).first
                    if await editor.count() > 0:
                        await editor.click()
                        await asyncio.sleep(0.2)
                        # For contenteditable, fill() sets the text directly
                        await editor.fill(question)
                        await asyncio.sleep(0.3)
                        await self.client.page.keyboard.press("Enter")
                        submitted = True
                        logger.info("[Kimi] Question submitted via .chat-input-editor locator")
                except Exception as e:
                    logger.debug("[Kimi] Direct locator submit failed: %s", e)

            if not submitted:
                # Fallback: snapshot-based ref
                snapshot = await self.client.snapshot(interactive_only=True)
                textarea_ref = self._find_textarea_ref(snapshot)
                if textarea_ref:
                    await self.client.fill(textarea_ref, question)
                    await asyncio.sleep(0.3)
                    await self.client.press("Enter")
                    submitted = True
                    logger.info("[Kimi] Question submitted via snapshot ref %s", textarea_ref)

            if not submitted:
                # Last resort: find_and_fill by placeholder text
                await self.client.find_and_fill("发送消息", question)
                await self.client.press("Enter")
                logger.info("[Kimi] Question submitted via find_and_fill fallback")

            # Step 6: Wait for response via content-stability detection.
            # max_wait MUST be < (per-question timeout − navigation time).
            # Per-question timeout = 90s; navigation ≈ 8s; so max_wait = 75s.
            yield self._create_event(
                BrowserState.WAITING_RESPONSE,
                "等待 AI 回复...",
                progress=0.7,
            )
            await asyncio.sleep(5)   # Give Kimi time to start generating
            max_wait = 75            # Hard cap well within 90s per-question timeout
            waited = 5
            prev_len = 0
            stable_count = 0

            # Build JS that tries multiple selectors and returns the max content length
            content_check_js = """
                const selectors = [
                    '.message-list .markdown-body',
                    '[class*="message"] .markdown-body',
                    '.chat-message [class*="content"]',
                    '[class*="markdown-body"]',
                ];
                let maxLen = 0;
                for (const sel of selectors) {
                    const nodes = document.querySelectorAll(sel);
                    if (nodes.length > 0) {
                        const last = nodes[nodes.length - 1];
                        maxLen = Math.max(maxLen, (last.textContent || '').length);
                    }
                }
                return String(maxLen);
            """

            while waited < max_wait:
                await asyncio.sleep(3)
                waited += 3
                result = await self.client.eval(content_check_js)
                cur_len = int(result.get("output", "0") or "0")
                # Log every ~15s so we can diagnose issues without spamming
                if waited % 15 == 0 or cur_len != prev_len:
                    logger.info("[Kimi] Wait %ds: content_len=%d (prev=%d)", waited, cur_len, prev_len)
                if cur_len > 0 and cur_len == prev_len:
                    stable_count += 1
                    if stable_count >= 2:
                        logger.info("[Kimi] Content stable at %d chars after %ds", cur_len, waited)
                        break
                else:
                    stable_count = 0
                prev_len = cur_len

            if prev_len == 0:
                logger.warning("[Kimi] No content detected after %ds — dumping page structure for diagnosis", waited)
                try:
                    dump = await self.client.page.evaluate("""() => {
                        // Sample page text
                        const bodyText = (document.body?.innerText || '').slice(0, 300);
                        // All unique class names on the page (to find new selector)
                        const allCls = new Set();
                        document.querySelectorAll('*').forEach(el => {
                            (el.className || '').split(' ').forEach(c => { if (c.trim()) allCls.add(c.trim()); });
                        });
                        const mdLike = [...allCls].filter(c =>
                            c.includes('markdown') || c.includes('message') ||
                            c.includes('chat') || c.includes('answer') ||
                            c.includes('content') || c.includes('reply')
                        ).slice(0, 40);
                        return { bodyText, mdLike };
                    }""")
                    logger.warning("[Kimi] Page text: %s", dump.get("bodyText", "")[:200])
                    logger.warning("[Kimi] Relevant classes: %s", dump.get("mdLike", []))
                except Exception as e:
                    logger.warning("[Kimi] Could not dump page: %s", e)

            # Step 7: Extract answer
            yield self._create_event(
                BrowserState.EXTRACTING,
                "提取回答内容...",
                progress=0.9,
            )
            answer_text = await self._extract_answer()
            search_refs = await self._extract_references()

            fetch_result = FetchResult(
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
                data=fetch_result,
            )

        except Exception as e:
            yield self._create_event(
                BrowserState.ERROR,
                f"抓取失败: {str(e)}",
                progress=0,
                requires_action=False,
            )

    def _find_textarea_ref(self, snapshot: dict) -> str | None:
        """Find textarea/textbox reference from snapshot."""
        try:
            refs = snapshot.get("refs", {})
            for ref_id, info in refs.items():
                if info.get("role") in ("textbox", "textfield", "input"):
                    return f"@{ref_id}"
            return None
        except Exception:
            return None

    async def _extract_answer(self) -> str:
        """Extract the last AI response from the page."""
        try:
            result = await self.client.eval("""
                const selectors = [
                    '.message-list .markdown-body',
                    '[class*="message"] .markdown-body',
                    '.chat-message [class*="content"]',
                    '[class*="markdown-body"]',
                ];
                for (const sel of selectors) {
                    const nodes = document.querySelectorAll(sel);
                    if (nodes.length > 0) {
                        return nodes[nodes.length - 1].textContent || '';
                    }
                }
                return '';
            """)
            text = result.get("output", "")
            if text:
                logger.info("[Kimi] Extracted answer (%d chars)", len(text))
            else:
                logger.warning("[Kimi] Answer extraction returned empty string")
            return text
        except Exception as e:
            logger.debug("[Kimi] _extract_answer failed: %s", e)
            return ""

    async def _extract_references(self) -> list[SearchReference]:
        """Extract search references from page."""
        refs = []

        # Try to expand the reference panel first
        for btn_text in ["来源", "Sources", "References", "引用来源"]:
            try:
                await self.client.find_and_click(btn_text)
                await asyncio.sleep(1.5)
                break
            except Exception:
                continue

        selectors_to_try = [
            ".source-item a",
            "[class*='source'] a[href^='http']",
            "[class*='reference'] a[href^='http']",
            "[data-testid*='source'] a",
            ".message-content a[href^='http']",
        ]

        import json

        for selector in selectors_to_try:
            try:
                result = await self.client.eval(
                    f"""
                    const links = document.querySelectorAll({repr(selector)});
                    return JSON.stringify([...links].map((el, idx) => ({{
                        index: idx + 1,
                        title: (el.textContent || el.title || '').trim().slice(0, 200),
                        url: el.href || '',
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
                        logger.info("[Kimi] Extracted %d references via selector: %s", len(cleaned), selector)
                        refs = cleaned
                        break
            except Exception as e:
                logger.debug("[Kimi] Selector '%s' failed: %s", selector, e)
                continue

        if not refs:
            # Diagnostic: dump all http links to find the right structure
            try:
                diag = await self.client.eval("""
                    const links = Array.from(document.querySelectorAll('a[href^="http"]'));
                    return JSON.stringify(links.slice(0, 10).map(a => ({
                        url: a.href.slice(0, 80),
                        txt: (a.textContent || '').trim().slice(0, 40),
                        cls: (a.className || '').slice(0, 60),
                        pCls: (a.parentElement?.className || '').slice(0, 60),
                    })));
                """)
                link_data = json.loads(diag.get("output", "[]") or "[]")
                logger.warning("[Kimi] No references found. Sample http links (%d): %s",
                               len(link_data), link_data[:5])
            except Exception:
                logger.warning("[Kimi] No references found after trying all selectors")

        return refs
