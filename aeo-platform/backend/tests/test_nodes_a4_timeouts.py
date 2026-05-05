import asyncio

import httpx

from app.core.constants import PlatformConstants
from app.workflow import nodes_a4


def test_browser_pipeline_timeout_uses_deepseek_override_for_multi_question_runs() -> (
    None
):
    timeout = nodes_a4._get_browser_pipeline_timeout("deepseek", 14)

    assert timeout == float(
        PlatformConstants.BROWSER_PIPELINE_TIMEOUT_OVERRIDES["deepseek"]
    )
    assert timeout > float(PlatformConstants.BROWSER_PIPELINE_TIMEOUT)


def test_browser_pipeline_timeout_keeps_default_cap_for_other_platforms() -> None:
    timeout = nodes_a4._get_browser_pipeline_timeout("kimi", 14)

    assert timeout == float(PlatformConstants.BROWSER_PIPELINE_TIMEOUT)


def test_browser_pipeline_timeout_preserves_single_question_human_budget() -> None:
    timeout = nodes_a4._get_browser_pipeline_timeout("kimi", 1)

    assert timeout == nodes_a4._get_browser_human_action_timeout("kimi")
    assert timeout > float(PlatformConstants.BROWSER_PIPELINE_TIMEOUT)


def test_browser_action_wait_timeout_is_capped_for_multi_question_runs() -> None:
    timeout = nodes_a4._get_browser_action_wait_timeout("kimi", 13)

    assert timeout == int(max(180.0, nodes_a4._get_browser_timeout("kimi") + 60.0))
    assert timeout < int(nodes_a4._BROWSER_ACTION_WAIT_TIMEOUT_SECONDS)


def test_browser_action_wait_timeout_preserves_single_question_budget() -> None:
    timeout = nodes_a4._get_browser_action_wait_timeout("deepseek", 1)

    assert timeout == int(nodes_a4._BROWSER_ACTION_WAIT_TIMEOUT_SECONDS)


def test_deepseek_runtime_page_failure_stops_platform_without_tripping_breaker() -> (
    None
):
    result = {
        "success": False,
        "error_type": "page_runtime_retry_or_risk_control",
        "failure_reason": "page_runtime_retry_or_risk_control",
    }

    assert nodes_a4._should_count_browser_failure_for_breaker(result) is False
    assert nodes_a4._should_stop_browser_platform_after_failure(result) is True


def test_legacy_risk_control_page_remains_soft_single_question_failure() -> None:
    result = {
        "success": False,
        "error_type": "risk_control_page",
        "failure_reason": "risk_control_page",
    }

    assert nodes_a4._should_count_browser_failure_for_breaker(result) is False
    assert nodes_a4._should_stop_browser_platform_after_failure(result) is False


class _FakeAioClient:
    aio_session_id = "aio-session"

    async def close(self) -> None:
        return None


class _FakeAioHandler:
    def __init__(self) -> None:
        self.client = _FakeAioClient()


async def test_browser_fetch_timeout_also_applies_to_aio_handlers() -> None:
    async def _slow_fetch(
        handler, question, profile, platform, platform_name, browser_state
    ):
        await asyncio.sleep(0.05)
        return {"success": True}

    result = await nodes_a4._browser_fetch_with_timeout(
        _slow_fetch,
        _FakeAioHandler(),
        "q",
        {},
        "kimi",
        "Kimi",
        object(),
        timeout=0.01,
    )

    assert result["success"] is False
    assert result["error_type"] == "question_timeout"


async def test_api_retry_fetch_converts_kimi_429_to_structured_failure(
    monkeypatch,
) -> None:
    monkeypatch.setattr(nodes_a4.settings, "A4_KIMI_API_MAX_RETRIES", 0)

    async def _rate_limited_fetch() -> dict[str, object]:
        request = httpx.Request("POST", "https://api.moonshot.cn/v1/chat/completions")
        response = httpx.Response(
            429,
            request=request,
            json={
                "error": {
                    "type": "rate_limit_reached_error",
                    "message": "try again after 7 seconds",
                }
            },
        )
        raise httpx.HTTPStatusError(
            "Client error '429 Too Many Requests'",
            request=request,
            response=response,
        )

    result = await nodes_a4._retry_fetch(
        _rate_limited_fetch,
        platform="kimi",
        method="api",
    )

    assert result["success"] is False
    assert result["platform"] == "kimi"
    assert result["platform_name"] == "Kimi"
    assert result["error_type"] == "api_rate_limited"
    assert result["provider_error_type"] == "rate_limit"
    assert result["retry_after_seconds"] == 7.0
    assert "api.moonshot.cn" not in result["error"]
    assert "api.moonshot.cn" not in result["error_detail"]
    assert "请求过于频繁" in result["error"]


