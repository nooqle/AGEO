"""Base browser handler for LLM platforms.

Provides Template Method pattern with shared logic extracted from
DeepSeek/Kimi/Yuanbao/Doubao handlers (Phase 0 refactor).

NOTE: The eval() calls in this module are Playwright's page.evaluate() which
executes JavaScript in the browser context for DOM scraping. This is the
standard Playwright API pattern - not Python's eval().
"""

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Awaitable, Callable, Union
from urllib.parse import urlparse

# CP1252 byte-to-Unicode mappings for the 0x80-0x9F range (where CP1252 differs
# from ISO-8859-1).  Used by _undo_double_utf8() to reverse double encoding.
_CP1252_EXTRA: dict[int, int] = {
    0x20AC: 0x80, 0x201A: 0x82, 0x0192: 0x83, 0x201E: 0x84,
    0x2026: 0x85, 0x2020: 0x86, 0x2021: 0x87, 0x02C6: 0x88,
    0x2030: 0x89, 0x0160: 0x8A, 0x2039: 0x8B, 0x0152: 0x8C,
    0x017D: 0x8E, 0x2018: 0x91, 0x2019: 0x92, 0x201C: 0x93,
    0x201D: 0x94, 0x2022: 0x95, 0x2013: 0x96, 0x2014: 0x97,
    0x02DC: 0x98, 0x2122: 0x99, 0x0161: 0x9A, 0x203A: 0x9B,
    0x0153: 0x9C, 0x017E: 0x9E, 0x0178: 0x9F,
}


def _undo_double_utf8(text: str) -> str:
    """Reverse double UTF-8 encoding (UTF-8 bytes → CP1252 chars → UTF-8).

    Some servers (e.g. Doubao) double-encode: original UTF-8 bytes are
    misinterpreted as CP1252 codepoints, then re-encoded as UTF-8.
    This function reverses that by mapping each char back to its byte value,
    then decoding the resulting bytes as UTF-8.
    """
    out = bytearray()
    for ch in text:
        cp = ord(ch)
        if cp < 0x100:
            out.append(cp)
        elif cp in _CP1252_EXTRA:
            out.append(_CP1252_EXTRA[cp])
        else:
            out.extend(ch.encode("utf-8"))
    return bytes(out).decode("utf-8", errors="replace")


from app.core.fetchers.browser.agent_browser import AgentBrowserClient
from app.core.fetchers.browser.parsers.base import (
    BaseResponseParser,
    InterceptConfig,
    ParsedResponse,
)
from app.core.fetchers.browser.playwright_client import PlaywrightBrowserClient
from app.schemas.fetch import (
    BrowserEvent,
    BrowserState,
    FetchResult,
    Platform,
    SearchReference,
)
from app.workflow.browser_action_runtime import (
    clear_browser_action_request,
    register_browser_action_request,
    wait_for_browser_action_resolution,
)

logger = logging.getLogger(__name__)

ReadyCheck = Callable[[int], Awaitable[bool]]


def _is_junk_title(title: str) -> bool:
    """Return True if the title is just numbers, dashes, or punctuation."""
    return bool(re.fullmatch(r'[-\d\s.\[\]()]+', title))


