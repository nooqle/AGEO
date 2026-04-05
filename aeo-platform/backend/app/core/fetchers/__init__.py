"""Fetchers for answer fetching from public LLM platforms.

Keep package exports lazy so importing a narrow submodule such as
``app.core.fetchers.browser.aio_client`` does not eagerly pull the entire
browser handler stack and create circular-import pressure.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "DoubaoClient",
    "HunyuanClient",
    "KimiClient",
    "AgentBrowserClient",
    "DeepSeekHandler",
    "KimiHandler",
]

_EXPORTS: dict[str, tuple[str, str]] = {
    "DoubaoClient": ("app.core.fetchers.api.doubao_client", "DoubaoClient"),
    "HunyuanClient": ("app.core.fetchers.api.hunyuan_client", "HunyuanClient"),
    "KimiClient": ("app.core.fetchers.api.kimi_client", "KimiClient"),
    "AgentBrowserClient": (
        "app.core.fetchers.browser.agent_browser",
        "AgentBrowserClient",
    ),
    "DeepSeekHandler": (
        "app.core.fetchers.browser.deepseek_handler",
        "DeepSeekHandler",
    ),
    "KimiHandler": ("app.core.fetchers.browser.kimi_handler", "KimiHandler"),
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
