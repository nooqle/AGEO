"""Small asyncio helpers shared by runtime entrypoints."""

from __future__ import annotations

import asyncio


async def wait_for_task_without_cancelling(
    task: asyncio.Task,
    *,
    timeout: float,
) -> bool:
    """Return whether a task finished within timeout without cancelling it."""

    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        return False
