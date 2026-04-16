from __future__ import annotations

from types import SimpleNamespace

import app.core.fetchers.browser.base_handler as base_handler_module
from app.core.fetchers.browser.base_handler import BaseBrowserHandler
from app.core.fetchers.browser.browser_agent_contract import (
    BrowserAgentAction,
    BrowserAgentDecision,
)
from app.core.fetchers.browser.deepseek_handler import DeepSeekHandler
from app.core.fetchers.browser.kimi_handler import KimiHandler
from app.schemas.fetch import Platform


class _DummyHandler(BaseBrowserHandler):
    URL = "https://kimi.com/"
    PLATFORM = Platform.KIMI
    PLATFORM_KEY = "kimi"

    async def fetch(self, question: str):
        if False:
            yield question


async def test_login_resume_probe_uses_browser_agent_when_page_is_ready(monkeypatch):
    async def _fake_collect(**kwargs):
        return SimpleNamespace(
            decision=BrowserAgentDecision(
                outcome="continue",
                blocker_kind="none",
                rationale="ready",
                confidence=0.9,
            )
        )

    monkeypatch.setattr(
        base_handler_module, "collect_browser_agent_step", _fake_collect
    )

    handler = _DummyHandler(client=SimpleNamespace(page=None))

    assert await handler.probe_resume_gate_ready("login") is True


async def test_login_resume_probe_stays_blocked_when_browser_agent_still_needs_takeover(
    monkeypatch,
):
    async def _fake_collect(**kwargs):
        return SimpleNamespace(
            decision=BrowserAgentDecision(
                outcome="takeover_required",
                blocker_kind="login",
                rationale="still blocked",
                confidence=0.95,
            )
        )

    monkeypatch.setattr(
        base_handler_module, "collect_browser_agent_step", _fake_collect
    )

    handler = _DummyHandler(client=SimpleNamespace(page=None))

    assert await handler.probe_resume_gate_ready("login") is False


async def test_login_resume_probe_runs_auto_action_before_ready(monkeypatch):
    decisions = iter(
        [
            SimpleNamespace(
                decision=BrowserAgentDecision(
                    outcome="continue",
                    blocker_kind="popup",
                    rationale="dismiss popup",
                    confidence=0.9,
                    actions=(
                        BrowserAgentAction(
                            action_type="wait",
                            wait_seconds=0.01,
                            reason="wait for auto recovery",
                        ),
                    ),
                )
            ),
            SimpleNamespace(
                decision=BrowserAgentDecision(
                    outcome="continue",
                    blocker_kind="none",
                    rationale="ready",
                    confidence=0.9,
                )
            ),
        ]
    )

    async def _fake_collect(**kwargs):
        return next(decisions)

    monkeypatch.setattr(
        base_handler_module, "collect_browser_agent_step", _fake_collect
    )

    handler = _DummyHandler(client=SimpleNamespace(page=None))

    assert await handler.probe_resume_gate_ready("login") is True


async def test_modal_resume_probe_prefers_browser_agent_ready_over_modal_scan(
    monkeypatch,
):
    async def _fake_collect(**kwargs):
        return SimpleNamespace(
            decision=BrowserAgentDecision(
                outcome="continue",
                blocker_kind="none",
                rationale="ready",
                confidence=0.88,
            )
        )

    monkeypatch.setattr(
        base_handler_module, "collect_browser_agent_step", _fake_collect
    )

    handler = _DummyHandler(client=SimpleNamespace(page=None))

    async def _fake_detect_modal():
        return "modal still present in stale selector path"

    monkeypatch.setattr(handler, "_detect_blocking_modal", _fake_detect_modal)

    assert await handler.probe_resume_gate_ready("modal") is True


async def test_wait_blocker_preserves_takeover_open_failure_event(monkeypatch):
    handler = _DummyHandler(client=SimpleNamespace(page=None))
    failure_event = object()

    async def _fake_emit(*args, **kwargs):
        return [failure_event], None

    monkeypatch.setattr(
        handler,
        "_emit_browser_agent_takeover_from_decision",
        _fake_emit,
    )

    events, handled = await handler._handle_browser_agent_wait_blocker(
        BrowserAgentDecision(
            outcome="takeover_required",
            blocker_kind="login",
            rationale="blocked",
            confidence=0.9,
        ),
        progress=0.7,
        fallback_url=handler.URL,
    )

    assert handled is True
    assert events == [failure_event]


async def test_parser_error_preserves_takeover_open_failure_event(monkeypatch):
    handler = _DummyHandler(client=SimpleNamespace(page=None))
    failure_event = object()

    async def _fake_emit(*args, **kwargs):
        return [failure_event], None

    monkeypatch.setattr(
        handler,
        "_emit_browser_agent_takeover_for_error_type",
        _fake_emit,
    )

    events, handled = await handler._handle_browser_agent_parser_error(
        parsed_error="auth required",
        error_type="auth_required",
        progress=0.7,
        fallback_url=handler.URL,
    )

    assert handled is True
    assert events == [failure_event]


async def test_empty_answer_preserves_takeover_open_failure_event(monkeypatch):
    handler = _DummyHandler(client=SimpleNamespace(page=None))
    failure_event = object()

    async def _fake_emit(*args, **kwargs):
        return [failure_event], None

    monkeypatch.setattr(
        handler,
        "_emit_browser_agent_takeover_for_current_page",
        _fake_emit,
    )

    events, handled = await handler._handle_browser_agent_empty_answer(
        "",
        progress=0.9,
        fallback_url=handler.URL,
    )

    assert handled is True
    assert events == [failure_event]


def test_kimi_resume_probe_context_uses_platform_specific_note():
    handler = KimiHandler(client=SimpleNamespace(page=None))

    context = handler._build_browser_agent_loop_context(
        stage="resume_probe",
        action_type="login",
        url=handler.URL,
    )

    assert context.note is not None
    assert "继续提问" in context.note
    assert "新建对话" in context.note
    assert "Ask Anything" in context.note
    assert context.meta["action_type"] == "login"


def test_deepseek_resume_probe_context_uses_platform_specific_note():
    handler = DeepSeekHandler(client=SimpleNamespace(page=None))

    context = handler._build_browser_agent_loop_context(
        stage="resume_probe",
        action_type="login",
        url=handler.URL,
    )

    assert context.note is not None
    assert "sign_in/login" in context.note
    assert context.meta["platform_display_name"] == "DeepSeek"
