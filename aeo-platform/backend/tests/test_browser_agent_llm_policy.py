from __future__ import annotations

from types import SimpleNamespace

import app.core.fetchers.browser.browser_agent_loop as browser_agent_loop
from app.core.fetchers.browser.browser_agent_contract import (
    BrowserAgentDecision,
    BrowserAgentLoopContext,
    BrowserPageObservation,
)
from app.core.fetchers.browser.browser_agent_loop import (
    BrowserAgentBootstrapPolicy,
    HybridBrowserAgentPolicy,
    LLMBrowserAgentPolicy,
    build_default_browser_agent_policy,
)


def _observation(text: str = "Upgrade now later") -> BrowserPageObservation:
    return BrowserPageObservation(
        platform="kimi",
        current_url="https://kimi.com/",
        title="Kimi",
        interactive_snapshot={
            "refs": {
                "e0": {
                    "role": "button",
                    "tag": "button",
                    "text": "Later",
                    "placeholder": "",
                }
            }
        },
        interactive_ref_count=1,
        visible_text_excerpt=text,
        screenshot=None,
        meta={},
    )


def _loop_context(stage: str = "preflight") -> BrowserAgentLoopContext:
    return BrowserAgentLoopContext(
        platform="kimi",
        stage=stage,
        target_url="https://kimi.com/",
    )


async def test_llm_browser_agent_policy_parses_json_response(monkeypatch):
    class _FakeModel:
        async def async_call(self, messages, tools=None, **kwargs):
            return SimpleNamespace(
                content="""
                {
                  "outcome": "continue",
                  "blocker_kind": "popup",
                  "rationale": "dismiss visible upsell modal",
                  "confidence": 0.83,
                  "actions": [
                    {
                      "action_type": "click_ref",
                      "ref": "@e0",
                      "reason": "close popup"
                    }
                  ]
                }
                """
            )

    monkeypatch.setattr(browser_agent_loop, "get_llm_model", lambda: _FakeModel())
    monkeypatch.setattr(
        browser_agent_loop,
        "get_settings",
        lambda: SimpleNamespace(
            BROWSER_AGENT_LLM_ENABLED=True,
            BROWSER_AGENT_LLM_MAX_CONCURRENCY=1,
            BROWSER_AGENT_LLM_MAX_TOKENS=384,
            BROWSER_AGENT_LLM_THINKING_ENABLED=False,
            BROWSER_AGENT_LLM_MODEL_NAME="glm-5",
        ),
    )

    decision = await LLMBrowserAgentPolicy().decide(
        _observation(),
        loop_context=_loop_context(),
    )

    assert decision is not None
    assert decision.outcome == "continue"
    assert decision.blocker_kind == "popup"
    assert decision.actions[0].action_type == "click_ref"
    assert decision.actions[0].ref == "@e0"


