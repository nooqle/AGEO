"""Base browser handler for LLM platforms."""

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Union

from app.core.fetchers.browser.agent_browser import AgentBrowserClient
from app.core.fetchers.browser.playwright_client import PlaywrightBrowserClient
from app.schemas.fetch import BrowserEvent, BrowserState, FetchResult


class BaseBrowserHandler(ABC):
    """Base class for browser-based LLM handlers.

    All browser handlers should inherit from this class and implement
    the fetch method.

    Supports both AgentBrowserClient (CLI-based) and PlaywrightBrowserClient (native).
    """

    URL: str = ""  # Platform URL to be overridden by subclasses

    def __init__(self, client: Union[AgentBrowserClient, PlaywrightBrowserClient]):
        """Initialize the browser handler.

        Args:
            client: Browser client instance (AgentBrowserClient or PlaywrightBrowserClient)
        """
        self.client = client
        self._is_playwright = isinstance(client, PlaywrightBrowserClient)

    @abstractmethod
    async def fetch(self, question: str) -> AsyncGenerator[BrowserEvent, None]:
        """Fetch answer for a question.

        This method should yield BrowserEvent objects to provide
        progress updates and eventually return the result.

        Args:
            question: The question to ask

        Yields:
            BrowserEvent objects representing the current state
        """
        pass
        # Make this a generator
        yield  # type: ignore

    async def _check_login_status(self, check_selector: str) -> bool:
        """Check if user is logged in.

        Args:
            check_selector: CSS selector that indicates logged-in state

        Returns:
            True if logged in
        """
        try:
            if self._is_playwright:
                # Use a short 4-second timeout: we just need to detect presence/absence
                # of the element, not wait for a full page load.  The old 15-second
                # default wasted ~180 s per pipeline (12 questions × 15 s each).
                result = await self.client.wait(selector=check_selector, timeout=4000)
                return result.get("success", False)
            else:
                # AgentBrowser: use CLI command
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
        """Wait for user to complete login.

        Args:
            check_selector: Selector to check for login
            timeout: Maximum wait time in seconds
            poll_interval: Polling interval in seconds

        Returns:
            True if login completed
        """
        import asyncio

        elapsed = 0.0
        while elapsed < timeout:
            if await self._check_login_status(check_selector):
                return True
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        return False

    def _create_event(
        self,
        state: BrowserState,
        message: str,
        progress: float = 0,
        requires_action: bool = False,
        action_hint: str | None = None,
        data: FetchResult | None = None,
    ) -> BrowserEvent:
        """Create a browser event.

        Args:
            state: Current state
            message: Human-readable message
            progress: Progress (0-1)
            requires_action: Whether user action is required
            action_hint: Hint for user action
            data: Result data (when completed)

        Returns:
            BrowserEvent
        """
        return BrowserEvent(
            state=state,
            message=message,
            progress=progress,
            requires_action=requires_action,
            action_type=None,
            action_hint=action_hint,
            error=None,
            recoverable=True,
            data=data,
        )
