"""Stage-aware bootstrap policy for the shared browser-agent runtime."""

from __future__ import annotations

from hashlib import sha1
from typing import Any, Iterable

from app.core.fetchers.browser.browser_agent_contract import (
    BrowserAgentAction,
    BrowserAgentDecision,
    BrowserAgentLoopContext,
    BrowserPageObservation,
    BrowserTakeoverNeed,
    PlatformBrowserProfile,
)

_LOGIN_KEYWORDS = (
    "log in",
    "login",
    "sign in",
    "登录",
    "微信登录",
    "手机号登录",
    "立即登录",
    "继续登录",
)
_LOGIN_SUPPORT_KEYWORDS = (
    "verification code",
    "phone number",
    "qr code",
    "scan",
    "验证码",
    "手机号",
    "二维码",
    "扫码",
)
_VERIFICATION_KEYWORDS = (
    "安全验证",
    "verify",
    "verification",
    "human verification",
    "人机验证",
    "短信验证",
)
_CAPTCHA_KEYWORDS = (
    "captcha",
    "滑块",
    "拖动",
    "拼图",
)
_SECURITY_KEYWORDS = (
    "安全确认",
    "确认是你本人",
    "suspicious activity",
    "security check",
    "账号异常",
    "安全检查",
)
_ACCOUNT_SELECTION_KEYWORDS = (
    "choose an account",
    "account chooser",
    "切换账号",
    "选择账号",
    "选择账户",
)
_CONSENT_KEYWORDS = (
    "cookie",
    "隐私",
    "协议",
    "policy",
    "terms",
    "同意",
)
_POPUP_KEYWORDS = (
    "upgrade",
    "download app",
    "new feature",
    "通知",
    "活动",
    "升级",
    "下载",
    "弹窗",
)
_DISMISS_KEYWORDS = (
    "关闭",
    "取消",
    "稍后",
    "跳过",
    "我知道了",
    "not now",
    "later",
    "skip",
    "dismiss",
    "close",
)
_NAVIGATION_ERROR_KEYWORDS = (
    "err_",
    "site can't be reached",
    "took too long to respond",
    "this page isn’t working",
    "this page isn't working",
    "无法访问此网站",
    "响应时间过长",
    "连接已重置",
)
_LOGIN_CTA_KEYWORDS = (
    "登录",
    "立即登录",
    "去登录",
    "login",
    "log in",
    "sign in",
)
_AUTH_MODAL_KEYWORDS = (
    "wechat qr code",
    "log in with phone number",
    "验证码",
    "手机号",
    "二维码",
    "扫码",
)


