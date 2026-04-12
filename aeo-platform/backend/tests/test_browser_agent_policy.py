from __future__ import annotations

from app.core.fetchers.browser.browser_agent_contract import BrowserPageObservation
from app.core.fetchers.browser.browser_agent_policy import decide_browser_preflight


def _observation(
    *,
    url: str = "https://kimi.com/",
    title: str = "Kimi AI",
    text: str = "",
    refs: dict | None = None,
    meta: dict | None = None,
) -> BrowserPageObservation:
    return BrowserPageObservation(
        platform="kimi",
        current_url=url,
        title=title,
        interactive_snapshot={"refs": refs or {}},
        interactive_ref_count=len(refs or {}),
        visible_text_excerpt=text,
        screenshot=None,
        meta=meta or {},
    )


def test_policy_detects_login_gate_from_auth_modal_signals():
    observation = _observation(
        url="https://kimi.com/",
        text="Log in to Chat with Kimi for Free WeChat QR Code Verification code",
        refs={
            "e0": {
                "role": "button",
                "tag": "button",
                "text": "Log In",
                "placeholder": "",
            }
        },
    )

    decision = decide_browser_preflight(observation, target_url="https://kimi.com/")

    assert decision.outcome == "takeover_required"
    assert decision.blocker_kind == "login"
    assert decision.takeover is not None
    assert decision.takeover.reason_code == "login_detected"


def test_policy_detects_verification_gate():
    observation = _observation(
        url="https://www.doubao.com/chat/",
        text="请完成安全验证 human verification 点击验证",
    )

    decision = decide_browser_preflight(
        observation,
        target_url="https://www.doubao.com/chat/",
    )

    assert decision.outcome == "takeover_required"
    assert decision.blocker_kind == "verification"


def test_policy_dismisses_generic_popup_when_close_ref_exists():
    observation = _observation(
        text="Upgrade now download app not now later",
        refs={
            "e0": {
                "role": "button",
                "tag": "button",
                "text": "Not now",
                "placeholder": "",
            }
        },
    )

    decision = decide_browser_preflight(observation, target_url="https://kimi.com/")

    assert decision.outcome == "continue"
    assert decision.blocker_kind == "popup"
    assert len(decision.actions) == 2
    assert decision.actions[0].action_type == "click_ref"
    assert decision.actions[0].ref == "@e0"


def test_policy_refreshes_blank_page():
    observation = _observation(
        url="about:blank",
        title="",
        text="",
        refs={},
    )

    decision = decide_browser_preflight(observation, target_url="https://chat.deepseek.com/")

    assert decision.outcome == "continue"
    assert decision.blocker_kind == "blank_page"
    assert decision.actions[0].action_type == "navigate"
    assert decision.actions[0].target_url == "https://chat.deepseek.com/"


def test_policy_requests_target_resync_when_page_is_closed():
    observation = _observation(
        url="https://www.doubao.com/chat/",
        text="",
        refs={},
        meta={"page_closed": True},
    )

    decision = decide_browser_preflight(
        observation,
        target_url="https://www.doubao.com/chat/",
    )

    assert decision.outcome == "continue"
    assert decision.blocker_kind == "target_closed"
