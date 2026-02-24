"""Playwright-based browser client for fetch agent.

Replaces agent-browser CLI with native Playwright implementation.
Supports Windows, Linux, and macOS.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright, Page, BrowserContext

from app.core.playwright_installer import ensure_playwright_ready

logger = logging.getLogger(__name__)

# Persistent browser session storage: ~/.specta/browser_sessions/<name>/
# Cookies and localStorage survive across backend restarts so users only
# need to log in to Kimi / DeepSeek once per machine.
_SESSION_BASE_DIR = Path.home() / ".specta" / "browser_sessions"


class PlaywrightBrowserClient:
    """Browser client using Playwright directly with persistent sessions.

    Provides similar interface to AgentBrowserClient but uses
    Playwright Python API instead of CLI.  Browser cookies and
    localStorage are stored in ~/.specta/browser_sessions/<session_name>/
    so login state is preserved across runs.
    """

    def __init__(self, session_name: str = "default"):
        """Initialize the browser client.

        Args:
            session_name: Session name — maps to a persistent user-data
                directory so cookies survive backend restarts.
        """
        self.session_name = session_name
        self.user_data_dir = _SESSION_BASE_DIR / session_name
        self.playwright = None
        # With launch_persistent_context there is no separate Browser object;
        # the context IS the browser.
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def _ensure_playwright(self):
        """Ensure playwright is initialized and browser is installed."""
        if self.playwright is None:
            # 首先确保浏览器已安装
            if not await ensure_playwright_ready():
                raise RuntimeError(
                    "Playwright 浏览器未安装。请运行: python -m playwright install chromium"
                )

            self.playwright = await async_playwright().start()

    async def open(self, url: str, headed: bool = False) -> dict[str, Any]:
        """Open a URL in the browser.

        Args:
            url: URL to open
            headed: Whether to show the browser window

        Returns:
            Command output
        """
        try:
            await self._ensure_playwright()

            if self.context is None and self.playwright is not None:
                # Ensure the user-data directory exists before launching.
                self.user_data_dir.mkdir(parents=True, exist_ok=True)

                # launch_persistent_context saves cookies, localStorage, etc.
                # to user_data_dir so login sessions survive backend restarts.
                self.context = await self.playwright.chromium.launch_persistent_context(
                    str(self.user_data_dir),
                    headless=not headed,
                    args=["--disable-blink-features=AutomationControlled"],
                    viewport={"width": 1280, "height": 720},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                )
                logger.info(
                    "[Browser] Launched persistent context for '%s' (headless=%s, dir=%s)",
                    self.session_name, not headed, self.user_data_dir,
                )

            if self.page is None and self.context is not None:
                # Reuse the first existing page if present (persistent context
                # may restore previous tabs), otherwise open a fresh one.
                if self.context.pages:
                    self.page = self.context.pages[0]
                else:
                    self.page = await self.context.new_page()

            if self.page is not None:
                # domcontentloaded fires once DOM is parsed; networkidle may never
                # fire in SPAs with background heartbeat requests.
                await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)

            return {"success": True, "url": url}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def snapshot(self, interactive_only: bool = True) -> dict[str, Any]:
        """Get a snapshot of the current page.

        Args:
            interactive_only: Only show interactive elements

        Returns:
            Snapshot data with element references
        """
        try:
            if self.page is None:
                return {"error": "Page not opened"}

            # Get all interactive elements
            elements = await self.page.query_selector_all(
                "button, input, textarea, a, [role='button'], [role='textbox']"
            )

            refs = {}
            for idx, element in enumerate(elements):
                ref_id = f"e{idx}"
                try:
                    role = await element.get_attribute("role") or ""
                    tag = await element.evaluate("el => el.tagName.toLowerCase()")
                    text = await element.inner_text()
                    placeholder = await element.get_attribute("placeholder") or ""
                    if not role:
                        if tag in {"input", "textarea"}:
                            role = "textbox"
                        elif tag == "button":
                            role = "button"
                        elif tag == "a":
                            role = "link"

                    refs[ref_id] = {
                        "role": role or tag,
                        "tag": tag,
                        "text": text[:100] if text else "",
                        "placeholder": placeholder,
                    }
                except Exception:
                    pass

            return {"refs": refs, "url": self.page.url}
        except Exception as e:
            return {"error": str(e)}

    async def click(self, ref: str) -> dict[str, Any]:
        """Click an element.

        Args:
            ref: Element reference (e.g., @e1) or text to find

        Returns:
            Command output
        """
        try:
            if self.page is None:
                return {"error": "Page not opened"}

            # Handle @ref format
            if ref.startswith("@"):
                ref_id = ref[1:]
                # Find by index
                elements = await self.page.query_selector_all(
                    "button, input, textarea, a, [role='button'], [role='textbox']"
                )
                idx = int(ref_id.replace("e", ""))
                if idx < len(elements):
                    await elements[idx].click()
                    return {"success": True}
                else:
                    return {"error": f"Element {ref} not found"}
            else:
                # Try to find by text
                element = self.page.get_by_text(ref).first
                if element:
                    await element.click()
                    return {"success": True}
                else:
                    return {"error": f"Element with text '{ref}' not found"}
        except Exception as e:
            return {"error": str(e)}

    async def fill(self, ref: str, text: str) -> dict[str, Any]:
        """Fill an input field.

        Args:
            ref: Element reference
            text: Text to fill

        Returns:
            Command output
        """
        try:
            if self.page is None:
                return {"error": "Page not opened"}

            # Handle @ref format
            if ref.startswith("@"):
                ref_id = ref[1:]
                # IMPORTANT: use same selector as snapshot() so index N in @eN
                # maps to the same element in both calls.
                elements = await self.page.query_selector_all(
                    "button, input, textarea, a, [role='button'], [role='textbox']"
                )
                idx = int(ref_id.replace("e", ""))
                if idx < len(elements):
                    element = elements[idx]
                    is_contenteditable = await element.evaluate(
                        "el => el.isContentEditable"
                    )
                    if is_contenteditable:
                        # contenteditable divs (e.g. Kimi chat input) need real
                        # keyboard events so React's synthetic event system fires.
                        await element.click()
                        await self.page.keyboard.press("Control+a")
                        await self.page.keyboard.type(text)
                    else:
                        await element.fill(text)
                    return {"success": True}
                else:
                    return {"error": f"Element {ref} not found"}
            else:
                # Try to find by placeholder or label
                element = self.page.get_by_placeholder(ref).first
                if not element:
                    element = self.page.get_by_label(ref).first
                if element:
                    await element.fill(text)
                    return {"success": True}
                else:
                    return {"error": f"Input '{ref}' not found"}
        except Exception as e:
            return {"error": str(e)}

    async def get_text(self, selector: str) -> dict[str, Any]:
        """Get text content of an element.

        Args:
            selector: CSS selector

        Returns:
            Text content
        """
        try:
            if self.page is None:
                return {"error": "Page not opened"}

            element = await self.page.query_selector(selector)
            if element:
                text = await element.inner_text()
                return {"output": text}
            else:
                return {"error": f"Element '{selector}' not found"}
        except Exception as e:
            return {"error": str(e)}

    async def wait(
        self,
        ms: int | None = None,
        text: str | None = None,
        selector: str | None = None,
        timeout: int = 15000,
    ) -> dict[str, Any]:
        """Wait for a condition.

        Args:
            ms: Milliseconds to wait
            text: Text to wait for
            selector: Selector to wait for
            timeout: Selector wait timeout in milliseconds (default 15000)

        Returns:
            Command output
        """
        try:
            if self.page is None:
                return {"error": "Page not opened"}

            if ms is not None:
                await asyncio.sleep(ms / 1000)
                return {"success": True}

            if text:
                await self.page.wait_for_selector(f"text={text}", timeout=timeout)
                return {"success": True}

            if selector:
                await self.page.wait_for_selector(selector, timeout=timeout)
                return {"success": True}

            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    async def find_and_click(self, text: str) -> dict[str, Any]:
        """Find element by text and click.

        Args:
            text: Text to find

        Returns:
            Command output
        """
        if self.page is None:
            return {"error": "Page not opened"}

        # Playwright Locators are always truthy; use count() to check existence.
        for locator in [
            self.page.get_by_text(text, exact=False),
            self.page.get_by_role("button", name=text),
        ]:
            try:
                if await locator.count() > 0:
                    await locator.first.click()
                    return {"success": True}
            except Exception:
                continue

        return {"error": f"Element with text '{text}' not found"}

    async def find_and_fill(self, label: str, text: str) -> dict[str, Any]:
        """Find input by label/placeholder and fill.

        Args:
            label: Label or placeholder text
            text: Text to fill

        Returns:
            Command output
        """
        if self.page is None:
            return {"error": "Page not opened"}

        # Playwright Locators are always truthy; use count() to check existence.
        for locator in [
            self.page.get_by_placeholder(label),
            self.page.get_by_label(label),
            self.page.get_by_role("textbox", name=label),
        ]:
            try:
                if await locator.count() > 0:
                    await locator.first.fill(text)
                    return {"success": True}
            except Exception:
                continue

        return {"error": f"Input '{label}' not found"}

    async def press(self, key: str) -> dict[str, Any]:
        """Press a key.

        Args:
            key: Key to press (e.g., "Enter", "Tab")

        Returns:
            Command output
        """
        try:
            if self.page is None:
                return {"error": "Page not opened"}

            await self.page.keyboard.press(key)
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    async def eval(self, script: str) -> dict[str, Any]:
        """Execute JavaScript in the page.

        Args:
            script: JavaScript code (must be a function expression like
                ``() => { ... }`` or a simple expression; bare ``return``
                statements outside a function cause a SyntaxError).

        Returns:
            Script output
        """
        try:
            if self.page is None:
                return {"error": "Page not opened"}

            result = await self.page.evaluate(script)
            return {"output": str(result) if result is not None else ""}
        except Exception as e:
            logger.warning("[Browser] eval() failed: %s | script: %.120s", e, script.strip())
            return {"error": str(e)}

    async def close(self) -> dict[str, Any]:
        """Close the browser.

        Returns:
            Command output
        """
        try:
            if self.page:
                await self.page.close()
                self.page = None

            if self.context:
                # Closing the persistent context flushes cookies/storage to
                # disk and terminates the browser process.
                await self.context.close()
                self.context = None

            if self.playwright:
                await self.playwright.stop()
                self.playwright = None

            return {"success": True}
        except Exception as e:
            return {"error": str(e)}

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