class BaseBrowserHandler(ABC):
    """Base class for browser-based LLM handlers.

    All browser handlers should inherit from this class and implement
    the fetch method.

    Supports both AgentBrowserClient (CLI-based) and PlaywrightBrowserClient (native).

    Subclasses MUST define:
        URL: str          — platform URL
        PLATFORM: Platform — enum value
        PLATFORM_KEY: str  — key in selectors.yaml
        _DEFAULTS: dict    — fallback selectors
    """

    URL: str = ""
    PLATFORM: Platform  # subclass must define
    PLATFORM_KEY: str = ""  # key in selectors.yaml
    _DEFAULTS: dict = {}
    DOUBLE_UTF8_FIX: bool = False  # Doubao needs double UTF-8 decoding

    def __init__(
        self,
        client: Union[AgentBrowserClient, PlaywrightBrowserClient],
        headed: bool = False,
        session_id: str | None = None,
    ):
        self.client = client
        self.headed = headed
        self.session_id = session_id
        self._is_playwright = isinstance(client, PlaywrightBrowserClient)
        self._sel_cache: dict = {}

    # ------------------------------------------------------------------ selectors

    def _sel(self, key: str):
        """Get selector from YAML config with fallback to _DEFAULTS."""
        return self._sel_cache.get(key, self._DEFAULTS.get(key))

    def _refresh_selectors(self):
        """Reload selectors from YAML (called at the start of each fetch)."""
        from app.core.fetchers.browser.selector_config import get_platform_config
        self._sel_cache = get_platform_config(self.PLATFORM_KEY)

    # ------------------------------------------------------------------ JS builders

    def _content_check_js(self) -> str:
        """Build content length check JS from current selectors.

        Handles both single-selector (DeepSeek) and multi-selector (others) formats.
        """
        content_sel = self._sel("content") or self._sel("answer")
        if isinstance(content_sel, list):
            sels = json.dumps(content_sel, ensure_ascii=False)
            return f"""() => {{
            const selectors = {sels};
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
        else:
            answer_sel = json.dumps(content_sel, ensure_ascii=False)
            return f"""() => {{
            const msgs = document.querySelectorAll({answer_sel});
            const last = msgs[msgs.length - 1];
            return last ? String(last.textContent.length) : '0';
        }}"""

    def _dismiss_popups_js(self) -> str:
        """Build popup dismissal JS from current selectors.

        Override in subclasses that need popup dismissal (Kimi, Yuanbao).
        Returns no-op JS by default.
        """
        return "() => 0"

    # ------------------------------------------------------------------ DOM extraction

    async def _extract_answer_dom(self) -> str:
        """Extract answer text from DOM.

        Handles both single-selector (DeepSeek) and multi-selector (others) formats.
        Clones DOM node and strips citation markers before extracting text.

        Uses Playwright's page.evaluate() to run JS in the browser context.
        """
        tag = self.PLATFORM_KEY.capitalize()
        try:
            content_sel = self._sel("content") or self._sel("answer")
            cite_strip_sel = json.dumps(
                self._sel("citation_strip") or "", ensure_ascii=False
            )

            if isinstance(content_sel, list):
                sels = json.dumps(content_sel, ensure_ascii=False)
                # Multi-selector: try each in priority order
                result = await self.client.eval(f"""() => {{
                    const selectors = {sels};
                    for (const sel of selectors) {{
                        const nodes = document.querySelectorAll(sel);
                        if (nodes.length > 0) {{
                            const clone = nodes[nodes.length - 1].cloneNode(true);
                            clone.querySelectorAll({cite_strip_sel}).forEach(el => el.remove());
                            return clone.textContent || '';
                        }}
                    }}
                    return '';
                }}""")
            else:
                sel = json.dumps(content_sel, ensure_ascii=False)
                # Single selector (e.g. DeepSeek's "div.ds-markdown")
                result = await self.client.eval(f"""() => {{
                    const messages = document.querySelectorAll({sel});
                    const lastMessage = messages[messages.length - 1];
                    if (!lastMessage) return '';
                    const clone = lastMessage.cloneNode(true);
                    clone.querySelectorAll({cite_strip_sel}).forEach(el => el.remove());
                    return clone.innerText;
                }}""")

            text = result.get("output", "")
            if text:
                logger.info("[%s] Extracted answer (%d chars)", tag, len(text))
            else:
                logger.warning("[%s] Answer extraction returned empty string", tag)
            return text
        except Exception as e:
            logger.debug("[%s] _extract_answer_dom failed: %s", tag, e)
            return ""

    async def _try_ref_selector(self, selector: str) -> list[SearchReference]:
        """Try a single CSS selector to extract references.

        If the extracted title looks like a bare number or dash-number,
        falls back to using the URL domain as the title.

        Uses Playwright's page.evaluate() to run JS in the browser context.
        """
        tag = self.PLATFORM_KEY.capitalize()
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
                    if not title or _is_junk_title(title):
                        try:
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
            logger.debug("[%s] Selector '%s' failed: %s", tag, selector, e)
            return []

    async def _extract_references_dom(self) -> list[SearchReference]:
        """Extract search references from page using 3-phase strategy.

        Phase 1: Try CSS selectors directly
        Phase 2: Expand reference panel, re-try selectors
        Phase 3: Diagnostic logging
        """
        tag = self.PLATFORM_KEY.capitalize()
        refs: list[SearchReference] = []
        selectors_to_try = self._sel("reference_links") or []

        # Phase 1: Try selectors without clicking anything
        for selector in selectors_to_try:
            refs = await self._try_ref_selector(selector)
            if refs:
                logger.info("[%s] Extracted %d references via selector: %s", tag, len(refs), selector)
                return refs

        # Phase 2: Try to expand the reference panel, then re-check
        expand_texts = self._sel("reference_expand_texts") or []
        for btn_text in expand_texts:
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
                logger.info("[%s] Extracted %d references (after expand) via: %s", tag, len(refs), selector)
                return refs

        # Phase 3: Diagnostic
        try:
            diag = await self.client.eval("""() => {
                const links = Array.from(document.querySelectorAll('a[href^="http"]'));
                return JSON.stringify(links.slice(0, 10).map(a => ({
                    url: a.href.slice(0, 80),
                    txt: (a.textContent || '').trim().slice(0, 40),
                    cls: (a.className || '').slice(0, 60),
                })));
            }""")
            link_data = json.loads(diag.get("output", "[]") or "[]")
            logger.warning("[%s] No references found. Sample http links (%d): %s",
                           tag, len(link_data), link_data[:5])
        except Exception:
            logger.warning("[%s] No references found after trying all selectors", tag)

        return refs

    # ------------------------------------------------------------------ polling helpers

    async def _wait_for_content_stable(
        self,
        max_wait: float = 50,
        poll_interval: float = 3,
        min_content_len: int = 0,
        stable_rounds: int = 2,
    ) -> tuple[int, float]:
        """Poll DOM content length until stable.

        Returns:
            (final_content_len, waited_seconds)
        """
        tag = self.PLATFORM_KEY.capitalize()
        await asyncio.sleep(poll_interval)
        waited = poll_interval
        prev_len = 0
        stable_count = 0

        while waited < max_wait:
            await asyncio.sleep(poll_interval)
            waited += poll_interval
            result = await self.client.eval(self._content_check_js())
            if "error" in result:
                logger.warning("[%s] eval error at %ds: %s", tag, waited, result["error"])
            cur_len = int(result.get("output", "0") or "0")
            logger.info("[%s] Poll %ds: content_len=%d (prev=%d, stable=%d)",
                        tag, waited, cur_len, prev_len, stable_count)

            if cur_len > 0 and cur_len == prev_len:
                stable_count += 1
                if stable_count >= stable_rounds and cur_len >= min_content_len:
                    logger.info("[%s] Content stable at %d chars after %ds", tag, cur_len, waited)
                    break
            else:
                stable_count = 0
            prev_len = cur_len

        return prev_len, waited

    async def _dump_page_debug(self, waited: float, extra_keywords: list[str] | None = None) -> None:
        """Dump page structure for diagnostics when no content is found.

        Uses Playwright's page.evaluate() for browser-context DOM inspection.
        """
        tag = self.PLATFORM_KEY.capitalize()
        logger.warning("[%s] No content detected after %ds — dumping page structure", tag, waited)
        try:
            keywords = [
                'markdown', 'message', 'chat', 'answer', 'content', 'reply',
            ] + (extra_keywords or [])
            kw_filter = " || ".join(f"c.includes('{kw}')" for kw in keywords)
            dump = await self.client.page.evaluate(f"""() => {{
                const bodyText = (document.body?.innerText || '').slice(0, 500);
                const allCls = new Set();
                document.querySelectorAll('*').forEach(el => {{
                    const cn = typeof el.className === 'string' ? el.className : (el.className?.baseVal || '');
                    cn.split(' ').forEach(c => {{ if (c.trim()) allCls.add(c.trim()); }});
                }});
                const mdLike = [...allCls].filter(c => {kw_filter}).slice(0, 40);
                return {{ bodyText, mdLike }};
            }}""")
            logger.warning("[%s] Page text: %s", tag, str(dump.get("bodyText", ""))[:300])
            logger.warning("[%s] Relevant classes: %s", tag, dump.get("mdLike", []))
        except Exception as e:
            logger.warning("[%s] Could not dump page: %s", tag, e)

    # ------------------------------------------------------------------ textarea helper

    def _find_textarea_ref(self, snapshot: dict) -> str | None:
        """Find textarea/textbox reference from accessibility snapshot."""
        try:
            refs = snapshot.get("refs", {})
            for ref_id, info in refs.items():
                if info.get("role") in ("textbox", "textfield", "input"):
                    return f"@{ref_id}"
            return None
        except Exception:
            return None

    # ------------------------------------------------------------------ visibility helper

    async def _is_visible(self, selector: str) -> bool:
        """Check if element exists AND is visible (offsetParent not null)."""
        page = self.client.page
        if page is None:
            return False
        try:
            return await page.evaluate(f"""() => {{
                const el = document.querySelector('{selector}');
                return el !== null && el.offsetParent !== null;
            }}""")
        except Exception:
            return False

    # ------------------------------------------------------------------ login

    async def _check_login_status(self, check_selector: str) -> bool:
        """Check if user is logged in."""
        try:
            if self._is_playwright:
                result = await self.client.wait(selector=check_selector, timeout=4000)
                return result.get("success", False)
            else:
                from app.core.fetchers.browser.agent_browser import AgentBrowserClient
                if isinstance(self.client, AgentBrowserClient):
                    result = await self.client.run_command(
                        "is", "visible", check_selector, json_output=True
                    )
                    return result.get("success", False)
                return False
        except Exception:
            return False

    async def _wait_for_login(
        self,
        check_selector: str,
        timeout: int = 300,
        poll_interval: float = 2.0,
    ) -> bool:
        """Wait for user to complete login."""
        elapsed = 0.0
        while elapsed < timeout:
            if await self._check_login_status(check_selector):
                return True
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        return False

    # ------------------------------------------------------------------ modal/popup detection

    # Common modal indicators across all platforms.  Subclasses can override
    # ``_DEFAULTS["modal_selectors"]`` or ``_DEFAULTS["modal_texts"]`` to
    # add platform-specific patterns.
    _COMMON_MODAL_SELECTORS = [
        "[role='dialog']",
        "[role='alertdialog']",
        "[class*='modal']",
        # NOTE: [class*='dialog'] removed — too broad (Yuanbao false positive)
    ]
    _COMMON_MODAL_TEXTS = [
        "已阅读并同意",
        "用户协议",
        "隐私政策",
        "服务条款",
        "Terms of Service",
        "Privacy Policy",
    ]

    async def _detect_blocking_modal(self) -> str:
        """Detect blocking modals/agreements on the page.

        Returns a description string if a modal is found, empty string otherwise.
        Checks for visible modal elements, then searches for agreement text
        INSIDE those modals (not the full page body — avoids footer false positives).
        """
        page = self.client.page
        if page is None:
            return ""

        extra_sels = self._DEFAULTS.get("modal_selectors", [])
        extra_texts = self._DEFAULTS.get("modal_texts", [])
        all_sels = json.dumps(self._COMMON_MODAL_SELECTORS + (extra_sels if isinstance(extra_sels, list) else []))
        all_texts = json.dumps(self._COMMON_MODAL_TEXTS + (extra_texts if isinstance(extra_texts, list) else []), ensure_ascii=False)

        try:
            result = await page.evaluate(f"""() => {{
                const sels = {all_sels};
                const texts = {all_texts};
                for (const sel of sels) {{
                    const el = document.querySelector(sel);
                    if (!el || el.offsetParent === null || el.offsetHeight < 50) continue;
                    // Check if this modal contains agreement/policy text
                    const modalText = el.innerText || '';
                    for (const txt of texts) {{
                        if (modalText.includes(txt)) return 'modal_text: ' + txt;
                    }}
                    // Visible modal without agreement text — might be a normal UI element
                    // Only flag it if it has typical blocking-modal traits
                    const hasOverlay = !!el.closest('[class*="overlay"], [class*="mask"]');
                    const hasCloseBtn = !!el.querySelector('[class*="close"], [aria-label*="close"], [aria-label*="关闭"]');
                    if (hasOverlay || hasCloseBtn) return 'modal: ' + sel;
                }}
                return '';
            }}""")
            return result or ""
        except Exception as e:
            logger.debug("[%s] Modal detection failed: %s", self.PLATFORM_KEY, e)
            return ""

    async def _wait_for_modal_clear(self, timeout: int = 300) -> bool:
        """Wait until blocking modals are gone (user dismissed them)."""
        elapsed = 0.0
        while elapsed < timeout:
            detected = await self._detect_blocking_modal()
            if not detected:
                return True
            await asyncio.sleep(2)
            elapsed += 2
        return False

    async def _open_headed_for_user_action(self, url: str | None = None) -> bool:
        """Reopen the page in headed mode and try to present it to the user."""
        await self.client.close()
        open_result = await self.client.open(url or self.URL, headed=True)
        if not open_result.get("success"):
            return False

        # Avoid prompting the user while the window is still on a blank bootstrap page.
        if self.client.page is not None:
            for _ in range(10):
                try:
                    current_url = self.client.page.url or ""
                    if current_url and current_url != "about:blank":
                        break
                except Exception:
                    pass
                await asyncio.sleep(0.5)

        bring_to_front = getattr(self.client, "bring_to_front", None)
        if callable(bring_to_front):
            try:
                await bring_to_front()
            except Exception as e:
                logger.debug("[%s] bring_to_front failed during user-action reopen: %s", self.PLATFORM_KEY, e)

        await asyncio.sleep(3)
        return True

    async def _prepare_user_action_request(
        self,
        action_type: str,
        message: str,
        action_hint: str | None,
        progress: float,
        url: str | None = None,
    ) -> str | None:
        """Open a stable headed browser window, then register a user-action request."""
        opened = await self._open_headed_for_user_action(url)
        if not opened:
            return None
        if not self.session_id:
            return None
        request = await register_browser_action_request(
            session_id=self.session_id,
            platform=self.PLATFORM.value,
            action_type=action_type,
            message=message,
            action_hint=action_hint,
            progress=progress,
        )
        return request.request_id

    async def _wait_for_user_action_completion(
        self,
        request_id: str | None,
        ready_check: ReadyCheck,
        timeout: int = 300,
        ready_timeout: int = 45,
    ) -> bool:
        """Wait until the user explicitly confirms completion, then validate readiness."""
        if not request_id:
            return False

        try:
            resolution = await wait_for_browser_action_resolution(request_id, timeout=timeout)
            if resolution != "completed":
                return False
            return await ready_check(ready_timeout)
        finally:
            await clear_browser_action_request(request_id)

    async def _check_and_handle_modal(self) -> "BrowserEvent | None":
        """Generic modal/popup check.  Call once after navigation, not per question.

        If a blocking modal is detected:
        1. Yields WAITING_FOR_MODAL event (distinct from WAITING_FOR_LOGIN)
        2. Opens headed browser for user to handle the modal
        3. Waits up to 300s for modal to clear

        Returns None if no modal, or a BrowserEvent (WAITING_FOR_MODAL or ERROR).
        """
        detected = await self._detect_blocking_modal()
        if not detected:
            return None

        platform_name = getattr(self, 'PLATFORM', self.PLATFORM_KEY)
        display_name = str(platform_name.value) if hasattr(platform_name, 'value') else str(platform_name)
        logger.info("[%s] Blocking modal detected: %s", self.PLATFORM_KEY, detected)

        event = self._create_event(
            BrowserState.WAITING_FOR_MODAL,
            f"检测到 {display_name} 页面弹窗需要确认，请在浏览器窗口中操作",
            progress=0.35,
            requires_action=True,
            action_hint=f"请在弹出的浏览器窗口中关闭弹窗或同意协议（{display_name}），完成后点击“我已完成”",
        )

        # Reopen as headed browser for user to interact
        opened = await self._open_headed_for_user_action(self.URL)
        if not opened:
            return self._create_event(BrowserState.ERROR, "打开浏览器窗口失败，请重试", progress=0)

        # Wait for user to dismiss the modal
        modal_cleared = await self._wait_for_modal_clear(timeout=300)
        if not modal_cleared:
            return self._create_event(BrowserState.ERROR, "弹窗处理超时，请重试", progress=0)

        logger.info("[%s] Modal cleared by user, continuing", self.PLATFORM_KEY)
        return event

    # ------------------------------------------------------------------ network interception

    def _get_intercept_config(self) -> InterceptConfig | None:
        """Load intercept config from selectors.yaml for this platform.

        Returns None if no intercept config is defined (fall back to DOM only).
        """
        intercept = self._sel("intercept")
        if not intercept or not isinstance(intercept, dict):
            return None
        url_pattern = intercept.get("url_pattern")
        if not url_pattern:
            return None
        return InterceptConfig(
            url_pattern=url_pattern,
            method=intercept.get("method", "POST"),
            content_type_contains=intercept.get("content_type_contains", ""),
            timeout=float(intercept.get("timeout", 60)),
        )

    def _get_response_parser(self) -> BaseResponseParser | None:
        """Return the appropriate response parser for this platform.

        Override in subclasses to provide platform-specific parsers.
        Returns None to skip network interception.
        """
        return None

    async def _intercept_and_wait(
        self,
        config: InterceptConfig,
        parser: BaseResponseParser,
    ) -> ParsedResponse | None:
        """Register a response listener, wait for a matching response, and parse it.

        Must be started as an asyncio.Task BEFORE the question is submitted,
        so the listener is active when the HTTP request fires.

        Returns ParsedResponse on success, None on timeout or error.
        """
        tag = self.PLATFORM_KEY.capitalize()
        page = self.client.page
        if page is None:
            return None

        result_future: asyncio.Future[ParsedResponse | None] = asyncio.get_running_loop().create_future()
        url_re = re.compile(config.url_pattern)

        async def on_response(response):
            try:
                if result_future.done():
                    return
                req = response.request
                if req.method.upper() != config.method.upper():
                    return
                if not url_re.search(response.url):
                    return
                ct = response.headers.get("content-type", "")
                if config.content_type_contains and config.content_type_contains not in ct:
                    return

                logger.info("[%s] Intercepted response: %s (%s)", tag, response.url[:80], ct)

                # Binary Connect protocol needs frame decoding
                if "connect" in ct or "grpc" in ct:
                    from app.core.fetchers.browser.parsers.connect import decode_binary_frames
                    body_bytes = await response.body()
                    frames = decode_binary_frames(body_bytes)
                    body = "\n".join(frames)
                    logger.info("[%s] Decoded %d binary frames", tag, len(frames))
                else:
                    raw = await response.body()
                    body = raw.decode("utf-8", errors="replace")
                    # Fix double UTF-8 encoding (Doubao's SSE is double-encoded)
                    if self.DOUBLE_UTF8_FIX:
                        try:
                            fixed = _undo_double_utf8(body)
                            if fixed != body:
                                body = fixed
                                logger.info("[%s] Fixed double UTF-8 encoding", tag)
                        except Exception:
                            pass

                # Diagnostic: dump body for debugging new/unstable parsers
                logger.debug("[%s] SSE body (%d chars), first 500: %s",
                             tag, len(body), body[:500])
                # Save full body to file for offline analysis (only when DEBUG)
                if logger.isEnabledFor(logging.DEBUG):
                    try:
                        from pathlib import Path
                        dump_dir = Path(__file__).parent / "debug_dumps"
                        dump_dir.mkdir(exist_ok=True)
                        dump_file = dump_dir / f"{tag.lower()}_sse_body.txt"
                        dump_file.write_text(body, encoding="utf-8")
                        logger.debug("[%s] SSE body saved to %s", tag, dump_file)
                    except Exception:
                        pass

                parsed = parser.parse(body, url=response.url)
                parsed = parser.validate(parsed)

                if not result_future.done():
                    result_future.set_result(parsed)
            except Exception as e:
                logger.warning("[%s] Intercept handler error: %s", tag, e)
                if not result_future.done():
                    result_future.set_result(None)

        page.on("response", on_response)
        try:
            result = await asyncio.wait_for(result_future, timeout=config.timeout)
            if result and result.parse_ok:
                logger.info("[%s] Network interception success: %d chars, %d refs",
                            tag, len(result.answer_text), len(result.references))
            else:
                logger.info("[%s] Network interception: parse_ok=%s, error=%s",
                            tag, result.parse_ok if result else "None",
                            result.error if result else "timeout")
            return result
        except asyncio.TimeoutError:
            logger.info("[%s] Network interception timed out after %ds", tag, config.timeout)
            return None
        except Exception as e:
            logger.warning("[%s] Network interception failed: %s", tag, e)
            return None
        finally:
            page.remove_listener("response", on_response)

    # ------------------------------------------------------------------ event helper

    def _create_event(
        self,
        state: BrowserState,
        message: str,
        progress: float = 0,
        requires_action: bool = False,
        action_type: str | None = None,
        action_hint: str | None = None,
        request_id: str | None = None,
        data: FetchResult | None = None,
        error_type: str | None = None,
    ) -> BrowserEvent:
        """Create a browser event."""
        return BrowserEvent(
            state=state,
            message=message,
            progress=progress,
            requires_action=requires_action,
            action_type=action_type,
            action_hint=action_hint,
            request_id=request_id,
            error=None,
            error_type=error_type,
            recoverable=True,
            data=data,
        )

    # ------------------------------------------------------------------ abstract

    @abstractmethod
    async def fetch(self, question: str) -> AsyncGenerator[BrowserEvent, None]:
        """Fetch answer for a question.

        Yields BrowserEvent objects for progress updates.
        """
        pass
        yield  # type: ignore
