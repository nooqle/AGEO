"""Kimi browser handler."""

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


class KimiHandler(BaseBrowserHandler):
    """Kimi browser-based handler.

    Uses Playwright to interact with Kimi Web UI.
    """

    URL = "https://kimi.com/"
    PLATFORM = Platform.KIMI

    # CSS selectors for Kimi Web UI (with fallbacks for UI updates)
    INPUT_SELECTOR = ".chat-input-editor, [class*='chat-input'], [contenteditable='true']"
    NEW_CHAT_SELECTOR = ".new-chat-btn, [class*='new-chat']"

    # Content detection: tried in priority order each poll cycle.
    # Multiple fallbacks in case Kimi renames classes across versions.
    CONTENT_SELECTORS_JS = json.dumps([
        ".message-list .markdown-body",
        "[class*='message'] .markdown-body",
        ".chat-message [class*='content']",
        "[class*='markdown-body']",
    ])

    # JS wrapped in arrow function to avoid bare-return SyntaxError in page.evaluate
    CONTENT_CHECK_JS = f"""() => {{
        const selectors = {CONTENT_SELECTORS_JS};
        let maxLen = 0;
        for (const sel of selectors) {{
            const nodes = document.querySelectorAll(sel);
            if (nodes.length > 0) {{
                const last = nodes[nodes.length - 1];
                maxLen = Math.max(maxLen, (last.textContent || '').length);
            }}
        }}
        return String(maxLen);
    }}"""

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

            # Step 3: Check login status.
            yield self._create_event(
                BrowserState.CHECKING_LOGIN,
                "检查登录状态...",
                progress=0.3,
            )

            # Detect login modal (Kimi may require login via WeChat/phone)
            login_detected = False
            if self.client.page is not None:
                try:
                    login_check = await self.client.page.evaluate("""() => {
                        const selectors = [
                            '.login-modal-content',
                            '.wechat-login',
                            '[class*="login-modal"]',
                            '[class*="login-dialog"]',
                            '[class*="auth-modal"]',
                        ];
                        for (const sel of selectors) {
                            if (document.querySelector(sel)) return sel;
                        }
                        // Check "not logged in" indicator: sidebar shows "登录" button
                        // when user is not authenticated (input field exists either way)
                        const notLogin = document.querySelector('.not-login-container');
                        if (notLogin && (notLogin.textContent || '').includes('登录')) {
                            return '__need_login__';
                        }
                        // Also check if input is available (no login needed)
                        const input = document.querySelector('.chat-input-editor');
                        if (input) return '__input_ready__';
                        return '__no_input__';
                    }""")
                    result_str = login_check if isinstance(login_check, str) else str(login_check)
                    if result_str == '__input_ready__':
                        logger.info("[Kimi] Input ready, no login required")
                    elif result_str == '__need_login__':
                        login_detected = True
                        logger.info("[Kimi] Not logged in (.not-login-container detected)")
                    elif result_str == '__no_input__':
                        # SPA may still be loading — wait up to 8s more before assuming login needed
                        logger.info("[Kimi] No input found yet, waiting for SPA to finish loading...")
                        for _wait_round in range(4):
                            await asyncio.sleep(2)
                            retry_check = await self.client.page.evaluate("""() => {
                                const input = document.querySelector('.chat-input-editor')
                                    || document.querySelector('[class*="chat-input"]')
                                    || document.querySelector('[contenteditable="true"]');
                                if (input) return '__input_ready__';
                                const loginSels = ['.login-modal-content', '.wechat-login',
                                    '[class*="login-modal"]', '[class*="login-dialog"]'];
                                for (const sel of loginSels) {
                                    if (document.querySelector(sel)) return sel;
                                }
                                return '__no_input__';
                            }""")
                            retry_str = retry_check if isinstance(retry_check, str) else str(retry_check)
                            if retry_str == '__input_ready__':
                                logger.info("[Kimi] Input became ready after extra wait")
                                break
                            if retry_str != '__no_input__':
                                login_detected = True
                                logger.info("[Kimi] Login modal appeared after wait: %s", retry_str)
                                break
                        else:
                            # After all retries still no input and no login modal
                            login_detected = True
                            logger.warning("[Kimi] Input still unavailable after extended wait, assuming login required")
                    else:
                        login_detected = True
                        logger.info("[Kimi] Login modal detected via: %s", result_str)
                except Exception as e:
                    logger.debug("[Kimi] Login detection check failed: %s", e)

            if login_detected:
                INPUT_READY_SELECTOR = ".chat-input-editor, [class*='chat-input']"
                yield self._create_event(
                    BrowserState.WAITING_FOR_LOGIN,
                    "检测到需要登录，请在浏览器窗口中完成登录",
                    progress=0.35,
                    requires_action=True,
                    action_hint="请在弹出的浏览器窗口中完成 Kimi 登录",
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

            # Step 4: Confirm input is ready.
            yield self._create_event(
                BrowserState.ENABLING_SEARCH,
                "确认输入框可用...",
                progress=0.5,
            )

            # Step 5: Submit question.
            # Primary: keyboard.type on contenteditable (.chat-input-editor).
            # Fallback 1: snapshot textbox ref (uses PlaywrightBrowserClient.fill
            #   which has special contenteditable handling via keyboard events).
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
                        # Use keyboard.type() instead of fill() for contenteditable
                        # to ensure React/Vue frameworks detect the input change.
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

            # Step 6: Wait for response via content-stability detection.
            # Budget: 90s external timeout − ~15s navigation/submit − ~10s extraction
            #       = ~65s available. Use max_wait=50 for safety margin.
            yield self._create_event(
                BrowserState.WAITING_RESPONSE,
                "等待 AI 回复...",
                progress=0.7,
            )

            # Wait for any previous content to clear (prevents answer bleed
            # from the previous question when reusing the same browser session).
            await asyncio.sleep(3)
            max_wait = 50
            waited = 3
            prev_len = 0
            stable_count = 0

            # Login check JS — reused during polling to detect late login modals
            _LOGIN_CHECK_JS = """() => {
                const sels = ['.login-modal-content', '.wechat-login',
                              '[class*="login-modal"]', '[class*="login-dialog"]'];
                for (const s of sels) { if (document.querySelector(s)) return true; }
                return false;
            }"""

            while waited < max_wait:
                await asyncio.sleep(3)
                waited += 3
                result = await self.client.eval(self.CONTENT_CHECK_JS)
                if "error" in result:
                    logger.warning("[Kimi] eval error at %ds: %s", waited, result["error"])
                cur_len = int(result.get("output", "0") or "0")
                logger.info("[Kimi] Poll %ds: content_len=%d (prev=%d, stable=%d)",
                            waited, cur_len, prev_len, stable_count)

                # Detect late login modal: if no content after 12s, check for login popup
                if cur_len == 0 and waited >= 12 and self.client.page is not None:
                    try:
                        has_login = await self.client.page.evaluate(_LOGIN_CHECK_JS)
                        if has_login:
                            logger.warning("[Kimi] Late login modal detected at %ds — switching to headed mode", waited)
                            INPUT_READY_SELECTOR = ".chat-input-editor, [class*='chat-input']"
                            yield self._create_event(
                                BrowserState.WAITING_FOR_LOGIN,
                                "检测到需要登录，请在浏览器窗口中完成登录",
                                progress=0.35,
                                requires_action=True,
                                action_hint="请在弹出的浏览器窗口中完成 Kimi 登录",
                            )
                            await self.client.close()
                            await self.client.open(self.URL, headed=True)
                            login_success = await self._wait_for_login(INPUT_READY_SELECTOR, timeout=300)
                            if not login_success:
                                yield self._create_event(
                                    BrowserState.ERROR, "登录超时，请重试",
                                    progress=0, requires_action=False,
                                )
                                return
                            # After login, close headed and reopen headless
                            await self.client.close()
                            await self.client.open(self.URL, headed=False)
                            await asyncio.sleep(4)
                            # Re-submit the question
                            if self.client.page is not None:
                                editor = self.client.page.locator(self.INPUT_SELECTOR).first
                                if await editor.count() > 0:
                                    await editor.click()
                                    await asyncio.sleep(0.2)
                                    await self.client.page.keyboard.press("Control+a")
                                    await self.client.page.keyboard.type(question)
                                    await asyncio.sleep(0.3)
                                    await self.client.page.keyboard.press("Enter")
                                    logger.info("[Kimi] Re-submitted question after login")
                            # Reset polling state
                            waited = 0
                            prev_len = 0
                            stable_count = 0
                            await asyncio.sleep(3)
                            waited += 3
                            continue
                    except Exception as e:
                        logger.debug("[Kimi] Late login check failed: %s", e)

                if cur_len > 0 and cur_len == prev_len:
                    stable_count += 1
                    if stable_count >= 2:
                        logger.info("[Kimi] Content stable at %d chars after %ds", cur_len, waited)
                        break
                else:
                    stable_count = 0
                prev_len = cur_len

            if prev_len == 0:
                logger.warning("[Kimi] No content detected after %ds — dumping page structure", waited)
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
                            c.includes('segment') || c.includes('bubble') ||
                            c.includes('text') || c.includes('response')
                        ).slice(0, 60);
                        return { bodyText, mdLike };
                    }""")
                    logger.warning("[Kimi] Page text: %s", str(dump.get("bodyText", ""))[:300])
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

            # Validate answer before reporting success
            if not answer_text or len(answer_text.strip()) < 10:
                logger.warning("[Kimi] Answer too short or empty (%d chars), reporting error",
                               len(answer_text) if answer_text else 0)
                yield self._create_event(
                    BrowserState.ERROR,
                    "未能提取到有效回答",
                    progress=0,
                    requires_action=False,
                )
                return

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
        """Extract the last AI response from the page.

        Clones the DOM node and strips inline citation markers before
        extracting textContent so that reference numbers do not pollute
        the answer text.
        """
        try:
            result = await self.client.eval(f"""() => {{
                const selectors = {self.CONTENT_SELECTORS_JS};
                for (const sel of selectors) {{
                    const nodes = document.querySelectorAll(sel);
                    if (nodes.length > 0) {{
                        const clone = nodes[nodes.length - 1].cloneNode(true);
                        // Remove inline citation markers
                        clone.querySelectorAll(
                            '[class*="cite"], [class*="citation"], [class*="ref-num"], ' +
                            'sup, a[data-index]'
                        ).forEach(el => el.remove());
                        return clone.textContent || '';
                    }}
                }}
                return '';
            }}""")
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
        """Extract search references from page.

        Strategy: try CSS selectors directly first, then attempt to expand
        reference panel only if needed (avoids clicking wrong elements).
        """
        refs = []

        selectors_to_try = [
            ".source-item a",
            "[class*='source'] a[href^='http']",
            "[class*='reference'] a[href^='http']",
            "[data-testid*='source'] a",
            ".message-content a[href^='http']",
        ]

        # Phase 1: Try selectors without clicking anything first
        for selector in selectors_to_try:
            refs = await self._try_ref_selector(selector)
            if refs:
                logger.info("[Kimi] Extracted %d references via selector: %s", len(refs), selector)
                return refs

        # Phase 2: Try to expand the reference panel, then re-check
        for btn_text in ["来源", "Sources", "References", "引用来源"]:
            try:
                result = await self.client.find_and_click(btn_text)
                if result.get("success"):
                    await asyncio.sleep(1.5)
                    break
            except Exception:
                continue

        for selector in selectors_to_try:
            refs = await self._try_ref_selector(selector)
            if refs:
                logger.info("[Kimi] Extracted %d references (after expand) via: %s", len(refs), selector)
                return refs

        # Diagnostic: dump sample http links
        try:
            diag = await self.client.eval("""() => {
                const links = Array.from(document.querySelectorAll('a[href^="http"]'));
                return JSON.stringify(links.slice(0, 10).map(a => ({
                    url: a.href.slice(0, 80),
                    txt: (a.textContent || '').trim().slice(0, 40),
                    cls: (a.className || '').slice(0, 60),
                    pCls: (a.parentElement?.className || '').slice(0, 60),
                })));
            }""")
            link_data = json.loads(diag.get("output", "[]") or "[]")
            logger.warning("[Kimi] No references found. Sample http links (%d): %s",
                           len(link_data), link_data[:5])
        except Exception:
            logger.warning("[Kimi] No references found after trying all selectors")

        return refs

    async def _try_ref_selector(self, selector: str) -> list[SearchReference]:
        """Try a single CSS selector to extract references.

        If the extracted title looks like a bare number or dash-number,
        falls back to using the URL domain as the title.
        """
        try:
            js_selector = json.dumps(selector)
            result = await self.client.eval(
                f"""() => {{
                    const links = document.querySelectorAll({js_selector});
                    return JSON.stringify([...links].map((el, idx) => ({{
                        index: idx + 1,
                        title: (el.getAttribute('title') || el.textContent || '').trim().slice(0, 200),
                        url: el.href || '',
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
            logger.debug("[Kimi] Selector '%s' failed: %s", selector, e)
            return []
