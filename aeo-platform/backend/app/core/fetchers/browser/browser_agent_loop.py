"""Loop helpers for pluggable Browser Agent policy execution."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

from app.config import get_settings
from app.core.llm import get_llm_model
from app.core.llm.glm5 import GLM5Config, GLM5Model
from app.core.fetchers.browser.browser_agent_contract import (
    BrowserAgentAction,
    BrowserAgentDecision,
    BrowserAgentLoopContext,
    BrowserPageObservation,
    BrowserTakeoverNeed,
    ScreenshotProvider,
    collect_browser_page_observation,
    get_observation_slice_profile,
    loop_context_to_llm_payload,
    observation_to_llm_payload,
)
from app.core.fetchers.browser.browser_agent_policy import decide_browser_stage

logger = logging.getLogger(__name__)
_LLM_DEFAULT_STAGES = frozenset({"preflight", "wait_gate", "resume_probe"})
_BROWSER_AGENT_LLM_PAYLOAD_LIMIT = 2200
_BROWSER_AGENT_LLM_SEMAPHORE: asyncio.Semaphore | None = None
_BROWSER_AGENT_LLM_SEMAPHORE_SIZE = 0
_LLM_BROWSER_SYSTEM_PROMPT = (
    "你是浏览器执行代理。"
    "请只基于给定阶段指令和精简页面观测，判断当前是继续自动操作、需要人工接管、还是已经可以继续主流程。"
    "只输出 JSON 对象。"
)


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
        return decide_browser_stage(
            observation,
            loop_context=loop_context,
            target_url=loop_context.target_url,
        )


def _build_llm_browser_agent_prompt(loop_context: BrowserAgentLoopContext) -> str:
    stage_rules = {
        "preflight": (
            "阶段=preflight。只判断是否已到可继续页面，或是否存在登录/验证/验证码/账号选择/安全确认/普通弹窗/空白页/导航错误。"
        ),
        "wait_gate": (
            "阶段=wait_gate。问题已提交。只判断是继续等待、轻量恢复，还是进入 late login / verification / captcha / popup / blank / error。"
        ),
        "resume_probe": (
            "阶段=resume_probe。用户刚完成接管。只有人工阻塞已清除、页面已回到可继续提问或继续读取答案的主界面时才可继续。"
        ),
        "empty_answer": (
            "阶段=empty_answer。只判断空答案是暂时等待、可自动恢复异常，还是需要人工接管。"
        ),
    }
    prompt = (
        "输出字段：outcome, blocker_kind, rationale, confidence, actions, takeover。"
        "登录/验证码/人机验证/安全确认/账号选择必须人工接管。"
        "普通弹窗、协议弹窗、空白页、轻量恢复优先自动处理。"
        "允许动作仅限 click_ref/press_key/wait/navigate/refresh/close_popup/complete/handoff。"
        f"{stage_rules.get(loop_context.stage, '')}"
    ).strip()
    if loop_context.note:
        prompt = f"{prompt} 当前阶段补充要求：{loop_context.note}".strip()
    return prompt


def _payload_char_length(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload, ensure_ascii=False))


def _trim_browser_agent_payload(
    payload: dict[str, Any],
    *,
    max_chars: int,
) -> tuple[dict[str, Any], bool]:
    compact = json.loads(json.dumps(payload, ensure_ascii=False))
    observation = compact.get("observation") or {}

    if _payload_char_length(compact) <= max_chars:
        return compact, False

    text = observation.get("visible_text_excerpt")
    if isinstance(text, str) and text:
        for text_limit in (180, 120, 80, 0):
            observation["visible_text_excerpt"] = (
                text[:text_limit] if text_limit > 0 else None
            )
            if _payload_char_length(compact) <= max_chars:
                return compact, False

    refs = list(observation.get("interactive_refs") or [])
    if refs:
        for ref_limit in (4, 3, 2, 0):
            observation["interactive_refs"] = refs[:ref_limit]
            if _payload_char_length(compact) <= max_chars:
                return compact, False

    return compact, _payload_char_length(compact) > max_chars


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
            blocker_kind=str(
                raw_takeover.get("blocker_kind") or blocker_kind or "unknown"
            ),
            reason_code=str(
                raw_takeover.get("reason_code") or "browser_agent_takeover"
            ),
            message=str(
                raw_takeover.get("message") or "browser agent takeover required"
            ),
            action_type=(
                str(raw_takeover.get("action_type"))
                if raw_takeover.get("action_type") is not None
                else None
            ),
            target_url=raw_takeover.get("target_url"),
            blocking_url=(
                str(raw_takeover.get("blocking_url"))
                if raw_takeover.get("blocking_url") is not None
                else None
            ),
            blocking_fingerprint=(
                str(raw_takeover.get("blocking_fingerprint"))
                if raw_takeover.get("blocking_fingerprint") is not None
                else None
            ),
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


def _is_safe_navigate_target(
    candidate_url: str | None,
    *,
    loop_context: BrowserAgentLoopContext,
) -> bool:
    if not candidate_url:
        return False
    if candidate_url == (loop_context.target_url or ""):
        return True
    target_url = loop_context.target_url
    if not target_url:
        return False
    try:
        candidate = urlparse(candidate_url)
        target = urlparse(target_url)
    except Exception:
        return False
    return bool(candidate.netloc and candidate.netloc == target.netloc)


def _get_browser_agent_llm_semaphore() -> asyncio.Semaphore:
    global _BROWSER_AGENT_LLM_SEMAPHORE, _BROWSER_AGENT_LLM_SEMAPHORE_SIZE

    settings = get_settings()
    configured = int(getattr(settings, "BROWSER_AGENT_LLM_MAX_CONCURRENCY", 1) or 1)
    limit = max(1, configured)
    if (
        _BROWSER_AGENT_LLM_SEMAPHORE is None
        or _BROWSER_AGENT_LLM_SEMAPHORE_SIZE != limit
    ):
        _BROWSER_AGENT_LLM_SEMAPHORE = asyncio.Semaphore(limit)
        _BROWSER_AGENT_LLM_SEMAPHORE_SIZE = limit
    return _BROWSER_AGENT_LLM_SEMAPHORE


def _get_browser_agent_llm_model() -> Any:
    settings = get_settings()
    browser_api_key = str(
        getattr(settings, "BROWSER_AGENT_LLM_API_KEY", "") or ""
    ).strip()
    provider = str(getattr(settings, "LLM_PROVIDER", "minimax") or "minimax").lower()
    if not browser_api_key or provider != "glm5":
        return get_llm_model()
    return GLM5Model(
        GLM5Config(
            api_key=browser_api_key,
            base_url=str(
                getattr(
                    settings,
                    "GLM5_BASE_URL",
                    "https://open.bigmodel.cn/api/paas/v4",
                )
                or "https://open.bigmodel.cn/api/paas/v4"
            ),
        )
    )


def _sanitize_llm_decision(
    decision: BrowserAgentDecision,
    *,
    loop_context: BrowserAgentLoopContext,
) -> BrowserAgentDecision | None:
    sanitized_actions: list[BrowserAgentAction] = []
    for action in decision.actions:
        if action.action_type == "navigate":
            target_url = action.target_url or loop_context.target_url
            if not _is_safe_navigate_target(target_url, loop_context=loop_context):
                continue
            sanitized_actions.append(
                BrowserAgentAction(
                    action_type="navigate",
                    target_url=target_url,
                    reason=action.reason,
                )
            )
            continue

        if action.action_type == "wait":
            wait_seconds = action.wait_seconds or 0.8
            sanitized_actions.append(
                BrowserAgentAction(
                    action_type="wait",
                    wait_seconds=max(0.2, min(wait_seconds, 3.0)),
                    reason=action.reason,
                )
            )
            continue

        if action.action_type in {"click_ref", "close_popup"}:
            if not action.ref:
                continue
            sanitized_actions.append(action)
            continue

        if action.action_type == "press_key":
            if not action.key:
                continue
            sanitized_actions.append(action)
            continue

        if action.action_type in {"refresh", "complete", "handoff"}:
            sanitized_actions.append(action)

    return BrowserAgentDecision(
        outcome=decision.outcome,
        actions=tuple(sanitized_actions),
        blocker_kind=decision.blocker_kind,
        rationale=decision.rationale,
        confidence=decision.confidence,
        takeover=decision.takeover,
        error=decision.error,
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
        settings = get_settings()
        if not bool(getattr(settings, "BROWSER_AGENT_LLM_ENABLED", True)):
            return None
        if loop_context.stage not in _LLM_DEFAULT_STAGES:
            return None
        try:
            model = _get_browser_agent_llm_model()
        except Exception as exc:
            logger.warning(
                "[BrowserAgentLoop] Failed to get browser-agent LLM model: %s", exc
            )
            return None
        compact_payload = {
            "loop_context": loop_context_to_llm_payload(loop_context),
            "observation": observation_to_llm_payload(
                observation,
                loop_context=loop_context,
                stage_profile=get_observation_slice_profile(loop_context.stage),
            ),
        }
        compact_payload, over_limit = _trim_browser_agent_payload(
            compact_payload,
            max_chars=_BROWSER_AGENT_LLM_PAYLOAD_LIMIT,
        )
        if over_limit:
            logger.info(
                "[BrowserAgentLoop] Skipping LLM policy because compact payload still exceeds limit "
                "(platform=%s, stage=%s, chars=%s)",
                loop_context.platform,
                loop_context.stage,
                _payload_char_length(compact_payload),
            )
            return None
        semaphore = _get_browser_agent_llm_semaphore()
        max_tokens = max(
            64,
            int(getattr(settings, "BROWSER_AGENT_LLM_MAX_TOKENS", 384) or 384),
        )
        thinking_enabled = bool(
            getattr(settings, "BROWSER_AGENT_LLM_THINKING_ENABLED", False)
        )
        model_name = str(
            getattr(settings, "BROWSER_AGENT_LLM_MODEL_NAME", "") or ""
        ).strip()
        call_kwargs: dict[str, Any] = {
            "temperature": 0.1,
            "max_tokens": max_tokens,
            "thinking_enabled": thinking_enabled,
        }
        if model_name:
            call_kwargs["model"] = model_name
        try:
            async with semaphore:
                response = await model.async_call(
                    messages=[
                        {"role": "system", "content": _LLM_BROWSER_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": (
                                f"{_build_llm_browser_agent_prompt(loop_context)} "
                                "当缺少足够把握时，返回 outcome=continue、blocker_kind=none、actions=[]。"
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                compact_payload,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        },
                    ],
                    **call_kwargs,
                )
        except Exception as exc:
            logger.warning("[BrowserAgentLoop] LLM browser decision failed: %s", exc)
            return None
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
        return _sanitize_llm_decision(decision, loop_context=loop_context)


class HybridBrowserAgentPolicy:
    """LLM-first for browser blocker stages, deterministic fallback elsewhere."""

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
        def _is_noop(decision: BrowserAgentDecision | None) -> bool:
            if decision is None:
                return True
            return (
                decision.outcome == "continue"
                and not decision.actions
                and decision.blocker_kind == "none"
            )

        llm_first = (
            self._llm_policy is not None and loop_context.stage in _LLM_DEFAULT_STAGES
        )

        llm_decision: BrowserAgentDecision | None = None
        if llm_first:
            llm_decision = self._llm_policy.decide(
                observation,
                loop_context=loop_context,
            )
            if inspect.isawaitable(llm_decision):
                llm_decision = await llm_decision
            if not _is_noop(llm_decision):
                return llm_decision

        bootstrap = self._bootstrap_policy.decide(
            observation,
            loop_context=loop_context,
        )
        if inspect.isawaitable(bootstrap):
            bootstrap = await bootstrap
        if not _is_noop(bootstrap) or self._llm_policy is None:
            return bootstrap

        if llm_decision is not None:
            return llm_decision

        llm_decision = self._llm_policy.decide(
            observation,
            loop_context=loop_context,
        )
        if inspect.isawaitable(llm_decision):
            llm_decision = await llm_decision
        return llm_decision or bootstrap


def build_default_browser_agent_policy() -> BrowserAgentPolicy:
    return HybridBrowserAgentPolicy(
        llm_policy=LLMBrowserAgentPolicy(),
    )


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
