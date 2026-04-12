"""Loop helpers for pluggable Browser Agent policy execution."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.fetchers.browser.browser_agent_contract import (
    BrowserAgentDecision,
    BrowserPageObservation,
    ScreenshotProvider,
    collect_browser_page_observation,
)
from app.core.fetchers.browser.browser_agent_policy import decide_browser_preflight


class BrowserAgentPolicy(Protocol):
    def decide(
        self,
        observation: BrowserPageObservation,
        *,
        target_url: str | None = None,
    ) -> BrowserAgentDecision | Any: ...


@dataclass(frozen=True, slots=True)
class BrowserAgentLoopStep:
    observation: BrowserPageObservation
    decision: BrowserAgentDecision


class BrowserAgentBootstrapPolicy:
    """Current default policy.

    This is intentionally deterministic and small. The important part is that
    handlers no longer call policy logic directly. A future LLM-driven browser
    agent can replace this object without changing handler flow.
    """

    def decide(
        self,
        observation: BrowserPageObservation,
        *,
        target_url: str | None = None,
    ) -> BrowserAgentDecision:
        return decide_browser_preflight(observation, target_url=target_url)


async def collect_browser_agent_step(
    *,
    client: Any,
    platform: str,
    target_url: str | None = None,
    screenshot_provider: ScreenshotProvider | None = None,
    policy: BrowserAgentPolicy | None = None,
) -> BrowserAgentLoopStep:
    observation = await collect_browser_page_observation(
        client=client,
        platform=platform,
        screenshot_provider=screenshot_provider,
    )
    active_policy = policy or BrowserAgentBootstrapPolicy()
    decision = active_policy.decide(observation, target_url=target_url)
    if inspect.isawaitable(decision):
        decision = await decision
    return BrowserAgentLoopStep(
        observation=observation,
        decision=decision,
    )
