import asyncio

import pytest

from app.core.asyncio_utils import wait_for_task_without_cancelling
from app.workflow.fetch_recovery import resolve_explicit_fetch_mode_from_text


def test_resolve_explicit_fetch_mode_from_fast_user_text() -> None:
    assert (
        resolve_explicit_fetch_mode_from_text(
            "请对理想汽车做品牌全景分析，并使用快速采集模式跑一遍。"
        )
        == "fast"
    )


def test_resolve_explicit_fetch_mode_from_full_user_text() -> None:
    assert resolve_explicit_fetch_mode_from_text("这次用完整采集跑一遍") == "full"


@pytest.mark.asyncio
async def test_wait_for_confirmation_does_not_cancel_running_task() -> None:
    task = asyncio.create_task(asyncio.sleep(0.2))

    completed = await wait_for_task_without_cancelling(task, timeout=0.01)
    assert completed is False
    assert not task.cancelled()
    await task
