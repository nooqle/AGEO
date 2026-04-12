"""Base browser handler for LLM platforms.

Provides Template Method pattern with shared logic extracted from
DeepSeek/Kimi/Yuanbao/Doubao handlers (Phase 0 refactor).

NOTE: The eval() calls in this module are Playwright's page.evaluate() which
executes JavaScript in the browser context for DOM scraping. This is the
standard Playwright API pattern - not Python's eval().
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Awaitable, Callable, Union
from urllib.parse import urlparse

from app.core.fetchers.browser.agent_browser import AgentBrowserClient
from app.core.fetchers.browser.aio_backend import AioSandboxBackend
from app.core.fetchers.browser.browser_agent_contract import (
    BrowserAgentAction,
    BrowserAgentDecision,
    BrowserAgentLoopContext,
    PlatformBrowserProfile,
    platform_profile_to_payload,
)
from app.core.fetchers.browser.browser_agent_loop import collect_browser_agent_step
from app.core.fetchers.browser.parsers.base import (
    BaseResponseParser,
    InterceptConfig,
    ParsedResponse,
)
from app.core.fetchers.browser.playwright_client import PlaywrightBrowserClient
from app.schemas.fetch import (
    BrowserEvent,
    BrowserState,
    FetchMethod,
    FetchResult,
    Platform,
    SearchReference,
)
from app.workflow.browser_action_runtime import (
    clear_browser_action_request,
    get_or_register_browser_action_request,
    infer_browser_action_state,
    wait_for_browser_action_resolution,
)

# CP1252 byte-to-Unicode mappings for the 0x80-0x9F range (where CP1252 differs
# from ISO-8859-1).  Used by _undo_double_utf8() to reverse double encoding.
_CP1252_EXTRA: dict[int, int] = {
    0x20AC: 0x80,
    0x201A: 0x82,
    0x0192: 0x83,
    0x201E: 0x84,
    0x2026: 0x85,
    0x2020: 0x86,
    0x2021: 0x87,
    0x02C6: 0x88,
    0x2030: 0x89,
    0x0160: 0x8A,
    0x2039: 0x8B,
    0x0152: 0x8C,
    0x017D: 0x8E,
    0x2018: 0x91,
    0x2019: 0x92,
    0x201C: 0x93,
    0x201D: 0x94,
    0x2022: 0x95,
    0x2013: 0x96,
    0x2014: 0x97,
    0x02DC: 0x98,
    0x2122: 0x99,
    0x0161: 0x9A,
    0x203A: 0x9B,
    0x0153: 0x9C,
    0x017E: 0x9E,
    0x0178: 0x9F,
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

logger = logging.getLogger(__name__)

ReadyCheck = Callable[[int], Awaitable[bool]]


def _is_junk_title(title: str) -> bool:
    """Return True if the title is just numbers, dashes, or punctuation."""
    return bool(re.fullmatch(r"[-\d\s.\[\]()]+", title))


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
    BROWSER_READY_URL_PATTERNS: tuple[str, ...] = ()
    BROWSER_LOGIN_URL_PATTERNS: tuple[str, ...] = ()
    BROWSER_READY_HINTS: tuple[str, ...] = ()
    BROWSER_LOGIN_HINTS: tuple[str, ...] = ()
    BROWSER_LATE_BLOCKER_HINTS: tuple[str, ...] = ()

    def __init__(
        self,
        client: Union[AgentBrowserClient, PlaywrightBrowserClient],
        headed: bool = False,
        session_id: str | None = None,
        run_id: str | None = None,
    ):
        self.client = client
        self.headed = headed
        self.session_id = session_id
        self.run_id = run_id
        self._is_playwright = isinstance(client, PlaywrightBrowserClient)
        self._sel_cache: dict = {}
        self._aio_backend = AioSandboxBackend()

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
                result = await self.client.eval(
                    f"""() => {{
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
                }}"""
                )
            else:
                sel = json.dumps(content_sel, ensure_ascii=False)
                # Single selector (e.g. DeepSeek's "div.ds-markdown")
                result = await self.client.eval(
                    f"""() => {{
                    const messages = document.querySelectorAll({sel});
                    const lastMessage = messages[messages.length - 1];
                    if (!lastMessage) return '';
                    const clone = lastMessage.cloneNode(true);
                    clone.querySelectorAll({cite_strip_sel}).forEach(el => el.remove());
                    return clone.innerText;
                }}"""
                )

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
                    cleaned.append(
                        SearchReference(
                            index=len(cleaned) + 1,
                            title=title,
                            url=url,
                            snippet=None,
                            site_name=None,
                            is_official=False,
                        )
                    )
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
                logger.info(
                    "[%s] Extracted %d references via selector: %s",
                    tag,
                    len(refs),
                    selector,
                )
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
                logger.info(
                    "[%s] Extracted %d references (after expand) via: %s",
                    tag,
                    len(refs),
                    selector,
                )
                return refs

        # Phase 3: Diagnostic
        try:
            diag = await self.client.eval(
                """() => {
                const links = Array.from(document.querySelectorAll('a[href^="http"]'));
                return JSON.stringify(links.slice(0, 10).map(a => ({
                    url: a.href.slice(0, 80),
                    txt: (a.textContent || '').trim().slice(0, 40),
                    cls: (a.className || '').slice(0, 60),
                })));
            }"""
            )
            link_data = json.loads(diag.get("output", "[]") or "[]")
            logger.warning(
                "[%s] No references found. Sample http links (%d): %s",
                tag,
                len(link_data),
                link_data[:5],
            )
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
        prev_len, waited, _ = await self._wait_for_content_with_browser_agent(
            max_wait=max_wait,
            poll_interval=poll_interval,
            min_content_len=min_content_len,
            stable_rounds=stable_rounds,
            target_url=self.URL,
        )
        return prev_len, waited

    async def _dump_page_debug(
        self, waited: float, extra_keywords: list[str] | None = None
    ) -> None:
        """Dump page structure for diagnostics when no content is found.

        Uses Playwright's page.evaluate() for browser-context DOM inspection.
        """
        tag = self.PLATFORM_KEY.capitalize()
        logger.warning(
            "[%s] No content detected after %ds — dumping page structure", tag, waited
        )
        try:
            keywords = [
                "markdown",
                "message",
                "chat",
                "answer",
                "content",
                "reply",
            ] + (extra_keywords or [])
            kw_filter = " || ".join(f"c.includes('{kw}')" for kw in keywords)
            dump = await self.client.page.evaluate(
                f"""() => {{
                const bodyText = (document.body?.innerText || '').slice(0, 500);
                const allCls = new Set();
                document.querySelectorAll('*').forEach(el => {{
                    const cn = typeof el.className === 'string' ? el.className : (el.className?.baseVal || '');
                    cn.split(' ').forEach(c => {{ if (c.trim()) allCls.add(c.trim()); }});
                }});
                const mdLike = [...allCls].filter(c => {kw_filter}).slice(0, 40);
                return {{ bodyText, mdLike }};
            }}"""
            )
            logger.warning(
                "[%s] Page text: %s", tag, str(dump.get("bodyText", ""))[:300]
            )
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
            return await page.evaluate(
                f"""() => {{
                const el = document.querySelector('{selector}');
                return el !== null && el.offsetParent !== null;
            }}"""
            )
        except Exception:
            return False

    def _platform_display_name(self) -> str:
        mapping = {
            "doubao": "豆包",
            "hunyuan": "元宝",
            "yuanbao": "元宝",
            "kimi": "Kimi",
            "deepseek": "DeepSeek",
        }
        return mapping.get(self.PLATFORM.value, self.PLATFORM.value)

    def _browser_agent_profile(self) -> PlatformBrowserProfile:
        return PlatformBrowserProfile(
            platform=self.PLATFORM.value,
            entry_url=self.URL,
            ready_url_patterns=tuple(self.BROWSER_READY_URL_PATTERNS),
            login_url_patterns=tuple(self.BROWSER_LOGIN_URL_PATTERNS),
            ready_hints=tuple(self.BROWSER_READY_HINTS),
            login_hints=tuple(self.BROWSER_LOGIN_HINTS),
            late_blocker_hints=tuple(self.BROWSER_LATE_BLOCKER_HINTS),
        )

    async def _browser_agent_screenshot_provider(self) -> dict | None:
        if not getattr(self.client, "aio_session_id", None):
            return None
        try:
            return await self._aio_backend.take_screenshot()
        except Exception as e:
            logger.debug(
                "[%s] Browser-agent screenshot capture failed: %s",
                self.PLATFORM_KEY,
                e,
            )
            return None

    def _build_browser_agent_loop_context(
        self,
        *,
        stage: str,
        url: str | None = None,
        action_type: str | None = None,
        note: str | None = None,
        meta: dict | None = None,
    ) -> BrowserAgentLoopContext:
        resolved_note = note or self._browser_agent_stage_note(
            stage=stage,
            action_type=action_type,
        )
        resolved_meta = self._browser_agent_stage_meta(
            stage=stage,
            action_type=action_type,
            extra_meta=meta,
        )
        return BrowserAgentLoopContext(
            platform=self.PLATFORM.value,
            stage=stage,
            target_url=url or self.URL,
            note=resolved_note,
            meta=resolved_meta,
        )

    def _browser_agent_stage_note(
        self,
        *,
        stage: str,
        action_type: str | None = None,
    ) -> str | None:
        platform_name = self._platform_display_name()
        if stage == "preflight":
            return (
                f"你正在为 {platform_name} 抓取答案做浏览器预检。"
                "优先自动处理空白页、错误页、Cookie/协议弹窗、下载/升级弹窗。"
                "只有登录、验证码、人机验证、安全确认、账号选择才交给人工接管。"
            )
        if stage == "wait_gate":
            return (
                f"当前问题已经提交到 {platform_name}。"
                "请判断页面是在正常生成回答、可以自动关闭的轻量弹窗、还是已经进入需要人工接管的登录/验证阻塞。"
            )
        if stage == "resume_probe":
            if action_type in {
                "login",
                "verify",
                "captcha",
                "security_confirmation",
                "account_selection",
            }:
                return (
                    f"当前正在判断 {platform_name} 的人工接管是否已经完成。"
                    "如果页面仍显示登录、二维码、手机号/验证码、人机验证、安全确认或账号选择，则不要放行。"
                    "只有当页面已经回到可继续提问、继续等待回答、或继续提取结果的主界面时，才视为 ready。"
                )
            if action_type == "modal":
                return (
                    f"当前正在判断 {platform_name} 的弹窗阻塞是否已解除。"
                    "优先自动关闭普通弹窗；如果仍是登录/验证类阻塞，则继续保持人工接管。"
                )
        if stage == "empty_answer":
            return (
                f"{platform_name} 当前提取到的回答为空或过短。"
                "请判断这是页面尚未完成、可自动恢复的弹窗/错误、还是需要人工接管才能继续。"
            )
        return None

    def _browser_agent_stage_meta(
        self,
        *,
        stage: str,
        action_type: str | None = None,
        extra_meta: dict | None = None,
    ) -> dict:
        resolved_meta = {
            "platform_display_name": self._platform_display_name(),
            "action_type": action_type,
            "platform_profile": platform_profile_to_payload(
                self._browser_agent_profile()
            ),
        }
        if extra_meta:
            resolved_meta.update(dict(extra_meta))
        return resolved_meta

    async def _execute_browser_agent_action(
        self,
        action: BrowserAgentAction,
        *,
        fallback_url: str | None,
    ) -> bool:
        try:
            if action.action_type in {"click_ref", "close_popup"}:
                if not action.ref:
                    return False
                result = await self.client.click(action.ref)
                return bool(result.get("success"))

            if action.action_type == "fill_ref":
                if not action.ref:
                    return False
                result = await self.client.fill(action.ref, action.text or "")
                return bool(result.get("success"))

            if action.action_type == "press_key":
                if not action.key:
                    return False
                result = await self.client.press(action.key)
                return bool(result.get("success"))

            if action.action_type == "wait":
                await asyncio.sleep(max(action.wait_seconds or 0.2, 0.2))
                return True

            if action.action_type == "refresh":
                if self.client.page is not None:
                    await self.client.page.reload(wait_until="domcontentloaded")
                    return True
                return False

            if action.action_type == "navigate":
                target_url = action.target_url or fallback_url
                if not target_url:
                    return False
                if self.client.page is not None:
                    await self.client.page.goto(target_url, wait_until="domcontentloaded")
                    return True
                result = await self.client.open(target_url, headed=self.headed)
                return bool(result.get("success"))

            return action.action_type == "complete"
        except Exception as e:
            logger.warning(
                "[%s] Browser-agent action failed (%s): %s",
                self.PLATFORM_KEY,
                action.action_type,
                e,
            )
            return False

    async def _begin_browser_agent_takeover_gate(
        self,
        *,
        blocker_kind: str,
        reason_code: str | None = None,
        blocking_url: str | None = None,
        blocking_fingerprint: str | None = None,
        progress: float,
        url: str | None,
    ) -> tuple[list[BrowserEvent], str | None]:
        platform_name = self._platform_display_name()
        if blocker_kind in {"verification", "captcha"}:
            return await self._begin_modal_takeover_gate(
                message="检测到安全验证，请在浏览器窗口中完成验证",
                action_hint=f"请在弹出的浏览器窗口中完成{platform_name}验证，完成后点击“我已完成”",
                progress=progress,
                url=url,
                open_error_message=f"打开{platform_name}浏览器窗口失败，请重试",
                reason_code=reason_code,
                blocking_url=blocking_url,
                blocking_fingerprint=blocking_fingerprint,
            )

        return await self._begin_login_takeover_gate(
            message="检测到登录或账号确认界面，请在浏览器窗口中完成操作",
            action_hint=f"请在弹出的浏览器窗口中完成{platform_name}登录或账号确认，完成后点击“我已完成”",
            progress=progress,
            url=url,
            open_error_message=f"打开{platform_name}浏览器窗口失败，请重试",
            reason_code=reason_code,
            blocking_url=blocking_url,
            blocking_fingerprint=blocking_fingerprint,
        )

    async def _run_browser_agent_preflight(
        self,
        *,
        progress: float,
        url: str | None = None,
        max_rounds: int = 3,
    ) -> tuple[list[BrowserEvent], bool]:
        """Run one generic browser-agent preflight before platform logic."""

        sync_method = getattr(self.client, "sync_to_existing_target_page", None)
        for _ in range(max_rounds):
            step = await collect_browser_agent_step(
                client=self.client,
                platform=self.PLATFORM.value,
                loop_context=self._build_browser_agent_loop_context(
                    stage="preflight",
                    url=url or self.URL,
                ),
                target_url=url or self.URL,
                screenshot_provider=self._browser_agent_screenshot_provider,
            )
            decision = step.decision
            logger.info(
                "[%s] Browser-agent preflight decision: outcome=%s blocker=%s rationale=%s",
                self.PLATFORM_KEY,
                decision.outcome,
                decision.blocker_kind,
                decision.rationale,
            )

            if (
                decision.blocker_kind == "target_closed"
                and callable(sync_method)
                and await sync_method(url or self.URL)
            ):
                continue

            if decision.outcome == "takeover_required":
                takeover = decision.takeover
                events, request_id = await self._begin_browser_agent_takeover_gate(
                    blocker_kind=decision.blocker_kind,
                    reason_code=takeover.reason_code if takeover else None,
                    blocking_url=(
                        takeover.blocking_url
                        if takeover and takeover.blocking_url
                        else step.observation.current_url
                    ),
                    blocking_fingerprint=(
                        takeover.blocking_fingerprint if takeover else None
                    ),
                    progress=progress,
                    url=(
                        takeover.target_url
                        if takeover and takeover.target_url
                        else (url or self.URL)
                    ),
                )
                return events, bool(request_id or events)

            if decision.outcome == "failed":
                return [
                    self._create_event(
                        BrowserState.ERROR,
                        decision.error or "浏览器智能预检查失败",
                        progress=0,
                    )
                ], True

            if not decision.actions:
                return [], False

            action_ok = True
            for action in decision.actions:
                action_ok = await self._execute_browser_agent_action(
                    action,
                    fallback_url=url or self.URL,
                )
                if not action_ok:
                    break
            if not action_ok:
                return [], False

        return [], False

    async def _wait_for_content_with_browser_agent(
        self,
        *,
        max_wait: float = 50,
        poll_interval: float = 3,
        min_content_len: int = 0,
        stable_rounds: int = 2,
        target_url: str | None = None,
        blocker_check_after_seconds: float = 9,
    ) -> tuple[int, float, BrowserAgentDecision | None]:
        """Poll DOM content while allowing Browser Agent blocker checks."""

        tag = self.PLATFORM_KEY.capitalize()
        sync_method = getattr(self.client, "sync_to_existing_target_page", None)
        await asyncio.sleep(poll_interval)
        waited = poll_interval
        prev_len = 0
        stable_count = 0

        while waited < max_wait:
            await asyncio.sleep(poll_interval)
            waited += poll_interval
            result = await self.client.eval(self._content_check_js())
            if "error" in result:
                error_message = str(result["error"])
                logger.warning(
                    "[%s] eval error at %ds: %s", tag, waited, error_message
                )
                if (
                    callable(sync_method)
                    and "target" in error_message.lower()
                    and "closed" in error_message.lower()
                ):
                    logger.info(
                        "[%s] Attempting live-page resync after target-closed eval failure",
                        tag,
                    )
                    try:
                        if await sync_method(target_url or self.URL):
                            continue
                    except Exception as sync_error:
                        logger.warning(
                            "[%s] Live-page resync failed after target-closed eval error: %s",
                            tag,
                            sync_error,
                        )
            cur_len = int(result.get("output", "0") or "0")
            logger.info(
                "[%s] Poll %ds: content_len=%d (prev=%d, stable=%d)",
                tag,
                waited,
                cur_len,
                prev_len,
                stable_count,
            )

            if cur_len == 0 and waited >= blocker_check_after_seconds:
                step = await collect_browser_agent_step(
                    client=self.client,
                    platform=self.PLATFORM.value,
                    loop_context=self._build_browser_agent_loop_context(
                        stage="wait_gate",
                        url=target_url or self.URL,
                        meta={
                            "waited_seconds": waited,
                            "min_content_len": min_content_len,
                            "stable_rounds": stable_rounds,
                        },
                    ),
                    target_url=target_url or self.URL,
                    screenshot_provider=self._browser_agent_screenshot_provider,
                )
                decision = step.decision
                if (
                    decision.blocker_kind == "target_closed"
                    and callable(sync_method)
                    and await sync_method(target_url or self.URL)
                ):
                    continue
                if decision.outcome == "takeover_required":
                    logger.warning(
                        "[%s] Browser-agent wait gate detected blocker=%s at %ds",
                        tag,
                        decision.blocker_kind,
                        waited,
                    )
                    return prev_len, waited, decision
                if decision.actions:
                    action_ok = True
                    for action in decision.actions:
                        action_ok = await self._execute_browser_agent_action(
                            action,
                            fallback_url=target_url or self.URL,
                        )
                        if not action_ok:
                            break
                    if action_ok:
                        continue

            if cur_len > 0 and cur_len == prev_len:
                stable_count += 1
                if stable_count >= stable_rounds and cur_len >= min_content_len:
                    logger.info(
                        "[%s] Content stable at %d chars after %ds",
                        tag,
                        cur_len,
                        waited,
                    )
                    break
            else:
                stable_count = 0
            prev_len = cur_len

        return prev_len, waited, None

    async def _emit_browser_agent_takeover_from_decision(
        self,
        decision: BrowserAgentDecision,
        *,
        progress: float,
        fallback_url: str | None = None,
    ) -> tuple[list[BrowserEvent], str | None]:
        if decision.outcome != "takeover_required":
            return [], None
        takeover_url = (
            decision.takeover.target_url
            if decision.takeover and decision.takeover.target_url
            else fallback_url
        )
        return await self._begin_browser_agent_takeover_gate(
            blocker_kind=decision.blocker_kind,
            reason_code=decision.takeover.reason_code if decision.takeover else None,
            blocking_url=(
                decision.takeover.blocking_url
                if decision.takeover and decision.takeover.blocking_url
                else None
            ),
            blocking_fingerprint=(
                decision.takeover.blocking_fingerprint if decision.takeover else None
            ),
            progress=progress,
            url=takeover_url,
        )

    def _browser_agent_blocker_for_error_type(self, error_type: str | None) -> str | None:
        normalized = str(error_type or "").strip().lower()
        if normalized in {"auth_required", "login"}:
            return "login"
        if normalized in {"verify", "verification"}:
            return "verification"
        if normalized == "captcha":
            return "captcha"
        return None

    async def _emit_browser_agent_takeover_for_error_type(
        self,
        *,
        error_type: str | None,
        progress: float,
        fallback_url: str | None = None,
    ) -> tuple[list[BrowserEvent], str | None]:
        blocker_kind = self._browser_agent_blocker_for_error_type(error_type)
        if blocker_kind is None:
            return [], None
        return await self._begin_browser_agent_takeover_gate(
            blocker_kind=blocker_kind,
            reason_code=error_type or blocker_kind,
            progress=progress,
            url=fallback_url or self.URL,
        )

    async def _emit_browser_agent_takeover_for_current_page(
        self,
        *,
        progress: float,
        fallback_url: str | None = None,
    ) -> tuple[list[BrowserEvent], str | None]:
        step = await collect_browser_agent_step(
            client=self.client,
            platform=self.PLATFORM.value,
            loop_context=self._build_browser_agent_loop_context(
                stage="empty_answer",
                url=fallback_url or self.URL,
            ),
            target_url=fallback_url or self.URL,
            screenshot_provider=self._browser_agent_screenshot_provider,
        )
        decision = step.decision
        if decision.outcome != "takeover_required":
            return [], None
        return await self._emit_browser_agent_takeover_from_decision(
            decision,
            progress=progress,
            fallback_url=fallback_url or self.URL,
        )

    async def _handle_browser_agent_wait_blocker(
        self,
        blocker_decision: BrowserAgentDecision | None,
        *,
        progress: float,
        fallback_url: str | None = None,
    ) -> tuple[list[BrowserEvent], bool]:
        if blocker_decision is None:
            return [], False
        events, request_id = await self._emit_browser_agent_takeover_from_decision(
            blocker_decision,
            progress=progress,
            fallback_url=fallback_url or self.URL,
        )
        if request_id or events:
            return events, True
        return [], False

    async def _handle_browser_agent_parser_error(
        self,
        *,
        parsed_error: str,
        error_type: str | None,
        progress: float,
        fallback_url: str | None = None,
        message_overrides: dict[str, str] | None = None,
    ) -> tuple[list[BrowserEvent], bool]:
        events, request_id = await self._emit_browser_agent_takeover_for_error_type(
            error_type=error_type,
            progress=progress,
            fallback_url=fallback_url or self.URL,
        )
        if request_id or events:
            return events, True

        normalized_error_type = str(error_type or "").strip().lower()
        message_map = {
            "verify": f"{self._platform_display_name()}触发安全验证，请在浏览器窗口完成验证后重新采集。",
            "captcha": f"{self._platform_display_name()}触发验证码校验，请在浏览器窗口完成验证后重新采集。",
            "auth_required": f"{self._platform_display_name()}需要登录后才能继续抓取。",
            "login": f"{self._platform_display_name()}需要登录后才能继续抓取。",
            "rate_limit": f"{self._platform_display_name()}触发平台限流，请稍后重试。",
        }
        if message_overrides:
            message_map.update(message_overrides)
        message = message_map.get(
            normalized_error_type,
            f"{self._platform_display_name()}返回错误: {parsed_error}",
        )
        return [
            self._create_event(
                BrowserState.ERROR,
                message,
                progress=0,
                error_type=error_type,
            )
        ], True

    async def _handle_browser_agent_empty_answer(
        self,
        answer_text: str | None,
        *,
        progress: float,
        fallback_url: str | None = None,
    ) -> tuple[list[BrowserEvent], bool]:
        if answer_text and len(answer_text.strip()) >= 10:
            return [], False

        events, request_id = await self._emit_browser_agent_takeover_for_current_page(
            progress=progress,
            fallback_url=fallback_url or self.URL,
        )
        if request_id or events:
            return events, True

        logger.warning(
            "[%s] Answer too short or empty (%d chars)",
            self.PLATFORM_KEY.capitalize(),
            len(answer_text) if answer_text else 0,
        )
        return [
            self._create_event(
                BrowserState.ERROR,
                "未能提取到有效回答",
                progress=0,
            )
        ], True

    async def _browser_agent_resume_probe_ready(
        self,
        *,
        target_url: str | None = None,
        action_type: str | None = None,
        timeout: float = 30,
        poll_interval: float = 2.0,
    ) -> bool:
        """Check whether the current live page no longer needs human takeover.

        This is the first shared resume probe that relies on the Browser Agent
        observation/decision seam instead of platform-specific login selectors.
        It intentionally stays conservative: if the page still needs a human
        blocker cleared, or if auto-healing actions are still pending, the
        manual resume gate should remain blocked.
        """

        sync_method = getattr(self.client, "sync_to_existing_target_page", None)
        elapsed = 0.0

        while elapsed <= timeout:
            try:
                step = await collect_browser_agent_step(
                    client=self.client,
                    platform=self.PLATFORM.value,
                    loop_context=self._build_browser_agent_loop_context(
                        stage="resume_probe",
                        url=target_url or self.URL,
                        action_type=action_type,
                        meta={"elapsed_seconds": round(elapsed, 2)},
                    ),
                    target_url=target_url or self.URL,
                    screenshot_provider=self._browser_agent_screenshot_provider,
                )
            except Exception as exc:
                logger.warning(
                    "[%s] Browser-agent resume probe failed: %s",
                    self.PLATFORM_KEY,
                    exc,
                )
                return False

            decision = step.decision
            logger.info(
                "[%s] Browser-agent resume probe: outcome=%s blocker=%s actions=%d confidence=%.2f",
                self.PLATFORM_KEY,
                decision.outcome,
                decision.blocker_kind,
                len(decision.actions),
                decision.confidence,
            )

            if (
                decision.blocker_kind == "target_closed"
                and callable(sync_method)
                and await sync_method(target_url or self.URL)
            ):
                await asyncio.sleep(0.3)
                elapsed += 0.3
                continue

            if decision.actions:
                all_ok = True
                for action in decision.actions:
                    if not await self._execute_browser_agent_action(
                        action,
                        fallback_url=target_url or self.URL,
                    ):
                        all_ok = False
                        break
                if all_ok:
                    await asyncio.sleep(max(poll_interval, 0.8))
                    elapsed += max(poll_interval, 0.8)
                    continue
                return False

            if decision.outcome in {"takeover_required", "failed"}:
                return False

            if decision.blocker_kind in {
                "blank_page",
                "navigation_error",
                "target_closed",
            }:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
                continue

            return True
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

    async def probe_takeover_ready(self, action_type: str) -> bool:
        """Cheap readiness probe used by AIO heartbeat auto-resume.

        The live A4 handler keeps owning the browser session while the user
        operates the Canvas/VNC surface. This probe lets the control plane ask
        whether the blocker has already been cleared, so takeover does not
        depend on a second frontend-specific resolve channel.
        """

        if action_type == "modal":
            return not bool(await self._detect_blocking_modal())
        if action_type == "login":
            # Login takeover must be explicitly resumed by the user.
            # Auto-resume is too aggressive for interactive Canvas flows and
            # can close the browser while the user is still operating it.
            return False
        return False

    async def probe_resume_gate_ready(self, action_type: str) -> bool:
        """Readiness probe used by explicit manual resolve."""

        if action_type in {
            "login",
            "verify",
            "captcha",
            "security_confirmation",
            "account_selection",
        }:
            return await self._browser_agent_resume_probe_ready(
                target_url=self.URL,
                action_type=action_type,
            )
        if action_type == "modal":
            if await self._browser_agent_resume_probe_ready(
                target_url=self.URL,
                action_type=action_type,
            ):
                return True
            return not bool(await self._detect_blocking_modal())
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
        all_sels = json.dumps(
            self._COMMON_MODAL_SELECTORS
            + (extra_sels if isinstance(extra_sels, list) else [])
        )
        all_texts = json.dumps(
            self._COMMON_MODAL_TEXTS
            + (extra_texts if isinstance(extra_texts, list) else []),
            ensure_ascii=False,
        )

        try:
            result = await page.evaluate(
                f"""() => {{
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
            }}"""
            )
            return result or ""
        except Exception as e:
            logger.debug("[%s] Modal detection failed: %s", self.PLATFORM_KEY, e)
            return ""

    async def _wait_for_modal_clear(self, timeout: int = 480) -> bool:
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
        if getattr(self.client, "aio_session_id", None):
            open_result = await self.client.open(url or self.URL, headed=False)
        else:
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
                logger.debug(
                    "[%s] bring_to_front failed during user-action reopen: %s",
                    self.PLATFORM_KEY,
                    e,
                )

        await asyncio.sleep(3)
        return True

    async def _prepare_takeover_surface(self, url: str | None = None) -> bool:
        """Prepare the interactive surface used for human takeover.

        For local Playwright runtimes we keep the old behavior of reopening in a
        visible headed browser. For AIO-backed clients the live browser already
        exists remotely, so we should preserve the leased session and only ensure
        the current page is available for takeover.
        """

        if getattr(self.client, "aio_session_id", None):
            page = getattr(self.client, "page", None)
            if page is None or page.is_closed():
                open_result = await self.client.open(url or self.URL, headed=False)
                if not open_result.get("success"):
                    return False
            bring_to_front = getattr(self.client, "bring_to_front", None)
            if callable(bring_to_front):
                try:
                    await bring_to_front()
                except Exception as e:
                    logger.debug(
                        "[%s] bring_to_front failed during AIO takeover prep: %s",
                        self.PLATFORM_KEY,
                        e,
                    )
            await asyncio.sleep(1)
            return True

        return await self._open_headed_for_user_action(url)

    async def _reuse_existing_aio_surface(self, url: str | None = None) -> bool:
        """Reuse the current AIO page when it already matches the target host.

        After a human takeover completes, the user has already interacted with
        the live remote browser surface. Reopening the platform URL at this
        point can discard or bypass the just-completed login/verification page
        and make the handler look as if the session was not preserved.
        """

        if not getattr(self.client, "aio_session_id", None):
            return False

        page = getattr(self.client, "page", None)
        if page is None or page.is_closed():
            return False

        current_url = page.url or ""
        target_url = url or self.URL
        current_host = (urlparse(current_url).netloc or "").lower()
        target_host = (urlparse(target_url).netloc or "").lower()
        if not current_host or not target_host or current_host != target_host:
            return False
        if current_url == "about:blank":
            return False

        logger.info(
            "[%s] Reusing existing AIO surface without reopening (current_url=%s target_host=%s)",
            self.PLATFORM_KEY,
            current_url,
            target_host,
        )
        return True

    async def _prepare_user_action_request(
        self,
        action_type: str,
        message: str,
        action_hint: str | None,
        progress: float,
        url: str | None = None,
        reason_code: str | None = None,
        blocking_url: str | None = None,
        blocking_fingerprint: str | None = None,
    ) -> str | None:
        """Open a stable headed browser window, then register a user-action request."""
        ensure_remote_runtime = getattr(self.client, "_ensure_remote_runtime", None)
        is_aio_client = callable(ensure_remote_runtime)
        if not is_aio_client:
            opened = await self._prepare_takeover_surface(url)
            if not opened:
                return None
        if not self.session_id:
            return None
        request, _ = await get_or_register_browser_action_request(
            session_id=self.session_id,
            platform=self.PLATFORM.value,
            action_type=action_type,
            message=message,
            action_hint=action_hint,
            target_url=url,
            progress=progress,
            run_id=self.run_id,
            task_id=str(getattr(self.client, "task_id", "") or "") or None,
            user_id=str(getattr(self.client, "user_id", "") or "") or None,
            state=infer_browser_action_state(action_type),
            reason_code=reason_code,
            blocking_url=blocking_url,
            blocking_fingerprint=blocking_fingerprint,
        )
        return request.request_id

    async def _wait_for_user_action_completion(
        self,
        request_id: str | None,
        ready_check: ReadyCheck,
        timeout: int = 480,
        ready_timeout: int = 45,
    ) -> tuple[bool, str | None]:
        """Wait until the user explicitly confirms completion.

        Readiness should be validated by the resumed automation path itself.
        Acknowledge user completion immediately so control returns to the
        browser agent instead of blocking on a second synchronous gate here.
        """
        if not request_id:
            return False, None

        resolution: str | None = None
        try:
            resolution = await wait_for_browser_action_resolution(
                request_id, timeout=timeout
            )
            if resolution != "completed":
                return False, resolution
            return True, resolution
        finally:
            await clear_browser_action_request(request_id)

    async def _run_user_action_gate(
        self,
        *,
        state: BrowserState,
        action_type: str,
        message: str,
        action_hint: str,
        progress: float,
        url: str | None,
        ready_check: ReadyCheck,
        timeout: int = 480,
        ready_timeout: int = 120,
        open_error_message: str,
        timeout_error_message: str,
    ) -> tuple[list[BrowserEvent], bool]:
        """Prepare, emit, and validate one human-action gate consistently."""

        initial_events, request_id = await self._begin_user_action_gate(
            state=state,
            action_type=action_type,
            message=message,
            action_hint=action_hint,
            progress=progress,
            url=url,
            open_error_message=open_error_message,
        )
        if not request_id:
            return initial_events, False

        completion_events, succeeded = await self._finish_user_action_gate(
            request_id=request_id,
            ready_check=ready_check,
            timeout=timeout,
            ready_timeout=ready_timeout,
            timeout_error_message=timeout_error_message,
        )
        return initial_events + completion_events, succeeded

    async def _begin_user_action_gate(
        self,
        *,
        state: BrowserState,
        action_type: str,
        message: str,
        action_hint: str,
        progress: float,
        url: str | None,
        open_error_message: str,
        reason_code: str | None = None,
        blocking_url: str | None = None,
        blocking_fingerprint: str | None = None,
    ) -> tuple[list[BrowserEvent], str | None]:
        """Create and emit the waiting event before blocking on user input."""

        request_id = await self._prepare_user_action_request(
            action_type=action_type,
            message=message,
            action_hint=action_hint,
            progress=progress,
            url=url,
            reason_code=reason_code,
            blocking_url=blocking_url,
            blocking_fingerprint=blocking_fingerprint,
        )
        if not request_id:
            return [
                self._create_event(
                    BrowserState.ERROR,
                    open_error_message,
                    progress=0,
                )
            ], None

        waiting_event = self._create_event(
            state,
            message,
            progress=progress,
            requires_action=True,
            action_type=action_type,
            action_hint=action_hint,
            request_id=request_id,
        )
        return [waiting_event], request_id

    async def _finish_user_action_gate(
        self,
        *,
        request_id: str,
        ready_check: ReadyCheck,
        timeout: int = 480,
        ready_timeout: int = 120,
        timeout_error_message: str,
    ) -> tuple[list[BrowserEvent], bool]:
        """Wait for user completion after the waiting event has already streamed."""

        succeeded, resolution = await self._wait_for_user_action_completion(
            request_id=request_id,
            ready_check=ready_check,
            timeout=timeout,
            ready_timeout=ready_timeout,
        )
        if succeeded:
            return [], True

        if resolution == "skip":
            return [
                self._create_event(
                    BrowserState.ERROR,
                    "已按你的选择跳过当前平台，本轮会继续其他平台。",
                    progress=0,
                    error_type="user_skipped",
                ),
            ], False

        return [
            self._create_event(
                BrowserState.ERROR,
                timeout_error_message,
                progress=0,
                error_type=(
                    "resume_gate_failed" if resolution == "completed" else "user_action_timeout"
                ),
            ),
        ], False

    async def _begin_login_takeover_gate(
        self,
        *,
        message: str,
        action_hint: str,
        progress: float,
        url: str | None = None,
        open_error_message: str,
        reason_code: str | None = None,
        blocking_url: str | None = None,
        blocking_fingerprint: str | None = None,
    ) -> tuple[list[BrowserEvent], str | None]:
        """Emit the login waiting event immediately and return request context."""

        return await self._begin_user_action_gate(
            state=BrowserState.WAITING_FOR_LOGIN,
            action_type="login",
            message=message,
            action_hint=action_hint,
            progress=progress,
            url=url,
            open_error_message=open_error_message,
            reason_code=reason_code,
            blocking_url=blocking_url,
            blocking_fingerprint=blocking_fingerprint,
        )

    async def _finish_login_takeover_gate(
        self,
        *,
        request_id: str,
        ready_check: ReadyCheck,
        timeout: int = 480,
        ready_timeout: int = 120,
        timeout_error_message: str,
    ) -> tuple[list[BrowserEvent], bool]:
        """Complete the login waiting cycle after user action."""

        return await self._finish_user_action_gate(
            request_id=request_id,
            ready_check=ready_check,
            timeout=timeout,
            ready_timeout=ready_timeout,
            timeout_error_message=timeout_error_message,
        )

    async def _begin_modal_takeover_gate(
        self,
        *,
        message: str,
        action_hint: str,
        progress: float,
        url: str | None = None,
        open_error_message: str,
        reason_code: str | None = None,
        blocking_url: str | None = None,
        blocking_fingerprint: str | None = None,
    ) -> tuple[list[BrowserEvent], str | None]:
        """Emit the modal waiting event immediately and return request context."""

        return await self._begin_user_action_gate(
            state=BrowserState.WAITING_FOR_MODAL,
            action_type="modal",
            message=message,
            action_hint=action_hint,
            progress=progress,
            url=url,
            open_error_message=open_error_message,
            reason_code=reason_code,
            blocking_url=blocking_url,
            blocking_fingerprint=blocking_fingerprint,
        )

    async def _finish_modal_takeover_gate(
        self,
        *,
        request_id: str,
        ready_check: ReadyCheck,
        timeout: int = 480,
        ready_timeout: int = 120,
        timeout_error_message: str,
    ) -> tuple[list[BrowserEvent], bool]:
        """Complete the modal waiting cycle after user action."""

        return await self._finish_user_action_gate(
            request_id=request_id,
            ready_check=ready_check,
            timeout=timeout,
            ready_timeout=ready_timeout,
            timeout_error_message=timeout_error_message,
        )

    async def _run_login_takeover_gate(
        self,
        *,
        message: str,
        action_hint: str,
        progress: float,
        ready_check: ReadyCheck,
        url: str | None = None,
        timeout: int = 480,
        ready_timeout: int = 120,
        open_error_message: str,
        timeout_error_message: str,
    ) -> tuple[list[BrowserEvent], bool]:
        """Shared login takeover gate for AIO/local browser handlers."""

        return await self._run_user_action_gate(
            state=BrowserState.WAITING_FOR_LOGIN,
            action_type="login",
            message=message,
            action_hint=action_hint,
            progress=progress,
            url=url,
            ready_check=ready_check,
            timeout=timeout,
            ready_timeout=ready_timeout,
            open_error_message=open_error_message,
            timeout_error_message=timeout_error_message,
        )

    async def _run_modal_takeover_gate(
        self,
        *,
        message: str,
        action_hint: str,
        progress: float,
        ready_check: ReadyCheck,
        url: str | None = None,
        timeout: int = 480,
        ready_timeout: int = 120,
        open_error_message: str,
        timeout_error_message: str,
    ) -> tuple[list[BrowserEvent], bool]:
        """Shared blocking-modal takeover gate for AIO/local browser handlers."""

        return await self._run_user_action_gate(
            state=BrowserState.WAITING_FOR_MODAL,
            action_type="modal",
            message=message,
            action_hint=action_hint,
            progress=progress,
            url=url,
            ready_check=ready_check,
            timeout=timeout,
            ready_timeout=ready_timeout,
            open_error_message=open_error_message,
            timeout_error_message=timeout_error_message,
        )

    async def _build_success_result(
        self,
        *,
        question: str,
        answer_text: str,
        search_references: list[SearchReference],
        source: str,
    ) -> FetchResult:
        """Create the canonical success result and persist AIO extraction artifact."""

        fetch_result = FetchResult(
            id=f"{self.PLATFORM.value}_{hash(question)}",
            question_id="",
            question_text=question,
            platform=self.PLATFORM,
            fetch_method=FetchMethod.BROWSER,
            status="success",
            answer_text=answer_text,
            search_references=search_references,
            raw_response={"source": source},
            error_message=None,
            fetch_duration=None,
        )
        await self._persist_extraction_artifact(
            question=question,
            fetch_result=fetch_result,
            source=source,
        )
        return fetch_result

    async def _persist_extraction_artifact(
        self,
        *,
        question: str,
        fetch_result: FetchResult,
        source: str,
    ) -> None:
        """Persist the current successful extraction under the AIO run_root."""

        session_id = getattr(self.client, "aio_session_id", None)
        workspace_id = getattr(self.client, "workspace_id", None)
        task_id = getattr(self.client, "task_id", None)
        if not session_id or not workspace_id or not task_id:
            return

        try:
            runtime = await self._aio_backend.ensure_runtime(
                workspace_id=str(workspace_id),
                task_id=str(task_id),
                platform=self.PLATFORM.value,
                purpose="a4_browser",
            )
            payload = {
                "platform": self.PLATFORM.value,
                "question": question,
                "answer_text": fetch_result.answer_text,
                "references": [
                    ref.model_dump() if hasattr(ref, "model_dump") else dict(ref)
                    for ref in fetch_result.search_references
                ],
                "source": source,
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }
            await self._aio_backend.persist_extraction(runtime, payload=payload)
        except Exception as exc:
            logger.warning(
                "[%s] Failed to persist AIO extraction artifact: %s",
                self.PLATFORM_KEY,
                exc,
            )

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

        platform_name = getattr(self, "PLATFORM", self.PLATFORM_KEY)
        display_name = (
            str(platform_name.value)
            if hasattr(platform_name, "value")
            else str(platform_name)
        )
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
            return self._create_event(
                BrowserState.ERROR, "打开浏览器窗口失败，请重试", progress=0
            )

        # Wait for user to dismiss the modal
        modal_cleared = await self._wait_for_modal_clear(timeout=480)
        if not modal_cleared:
            return self._create_event(
                BrowserState.ERROR, "弹窗处理超时，请重试", progress=0
            )

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

        result_future: asyncio.Future[ParsedResponse | None] = (
            asyncio.get_running_loop().create_future()
        )
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
                if (
                    config.content_type_contains
                    and config.content_type_contains not in ct
                ):
                    return

                logger.info(
                    "[%s] Intercepted response: %s (%s)", tag, response.url[:80], ct
                )

                # Binary Connect protocol needs frame decoding
                if "connect" in ct or "grpc" in ct:
                    from app.core.fetchers.browser.parsers.connect import (
                        decode_binary_frames,
                    )

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
                logger.debug(
                    "[%s] SSE body (%d chars), first 500: %s",
                    tag,
                    len(body),
                    body[:500],
                )
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
                logger.info(
                    "[%s] Network interception success: %d chars, %d refs",
                    tag,
                    len(result.answer_text),
                    len(result.references),
                )
            else:
                logger.info(
                    "[%s] Network interception: parse_ok=%s, error=%s",
                    tag,
                    result.parse_ok if result else "None",
                    result.error if result else "timeout",
                )
            return result
        except asyncio.TimeoutError:
            logger.info(
                "[%s] Network interception timed out after %ds", tag, config.timeout
            )
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
