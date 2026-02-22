"""Browser fetchers for LLM platforms."""

from app.core.fetchers.browser.agent_browser import AgentBrowserClient
from app.core.fetchers.browser.playwright_client import PlaywrightBrowserClient
from app.core.fetchers.browser.deepseek_handler import DeepSeekHandler
from app.core.fetchers.browser.kimi_handler import KimiHandler

__all__ = [
    "AgentBrowserClient",
    "PlaywrightBrowserClient",
    "DeepSeekHandler",
    "KimiHandler",
]
