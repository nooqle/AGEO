"""Qwen web collector with authenticated-session and search-evidence gates."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import AsyncGenerator
from urllib.parse import urlparse

from app.core.fetchers.browser.base_handler import BaseBrowserHandler
from app.core.fetchers.browser.browser_executor import (
    BrowserAnswerExecutionPlan,
    execute_post_submit_capture_flow,
)
from app.schemas.fetch import BrowserState, FetchMethod, FetchResult, Platform

logger = logging.getLogger(__name__)


class QwenSearchNotVerified(Exception):
    error_type = "search_not_verified"
    user_message = "千问本次回答未显示可核验的联网资料，已停止采集"


class QwenHandler(BaseBrowserHandler):
    URL = "https://www.qianwen.com/"
    PLATFORM = Platform.QWEN
    PLATFORM_KEY = "qwen"
    BROWSER_READY_URL_PATTERNS = ("qwen.com", "qianwen.com")
    BROWSER_LOGIN_URL_PATTERNS = ("login", "signin", "auth")
    BROWSER_LOGIN_HINTS = ("登录", "扫码", "验证码", "手机号", "Qwen App")
    BROWSER_LATE_BLOCKER_HINTS = ("登录", "验证码", "安全验证")

    _DEFAULTS = {
        "input": "[contenteditable='true'][role='textbox'], textarea, [contenteditable='true']",
        "new_chat": "[data-session-switch-target='new-chat'], a[href='/'], button[aria-label*='新建'], button[aria-label*='New chat']",
        "content": [
            ".qk-markdown-react",
            "[data-testid='message-content']",
            "[class*='assistant'] [class*='markdown']",
            "[class*='assistant'] [class*='message']",
        ],
        "account_marker": (
            "button[aria-haspopup='menu']:has(img), "
            "header [data-testid='user-avatar'], "
            "header button[aria-label*='个人'], "
            "header button[aria-label*='账号'], "
            "nav [data-testid='user-avatar']"
        ),
        "citation_strip": "[class*='cite'], [class*='citation'], sup",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._search_evidence: dict = {}

    async def _authenticated(self) -> bool:
        page = self.client.page
        host = urlparse(page.url).hostname if page is not None else None
        if host not in {"qwen.com", "qianwen.com"} and not (
            (host or "").endswith(".qwen.com") or (host or "").endswith(".qianwen.com")
        ):
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

    async def _verify_search_evidence(self) -> None:
        """Require search status plus source cards from this conversation."""

        page = self.client.page
        if page is None:
            raise QwenSearchNotVerified()
        try:
            cards = page.locator('[data-c="refer_panel"][data-d="card"]')
            if not await cards.count():
                source_count = page.get_by_text(re.compile(r"\d+篇来源$"))
                if await source_count.count() and await source_count.last.is_visible():
                    await source_count.last.click(timeout=5000)
                    await cards.first.wait_for(timeout=5000)
            response = await self.client.eval(
                """() => {
                    const match = document.body.innerText.match(/搜索\\s+(\\d+)\\s+个关键词，参考\\s+(\\d+)\\s+篇资料/);
                    const cards = [...document.querySelectorAll('[data-c="refer_panel"][data-d="card"]')];
                    const sources = cards.map(card => {
                        try {
                            const item = JSON.parse(card.getAttribute('data-click-extra') || '{}');
                            return {index: Number(item.refer_num), title: item.title || '', url: item.url || ''};
                        } catch { return null; }
                    }).filter(Boolean);
                    return JSON.stringify({query_count: match ? Number(match[1]) : 0,
                        source_count: match ? Number(match[2]) : 0, retrieved_sources: sources});
                }"""
            )
            evidence = json.loads(response.get("output", "{}") or "{}")
            sources = []
            seen = set()
            for item in evidence.get("retrieved_sources", []):
                url = str(item.get("url") or "")
                if urlparse(url).scheme not in {"http", "https"} or url in seen:
                    continue
                seen.add(url)
                sources.append(
                    {
                        "index": item.get("index"),
                        "title": str(item.get("title") or "")[:200],
                        "url": url,
                    }
                )
            if (
                evidence.get("query_count", 0) < 1
                or evidence.get("source_count", 0) < 1
                or not sources
            ):
                raise QwenSearchNotVerified()
            self._search_evidence = {
                "web_search_executed": True,
                "query_count": evidence["query_count"],
                "source_count": evidence["source_count"],
                "retrieved_sources": sources,
                "reference_scope": "retrieved_search_results",
            }
        except Exception as exc:
            if not isinstance(exc, QwenSearchNotVerified):
                logger.warning("[Qwen] Search evidence check failed: %s", exc)
            raise QwenSearchNotVerified() from exc

    async def _build_success_result(
        self, *, question: str, answer_text: str, search_references: list, source: str
    ) -> FetchResult:
        result = FetchResult(
            id=f"{self.PLATFORM.value}_{hash(question)}",
            question_id="",
            question_text=question,
            platform=self.PLATFORM,
            fetch_method=FetchMethod.BROWSER,
            status="success",
            answer_text=answer_text,
            search_references=search_references,
            raw_response={"source": source, **self._search_evidence},
        )
        await self._persist_extraction_artifact(
            question=question, fetch_result=result, source=source
        )
        return result

    async def fetch(self, question: str) -> AsyncGenerator:
        self._refresh_selectors()
        self._search_evidence = {}
        try:
            yield self._create_event(
                BrowserState.INITIALIZING, "初始化千问浏览器", progress=0.1
            )
            result = await self.client.open(self.URL, headed=self.headed)
            if not result.get("success"):
                yield self._create_event(
                    BrowserState.ERROR, "千问页面打开失败", progress=0
                )
                return
            await asyncio.sleep(2)

            if not await self._authenticated():
                events, request_id = await self._begin_login_takeover_gate(
                    message="千问需要登录后才能采集，请在浏览器中完成登录",
                    action_hint="在千问页面扫码或使用手机号登录，完成后点击我已完成",
                    progress=0.25,
                    url=self.URL,
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
                        progress=0,
                        error_type="login_not_verified",
                    )
                    return

            preflight_events, abort = await self._run_browser_agent_preflight(
                progress=0.35,
                url=self.URL,
            )
            for event in preflight_events:
                yield event
            if abort or not await self._authenticated():
                if not abort:
                    yield self._create_event(
                        BrowserState.ERROR, "千问登录状态已失效", progress=0
                    )
                return

            page = self.client.page
            if page is None:
                yield self._create_event(
                    BrowserState.ERROR, "千问页面不可用", progress=0
                )
                return
            new_chat = page.locator(self._sel("new_chat")).first
            if await new_chat.count() and await new_chat.is_visible():
                await new_chat.click(timeout=5000)
            if not await self._authenticated():
                yield self._create_event(
                    BrowserState.ERROR, "千问新对话后登录状态未确认", progress=0
                )
                return
            editor = page.locator(self._sel("input")).first
            if not await editor.count() or not await editor.is_visible():
                yield self._create_event(
                    BrowserState.ERROR, "千问输入框不可用", progress=0
                )
                return
            await editor.fill(question)
            await editor.press("Enter")
            yield self._create_event(
                BrowserState.WAITING_RESPONSE, "等待千问回答", progress=0.7
            )
            fetch_result, events = await execute_post_submit_capture_flow(
                self,
                BrowserAnswerExecutionPlan(
                    question=question,
                    intercept_task=None,
                    fallback_url=self.URL,
                    max_wait=90,
                    poll_interval=3,
                    min_content_len=40,
                    stable_rounds=2,
                    blocker_check_after_seconds=9,
                    dump_keywords=["assistant", "markdown"],
                    before_dom_extract=self._verify_search_evidence,
                    extract_references=self._extract_cited_references,
                ),
            )
            for event in events:
                yield event
            if fetch_result is None:
                return
            yield self._create_event(
                BrowserState.COMPLETED, "千问抓取完成", progress=1.0, data=fetch_result
            )
        except Exception as exc:
            logger.warning("[Qwen] Browser collection failed: %s", exc)
            yield self._create_event(
                BrowserState.ERROR, f"千问抓取失败: {exc}", progress=0
            )

    async def _extract_cited_references(self) -> list:
        # The source panel lists retrieved candidates, not answer-level citations.
        return []
