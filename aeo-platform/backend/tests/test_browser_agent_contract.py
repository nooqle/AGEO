from __future__ import annotations

from app.core.fetchers.browser.browser_agent_contract import (
    collect_browser_page_observation,
    observation_to_llm_payload,
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

    payload = observation_to_llm_payload(observation)

    assert payload["platform"] == "kimi"
    assert payload["interactive_ref_count"] == 2
    assert len(payload["interactive_refs"]) == 2
    assert payload["interactive_refs"][0]["ref"] == "e0"
    assert payload["interactive_refs"][1]["placeholder"] == "Ask Anything..."


def test_requires_human_takeover_marks_only_hard_blockers():
    assert requires_human_takeover("login") is True
    assert requires_human_takeover("verification") is True
    assert requires_human_takeover("captcha") is True
    assert requires_human_takeover("security_confirmation") is True
    assert requires_human_takeover("popup") is False
    assert requires_human_takeover("blank_page") is False
    assert requires_human_takeover("target_closed") is False
