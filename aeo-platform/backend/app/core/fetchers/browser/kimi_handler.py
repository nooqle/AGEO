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

    # Selectors for Kimi Web UI
    # Presence of .not-login-container means the user is NOT logged in
    NOT_LOGGED_IN_SELECTOR = ".not-login-container"
    NEW_CHAT_SELECTOR = ".new-chat-btn"  # New chat button
    TEXTAREA_SELECTOR = ".chat-input-editor"  # contenteditable input div
    SEND_BUTTON_SELECTOR = ".send-button-container"  # Send button
    ANSWER_SELECTOR = ".message-list"  # Answer message list

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
            # .not-login-container present => user is NOT logged in
            not_logged_in_present = await self._check_login_status(self.NOT_LOGGED_IN_SELECTOR)
            is_logged_in = not not_logged_in_present

            if not is_logged_in:
                # Need to login
                yield self._create_event(
                    BrowserState.WAITING_FOR_LOGIN,
                    "检测到需要登录，请在浏览器窗口中完成登录",
                    progress=0.35,
                    requires_action=True,
                    action_hint="请在弹出的浏览器窗口中完成 Kimi 登录（支持手机号登录）",
                )

                # Reopen in headed mode for login
                await self.client.close()
                await self.client.open(self.URL, headed=True)

                # Wait until .not-login-container disappears (login completed)
                login_success = await self._wait_for_login_disappear(
                    self.NOT_LOGGED_IN_SELECTOR,
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

            # Step 4: Create new chat (optional but recommended)
            yield self._create_event(
                BrowserState.ENABLING_SEARCH,
                "准备新对话...",
                progress=0.5,
            )
            try:
                await self.client.find_and_click("新建对话")
                await asyncio.sleep(1)
            except Exception:
                # Might already be on a new chat
                pass

            # Step 5: Submit question
            yield self._create_event(
                BrowserState.SUBMITTING,
                f"提交问题: {question[:30]}...",
                progress=0.6,
            )

            # Fill question
            snapshot = await self.client.snapshot(interactive_only=True)
            textarea_ref = self._find_textarea_ref(snapshot)
            if textarea_ref:
                await self.client.fill(textarea_ref, question)
                await asyncio.sleep(0.5)
                await self.client.press("Enter")
            else:
                await self.client.find_and_fill("发送消息", question)
                await self.client.press("Enter")

            # Step 6: Wait for response
            yield self._create_event(
                BrowserState.WAITING_RESPONSE,
                "等待 AI 回复...",
                progress=0.7,
            )

            # Wait for response to complete using content-stability detection.
            # Polling the .loading selector is unreliable across Kimi UI versions;
            # stable content length is a platform-agnostic signal.
            await asyncio.sleep(5)  # Initial wait, give AI time to start generating
            max_wait = 120
            waited = 5
            prev_content_len = 0
            stable_count = 0
            while waited < max_wait:
                await asyncio.sleep(3)
                waited += 3
                length_result = await self.client.eval(
                    """
                    const messages = document.querySelectorAll('.message-list .markdown-body');
                    const last = messages[messages.length - 1];
                    return last ? String(last.textContent.length) : '0';
                    """
                )
                current_len = int(length_result.get("output", "0") or "0")
                if current_len > 0 and current_len == prev_content_len:
                    stable_count += 1
                    if stable_count >= 2:
                        # Content identical for two consecutive polls — generation done
                        break
                else:
                    stable_count = 0
                prev_content_len = current_len

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
            fetch_result = FetchResult(
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
                data=fetch_result,
            )

        except Exception as e:
            yield self._create_event(
                BrowserState.ERROR,
                f"抓取失败: {str(e)}",
                progress=0,
                requires_action=False,
            )

    async def _wait_for_login_disappear(
        self,
        not_logged_in_selector: str,
        timeout: int = 300,
        poll_interval: float = 2.0,
    ) -> bool:
        """Wait until the not-logged-in container disappears (login completed).

        The base class _wait_for_login waits for a selector to appear, but for
        Kimi we need the inverse: wait until .not-login-container is gone.

        Args:
            not_logged_in_selector: Selector that is present when NOT logged in
            timeout: Maximum wait time in seconds
            poll_interval: Polling interval in seconds

        Returns:
            True if login completed (selector gone)
        """
        elapsed = 0.0
        while elapsed < timeout:
            still_not_logged_in = await self._check_login_status(not_logged_in_selector)
            if not still_not_logged_in:
                return True
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        return False

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
            # Get last AI message from message list
            result = await self.client.eval(
                """
                const messages = document.querySelectorAll('.message-list .markdown-body');
                const lastMessage = messages[messages.length - 1];
                return lastMessage ? lastMessage.textContent : '';
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
        for btn_text in ["来源", "Sources", "References", "引用来源"]:
            try:
                await self.client.find_and_click(btn_text)
                await asyncio.sleep(2)
                break
            except Exception:
                continue

        # Multiple selectors tried in priority order; stop on first non-empty result
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
                            "[Kimi] Extracted %d references using selector: %s",
                            len(cleaned), selector,
                        )
                        refs = cleaned
                        break
            except Exception as e:
                logger.debug("[Kimi] Selector '%s' failed: %s", selector, e)
                continue

        if not refs:
            logger.warning("[Kimi] No references found after trying all selectors")

        return refs