async def test_llm_browser_agent_policy_uses_browser_agent_limits(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeModel:
        async def async_call(self, messages, tools=None, **kwargs):
            captured["messages"] = messages
            captured["kwargs"] = kwargs
            return SimpleNamespace(
                content='{"outcome":"continue","blocker_kind":"none","confidence":0.8,"actions":[]}'
            )

    monkeypatch.setattr(browser_agent_loop, "get_llm_model", lambda: _FakeModel())
    monkeypatch.setattr(
        browser_agent_loop,
        "get_settings",
        lambda: SimpleNamespace(
            BROWSER_AGENT_LLM_ENABLED=True,
            BROWSER_AGENT_LLM_MAX_CONCURRENCY=2,
            BROWSER_AGENT_LLM_MAX_TOKENS=320,
            BROWSER_AGENT_LLM_THINKING_ENABLED=False,
            BROWSER_AGENT_LLM_MODEL_NAME="glm-4.7",
        ),
    )

    decision = await LLMBrowserAgentPolicy().decide(
        _observation(),
        loop_context=_loop_context(),
    )

    assert decision is not None
    assert captured["kwargs"] == {
        "temperature": 0.1,
        "max_tokens": 320,
        "thinking_enabled": False,
        "model": "glm-4.7",
        "response_format": {"type": "json_object"},
    }


def test_get_browser_agent_llm_model_uses_dedicated_api_key(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeGLM5Model:
        def __init__(self, config):
            captured["config"] = config

    monkeypatch.setattr(browser_agent_loop, "GLM5Model", _FakeGLM5Model)
    monkeypatch.setattr(
        browser_agent_loop,
        "get_settings",
        lambda: SimpleNamespace(
            LLM_PROVIDER="glm5",
            BROWSER_AGENT_LLM_API_KEY="browser-key",
            GLM5_BASE_URL="https://open.bigmodel.cn/api/paas/v4",
        ),
    )

    model = browser_agent_loop._get_browser_agent_llm_model()

    assert isinstance(model, _FakeGLM5Model)
    assert captured["config"].api_key == "browser-key"


def test_get_browser_agent_llm_model_falls_back_without_dedicated_key(monkeypatch):
    fallback_model = object()

    monkeypatch.setattr(browser_agent_loop, "get_llm_model", lambda: fallback_model)
    monkeypatch.setattr(
        browser_agent_loop,
        "get_settings",
        lambda: SimpleNamespace(
            LLM_PROVIDER="glm5",
            BROWSER_AGENT_LLM_API_KEY="",
        ),
    )

    model = browser_agent_loop._get_browser_agent_llm_model()

    assert model is fallback_model


async def test_hybrid_browser_agent_policy_keeps_bootstrap_takeover_outside_llm_stage(
    monkeypatch,
):
    class _UnexpectedLLMPolicy:
        async def decide(self, observation, *, loop_context):
            raise AssertionError(
                "llm policy should not run when bootstrap already decided"
            )

    observation = BrowserPageObservation(
        platform="kimi",
        current_url="https://kimi.com/",
        title="Kimi",
        interactive_snapshot={"refs": {}},
        interactive_ref_count=0,
        visible_text_excerpt="Log in to Chat with Kimi for Free QR Code",
        screenshot=None,
        meta={},
    )

    decision = await HybridBrowserAgentPolicy(
        bootstrap_policy=BrowserAgentBootstrapPolicy(),
        llm_policy=_UnexpectedLLMPolicy(),
    ).decide(
        observation,
        loop_context=_loop_context(stage="empty_answer"),
    )

    assert decision.outcome == "takeover_required"
    assert decision.blocker_kind == "login"


def test_build_default_browser_agent_policy_respects_setting(monkeypatch):
    monkeypatch.setattr(
        browser_agent_loop,
        "get_settings",
        lambda: SimpleNamespace(BROWSER_AGENT_LLM_ENABLED=True),
    )

    policy = build_default_browser_agent_policy()

    assert isinstance(policy, HybridBrowserAgentPolicy)


async def test_hybrid_browser_agent_policy_uses_llm_when_bootstrap_is_clear():
    class _FakeLLMPolicy:
        async def decide(self, observation, *, loop_context):
            return BrowserAgentDecision(
                outcome="continue",
                blocker_kind="popup",
                rationale="llm found popup",
                confidence=0.8,
            )

    decision = await HybridBrowserAgentPolicy(
        bootstrap_policy=BrowserAgentBootstrapPolicy(),
        llm_policy=_FakeLLMPolicy(),
    ).decide(
        _observation(text="page looks normal"),
        loop_context=_loop_context(stage="wait_gate"),
    )

    assert decision.blocker_kind == "popup"
    assert decision.rationale == "llm found popup"


async def test_hybrid_browser_agent_policy_prefers_llm_first_for_supported_stage():
    calls: list[str] = []

    class _BootstrapPolicy:
        async def decide(self, observation, *, loop_context):
            calls.append("bootstrap")
            return BrowserAgentDecision(
                outcome="continue",
                blocker_kind="none",
                rationale="bootstrap clear",
                confidence=0.2,
            )

    class _LLMPolicy:
        async def decide(self, observation, *, loop_context):
            calls.append("llm")
            return BrowserAgentDecision(
                outcome="takeover_required",
                blocker_kind="login",
                rationale="llm detected login blocker",
                confidence=0.9,
            )

    decision = await HybridBrowserAgentPolicy(
        bootstrap_policy=_BootstrapPolicy(),
        llm_policy=_LLMPolicy(),
    ).decide(
        _observation(text="page looks normal"),
        loop_context=_loop_context(stage="preflight"),
    )

    assert calls == ["llm"]
    assert decision.outcome == "takeover_required"
    assert decision.blocker_kind == "login"


def test_build_default_browser_agent_policy_is_hybrid_by_default(monkeypatch):
    monkeypatch.setattr(
        browser_agent_loop,
        "get_settings",
        lambda: SimpleNamespace(BROWSER_AGENT_LLM_ENABLED=False),
    )

    policy = build_default_browser_agent_policy()

    assert isinstance(policy, HybridBrowserAgentPolicy)
