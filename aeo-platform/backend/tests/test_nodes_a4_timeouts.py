import asyncio

from app.core.constants import PlatformConstants
from app.workflow import nodes_a4


def test_browser_pipeline_timeout_caps_multi_question_runs() -> None:
    timeout = nodes_a4._get_browser_pipeline_timeout("deepseek", 12)

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


class _FakeAioClient:
    aio_session_id = "aio-session"

    async def close(self) -> None:
        return None


class _FakeAioHandler:
    def __init__(self) -> None:
        self.client = _FakeAioClient()


async def test_browser_fetch_timeout_also_applies_to_aio_handlers() -> None:
    async def _slow_fetch(handler, question, profile, platform, platform_name, browser_state):
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
