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


@dataclass(frozen=True, slots=True)
class ObservationSliceProfile:
    stage: BrowserAgentStage
    visible_text_limit: int
    interactive_ref_limit: int
    include_screenshot: bool = False
    loop_meta_keys: tuple[str, ...] = ()
    observation_meta_keys: tuple[str, ...] = ()


_OBSERVATION_SLICE_PROFILES: dict[BrowserAgentStage, ObservationSliceProfile] = {
    "preflight": ObservationSliceProfile(
        stage="preflight",
        visible_text_limit=320,
        interactive_ref_limit=8,
        include_screenshot=False,
        observation_meta_keys=("page_present", "page_closed", "snapshot_present"),
    ),
    "wait_gate": ObservationSliceProfile(
        stage="wait_gate",
        visible_text_limit=220,
        interactive_ref_limit=6,
        include_screenshot=False,
        loop_meta_keys=("waited_seconds",),
        observation_meta_keys=("page_present", "page_closed", "snapshot_present"),
    ),
    "resume_probe": ObservationSliceProfile(
        stage="resume_probe",
        visible_text_limit=220,
        interactive_ref_limit=6,
        include_screenshot=False,
        loop_meta_keys=("action_type",),
        observation_meta_keys=("page_present", "page_closed", "snapshot_present"),
    ),
    "empty_answer": ObservationSliceProfile(
        stage="empty_answer",
        visible_text_limit=260,
        interactive_ref_limit=6,
        include_screenshot=False,
        loop_meta_keys=("force_visual",),
        observation_meta_keys=("page_present", "page_closed", "snapshot_present"),
    ),
}


ScreenshotProvider = Callable[[], Awaitable[dict[str, Any] | None]]


def requires_human_takeover(blocker_kind: BrowserBlockerKind) -> bool:
    return blocker_kind in HUMAN_TAKEOVER_BLOCKERS


def _unwrap_client_output(value: Any) -> Any:
    if isinstance(value, dict) and "output" in value:
        return value.get("output")
    return value


def _compact_text(value: Any, limit: int) -> str | None:
    text = " ".join(str(value or "").split())
    if not text:
        return None
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    return text[: limit - 1] + "…"


def _matches_keywords(value: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in value for keyword in keywords)


def _ref_priority(item: dict[str, Any]) -> tuple[int, str]:
    haystack = " ".join(
        str(item.get(key) or "").strip().lower()
        for key in ("text", "placeholder", "role", "tag")
    )
    login_keywords = ("log in", "login", "登录", "sign in", "wechat qr", "二维码", "账号")
    verify_keywords = ("验证", "captcha", "verification", "短信", "code", "安全确认", "人机")
    dismiss_keywords = ("关闭", "稍后", "以后", "skip", "later", "close", "dismiss", "同意", "accept")
    input_keywords = ("input", "textarea", "textbox", "submit", "send", "ask", "search", "问题", "发送", "输入")

    if _matches_keywords(haystack, login_keywords):
        return (0, haystack)
    if _matches_keywords(haystack, verify_keywords):
        return (1, haystack)
    if _matches_keywords(haystack, dismiss_keywords):
        return (2, haystack)
    if _matches_keywords(haystack, input_keywords):
        return (3, haystack)
    return (4, haystack)


def get_observation_slice_profile(stage: BrowserAgentStage) -> ObservationSliceProfile:
    return _OBSERVATION_SLICE_PROFILES[stage]


def _slice_interactive_refs(
    refs: dict[str, Any] | None,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    if not isinstance(refs, dict):
        return []
    ranked_items: list[tuple[tuple[int, str], str, dict[str, Any]]] = []
    for ref_id, item in refs.items():
        if not isinstance(item, dict):
            continue
        ranked_items.append((_ref_priority(item), str(ref_id), item))
    ranked_items.sort(key=lambda item: (item[0][0], item[0][1], item[1]))

    preview_refs: list[dict[str, Any]] = []
    for _, ref_id, item in ranked_items[:limit]:
        preview_refs.append(
            {
                "ref": ref_id,
                "role": item.get("role"),
                "tag": item.get("tag"),
                "text": _compact_text(item.get("text"), 80),
                "placeholder": _compact_text(item.get("placeholder"), 60),
            }
        )
    return preview_refs


def build_observation_slice(
    observation: BrowserPageObservation,
    *,
    loop_context: BrowserAgentLoopContext | None = None,
    stage_profile: ObservationSliceProfile | None = None,
) -> dict[str, Any]:
    profile = stage_profile or get_observation_slice_profile(
        loop_context.stage if loop_context is not None else "preflight"
    )
    include_screenshot = profile.include_screenshot
    if loop_context and loop_context.stage == "empty_answer":
        include_screenshot = include_screenshot or bool(loop_context.meta.get("force_visual"))

    observation_meta = {
        key: observation.meta.get(key)
        for key in profile.observation_meta_keys
        if key in observation.meta
    }

    return {
        "platform": observation.platform,
        "current_url": observation.current_url,
        "title": _compact_text(observation.title, 80),
        "interactive_ref_count": observation.interactive_ref_count,
        "interactive_refs": _slice_interactive_refs(
            observation.interactive_snapshot.get("refs"),
            limit=profile.interactive_ref_limit,
        ),
        "visible_text_excerpt": _compact_text(
            observation.visible_text_excerpt,
            profile.visible_text_limit,
        ),
        "meta": observation_meta,
        "screenshot": observation.screenshot if include_screenshot else None,
    }


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


def observation_to_llm_payload(
    observation: BrowserPageObservation,
    *,
    loop_context: BrowserAgentLoopContext | None = None,
    stage_profile: ObservationSliceProfile | None = None,
) -> dict[str, Any]:
    """Convert one observation into a compact LLM-friendly payload."""

    return build_observation_slice(
        observation,
        loop_context=loop_context,
        stage_profile=stage_profile,
    )


def loop_context_to_llm_payload(loop_context: BrowserAgentLoopContext) -> dict[str, Any]:
    stage_profile = get_observation_slice_profile(loop_context.stage)
    compact_meta = {
        key: loop_context.meta.get(key)
        for key in stage_profile.loop_meta_keys
        if key in loop_context.meta
    }
    return {
        "platform": loop_context.platform,
        "stage": loop_context.stage,
        "target_url": loop_context.target_url,
        "note": _compact_text(loop_context.note, 160),
        "meta": compact_meta,
    }


def platform_profile_to_payload(profile: PlatformBrowserProfile) -> dict[str, Any]:
    return {
        "platform": profile.platform,
        "entry_url": profile.entry_url,
        "ready_url_patterns": list(profile.ready_url_patterns[:3]),
        "login_url_patterns": list(profile.login_url_patterns[:3]),
        "ready_hints": list(profile.ready_hints[:4]),
        "login_hints": list(profile.login_hints[:4]),
        "late_blocker_hints": list(profile.late_blocker_hints[:4]),
    }


def observation_to_llm_json(observation: BrowserPageObservation) -> str:
    return json.dumps(
        observation_to_llm_payload(observation),
        ensure_ascii=False,
        indent=2,
    )
