import asyncio
from types import SimpleNamespace

import pytest

from app.core.fetchers.browser.browser_executor import (
    BrowserAnswerExecutionPlan,
    execute_post_submit_capture_flow,
    handle_browser_failure,
)
from app.core.fetchers.browser.parsers.base import ParsedResponse
from app.schemas.fetch import SearchReference


class _FakeHandler:
    PLATFORM_KEY = "fake"

    def __init__(self, dom_refs: list[SearchReference] | None = None):
        self.dom_refs = dom_refs or []
        self.dom_reference_calls = 0
        self.before_dom_calls = 0
        self.build_calls: list[dict] = []

    def _create_event(self, *args, **kwargs):
        return {"args": args, "kwargs": kwargs}

    async def _handle_browser_agent_empty_answer(self, *args, **kwargs):
        return [], False

    async def _extract_references_dom(self):
        self.dom_reference_calls += 1
        return list(self.dom_refs)

    async def before_dom_extract(self):
        self.before_dom_calls += 1

    async def _build_success_result(self, **kwargs):
        self.build_calls.append(kwargs)
        return SimpleNamespace(**kwargs)

    def _platform_display_name(self):
        return "Fake"


def _resolved_task(parsed: ParsedResponse):
    async def _return_parsed():
        return parsed

    return asyncio.create_task(_return_parsed())


@pytest.mark.asyncio
async def test_network_answer_with_zero_refs_falls_back_to_dom_references():
    dom_ref = SearchReference(
        index=1,
        title="Visible source",
        url="https://example.com/source",
    )
    handler = _FakeHandler(dom_refs=[dom_ref])
    parsed = ParsedResponse(
        answer_text="This is a sufficiently long network answer.",
        references=[],
        parse_ok=True,
    )

    result, _events = await execute_post_submit_capture_flow(
        handler,
        BrowserAnswerExecutionPlan(
            question="question",
            intercept_task=_resolved_task(parsed),
            fallback_url="https://example.com",
            before_dom_extract=handler.before_dom_extract,
        ),
    )

    assert result is not None
    assert result.search_references == [dom_ref]
    assert result.source == "network+dom_refs"
    assert handler.before_dom_calls == 1
    assert handler.dom_reference_calls == 1


@pytest.mark.asyncio
async def test_network_answer_with_refs_does_not_run_dom_reference_fallback():
    network_ref = SearchReference(
        index=1,
        title="Network source",
        url="https://example.com/network",
    )
    handler = _FakeHandler(
        dom_refs=[
            SearchReference(
                index=1,
                title="DOM source",
                url="https://example.com/dom",
            )
        ]
    )
    parsed = ParsedResponse(
        answer_text="This is a sufficiently long network answer.",
        references=[network_ref],
        parse_ok=True,
    )

    result, _events = await execute_post_submit_capture_flow(
        handler,
        BrowserAnswerExecutionPlan(
            question="question",
            intercept_task=_resolved_task(parsed),
            fallback_url="https://example.com",
            before_dom_extract=handler.before_dom_extract,
        ),
    )

    assert result is not None
    assert result.search_references == [network_ref]
    assert result.source == "network"
    assert handler.before_dom_calls == 0
    assert handler.dom_reference_calls == 0


@pytest.mark.asyncio
async def test_context_closed_capture_flow_is_retryable_client_failure():
    async def _raise_context_closed():
        raise RuntimeError(
            "Page.evaluate: Target page, context or browser has been closed"
        )

    handler = _FakeHandler()

    result, events = await execute_post_submit_capture_flow(
        handler,
        BrowserAnswerExecutionPlan(
            question="question",
            intercept_task=asyncio.create_task(_raise_context_closed()),
            fallback_url="https://example.com",
        ),
    )

    assert result is None
    assert len(events) == 1
    event = events[0]
    assert event["kwargs"]["error_type"] == "browser_context_closed"
    assert event["kwargs"]["failure_reason"] == "browser_context_closed"
    assert event["kwargs"]["failure_layer"] == "client"
    assert event["kwargs"]["retryable"] is True


@pytest.mark.asyncio
async def test_context_closed_failure_retries_once():
    closed = False
    states: list[dict] = []

    async def _close():
        nonlocal closed
        closed = True

    async def _send_browser_state(**kwargs):
        states.append(kwargs)

    async def _retry_fetch(**kwargs):
        return {"success": True, "retried": True}

    result = await handle_browser_failure(
        handler=SimpleNamespace(
            client=SimpleNamespace(close=_close),
            URL="https://chat.deepseek.com/",
        ),
        platform="deepseek",
        platform_name="DeepSeek",
        question="question",
        question_id=None,
        session_id="session-1",
        user_id=None,
        run_id=None,
        pending_action=None,
        error_message="Page.evaluate: Target page, context or browser has been closed",
        error_type="browser_context_closed",
        duration=0.0,
        question_count=1,
        timeout=90,
        is_retry=False,
        verify_recovery_count=0,
        max_verify_recoveries=3,
        auth_state_updated=False,
        should_defer_surface_open=lambda handler: True,
        emit_handoff=_retry_fetch,
        wait_for_outcome=_retry_fetch,
        resume_action=_retry_fetch,
        send_browser_state=_send_browser_state,
        send_reply=_retry_fetch,
        capture_evidence=_retry_fetch,
        build_failure_result=lambda **kwargs: kwargs,
        retry_fetch=_retry_fetch,
    )

    assert result == {"success": True, "retried": True}
    assert closed is True
    assert states[0]["state"] == "waiting_response"
