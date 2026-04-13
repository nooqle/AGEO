from __future__ import annotations

from app.core.fetchers.browser.browser_agent_contract import (
    BrowserAgentLoopContext,
    PlatformBrowserProfile,
    build_observation_slice,
    collect_browser_page_observation,
    get_observation_slice_profile,
    loop_context_to_llm_payload,
    observation_to_llm_payload,
    platform_profile_to_payload,
    requires_human_takeover,
)


class _FakePage:
    def __init__(self, url: str, title: str):
        self.url = url
        self._title = title

    def is_closed(self) -> bool:
        return False

    async def title(self) -> str:
        return self._title


class _FakeClient:
    def __init__(self):
        self.page = _FakePage("https://kimi.com/", "Kimi AI")

    async def snapshot(self, interactive_only: bool = True):
        return {
            "url": "https://kimi.com/",
            "refs": {
                "e0": {
                    "role": "button",
                    "tag": "button",
                    "text": "New Chat",
                    "placeholder": "",
                },
                "e1": {
                    "role": "textbox",
                    "tag": "textarea",
                    "text": "",
                    "placeholder": "Ask Anything...",
                },
            },
            "interactive_only": interactive_only,
        }

    async def eval(self, script: str):
        assert "document.body" in script
        return {"output": "KIMI\nAsk Anything...\nNew Chat"}


async def _fake_screenshot_provider():
    return {
        "content_type": "image/png",
        "image_base64": "ZmFrZQ==",
        "image_width": 1280,
        "image_height": 720,
    }


async def test_collect_browser_page_observation_captures_snapshot_and_text():
    observation = await collect_browser_page_observation(
        client=_FakeClient(),
        platform="kimi",
        screenshot_provider=_fake_screenshot_provider,
    )

    assert observation.platform == "kimi"
    assert observation.current_url == "https://kimi.com/"
    assert observation.title == "Kimi AI"
    assert observation.interactive_ref_count == 2
    assert "Ask Anything" in (observation.visible_text_excerpt or "")
    assert observation.screenshot is not None
    assert observation.meta["page_present"] is True
    assert observation.meta["page_closed"] is False
    assert observation.meta["snapshot_present"] is True
    assert observation.meta["screenshot_present"] is True


async def test_observation_to_llm_payload_compacts_refs():
    observation = await collect_browser_page_observation(
        client=_FakeClient(),
        platform="kimi",
    )

    payload = observation_to_llm_payload(
        observation,
        loop_context=BrowserAgentLoopContext(platform="kimi", stage="preflight"),
    )

    assert payload["platform"] == "kimi"
    assert payload["interactive_ref_count"] == 2
    assert len(payload["interactive_refs"]) == 2
    assert {item["ref"] for item in payload["interactive_refs"]} == {"e0", "e1"}
    assert any(
        item["placeholder"] == "Ask Anything..."
        for item in payload["interactive_refs"]
    )
    assert payload["screenshot"] is None
    assert set(payload["meta"].keys()) == {"page_present", "page_closed", "snapshot_present"}


def test_requires_human_takeover_marks_only_hard_blockers():
    assert requires_human_takeover("login") is True
    assert requires_human_takeover("verification") is True
    assert requires_human_takeover("captcha") is True
    assert requires_human_takeover("security_confirmation") is True
    assert requires_human_takeover("popup") is False
    assert requires_human_takeover("blank_page") is False
    assert requires_human_takeover("target_closed") is False


def test_loop_context_to_llm_payload_preserves_stage_and_meta():
    payload = loop_context_to_llm_payload(
        BrowserAgentLoopContext(
            platform="kimi",
            stage="resume_probe",
            target_url="https://kimi.com/",
            note="after manual resolve",
            meta={"waited_seconds": 12},
        )
    )

    assert payload["platform"] == "kimi"
    assert payload["stage"] == "resume_probe"
    assert payload["target_url"] == "https://kimi.com/"
    assert payload["note"] == "after manual resolve"
    assert payload["meta"] == {}


async def test_build_observation_slice_uses_stage_limits_and_no_default_screenshot():
    observation = await collect_browser_page_observation(
        client=_FakeClient(),
        platform="kimi",
        screenshot_provider=_fake_screenshot_provider,
    )

    payload = build_observation_slice(
        observation,
        loop_context=BrowserAgentLoopContext(platform="kimi", stage="wait_gate"),
    )

    assert payload["screenshot"] is None
    assert len(payload["interactive_refs"]) <= 6
    assert len(payload["visible_text_excerpt"]) <= 220
    assert set(payload["meta"].keys()) == {"page_present", "page_closed", "snapshot_present"}


def test_get_observation_slice_profile_exposes_stage_defaults():
    profile = get_observation_slice_profile("resume_probe")

    assert profile.visible_text_limit == 220
    assert profile.interactive_ref_limit == 6
    assert profile.loop_meta_keys == ("action_type",)


def test_platform_profile_to_payload_trims_patterns_and_hints():
    payload = platform_profile_to_payload(
        PlatformBrowserProfile(
            platform="kimi",
            entry_url="https://kimi.com/",
            ready_url_patterns=("a", "b", "c", "d"),
            login_url_patterns=("l1", "l2", "l3", "l4"),
            ready_hints=("h1", "h2", "h3", "h4", "h5"),
            login_hints=("i1", "i2", "i3", "i4", "i5"),
            late_blocker_hints=("x1", "x2", "x3", "x4", "x5"),
        )
    )

    assert payload["ready_url_patterns"] == ["a", "b", "c"]
    assert payload["login_url_patterns"] == ["l1", "l2", "l3"]
    assert payload["ready_hints"] == ["h1", "h2", "h3", "h4"]
    assert payload["login_hints"] == ["i1", "i2", "i3", "i4"]
    assert payload["late_blocker_hints"] == ["x1", "x2", "x3", "x4"]