def test_kimi_429_retry_wait_uses_configured_cooldown(monkeypatch) -> None:
    monkeypatch.setattr(nodes_a4.settings, "A4_KIMI_API_429_COOLDOWN_SECONDS", 20.0)

    assert nodes_a4._provider_429_retry_wait("kimi", "rate_limit", 7.0) == 20.0
    assert nodes_a4._provider_429_retry_wait("doubao", "rate_limit", 7.0) == 7.0


async def test_api_retry_fetch_recovers_after_kimi_429_cooldown(monkeypatch) -> None:
    monkeypatch.setattr(nodes_a4.settings, "A4_KIMI_API_MAX_RETRIES", 1)
    monkeypatch.setattr(nodes_a4.settings, "A4_KIMI_API_429_COOLDOWN_SECONDS", 20.0)
    sleeps: list[float] = []

    async def _sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(nodes_a4.asyncio, "sleep", _sleep)
    calls = 0

    async def _eventually_successful_fetch() -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            request = httpx.Request(
                "POST",
                "https://api.moonshot.cn/v1/chat/completions",
            )
            response = httpx.Response(
                429,
                request=request,
                json={
                    "error": {
                        "type": "rate_limit_reached_error",
                        "message": "try again after 7 seconds",
                    }
                },
            )
            raise httpx.HTTPStatusError(
                "Client error '429 Too Many Requests'",
                request=request,
                response=response,
            )
        return {"success": True, "platform": "kimi"}

    result = await nodes_a4._retry_fetch(
        _eventually_successful_fetch,
        platform="kimi",
        method="api",
    )

    assert result["success"] is True
    assert calls == 2
    assert sleeps == [20.0]


def test_supplemental_preserve_keeps_non_target_question_pairs() -> None:
    preserved = nodes_a4._derive_preserved_fetch_results(
        current_questions=[
            {"id": "q1", "text": "Q1"},
            {"id": "q2", "text": "Q2"},
        ],
        existing_fetch_results=[
            {
                "question_id": "q1",
                "question_text": "Q1",
                "platform_results": [
                    {"platform": "kimi", "answer": {"content": "old"}},
                    {"platform": "deepseek", "answer": {"content": "keep"}},
                ],
                "aio_platform_packets": [
                    {"platform": "kimi", "status": "result"},
                    {"platform": "deepseek", "status": "result"},
                ],
            },
            {
                "question_id": "q2",
                "question_text": "Q2",
                "platform_results": [
                    {"platform": "kimi", "answer": {"content": "keep"}},
                    {"platform": "deepseek", "answer": {"content": "keep"}},
                ],
                "aio_platform_packets": [
                    {"platform": "kimi", "status": "result"},
                    {"platform": "deepseek", "status": "result"},
                ],
            },
        ],
        selected_platforms={"kimi"},
        question_platform_targets={"q1": {"kimi"}},
    )

    pair_count = sum(len(item["platform_results"]) for item in preserved)
    q1_platforms = {
        result["platform"]
        for item in preserved
        if item["question_id"] == "q1"
        for result in item["platform_results"]
    }
    q2_platforms = {
        result["platform"]
        for item in preserved
        if item["question_id"] == "q2"
        for result in item["platform_results"]
    }

    assert pair_count == 3
    assert q1_platforms == {"deepseek"}
    assert q2_platforms == {"kimi", "deepseek"}
    assert [
        packet["platform"]
        for item in preserved
        if item["question_id"] == "q1"
        for packet in item["aio_platform_packets"]
    ] == ["deepseek"]


def test_domain_intelligence_contexts_cover_legacy_and_aio_citations() -> None:
    legacy_citation = {
        "title": "口腔清洁护理产品 - 京东",
        "url": "https://jingfen.jd.com/detail/example.html",
    }
    aio_citation = {
        "title": "post.smzdm.com",
        "url": "https://post.smzdm.com/talk/p/example/",
    }
    fetch_results = [
        {
            "question_id": "q1",
            "question_text": "Q1",
            "platform_results": [
                {
                    "platform": "yuanbao",
                    "citations": [legacy_citation],
                }
            ],
            "aio_platform_packets": [
                {
                    "platform": "deepseek",
                    "citations": [aio_citation],
                }
            ],
        }
    ]

    contexts = list(nodes_a4._iter_citation_intelligence_contexts(fetch_results))
    targets = nodes_a4._collect_citation_intelligence_targets(fetch_results)

    assert [context.citation for context in contexts] == [
        legacy_citation,
        aio_citation,
    ]
    assert [target.canonical_domain for target in targets] == [
        "jingfen.jd.com",
        "post.smzdm.com",
    ]
