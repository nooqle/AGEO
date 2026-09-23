"""Qwen web collector with an explicit authenticated-session gate.

The selectors are intentionally conservative until a logged-in qwen.com
surface can be checked in a live AIO sandbox. Anonymous chat is not accepted.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator
from urllib.parse import urlparse

from app.core.fetchers.browser.base_handler import BaseBrowserHandler
from app.core.fetchers.browser.browser_executor import (
    BrowserAnswerExecutionPlan,
    execute_post_submit_capture_flow,
)
from app.schemas.fetch import BrowserState, Platform

logger = logging.getLogger(__name__)


class QwenHandler(BaseBrowserHandler):
    URL = "https://www.qwen.com/"
    PLATFORM = Platform.QWEN
    PLATFORM_KEY = "qwen"
    BROWSER_READY_URL_PATTERNS = ("qwen.com",)
    BROWSER_LOGIN_URL_PATTERNS = ("login", "signin", "auth")
    BROWSER_LOGIN_HINTS = ("登录", "扫码", "验证码", "手机号", "Qwen App")
    BROWSER_LATE_BLOCKER_HINTS = ("登录", "验证码", "安全验证")

    _DEFAULTS = {
        "input": "[contenteditable='true'][role='textbox'], textarea, [contenteditable='true']",
        "new_chat": "a[href='/'], button[aria-label*='新建'], button[aria-label*='New chat']",
        "content": [
            "[data-testid='message-content']",
            "[class*='assistant'] [class*='markdown']",
            "[class*='assistant'] [class*='message']",
        ],
        "account_marker": (
            "header [data-testid='user-avatar'], "
            "header button[aria-label*='个人'], "
            "header button[aria-label*='账号'], "
            "nav [data-testid='user-avatar']"
        ),
        "search_button": "button:has-text('联网搜索'), button:has-text('Web Search')",
        "reference_links": [
            "[class*='source'] a[href^='http']",
            "[class*='reference'] a[href^='http']",
        ],
        "citation_strip": "[class*='cite'], [class*='citation'], sup",
        "reference_expand_texts": ["来源", "引用", "Sources"],
    }

    async def _authenticated(self) -> bool:
        page = self.client.page
        host = urlparse(page.url).hostname if page is not None else None
        if host != "qwen.com" and not (host or "").endswith(".qwen.com"):
            return False
        try:
            marker = page.locator(self._sel("account_marker"))
            if not await marker.count() or not await marker.first.is_visible():
                return False
            login = page.get_by_role("button", name="登录", exact=True)
            return not (await login.count() and await login.first.is_visible())
        except Exception:
            return False

    async def probe_takeover_ready(self, action_type: str) -> bool:
        if action_type == "login":
            return await self._authenticated()
        return await super().probe_takeover_ready(action_type)

    async def _ensure_search_enabled(self) -> bool:
        page = self.client.page
        if page is None:
            return False
        try:
            button = page.locator(self._sel("search_button")).first
            if not await button.count() or not await button.is_visible():
                return False
            pressed = await button.get_attribute("aria-pressed")
            state = await button.get_attribute("data-state")
            if pressed == "true" or state in {"on", "active", "checked"}:
                return True
            await button.click(timeout=5000)
            pressed = await button.get_attribute("aria-pressed")
            state = await button.get_attribute("data-state")
            return pressed == "true" or state in {"on", "active", "checked"}
        except Exception as exc:
            logger.warning("[Qwen] Search control check failed: %s", exc)
            return False

    async def fetch(self, question: str) -> AsyncGenerator:
        self._refresh_selectors()
        try:
            yield self._create_event(BrowserState.INITIALIZING, "初始化千问浏览器", progress=0.1)
            result = await self.client.open(self.URL, headed=self.headed)
            if not result.get("success"):
                yield self._create_event(BrowserState.ERROR, "千问页面打开失败", progress=0)
                return
            await asyncio.sleep(2)

            if not await self._authenticated():
                events, request_id = await self._begin_login_takeover_gate(
                    message="千问需要登录后才能采集，请在浏览器中完成登录",
                    action_hint="在千问页面扫码或使用手机号登录，完成后点击我已完成",
                    progress=0.25, url=self.URL,
                    open_error_message="千问登录接管窗口无法打开",
                )
                for event in events:
                    yield event
                if not request_id:
                    return
                events, completed = await self._finish_login_takeover_gate(
                    request_id=request_id,
                    ready_check=lambda _: self._authenticated(),
                    timeout_error_message="千问登录等待超时",
                )
                for event in events:
                    yield event
                if not completed:
                    return
                if not await self._authenticated():
                    yield self._create_event(
                        BrowserState.ERROR,
                        "未检测到千问已登录账号，请完成登录后重试",
                        progress=0, error_type="login_not_verified",
                    )
                    return

            preflight_events, abort = await self._run_browser_agent_preflight(
                progress=0.35, url=self.URL,
            )
            for event in preflight_events:
                yield event
            if abort or not await self._authenticated():
                if not abort:
                    yield self._create_event(BrowserState.ERROR, "千问登录状态已失效", progress=0)
                return

            page = self.client.page
            if page is None:
                yield self._create_event(BrowserState.ERROR, "千问页面不可用", progress=0)
                return
            new_chat = page.locator(self._sel("new_chat")).first
            if await new_chat.count() and await new_chat.is_visible():
                await new_chat.click(timeout=5000)
            if not await self._authenticated():
                yield self._create_event(BrowserState.ERROR, "千问新对话后登录状态未确认", progress=0)
                return
            if not await self._ensure_search_enabled():
                yield self._create_event(
                    BrowserState.ERROR, "千问联网搜索未确认开启，已停止采集",
                    progress=0, error_type="search_not_verified",
                )
                return
            editor = page.locator(self._sel("input")).first
            if not await editor.count() or not await editor.is_visible():
                yield self._create_event(BrowserState.ERROR, "千问输入框不可用", progress=0)
                return
            await editor.fill(question)
            await editor.press("Enter")
            yield self._create_event(BrowserState.WAITING_RESPONSE, "等待千问回答", progress=0.7)
            fetch_result, events = await execute_post_submit_capture_flow(
                self,
                BrowserAnswerExecutionPlan(
                    question=question, intercept_task=None, fallback_url=self.URL,
                    max_wait=90, poll_interval=3, min_content_len=40,
                    stable_rounds=2, blocker_check_after_seconds=9,
                    dump_keywords=["assistant", "markdown"],
                ),
            )
            for event in events:
                yield event
            if fetch_result is None:
                return
            yield self._create_event(BrowserState.COMPLETED, "千问抓取完成", progress=1.0, data=fetch_result)
        except Exception as exc:
            logger.warning("[Qwen] Browser collection failed: %s", exc)
            yield self._create_event(BrowserState.ERROR, f"千问抓取失败: {exc}", progress=0)
