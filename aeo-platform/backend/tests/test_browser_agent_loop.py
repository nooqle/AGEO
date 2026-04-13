from __future__ import annotations

import json
from types import SimpleNamespace

from app.core.fetchers.browser.browser_agent_contract import BrowserAgentLoopContext
from app.core.fetchers.browser.browser_agent_loop import (
    _BROWSER_AGENT_LLM_PAYLOAD_LIMIT,
    BrowserAgentBootstrapPolicy,
    LLMBrowserAgentPolicy,
    collect_browser_agent_step,
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
                    "text": "Log In",
                    "placeholder": "",
                }
            },
        }

    async def eval(self, script: str):
        return {"output": "Log in to Chat with Kimi for Free WeChat QR Code"}


async def test_collect_browser_agent_step_uses_bootstrap_policy():
    step = await collect_browser_agent_step(
        client=_FakeClient(),
        platform="kimi",
        loop_context=BrowserAgentLoopContext(
            platform="kimi",
            stage="preflight",
            target_url="https://kimi.com/",
        ),
        target_url="https://kimi.com/",
    )

    assert step.loop_context.stage == "preflight"
    assert step.observation.platform == "kimi"
    assert isinstance(BrowserAgentBootstrapPolicy(), BrowserAgentBootstrapPolicy)
    assert step.decision.outcome == "takeover_required"
    assert step.decision.blocker_kind == "login"


class _CaptureModel:
    def __init__(self):
        self.messages = None

    async def async_call(self, *, messages, temperature, max_tokens):
        self.messages = messages
        return SimpleNamespace(
            content=json.dumps(
                {
                    "outcome": "continue",
                    "blocker_kind": "none",
                    "confidence": 0.9,
                    "actions": [],
                },
                ensure_ascii=False,
            )
        )


async def test_llm_browser_policy_uses_compact_payload(monkeypatch):
    model = _CaptureModel()
    monkeypatch.setattr(
        "app.core.fetchers.browser.browser_agent_loop.get_llm_model",
        lambda: model,
    )

    client = _FakeClient()
    client.page._title = "Kimi AI" + " 页面" * 80

    step = await collect_browser_agent_step(
        client=client,
        platform="kimi",
        loop_context=BrowserAgentLoopContext(
            platform="kimi",
            stage="preflight",
            target_url="https://kimi.com/",
            note="请先判断当前是否仍然停留在登录页或已进入可提问主界面。" * 30,
            meta={"waited_seconds": 99, "action_type": "login"},
        ),
        target_url="https://kimi.com/",
        policy=LLMBrowserAgentPolicy(min_confidence=0.1),
    )

    assert step.decision.outcome == "continue"
    assert model.messages is not None
    payload = json.loads(model.messages[-1]["content"])
    assert len(model.messages[-1]["content"]) <= _BROWSER_AGENT_LLM_PAYLOAD_LIMIT
    assert payload["loop_context"]["stage"] == "preflight"
    assert payload["observation"]["screenshot"] is None
    assert len(payload["observation"]["interactive_refs"]) <= 8
