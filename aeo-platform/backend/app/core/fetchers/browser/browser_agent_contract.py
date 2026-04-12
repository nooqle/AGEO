"""Shared contracts for an agent-driven browser execution loop.

This module defines the stable seam between:

1. the AIO answer-fetch tool / harness layer
2. the browser-facing agent loop that observes and acts on pages
3. the final human takeover fallback

The goal is to move page understanding out of platform-specific selector
branches and into an explicit browser-agent policy. Deterministic runtime
mechanics such as session persistence, takeover issuance, and artifact writes
remain outside this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from typing import Any, Awaitable, Callable, Literal

logger = logging.getLogger(__name__)

BrowserBlockerKind = Literal[
    "none",
    "login",
    "verification",
    "captcha",
    "security_confirmation",
    "account_selection",
    "consent_modal",
    "popup",
    "blank_page",
    "navigation_error",
    "rate_limit",
    "target_closed",
    "unknown",
]

BrowserActionType = Literal[
    "click_ref",
    "fill_ref",
    "press_key",
    "wait",
    "navigate",
    "refresh",
    "close_popup",
    "complete",
    "handoff",
]

BrowserDecisionOutcome = Literal[
    "continue",
    "takeover_required",
    "completed",
    "failed",
]

BrowserAgentStage = Literal[
    "preflight",
    "wait_gate",
    "resume_probe",
    "empty_answer",
]

HUMAN_TAKEOVER_BLOCKERS: frozenset[BrowserBlockerKind] = frozenset(
    {
        "login",
        "verification",
        "captcha",
        "security_confirmation",
        "account_selection",
    }
)


@dataclass(frozen=True, slots=True)
class PlatformBrowserProfile:
    platform: str
    entry_url: str
    ready_url_patterns: tuple[str, ...] = ()
    login_url_patterns: tuple[str, ...] = ()
    ready_hints: tuple[str, ...] = ()
    login_hints: tuple[str, ...] = ()
    late_blocker_hints: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BrowserAgentAction:
    action_type: BrowserActionType
    ref: str | None = None
    text: str | None = None
    key: str | None = None
    target_url: str | None = None
    wait_seconds: float | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class BrowserTakeoverNeed:
    blocker_kind: BrowserBlockerKind
    reason_code: str
    message: str
    action_type: str | None = None
    target_url: str | None = None
    blocking_url: str | None = None
    blocking_fingerprint: str | None = None
    resume_expectation: str = "manual_resume_gate"


@dataclass(frozen=True, slots=True)
class BrowserPageObservation:
    platform: str
    current_url: str | None
    title: str | None
    interactive_snapshot: dict[str, Any] = field(default_factory=dict)
    interactive_ref_count: int = 0
    visible_text_excerpt: str | None = None
    screenshot: dict[str, Any] | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BrowserAgentDecision:
    outcome: BrowserDecisionOutcome
    actions: tuple[BrowserAgentAction, ...] = ()
    blocker_kind: BrowserBlockerKind = "none"
    rationale: str = ""
    confidence: float = 0.0
    takeover: BrowserTakeoverNeed | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class BrowserAgentLoopContext:
    platform: str
    stage: BrowserAgentStage
    target_url: str | None = None
    note: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


ScreenshotProvider = Callable[[], Awaitable[dict[str, Any] | None]]


def requires_human_takeover(blocker_kind: BrowserBlockerKind) -> bool:
    return blocker_kind in HUMAN_TAKEOVER_BLOCKERS


def _unwrap_client_output(value: Any) -> Any:
    if isinstance(value, dict) and "output" in value:
        return value.get("output")
    return value


async def collect_browser_page_observation(
    *,
    client: Any,
    platform: str,
    screenshot_provider: ScreenshotProvider | None = None,
    interactive_only: bool = True,
    visible_text_limit: int = 1200,
) -> BrowserPageObservation:
    """Capture one browser observation from the current live page.

    This helper is intentionally lightweight: it collects URL/title,
    interactive snapshot refs, a short visible-text excerpt, and an optional
    screenshot payload. A future Browser Agent policy can consume this
    observation without depending on platform-specific selectors.
    """

    current_url: str | None = None
    title: str | None = None
    interactive_snapshot: dict[str, Any] = {}
    interactive_ref_count = 0
    visible_text_excerpt: str | None = None
    screenshot: dict[str, Any] | None = None

    page = getattr(client, "page", None)
    page_present = page is not None
    page_closed = False
    if page is not None:
        try:
            page_closed = bool(page.is_closed())
        except Exception:
            page_closed = False
        try:
            page_url = getattr(page, "url", None)
            if isinstance(page_url, str) and page_url.strip():
                current_url = page_url.strip()
        except Exception as exc:
            logger.debug("[BrowserAgentContract] Failed to read page url: %s", exc)
        try:
            page_title = await page.title()
            if isinstance(page_title, str) and page_title.strip():
                title = page_title.strip()
        except Exception as exc:
            logger.debug("[BrowserAgentContract] Failed to read page title: %s", exc)

    snapshot_method = getattr(client, "snapshot", None)
    if callable(snapshot_method):
        try:
            snapshot_result = await snapshot_method(interactive_only=interactive_only)
            if isinstance(snapshot_result, dict):
                interactive_snapshot = dict(snapshot_result)
                refs = interactive_snapshot.get("refs")
                if isinstance(refs, dict):
                    interactive_ref_count = len(refs)
                if not current_url:
                    snapshot_url = interactive_snapshot.get("url")
                    if isinstance(snapshot_url, str) and snapshot_url.strip():
                        current_url = snapshot_url.strip()
        except Exception as exc:
            logger.warning(
                "[BrowserAgentContract] Failed to capture interactive snapshot "
                "(platform=%s): %s",
                platform,
                exc,
            )

    eval_method = getattr(client, "eval", None)
    if callable(eval_method):
        try:
            eval_result = await eval_method(
                f"""() => {{
                    const text = (document.body && document.body.innerText) || '';
                    return text.slice(0, {int(visible_text_limit)});
                }}"""
            )
            raw_output = _unwrap_client_output(eval_result)
            if isinstance(raw_output, str):
                visible_text_excerpt = raw_output.strip() or None
            elif raw_output is not None:
                visible_text_excerpt = str(raw_output).strip() or None
        except Exception as exc:
            logger.debug(
                "[BrowserAgentContract] Failed to capture visible text "
                "(platform=%s): %s",
                platform,
                exc,
            )

    if callable(screenshot_provider):
        try:
            screenshot = await screenshot_provider()
        except Exception as exc:
            logger.warning(
                "[BrowserAgentContract] Failed to capture screenshot "
                "(platform=%s): %s",
                platform,
                exc,
            )

    meta = {
        "page_present": page_present,
        "page_closed": page_closed,
        "snapshot_present": bool(interactive_snapshot),
        "screenshot_present": bool(screenshot),
        "has_visible_text": bool(visible_text_excerpt),
    }

    return BrowserPageObservation(
        platform=platform,
        current_url=current_url,
        title=title,
        interactive_snapshot=interactive_snapshot,
        interactive_ref_count=interactive_ref_count,
        visible_text_excerpt=visible_text_excerpt,
        screenshot=screenshot,
        meta=meta,
    )


def observation_to_llm_payload(observation: BrowserPageObservation) -> dict[str, Any]:
    """Convert one observation into a compact LLM-friendly payload."""

    refs = observation.interactive_snapshot.get("refs")
    preview_refs: list[dict[str, Any]] = []
    if isinstance(refs, dict):
        for ref_id, item in list(refs.items())[:20]:
            if not isinstance(item, dict):
                continue
            preview_refs.append(
                {
                    "ref": ref_id,
                    "role": item.get("role"),
                    "tag": item.get("tag"),
                    "text": item.get("text"),
                    "placeholder": item.get("placeholder"),
                }
            )

    return {
        "platform": observation.platform,
        "current_url": observation.current_url,
        "title": observation.title,
        "interactive_ref_count": observation.interactive_ref_count,
        "interactive_refs": preview_refs,
        "visible_text_excerpt": observation.visible_text_excerpt,
        "meta": dict(observation.meta),
        "screenshot": observation.screenshot,
    }


def loop_context_to_llm_payload(loop_context: BrowserAgentLoopContext) -> dict[str, Any]:
    return {
        "platform": loop_context.platform,
        "stage": loop_context.stage,
        "target_url": loop_context.target_url,
        "note": loop_context.note,
        "meta": dict(loop_context.meta),
    }


def platform_profile_to_payload(profile: PlatformBrowserProfile) -> dict[str, Any]:
    return {
        "platform": profile.platform,
        "entry_url": profile.entry_url,
        "ready_url_patterns": list(profile.ready_url_patterns),
        "login_url_patterns": list(profile.login_url_patterns),
        "ready_hints": list(profile.ready_hints),
        "login_hints": list(profile.login_hints),
        "late_blocker_hints": list(profile.late_blocker_hints),
    }


def observation_to_llm_json(observation: BrowserPageObservation) -> str:
    return json.dumps(
        observation_to_llm_payload(observation),
        ensure_ascii=False,
        indent=2,
    )
