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
    "BrowserAgentAction",
    "BrowserAgentDecision",
    "BrowserPageObservation",
    "BrowserTakeoverNeed",
    "BrowserAgentBootstrapPolicy",
    "BrowserAgentLoopStep",
    "collect_browser_page_observation",
    "collect_browser_agent_step",
    "decide_browser_preflight",
    "observation_to_llm_json",
    "observation_to_llm_payload",
    "requires_human_takeover",
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
    "BrowserAgentAction": (
        "app.core.fetchers.browser.browser_agent_contract",
        "BrowserAgentAction",
    ),
    "BrowserAgentDecision": (
        "app.core.fetchers.browser.browser_agent_contract",
        "BrowserAgentDecision",
    ),
    "BrowserPageObservation": (
        "app.core.fetchers.browser.browser_agent_contract",
        "BrowserPageObservation",
    ),
    "BrowserTakeoverNeed": (
        "app.core.fetchers.browser.browser_agent_contract",
        "BrowserTakeoverNeed",
    ),
    "BrowserAgentBootstrapPolicy": (
        "app.core.fetchers.browser.browser_agent_loop",
        "BrowserAgentBootstrapPolicy",
    ),
    "BrowserAgentLoopStep": (
        "app.core.fetchers.browser.browser_agent_loop",
        "BrowserAgentLoopStep",
    ),
    "collect_browser_page_observation": (
        "app.core.fetchers.browser.browser_agent_contract",
        "collect_browser_page_observation",
    ),
    "collect_browser_agent_step": (
        "app.core.fetchers.browser.browser_agent_loop",
        "collect_browser_agent_step",
    ),
    "decide_browser_preflight": (
        "app.core.fetchers.browser.browser_agent_policy",
        "decide_browser_preflight",
    ),
    "observation_to_llm_json": (
        "app.core.fetchers.browser.browser_agent_contract",
        "observation_to_llm_json",
    ),
    "observation_to_llm_payload": (
        "app.core.fetchers.browser.browser_agent_contract",
        "observation_to_llm_payload",
    ),
    "requires_human_takeover": (
        "app.core.fetchers.browser.browser_agent_contract",
        "requires_human_takeover",
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
