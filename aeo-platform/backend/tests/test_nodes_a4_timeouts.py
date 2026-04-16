from app.core.constants import PlatformConstants
from app.workflow import nodes_a4


def test_browser_pipeline_timeout_caps_multi_question_runs() -> None:
    timeout = nodes_a4._get_browser_pipeline_timeout("deepseek", 12)

    assert timeout == float(PlatformConstants.BROWSER_PIPELINE_TIMEOUT)


def test_browser_pipeline_timeout_preserves_single_question_human_budget() -> None:
    timeout = nodes_a4._get_browser_pipeline_timeout("kimi", 1)

    assert timeout == nodes_a4._get_browser_human_action_timeout("kimi")
    assert timeout > float(PlatformConstants.BROWSER_PIPELINE_TIMEOUT)
