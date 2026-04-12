"""Bootstrap policy for the browser-agent execution loop.

This module is intentionally generic. It consumes one page observation and
returns the next action/takeover decision without relying on platform-specific
selectors. The current implementation is a bootstrap policy so the control
surface can move out of platform handlers first; it can later be replaced by
an LLM-driven policy without changing handler contracts.
"""

from __future__ import annotations

from typing import Any, Iterable
from urllib.parse import urlparse

from app.core.fetchers.browser.browser_agent_contract import (
    BrowserAgentAction,
    BrowserAgentDecision,
    BrowserPageObservation,
    BrowserTakeoverNeed,
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
    return any(keyword in text for keyword in keywords)


def _find_ref_by_keywords(
    observation: BrowserPageObservation,
    keywords: Iterable[str],
) -> str | None:
    normalized_keywords = tuple(_normalize_text(item) for item in keywords)
    for ref_id, _, ref_text in _iter_ref_entries(observation):
        if ref_text and _matches_any(ref_text, normalized_keywords):
            return ref_id
    return None


def _is_blank_page(observation: BrowserPageObservation) -> bool:
    current_url = (observation.current_url or "").strip().lower()
    if current_url == "about:blank":
        return True
    if (
        not current_url
        and observation.interactive_ref_count == 0
        and not observation.visible_text_excerpt
    ):
        return True
    return False


def _login_like(observation: BrowserPageObservation, text_blob: str) -> bool:
    current_url = _normalize_text(observation.current_url)
    url_path = _normalize_text(urlparse(observation.current_url or "").path)
    if any(token in current_url for token in ("/sign_in", "/login", "/auth", "/signin")):
        return True
    if any(token in url_path for token in ("sign_in", "login", "signin", "auth")):
        return True

    login_signal = _matches_any(text_blob, _LOGIN_KEYWORDS)
    support_signal = _matches_any(text_blob, _LOGIN_SUPPORT_KEYWORDS)
    login_ref = _find_ref_by_keywords(observation, _LOGIN_KEYWORDS)
    return bool(login_ref and support_signal) or (login_signal and support_signal)


def decide_browser_preflight(
    observation: BrowserPageObservation,
    *,
    target_url: str | None = None,
) -> BrowserAgentDecision:
    """Return the next generic browser action before platform logic runs."""

    text_blob = _collect_text_blob(observation)

    if observation.meta.get("page_closed"):
        return BrowserAgentDecision(
            outcome="continue",
            blocker_kind="target_closed",
            rationale="current page handle is closed; try to sync to live page",
            confidence=0.95,
        )

    if _is_blank_page(observation):
        action = BrowserAgentAction(
            action_type="navigate" if target_url else "refresh",
            target_url=target_url,
            reason="blank page detected",
        )
        return BrowserAgentDecision(
            outcome="continue",
            actions=(action,),
            blocker_kind="blank_page",
            rationale="blank browser surface detected",
            confidence=0.9,
        )

    if _matches_any(text_blob, _NAVIGATION_ERROR_KEYWORDS):
        action = BrowserAgentAction(
            action_type="navigate" if target_url else "refresh",
            target_url=target_url,
            reason="navigation error detected",
        )
        return BrowserAgentDecision(
            outcome="continue",
            actions=(action,),
            blocker_kind="navigation_error",
            rationale="navigation error page detected",
            confidence=0.92,
        )

    if _matches_any(text_blob, _CAPTCHA_KEYWORDS):
        return BrowserAgentDecision(
            outcome="takeover_required",
            blocker_kind="captcha",
            rationale="captcha or slider verification detected",
            confidence=0.96,
            takeover=BrowserTakeoverNeed(
                blocker_kind="captcha",
                reason_code="captcha_detected",
                message="captcha detected",
                target_url=target_url or observation.current_url,
            ),
        )

    if _matches_any(text_blob, _SECURITY_KEYWORDS):
        return BrowserAgentDecision(
            outcome="takeover_required",
            blocker_kind="security_confirmation",
            rationale="security confirmation detected",
            confidence=0.93,
            takeover=BrowserTakeoverNeed(
                blocker_kind="security_confirmation",
                reason_code="security_confirmation_detected",
                message="security confirmation detected",
                target_url=target_url or observation.current_url,
            ),
        )

    if _matches_any(text_blob, _ACCOUNT_SELECTION_KEYWORDS):
        return BrowserAgentDecision(
            outcome="takeover_required",
            blocker_kind="account_selection",
            rationale="account chooser detected",
            confidence=0.92,
            takeover=BrowserTakeoverNeed(
                blocker_kind="account_selection",
                reason_code="account_selection_detected",
                message="account selection detected",
                target_url=target_url or observation.current_url,
            ),
        )

    if _login_like(observation, text_blob):
        return BrowserAgentDecision(
            outcome="takeover_required",
            blocker_kind="login",
            rationale="login gate detected from page text and url",
            confidence=0.85,
            takeover=BrowserTakeoverNeed(
                blocker_kind="login",
                reason_code="login_detected",
                message="login detected",
                target_url=target_url or observation.current_url,
            ),
        )

    if _matches_any(text_blob, _VERIFICATION_KEYWORDS):
        return BrowserAgentDecision(
            outcome="takeover_required",
            blocker_kind="verification",
            rationale="verification challenge detected",
            confidence=0.94,
            takeover=BrowserTakeoverNeed(
                blocker_kind="verification",
                reason_code="verification_detected",
                message="verification detected",
                target_url=target_url or observation.current_url,
            ),
        )

    dismiss_ref = _find_ref_by_keywords(observation, _DISMISS_KEYWORDS)
    if dismiss_ref and _matches_any(text_blob, _CONSENT_KEYWORDS + _POPUP_KEYWORDS):
        blocker_kind = (
            "consent_modal" if _matches_any(text_blob, _CONSENT_KEYWORDS) else "popup"
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
            confidence=0.8,
        )

    return BrowserAgentDecision(
        outcome="continue",
        blocker_kind="none",
        rationale="no generic blocker detected",
        confidence=0.5,
    )
