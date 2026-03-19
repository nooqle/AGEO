"""Task domain event bus.

This keeps task lifecycle publishing decoupled from concrete transports
such as WebSocket while remaining lightweight for the current single-process
runtime.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TaskStatusChangedEvent:
    """Domain event emitted after a task lifecycle transition is committed."""

    session_id: str | None
    status: str
    task: dict[str, Any]


TaskStatusSubscriber = Callable[[TaskStatusChangedEvent], Awaitable[None]]


class TaskEventBus:
    """In-process async event publisher for task domain events."""

    def __init__(self) -> None:
        self._task_status_subscribers: list[TaskStatusSubscriber] = []

    def subscribe_task_status(self, subscriber: TaskStatusSubscriber) -> None:
        """Register a task status subscriber once."""

        if subscriber not in self._task_status_subscribers:
            self._task_status_subscribers.append(subscriber)

    def unsubscribe_task_status(self, subscriber: TaskStatusSubscriber) -> None:
        """Remove a previously registered task status subscriber."""

        self._task_status_subscribers = [
            current
            for current in self._task_status_subscribers
            if current is not subscriber
        ]

    async def publish_task_status(self, event: TaskStatusChangedEvent) -> None:
        """Fan out a committed task status event to all subscribers."""

        for subscriber in tuple(self._task_status_subscribers):
            try:
                await subscriber(event)
            except Exception:
                logger.exception(
                    "[TaskEventBus] Task status subscriber failed "
                    "(session=%s, status=%s)",
                    event.session_id,
                    event.status,
                )


task_event_bus = TaskEventBus()
