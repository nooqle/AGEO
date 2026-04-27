import asyncio
from types import SimpleNamespace

import pytest

from app.core.fetchers.browser.browser_executor import (
    BrowserAnswerExecutionPlan,
    execute_post_submit_capture_flow,
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