def _normalize_text(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def _collect_text_blob(observation: BrowserPageObservation) -> str:
    parts = [
        observation.current_url or "",
        observation.title or "",
        observation.visible_text_excerpt or "",
    ]
    refs = observation.interactive_snapshot.get("refs")
    if isinstance(refs, dict):
        for item in refs.values():
            if not isinstance(item, dict):
                continue
            parts.append(str(item.get("text") or ""))
            parts.append(str(item.get("placeholder") or ""))
    return _normalize_text(" ".join(parts))


def _iter_ref_entries(
    observation: BrowserPageObservation,
) -> Iterable[tuple[str, dict[str, Any], str]]:
    refs = observation.interactive_snapshot.get("refs")
    if not isinstance(refs, dict):
        return []
    entries: list[tuple[str, dict[str, Any], str]] = []
    for ref_id, item in refs.items():
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        if role not in {"button", "link", "textbox", "input"}:
            continue
        ref_text = _normalize_text(
            f"{item.get('text') or ''} {item.get('placeholder') or ''}"
        )
        entries.append((f"@{ref_id}", item, ref_text))
    return entries


def _matches_any(text: str, keywords: Iterable[str]) -> bool:
    return any(keyword in text for keyword in keywords if keyword)


def _normalize_keywords(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(item for item in (_normalize_text(value) for value in values) if item)


def _find_ref_by_keywords(
    observation: BrowserPageObservation,
    keywords: Iterable[str],
) -> str | None:
    normalized_keywords = _normalize_keywords(keywords)
    for ref_id, _, ref_text in _iter_ref_entries(observation):
        if ref_text and _matches_any(ref_text, normalized_keywords):
            return ref_id
    return None


def _find_refs_by_keywords(
    observation: BrowserPageObservation,
    keywords: Iterable[str],
) -> list[str]:
    normalized_keywords = _normalize_keywords(keywords)
    matches: list[str] = []
    for ref_id, _, ref_text in _iter_ref_entries(observation):
        if ref_text and _matches_any(ref_text, normalized_keywords):
            matches.append(ref_id)
    return matches


def _extract_platform_profile(loop_context: BrowserAgentLoopContext) -> PlatformBrowserProfile | None:
    raw = loop_context.meta.get("platform_profile")
    if not isinstance(raw, dict):
        return None
    entry_url = raw.get("entry_url")
    platform = raw.get("platform")
    if not isinstance(entry_url, str) or not entry_url.strip():
        return None
    if not isinstance(platform, str) or not platform.strip():
        return None
    return PlatformBrowserProfile(
        platform=platform,
        entry_url=entry_url.strip(),
        ready_url_patterns=tuple(
            item for item in raw.get("ready_url_patterns", []) if isinstance(item, str)
        ),
        login_url_patterns=tuple(
            item for item in raw.get("login_url_patterns", []) if isinstance(item, str)
        ),
        ready_hints=tuple(
            item for item in raw.get("ready_hints", []) if isinstance(item, str)
        ),
        login_hints=tuple(
            item for item in raw.get("login_hints", []) if isinstance(item, str)
        ),
        late_blocker_hints=tuple(
            item for item in raw.get("late_blocker_hints", []) if isinstance(item, str)
        ),
    )


def _url_matches_patterns(url: str | None, patterns: Iterable[str]) -> bool:
    normalized_url = _normalize_text(url)
    if not normalized_url:
        return False
    return any(_normalize_text(pattern) in normalized_url for pattern in patterns if pattern)


def _is_blank_page(observation: BrowserPageObservation) -> bool:
    current_url = (observation.current_url or "").strip().lower()
    if current_url == "about:blank":
        return True
    return (
        not current_url
        and observation.interactive_ref_count == 0
        and not observation.visible_text_excerpt
    )


def _is_ready_surface(
    observation: BrowserPageObservation,
    text_blob: str,
    profile: PlatformBrowserProfile | None,
) -> bool:
    if profile is None:
        return False
    if _url_matches_patterns(observation.current_url, profile.ready_url_patterns):
        return True
    if profile.ready_hints and _matches_any(text_blob, _normalize_keywords(profile.ready_hints)):
        return True
    return False


def _is_login_surface(
    observation: BrowserPageObservation,
    text_blob: str,
    profile: PlatformBrowserProfile | None,
) -> bool:
    login_patterns = profile.login_url_patterns if profile is not None else ()
    if _url_matches_patterns(observation.current_url, login_patterns):
        return True
    login_hints = _normalize_keywords(profile.login_hints if profile is not None else ())
    if login_hints and _matches_any(text_blob, login_hints):
        return True
    if _matches_any(text_blob, _normalize_keywords(_LOGIN_KEYWORDS + _AUTH_MODAL_KEYWORDS)):
        return _matches_any(text_blob, _normalize_keywords(_LOGIN_SUPPORT_KEYWORDS))
    return False


def _has_login_cta(
    observation: BrowserPageObservation,
    text_blob: str,
    profile: PlatformBrowserProfile | None,
) -> str | None:
    keywords = list(_LOGIN_CTA_KEYWORDS)
    if profile is not None:
        keywords.extend(profile.login_hints)
    ref = _find_ref_by_keywords(observation, keywords)
    if ref and not _is_login_surface(observation, text_blob, profile):
        return ref
    return None


def _detect_blocking_kind(
    observation: BrowserPageObservation,
    text_blob: str,
    loop_context: BrowserAgentLoopContext,
    profile: PlatformBrowserProfile | None,
) -> tuple[str, str] | None:
    if _matches_any(text_blob, _normalize_keywords(_CAPTCHA_KEYWORDS)):
        return "captcha", "captcha_detected"
    if _matches_any(text_blob, _normalize_keywords(_SECURITY_KEYWORDS)):
        return "security_confirmation", "security_confirmation_detected"
    if _matches_any(text_blob, _normalize_keywords(_ACCOUNT_SELECTION_KEYWORDS)):
        return "account_selection", "account_selection_detected"
    if _is_login_surface(observation, text_blob, profile):
        return "login", "login_detected"
    if _matches_any(text_blob, _normalize_keywords(_VERIFICATION_KEYWORDS)):
        return "verification", "verification_detected"

    late_hints = _normalize_keywords(profile.late_blocker_hints if profile is not None else ())
    if loop_context.stage in {"wait_gate", "resume_probe"} and late_hints and _matches_any(text_blob, late_hints):
        return "verification", "late_blocker_detected"
    return None


def _build_blocking_fingerprint(
    *,
    blocker_kind: str,
    observation: BrowserPageObservation,
    reason_code: str,
    text_blob: str,
) -> str:
    seed = "|".join(
        [
            blocker_kind,
            reason_code,
            _normalize_text(observation.current_url),
            _normalize_text(observation.title),
            text_blob[:160],
        ]
    )
    return sha1(seed.encode("utf-8")).hexdigest()[:16]


def _build_takeover(
    *,
    blocker_kind: str,
    reason_code: str,
    observation: BrowserPageObservation,
    loop_context: BrowserAgentLoopContext,
    text_blob: str,
) -> BrowserTakeoverNeed:
    action_type = "verify" if blocker_kind in {"verification", "captcha"} else "login"
    return BrowserTakeoverNeed(
        blocker_kind=blocker_kind,
        reason_code=reason_code,
        message=f"{blocker_kind} detected",
        action_type=action_type,
        target_url=loop_context.target_url or observation.current_url,
        blocking_url=observation.current_url,
        blocking_fingerprint=_build_blocking_fingerprint(
            blocker_kind=blocker_kind,
            observation=observation,
            reason_code=reason_code,
            text_blob=text_blob,
        ),
    )


def decide_browser_stage(
    observation: BrowserPageObservation,
    *,
    loop_context: BrowserAgentLoopContext,
    target_url: str | None = None,
) -> BrowserAgentDecision:
    text_blob = _collect_text_blob(observation)
    profile = _extract_platform_profile(loop_context)
    fallback_target_url = target_url or loop_context.target_url

    if observation.meta.get("page_closed"):
        return BrowserAgentDecision(
            outcome="continue",
            blocker_kind="target_closed",
            rationale="current page handle is closed; try to sync to live page",
            confidence=0.95,
        )

    if _is_blank_page(observation):
        return BrowserAgentDecision(
            outcome="continue",
            actions=(
                BrowserAgentAction(
                    action_type="navigate" if fallback_target_url else "refresh",
                    target_url=fallback_target_url,
                    reason="blank page detected",
                ),
            ),
            blocker_kind="blank_page",
            rationale="blank browser surface detected",
            confidence=0.9,
        )

    if _matches_any(text_blob, _normalize_keywords(_NAVIGATION_ERROR_KEYWORDS)):
        return BrowserAgentDecision(
            outcome="continue",
            actions=(
                BrowserAgentAction(
                    action_type="navigate" if fallback_target_url else "refresh",
                    target_url=fallback_target_url,
                    reason="navigation error detected",
                ),
            ),
            blocker_kind="navigation_error",
            rationale="navigation error page detected",
            confidence=0.92,
        )

    dismiss_ref = _find_ref_by_keywords(observation, _DISMISS_KEYWORDS)
    if dismiss_ref and _matches_any(
        text_blob,
        _normalize_keywords(_CONSENT_KEYWORDS + _POPUP_KEYWORDS),
    ):
        blocker_kind = (
            "consent_modal"
            if _matches_any(text_blob, _normalize_keywords(_CONSENT_KEYWORDS))
            else "popup"
        )
        return BrowserAgentDecision(
            outcome="continue",
            actions=(
                BrowserAgentAction(
                    action_type="click_ref",
                    ref=dismiss_ref,
                    reason=f"auto dismiss {blocker_kind}",
                ),
                BrowserAgentAction(
                    action_type="wait",
                    wait_seconds=0.8,
                    reason="wait after dismissing popup",
                ),
            ),
            blocker_kind=blocker_kind,
            rationale=f"{blocker_kind} detected with dismiss action",
            confidence=0.82,
        )

    blocking = _detect_blocking_kind(
        observation,
        text_blob,
        loop_context,
        profile,
    )
    if blocking is not None:
        blocker_kind, reason_code = blocking
        return BrowserAgentDecision(
            outcome="takeover_required",
            blocker_kind=blocker_kind,
            rationale=f"{blocker_kind} gate detected from shared browser runtime",
            confidence=0.9,
            takeover=_build_takeover(
                blocker_kind=blocker_kind,
                reason_code=reason_code,
                observation=observation,
                loop_context=loop_context,
                text_blob=text_blob,
            ),
        )

    if loop_context.stage == "preflight":
        login_cta_ref = _has_login_cta(observation, text_blob, profile)
        if login_cta_ref:
            return BrowserAgentDecision(
                outcome="continue",
                actions=(
                    BrowserAgentAction(
                        action_type="click_ref",
                        ref=login_cta_ref,
                        reason="expand login surface before takeover",
                    ),
                    BrowserAgentAction(
                        action_type="wait",
                        wait_seconds=1.0,
                        reason="wait for login surface to open",
                    ),
                ),
                blocker_kind="popup",
                rationale="login entry detected; opening live blocking scene first",
                confidence=0.84,
            )

    if loop_context.stage == "resume_probe" and _is_ready_surface(observation, text_blob, profile):
        return BrowserAgentDecision(
            outcome="continue",
            blocker_kind="none",
            rationale="resume probe sees a ready surface",
            confidence=0.88,
        )

    return BrowserAgentDecision(
        outcome="continue",
        blocker_kind="none",
        rationale="no shared browser blocker detected",
        confidence=0.55,
    )


def decide_browser_preflight(
    observation: BrowserPageObservation,
    *,
    target_url: str | None = None,
) -> BrowserAgentDecision:
    """Backward-compatible wrapper for preflight-only tests/callers."""

    return decide_browser_stage(
        observation,
        loop_context=BrowserAgentLoopContext(
            platform=observation.platform,
            stage="preflight",
            target_url=target_url or observation.current_url,
            meta=dict(observation.meta),
        ),
        target_url=target_url or observation.current_url,
    )
