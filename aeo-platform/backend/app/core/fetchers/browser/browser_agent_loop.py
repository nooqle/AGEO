"""Loop helpers for pluggable Browser Agent policy execution."""

from __future__ import annotations

import inspect
import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from app.config import get_settings
from app.core.llm import get_llm_model
from app.core.fetchers.browser.browser_agent_contract import (
    BrowserAgentAction,
    BrowserAgentDecision,
    BrowserAgentLoopContext,
    BrowserPageObservation,
    BrowserTakeoverNeed,
    ScreenshotProvider,
    collect_browser_page_observation,
    loop_context_to_llm_payload,
    observation_to_llm_payload,
)
from app.core.fetchers.browser.browser_agent_policy import decide_browser_preflight

logger = logging.getLogger(__name__)


class BrowserAgentPolicy(Protocol):
    def decide(
        self,
        observation: BrowserPageObservation,
        *,
        loop_context: BrowserAgentLoopContext,
    ) -> BrowserAgentDecision | Any: ...


@dataclass(frozen=True, slots=True)
class BrowserAgentLoopStep:
    loop_context: BrowserAgentLoopContext
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
        loop_context: BrowserAgentLoopContext,
    ) -> BrowserAgentDecision:
        return decide_browser_preflight(
            observation,
            target_url=loop_context.target_url,
        )


def _extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = str(text or "").strip()
    if not stripped:
        return None
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        last_fence = stripped.rfind("```")
        if first_newline != -1 and last_fence > first_newline:
            stripped = stripped[first_newline + 1 : last_fence].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _parse_llm_decision(payload: dict[str, Any]) -> BrowserAgentDecision | None:
    outcome = str(payload.get("outcome") or "").strip()
    blocker_kind = str(payload.get("blocker_kind") or "none").strip()
    if outcome not in {"continue", "takeover_required", "completed", "failed"}:
        return None

    actions: list[BrowserAgentAction] = []
    raw_actions = payload.get("actions")
    if isinstance(raw_actions, list):
        for item in raw_actions[:3]:
            if not isinstance(item, dict):
                continue
            action_type = str(item.get("action_type") or "").strip()
            if action_type not in {
                "click_ref",
                "fill_ref",
                "press_key",
                "wait",
                "navigate",
                "refresh",
                "close_popup",
                "complete",
                "handoff",
            }:
                continue
            actions.append(
                BrowserAgentAction(
                    action_type=action_type,
                    ref=item.get("ref"),
                    text=item.get("text"),
                    key=item.get("key"),
                    target_url=item.get("target_url"),
                    wait_seconds=item.get("wait_seconds"),
                    reason=item.get("reason"),
                )
            )

    takeover = None
    raw_takeover = payload.get("takeover")
    if isinstance(raw_takeover, dict):
        takeover = BrowserTakeoverNeed(
            blocker_kind=str(raw_takeover.get("blocker_kind") or blocker_kind or "unknown"),
            reason_code=str(raw_takeover.get("reason_code") or "browser_agent_takeover"),
            message=str(raw_takeover.get("message") or "browser agent takeover required"),
            target_url=raw_takeover.get("target_url"),
            resume_expectation=str(
                raw_takeover.get("resume_expectation") or "manual_resume_gate"
            ),
        )

    try:
        confidence = float(payload.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0

    return BrowserAgentDecision(
        outcome=outcome,
        actions=tuple(actions),
        blocker_kind=blocker_kind or "none",
        rationale=str(payload.get("rationale") or "").strip(),
        confidence=max(0.0, min(confidence, 1.0)),
        takeover=takeover,
        error=str(payload.get("error") or "").strip() or None,
    )


class LLMBrowserAgentPolicy:
    """Optional LLM-backed browser policy.

    This policy is intentionally conservative:
    1. it runs only after deterministic bootstrap returns "no blocker"
    2. it can only emit the shared BrowserAgentDecision contract
    3. invalid or low-confidence output falls back to the deterministic path
    """

    def __init__(self, *, min_confidence: float = 0.55):
        self._min_confidence = min_confidence

    async def decide(
        self,
        observation: BrowserPageObservation,
        *,
        loop_context: BrowserAgentLoopContext,
    ) -> BrowserAgentDecision | None:
        model = get_llm_model()
        prompt = (
            "你是浏览器执行代理。"
            "请基于给定的页面观测，判断当前是否需要继续自动操作、交给人工接管、或保持继续。"
            "只能输出 JSON 对象，不要输出解释。"
            "可用 outcome: continue/takeover_required/completed/failed。"
            "可用 blocker_kind: none/login/verification/captcha/security_confirmation/"
            "account_selection/consent_modal/popup/blank_page/navigation_error/rate_limit/"
            "target_closed/unknown。"
            "如果给出 actions，只能使用 click_ref/fill_ref/press_key/wait/navigate/refresh/"
            "close_popup/complete/handoff。"
            "当缺少足够把握时，返回 outcome=continue、blocker_kind=none、actions=[]。"
        )
        response = await model.async_call(
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "loop_context": loop_context_to_llm_payload(loop_context),
                            "observation": observation_to_llm_payload(observation),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                },
            ],
            temperature=0.1,
            max_tokens=1200,
        )
        payload = _extract_json_object(response.content)
        if not payload:
            logger.warning("[BrowserAgentLoop] LLM policy returned non-JSON content")
            return None
        decision = _parse_llm_decision(payload)
        if decision is None:
            logger.warning("[BrowserAgentLoop] LLM policy returned invalid decision")
            return None
        if decision.confidence < self._min_confidence:
            logger.info(
                "[BrowserAgentLoop] Ignoring low-confidence LLM browser decision: %.2f",
                decision.confidence,
            )
            return None
        return decision


