"""Session-scoped event publishing boundary.

Workflow and orchestration code should emit through this adapter instead of
depending directly on the concrete WebSocket connection manager. This keeps the
event protocol stable while allowing the transport implementation to evolve.
"""

from __future__ import annotations

from typing import Protocol

from fastapi import WebSocket

from app.core.websocket_server import manager


class SessionEventPublisher(Protocol):
    """Transport-agnostic session event publisher."""

    async def emit_to_session(
        self,
        session_id: str,
        event: str,
        data: dict,
        *,
        bypass_runtime_guard: bool = False,
    ) -> None: ...

    async def emit_to_websocket(
        self,
        websocket: WebSocket,
        event: str,
        data: dict,
    ) -> None: ...


class WebSocketSessionEventPublisher:
    """Default publisher backed by the current WebSocket connection manager."""

    async def emit_to_session(
        self,
        session_id: str,
        event: str,
        data: dict,
        *,
        bypass_runtime_guard: bool = False,
    ) -> None:
        await manager.emit_to_session(
            session_id,
            event,
            data,
            bypass_runtime_guard=bypass_runtime_guard,
        )

    async def emit_to_websocket(
        self,
        websocket: WebSocket,
        event: str,
        data: dict,
    ) -> None:
        await manager.emit_to_websocket(websocket, event, data)


session_event_publisher: SessionEventPublisher = WebSocketSessionEventPublisher()
