"""Browser fetchers for LLM platforms."""

from app.core.fetchers.browser.agent_browser import AgentBrowserClient
from app.core.fetchers.browser.playwright_client import PlaywrightBrowserClient
from app.core.fetchers.browser.deepseek_handler import DeepSeekHandler
from app.core.fetchers.browser.doubao_handler import DoubaoHandler
from app.core.fetchers.browser.kimi_handler import KimiHandler
from app.core.fetchers.browser.yuanbao_handler import YuanbaoHandler

__all__ = [
    "AgentBrowserClient",
    "PlaywrightBrowserClient",
    "DeepSeekHandler",
    "DoubaoHandler",
    "KimiHandler",
    "YuanbaoHandler",
]