class HybridBrowserAgentPolicy:
    """Deterministic bootstrap first, optional LLM second."""

    def __init__(
        self,
        *,
        bootstrap_policy: BrowserAgentPolicy | None = None,
        llm_policy: BrowserAgentPolicy | None = None,
    ):
        self._bootstrap_policy = bootstrap_policy or BrowserAgentBootstrapPolicy()
        self._llm_policy = llm_policy

    async def decide(
        self,
        observation: BrowserPageObservation,
        *,
        loop_context: BrowserAgentLoopContext,
    ) -> BrowserAgentDecision:
        bootstrap = self._bootstrap_policy.decide(
            observation,
            loop_context=loop_context,
        )
        if inspect.isawaitable(bootstrap):
            bootstrap = await bootstrap
        if (
            bootstrap.outcome != "continue"
            or bootstrap.actions
            or bootstrap.blocker_kind != "none"
            or self._llm_policy is None
        ):
            return bootstrap

        llm_decision = self._llm_policy.decide(
            observation,
            loop_context=loop_context,
        )
        if inspect.isawaitable(llm_decision):
            llm_decision = await llm_decision
        return llm_decision or bootstrap


def build_default_browser_agent_policy() -> BrowserAgentPolicy:
    settings = get_settings()
    if bool(getattr(settings, "BROWSER_AGENT_LLM_ENABLED", False)):
        return HybridBrowserAgentPolicy(
            llm_policy=LLMBrowserAgentPolicy(),
        )
    return BrowserAgentBootstrapPolicy()


async def collect_browser_agent_step(
    *,
    client: Any,
    platform: str,
    loop_context: BrowserAgentLoopContext,
    target_url: str | None = None,
    screenshot_provider: ScreenshotProvider | None = None,
    policy: BrowserAgentPolicy | None = None,
) -> BrowserAgentLoopStep:
    observation = await collect_browser_page_observation(
        client=client,
        platform=platform,
        screenshot_provider=screenshot_provider,
    )
    effective_loop_context = BrowserAgentLoopContext(
        platform=loop_context.platform,
        stage=loop_context.stage,
        target_url=loop_context.target_url or target_url,
        note=loop_context.note,
        meta=dict(loop_context.meta),
    )
    active_policy = policy or build_default_browser_agent_policy()
    decision = active_policy.decide(
        observation,
        loop_context=effective_loop_context,
    )
    if inspect.isawaitable(decision):
        decision = await decision
    return BrowserAgentLoopStep(
        loop_context=effective_loop_context,
        observation=observation,
        decision=decision,
    )
