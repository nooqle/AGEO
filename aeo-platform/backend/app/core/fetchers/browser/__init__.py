"""Browser fetchers for LLM platforms.

Exports stay lazy so importing one AIO/browser submodule does not eagerly import
every platform handler and recreate circular dependencies.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "AgentBrowserClient",
    "PlaywrightBrowserClient",
    "DeepSeekHandler",
    "DoubaoHandler",
    "KimiHandler",
    "YuanbaoHandler",
]

_EXPORTS: dict[str, tuple[str, str]] = {
    "AgentBrowserClient": (
        "app.core.fetchers.browser.agent_browser",
        "AgentBrowserClient",
    ),
    "PlaywrightBrowserClient": (
        "app.core.fetchers.browser.playwright_client",
        "PlaywrightBrowserClient",
    ),
    "DeepSeekHandler": (
        "app.core.fetchers.browser.deepseek_handler",
        "DeepSeekHandler",
    ),
    "DoubaoHandler": ("app.core.fetchers.browser.doubao_handler", "DoubaoHandler"),
    "KimiHandler": ("app.core.fetchers.browser.kimi_handler", "KimiHandler"),
    "YuanbaoHandler": ("app.core.fetchers.browser.yuanbao_handler", "YuanbaoHandler"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attr_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
