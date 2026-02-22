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
    # Verified against live DOM 2026-02-23: DeepSeek uses ds- prefixed stable classes
    # and div[role="button"] instead of <button> elements.
    LOGIN_CHECK_SELECTOR = "textarea[placeholder*='DeepSeek']"  # Exists on main chat, not on sign_in page
    TEXTAREA_SELECTOR = "textarea"  # Single textarea on page
    # No submit button selector needed — Enter key is used (more reliable than clicking)
    ANSWER_SELECTOR = "div.ds-markdown"  # Stable ds- prefixed class for AI reply content
    NEW_CHAT_SELECTOR = "div[class*='_5a8ac7a']"  # "开启新对话" button

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

            # Step 2: Navigate to page
            yield self._create_event(
                BrowserState.NAVIGATING,
                f"正在访问 {self.URL}...",
                progress=0.2,
            )
            await self.client.open(self.URL, headed=False)
            await asyncio.sleep(2)  # Wait for page load

            # Step 3: Check login status
            yield self._create_event(
                BrowserState.CHECKING_LOGIN,
                "检查登录状态...",
                progress=0.3,
            )
            is_logged_in = await self._check_login_status(self.LOGIN_CHECK_SELECTOR)

            if not is_logged_in:
                # Need to login
                yield self._create_event(
                    BrowserState.WAITING_FOR_LOGIN,
                    "检测到需要登录，请在浏览器窗口中完成登录",
                    progress=0.35,
                    requires_action=True,
                    action_hint="请在弹出的浏览器窗口中完成 DeepSeek 登录",
                )

                # Reopen in headed mode for login
                await self.client.close()
                await self.client.open(self.URL, headed=True)

                # Wait for login
                login_success = await self._wait_for_login(
                    self.LOGIN_CHECK_SELECTOR,
                    timeout=300,
                )

                if not login_success:
                    yield self._create_event(
                        BrowserState.ERROR,
                        "登录超时，请重试",
                        progress=0,
                        requires_action=False,
                    )
                    return

            # Step 4: Enable search if needed
            yield self._create_event(
                BrowserState.ENABLING_SEARCH,
                "开启联网搜索...",
                progress=0.5,
            )
            try:
                # Try to enable search toggle
                await self.client.find_and_click("联网搜索")
                await asyncio.sleep(0.5)
            except Exception:
                # Search might already be enabled or not available
                pass

            # Step 5: Submit question
            yield self._create_event(
                BrowserState.SUBMITTING,
                f"提交问题: {question[:30]}...",
                progress=0.6,
            )

            # Fill question
            snapshot = await self.client.snapshot(interactive_only=True)
            # Find textarea ref from snapshot
            textarea_ref = self._find_textarea_ref(snapshot)
            if textarea_ref:
                await self.client.fill(textarea_ref, question)
                await asyncio.sleep(0.5)
                await self.client.press("Enter")
            else:
                # Fallback: try to find and fill by role
                await self.client.find_and_fill("发送消息", question)
                await self.client.press("Enter")

            # Step 6: Wait for response
            yield self._create_event(
                BrowserState.WAITING_RESPONSE,
                "等待 AI 回复...",
                progress=0.7,
            )

            # Wait for response to complete using Playwright native selector waits.
            # Polling snapshot() is slow (full DOM scan); wait_for_selector is O(1).
            await asyncio.sleep(5)  # Initial wait, give DeepSeek time to start generating

            # DeepSeek uses div[role="button"] not <button>; use :is() to match both
            # Wait for the stop button to appear — confirms generation has started
            stop_selector = ":is(button,[role='button']):has-text('停止')"
            try:
                await self.client.page.wait_for_selector(
                    stop_selector,
                    state="visible",
                    timeout=15000,
                )
            except Exception:
                logger.debug("[DeepSeek] Stop button not detected, assuming generation started")

            # Wait for the stop button to disappear — confirms generation is done
            try:
                await self.client.page.wait_for_selector(
                    stop_selector,
                    state="hidden",
                    timeout=120000,
                )
                logger.debug("[DeepSeek] Generation complete (stop button disappeared)")
            except Exception:
                logger.warning("[DeepSeek] Stop button wait timed out after 120s, proceeding anyway")

            await asyncio.sleep(2)  # Extra wait for content to fully render

            # Step 7: Extract answer
            yield self._create_event(
                BrowserState.EXTRACTING,
                "提取回答内容...",
                progress=0.9,
            )

            # Get answer text
            answer_text = await self._extract_answer()

            # Get search references
            search_refs = await self._extract_references()

            # Create result
            result = FetchResult(
                id=f"{self.PLATFORM.value}_{hash(question)}",
                question_id="",  # Will be set by caller
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

    def _find_textarea_ref(self, snapshot: dict) -> str | None:
        """Find textarea reference from snapshot.

        Args:
            snapshot: Page snapshot

        Returns:
            Reference string or None
        """
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

        Returns:
            Answer text
        """
        try:
            # div.ds-markdown is the stable DS design-system class for AI response content
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
        silent failures. All errors are logged rather than swallowed.

        Returns:
            List of search references
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

        # Multiple selectors tried in priority order; stop on first non-empty result
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
                        # Filter out non-navigable URLs
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
            logger.warning("[DeepSeek] No references found after trying all selectors")

        return refs
